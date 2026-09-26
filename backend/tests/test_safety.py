from fastapi.testclient import TestClient  # noqa: E402
import pytest

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.safety_zone import SafetyZone  # noqa: E402

client = TestClient(app)


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


def test_route_safety_returns_score():
    res = client.post(
        "/safety/route",
        json={"start_lat": 37.50, "start_lng": 127.00, "end_lat": 37.51, "end_lng": 127.01},
    )
    assert res.status_code == 200
    body = res.json()
    assert "safety_score" in body
    assert len(body["zones_passed"]) >= 1


def test_route_safety_accepts_night_timestamp():
    res = client.post(
        "/safety/route",
        json={
            "start_lat": 37.50,
            "start_lng": 127.00,
            "end_lat": 37.51,
            "end_lng": 127.01,
            "at": "2026-01-01T23:30:00+09:00",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "safety_score" in body
    assert len(body["zones_passed"]) >= 1


def test_route_fallback_ignores_incomplete_artifact_score_map(monkeypatch):
    from app.api import safety as safety_api

    async def tmap_points(*_):
        return [(37.50, 127.00), (37.51, 127.01)]

    monkeypatch.setattr(safety_api, "find_safe_routes", lambda *args, **kwargs: None)
    monkeypatch.setattr(safety_api, "get_pedestrian_route", tmap_points)
    monkeypatch.setattr(safety_api.route_artifact_runtime, "score_map", lambda period: {"TEST1": 99.0})
    monkeypatch.setattr(
        safety_api,
        "compute_zone_period_scores",
        lambda zones, period: {"TEST1": 31.0, "TEST2": 69.0},
    )

    response = client.post(
        "/safety/route",
        json={
            "start_lat": 37.50,
            "start_lng": 127.00,
            "end_lat": 37.51,
            "end_lng": 127.01,
            "at": "2026-01-01T23:30:00+09:00",
        },
    )

    assert response.status_code == 200
    assert [zone["safety_score"] for zone in response.json()["zones_passed"]] == [31.0, 69.0]


def test_nearby_bells_limit_query_param_is_honored():
    from app.services import bells as bells_module

    bells_module._cached_points = [(37.5001 + 0.0001 * i, 127.0) for i in range(10)]
    try:
        res = client.get("/safety/bells", params={"lat": 37.5, "lng": 127.0, "radius_km": 5, "limit": 3})
        assert res.status_code == 200
        assert len(res.json()) == 3
    finally:
        bells_module._cached_points = None


def test_route_safety_includes_shortest_route_field():
    res = client.post(
        "/safety/route",
        json={"start_lat": 37.50, "start_lng": 127.00, "end_lat": 37.51, "end_lng": 127.01},
    )
    assert res.status_code == 200
    body = res.json()
    # Tmap 키 미설정/실패 시 None으로 조용히 빠지므로 값 자체보단 필드 존재만 확인.
    assert "shortest_route_points" in body


def test_route_without_comparison_skips_tmap_when_safe_route_exists(monkeypatch):
    from app.api import safety as safety_api

    monkeypatch.setattr(
        safety_api,
        "find_safe_routes",
        lambda *args, **kwargs: [
            {"points": [(37.5, 127.0), (37.51, 127.01)], "score": 70.0, "distance_m": 1400.0}
        ],
    )
    called = False

    async def fake_tmap(*args, **kwargs):
        nonlocal called
        called = True
        return [(37.5, 127.0), (37.51, 127.01)]

    monkeypatch.setattr(safety_api, "get_pedestrian_route", fake_tmap)

    res = client.post(
        "/safety/route",
        json={
            "start_lat": 37.5,
            "start_lng": 127.0,
            "end_lat": 37.51,
            "end_lng": 127.01,
            "include_comparison": False,
        },
    )

    assert res.status_code == 200
    assert called is False
    assert res.json()["shortest_route_points"] is None


def test_route_safety_returns_retry_after_when_request_limit_is_exhausted(monkeypatch):
    from app.api import safety as safety_api
    from app.services.route_request_limit import RouteRequestGate

    monkeypatch.setattr(
        safety_api,
        "route_request_gate",
        RouteRequestGate(
            max_concurrent=2,
            ip_requests_per_minute=1,
            ip_burst=1,
            user_requests_per_minute=1,
            user_burst=1,
        ),
        raising=False,
    )
    monkeypatch.setattr(
        safety_api,
        "find_safe_routes",
        lambda *args, **kwargs: [
            {"points": [(37.5, 127.0), (37.51, 127.01)], "score": 70.0, "distance_m": 1400.0}
        ],
    )

    first = client.post(
        "/safety/route",
        json={"start_lat": 37.5, "start_lng": 127.0, "end_lat": 37.51, "end_lng": 127.01},
    )
    second = client.post(
        "/safety/route",
        json={"start_lat": 37.5, "start_lng": 127.0, "end_lat": 37.51, "end_lng": 127.01},
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"


def test_health_reports_route_artifact_status(monkeypatch):
    from app import main

    monkeypatch.setattr(main.route_artifact_runtime, "status", lambda: {"available": True, "version": "v1"})

    assert client.get("/health").json()["route_artifact"] == {"available": True, "version": "v1"}
