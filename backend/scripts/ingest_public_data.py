"""공공데이터(CCTV·보안등·구 단위 범죄통계)를 동 단위 안전 지수로 변환해 DB에 적재.

데이터 출처:
- CCTV: data.go.kr 전국CCTV표준데이터 (프로젝트 루트 CCTV정보.csv, "생활방범" 목적만 사용)
- 보안등: data.go.kr 전국보안등정보표준데이터 OpenAPI (SECURITY_LIGHT_API_KEY)
- 범죄: data.go.kr 경찰청_범죄 발생 지역별 통계 (구 단위 5대 범죄 합계, 프로젝트 루트 CSV)
- 경찰서·상점: OSM에서 extract_safety_pois.py로 미리 뽑은 data/osm/safety_pois.json
- 안전비상벨: data.go.kr 전국안전비상벨위치표준데이터 (프로젝트 루트 안전비상벨위치정보.csv)
- 교통사고 다발지역: data.go.kr 전국교통사고다발지역표준데이터 (프로젝트 루트 전국교통사고다발지역표준데이터.csv)
- 인구: jumin.mois.go.kr 주민등록 인구 및 세대현황(월간, 범죄 통계와 같은 연도의 서울·경기
  시군구; 프로젝트 루트 *주민등록인구및세대현황*.csv) — 범죄 건수를 1만 명당 범죄율로 보정
- 좌표→행정동 변환: build_dong_grid.py로 미리 만든 격자 캐시(app/data/dong_grid.json)

ponytail: 범죄 통계는 구 단위가 공개 최소 단위라 같은 구의 모든 동이 범죄
건수를 공유한다. CCTV/보안등은 격자 스냅으로 동 단위 밀도를 구해 차등을 준다.
매 실행마다 safety_zones 테이블을 통째로 다시 계산해 덮어쓴다(증분 아님).

사용법:
    backend/.venv/Scripts/python.exe scripts/ingest_public_data.py
    # 보안등 API를 다시 받지 않고 경찰서·상점·1만 명당 범죄율만 기존 DB에 다시 계산:
    backend/.venv/Scripts/python.exe scripts/ingest_public_data.py --refresh
    # 도로 구간별 밀도용 CCTV·보안등 좌표만 저장(API ~1,900회, 수 분~수십 분):
    backend/.venv/Scripts/python.exe scripts/ingest_public_data.py --dump-points
    # 위 CCTV·보안등 좌표는 그대로 두고 교통사고 다발지역 좌표만 추가:
    backend/.venv/Scripts/python.exe scripts/ingest_public_data.py --dump-accidents
"""
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from sqlalchemy import inspect, text

from app.db.session import Base, SessionLocal, engine
from app.models.safety_zone import SafetyZone
from app.services.crime_rate import crime_rate_per_10k, parse_population_csv, region_key_for
from app.services.poi_factors import nearest_bell_distances_m, nearest_police_distances_m
from app.services.safety_score import compute_safety_scores, flag_unknown_streetlights

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
PROJECT_ROOT = BACKEND_DIR.parent

CCTV_CSV = PROJECT_ROOT / "CCTV정보.csv"
BELL_CSV = PROJECT_ROOT / "안전비상벨위치정보.csv"
ACCIDENT_CSV = PROJECT_ROOT / "전국교통사고다발지역표준데이터.csv"
CRIME_CSV = PROJECT_ROOT / "경찰청_범죄 발생 지역별 통계_20241231.csv"
GRID_PATH = BACKEND_DIR / "app" / "data" / "dong_grid.json"
ENV_PATH = BACKEND_DIR / ".env"
# extract_safety_pois.py가 OSM PBF에서 뽑아둔 경찰서·상점 좌표.
POIS_PATH = BACKEND_DIR / "data" / "osm" / "safety_pois.json"
# --dump-points가 만드는 CCTV·보안등 좌표(도로 구간별 밀도 계산용).
FACILITY_POINTS_PATH = BACKEND_DIR / "data" / "osm" / "facility_points.json"
# 안전비상벨 좌표(서울+경기 범위) — 안전지수 계산과 지도 표시(app/services/bells.py) 둘 다 이 파일을 쓴다.
BELL_POINTS_PATH = BACKEND_DIR / "data" / "osm" / "bell_points.json"
# 좌표 없이 주소만 있는 보안등 행(주소별 개수) — geocode_light_addresses.py가 좌표로 바꾼다.
LIGHT_ADDRESSES_PATH = BACKEND_DIR / "data" / "osm" / "light_addresses.json"

