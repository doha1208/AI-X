import os

if os.path.exists("test_safety.db"):
    os.remove("test_safety.db")
os.environ["DATABASE_URL"] = "sqlite:///./test_safety.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.safety_zone import SafetyZone  # noqa: E402

client = TestClient(app)


def setup_module():
    Base.metadata.create_all(bind=engine)
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
