from dataclasses import replace
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.route_environment_sources import build_environment_index
from app.services.safe_route import RouteArtifactRuntime
from app.services.time_period import KST
from test_facility_assessment import source
from test_route_artifact_schema4 import extended

START = {"lat": 37.5, "lng": 127.0}
END = {"lat": 37.502, "lng": 127.0}


@pytest.fixture
def api(monkeypatch):
    from app.api import safety

    runtime = RouteArtifactRuntime()
    light = source("lighting")
    bell = source("bell", [(37.5, 127.0)])
    store = source("open_store", [(37.5, 127.0)], opening_hours_evidence="official",
                   opening_hours={"3": [[23 * 60, 30]]})
    runtime.install(replace(extended(), version="live-1", environment_index=build_environment_index([light, bell, store])))
    monkeypatch.setattr(runtime, "reload_if_changed", lambda *a, **k: False)
    monkeypatch.setattr(safety, "route_artifact_runtime", runtime)
    monkeypatch.setattr(safety, "route_request_gate", safety.RouteRequestGate(
        max_concurrent=2, ip_requests_per_minute=30, ip_burst=8, user_requests_per_minute=20, user_burst=5,
    ))
    monkeypatch.setattr(safety, "is_in_service_area", lambda lat, lng, **kw: 37.4 <= lat <= 37.7)
    monkeypatch.setattr("app.services.spot_report.load_haven_index", lambda: None)
    return TestClient(app), runtime


def request(client, at, **overrides):
    return client.post("/safety/route-environment", json={
        "route_points": [START, END], "position": START, "at": at, **overrides,
    })


def test_route_and_point_share_snapshot_and_keep_all_three_evidence_states(api):
    client, _ = api
    response = request(client, "2026-11-05T22:59:45+09:00")
    assert response.status_code == 200
    body = response.json()
    assert body["artifact_version"] == body["local_environment"]["artifact_version"] == "live-1"
    assert body["local_environment"]["assessed_at"] == body["evaluated_at"]
    assert body["route_evidence"]["lighting"] == [
        {"start_m": 0, "end_m": body["assessment"]["distance_m"], "state": "absent_in_verified_inventory"},
    ]
    assert body["route_evidence"]["cctv"][0]["state"] == "unknown"
    assert body["route_evidence"]["bell"][0]["state"] == "present"
    assert body["valid_until"] == "2026-11-05T23:00:00+09:00"
    opened = request(client, "2026-11-05T23:00:00+09:00").json()
    assert opened["route_evidence"]["open_store"][0]["state"] == "present"
    assert opened["temporal_key"] != body["temporal_key"]


@pytest.mark.parametrize("endpoint", ["live", "spot"])
def test_publish_during_request_does_not_mix_facility_generations(api, monkeypatch, endpoint):
    from app.api import safety

    client, runtime = api
    original = safety.assess_live_route if endpoint == "live" else safety.assess_area_environment
    replacement = replace(extended(), version="live-2", environment_index=build_environment_index([source("bell")]))
    def publish_after_capture(*, snapshot, **kwargs):
        runtime.install(replacement)
        return original(snapshot=snapshot, **kwargs)
    monkeypatch.setattr(safety, "assess_live_route" if endpoint == "live" else "assess_area_environment", publish_after_capture)
    def fetch():
        return (request(client, "2026-11-05T23:00:00+09:00") if endpoint == "live" else
                client.get("/safety/spot", params={**START, "at": "2026-11-05T23:00:00+09:00"}))
    first = fetch()
    assert first.status_code == 200
    old = first.json()
    assert old["artifact_version"] == old["local_environment"]["artifact_version"] == "live-1"
    assert old["local_environment"]["factors"]["bell"]["state"] == "present"
    second = fetch().json()
    assert second["artifact_version"] == second["local_environment"]["artifact_version"] == "live-2"
    assert second["local_environment"]["factors"]["bell"]["state"] == "absent_in_verified_inventory"


@pytest.mark.parametrize("at,expires", [
    ("2026-11-05T21:59:45+09:00", "2026-11-05T22:00:00+09:00"),
    ("2026-11-05T23:59:45+09:00", "2026-11-06T00:00:00+09:00"),
    ("2026-11-06T00:29:45+09:00", "2026-11-06T00:30:00+09:00"),
    ("2026-11-06T05:59:45+09:00", "2026-11-06T06:00:00+09:00"),
    ("2026-11-06T10:00:45+09:00", "2026-11-06T10:01:45+09:00"),
])
def test_freshness_caps_and_kst_boundaries(api, at, expires):
    response = request(api[0], at)
    assert response.status_code == 200
    assert response.json()["valid_until"] == expires


@pytest.mark.parametrize("overrides", [
    {"route_points": [START] * 5001},
    {"route_points": [START, START]},
    {"route_points": [START, {"lat": 37.69, "lng": 127}]},
    {"route_points": [START, {"lat": 37.35, "lng": 127}]},
    {"route_points": [START, {"lat": 91, "lng": 127}]},
    {"position": {"lat": 38, "lng": 127}},
])
def test_invalid_geometry_does_not_produce_evidence(api, overrides):
    assert request(api[0], "2026-11-05T23:00:00+09:00", **overrides).status_code == 422


def test_missing_snapshot_preserves_route_client_side_with_pending_evidence(api, monkeypatch):
    client, runtime = api
    monkeypatch.setattr(runtime, "environment_snapshot", lambda: None)
    response = request(client, datetime(2026, 11, 5, 23, tzinfo=KST).isoformat())
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["route_evidence"] == {} and body["assessment"] is None
    assert "route_points" not in body


def test_live_assessment_shares_the_route_request_limit(api, monkeypatch):
    from app.api import safety
    gate = safety.RouteRequestGate(max_concurrent=1, ip_requests_per_minute=30, ip_burst=8,
                                  user_requests_per_minute=20, user_burst=5)
    monkeypatch.setattr(safety, "route_request_gate", gate)
    held = gate.acquire(client_ip="first", user_id=None)
    assert held.granted
    try:
        response = request(api[0], "2026-11-05T23:00:00+09:00")
        assert response.status_code == 429 and response.headers["Retry-After"]
    finally:
        held.release()
