from dataclasses import asdict
from datetime import datetime
import importlib
import json
from pathlib import Path

import pytest

from app.services.route_environment import RouteCandidate
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_rank import assess_and_select
from app.services.route_environment_sources import FacilitySource, build_environment_index
from app.services.time_period import KST

AREA = {"type": "Polygon", "coordinates": [[[126, 37], [128, 37], [128, 38], [126, 38], [126, 37]]]}
POINTS = [(37.5, 127), (37.502, 127), (37.504, 127)]
AT = datetime(2026, 11, 4, 12, tzinfo=KST)


def source(factor, points=(), **kwargs):
    return FacilitySource(factor, factor, "https://data.go.kr/test", "2026-11-01", "2026-11-04", "a" * 64,
                          coverage_geometry=AREA, completeness="verified_complete", points=list(points),
                          purpose="crime_prevention" if factor == "cctv" else None, **kwargs)


def core():
    return importlib.import_module("app.services.facility_assessment")


def samples():
    return [core().AssessmentSample(str(i), p, weight) for i, (p, weight) in enumerate(zip(POINTS, [40, 40, 20]))]


def assess(sources, common=frozenset(), at=AT):
    return core().assess_facility_samples(samples(), scope="area", at=at, policy=EnvironmentPolicy(),
                                         indexes=build_environment_index(sources), common_factors=common)


def test_length_weighted_coverage_is_shared_without_count_saturation():
    result = assess([source("cctv", POINTS[:2]), source("bell", POINTS[:1])], {"cctv", "bell"})
    assert result.score == pytest.approx(60)
    assert result.factor_coverage == {"bell": 0.4, "cctv": 0.8}
    assert result.sampled_length_m == 100 and result.scope == "area"
    assert result.weight_unit == "metre" and result.evaluation_basis == "multi_factor"


def test_single_factor_is_named_reference_and_verified_zero_stays_zero():
    result = assess([source("cctv", POINTS[:2])], {"cctv"})
    assert result.score is None and result.reference_score == 80 and result.reference_factor == "cctv"
    zero = assess([source("cctv")], {"cctv"})
    assert zero.reference_score == 0 and zero.evaluation_basis == "single_factor"


def test_partial_official_coordinates_prove_presence_but_not_absence():
    partial = source("lighting", POINTS[:1])
    partial.completeness = "partial"
    partial.coverage_basis = "declared_agency_boundary"
    partial.collection_evidence = {"status": "complete", "method": "official_api", "response_pages": [{}],
        "received_records": 2, "expected_records": 2, "coordinate_missing": 1, "date_missing": 0,
        "scope": {"agency_code": "test"}, "original_sha256": "a" * 64}
    result = assess([partial], at=AT.replace(hour=23))
    assert result.score is None and result.reference_score is None
    assert result.score_bounds == {"lower": 10, "upper": 100}
    assert result.factor_evaluation_ratio["lighting"] == 0.4
    states = [o.factors["lighting"].state for o in result.observations]
    assert states == ["present", "unknown", "unknown"]


def test_unverified_positions_are_observations_without_verified_scores():
    legacy = source("cctv", POINTS[:1])
    legacy.completeness = "partial"
    result = assess([legacy])
    assert result.score is None and result.score_bounds is None
    assert result.evaluation_basis == "observed_only"
    assert result.observations[0].factors["cctv"].state == "unknown"


def test_point_evidence_has_states_and_metadata_without_fake_distance_or_score():
    local = core().assess_local_facilities(POINTS[0], at=AT, policy=EnvironmentPolicy(),
        indexes=build_environment_index([source("cctv", POINTS[:1]), source("bell")]), artifact_version="fixture-v1")
    assert local.factors["cctv"].state == "present"
    assert local.factors["bell"].state == "absent_in_verified_inventory"
    assert local.factors["open_store"].state == "unknown"
    assert local.artifact_version == "fixture-v1" and local.assessed_at == AT
    assert "score" not in asdict(local) and "sampled_length_m" not in asdict(local)


def test_store_hours_use_requested_weekday_and_overnight_previous_day():
    shop = source("open_store", POINTS[:1], opening_hours_evidence="official hours", opening_hours={"2": [[1320, 120]]})
    index = build_environment_index([shop])
    def state(at):
        return core().observe_facilities(POINTS[:1], at=at, policy=EnvironmentPolicy(), indexes=index)[0].factors["open_store"].state
    assert state(AT.replace(hour=23)) == "present"  # Wednesday.
    assert state(AT.replace(day=5, hour=1)) == "present"  # Thursday, previous day's schedule.
    assert state(AT.replace(day=5, hour=2)) == "absent_in_verified_inventory"
    assert state(AT.replace(day=7, hour=23)) == "absent_in_verified_inventory"  # Saturday is not Wednesday.


def test_empty_samples_do_not_create_score_or_divide_by_zero():
    result = core().assess_facility_samples([], scope="zone", at=AT, policy=EnvironmentPolicy(),
        indexes=build_environment_index([source("bell")]), common_factors={"bell"})
    assert result.score is None and result.reference_score is None and result.sampled_length_m == 0


def test_unverified_presence_cannot_be_forced_into_a_comparison_factor():
    legacy = source("cctv", POINTS[:1])
    legacy.completeness = "partial"
    with pytest.raises(ValueError, match="verified evidence"):
        assess([legacy], {"cctv"})


@pytest.mark.parametrize("weight", [0, -1, float("nan"), float("inf")])
def test_invalid_sample_weights_are_rejected(weight):
    with pytest.raises(ValueError):
        core().AssessmentSample("bad", POINTS[0], weight)


FIXTURES = json.loads((Path(__file__).parent / "fixtures/route_environment_before_common.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", FIXTURES, ids=lambda case: case["name"])
def test_route_scores_bounds_gaps_and_selection_match_pre_refactor_fixture(case):
    sources = [FacilitySource(**{**s, "points": [tuple(p) for p in s["points"]]}) for s in case["sources"]]
    candidates = [RouteCandidate(c["candidate_id"], [tuple(p) for p in c["points"]], c["source"]) for c in case["candidates"]]
    selected, evaluated, _ = assess_and_select(candidates, baseline_id="baseline", at=datetime.fromisoformat(case["at"]),
                                             policy=EnvironmentPolicy(), indexes=build_environment_index(sources))
    assert [r.candidate.candidate_id for r in selected] == case["selected"]
    assert {r.candidate.candidate_id: asdict(r.assessment) for r in evaluated} == case["assessments"]
