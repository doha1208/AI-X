"""남한 전체 OSM PBF에서 서울 권역 보행자 도로망만 추출해 osmnx가 읽을 수
있는 .osm(XML) 파일로 저장한다.

한 번만 실행하면 되고, 이후 백엔드는 이 로컬 파일만 사용해 외부 네트워크
호출(Overpass API) 없이 안전 경로를 계산한다.

사전 준비: https://download.geofabrik.de/asia/south-korea-latest.osm.pbf 를
backend/data/osm/south-korea-latest.osm.pbf 로 받아둔다.

사용법:
    backend/.venv/Scripts/python.exe scripts/extract_seoul_walk_network.py
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import osmium

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data" / "osm"
SOURCE_PBF = DATA_DIR / "south-korea-latest.osm.pbf"
OUTPUT_XML = DATA_DIR / "seoul-walk.osm"

# 서울 대략적 경계 + 여유 (west, south, east, north). 안전구역 데이터가
# 다른 도시로 늘어나면 이 값을 넓혀서 다시 실행하면 된다.
BBOX = (126.76, 37.42, 127.18, 37.70)

# osmnx의 network_type="walk" 필터(app/services/safe_route.py가 기대하는 것과
# 동일한 도로망이 나오도록)를 그대로 재현한 것. osmnx/_overpass.py 참고.
EXCLUDED_HIGHWAY_SUBSTRINGS = (
    "abandoned", "bus_guideway", "construction", "cycleway", "motor", "no",
    "planned", "platform", "proposed", "raceway", "razed", "rest_area", "services",
)
SEPARATE_SIDEWALK_KEYS = ("sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right")


def _is_walkable(tags: dict) -> bool:
    highway = tags.get("highway")
    if not highway:
        return False
    if tags.get("area") == "yes":
        return False
    if tags.get("access") == "private":
        return False
    if any(x in highway for x in EXCLUDED_HIGHWAY_SUBSTRINGS):
        return False
    if tags.get("foot") == "no":
        return False
    if tags.get("service") == "private":
        return False
    return not any(tags.get(k) == "separate" for k in SEPARATE_SIDEWALK_KEYS)


def _in_bbox(lon: float, lat: float) -> bool:
    west, south, east, north = BBOX
    return west <= lon <= east and south <= lat <= north


class _WalkWayCollector(osmium.SimpleHandler):
    """NodeLocationsForWays와 함께 apply하면 way의 각 노드에 위치 정보가 채워진다."""

    def __init__(self) -> None:
        super().__init__()
        self.ways: list[tuple[int, dict, list[tuple[int, float, float]]]] = []

    def way(self, w: osmium.osm.Way) -> None:
        tags = dict(w.tags)
        if not _is_walkable(tags):
            return

        coords: list[tuple[int, float, float]] = []
        for n in w.nodes:
            try:
                loc = n.location
                if not loc.valid():
                    return
                coords.append((n.ref, loc.lon, loc.lat))
            except osmium.InvalidLocationError:
                return

        if any(_in_bbox(lon, lat) for _, lon, lat in coords):
            self.ways.append((w.id, tags, coords))


def main() -> None:
    if not SOURCE_PBF.exists():
        raise SystemExit(f"소스 PBF가 없어요: {SOURCE_PBF}")

    # 파일 기반 인덱스(sparse_file_array)는 비ASCII 경로(한글 폴더명)에서
    # libosmium이 파일을 못 여는 문제가 있어 메모리 기반 인덱스를 사용한다.
    idx = osmium.index.create_map("sparse_mem_array")
    loc_handler = osmium.NodeLocationsForWays(idx)
    loc_handler.ignore_errors()

    collector = _WalkWayCollector()
    print("PBF에서 서울 권역 보행자 도로망 추출 중... (수 분 소요될 수 있어요)")
    # libosmium이 한글이 섞인 긴 절대경로에서 파일을 못 여는 문제가 있어
    # (버퍼/인코딩 이슈로 추정) 현재 작업 디렉터리 기준 상대경로로 넘긴다.
    relative_source = os.path.relpath(SOURCE_PBF, start=os.getcwd())
    osmium.apply(relative_source, loc_handler, collector)

    print(f"추출된 way 수: {len(collector.ways)}")
    if not collector.ways:
        raise SystemExit("추출된 way가 없어요 — BBOX나 필터를 확인해주세요.")

    seen_nodes: dict[int, tuple[float, float]] = {}
    for _, _, coords in collector.ways:
        for nid, lon, lat in coords:
            seen_nodes.setdefault(nid, (lon, lat))

    root = ET.Element("osm", version="0.6", generator="extract_seoul_walk_network.py")
    for nid, (lon, lat) in seen_nodes.items():
        ET.SubElement(root, "node", id=str(nid), lat=f"{lat:.7f}", lon=f"{lon:.7f}")
    for wid, tags, coords in collector.ways:
        way_el = ET.SubElement(root, "way", id=str(wid))
        for nid, _, _ in coords:
            ET.SubElement(way_el, "nd", ref=str(nid))
        for k, v in tags.items():
            ET.SubElement(way_el, "tag", k=k, v=v)

    ET.ElementTree(root).write(OUTPUT_XML, encoding="utf-8", xml_declaration=True)
    print(f"완료: {OUTPUT_XML} (노드 {len(seen_nodes)}개, way {len(collector.ways)}개)")


if __name__ == "__main__":
    main()
