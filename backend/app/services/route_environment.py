"""Common coordinate-based assessment for OSM and Tmap; no dong scores."""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math

import numpy as np

from app.services.geo import haversine_km
from app.services.poi_factors import to_meters
from app.services.route_environment_gaps import summarize_gaps
from app.services.route_environment_sources import EnvironmentIndex, eligible_factors
from app.services.time_period import KST, period_for

MODEL_VERSION = "facility-access-v1"


@dataclass
class RouteCell:
    start_m: float
    end_m: float
    midpoint: tuple[float, float]


@dataclass
class EnvironmentAssessment:
    model_version: str
    policy_version: str
    status: str
    period: str
    distance_m: float
    score: float | None
    active_factors: list[str]
    used_factors: list[str]
    excluded_factors: dict[str, str]
    factor_coverage: dict[str, float]
    data_factor_availability_ratio: float
    longest_support_gap_m: float | None
    total_support_gap_m: float | None
    gap_intervals: list[dict]
    source_versions: dict[str, str]
    comparison_group_id: str
    per_factor_gaps: dict[str, list[dict]] = field(default_factory=dict)


@dataclass
class RouteCandidate:
    candidate_id: str
    points: list[tuple[float, float]]
    source: str


@dataclass
class EvaluatedRoute:
    candidate: RouteCandidate
    assessment: EnvironmentAssessment


def sample_route(points, *, step_m: float) -> list[RouteCell]:
    if not math.isfinite(step_m) or step_m <= 0:
        raise ValueError("step_m must be positive")
    segments, total = [], 0.0
    for a, b in zip(points, points[1:]):
        length = haversine_km(*a, *b) * 1000
        if length > 0:
            segments.append((total, total + length, a, b))
            total += length
    cells, index = [], 0
    for start in np.arange(0, total, step_m):
        end = min(float(start) + step_m, total)
        mid = (start + end) / 2
        while index + 1 < len(segments) and mid >= segments[index][1]:
            index += 1
        lo, hi, a, b = segments[index]
        t = (mid - lo) / (hi - lo)
        point = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        cells.append(RouteCell(float(start), end, point))
    return cells


def evaluate_route_environment(points, *, at, policy, indexes, sources=None, common_factors=frozenset(), excluded_factors=None,
                               comparison_group_id="") -> EnvironmentAssessment:
    period = period_for(at)
    cells = sample_route(points, step_m=policy.step_m)
    length = cells[-1].end_m if cells else 0.0
    observations, coverage = {}, {}
    meters = to_meters([c.midpoint for c in cells])
    for factor in sorted(common_factors):
        present = np.zeros(len(cells), dtype=bool)
        for entry in indexes.sources:
            if entry.source.factor == factor and entry.source.eligible() and entry.source.is_open(at) and entry.tree is not None and cells:
                present |= entry.tree.query_ball_point(meters, r=policy.radius(factor), return_length=True) > 0
        observations[factor] = present.tolist()
        coverage[factor] = sum((c.end_m - c.start_m) for c, p in zip(cells, present) if p) / length if length else 0.0
    score = 100 * sum(coverage.values()) / len(coverage) if len(coverage) >= 2 and length else None
    active = list(policy.active_factors(period))
    gaps = summarize_gaps(cells, observations, period=period, common_factors=common_factors)
    return EnvironmentAssessment(MODEL_VERSION, policy.version, "available" if score is not None and len(coverage) == len(active) else "degraded" if score is not None else "unavailable",
                                 period, length, score, active, sorted(common_factors), excluded_factors or {}, coverage,
                                 len(common_factors) / len(active), source_versions={e.source.source_id: e.source.sha256 for e in indexes.sources if e.source.factor in common_factors and e.source.eligible()},
                                 comparison_group_id=comparison_group_id, **gaps)


def evaluate_route_group(candidates, *, at, policy, indexes: EnvironmentIndex) -> list[EvaluatedRoute]:
    at = at or datetime.now(KST)
    common, excluded = eligible_factors(indexes, [c.points for c in candidates], period_for(at), policy)
    identity = dict(policy=policy.fingerprint(), at=at.isoformat(), factors=sorted(common),
                    sources=sorted((e.source.source_id, e.source.sha256) for e in indexes.sources))
    group_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return [EvaluatedRoute(c, evaluate_route_environment(c.points, at=at, policy=policy, indexes=indexes, common_factors=common,
                            excluded_factors=excluded, comparison_group_id=group_id)) for c in candidates]
