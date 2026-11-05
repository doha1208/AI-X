import os
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.safety_zone import SafetyZone
from app.services.spot_report import nearest_havens

client = TestClient(app)
HOME = (37.2665, 127.0005)


def _offset(lat: float, lng: float, north_m: float, east_m: float) -> tuple[float, float]:
    return lat + north_m / 111_320.0, lng + east_m / (111_320.0 * 0.794)


def test_nearest_havens_gives_one_per_kind_sorted_by_distance_and_drops_far_ones(tmp_path, monkeypatch):
    import json
    from app.services.route_environment_sources import build_environment_index
    from test_facility_assessment import source

    police = tmp_path / "police.json"
    police.write_text(json.dumps({"police": [(37.2735, HOME[1])]}))
    original_stat = police.stat()
    monkeypatch.setattr("app.services.spot_report.POLICE_POINTS_PATH", police)
    value = build_environment_index([source("bell", [_offset(*HOME, 100, 0), _offset(*HOME, 50, 0)]),
                                     source("open_store", [_offset(*HOME, 20, 0)])])
    at = datetime(2026, 11, 5, 23)
    havens = nearest_havens(value, *HOME, at=at)
    assert [h["kind"] for h in havens] == ["bell", "police"]
    assert havens[0]["distance_m"] == pytest.approx(50, abs=2)
    assert havens[0]["operation_status"] == "unverified"
    police.write_text(json.dumps({"police": [(37.2935, HOME[1])]}))
    os.utime(police, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    assert police.stat().st_size == original_stat.st_size and police.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert [h["kind"] for h in nearest_havens(value, *HOME, at=at)] == ["bell"]


@pytest.fixture
def spot_api(monkeypatch):
    from app.api import safety as safety_api

    db = SessionLocal()
    db.add_all(
        [
            SafetyZone(dong_code="4111100001", dong_name="가동", lat=HOME[0], lng=HOME[1], cctv_count=30, cctv_known=False,
                       streetlight_count=50, crime_rate=10.0, police_dist_m=300.0, bell_dist_m=80.0, safety_score=80),
            SafetyZone(dong_code="4111100002", dong_name="나동", lat=HOME[0] + 0.02, lng=HOME[1], cctv_count=3,
                       streetlight_count=5, cctv_known=False, crime_rate=40.0, police_dist_m=2000.0, safety_score=20),
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(safety_api, "is_in_service_area", lambda *a, **k: True)
    from dataclasses import replace
    from types import SimpleNamespace
    from app.services.route_environment_sources import build_environment_index
    from test_facility_assessment import source
    from test_route_artifact_schema4 import extended
    from test_walk_environment_samples import index

    store = replace(source("open_store", [HOME]), source_id="published-hours-emart24",
                    completeness="partial", schedule_status="published_schedule")
    artifact = replace(extended(), walk_environment_index=index([(1, 2, HOME, _offset(*HOME, 120, 0), {})]),
                       environment_index=build_environment_index([source("cctv", [HOME]), source("lighting", [HOME]), store]))
    monkeypatch.setattr(safety_api.route_artifact_runtime, "reload_if_changed", lambda *a, **k: None)
    monkeypatch.setattr(safety_api.route_artifact_runtime, "environment_snapshot", lambda: SimpleNamespace(artifact=artifact))
    monkeypatch.setattr("app.services.spot_report.POLICE_POINTS_PATH", Path("missing-police-fixture.json"))
    return safety_api


def test_spot_report_returns_nearest_zone_scores_counts_and_havens(spot_api, monkeypatch):
    def reject_legacy_score(*args, **kwargs):
        pytest.fail("the endpoint must not use the legacy grid or point score")
    monkeypatch.setattr("app.services.facility_density.edge_local_scores", reject_legacy_score)
    res = client.get("/safety/spot", params={"lat": HOME[0], "lng": HOME[1], "at": "2026-11-04T16:30:00Z"})
    assert res.status_code == 200
    body = res.json()
    assert body["zone"]["dong_name"] == "가동"
    assert body["zone"]["rank"] == 1 and body["zone"]["total"] == 2
    assert body["facility_observations"]["cctv"]["count"] == 1
    assert body["area_environment"]["night"]["artifact_version"] == body["artifact_version"]
    assert body["local_environment"]["period"] == "night"
    assert body["havens"][0]["kind"] == "convenience"
    assert body["havens"][0]["opening_status"] == "unverified"
    assert body["havens"][0]["staffing_status"] == "unverified"
    assert all(body[key] is None for key in ("here_score", "area_day_score", "area_night_score"))


def test_spot_report_rejects_points_outside_the_service_area(spot_api, monkeypatch):
    monkeypatch.setattr(spot_api, "is_in_service_area", lambda *a, **k: False)
    res = client.get("/safety/spot", params={"lat": 37.57, "lng": 126.98})
    assert res.status_code == 422


def test_zone_detail_hides_cctv_count_for_a_region_that_did_not_submit_it(spot_api):
    res = client.get("/safety/zones/4111100002")
    assert res.status_code == 200
    body = res.json()
    assert body["cctv_count"] is None
    assert body["streetlight_count"] == 5
    assert body["rank"] == 2


def test_zone_detail_returns_404_for_an_unknown_dong(spot_api):
    assert client.get("/safety/zones/0000000000").status_code == 404
