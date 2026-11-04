"""로컬 OSM PBF에서 경기도 역 이름과 좌표를 주소 후보용 정적 파일로 추출한다.

사용법 (backend 폴더에서): python -m scripts.build_station_suggestions
원본: backend/data/osm/south-korea-latest.osm.pbf (OpenStreetMap, ODbL)
"""

import json
import os
from pathlib import Path
from typing import Callable

import osmium

from app.services.service_area import is_in_service_area


HERE = Path(__file__).resolve().parent
SOURCE_PBF = HERE.parent / "data" / "osm" / "south-korea-latest.osm.pbf"
OUTPUT_JSON = HERE.parent.parent / "frontend" / "public" / "data" / "gyeonggi-stations.json"


class _StationCollector(osmium.SimpleHandler):
    def __init__(self, in_scope: Callable[[float, float], bool]) -> None:
        super().__init__()
        self.in_scope = in_scope
        self.stations: list[dict] = []
        self.seen: set[tuple[str, float, float]] = set()

    def node(self, node: osmium.osm.Node) -> None:
        if node.tags.get("railway") not in ("station", "halt") or not node.location.valid():
            return
        name = (node.tags.get("name:ko") or node.tags.get("name") or "").strip()
        if not name or not any("가" <= char <= "힣" for char in name):
            return
        lat, lng = node.location.lat, node.location.lon
        if not self.in_scope(lat, lng):
            return
        key = (name, round(lat, 3), round(lng, 3))
        if key in self.seen:
            return
        self.seen.add(key)
        self.stations.append({"name": name, "lat": round(lat, 6), "lng": round(lng, 6)})


def collect_stations(source: Path, *, in_scope: Callable[[float, float], bool] | None = None) -> list[dict]:
    scope = in_scope or (lambda lat, lng: is_in_service_area(lat, lng, region_scope_prefix="41"))
    collector = _StationCollector(scope)
    osmium.apply(os.path.relpath(source, start=os.getcwd()), collector)
    return sorted(collector.stations, key=lambda station: (station["name"], station["lat"], station["lng"]))


def main() -> None:
    if not SOURCE_PBF.exists():
        raise SystemExit(f"OSM 원본이 없습니다: {SOURCE_PBF}")
    stations = collect_stations(SOURCE_PBF)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps({"source": "OpenStreetMap contributors (ODbL)", "stations": stations}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"경기도 역 {len(stations)}개 -> {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