FIVE_MAJOR_CRIME_SUBCATS = {
    "살인기수", "살인미수등", "강도",
    "강간", "유사강간", "강제추행", "기타 강간/강제추행등",
    "절도범죄",
    "상해", "폭행", "체포/감금", "협박", "약취/유인", "폭력행위등", "공갈", "손괴",
}


def load_env_value(name: str) -> str:
    text = ENV_PATH.read_text(encoding="utf-8")
    match = re.search(rf"{name}=(.*)", text)
    if not match or not match.group(1).strip():
        raise RuntimeError(f"{name} not set in backend/.env")
    return match.group(1).strip()


def load_grid() -> tuple[float, dict, tuple[float, float, float, float]]:
    data = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    return data["step"], data["cells"], tuple(data["bbox"])


def snap_to_dong(lat: float, lng: float, step: float, cells: dict, bbox) -> dict | None:
    west, south, east, north = bbox
    if not (west - step <= lng <= east + step and south - step <= lat <= north + step):
        return None
    grid_lat = round(round((lat - south) / step) * step + south, 5)
    grid_lng = round(round((lng - west) / step) * step + west, 5)
    cell = cells.get(f"{grid_lat}:{grid_lng}")
    if cell:
        return cell
    # 경계 근처라 정확한 칸이 비어있으면 3x3 이웃 중 가장 가까운 칸을 사용
    best, best_dist = None, None
    for dlat in (-step, 0, step):
        for dlng in (-step, 0, step):
            neighbor = cells.get(f"{round(grid_lat + dlat, 5)}:{round(grid_lng + dlng, 5)}")
            if neighbor:
                dist = (neighbor["lat"] - lat) ** 2 + (neighbor["lng"] - lng) ** 2
                if best_dist is None or dist < best_dist:
                    best, best_dist = neighbor, dist
    return best


