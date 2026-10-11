from app.services.address_geocode import parse_address_response, query_candidates


def test_jibun_address_is_tried_first_then_road_address():
    got = query_candidates("서울특별시 마포구 서교동 353-2", "서울특별시 마포구 양화로 129")
    assert got == ["서울특별시 마포구 서교동 353-2", "서울특별시 마포구 양화로 129"]


def test_trailing_business_name_is_stripped_as_a_last_resort():
    got = query_candidates("", "서울특별시 마포구 양화로 129 디키즈코리아")
    assert got == ["서울특별시 마포구 양화로 129 디키즈코리아", "서울특별시 마포구 양화로 129"]


def test_road_names_with_numbers_keep_their_building_number():
    got = query_candidates("", "서울특별시 마포구 양화로15길 16 3층")
    assert got[-1] == "서울특별시 마포구 양화로15길 16"


def test_missing_space_between_district_and_dong_is_added_as_a_candidate():
    got = query_candidates("서울특별시 용산구한남동 1-2", "")
    assert got == ["서울특별시 용산구한남동 1-2", "서울특별시 용산구 한남동 1-2"]


def test_legit_dong_names_starting_with_gu_are_not_split():
    # "구로동"은 그 자체가 동 이름 — 앞에 구/군 글자가 없으니 건드리지 않는다
    assert query_candidates("서울특별시 구로구 구로동 1", "") == ["서울특별시 구로구 구로동 1"]


def test_missing_or_duplicate_addresses_are_dropped():
    assert query_candidates("", "") == []
    assert query_candidates("서울특별시 용산구 이태원동 1", "서울특별시 용산구 이태원동 1") == [
        "서울특별시 용산구 이태원동 1"
    ]


def test_kakao_response_is_read_as_lat_lng():
    payload = {"documents": [{"x": "126.9199", "y": "37.5547"}, {"x": "0", "y": "0"}]}
    assert parse_address_response(payload) == (37.5547, 126.9199)


def test_no_match_returns_none():
    assert parse_address_response({"documents": []}) is None
    assert parse_address_response({}) is None
