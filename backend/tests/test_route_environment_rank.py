from dataclasses import replace

from app.services.route_environment import EnvironmentAssessment, EvaluatedRoute, RouteCandidate
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_rank import rank_environment_routes


def route(name, score, gap, minutes):
    a = EnvironmentAssessment("facility-access-v1", "environment-v1-draft", "degraded", "night", minutes * 67,
                              score, ["lighting", "open_store"], ["lighting", "open_store"], {}, {}, 0.5,
                              gap, gap, [], {}, "same-group")
    return EvaluatedRoute(RouteCandidate(name, [(37.5, 127), (37.501, 127)], "osm"), a)


def test_chooses_shorter_gap_within_score_tolerance_and_detour_budget():
    values = [route("best-score", 80, 400, 20), route("short-gap", 78, 100, 23), route("too-low", 76, 0, 20), route("too-long", 80, 0, 23.01)]
    result = rank_environment_routes(values, baseline_distance_m=1340, policy=EnvironmentPolicy())
    assert [r.candidate.candidate_id for r in result] == ["short-gap", "best-score"]


def test_short_route_uses_ratio_limit_not_just_three_minutes():
    values = [route("within", 80, 100, 12), route("outside", 90, 0, 12.01)]
    assert [r.candidate.candidate_id for r in rank_environment_routes(values, baseline_distance_m=670, policy=EnvironmentPolicy())] == ["within"]


def test_unknown_gap_never_behaves_like_zero():
    values = [route("known", 80, 100, 10), route("unknown", 79, None, 10)]
    assert rank_environment_routes(values, baseline_distance_m=670, policy=EnvironmentPolicy())[0].candidate.candidate_id == "known"


def test_no_scores_returns_only_shortest_general_route():
    values = [route("long", None, None, 11), route("general", None, None, 10)]
    assert [r.candidate.candidate_id for r in rank_environment_routes(values, baseline_distance_m=670, policy=EnvironmentPolicy())] == ["general"]


def test_cannot_mix_different_comparison_groups():
    values = [route("a", 80, 0, 10), route("b", 90, 0, 10)]
    values[1].assessment = replace(values[1].assessment, comparison_group_id="other")
    import pytest
    with pytest.raises(ValueError, match="comparison"):
        rank_environment_routes(values, baseline_distance_m=670, policy=EnvironmentPolicy())
