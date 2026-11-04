from fastapi.testclient import TestClient  # noqa: E402
from datetime import UTC, datetime
import pytest

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.safety_zone import SafetyZone  # noqa: E402

client = TestClient(app)


def _route_response(**overrides):
    payload = dict(start_lat=37.5, start_lng=127, end_lat=37.51, end_lng=127.01)
    return client.post("/safety/route", json={**payload, **overrides})


@pytest.fixture(autouse=True)
def isolated_walking_providers(monkeypatch):
    from app.api import safety as api
    monkeypatch.setattr(api.route_artifact_runtime, "reload_if_changed", lambda *a, **k: False)
    monkeypatch.setattr(api.route_artifact_runtime, "environment_snapshot", lambda: None)
    async def walking(start_lat, start_lng, end_lat, end_lng):
        return [(start_lat,start_lng),(end_lat,end_lng)]
    monkeypatch.setattr(api, "get_pedestrian_route", walking)


@pytest.fixture(autouse=True)
def isolated_route_request_gate(monkeypatch):
    from app.api import safety as safety_api
    from app.services.route_request_limit import RouteRequestGate

    monkeypatch.setattr(
        safety_api,
        "route_request_gate",
        RouteRequestGate(
            max_concurrent=2,
            ip_requests_per_minute=100,
            ip_burst=100,
            user_requests_per_minute=100,
            user_burst=100,
        ),
    )


@pytest.fixture(autouse=True)
def safety_zones():
    db = SessionLocal()
    db.add_all(
        [
            SafetyZone(
                dong_code="TEST1",
                dong_name="테스트동1",
                lat=37.50,
                lng=127.00,
                cctv_count=40,
                streetlight_count=80,
                crime_count=2,
                safety_score=90,
            ),
            SafetyZone(
                dong_code="TEST2",
                dong_name="테스트동2",
                lat=37.51,
                lng=127.01,
                cctv_count=5,
                streetlight_count=10,
                crime_count=20,
                safety_score=20,
            ),
        ]
    )
    db.commit()
    db.close()
    yield


def test_nearby_zones():
    res = client.get("/safety/zones", params={"lat": 37.50, "lng": 127.00, "radius_km": 5})
    assert res.status_code == 200
    codes = {z["dong_code"] for z in res.json()}
    assert "TEST1" in codes


def test_residence_recommend_orders_by_score():
    res = client.get("/safety/residence-recommend", params={"limit": 2})
    assert res.status_code == 200
    scores = [z["safety_score"] for z in res.json()]
    assert scores == sorted(scores, reverse=True)


def test_residence_recommend_uses_active_artifact_day_scores(monkeypatch):
    from app.api import safety as safety_api

    monkeypatch.setattr(safety_api, "period_for", lambda: "day")
    monkeypatch.setattr(
        safety_api.route_artifact_runtime,
        "score_map",
        lambda period: {"TEST1": 12.0, "TEST2": 98.0},
    )

    body = client.get("/safety/residence-recommend", params={"limit": 2}).json()

    assert [(zone["dong_code"], zone["safety_score"]) for zone in body] == [
        ("TEST2", 98.0),
        ("TEST1", 12.0),
    ]


def test_residence_recommend_uses_the_current_kst_period_and_returns_both_scores(monkeypatch):
    from app.api import safety as safety_api

    monkeypatch.setattr(safety_api, "period_for", lambda: "night")
    monkeypatch.setattr(
        safety_api.route_artifact_runtime,
        "score_map",
        lambda period: (
            {"TEST1": 12.0, "TEST2": 98.0}
            if period == "day"
            else {"TEST1": 91.0, "TEST2": 23.0}
        ),
    )

    body = client.get("/safety/residence-recommend", params={"limit": 2}).json()

    assert [zone["dong_code"] for zone in body] == ["TEST1", "TEST2"]
    assert body[0]["period"] == "night"
    assert body[0]["safety_score"] == 91.0
    assert body[0]["day_safety_score"] == 12.0
    assert body[0]["night_safety_score"] == 91.0


