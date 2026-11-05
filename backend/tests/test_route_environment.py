from datetime import datetime

import pytest

from app.services.route_environment import RouteCandidate, evaluate_route_group, sample_route
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_sources import FacilitySource, build_environment_index
from app.services.time_period import KST


AREA = {"type": "Polygon", "coordinates": [[[126, 37], [128, 37], [128, 38], [126, 38], [126, 37]]]}
NIGHT = datetime(2026, 11, 4, 23, tzinfo=KST)
POINTS = [(37.5, 127.0), (37.5018, 127.0)]  # about 200m


def source(factor, points=(), **kw):
    return FacilitySource(source_id=factor, factor=factor, source_url="https://data.go.kr/test",
                          observed_at="2026-11-01", retrieved_at="2026-11-04", sha256="a" * 64,
                          coverage_geometry=AREA, completeness="verified_complete",
                          purpose="crime_prevention" if factor == "cctv" else None,
                          opening_hours={str(d): [[0, 1440]] for d in range(7)} if factor == "open_store" else None,
                          opening_hours_evidence="official hours" if factor == "open_store" else None,
                          points=list(points), **kw)


def evaluate(sources, paths=None, at=NIGHT):
    paths = paths or [POINTS]
    return evaluate_route_group([RouteCandidate(str(i), p, "osm") for i, p in enumerate(paths)],
                                at=at, policy=EnvironmentPolicy(), indexes=build_environment_index(sources))


def test_same_geometry_with_extra_vertices_has_same_length_weighted_score():
    sources = [source("cctv", [(37.5009, 127)]), source("bell", [(37.5009, 127)])]
    a, b = evaluate(sources, [POINTS, [POINTS[0], (37.5009, 127), POINTS[1]]])
    assert a.assessment.score == pytest.approx(b.assessment.score, abs=0.1)
    assert a.assessment.factor_coverage["bell"] == 1
    assert 65 < a.assessment.score < 85
    assert a.assessment.comparison_group_id == b.assessment.comparison_group_id


def test_partial_missing_and_official_zero_are_not_interchangeable():
    partial = source("lighting")
    partial.completeness = "partial"
    result = evaluate([partial, source("cctv")])[0].assessment
    assert result.score is None
    assert "lighting" in result.excluded_factors
    assert result.factor_coverage["cctv"] == 0
    assert result.longest_support_gap_m is None


def test_unverified_hours_and_cctv_purpose_are_excluded():
    shop, cctv = source("open_store"), source("cctv")
    shop.opening_hours_evidence = None
    cctv.purpose = None
    result = evaluate([shop, cctv])[0].assessment
    assert result.used_factors == []
    assert result.score is None


def test_partial_coordinates_are_observed_without_inventing_composite_scores():
    bell = source("bell", [(37.5009, 127)])
    bell.completeness = "partial"
    shop = source("open_store", [(37.5009, 127)])
    shop.opening_hours_evidence = None
    result = evaluate([bell, shop])[0].assessment
    assert result.score is None
    assert result.observed_facility_counts["bell"] == 1
    assert result.observed_facility_counts["store"] == 1
    assert result.observed_factor_coverage["bell"] == 1
    assert "open_store" not in result.observed_factor_coverage
    assert result.excluded_factors["bell"] == "coverage_unverified"
    assert result.excluded_factors["open_store"] == "opening_hours_unverified"


def test_published_schedule_subset_is_reported_without_asserting_current_opening():
    shop = source("open_store", [(37.5009, 127)])
    shop.completeness = "partial"
    shop.opening_hours = None
    shop.schedule_status = "published_schedule"
    shop.staffing_status = "unverified"
    result = evaluate([shop, source("bell", [(37.5009, 127)])])[0].assessment
    assert result.observed_facility_counts["store_with_published_hours"] == 1
    assert result.score is None and "open_store" not in result.used_factors
    assert result.longest_support_gap_m is None


def test_closed_store_is_not_replaced_by_general_shops():
    shop = source("open_store", [(37.5009, 127)])
    shop.opening_hours = {str(d): [[600, 1200]] for d in range(7)}
    result = evaluate([shop, source("bell", [(37.5009, 127)])])[0].assessment
    assert result.factor_coverage["open_store"] == 0
    assert result.score == 50


