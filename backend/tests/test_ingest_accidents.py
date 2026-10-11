import scripts.ingest_public_data as ingest


def test_only_recent_accident_hotspots_are_used(tmp_path, monkeypatch):
    csv_path = tmp_path / "accidents.csv"
    rows = [
        "사고연도,사고다발지역시도시군구,위도,경도",
        "2012,경기도 수원시1,37.1,127.1",  # 오래된 지점 — 빠져야 한다
        "2021,경기도 수원시1,37.2,127.2",  # 최신(2024)-3 = 2021 — 빠져야 한다
        "2022,경기도 수원시1,37.3,127.3",
        "2024,경기도 안산시1,37.4,126.8",
        "2024,부산광역시 중구1,35.1,129.0",  # 서비스 지역 밖
    ]
    csv_path.write_text("\n".join(rows) + "\n", encoding="cp949")
    monkeypatch.setattr(ingest, "ACCIDENT_CSV", csv_path)

    assert list(ingest.iter_accident_points()) == [(37.3, 127.3), (37.4, 126.8)]
