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
    values = [route("best-score", 80, 400, 20), route("short-gap", 78, 100, 23), route("too-low", 74, 0, 20), route("too-long", 80, 0, 23.01)]
    result = rank_environment_routes(values, baseline_distance_m=1340, policy=EnvironmentPolicy())
    assert [r.candidate.candidate_id for r in result] == ["short-gap", "best-score"]


def test_keeps_candidates_up_to_five_points_below_best_and_excludes_lower_scores():
    values = [route("best", 80, 400, 10), route("four-below", 76, 100, 10),
              route("five-below", 75, 50, 10), route("over-five", 74.99, 0, 10)]
    result = rank_environment_routes(values, baseline_distance_m=670, policy=EnvironmentPolicy())
    assert [r.candidate.candidate_id for r in result] == ["five-below", "four-below", "best"]


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


def test_candidate_outside_scope_does_not_remove_baseline_verified_factors():
    from test_route_environment import source, POINTS, NIGHT
    from app.services.route_environment_sources import build_environment_index
    from app.services.route_environment_rank import assess_and_select
    cctv = source("cctv", [(37.5009,127)])
    cctv.coverage_geometry = {"type":"Polygon","coordinates":[[[126.9,37.4],[127.00072,37.4],[127.00072,37.6],[126.9,37.6],[126.9,37.4]]]}
    baseline = RouteCandidate("baseline",POINTS,"tmap")
    outside = RouteCandidate("outside",[POINTS[0],(37.5009,127.00012),POINTS[-1]],"osm")
    selected, evaluated, _ = assess_and_select([baseline,outside],baseline_id="baseline",at=NIGHT,policy=EnvironmentPolicy(),indexes=build_environment_index([cctv,source("bell")]))
    assert selected[0].assessment.score is not None
    assert selected[0].assessment.used_factors == ["bell","cctv"]
    assert len(evaluated) == 1


def test_single_factor_references_use_the_same_five_point_band():
    values = [route("best",None,None,10),route("within",None,None,10),route("outside",None,None,10)]
    for value, score in zip(values,[80,75,74.99]):
        value.assessment.evaluation_basis = "single_factor"
        value.assessment.reference_factor = "bell"
        value.assessment.reference_score = score
    result = rank_environment_routes(values,baseline_distance_m=670,policy=EnvironmentPolicy())
    assert [r.candidate.candidate_id for r in result] == ["best","within"]
