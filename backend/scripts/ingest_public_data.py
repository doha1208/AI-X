"""공공데이터(CCTV·보안등·구 단위 범죄통계)를 동 단위 안전 지수로 변환해 DB에 적재.

데이터 출처:
- CCTV: data.go.kr 전국CCTV표준데이터 (프로젝트 루트 CCTV정보.csv, "생활방범" 목적만 사용)
- 보안등: data.go.kr 전국보안등정보표준데이터 OpenAPI (SECURITY_LIGHT_API_KEY)
- 범죄: data.go.kr 경찰청_범죄 발생 지역별 통계 (구 단위 5대 범죄 합계, 프로젝트 루트 CSV)
- 좌표→행정동 변환: build_dong_grid.py로 미리 만든 격자 캐시(app/data/dong_grid.json)

ponytail: 범죄 통계는 구 단위가 공개 최소 단위라 같은 구의 모든 동이 범죄
건수를 공유한다. CCTV/보안등은 격자 스냅으로 동 단위 밀도를 구해 차등을 준다.
매 실행마다 safety_zones 테이블을 통째로 다시 계산해 덮어쓴다(증분 아님).

사용법:
    backend/.venv/Scripts/python.exe scripts/ingest_public_data.py
"""
import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from app.db.session import Base, SessionLocal, engine
from app.models.safety_zone import SafetyZone
from app.services.safety_score import compute_safety_scores

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
PROJECT_ROOT = BACKEND_DIR.parent

CCTV_CSV = PROJECT_ROOT / "CCTV정보.csv"
CRIME_CSV = PROJECT_ROOT / "경찰청_범죄 발생 지역별 통계_20241231.csv"
GRID_PATH = BACKEND_DIR / "app" / "data" / "dong_grid.json"
ENV_PATH = BACKEND_DIR / ".env"

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


def resolve_crime_by_gu(crime_by_region: dict[str, int], gu_names: set[str]) -> dict[str, int]:
    """격자의 gu_name -> 범죄 건수.

    경찰청 통계는 시 단위("수원시")인데 카카오는 구 단위("수원시 장안구")를 준다.
    정확히 일치하면 그 값을, 아니면 시 합계를 하위 구 개수로 균등 배분한다(서울 구
    단위 수치와 스케일을 맞추려는 근사 — 구별 인구 차이는 반영하지 못한다).
    통계에 없는 지역은 결과에서 뺀다 — 0으로 채우면 "가장 안전"으로 오인된다.
    """
    districts_per_city = Counter(name.split()[0] for name in gu_names if " " in name)
    result: dict[str, int] = {}
    for name in gu_names:
        if name in crime_by_region:
            result[name] = crime_by_region[name]
            continue
        city = name.split()[0]
        if city in crime_by_region and districts_per_city[city]:
            result[name] = crime_by_region[city] // districts_per_city[city]
    return result


def count_cctv_by_dong(step: float, cells: dict, bbox) -> dict:
    counts: dict[str, int] = {}
    with CCTV_CSV.open(encoding="cp949", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
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
            cell = snap_to_dong(lat, lng, step, cells, bbox)
            if cell:
                counts[cell["dong_code"]] = counts.get(cell["dong_code"], 0) + 1
    return counts


MAX_ATTEMPTS = 3
RETRY_BACKOFF_SEC = 2.0


def fetch_json_with_retry(url: str) -> dict:
    """전국 보안등은 ~1,860페이지라 한 번의 일시 오류(타임아웃/5xx)로 처음부터 다시
    돌리지 않도록 페이지 단위로 재시도한다. 마지막 시도까지 실패하면 그대로 올린다."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise AssertionError("unreachable")


def fetch_security_lights(step: float, cells: dict, bbox) -> dict:
    """보안등 표준데이터 API는 instt_code 없이도 전국 데이터를 페이지네이션으로
    받을 수 있다(실측 확인, totalCount~186만 건). 기관코드를 미리 조사해둘
    필요 없이 snap_to_dong의 bbox 체크가 서울+경기 밖 지점은 자동으로 걸러준다.

    ponytail: 전국 페이지를 순서대로 다 훑는 단순한 방식 — 기관코드/지역별로
    쪼개 병렬 호출하면 더 빠르겠지만, 이 스크립트는 가끔 한 번 돌리는 배치라
    단순함이 낫다.
    """
    key = load_env_value("SECURITY_LIGHT_API_KEY")
    counts: dict[str, int] = {}
    page = 1
    while True:
        params = {
            "serviceKey": key,
            "pageNo": str(page),
            "numOfRows": "1000",
            "type": "json",
        }
        url = "https://api.data.go.kr/openapi/tn_pubr_public_scrty_lmp_api?" + urllib.parse.urlencode(params)
        body = fetch_json_with_retry(url)
        payload = body.get("body") or {}
        items = (payload.get("items") or {}).get("item")
        if not items:
            break
        if isinstance(items, dict):
            items = [items]
        for item in items:
            try:
                lat = float(item["latitude"])
                lng = float(item["longitude"])
            except (KeyError, ValueError, TypeError):
                continue
            cell = snap_to_dong(lat, lng, step, cells, bbox)
            if cell:
                counts[cell["dong_code"]] = counts.get(cell["dong_code"], 0) + 1
        total_count = payload.get("totalCount", 0)
        if page * 1000 >= total_count:
            break
        page += 1
        time.sleep(0.1)
    return counts


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
    step, cells, bbox = load_grid()

    print("Loading crime stats by gu...")
    crime_by_gu = load_crime_by_gu()

    print("Counting CCTV by dong (scanning ~79MB CSV, may take a minute)...")
    cctv_by_dong = count_cctv_by_dong(step, cells, bbox)
    print(f"  {sum(cctv_by_dong.values())} CCTV assigned across {len(cctv_by_dong)} dongs")

    print("Fetching security lights by dong (paginated API calls)...")
    light_by_dong = fetch_security_lights(step, cells, bbox)
    print(f"  {sum(light_by_dong.values())} lights assigned across {len(light_by_dong)} dongs")

    dong_meta = build_dong_meta(cells)

    crime_by_gu = resolve_crime_by_gu(crime_by_gu, {m["gu_name"] for m in dong_meta.values()})
    unmatched = {m["gu_name"] for m in dong_meta.values()} - crime_by_gu.keys()
    if unmatched:
        print(f"주의: 범죄 통계와 매칭되지 않은 지역 {len(unmatched)}곳은 crime_count=0으로 들어가요: {sorted(unmatched)}")

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
                "crime_count": crime_by_gu.get(meta["gu_name"], 0),
            }
        )

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
    ingest()
