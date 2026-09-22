import pytest

from app.services.crime_rate import crime_rate_per_10k, parse_population_csv, region_key_for


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
