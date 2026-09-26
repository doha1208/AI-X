import pytest

from app.services.crime_rate import (
    crime_rate_per_10k,
    parse_floating_population_csv,
    parse_population_csv,
    region_key_for,
)


def _write_csv(path, rows):
    header = "행정구역,2024년01월_총인구수,2024년01월_세대수,2024년02월_총인구수,2024년02월_세대수\n"
    path.write_bytes((header + "\n".join(rows) + "\n").encode("cp949"))


def test_population_is_averaged_over_months_and_keyed_by_region_name(tmp_path):
    csv_path = tmp_path / "pop.csv"
    _write_csv(
        csv_path,
        [
            '서울특별시  (1100000000),"9,000,000","4,000,000","9,000,000","4,000,000"',
            '서울특별시 종로구 (1111000000),"100,000","50,000","102,000","51,000"',
            '경기도  (4100000000),"13,000,000","6,000,000","13,000,000","6,000,000"',
            '경기도 수원시 (4111000000),"1,000,000","500,000","1,200,000","600,000"',
            '경기도 수원시 장안구 (4111100000),"300,000","150,000","300,000","150,000"',
            '부산광역시 중구 (2611000000),"40,000","20,000","40,000","20,000"',
        ],
    )

    pop = parse_population_csv(csv_path)

    assert pop["종로구"] == 101_000  # 서울 구는 시도 접두어 없이
    assert pop["수원시"] == 1_100_000  # 1월·2월 평균
    assert pop["수원시 장안구"] == 300_000
    assert set(pop) == {"종로구", "수원시", "수원시 장안구"}  # 시도 합계 행·서울경기 밖 지역은 제외


def test_sub_district_falls_back_to_its_city():
    known = {"수원시", "종로구", "양평군"}
    assert region_key_for("수원시 장안구", known) == "수원시"
    assert region_key_for("종로구", known) == "종로구"
    assert region_key_for("양평군", known) == "양평군"


def test_unknown_region_is_reported_instead_of_silently_zero():
    with pytest.raises(KeyError):
        region_key_for("없는시 어느구", {"수원시"})


def test_rate_is_per_ten_thousand_residents():
    assert crime_rate_per_10k(500, 100_000) == 50.0


def test_rate_rejects_empty_population():
    with pytest.raises(ValueError):
        crime_rate_per_10k(10, 0)


def _write_floating_csv(path, rows):
    header = "행정동코드,시도명,시군구명,행정동명,시간대별,내외국인구분,10~14세 남성 인구수,20~24세 여성 인구수,기준년월일\n"
    path.write_bytes((header + "\n".join(rows) + "\n").encode("cp949"))


def test_floating_population_is_summed_per_gu_and_averaged_over_time(tmp_path):
    csv_path = tmp_path / "floating.csv"
    _write_floating_csv(
        csv_path,
        [
            "41117596,경기도,수원시 영통구,망포2동,0,N,10.0,5.0,20240101",
            "41117597,경기도,수원시 영통구,망포3동,0,N,20.0,5.0,20240101",
            "41117596,경기도,수원시 영통구,망포2동,1,N,8.0,4.0,20240101",
            "41117597,경기도,수원시 영통구,망포3동,1,N,12.0,4.0,20240101",
        ],
    )

    result = parse_floating_population_csv(csv_path)

    # 시간대 0: (10+5)+(20+5)=40, 시간대 1: (8+4)+(12+4)=28 -> 평균 34
    assert result["수원시 영통구"] == 34.0


def test_floating_population_keys_are_gu_names_without_sido_prefix(tmp_path):
    csv_path = tmp_path / "floating.csv"
    _write_floating_csv(csv_path, ["41117596,경기도,수원시 영통구,망포2동,0,N,1.0,1.0,20240101"])

    result = parse_floating_population_csv(csv_path)

    assert set(result) == {"수원시 영통구", "수원시"}


def test_floating_population_also_rolls_up_to_city_level(tmp_path):
    # 범죄 통계는 구가 나뉜 시라도 시 단위 합계 하나뿐이라, 구 값과 별도로 시 단위 합도 필요하다.
    csv_path = tmp_path / "floating.csv"
    _write_floating_csv(
        csv_path,
        [
            "41117596,경기도,수원시 영통구,망포2동,0,N,10.0,5.0,20240101",
            "41111100,경기도,수원시 장안구,파장동,0,N,20.0,5.0,20240101",
        ],
    )

    result = parse_floating_population_csv(csv_path)

    assert result["수원시 영통구"] == 15.0
    assert result["수원시 장안구"] == 25.0
    assert result["수원시"] == 40.0  # 같은 시의 모든 구 합계
