"""지도에 표시할 안전비상벨 좌표. scripts/ingest_public_data.py --refresh(또는 ingest)가
만들어둔 data/osm/bell_points.json을 읽어, 반경 검색으로 필터링해 내려준다.

ponytail: nearby_zones(app/api/safety.py)와 같은 방식(리스트 전체를 haversine으로 훑기) —
5.8만 개 정도는 매 요청 훑어도 수십 ms면 끝나 KD-tree 같은 색인이 아직 필요 없다.
"""
import json
from pathlib import Path

from app.services.geo import haversine_km

BELL_POINTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "osm" / "bell_points.json"

# 도심은 비상벨이 촘촘해서(격자로 묶어도 크게 안 줄어듦 — 실제로 그만큼 많이 설치돼 있음)
# 반경만으로 거르면 지도가 마커로 뒤덮여 경로선이 안 보인다. 가까운 것부터 이 개수까지만 보여준다.
DEFAULT_BELL_LIMIT = 60

Point = tuple[float, float]

_cached_points: list[Point] | None = None


def load_bell_points(path: Path = BELL_POINTS_PATH) -> list[Point]:
    """좌표 파일이 없으면 빈 목록 — 지도에 마커가 안 보일 뿐 나머지 기능은 그대로 동작한다."""
    global _cached_points
    if _cached_points is None:
        if not path.exists():
            _cached_points = []
        else:
            _cached_points = [tuple(p) for p in json.loads(path.read_text(encoding="utf-8"))]
    return _cached_points


def nearby_bells(
    lat: float, lng: float, radius_km: float, points: list[Point] | None = None, limit: int = DEFAULT_BELL_LIMIT
) -> list[dict]:
    """중심점 반경 안의 비상벨 좌표를, 가까운 순으로 최대 limit개까지 {lat, lng} 목록으로 돌려준다."""
    candidates = load_bell_points() if points is None else points
    with_dist = ((haversine_km(lat, lng, p_lat, p_lng), p_lat, p_lng) for p_lat, p_lng in candidates)
    within_radius = sorted((item for item in with_dist if item[0] <= radius_km), key=lambda item: item[0])
    return [{"lat": p_lat, "lng": p_lng} for _, p_lat, p_lng in within_radius[:limit]]
