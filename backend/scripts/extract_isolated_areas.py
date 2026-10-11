"""남한 전체 OSM PBF에서 밤에 인적이 드문 영역(공원·숲·하천변·공터)의 폴리곤을 뽑아 JSON으로 저장한다.

facility_density.py가 이 파일을 읽어, 밤에 도로 구간 중간점이 이 영역 안이면 구간 점수를 깎는다.
한 번만 실행하면 된다(PBF가 바뀌면 다시). 실행 후 build_route_artifacts.py로 경로 데이터를 다시 만든다.

사전 준비: extract_safety_pois.py와 같은 backend/data/osm/south-korea-latest.osm.pbf.

사용법 (backend 폴더에서):
    python scripts/extract_isolated_areas.py

ponytail: 하천은 물 폴리곤을 약 20m 넓혀 둔치·하천변 산책로를 잡는다(위경도 도 단위 근사 버퍼).
공원 안의 밝은 광장·한강공원 조명은 구분하지 않는다 — 공원 안이면 똑같이 본다.
"""

import json
import os
from pathlib import Path

import osmium
import shapely

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data" / "osm"
SOURCE_PBF = DATA_DIR / "south-korea-latest.osm.pbf"
OUTPUT_JSON = DATA_DIR / "isolated_areas.json"

# extract_seoul_walk_network.py의 BBOX와 같은 서울+경기 범위.
BBOX = (126.30, 36.85, 127.90, 38.30)
SIMPLIFY_DEG = 0.00005  # 약 5m — 파일 크기를 줄이되 길 하나 폭보다 작게
WATER_BUFFER_DEG = 0.0002  # 약 20m — 하천 가장자리 산책로까지


def _kind(tags) -> str | None:
    if tags.get("leisure") in ("park", "nature_reserve"):
        return "park"
    if tags.get("landuse") == "forest" or tags.get("natural") == "wood":
        return "forest"
    if tags.get("natural") == "water" or tags.get("waterway") == "riverbank" or tags.get("landuse") == "reservoir":
        return "water"
    if tags.get("landuse") in ("brownfield", "greenfield"):
        return "vacant"
    return None


class _AreaCollector(osmium.SimpleHandler):
    def __init__(self) -> None:
        super().__init__()
        self.wkb = osmium.geom.WKBFactory()
        self.bbox = shapely.box(*BBOX)
        self.areas: dict[str, list[str]] = {"park": [], "forest": [], "water": [], "vacant": []}

    def area(self, a: osmium.osm.Area) -> None:
        kind = _kind(a.tags)
        if not kind:
            return
        try:
            geom = shapely.from_wkb(self.wkb.create_multipolygon(a))
        except (RuntimeError, shapely.errors.GEOSException):
            return  # 닫히지 않은 멀티폴리곤 등 깨진 데이터
        if not geom.intersects(self.bbox):
            return
        geom = geom.simplify(SIMPLIFY_DEG)
        if kind == "water":
            geom = geom.buffer(WATER_BUFFER_DEG)
        if not geom.is_empty:
            self.areas[kind].append(shapely.to_wkt(geom, rounding_precision=6))


def main() -> None:
    if not SOURCE_PBF.exists():
        raise SystemExit(f"소스 PBF가 없어요: {SOURCE_PBF}")

    collector = _AreaCollector()
    print("PBF에서 공원·숲·하천·공터 영역 추출 중... (수 분 소요될 수 있어요)")
    # 한글 경로 문제 회피: extract_safety_pois.py처럼 상대경로로 연다.
    collector.apply_file(os.path.relpath(SOURCE_PBF, start=os.getcwd()), locations=True, idx="sparse_mem_array")

    payload = {"bbox": list(BBOX), **collector.areas}
    OUTPUT_JSON.write_text(json.dumps(payload), encoding="utf-8")
    counts = ", ".join(f"{k} {len(v)}" for k, v in collector.areas.items())
    print(f"완료: {counts} -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