def load_crime_by_gu() -> dict:
    """구/시/군 이름 -> 5대 범죄 합계. 서울 25개 구(컬럼 2:27) +
    경기도 31개 시/군(컬럼 78:109, 실측 확인)을 합쳐서 반환한다."""
    with CRIME_CSV.open(encoding="cp949", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    col_indices = list(range(2, 27)) + list(range(78, 109))
    region_cols = [header[i] for i in col_indices]
    totals = [0] * len(col_indices)
    for row in rows:
        if row[1] in FIVE_MAJOR_CRIME_SUBCATS:
            for i, col_idx in enumerate(col_indices):
                totals[i] += int(row[col_idx])

    result: dict[str, int] = {}
    for name, total in zip(region_cols, totals):
        result[name.replace("서울 ", "").replace("경기도 ", "")] = total
    return result


def iter_cctv_points():
    """서울+경기 '생활방범' CCTV의 (lat, lng)."""
    with CCTV_CSV.open(encoding="cp949", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("설치목적구분", "").strip() != "생활방범":
                continue
            addr = row.get("소재지도로명주소") or row.get("소재지지번주소") or ""
            if not addr.startswith(("서울", "경기")):
                continue
            try:
                lat = float(row["WGS84위도"])
                lng = float(row["WGS84경도"])
            except (KeyError, ValueError):
                continue
            yield lat, lng


def iter_bell_points():
    """서울+경기 안전비상벨의 (lat, lng). CCTV와 같은 표준데이터 컬럼(WGS84위도/경도)을 쓴다."""
    with BELL_CSV.open(encoding="cp949", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            addr = row.get("소재지도로명주소") or row.get("소재지지번주소") or ""
            if not addr.startswith(("서울", "경기")):
                continue
            try:
                lat = float(row["WGS84위도"])
                lng = float(row["WGS84경도"])
            except (KeyError, ValueError):
                continue
            yield lat, lng


def iter_accident_points():
    """서울+경기 교통사고 다발지역의 (lat, lng) — 사고건수만큼 반복해 밀도 계산 시 자연히 가중된다."""
    with ACCIDENT_CSV.open(encoding="cp949", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            addr = row.get("사고다발지역시도시군구", "")
            if not addr.startswith(("서울", "경기")):
                continue
            try:
                lat = float(row["위도"])
                lng = float(row["경도"])
                count = max(1, int(row.get("사고건수", 1)))
            except (KeyError, ValueError):
                continue
            for _ in range(count):
                yield lat, lng


def dump_accident_points() -> None:
    """기존 facility_points.json(CCTV·보안등, 특히 오래 걸린 lights_geocoded)을 건드리지 않고
    교통사고 다발지역 좌표만 추가/갱신한다."""
    payload = load_facility_points()
    west, south, east, north = payload["bbox"]

    def inside(lat: float, lng: float) -> bool:
        return west <= lng <= east and south <= lat <= north

    accidents = [[round(lat, 6), round(lng, 6)] for lat, lng in iter_accident_points() if inside(lat, lng)]
    payload["accidents"] = accidents
    _atomic_write_json(FACILITY_POINTS_PATH, payload)
    print(f"Saved {len(accidents)} accident-weighted points to {FACILITY_POINTS_PATH}")


def dump_bell_points() -> list[tuple[float, float]]:
    """비상벨 CSV를 한 번만 읽어 (동 점수 계산용 리스트를 돌려주고) 지도 표시용 JSON도 저장한다."""
    points = list(iter_bell_points())
    _atomic_write_json(BELL_POINTS_PATH, [[round(lat, 6), round(lng, 6)] for lat, lng in points])
    return points


def load_facility_points() -> dict:
    """--dump-points(와 geocode_light_addresses.py)가 만든 CCTV·보안등 좌표."""
    if not FACILITY_POINTS_PATH.exists():
        raise RuntimeError(f"{FACILITY_POINTS_PATH} 없음 — 먼저 ingest_public_data.py --dump-points를 실행하세요.")
    return json.loads(FACILITY_POINTS_PATH.read_text(encoding="utf-8"))


def count_facilities_by_dong(step: float, cells: dict, bbox) -> tuple[dict, dict]:
    """(동별 CCTV 수, 동별 보안등 수). 보안등은 원래 좌표가 있던 행과 주소를 좌표로 바꾼 행을 합친다."""
    points = load_facility_points()
    cctv = count_points_by_dong(points["cctv"], step, cells, bbox)
    lights = count_points_by_dong(points["lights"] + points.get("lights_geocoded", []), step, cells, bbox)
    return cctv, lights


def _fetch_json(url: str, attempts: int = 5) -> dict:
    """일시적인 타임아웃/네트워크 오류 한 번에 1,900페이지짜리 수집이 통째로 죽지 않게 재시도한다."""
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt == attempts:
                raise
            time.sleep(2 * attempt)


def iter_light_rows():
    """보안등 표준데이터 API의 행을 (lat, lng, 지번주소, 도로명주소, 기관명)으로 돌려준다.

    좌표가 비어 있으면 lat/lng는 None이다 — 강남·마포·용산·고양·김포처럼 주소만 올린 지자체가
    있어서, 좌표 없는 행을 버리면 그 지역이 "보안등 0개"로 잡힌다.

    보안등 표준데이터 API는 instt_code 없이도 전국 데이터를 페이지네이션으로
    받을 수 있다(실측 확인, totalCount~186만 건). 서울+경기 밖 행은 호출부가 거른다.

    ponytail: 전국 페이지를 순서대로 다 훑는 단순한 방식 — 기관코드/지역별로
    쪼개 병렬 호출하면 더 빠르겠지만, 이 스크립트는 가끔 한 번 돌리는 배치라
    단순함이 낫다.
    """
    key = load_env_value("SECURITY_LIGHT_API_KEY")
    page = 1
    while True:
        params = {
            "serviceKey": key,
            "pageNo": str(page),
            "numOfRows": "1000",
            "type": "json",
        }
        url = "https://api.data.go.kr/openapi/tn_pubr_public_scrty_lmp_api?" + urllib.parse.urlencode(params)
        body = _fetch_json(url)
        payload = body.get("body") or {}
        items = (payload.get("items") or {}).get("item")
        if not items:
            break
        if isinstance(items, dict):
            items = [items]
        for item in items:
            try:
                lat, lng = float(item["latitude"]), float(item["longitude"])
            except (KeyError, ValueError, TypeError):
                lat = lng = None
            yield (
                lat,
                lng,
                (item.get("lnmadr") or "").strip(),
                (item.get("rdnmadr") or "").strip(),
                (item.get("insttNm") or "").strip(),
            )
        total_count = payload.get("totalCount", 0)
        if page * 1000 >= total_count:
            break
        if page % 100 == 0:
            print(f"  light pages {page}/{-(-total_count // 1000)}")
        page += 1
        time.sleep(0.1)


def dump_facility_points() -> None:
    """도로 구간 단위 밀도 계산용으로 CCTV·보안등 좌표를 서울+경기 범위만 JSON에 저장한다."""
    _, _, (west, south, east, north) = load_grid()

    def inside(lat: float, lng: float) -> bool:
        return west <= lng <= east and south <= lat <= north

    print("Collecting CCTV points...")
    cctv = [[round(lat, 6), round(lng, 6)] for lat, lng in iter_cctv_points() if inside(lat, lng)]
    print(f"  {len(cctv)} CCTV points")
    print("Fetching security light rows (paginated API, ~1,900 calls)...")
    lights: list[list[float]] = []
    address_only: dict[tuple[str, str], int] = {}
    for lat, lng, jibun, road, institution in iter_light_rows():
        if lat is not None:
            if inside(lat, lng):
                lights.append([round(lat, 6), round(lng, 6)])
        elif institution.startswith(("서울특별시", "경기도")) and (jibun or road):
            address_only[(jibun, road)] = address_only.get((jibun, road), 0) + 1
    print(f"  {len(lights)} light points with coordinates, {sum(address_only.values())} address-only rows "
          f"({len(address_only)} unique addresses)")

    # lights_geocoded는 geocode_light_addresses.py가 채운다(주소→좌표 변환 결과).
    payload = {"bbox": [west, south, east, north], "cctv": cctv, "lights": lights, "lights_geocoded": []}
    _atomic_write_json(FACILITY_POINTS_PATH, payload)
    _atomic_write_json(
        LIGHT_ADDRESSES_PATH,
        [{"jibun": jibun, "road": road, "n": n} for (jibun, road), n in address_only.items()],
    )
    print(f"Saved {FACILITY_POINTS_PATH} and {LIGHT_ADDRESSES_PATH}")


def _atomic_write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load_pois() -> dict:
    if not POIS_PATH.exists():
        raise RuntimeError(f"{POIS_PATH} 없음 — 먼저 scripts/extract_safety_pois.py를 실행하세요.")
    return json.loads(POIS_PATH.read_text(encoding="utf-8"))


def count_points_by_dong(points: list, step: float, cells: dict, bbox) -> dict:
    counts: dict[str, int] = {}
    for lat, lng in points:
        cell = snap_to_dong(lat, lng, step, cells, bbox)
        if cell:
            counts[cell["dong_code"]] = counts.get(cell["dong_code"], 0) + 1
    return counts


def add_poi_factors(records: list[dict], step: float, cells: dict, bbox) -> None:
    """dong_code/lat/lng를 가진 레코드에 경찰서까지 거리(police_dist_m), 비상벨까지 거리(bell_dist_m),
    상점 수(store_count)를 채운다."""
    pois = load_pois()
    centroids = [(r["lat"], r["lng"]) for r in records]
    police_dists = nearest_police_distances_m(centroids, [(lat, lng) for lat, lng in pois["police"]])
    bell_points = dump_bell_points()
    bell_dists = nearest_bell_distances_m(centroids, bell_points)
    stores_by_dong = count_points_by_dong(pois["stores"], step, cells, bbox)
    for record, police_dist, bell_dist in zip(records, police_dists, bell_dists):
        record["police_dist_m"] = police_dist
        record["bell_dist_m"] = bell_dist
        record["store_count"] = stores_by_dong.get(record["dong_code"], 0)
    print(
        f"  {len(pois['police'])} police, {len(bell_points)} bells, {len(pois['stores'])} stores "
        f"-> {sum(stores_by_dong.values())} stores assigned"
    )


def load_population() -> dict[str, float]:
    """프로젝트 루트의 주민등록 인구 및 세대현황 CSV(jumin.mois.go.kr, 월간, 시군구)를 모두 합친다.

    서울과 경기를 따로 내려받아도, 전국을 한 번에 받아도 된다. 같은 지역이 여러 파일에 있으면
    파일 이름 순으로 나중 것이 이긴다.
    """
    files = sorted(PROJECT_ROOT.glob("*주민등록인구및세대현황*.csv"))
    if not files:
        raise RuntimeError(
            "주민등록 인구 CSV 없음 — jumin.mois.go.kr에서 서울·경기 시군구 인구(범죄 통계와 같은 연도)를 "
            f"받아 {PROJECT_ROOT}에 두세요."
        )
    population: dict[str, float] = {}
    for path in files:
        population.update(parse_population_csv(path))
    return population


def add_crime_rate(records: list[dict], cells: dict, crime_by_gu: dict) -> None:
    """레코드에 시·군·구 단위로 맞춘 범죄 건수(crime_count)와 1만 명당 범죄율(crime_rate)을 채운다.

    범죄 통계는 시 단위("수원시")인데 동 격자는 구 단위("수원시 장안구")라, 같은 단위로 묶는다.
    이름이 안 맞으면 0건으로 두지 않고 KeyError로 멈춘다.
    """
    population = load_population()
    known = set(crime_by_gu) & set(population)
    gu_by_dong = {cell["dong_code"]: cell["gu_name"] for cell in cells.values()}
    for record in records:
        key = region_key_for(gu_by_dong[record["dong_code"]], known)
        record["crime_count"] = crime_by_gu[key]
        record["crime_rate"] = crime_rate_per_10k(crime_by_gu[key], population[key])
    print(f"  crime rate assigned for {len(records)} dongs ({len(known)} regions)")


def ensure_new_columns() -> None:
    """이미 있는 safety_zones 테이블에 새 컬럼이 없으면 추가한다(create_all은 기존 테이블을 바꾸지 않음)."""
    existing = {col["name"] for col in inspect(engine).get_columns("safety_zones")}
    new_columns = (
        ("police_dist_m", "FLOAT"),
        ("store_count", "INTEGER DEFAULT 0"),
        ("crime_rate", "FLOAT"),
        ("lights_known", "BOOLEAN DEFAULT TRUE"),
        ("bell_dist_m", "FLOAT"),
    )
    with engine.begin() as conn:
        for name, ddl in new_columns:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE safety_zones ADD COLUMN {name} {ddl}"))


def refresh_derived_factors() -> None:
    """보안등 API를 다시 받지 않고, DB의 기존 동 행에 경찰서·상점·범죄율을 채워 점수를 다시 계산한다.

    CCTV·보안등 개수는 좌표 파일(--dump-points, 주소를 좌표로 바꾼 보안등 포함)에서 다시 센다.
    범죄 건수는 시 단위로 바로잡힌 값으로 덮어쓴다.
    """
    Base.metadata.create_all(bind=engine)
    ensure_new_columns()
    step, cells, bbox = load_grid()
    crime_by_gu = load_crime_by_gu()

    db = SessionLocal()
    try:
        zones = db.query(SafetyZone).all()
        cctv_by_dong, light_by_dong = count_facilities_by_dong(step, cells, bbox)
        records = [
            {
                "dong_code": z.dong_code,
                "lat": z.lat,
                "lng": z.lng,
                "cctv_count": cctv_by_dong.get(z.dong_code, 0),
                "streetlight_count": light_by_dong.get(z.dong_code, 0),
            }
            for z in zones
        ]
        print("Adding police/store factors and crime rate to existing dongs...")
        add_poi_factors(records, step, cells, bbox)
        add_crime_rate(records, cells, crime_by_gu)
        flagged = flag_unknown_streetlights(records)
        print(f"  보안등 데이터가 사실상 없어 '모름'으로 보는 시·군·구 {len(flagged)}곳: {flagged}")
        compute_safety_scores(records)
        by_code = {r["dong_code"]: r for r in records}
        for zone in zones:
            rec = by_code[zone.dong_code]
            zone.cctv_count = rec["cctv_count"]
            zone.streetlight_count = rec["streetlight_count"]
            zone.lights_known = rec["lights_known"]
            zone.police_dist_m = rec["police_dist_m"]
            zone.bell_dist_m = rec["bell_dist_m"]
            zone.store_count = rec["store_count"]
            zone.crime_count = rec["crime_count"]
            zone.crime_rate = rec["crime_rate"]
            zone.safety_score = rec["safety_score"]
        db.commit()
        print(f"Updated {len(zones)} dongs.")
    finally:
        db.close()


def build_dong_meta(cells: dict) -> dict:
    meta: dict[str, dict] = {}
    for cell in cells.values():
        code = cell["dong_code"]
        entry = meta.setdefault(
            code, {"dong_name": cell["dong_name"], "gu_name": cell["gu_name"], "lats": [], "lngs": []}
        )
        entry["lats"].append(cell["lat"])
        entry["lngs"].append(cell["lng"])
    return meta


def ingest():
    Base.metadata.create_all(bind=engine)
    ensure_new_columns()
    step, cells, bbox = load_grid()

    print("Loading crime stats by gu...")
    crime_by_gu = load_crime_by_gu()

    print("Counting CCTV and security lights by dong (from --dump-points output)...")
    cctv_by_dong, light_by_dong = count_facilities_by_dong(step, cells, bbox)
    print(f"  {sum(cctv_by_dong.values())} CCTV assigned across {len(cctv_by_dong)} dongs")
    print(f"  {sum(light_by_dong.values())} lights assigned across {len(light_by_dong)} dongs")

    dong_meta = build_dong_meta(cells)

    records = []
    for code, meta in dong_meta.items():
        records.append(
            {
                "dong_code": code,
                "dong_name": meta["dong_name"],
                "lat": sum(meta["lats"]) / len(meta["lats"]),
                "lng": sum(meta["lngs"]) / len(meta["lngs"]),
                "cctv_count": cctv_by_dong.get(code, 0),
                "streetlight_count": light_by_dong.get(code, 0),
            }
        )

    print("Adding police/store factors and crime rate...")
    add_poi_factors(records, step, cells, bbox)
    add_crime_rate(records, cells, crime_by_gu)
    flagged = flag_unknown_streetlights(records)
    print(f"  보안등 데이터가 사실상 없어 '모름'으로 보는 시·군·구 {len(flagged)}곳: {flagged}")
    compute_safety_scores(records)

    db = SessionLocal()
    try:
        db.query(SafetyZone).delete()
        for rec in records:
            db.add(SafetyZone(**rec))
        db.commit()
        print(f"Ingested {len(records)} dongs (previous rows replaced).")
    finally:
        db.close()


if __name__ == "__main__":
    # --refresh(=--pois-only): 보안등 API 재수집 없이 경찰서·상점·범죄율만 기존 DB에 다시 채운다.
    # --dump-points: DB는 건드리지 않고 CCTV·보안등 좌표만 JSON으로 저장한다.
    if "--refresh" in sys.argv or "--pois-only" in sys.argv:
        refresh_derived_factors()
    elif "--dump-points" in sys.argv:
        dump_facility_points()
    elif "--dump-accidents" in sys.argv:
        dump_accident_points()
    else:
        ingest()
