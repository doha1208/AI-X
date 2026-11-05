"""Shared facility evidence and length weighting, independent of route geometry."""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math
from typing import Literal

import numpy as np
from shapely import points as geo_points

from app.services.poi_factors import Point, to_meters
from app.services.route_environment_sources import EnvironmentIndex, coverage_known_mask
from app.services.time_period import KST, Period, period_for

MODEL_VERSION = "facility-access-v1"
Scope = Literal["route", "area", "zone"]
EvidenceState = Literal["present", "absent_in_verified_inventory", "unknown"]


@dataclass(frozen=True)
class AssessmentSample:
    sample_id: str
    point: Point
    weight: float

    def __post_init__(self):
        if not math.isfinite(self.weight) or self.weight <= 0:
            raise ValueError("Sample weight must be finite and positive")


@dataclass(frozen=True)
class FactorEvidence:
    state: EvidenceState
    comparison_present: bool
    comparison_known: bool
    observed_present: bool


@dataclass(frozen=True)
class FacilityObservation:
    point: Point
    factors: dict[str, FactorEvidence]


@dataclass(frozen=True)
class LocalFacilityEvidence:
    point: Point
    factors: dict[str, FactorEvidence]
    period: Period
    model_version: str
    policy_version: str
    assessed_at: datetime
    source_versions: dict[str, str]
    artifact_version: str | None = None


@dataclass
class FacilityAssessment:
    scope: Scope
    period: Period
    sampled_length_m: float
    score: float | None
    reference_score: float | None
    reference_factor: str | None
    evaluation_basis: str
    status: str
    active_factors: list[str]
    used_factors: list[str]
    factor_coverage: dict[str, float]
    score_bounds: dict[str, float] | None
    factor_evaluation_ratio: dict[str, float]
    verified_distance_ratio: float
    evidence_factors: list[str]
    source_versions: dict[str, str]
    model_version: str
    policy_version: str
    assessed_at: datetime
    comparison_basis_id: str
    observations: list[FacilityObservation] = field(repr=False)
    weight_unit: str = "metre"
    artifact_version: str | None = None
    reference_at: datetime | None = None
    excluded_factors: dict[str, str] = field(default_factory=dict)
    unavailable_reason: str | None = None


def _moment(at):
    moment = at if at is not None else datetime.now(KST)
    return moment.replace(tzinfo=KST) if moment.tzinfo is None else moment.astimezone(KST)


def observe_facilities(points, *, at, policy, indexes: EnvironmentIndex, period=None) -> list[FacilityObservation]:
    """Partial verified positions prove presence; only complete coverage proves absence."""
    moment = _moment(at)
    active = policy.active_factors(period or period_for(moment))
    coords = [tuple(p) for p in points]
    meters = to_meters(coords)
    locations = geo_points(meters[:, [1, 0]]) if coords else None
    factors = [dict() for _ in coords]
    for factor in active:
        positive = np.zeros(len(coords), dtype=bool)
        comparison = np.zeros(len(coords), dtype=bool)
        observed = np.zeros(len(coords), dtype=bool)
        for entry in indexes.sources:
            source = entry.source
            if source.factor != factor or entry.tree is None or not coords:
                continue
            is_open = source.is_open(moment)
            may_observe = not (factor == "open_store" and source.opening_hours_evidence and source.opening_hours and not is_open)
            presence_eligible = source.presence_eligible() and is_open
            comparison_eligible = source.eligible() and is_open
            if not (may_observe or presence_eligible or comparison_eligible):
                continue
            hits = entry.tree.query_ball_point(meters, r=policy.radius(factor), return_length=True) > 0
            if presence_eligible:
                positive |= hits
            if comparison_eligible:
                comparison |= hits
            if may_observe:
                observed |= hits
        covered = coverage_known_mask(indexes, factor, locations, policy.radius(factor)) if coords else np.zeros(0, dtype=bool)
        for i in range(len(coords)):
            state = "present" if positive[i] else "absent_in_verified_inventory" if covered[i] else "unknown"
            factors[i][factor] = FactorEvidence(state, bool(comparison[i]), bool(covered[i] or comparison[i]), bool(observed[i]))
    return [FacilityObservation(point, values) for point, values in zip(coords, factors)]


