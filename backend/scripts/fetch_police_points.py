"""행정안전부 공통POI(경찰)에서 전국 경찰서·지구대·파출소 좌표를 받아 JSON으로 저장한다.

ingest_public_data.py가 동별 '가장 가까운 경찰서까지 거리'를 잴 때 OSM 경찰 시설 대신 이 파일을 쓴다.
경기도 밖도 남긴다 — 서울·인천과 맞닿은 동은 가장 가까운 지구대가 시 경계 너머일 수 있다.

데이터 출처: 재난안전데이터 공유플랫폼(safetydata.go.kr) '행정안전부_공통POI_경찰' 오픈API
(DSSP-IF-00080, 활용신청 필요 — .env의 SAFETYDATA_API_KEY). 좌표는 EPSG:3857.

사용법 (backend 폴더에서):
    python scripts/fetch_police_points.py

ponytail: 밤에도 사람이 있는 경찰서·지구대·파출소만 센다. 치안센터는 야간 무인인 곳이 많고,
스마트 안심부스·지방청은 도움을 청하러 가는 곳이 아니라 뺀다.
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Transformer

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
OUTPUT_JSON = BACKEND_DIR / "data" / "osm" / "police_points.json"
API_URL = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00080"
PAGE_SIZE = 100
STAFFED_TYPES = {"경찰서", "지구대", "파출소"}

_TO_WGS84 = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)


def _api_key() -> str:
    for line in (BACKEND_DIR / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("SAFETYDATA_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("SAFETYDATA_API_KEY가 .env에 없어요")


def staffed_points(rows: list[dict]) -> list[list[float]]:
    points = []
    for row in rows:
        if (row.get("FCLT_TYPE") or "").strip() not in STAFFED_TYPES:
            continue
        try:
            lng, lat = _TO_WGS84.transform(float(row["XMAP_CRTS"]), float(row["YMAP_CRTS"]))
        except (KeyError, TypeError, ValueError):
            continue
        points.append([round(lat, 6), round(lng, 6)])
    return points


def fetch_all(key: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        query = urllib.parse.urlencode({"serviceKey": key, "pageNo": page, "numOfRows": PAGE_SIZE, "returnType": "json"})
        with urllib.request.urlopen(f"{API_URL}?{query}", timeout=60) as resp:
            body = json.load(resp).get("body") or []
        if not body:
            return rows
        rows += body
        page += 1


def main() -> None:
    rows = fetch_all(_api_key())
    points = staffed_points(rows)
    OUTPUT_JSON.write_text(json.dumps({"source": "행정안전부_공통POI_경찰", "police": points}), encoding="utf-8")
    print(f"완료: 전국 {len(rows)}곳 중 경찰서·지구대·파출소 {len(points)}곳 -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