def test_nearby_zones_use_the_current_kst_period(monkeypatch):
    from app.api import safety as safety_api

    monkeypatch.setattr(safety_api, "period_for", lambda: "night")
    monkeypatch.setattr(
        safety_api.route_artifact_runtime,
        "score_map",
        lambda period: (
            {"TEST1": 15.0, "TEST2": 85.0}
            if period == "day"
            else {"TEST1": 88.0, "TEST2": 22.0}
        ),
    )

    body = client.get(
        "/safety/zones",
        params={"lat": 37.50, "lng": 127.00, "radius_km": 5},
    ).json()

    by_code = {zone["dong_code"]: zone for zone in body}
    assert by_code["TEST1"] == {
        "dong_code": "TEST1",
        "dong_name": "테스트동1",
        "lat": 37.5,
        "lng": 127.0,
        "safety_score": 88.0,
        "day_safety_score": 15.0,
        "night_safety_score": 88.0,
        "period": "night",
    }


def test_service_area_defaults_to_gyeonggi_only():
    from app.core.config import Settings

    assert Settings.model_fields["region_scope_prefix"].default == "41"


def test_route_rejects_seoul_coordinates_in_gyeonggi_scope(monkeypatch):
    # 신림동 → 신림동
    from app.core.config import settings

    monkeypatch.setattr(settings, "region_scope_prefix", "41")
    response = client.post(
        "/safety/route",
        json={"start_lat": 37.4842, "start_lng": 126.9297, "end_lat": 37.4870, "end_lng": 126.9330},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "outside_service_area"


def test_route_rejects_coordinates_outside_the_gyeonggi_service_area():
    response = client.post(
        "/safety/route",
        json={
            "start_lat": 35.1796,
            "start_lng": 129.0756,
            "end_lat": 35.1830,
            "end_lng": 129.0810,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "reason": "outside_service_area",
        "action": "현재 길찾기는 경기도 지역에서만 지원합니다.",
        "points": ["start", "end"],
    }


def test_route_returns_facility_assessment_without_a_dong_score():
    body = _route_response().json()
    assert body["safety_score"] is None
    assert body["environment_model_applied"] is True
    assert body["zones_passed"] == []
    assert body["environment_assessment"]["score"] is None


def test_route_safety_accepts_night_timestamp():
    body = _route_response(at="2026-01-01T23:30:00+09:00").json()
    assert body["period"] == body["environment_assessment"]["period"] == "night"


def test_route_remains_available_without_residence_zone_records():
    with SessionLocal() as db:
        db.query(SafetyZone).delete()
        db.commit()
    response = _route_response()
    assert response.status_code == 200
    assert response.json()["zones_passed"] == []


def test_route_never_uses_legacy_artifact_dong_scores(monkeypatch):
    from app.api import safety as api
    monkeypatch.setattr(api, "_period_score_maps", lambda *a: (_ for _ in ()).throw(AssertionError("dong scoring")))
    assert _route_response().json()["safety_score"] is None


def test_route_response_discloses_walking_fallback_and_missing_facility_inputs():
    body = _route_response().json()
    disclosure = body["data_disclosure"]
    assert disclosure["data_basis"] == ["tmap_pedestrian_route"]
    assert disclosure["fallback"]["applied"] is True
    assert disclosure["updated_at"] is None
    assert disclosure["missing_data"] == []
    assert body["environment_assessment"]["excluded_factors"]["bell"] == "source_missing"


def test_route_returns_an_error_instead_of_a_straight_line_when_no_pedestrian_route_exists(monkeypatch):
    from app.api import safety as api
    async def unavailable(*a):
        return None
    monkeypatch.setattr(api, "get_pedestrian_route", unavailable)
    response = _route_response()
    assert response.status_code == 503
    assert response.json()["detail"]["reason"] == "pedestrian_route_unavailable"


def test_nearby_bells_limit_query_param_is_honored():
    from app.services import bells as bells_module

    bells_module._cached_points = [(37.5001 + 0.0001 * i, 127.0) for i in range(10)]
    try:
        res = client.get("/safety/bells", params={"lat": 37.5, "lng": 127.0, "radius_km": 5, "limit": 3})
        assert res.status_code == 200
        assert len(res.json()) == 3
    finally:
        bells_module._cached_points = None


def test_nearby_bells_excludes_seoul_with_gyeonggi_scope(monkeypatch):
    from app.core.config import settings
    from app.services import bells as bells_module

    monkeypatch.setattr(settings, "region_scope_prefix", "41")
    monkeypatch.setattr(bells_module, "_cached_points", [(37.4842, 126.9297)])

    res = client.get(
        "/safety/bells",
        params={"lat": 37.4842, "lng": 126.9297, "radius_km": 1},
    )

    assert res.status_code == 200
    assert res.json() == []


def test_nearby_bells_excludes_seoul_points_near_gyeonggi(monkeypatch):
    from app.core.config import settings
    from app.services import bells as bells_module

    gyeonggi_bell = (37.451, 126.92)
    monkeypatch.setattr(settings, "region_scope_prefix", "41")
    monkeypatch.setattr(bells_module, "_cached_points", [(37.47, 126.91), gyeonggi_bell])

    res = client.get(
        "/safety/bells",
        params={"lat": 37.45, "lng": 126.92, "radius_km": 5, "limit": 2},
    )

    assert res.status_code == 200
    assert res.json() == [{"lat": gyeonggi_bell[0], "lng": gyeonggi_bell[1]}]


def test_route_safety_includes_comparison_geometry():
    body = _route_response().json()
    assert len(body["shortest_route_points"]) >= 2
    assert body["comparison_environment_assessment"]["comparison_group_id"] == body["environment_assessment"]["comparison_group_id"]


def test_route_alternatives_do_not_include_residence_scores():
    body = _route_response().json()
    assert body["alternatives"]
    assert all(a["zones_passed"] == [] and a["safety_score"] is None for a in body["alternatives"])


def test_route_without_comparison_skips_tmap_when_environment_graph_exists(monkeypatch):
    from types import SimpleNamespace
    from app.api import safety as api
    from app.services.route_environment import RouteCandidate
    from app.services.route_environment_sources import EnvironmentIndex
    monkeypatch.setattr(api.route_artifact_runtime, "environment_snapshot", lambda: SimpleNamespace(artifact=SimpleNamespace(environment_index=EnvironmentIndex())))
    monkeypatch.setattr(api.route_artifact_runtime, "find_environment_candidates", lambda *a, **k: [RouteCandidate("baseline", [(37.5,127),(37.51,127.01)], "osm")])
    async def must_not_call(*a):
        raise AssertionError("Tmap must not be called for a plain reroute")
    monkeypatch.setattr(api, "get_pedestrian_route", must_not_call)
    body = _route_response(include_comparison=False).json()
    assert body["mode"] == "safety_weighted"
    assert body["shortest_route_points"] is None


def test_route_safety_returns_retry_after_when_request_limit_is_exhausted(monkeypatch):
    from app.api import safety as api
    from app.services.route_request_limit import RouteRequestGate
    monkeypatch.setattr(api, "route_request_gate", RouteRequestGate(max_concurrent=2, ip_requests_per_minute=1, ip_burst=1, user_requests_per_minute=1, user_burst=1))
    assert _route_response().status_code == 200
    second = _route_response()
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"


def test_health_reports_route_artifact_status(monkeypatch):
    from app import main

    monkeypatch.setattr(main.route_artifact_runtime, "status", lambda: {"available": True, "version": "v1"})

    assert client.get("/health").json()["route_artifact"] == {"available": True, "version": "v1"}


def test_route_comparison_excludes_dong_scores():
    assert _route_response().json()["shortest_zones_passed"] == []


def test_route_response_reports_which_day_night_period_was_used():
    assert _route_response(at="2026-01-01T23:00:00+09:00").json()["period"] == "night"
    assert _route_response(at="2026-01-01T12:00:00+09:00").json()["period"] == "day"
