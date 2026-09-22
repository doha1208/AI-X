import json

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


def test_unknown_lights_area_is_neutral_between_dark_and_lit():
    dark = build_facility_index(cctv=[], lights=[FAR])
    lit = build_facility_index(cctv=[], lights=[NEAR] * LIGHT_SATURATION)

    unknown = edge_local_scores(dark, [ORIGIN], "night", lights_known=[False])[0]

    assert _score(dark, "night") < unknown < _score(lit, "night")


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