def summarize_facility_evidence(samples, observations, *, active_factors):
    weights = np.asarray([sample.weight for sample in samples], dtype=float)
    length = float(weights.sum())
    ratios, evidence_factors = {}, []
    any_known = np.zeros(len(samples), dtype=bool)
    positive_length = unknown_length = 0.0
    for factor in active_factors:
        positive = np.asarray([o.factors[factor].state == "present" for o in observations], dtype=bool)
        known = np.asarray([o.factors[factor].state != "unknown" for o in observations], dtype=bool)
        ratios[factor] = float(weights[known].sum() / length) if length else 0.0
        if np.any(known):
            evidence_factors.append(factor)
        any_known |= known
        positive_length += float(weights[positive].sum())
        unknown_length += float(weights[~known].sum())
    denominator = length * len(active_factors)
    bounds = {"lower": 100 * positive_length / denominator,
              "upper": min(100.0, 100 * (positive_length + unknown_length) / denominator)} if denominator and evidence_factors else None
    return {"evidence_factors": sorted(evidence_factors), "factor_evaluation_ratio": ratios,
            "verified_distance_ratio": float(weights[any_known].sum() / length) if length else 0.0, "bounds": bounds}


def _source_versions(indexes, evidence_factors):
    return {e.source.source_id: e.source.sha256 for e in indexes.sources
            if e.source.factor in evidence_factors and e.source.presence_eligible()}


def assess_local_facilities(point, *, at, policy, indexes, artifact_version=None) -> LocalFacilityEvidence:
    moment = _moment(at)
    observation = observe_facilities([point], at=moment, policy=policy, indexes=indexes)[0]
    evidence = {f for f, value in observation.factors.items() if value.state != "unknown"}
    return LocalFacilityEvidence(observation.point, observation.factors, period_for(moment), MODEL_VERSION, policy.version,
                                 moment, _source_versions(indexes, evidence), artifact_version)


def assess_facility_samples(samples, *, scope: Scope, at, policy, indexes, common_factors=frozenset(),
                            excluded_factors=None, comparison_basis_id="", artifact_version=None, reference_at=None) -> FacilityAssessment:
    if scope not in {"route", "area", "zone"}:
        raise ValueError("Length assessment requires route, area or zone scope")
    samples = list(samples)
    moment = _moment(at)
    period = period_for(moment)
    active = list(policy.active_factors(period))
    common = sorted(common_factors)
    if not set(common).issubset(active):
        raise ValueError("Comparison factors must be active in the requested period")
    observations = observe_facilities([s.point for s in samples], at=moment, policy=policy, indexes=indexes)
    if any(not o.factors[f].comparison_known for f in common for o in observations):
        raise ValueError("Comparison factors require verified evidence for every sample")
    length = float(sum(s.weight for s in samples))
    coverage = {f: sum(s.weight for s, o in zip(samples, observations) if o.factors[f].comparison_present) / length if length else 0.0
                for f in common}
    score = 100 * sum(coverage.values()) / len(coverage) if len(coverage) >= 2 and length else None
    reference_factor = next(iter(coverage)) if len(coverage) == 1 and length else None
    reference_score = 100 * coverage[reference_factor] if reference_factor else None
    evidence = summarize_facility_evidence(samples, observations, active_factors=active)
    observed = any(v.observed_present for o in observations for v in o.factors.values())
    basis = "multi_factor" if score is not None else "single_factor" if reference_score is not None else "partial_coverage" if evidence["bounds"] else "observed_only" if observed else "unavailable"
    status = "available" if score is not None and len(common) == len(active) else "degraded" if basis in {"multi_factor", "single_factor", "partial_coverage"} else "unavailable"
    if not comparison_basis_id:
        identity = {"scope": scope, "model": MODEL_VERSION, "policy": policy.fingerprint(), "factors": common,
                    "period": period, "weekday": moment.weekday(), "time": moment.strftime("%H:%M")}
        comparison_basis_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return FacilityAssessment(scope=scope, period=period, sampled_length_m=length, score=score,
        reference_score=reference_score, reference_factor=reference_factor, evaluation_basis=basis, status=status,
        active_factors=active, used_factors=common, factor_coverage=coverage,
        score_bounds=evidence["bounds"] if basis == "partial_coverage" else None,
        factor_evaluation_ratio=evidence["factor_evaluation_ratio"], verified_distance_ratio=evidence["verified_distance_ratio"],
        evidence_factors=evidence["evidence_factors"], source_versions=_source_versions(indexes, evidence["evidence_factors"]),
        model_version=MODEL_VERSION, policy_version=policy.version, assessed_at=moment,
        comparison_basis_id=comparison_basis_id, observations=observations, artifact_version=artifact_version,
        reference_at=reference_at, excluded_factors=dict(excluded_factors or {}),
        unavailable_reason="no_walk_samples" if not samples else "verified_facility_evidence_missing" if basis in {"observed_only", "unavailable"} else None)
