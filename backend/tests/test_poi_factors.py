from app.services.poi_factors import POLICE_DIST_CAP_M, nearest_police_distances_m


def test_distance_to_nearest_station_in_meters():
    # 위도 0.001도 ≈ 111m
    dists = nearest_police_distances_m([(37.500, 127.000)], [(37.501, 127.000), (37.520, 127.000)])
    assert 105 < dists[0] < 118


def test_longitude_degrees_are_shorter_than_latitude_degrees():
    # 서울 위도에서 경도 0.001도 ≈ 88m (위도 0.001도 ≈ 111m 보다 짧다)
    lat_dist = nearest_police_distances_m([(37.5, 127.0)], [(37.501, 127.0)])[0]
    lng_dist = nearest_police_distances_m([(37.5, 127.0)], [(37.5, 127.001)])[0]
    assert lng_dist < lat_dist


def test_far_or_missing_stations_are_capped():
    assert nearest_police_distances_m([(37.5, 127.0)], [(38.5, 127.0)]) == [POLICE_DIST_CAP_M]
    assert nearest_police_distances_m([(37.5, 127.0)], []) == [POLICE_DIST_CAP_M]
