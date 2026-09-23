from app.services.bells import DEFAULT_BELL_LIMIT, nearby_bells

SEOUL_CITY_HALL = (37.5665, 126.9780)
NEAR = (37.5670, 126.9785)  # ~65m
FAR = (37.70, 127.20)  # 수십km


def test_bells_within_radius_are_returned():
    result = nearby_bells(*SEOUL_CITY_HALL, radius_km=1.0, points=[NEAR, FAR])
    assert result == [{"lat": NEAR[0], "lng": NEAR[1]}]


def test_bells_outside_radius_are_excluded():
    result = nearby_bells(*SEOUL_CITY_HALL, radius_km=0.01, points=[NEAR])
    assert result == []


def test_empty_point_list_returns_empty():
    assert nearby_bells(*SEOUL_CITY_HALL, radius_km=5.0, points=[]) == []


def test_result_is_capped_to_the_closest_points():
    # 도심처럼 촘촘한 지역에서 지도가 마커로 뒤덮이지 않도록 가까운 것부터 limit개만 돌려준다.
    lat, lng = SEOUL_CITY_HALL
    far_to_near = [(lat + 0.001 * i, lng) for i in range(10, 0, -1)]  # 10번째가 가장 멈, 1번째가 가장 가까움
    result = nearby_bells(lat, lng, radius_km=5.0, points=far_to_near, limit=3)
    closest_first = list(reversed(far_to_near[-3:]))  # 가까운 순: 마지막 원소가 가장 가까움
    assert result == [{"lat": p[0], "lng": p[1]} for p in closest_first]


def test_default_limit_is_a_small_positive_number():
    # 상수 자체가 합리적인 값인지(0이거나 터무니없이 크지 않은지) 확인.
    assert 0 < DEFAULT_BELL_LIMIT <= 200
