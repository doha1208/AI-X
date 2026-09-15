"""서울 전역에 0.005도 격자를 깔고 Kakao coord2regioncode로 각 격자점의
행정동을 한 번씩만 조회해 캐싱한다.

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
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE.parent / ".env"
OUT_PATH = HERE.parent / "app" / "data" / "dong_grid.json"

BBOX = (126.76, 37.42, 127.18, 37.70)  # west, south, east, north (extract_seoul_walk_network.py와 동일)
STEP = 0.005

REQUEST_DELAY_SEC = 0.15


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
        if doc.get("region_type") == "H" and doc.get("region_1depth_name") == "서울특별시":
            return {
                "dong_code": doc["code"],
                "dong_name": doc["region_3depth_name"],
                "gu_name": doc["region_2depth_name"],
                "lat": doc["y"],
                "lng": doc["x"],
            }
    return None


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

    total = len(lats) * len(lngs)
    print(f"grid size: {len(lats)} x {len(lngs)} = {total} points")

    grid = {}
    done = 0
    hits = 0
    for lat in lats:
        for lng in lngs:
            done += 1
            try:
                result = reverse_geocode(key, lng, lat)
            except Exception as e:
                print(f"ERR at {lat},{lng}: {e}")
                result = None
            if result:
                grid[f"{lat}:{lng}"] = result
                hits += 1
            if done % 200 == 0:
                print(f"{done}/{total} done, {hits} hits")
            time.sleep(REQUEST_DELAY_SEC)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {"step": STEP, "bbox": list(BBOX), "cells": grid},
            ensure_ascii=False,
            indent=None,
        ),
        encoding="utf-8",
    )
    print(f"Saved {hits} grid cells (of {total} queried) to {OUT_PATH}")


if __name__ == "__main__":
    main()
