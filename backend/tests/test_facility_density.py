import json

import shapely
import shapely.affinity

from app.services.facility_density import (
    LIGHT_SATURATION,
    build_facility_index,
    edge_local_scores,
    load_facility_index,
)

# 위도 0.0002도 ≈ 22m, 0.001도 ≈ 111m
ORIGIN = (37.5000, 127.0000)
NEAR = (37.5002, 127.0000)
FAR = (37.5100, 127.0000)  # 약 1.1km


def _score(index, period, point=ORIGIN):
    return edge_local_scores(index, [point], period)[0]


def test_nearby_lights_raise_night_score():
    lit = build_facility_index(cctv=[], lights=[NEAR, NEAR])
    dark = build_facility_index(cctv=[], lights=[FAR, FAR])
    assert _score(lit, "night") > _score(dark, "night")


def test_points_outside_the_radius_are_ignored():
    index = build_facility_index(cctv=[FAR], lights=[FAR])
    assert _score(index, "night") == 0.0


def test_score_saturates_instead_of_growing_with_count():
    few = build_facility_index(cctv=[], lights=[NEAR] * LIGHT_SATURATION)
    many = build_facility_index(cctv=[], lights=[NEAR] * (LIGHT_SATURATION * 10))
    assert _score(few, "night") == _score(many, "night")


def test_lights_matter_more_at_night_and_cctv_more_by_day():
    lights_only = build_facility_index(cctv=[], lights=[NEAR] * 5)
    cctv_only = build_facility_index(cctv=[NEAR] * 5, lights=[])
    assert _score(lights_only, "night") > _score(lights_only, "day")
    assert _score(cctv_only, "day") > _score(cctv_only, "night")


def test_unknown_lights_area_is_judged_by_cctv_alone():
    # 보안등 데이터가 없는 구간은 "깜깜함(0점)"도 "중간(50점)"도 아니다 — CCTV만으로 판단한다.
    cctv_only = build_facility_index(cctv=[NEAR], lights=[])

    unknown = edge_local_scores(cctv_only, [ORIGIN], "night", lights_known=[False])[0]
    known_dark = edge_local_scores(cctv_only, [ORIGIN], "night", lights_known=[True])[0]

    assert unknown == 100.0  # CCTV가 포화 → 그 부분 만점
    assert known_dark < unknown  # 보안등이 정말 0개인 곳은 깎인다


def test_unknown_lights_keep_the_cctv_part():
    # 보안등을 모르는 구간이라도 CCTV 밀도는 그대로 반영된다
    with_cctv = build_facility_index(cctv=[NEAR], lights=[])
    without = build_facility_index(cctv=[], lights=[])

    assert (
        edge_local_scores(with_cctv, [ORIGIN], "day", lights_known=[False])[0]
        > edge_local_scores(without, [ORIGIN], "day", lights_known=[False])[0]
    )


def test_scores_are_in_range_and_one_per_point():
    index = build_facility_index(cctv=[NEAR], lights=[NEAR])
    scores = edge_local_scores(index, [ORIGIN, FAR, NEAR], "night")
    assert len(scores) == 3
    assert all(0.0 <= s <= 100.0 for s in scores)


def test_nearby_stores_raise_the_score():
    shops = build_facility_index(cctv=[], lights=[], stores=[NEAR] * 3)
    empty = build_facility_index(cctv=[], lights=[], stores=[FAR])
    assert _score(shops, "day") > _score(empty, "day")


def test_only_convenience_stores_count_at_night():
    # 밤엔 일반 상점이 문을 닫는다 — 편의점(24시간, 대부분 여성안심지킴이집)만 사람 눈으로 본다.
    shops_only = build_facility_index(cctv=[], lights=[], stores=[NEAR] * 3, convenience=[FAR])
    convenience = build_facility_index(cctv=[], lights=[], stores=[NEAR] * 3, convenience=[NEAR])

    assert _score(convenience, "night") > _score(shops_only, "night")
    assert _score(convenience, "day") == _score(shops_only, "day")


def test_night_falls_back_to_all_stores_without_convenience_data():
    with_shops = build_facility_index(cctv=[], lights=[], stores=[NEAR] * 3)
    empty = build_facility_index(cctv=[], lights=[], stores=[FAR])
    assert _score(with_shops, "night") > _score(empty, "night")


def test_nightlife_nearby_lowers_the_score_at_night_only():
    bars = build_facility_index(cctv=[NEAR], lights=[NEAR], nightlife=[NEAR])
    quiet = build_facility_index(cctv=[NEAR], lights=[NEAR], nightlife=[FAR])

    assert _score(bars, "night") < _score(quiet, "night")
    assert _score(bars, "day") == _score(quiet, "day")


