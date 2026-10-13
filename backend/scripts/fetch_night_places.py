"""행정안전부 지방행정 인허가 API에서 서울·경기의 영업 중인 편의점·유흥업소 좌표를 받아 JSON으로 저장한다.

facility_density.py가 이 파일을 읽는다 — 밤에 편의점(24시간, 여성안심지킴이집 대부분)은
가점, 유흥주점·단란주점 근처 구간은 감점.

데이터 출처 (공공데이터포털, 행정안전부, 일간 갱신. 활용신청 필요 — 키는 SECURITY_LIGHT_API_KEY와 같은 계정 키):
- 행정안전부_식품_휴게음식점 조회서비스 (위생업태명이 "편의점"인 곳만)
- 행정안전부_식품_유흥주점영업 조회서비스
- 행정안전부_식품_단란주점영업 조회서비스

사용법 (backend 폴더에서):
    python scripts/fetch_night_places.py

ponytail: API의 주소 LIKE 조건이 서버 오류(HTTP_ERROR)를 내서, 영업 중인 전국 업소를 다 받은 뒤
주소로 서울·경기만 거른다(휴게음식점 약 2,000번 호출 — 개발계정 하루 한도 10,000건 안).
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pyproj import Transformer

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
OUTPUT_JSON = BACKEND_DIR / "data" / "osm" / "night_places.json"
API_ROOT = "https://apis.data.go.kr/1741000"
PAGE_SIZE = 100  # API 최대값
WORKERS = 8
SERVICE_AREAS = ("서울특별시", "경기도")

# 인허가 좌표계: 보정계수 없는 Bessel 중부원점TM(EPSG:5174) → WGS84
_TO_WGS84 = Transformer.from_crs("EPSG:5174", "EPSG:4326", always_xy=True)


def _api_key() -> str:
    key = os.environ.get("SECURITY_LIGHT_API_KEY", "")
    env = BACKEND_DIR / ".env"
    if not key and env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("SECURITY_LIGHT_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("SECURITY_LIGHT_API_KEY가 없어요 (.env)")
    return urllib.parse.unquote(key)  # 인코딩된 키를 붙여넣었어도 한 번만 인코딩되게


def _fetch_page(service: str, page: int, key: str, attempts: int = 5) -> dict:
    query = urllib.parse.urlencode(
        {
            "serviceKey": key,
            "pageNo": page,
            "numOfRows": PAGE_SIZE,
            "returnType": "json",
            "cond[SALS_STTS_CD::EQ]": "01",  # 영업/정상
        }
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(f"{API_ROOT}/{service}/info?{query}", timeout=60) as resp:
                return json.load(resp)["response"]["body"]
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError):
            if attempt == attempts - 1:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def _items(body: dict) -> list[dict]:
    items = (body.get("items") or {}).get("item") or []
    return items if isinstance(items, list) else [items]


def _to_point(item: dict) -> list[float] | None:
    try:
        lng, lat = _TO_WGS84.transform(float(item["CRD_INFO_X"]), float(item["CRD_INFO_Y"]))
    except (KeyError, TypeError, ValueError):
        return None  # 좌표 없는 업소
    return [round(lat, 6), round(lng, 6)]


def fetch_service(service: str, key: str, keep=lambda item: True) -> list[list[float]]:
    first = _fetch_page(service, 1, key)
    pages = -(-int(first["totalCount"]) // PAGE_SIZE)
    print(f"  {service}: 영업 중 {first['totalCount']}곳, {pages}페이지")
    with ThreadPoolExecutor(WORKERS) as pool:
        bodies = [first, *pool.map(lambda p: _fetch_page(service, p, key), range(2, pages + 1))]
    points = []
    for item in (i for body in bodies for i in _items(body)):
        address = item.get("ROAD_NM_ADDR") or item.get("LOTNO_ADDR") or ""
        if address.startswith(SERVICE_AREAS) and keep(item):
            point = _to_point(item)
            if point:
                points.append(point)
    return points


def _is_convenience(item: dict) -> bool:
    return (item.get("SNTTN_BZSTAT_NM") or "").strip() == "편의점"


def main() -> None:
    key = _api_key()
    print("인허가 API에서 서울·경기 편의점·유흥업소 받는 중... (수 분 소요)")
    convenience = fetch_service("rest_cafes", key, keep=_is_convenience)
    nightlife = fetch_service("entertainment_bars", key) + fetch_service("singing_bars", key)
    payload = {
        "source": "행정안전부 지방행정 인허가(영업 중)",
        "fetched": time.strftime("%Y-%m-%d"),
        "convenience": convenience,
        "nightlife": nightlife,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"완료: 편의점 {len(convenience)}곳, 유흥·단란주점 {len(nightlife)}곳 -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
