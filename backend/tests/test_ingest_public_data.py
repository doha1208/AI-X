import scripts.ingest_public_data as ingest


def test_store_extraction_reads_only_gyeonggi_from_archive(tmp_path, monkeypatch):
    import csv
    import io
    import json
    import zipfile

    from scripts import extract_store_points

    source = tmp_path / "소상공인시장진흥공단_상가(상권)정보_20260630.zip"
    fields = ["상권업종대분류명", "상권업종소분류명", "층정보", "위도", "경도"]
    with zipfile.ZipFile(source, "w") as archive:
        for region, lat in (("서울", "37.55"), ("경기", "37.30"), ("부산", "35.18")):
            content = io.StringIO()
            writer = csv.DictWriter(content, fieldnames=fields)
            writer.writeheader()
            writer.writerow({"상권업종대분류명": "소매", "상권업종소분류명": "편의점", "층정보": "1", "위도": lat, "경도": "127.0"})
            archive.writestr(f"상가_{region}_202606.csv", content.getvalue())
    output = tmp_path / "store_points.json"
    monkeypatch.setattr(extract_store_points, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(extract_store_points, "OUTPUT_JSON", output)

    extract_store_points.main()

    points = json.loads(output.read_text(encoding="utf-8"))
    assert points["stores"] == [[37.3, 127.0]]
    assert points["convenience"] == points["stores"]


def test_night_places_include_only_gyeonggi(monkeypatch):
    from scripts import fetch_night_places

    items = [
        {"ROAD_NM_ADDR": "서울특별시 종로구", "lat": 37.57},
        {"ROAD_NM_ADDR": "경기도 수원시", "lat": 37.28},
        {"ROAD_NM_ADDR": "부산광역시 중구", "lat": 35.1},
    ]
    monkeypatch.setattr(fetch_night_places, "_fetch_page", lambda *_: {"totalCount": 3, "items": {"item": items}})
    monkeypatch.setattr(fetch_night_places, "_to_point", lambda item: [item["lat"], 127.0])

    assert fetch_night_places.fetch_service("rest_cafes", "key") == [[37.28, 127.0]]


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


def test_night_floating_population_averages_night_hours_per_dong(tmp_path):
    import zipfile

    header = "ADMI_CD,CTY_NM,ADMI_NM,TIME_CD,FORN_GB,M_20_CNT,F_20_CNT,ETL_YMD"
    rows = [
        "41117596,x,x,23,N,10,10,20260301",  # 밤 23시: 내국인 20 + 외국인 4 = 24
        "41117596,x,x,23,F,2,2,20260301",
        "41117596,x,x,2,N,3,3,20260302",  # 밤 2시: 6
        "41117596,x,x,14,N,500,500,20260301",  # 낮 — 빠져야 한다
    ]
    archive = tmp_path / "유동인구_행정동 단위 집계_202603.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("T22_GG_ADMI_FLOWPOP_202603_x.csv", "\n".join([header, *rows]) + "\n")

    result = ingest.parse_night_floating_population([archive])

    assert result == {"4111759600": (24 + 6) / 2}


def test_store_extraction_keeps_street_level_food_and_retail_and_convenience():
    from scripts.extract_store_points import extract

    def row(category, sub, floor, lat="37.5"):
        return {"상권업종대분류명": category, "상권업종소분류명": sub, "층정보": floor, "위도": lat, "경도": "127.0"}

    rows = [
        row("음식", "카페", ""),  # 층 정보 없음 → 길가로 본다
        row("소매", "편의점", "1"),
        row("소매", "편의점", "3"),  # 3층 편의점은 길을 보지 않는다
        row("교육", "입시·교과학원", "1"),  # 학원은 상점이 아니다
        row("음식", "치킨", "지"),
    ]

    result = extract(rows)

    assert len(result["stores"]) == 3
    assert result["convenience"] == [[37.5, 127.0]]


def test_police_points_keep_staffed_facilities_including_neighbouring_regions():
    # 경계의 동은 가장 가까운 지구대가 서울·인천일 수 있어 지역으로 거르지 않는다.
    from scripts.fetch_police_points import staffed_points

    def row(sido, kind):
        # EPSG:3857 좌표 — 수원시 장안구 근처
        return {"STDG_CTPV_CD": sido, "FCLT_TYPE": kind, "XMAP_CRTS": 14137820.0, "YMAP_CRTS": 4479700.0}

    rows = [row("41", "지구대"), row("41", "파출소"), row("41", "치안센터"), row("11", "경찰서")]

    points = staffed_points(rows)

    assert len(points) == 3  # 치안센터만 빠진다
    lat, lng = points[0]
    assert 37.2 < lat < 37.4 and 126.9 < lng < 127.1