def test_nearby_accident_hotspot_lowers_the_score():
    hotspot = build_facility_index(cctv=[NEAR], lights=[NEAR], accidents=[NEAR])
    clear = build_facility_index(cctv=[NEAR], lights=[NEAR], accidents=[FAR])
    assert _score(hotspot, "night") < _score(clear, "night")


# ORIGIN을 감싸는 약 200m 크기 공원
PARK_WKT = "POLYGON ((126.999 37.499, 127.001 37.499, 127.001 37.501, 126.999 37.501, 126.999 37.499))"


def test_segments_inside_a_park_or_riverside_lose_points_at_night_only():
    park = shapely.from_wkt(PARK_WKT)
    in_park = build_facility_index(cctv=[NEAR], lights=[NEAR], isolated_areas=[park])
    park_elsewhere = build_facility_index(cctv=[NEAR], lights=[NEAR], isolated_areas=[shapely.affinity.translate(park, yoff=0.01)])

    assert _score(in_park, "night") < _score(park_elsewhere, "night")
    assert _score(in_park, "day") == _score(park_elsewhere, "day")


def test_isolated_areas_file_loads_every_kind(tmp_path):
    facilities = tmp_path / "facility_points.json"
    facilities.write_text(json.dumps({"cctv": [], "lights": []}))
    areas = tmp_path / "isolated_areas.json"
    areas.write_text(json.dumps({"bbox": [0, 0, 1, 1], "park": [], "water": [PARK_WKT]}))

    index = load_facility_index(facilities, tmp_path / "none.json", tmp_path / "none.json", areas)

    assert index.isolated_tree is not None
    assert edge_local_scores(index, [ORIGIN], "night")[0] < edge_local_scores(index, [FAR], "night")[0]


def test_store_and_accident_files_load_alongside_facilities(tmp_path):
    facilities = tmp_path / "facility_points.json"
    facilities.write_text(json.dumps({"cctv": [], "lights": []}))
    pois = tmp_path / "safety_pois.json"
    pois.write_text(json.dumps({"police": [], "stores": [list(NEAR)] * 3}))
    accidents = tmp_path / "accident_points.json"
    accidents.write_text(json.dumps([list(FAR)]))
    night_places = tmp_path / "night_places.json"
    night_places.write_text(json.dumps({"convenience": [list(NEAR)], "nightlife": [list(FAR)]}))

    index = load_facility_index(facilities, pois, accidents, tmp_path / "none.json", night_places)

    assert index.store_tree is not None and index.accident_tree is not None
    assert index.convenience_tree is not None and index.nightlife_tree is not None
    assert _score(index, "day") > 0


def test_missing_points_file_means_no_index(tmp_path):
    assert load_facility_index(tmp_path / "nope.json") is None


def test_geocoded_lights_are_included_when_loading(tmp_path):
    # 좌표가 있던 보안등은 없고, 주소를 변환해 복구한 것만 있는 경우에도 점수가 나와야 한다
    path = tmp_path / "facility_points.json"
    path.write_text(
        json.dumps({"bbox": [126.3, 36.85, 127.9, 38.3], "cctv": [], "lights": [], "lights_geocoded": [list(NEAR)] * 2})
    )

    index = load_facility_index(path)

    assert index is not None
    assert _score(index, "night") > 0


def test_index_loads_from_points_file(tmp_path):
    path = tmp_path / "facility_points.json"
    path.write_text(json.dumps({"bbox": [126.3, 36.85, 127.9, 38.3], "cctv": [list(NEAR)], "lights": [list(NEAR)]}))

    index = load_facility_index(path)

    assert index is not None
    assert _score(index, "night") > 0


def test_unsubmitted_cctv_area_is_judged_by_lights_alone():
    lights_only = build_facility_index(cctv=[], lights=[NEAR] * LIGHT_SATURATION)

    unknown = edge_local_scores(lights_only, [ORIGIN], "night", cctv_known=[False])[0]
    known_none = edge_local_scores(lights_only, [ORIGIN], "night", cctv_known=[True])[0]

    assert unknown == 100.0
    assert known_none < unknown


def test_when_neither_cctv_nor_lights_were_submitted_the_part_is_dropped():
    # 둘 다 모르면 그 부분을 빼고 나머지(사고다발 등)만으로 판단한다 — 0점도 50점도 아니다.
    index = build_facility_index(cctv=[], lights=[], accidents=[FAR])

    score = edge_local_scores(index, [ORIGIN], "night", lights_known=[False], cctv_known=[False])[0]

    assert score == 100.0  # 사고다발지역 근처가 아니라는 것만 안다
