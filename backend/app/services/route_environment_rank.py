"""Rank only comparable assessments inside a finite candidate set."""

from app.services.geo import haversine_km
from app.services.route_environment import evaluate_route_group
from app.services.route_environment_sources import eligible_factors
from app.services.time_period import period_for


def ranking_score(assessment):
    if assessment.score is not None:
        return assessment.score
    return assessment.reference_score if assessment.evaluation_basis == "single_factor" else None


def assess_and_select(candidates, *, baseline_id, at, policy, indexes):
    """Shared production/offline selection; only feasible candidates define scoring evidence."""
    def distance(candidate):
        return sum(haversine_km(*a, *b) * 1000 for a, b in zip(candidate.points, candidate.points[1:]))
    baseline_candidate = next(c for c in candidates if c.candidate_id == baseline_id)
    length = distance(baseline_candidate)
    limit = length + min(length * policy.max_detour_ratio, policy.max_extra_minutes * 67)
    feasible = [c for c in candidates if distance(c) <= limit + 1e-6]
    baseline_factors, _ = eligible_factors(indexes, [baseline_candidate.points], period_for(at), policy)
    if baseline_factors:
        feasible = [c for c in feasible if baseline_factors.issubset(
            eligible_factors(indexes, [c.points], period_for(at), policy)[0])]
    evaluated = evaluate_route_group(feasible, at=at, policy=policy, indexes=indexes)
    baseline = next(r for r in evaluated if r.candidate.candidate_id == baseline_id)
    selected = rank_environment_routes(evaluated, baseline_distance_m=length, policy=policy)
    if not selected or all(ranking_score(r.assessment) is None for r in evaluated):
        selected = [baseline]
    return selected, evaluated, baseline


def rank_environment_routes(candidates, *, baseline_distance_m, policy):
    groups = {r.assessment.comparison_group_id for r in candidates}
    if len(groups) > 1:
        raise ValueError("Different comparison groups cannot be ranked together")
    limit = baseline_distance_m + min(baseline_distance_m * policy.max_detour_ratio, policy.max_extra_minutes * 67)
    eligible = [r for r in candidates if r.assessment.distance_m <= limit + 1e-6]
    if not eligible:
        return []
    scored = [r for r in eligible if ranking_score(r.assessment) is not None]
    if not scored:
        return [min(eligible, key=lambda r: r.assessment.distance_m)]
    bases = {("multi_factor", None) if r.assessment.score is not None else ("single_factor", r.assessment.reference_factor) for r in scored}
    if len(bases) > 1:
        raise ValueError("Different evidence bases cannot be ranked together")
    best = max(ranking_score(r.assessment) for r in scored)
    scored = [r for r in scored if ranking_score(r.assessment) >= best - policy.score_tolerance]
    if all(r.assessment.longest_support_gap_m is not None for r in scored):
        return sorted(scored, key=lambda r: (r.assessment.longest_support_gap_m, r.assessment.total_support_gap_m,
                                             -ranking_score(r.assessment), r.assessment.distance_m, r.candidate.candidate_id))
    return sorted(scored, key=lambda r: (-ranking_score(r.assessment), r.assessment.distance_m, r.candidate.candidate_id))
