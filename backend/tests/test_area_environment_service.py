from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

import pytest
from shapely.geometry import box, mapping

from app.services.route_environment_sources import build_environment_index
from test_facility_assessment import source
from test_route_artifact_schema4 import extended
from test_walk_environment_samples import index, point


def evaluate(artifact, at="2026-11-04T16:30:00Z"):
    from app.services.area_environment_service import assess_area_environment
    lat, lng = point(0, 0)
    return assess_area_environment(snapshot=SimpleNamespace(artifact=artifact), lat=lat, lng=lng,
                                   radius_m=300, at=datetime.fromisoformat(at))


def test_area_scores_actual_walk_length_with_known_zero_and_kst_reference_slots():
    roads = index([(1, 2, point(0, -400), point(0, 400), {})])
    value = replace(extended(), walk_environment_index=roads, environment_index=build_environment_index([source("bell")]))
    report = evaluate(value)
    assert report.artifact_version == value.version
    assert report.area_environment["day"].sampled_length_m == pytest.approx(600)
    for period, hour in (("day", 12), ("night", 23)):
        assessment = report.area_environment[period]
        assert assessment.reference_at.isoformat() == f"2026-11-05T{hour}:00:00+09:00"
        assert assessment.reference_score == 0
    assert report.local_environment.assessed_at.isoformat() == "2026-11-05T01:30:00+09:00"
    assert report.local_environment.factors["bell"].state == "absent_in_verified_inventory"
    assert report.facility_observations["bell"]["count"] == 0
    assert not hasattr(report.local_environment, "score")


def test_partial_scope_and_deduplicated_observations_from_same_snapshot():
    bell = source("bell", [point(0, 0)])
    bell.coverage_geometry = mapping(box(126.99, 37.49, 127.0001, 37.51))
    legacy = replace(bell, source_id="legacy", completeness="partial", coverage_geometry=None)
    value = replace(extended(), environment_index=build_environment_index([bell, legacy]))
    report = evaluate(value)
    assert report.area_environment["day"].evaluation_basis == "partial_coverage"
    assert report.area_environment["day"].score is None
    assert report.local_environment.artifact_version == value.version
    assert report.facility_observations["bell"]["count"] == 1
    assert report.facility_observations["bell"]["coverage"] == "partial"
    assert report.facility_observations["lighting"]["count"] is None


@pytest.mark.parametrize("schema,reason", [(3, "area_artifact_pending"), (4, "no_walk_samples")])
def test_schema3_and_empty_walk_network_keep_local_evidence(schema, reason):
    value = replace(extended(), schema_version=schema, walk_environment_index=index([]),
                    environment_index=build_environment_index([source("bell", [point(0, 0)])]))
    report = evaluate(value)
    assert report.unavailable_reason == reason
    assert report.local_environment.factors["bell"].state == "present"
    assert report.area_environment is None or report.area_environment["day"].score is None
