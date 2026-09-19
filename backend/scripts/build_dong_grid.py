"""서울+경기도 전역에 0.005도 격자를 깔고 Kakao coord2regioncode로 각 격자점의
행정동을 한 번씩만 조회해 캐싱한다. 수 시간 걸리는 배치라 진행상황을
dong_grid.partial.json에 주기적으로 저장하고, 끊기면 같은 명령으로 이어서 실행된다.

CCTV/보안등처럼 포인트가 수십만 개인 데이터를 동 단위로 집계할 때, 포인트마다
역지오코딩하면 API 호출이 너무 많아진다. 대신 격자점만 미리 역지오코딩해두고
각 포인트는 가장 가까운 격자점의 동으로 스냅시킨다.

ponytail: 0.005도(~500m) 격자 스냅 방식 - 동 경계 근처 포인트는 오분류될 수
있음. 더 정확하게 하려면 실제 행정동 경계 폴리곤(shapefile)으로 point-in-
polygon 계산해야 함.

사용법:
    backend/.venv/Scripts/python.exe scripts/build_dong_grid.py
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE.parent / ".env"
OUT_PATH = HERE.parent / "app" / "data" / "dong_grid.json"

BBOX = (126.30, 36.85, 127.90, 38.30)  # west, south, east, north — 서울+경기도 전역(근사치)
# extract_seoul_walk_network.py의 BBOX, safe_route.LOCAL_WALK_NETWORK_BBOX와 같아야 한다
# (tests/test_walk_network_bbox.py가 어긋나면 잡는다).
STEP = 0.005

REQUEST_DELAY_SEC = 0.15

# 수 시간짜리 배치라 중간에 끊겨도(절전/재부팅/네트워크/Kakao 일일 쿼터) 처음부터
# 다시 하지 않도록 주기적으로 진행상황을 저장한다. 최종 파일과 같은 폴더에 둔다.
CHECKPOINT_PATH = OUT_PATH.with_suffix(".partial.json")
CHECKPOINT_EVERY = 500
WORKERS = 4
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SEC = 2.0


class QuotaExceeded(Exception):
    """Kakao API가 HTTP 429(일일 쿼터/호출 제한)를 반환했다 — 재시도해도 소용없다."""


def load_kakao_key() -> str:
    env_text = ENV_PATH.read_text(encoding="utf-8")
    match = re.search(r"KAKAO_REST_API_KEY=(.*)", env_text)
    if not match or not match.group(1).strip():
        raise RuntimeError("KAKAO_REST_API_KEY not set in backend/.env")
    return match.group(1).strip()


def reverse_geocode(key: str, lng: float, lat: float) -> dict | None:
    url = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json?" + urllib.parse.urlencode(
        {"x": lng, "y": lat}
    )
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {key}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read())
    for doc in body.get("documents", []):
        if doc.get("region_type") == "H" and doc.get("region_1depth_name") in ("서울특별시", "경기도"):
            return {
                "dong_code": doc["code"],
                "dong_name": doc["region_3depth_name"],
                "gu_name": doc["region_2depth_name"],
                "lat": doc["y"],
                "lng": doc["x"],
            }
    return None


def reverse_geocode_with_retry(key: str, lng: float, lat: float) -> dict | None:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return reverse_geocode(key, lng, lat)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise QuotaExceeded() from e
            if attempt == MAX_ATTEMPTS:
                raise
        except Exception:
            if attempt == MAX_ATTEMPTS:
                raise
        time.sleep(RETRY_BACKOFF_SEC * attempt)
    return None


def geocode_point(key: str, lat: float, lng: float) -> tuple[dict | None, bool]:
    """(결과, 실패여부). 쿼터 초과(QuotaExceeded)만 그대로 올려보내 배치를 멈춘다."""
    try:
        return reverse_geocode_with_retry(key, lng, lat), False
    except QuotaExceeded:
        raise
    except Exception as e:
        print(f"ERR at {lat},{lng} (재시도 후에도 실패): {e}")
        return None, True
    finally:
        time.sleep(REQUEST_DELAY_SEC)


def load_checkpoint() -> tuple[dict, int, int]:
    """(cells, next_index, hits). 체크포인트가 없거나 step/bbox가 다르면 처음부터."""
    if not CHECKPOINT_PATH.exists():
        return {}, 0, 0
    data = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    if data.get("step") != STEP or tuple(data.get("bbox", ())) != BBOX:
        print("체크포인트의 step/bbox가 현재 설정과 달라 무시하고 처음부터 시작합니다.")
        return {}, 0, 0
    return data["cells"], data["next_index"], data["hits"]


def save_checkpoint(cells: dict, next_index: int, hits: int) -> None:
    # 저장 도중 프로세스가 죽어도 이전 체크포인트가 깨지지 않게 임시 파일에 쓴 뒤 교체한다.
    tmp = CHECKPOINT_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {"step": STEP, "bbox": list(BBOX), "next_index": next_index, "hits": hits, "cells": cells},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    tmp.replace(CHECKPOINT_PATH)


def main():
    key = load_kakao_key()
    west, south, east, north = BBOX

    lats = []
    v = south
    while v <= north:
        lats.append(round(v, 5))
        v += STEP
    lngs = []
    v = west
    while v <= east:
        lngs.append(round(v, 5))
        v += STEP

    points = [(lat, lng) for lat in lats for lng in lngs]
    total = len(points)
    print(f"grid size: {len(lats)} x {len(lngs)} = {total} points")

    grid, start_index, hits = load_checkpoint()
    if start_index:
        print(f"resuming from checkpoint: {start_index}/{total} already done, {hits} hits")

    failed = 0
    # 체크포인트 단위(CHECKPOINT_EVERY)로 묶어 WORKERS개 스레드가 병렬 조회한다.
    # 순차로 돌리면 왕복 지연 때문에 9만 점에 약 8시간이 걸린다(실측 ~3.3점/초).
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for chunk_start in range(start_index, total, CHECKPOINT_EVERY):
            chunk = points[chunk_start : chunk_start + CHECKPOINT_EVERY]
            try:
                results = list(pool.map(lambda p: geocode_point(key, p[0], p[1]), chunk))
            except QuotaExceeded:
                save_checkpoint(grid, chunk_start, hits)
                print(f"Kakao 쿼터/호출 제한(429) — {chunk_start}/{total}까지 저장했어요. 같은 명령으로 이어서 실행하세요.")
                return
            for (lat, lng), (result, was_failure) in zip(chunk, results):
                failed += was_failure
                if result:
                    grid[f"{lat}:{lng}"] = result
                    hits += 1
            done = chunk_start + len(chunk)
            save_checkpoint(grid, done, hits)
            print(f"{done}/{total} done, {hits} hits, {failed} failed")

    if failed:
        print(f"주의: {failed}개 격자점이 재시도 후에도 실패해 빈 칸으로 남았어요(이웃 칸 스냅으로 대부분 보완됨).")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {"step": STEP, "bbox": list(BBOX), "cells": grid},
            ensure_ascii=False,
            indent=None,
        ),
        encoding="utf-8",
    )
    CHECKPOINT_PATH.unlink(missing_ok=True)
    print(f"Saved {hits} grid cells (of {total} queried) to {OUT_PATH}")


if __name__ == "__main__":
    main()
