"""좌표 없이 주소만 있는 보안등(light_addresses.json)을 카카오 주소검색으로 좌표로 바꿔
facility_points.json의 lights_geocoded에 채운다.

결과는 geocode_cache.json에 저장돼서 중간에 끊겨도(카카오 일일 쿼터 429, 절전, 네트워크)
같은 명령으로 이어서 실행하면 된다. 이미 변환한 주소는 다시 호출하지 않는다.

사전 준비: ingest_public_data.py --dump-points (light_addresses.json을 만든다).

사용법 (backend 폴더에서):
    python scripts/geocode_light_addresses.py

ponytail: 변환 결과가 서울+경기 범위 밖이면 오변환으로 보고 버린다. 지번/도로명이 모호한
주소는 카카오의 첫 결과를 그대로 쓴다.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.services.address_geocode import Point, parse_address_response, query_candidates

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
DATA_DIR = BACKEND_DIR / "data" / "osm"
ADDRESSES_PATH = DATA_DIR / "light_addresses.json"
CACHE_PATH = DATA_DIR / "geocode_cache.json"
FACILITY_POINTS_PATH = DATA_DIR / "facility_points.json"
ENV_PATH = BACKEND_DIR / ".env"

WORKERS = 4
REQUEST_DELAY_SEC = 0.15  # build_dong_grid.py와 같은 호출 간격(워커마다)
CHUNK_SIZE = 400  # 이만큼 처리할 때마다 캐시를 저장한다
RETRIES = 3
RATE_LIMIT_WAIT_SEC = 5


class QuotaExceeded(Exception):
    """카카오가 HTTP 429(일일 쿼터/호출 제한)를 계속 반환한다 — 더 시도해도 소용없다."""


def load_kakao_key() -> str:
    match = re.search(r"KAKAO_REST_API_KEY=(.*)", ENV_PATH.read_text(encoding="utf-8"))
    if not match or not match.group(1).strip():
        raise RuntimeError("KAKAO_REST_API_KEY not set in backend/.env")
    return match.group(1).strip()


def search_address(key: str, query: str) -> Point | None:
    url = "https://dapi.kakao.com/v2/local/search/address.json?" + urllib.parse.urlencode({"query": query})
    request = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
    for attempt in range(1, RETRIES + 2):
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                return parse_address_response(json.loads(resp.read()))
        except urllib.error.HTTPError as error:
            if error.code == 429:
                if attempt > RETRIES:
                    raise QuotaExceeded() from error
                time.sleep(RATE_LIMIT_WAIT_SEC * attempt)
            elif error.code == 400:
                return None  # 질의로 쓸 수 없는 주소 문자열
            else:
                raise  # 401/403 등 인증 문제는 조용히 넘기지 않는다
        except (urllib.error.URLError, TimeoutError):
            if attempt > RETRIES:
                raise
            time.sleep(2 * attempt)
    return None


def geocode_entry(key: str, entry: dict) -> Point | None:
    for query in query_candidates(entry["jibun"], entry["road"]):
        point = search_address(key, query)
        time.sleep(REQUEST_DELAY_SEC)
        if point:
            return point
    return None


def cache_key(entry: dict) -> str:
    return f"{entry['jibun']}|{entry['road']}"


def write_json(path: Path, payload) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def apply_to_facility_points(addresses: list[dict], cache: dict) -> tuple[int, int]:
    """캐시의 변환 결과를 facility_points.json의 lights_geocoded에 채운다. (채운 행 수, 범위 밖으로 버린 행 수)"""
    points = json.loads(FACILITY_POINTS_PATH.read_text(encoding="utf-8"))
    west, south, east, north = points["bbox"]
    geocoded: list[list[float]] = []
    outside = 0
    for entry in addresses:
        coord = cache.get(cache_key(entry))
        if not coord:
            continue
        lat, lng = coord
        if west <= lng <= east and south <= lat <= north:
            geocoded.extend([[round(lat, 6), round(lng, 6)]] * entry["n"])
        else:
            outside += entry["n"]
    points["lights_geocoded"] = geocoded
    write_json(FACILITY_POINTS_PATH, points)
    return len(geocoded), outside


def main() -> None:
    if not ADDRESSES_PATH.exists():
        raise SystemExit(f"{ADDRESSES_PATH} 없음 — 먼저 ingest_public_data.py --dump-points를 실행하세요.")
    addresses = json.loads(ADDRESSES_PATH.read_text(encoding="utf-8"))
    cache: dict = json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    pending = [e for e in addresses if cache_key(e) not in cache]
    print(f"주소 {len(addresses)}개 중 변환 대기 {len(pending)}개 (캐시 {len(addresses) - len(pending)}개)")

    key = load_kakao_key()
    stopped = False
    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for start in range(0, len(pending), CHUNK_SIZE):
            chunk = pending[start : start + CHUNK_SIZE]
            futures = {pool.submit(geocode_entry, key, entry): entry for entry in chunk}
            for future in as_completed(futures):
                try:
                    point = future.result()
                except QuotaExceeded:
                    stopped = True
                    continue
                cache[cache_key(futures[future])] = list(point) if point else None
                done += 1
            write_json(CACHE_PATH, cache)
            print(f"  {done}/{len(pending)} 변환 (성공 {sum(1 for v in cache.values() if v)}개)", flush=True)
            if stopped:
                break

    filled, outside = apply_to_facility_points(addresses, cache)
    resolved = sum(1 for e in addresses if cache.get(cache_key(e)))
    print(f"좌표를 얻은 주소 {resolved}/{len(addresses)}개 -> lights_geocoded {filled}개 반영 (범위 밖 {outside}개 버림)")
    if stopped:
        print("Kakao 쿼터/호출 제한(429) — 진행분을 저장했어요. 같은 명령으로 이어서 실행하세요.")


if __name__ == "__main__":
    main()