def test_group_uses_common_factors_over_all_candidate_geometries():
    cctv = source("cctv", [(37.5009, 127)])
    cctv.coverage_geometry = {"type": "Polygon", "coordinates": [[[126.9, 37.4], [127.1, 37.4], [127.1, 37.6], [126.9, 37.6], [126.9, 37.4]]]}
    results = evaluate([cctv, source("bell")], [POINTS, [(37.7, 127), (37.701, 127)]])
    assert all(r.assessment.used_factors == ["bell"] for r in results)
    assert all(r.assessment.score is None for r in results)


def test_duplicate_facilities_do_not_increase_coverage():
    point = (37.5009, 127)
    a = evaluate([source("cctv", [point]), source("bell", [point])])[0]
    b = evaluate([source("cctv", [point] * 10), source("bell", [point])])[0]
    assert a.assessment.score == b.assessment.score


def test_long_gap_is_continuous_across_input_edges_and_bell_does_not_break_it():
    path = [POINTS[0], (37.5009, 127), POINTS[1]]
    result = evaluate([source("lighting"), source("open_store"), source("bell", [path[1]])], [path])[0].assessment
    assert result.longest_support_gap_m == pytest.approx(200.15, abs=1)
    assert len(result.gap_intervals) == 1
    assert result.total_support_gap_m == result.longest_support_gap_m


def test_zero_length_path_has_no_score_or_gap():
    assert sample_route([POINTS[0], POINTS[0]], step_m=20) == []
    result = evaluate([source("cctv"), source("bell")], [[POINTS[0], POINTS[0]]])[0].assessment
    assert result.score is None
    assert result.longest_support_gap_m is None


def test_overnight_hours_use_previous_weekday_after_midnight():
    shop = source("open_store", [(37.5009, 127)])
    shop.opening_hours = {"2": [[1320, 120]]}  # Wed 22:00 to Thu 02:00
    result = evaluate([shop, source("bell")], at=datetime(2026, 11, 5, 1, tzinfo=KST))[0].assessment
    assert result.factor_coverage["open_store"] > 0


def test_single_verified_factor_provides_named_reference_without_composite_score():
    result = evaluate([source("bell", [(37.5009, 127)])])[0].assessment
    assert result.score is None
    assert result.reference_score == 100
    assert result.reference_factor == "bell"
    assert result.evaluation_basis == "single_factor"


def test_known_zero_single_factor_is_reference_zero_not_missing():
    result = evaluate([source("bell")])[0].assessment
    assert result.reference_score == 0
    assert result.evaluation_basis == "single_factor"


def test_partial_route_reports_bounds_and_verified_extent_instead_of_guessing_zero():
    cctv = source("cctv", [(37.5009, 127)])
    cctv.coverage_geometry = {"type": "Polygon", "coordinates": [[[126.9,37.4],[127.0002,37.4],[127.0002,37.6],[126.9,37.6],[126.9,37.4]]]}
    result = evaluate([cctv])[0].assessment
    assert result.score is None and result.reference_score is None
    assert result.evaluation_basis == "partial_coverage"
    assert 0 < result.score_bounds["lower"] < result.score_bounds["upper"] <= 100
    assert 0 < result.factor_evaluation_ratio["cctv"] < 1
    assert result.source_versions["cctv"] == cctv.sha256


def test_unverified_legacy_coordinates_do_not_produce_reference_scores_or_bounds():
    partial = source("bell", [(37.5009,127)])
    partial.completeness = "partial"
    result = evaluate([partial])[0].assessment
    assert result.score is None and result.reference_score is None and result.score_bounds is None
    assert result.evaluation_basis == "observed_only"


def test_official_missing_coordinates_can_prove_presence_without_proving_absence():
    partial = source("lighting", [(37.5,127)])
    partial.completeness = "partial"
    partial.coverage_basis = "declared_agency_boundary"
    partial.collection_evidence = {"status":"complete","method":"official_api","response_pages":[{}],
        "received_records":2,"expected_records":2,"coordinate_missing":1,"date_missing":0,
        "scope":{"agency_code":"test"},"original_sha256":"a"*64}
    result = evaluate([partial])[0].assessment
    assert result.evaluation_basis == "partial_coverage"
    assert result.reference_score is None
    assert 0 < result.score_bounds["lower"] < result.score_bounds["upper"] == 100
