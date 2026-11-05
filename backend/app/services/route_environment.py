"""Common coordinate-based assessment for OSM and Tmap; no dong scores."""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math

import numpy as np

from app.services.geo import haversine_km
from app.services.facility_assessment import MODEL_VERSION, AssessmentSample, assess_facility_samples
from app.services.poi_factors import to_meters
from app.services.route_environment_gaps import summarize_gaps
from app.services.route_environment_sources import EnvironmentIndex, eligible_factors
from app.services.time_period import KST, period_for

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
    observed_facility_counts: dict[str, int] = field(default_factory=dict)
    observed_factor_coverage: dict[str, float] = field(default_factory=dict)
    evaluation_basis: str = "unavailable"
    reference_score: float | None = None
    reference_factor: str | None = None
    score_bounds: dict[str, float] | None = None
    factor_evaluation_ratio: dict[str, float] = field(default_factory=dict)
    verified_distance_ratio: float = 0.0
    evidence_factors: list[str] = field(default_factory=list)


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
    cells = sample_route(points, step_m=policy.step_m)
    assessment, _ = evaluate_route_cells(cells, at=at, policy=policy, indexes=indexes, common_factors=common_factors,
                                         excluded_factors=excluded_factors, comparison_group_id=comparison_group_id)
    return assessment


def evaluate_route_cells(cells, *, at, policy, indexes, common_factors=frozenset(), excluded_factors=None,
                         comparison_group_id=""):
    """One evaluation supplies both the route summary and its ordered facility observations."""
    period = period_for(at)
    length = cells[-1].end_m if cells else 0.0
    shared = assess_facility_samples([AssessmentSample(str(i), c.midpoint, c.end_m - c.start_m) for i, c in enumerate(cells)],
                                    scope="route", at=at, policy=policy, indexes=indexes, common_factors=common_factors,
                                    excluded_factors=excluded_factors, comparison_basis_id=comparison_group_id)
    observations = {f: [o.factors[f].comparison_present for o in shared.observations] for f in sorted(common_factors)}
    coverage = shared.factor_coverage
    meters = to_meters([c.midpoint for c in cells])
    active = shared.active_factors
    gaps = summarize_gaps(cells, observations, period=period, common_factors=common_factors)
    observed_counts, observed_coverage = {}, {}
    # Partial coordinates prove presence only. They never enter the composite score or gap ranking.
    for factor in sorted({e.source.factor for e in indexes.sources}):
        hits, schedule_hits, present = set(), set(), np.zeros(len(cells), dtype=bool)
        for entry in indexes.sources:
            if entry.source.factor != factor or entry.tree is None or not cells:
                continue
            if factor == "open_store" and entry.source.opening_hours_evidence and entry.source.opening_hours and not entry.source.is_open(at):
                continue
            found = entry.tree.query_ball_point(meters, r=policy.radius(factor))
            for i, numbers in enumerate(found):
                present[i] |= bool(numbers)
                hits.update(entry.source.points[n] for n in numbers)
                if entry.source.schedule_status == "published_schedule":
                    schedule_hits.update(entry.source.points[n] for n in numbers)
        key = "store" if factor == "open_store" else factor
        observed_counts[key] = len(hits)
        if factor == "open_store" and any(e.source.schedule_status == "published_schedule" for e in indexes.sources):
            observed_counts["store_with_published_hours"] = len(schedule_hits)
        if factor != "open_store":
            observed_coverage[factor] = sum((c.end_m - c.start_m) for c, p in zip(cells, present) if p) / length if length else 0.0
    # Observations of inactive factors remain visible, without affecting the active-factor score.
    basis = "observed_only" if shared.evaluation_basis == "unavailable" and any(observed_counts.values()) else shared.evaluation_basis
    assessment = EnvironmentAssessment(MODEL_VERSION, policy.version, shared.status,
                                 period, length, shared.score, active, sorted(common_factors), excluded_factors or {}, coverage,
                                 len(common_factors) / len(active), source_versions=shared.source_versions,
                                 comparison_group_id=comparison_group_id, observed_facility_counts=observed_counts,
                                 observed_factor_coverage=observed_coverage, evaluation_basis=basis,
                                 reference_score=shared.reference_score, reference_factor=shared.reference_factor,
                                 score_bounds=shared.score_bounds,
                                 factor_evaluation_ratio=shared.factor_evaluation_ratio,
                                 verified_distance_ratio=shared.verified_distance_ratio, evidence_factors=shared.evidence_factors, **gaps)
    return assessment, shared.observations


def evaluate_route_group(candidates, *, at, policy, indexes: EnvironmentIndex) -> list[EvaluatedRoute]:
    at = at or datetime.now(KST)
    common, excluded = eligible_factors(indexes, [c.points for c in candidates], period_for(at), policy)
    identity = dict(policy=policy.fingerprint(), assessment="evidence-fallback-v1", at=at.isoformat(), factors=sorted(common),
                    sources=sorted((e.source.source_id, e.source.sha256) for e in indexes.sources))
    group_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return [EvaluatedRoute(c, evaluate_route_environment(c.points, at=at, policy=policy, indexes=indexes, common_factors=common,
                            excluded_factors=excluded, comparison_group_id=group_id)) for c in candidates]
