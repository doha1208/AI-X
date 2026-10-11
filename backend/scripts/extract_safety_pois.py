"""남한 전체 OSM PBF에서 안전 요소 POI(경찰서·파출소, 상점)의 좌표만 뽑아 JSON으로 저장한다.

ingest_public_data.py가 이 파일을 읽어 동별 "가까운 경찰서까지 거리"와 "상점 수"를 계산한다.
한 번만 실행하면 된다(PBF가 바뀌면 다시).

사전 준비: extract_seoul_walk_network.py와 같은 backend/data/osm/south-korea-latest.osm.pbf.

사용법 (backend 폴더에서):
    python scripts/extract_safety_pois.py

ponytail: 태그가 붙은 노드와 폐곡선(건물) way의 중심점만 본다 — 관계(relation)로 그려진
큰 건물은 빠진다. 상점은 shop=* 전체(vacant 제외)를 똑같이 1개로 센다.
"""

import json
import os
from pathlib import Path

import osmium

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE.parent / "data" / "osm"
SOURCE_PBF = DATA_DIR / "south-korea-latest.osm.pbf"
OUTPUT_JSON = DATA_DIR / "safety_pois.json"

# extract_seoul_walk_network.py의 BBOX와 같은 서울+경기 범위.
BBOX = (126.30, 36.85, 127.90, 38.30)


def _in_bbox(lat: float, lng: float) -> bool:
    west, south, east, north = BBOX
    return west <= lng <= east and south <= lat <= north


def _kind(tags) -> str | None:
    if tags.get("amenity") == "police":
        return "police"
    shop = tags.get("shop")
    if shop and shop != "vacant":
        return "store"
    return None


class _PoiCollector(osmium.SimpleHandler):
    """NodeLocationsForWays와 함께 apply하면 way의 각 노드에 위치 정보가 채워진다."""

    def __init__(self) -> None:
        super().__init__()
        self.points: dict[str, list[list[float]]] = {"police": [], "store": []}

    def _add(self, kind: str, lat: float, lng: float) -> None:
        if _in_bbox(lat, lng):
            self.points[kind].append([round(lat, 6), round(lng, 6)])

    def node(self, n: osmium.osm.Node) -> None:
        if not len(n.tags):
            return
        kind = _kind(n.tags)
        if kind and n.location.valid():
            self._add(kind, n.location.lat, n.location.lon)

    def way(self, w: osmium.osm.Way) -> None:
        if not len(w.tags):
            return
        kind = _kind(w.tags)
        if not kind:
            return
        coords: list[tuple[float, float]] = []
        for n in w.nodes:
            try:
                if n.location.valid():
                    coords.append((n.location.lat, n.location.lon))
            except osmium.InvalidLocationError:
                return
        if coords:
            self._add(kind, sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords))


def main() -> None:
    if not SOURCE_PBF.exists():
        raise SystemExit(f"소스 PBF가 없어요: {SOURCE_PBF}")

    # 한글 경로 문제 회피 방식은 extract_seoul_walk_network.py와 동일(메모리 인덱스 + 상대경로).
    idx = osmium.index.create_map("sparse_mem_array")
    loc_handler = osmium.NodeLocationsForWays(idx)
    loc_handler.ignore_errors()

    collector = _PoiCollector()
    print("PBF에서 경찰서·상점 좌표 추출 중... (수 분 소요될 수 있어요)")
    osmium.apply(os.path.relpath(SOURCE_PBF, start=os.getcwd()), loc_handler, collector)

    payload = {"bbox": list(BBOX), "police": collector.points["police"], "stores": collector.points["store"]}
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"완료: 경찰서/파출소 {len(payload['police'])}곳, 상점 {len(payload['stores'])}곳 -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
