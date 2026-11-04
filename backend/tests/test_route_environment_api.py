from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.api import safety as api
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.safety_zone import SafetyZone
from app.services.route_environment import RouteCandidate
from app.services.route_environment_sources import build_environment_index
from app.services.route_request_limit import RouteRequestGate
from test_route_environment import source, POINTS


@pytest.fixture(autouse=True)
def environment_request(monkeypatch):
    monkeypatch.setattr(api, "is_in_service_area", lambda *a, **kw: True)
    monkeypatch.setattr(api, "route_request_gate", RouteRequestGate(max_concurrent=2, ip_requests_per_minute=100, ip_burst=100, user_requests_per_minute=100, user_burst=100))
    with SessionLocal() as db:
        db.add(SafetyZone(dong_code="TEST1", dong_name="테스트동", lat=37.5, lng=127, cctv_count=40, streetlight_count=80, crime_count=2, safety_score=48))
        db.commit()
    monkeypatch.setattr(api.route_artifact_runtime, "reload_if_changed", lambda *a, **kw: False)


PAYLOAD = dict(start_lat=37.5, start_lng=127, end_lat=37.5018, end_lng=127, at="2026-11-04T23:00:00+09:00")


def test_both_engines_use_one_group_and_do_not_publish_legacy_dong_score(monkeypatch):
    index = build_environment_index([source("cctv", [(37.5009,127)]), source("bell", [(37.5009,127)])])
    snapshot = SimpleNamespace(artifact=SimpleNamespace(environment_index=index))
    monkeypatch.setattr(api.route_artifact_runtime, "environment_snapshot", lambda: snapshot)
    monkeypatch.setattr(api.route_artifact_runtime, "find_environment_candidates", lambda *a, **kw: [RouteCandidate("osm-0", POINTS, "osm")])
    async def tmap(*args):
        return POINTS
    monkeypatch.setattr(api, "get_pedestrian_route", tmap)
    # No call to the legacy safety-weighted engine is permitted in active mode.
    monkeypatch.setattr(api, "_period_score_maps", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("route must not calculate dong scores")))
    response = TestClient(app).post("/safety/route", json=PAYLOAD)
    assert response.status_code == 200
    body = response.json()
    a, b = body["environment_assessment"], body["comparison_environment_assessment"]
    assert a["score"] == b["score"]
    assert a["comparison_group_id"] == b["comparison_group_id"]
    assert body["safety_score"] is None
    assert all(r["safety_score"] is None for r in body["alternatives"])
    assert body["environment_model_applied"] is True


def test_no_artifact_still_returns_tmap_without_invented_environment_score(monkeypatch):
    monkeypatch.setattr(api.route_artifact_runtime, "environment_snapshot", lambda: None)
    async def tmap(*args):
        return POINTS
    monkeypatch.setattr(api, "get_pedestrian_route", tmap)
    body = TestClient(app).post("/safety/route", json=PAYLOAD).json()
    assert body["mode"] == "tmap"
    assert body["environment_assessment"]["score"] is None
    assert body["environment_assessment"]["longest_support_gap_m"] is None


def test_no_pedestrian_engine_returns_503(monkeypatch):
    monkeypatch.setattr(api.route_artifact_runtime, "environment_snapshot", lambda: None)
    async def tmap(*args):
        return None
    monkeypatch.setattr(api, "get_pedestrian_route", tmap)
    response = TestClient(app).post("/safety/route", json=PAYLOAD)
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "pedestrian_route_unavailable"


def test_reroute_with_degenerate_osm_result_still_uses_tmap(monkeypatch):
    snapshot = SimpleNamespace(artifact=SimpleNamespace(environment_index=build_environment_index([])))
    monkeypatch.setattr(api.route_artifact_runtime, "environment_snapshot", lambda: snapshot)
    monkeypatch.setattr(api.route_artifact_runtime, "find_environment_candidates", lambda *a, **kw: [RouteCandidate("osm-0", [POINTS[0]], "osm")])
    async def tmap(*args):
        return POINTS
    monkeypatch.setattr(api, "get_pedestrian_route", tmap)
    response = TestClient(app).post("/safety/route", json={**PAYLOAD, "include_comparison":False})
    assert response.status_code == 200
    assert response.json()["mode"] == "tmap"


def test_out_of_budget_candidate_does_not_remove_evidence_from_valid_routes(monkeypatch):
    sources = [source("cctv", [(37.5009,127)]), source("bell", [(37.5009,127)])]
    for s in sources:
        s.coverage_geometry = {"type":"Polygon", "coordinates":[[[126.99,37.49],[127.01,37.49],[127.01,37.51],[126.99,37.51],[126.99,37.49]]]}
    snapshot = SimpleNamespace(artifact=SimpleNamespace(environment_index=build_environment_index(sources)))
    monkeypatch.setattr(api.route_artifact_runtime, "environment_snapshot", lambda: snapshot)
    detour = [POINTS[0], (37.5,127.02),(37.5018,127.02),POINTS[1]]
    monkeypatch.setattr(api.route_artifact_runtime, "find_environment_candidates", lambda *a, **kw: [RouteCandidate("osm-0", detour, "osm")])
    async def tmap(*args):
        return POINTS
    monkeypatch.setattr(api, "get_pedestrian_route", tmap)
    body = TestClient(app).post("/safety/route", json=PAYLOAD).json()
    assert body["environment_assessment"]["score"] is not None
    assert body["mode"] == "tmap"
    assert body["data_disclosure"]["fallback"]["applied"] is False
