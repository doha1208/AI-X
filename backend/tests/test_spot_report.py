import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.safety_zone import SafetyZone
from app.services.facility_density import build_facility_index
from app.services.spot_report import (
    area_scores,
    build_haven_index,
    facility_counts,
    grid_around,
    nearest_havens,
)

client = TestClient(app)
HOME = (37.2665, 127.0005)


def _offset(lat: float, lng: float, north_m: float, east_m: float) -> tuple[float, float]:
    return lat + north_m / 111_320.0, lng + east_m / (111_320.0 * 0.794)


def test_grid_stays_inside_the_radius_and_includes_the_center():
    grid = grid_around(*HOME, radius_m=300, step_m=50)
    assert HOME in grid
    assert len(grid) > 100


def test_nearest_havens_gives_one_per_kind_sorted_by_distance_and_drops_far_ones():
    index = build_haven_index(
        police=[_offset(*HOME, 800, 0)],
        convenience=[_offset(*HOME, 100, 0), _offset(*HOME, 50, 0)],
        bells=[_offset(*HOME, 3000, 0)],
    )
    havens = nearest_havens(index, *HOME, max_m=1500)
    assert [h["kind"] for h in havens] == ["convenience", "police"]
    assert havens[0]["distance_m"] == pytest.approx(50, abs=2)


def test_area_with_cctv_and_lights_scores_higher_at_night_than_a_bare_area():
    lit = [_offset(*HOME, n, e) for n in range(-300, 301, 30) for e in range(-300, 301, 30)]
    busy = build_facility_index(cctv=lit, lights=lit)
    bare = build_facility_index(cctv=[], lights=[])
    assert area_scores(busy, *HOME, True, True)["night"] > area_scores(bare, *HOME, True, True)["night"]


def test_counts_are_unknown_not_zero_when_the_region_did_not_submit_the_data():
    index = build_facility_index(cctv=[HOME], lights=[HOME])
    counts = facility_counts(index, *HOME, lights_known=False, cctv_known=True)
    assert counts["cctv"] == 1
    assert counts["lights"] is None


@pytest.fixture
def spot_api(monkeypatch):
    from app.api import safety as safety_api

    db = SessionLocal()
    db.add_all(
        [
            SafetyZone(dong_code="4111100001", dong_name="가동", lat=HOME[0], lng=HOME[1], cctv_count=30,
                       streetlight_count=50, crime_rate=10.0, police_dist_m=300.0, bell_dist_m=80.0, safety_score=80),
            SafetyZone(dong_code="4111100002", dong_name="나동", lat=HOME[0] + 0.02, lng=HOME[1], cctv_count=3,
                       streetlight_count=5, cctv_known=False, crime_rate=40.0, police_dist_m=2000.0, safety_score=20),
        ]
    )
    db.commit()
    db.close()
    monkeypatch.setattr(safety_api, "is_in_service_area", lambda *a, **k: True)
    monkeypatch.setattr(safety_api, "_facility_index", lambda: build_facility_index(cctv=[HOME], lights=[HOME]))
    monkeypatch.setattr(
        safety_api, "load_haven_index",
        lambda: build_haven_index(police=[_offset(*HOME, 300, 0)], convenience=[_offset(*HOME, 40, 0)], bells=[]),
    )
    return safety_api


def test_spot_report_returns_nearest_zone_scores_counts_and_havens(spot_api):
    res = client.get("/safety/spot", params={"lat": HOME[0], "lng": HOME[1]})
    assert res.status_code == 200
    body = res.json()
    assert body["zone"]["dong_name"] == "가동"
    assert body["zone"]["rank"] == 1 and body["zone"]["total"] == 2
    # 편의점 좌표를 안 넣은 시설 색인이라 0개가 아니라 모름(None)
    assert body["counts"] == {"cctv": 1, "lights": 1, "convenience": None}
    assert [h["kind"] for h in body["havens"]] == ["convenience", "police"]
    assert 0 <= body["here_score"] <= 100
    assert body["area_day_score"] is not None and body["area_night_score"] is not None


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
