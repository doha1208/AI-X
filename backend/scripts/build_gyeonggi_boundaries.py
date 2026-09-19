"""경기도 행정동 경계 폴리곤(GeoJSON)을 만들어 프론트 정적 파일로 저장한다.

전국 행정동 경계(약 35MB)를 받아서 dong_grid.json에 실제로 쓰인 경기도 동만 남기고,
지도에 그리기에 충분한 수준으로 경계선을 단순화해 용량을 줄인다.
서울은 frontend/public/data/seoul-dong-boundaries.geojson이 이미 있다.

데이터 출처(표기 의무): 통계청 SGIS 행정동 경계(공공누리 제1유형)를
vuski/admdongkor가 가공, CC BY 4.0 — 출력 파일의 "attribution" 필드에 그대로 남긴다.

사용법:
    python scripts/build_gyeonggi_boundaries.py
"""
import json
import urllib.request
from pathlib import Path

import shapely
from shapely.geometry import mapping, shape

SOURCE_URL = (
    "https://raw.githubusercontent.com/vuski/admdongkor/master/"
    "ver20260701/HangJeongDong_ver20260701.geojson"
)
ATTRIBUTION = (
    "본 데이터는 통계청 통계지리정보서비스(SGIS, https://sgis.kostat.go.kr)에서 공공누리 제1유형으로 "
    "개방한 행정동 경계를 가공한 것이며(가공: vuski/admdongkor, https://github.com/vuski/admdongkor), "
    "CC BY 4.0으로 배포됩니다."
)

HERE = Path(__file__).resolve().parent
GRID_PATH = HERE.parent / "app" / "data" / "dong_grid.json"
OUT_PATH = HERE.parent.parent / "frontend" / "public" / "data" / "gyeonggi-dong-boundaries.geojson"

GYEONGGI_SIDO_CODE = "41"
# 위경도 0.0002도 ≈ 20m. 동 단위 폴리곤을 화면에 그리는 데는 눈에 띄는 차이가 없다.
SIMPLIFY_TOLERANCE_DEG = 0.0002
COORD_DECIMALS = 5  # ≈ 1m


def gyeonggi_dong_codes() -> set[str]:
    cells = json.loads(GRID_PATH.read_text(encoding="utf-8"))["cells"]
    return {c["dong_code"] for c in cells.values() if c["dong_code"].startswith(GYEONGGI_SIDO_CODE)}


def simplify_geometry(geometry: dict) -> dict:
    simplified = shape(geometry).simplify(SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
    return mapping(shapely.set_precision(simplified, 10**-COORD_DECIMALS))


def build_features(source: dict, wanted_codes: set[str]) -> list[dict]:
    features = []
    for feature in source["features"]:
        props = feature["properties"]
        if props["adm_cd2"] not in wanted_codes:
            continue
        features.append(
            {
                "type": "Feature",
                "properties": {"adm_cd2": props["adm_cd2"], "adm_nm": props["adm_nm"], "sggnm": props["sggnm"]},
                "geometry": simplify_geometry(feature["geometry"]),
            }
        )
    return features


def main() -> None:
    wanted = gyeonggi_dong_codes()
    print(f"downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as resp:
        source = json.loads(resp.read())

    features = build_features(source, wanted)
    found = {f["properties"]["adm_cd2"] for f in features}
    if found != wanted:
        raise SystemExit(f"경계가 없는 동 {len(wanted - found)}개: {sorted(wanted - found)[:10]}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {"type": "FeatureCollection", "attribution": ATTRIBUTION, "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(features)} features to {OUT_PATH} ({OUT_PATH.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
