"""소상공인시장진흥공단 상가(상권)정보에서 경기도의 길가 상점·편의점 좌표를 뽑아 JSON으로 저장한다.

ingest_public_data.py(동별 상점 수)와 facility_density.py(도로 구간 주변 상점, 밤 편의점)가 읽는다.
OSM 상점은 사람이 지도에 직접 입력한 것이라 빠진 곳이 많아, 영업 중 상가 전수 데이터로 바꾼다.

데이터 출처: 공공데이터포털 '소상공인시장진흥공단_상가(상권)정보'(분기 갱신, 전국 zip).
받은 zip을 backend/data/raw/csv_files/에 그대로 둔다 — 여러 개면 파일 이름순으로 마지막(최신) 것을 쓴다.

사용법 (backend 폴더에서):
    python scripts/extract_store_points.py

ponytail: '거리의 사람 눈'으로 볼 상점은 음식·소매만, 그리고 2층 이상으로 확인된 곳은 뺀다
(층 정보가 빈 곳은 길가로 본다). 사무실·학원·부동산은 밤에 길을 지켜보지 않는다.
"""

import csv
from datetime import UTC, datetime
import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
# 내려받은 공공데이터 원본. backend/data/ 전체가 Git 제외 대상이며 외부로 유출하면 안 된다.
RAW_DATA_DIR = BACKEND_DIR / "data" / "raw" / "csv_files"
ZIP_GLOB = "소상공인시장진흥공단_상가(상권)정보_*.zip"
OUTPUT_JSON = BACKEND_DIR / "data" / "osm" / "store_points.json"
SIDOS = ("경기",)
STREET_CATEGORIES = {"음식", "소매"}
GROUND_FLOORS = {"", "1", "지", "B1"}  # 층 정보가 없거나 1층·지하1층


def _point(row: dict) -> list[float] | None:
    try:
        lat, lng = float(row["위도"]), float(row["경도"])
        if not math.isfinite(lat) or not math.isfinite(lng) or not -90 <= lat <= 90 or not -180 <= lng <= 180:
            return None
        return [round(lat, 6), round(lng, 6)]
    except (KeyError, ValueError):
        return None


def extract(rows) -> dict:
    stores, convenience, places = [], [], []
    for row in rows:
        if row["층정보"].strip() not in GROUND_FLOORS:
            continue
        point = _point(row)
        if point is None:
            continue
        if row["상권업종대분류명"] in STREET_CATEGORIES:
            stores.append(point)
        if row["상권업종소분류명"] == "편의점":
            convenience.append(point)
        if row["상권업종대분류명"] in STREET_CATEGORIES or row["상권업종소분류명"] == "편의점":
            places.append({"source_id": row.get("상가업소번호"), "name": row.get("상호명"),
                           "road_address": row.get("도로명주소"), "lot_address": row.get("지번주소"),
                           "category": row.get("상권업종소분류명"), "point": point,
                           "floor": row["층정보"].strip(), "street_level_confirmed": bool(row["층정보"].strip()),
                           "hours_status": "unknown", "opening_hours": None, "staffed": None})
    return {"stores": stores, "convenience": convenience, "places": places}


def main() -> None:
    zips = sorted(RAW_DATA_DIR.glob(ZIP_GLOB))
    if not zips:
        raise SystemExit(f"{RAW_DATA_DIR}에 {ZIP_GLOB} 파일이 없어요")
    source = zips[-1]
    points = {"stores": [], "convenience": [], "places": []}
    with zipfile.ZipFile(source, metadata_encoding="cp949") as archive:
        names = [item.filename for item in archive.infolist()]
        for sido in SIDOS:
            name = next((name for name in names if f"_{sido}_" in name), None)
            if name is None:
                raise SystemExit(f"{source.name}에 {sido} 상가정보가 없어요")
            with archive.open(name) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                region_points = extract(csv.DictReader(text))
            for kind in points:
                points[kind].extend(region_points[kind])
    with source.open("rb") as stream:
        source_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    payload = {"source": source.name, "source_evidence": {
        "source_url": "https://www.data.go.kr/data/15012005/openapi.do", "original_filename": source.name,
        "original_sha256": source_sha, "processed_at": datetime.now(UTC).isoformat(),
        "scope": list(SIDOS), "opening_hours_included": False}, **points}
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"완료: 길가 상점 {len(points['stores'])}곳, 편의점 {len(points['convenience'])}곳 -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
