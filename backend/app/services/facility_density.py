"""도로 구간(edge) 주변의 시설로 구간별 안전 점수(0~100)를 계산한다.

동 단위 점수는 같은 동 안의 모든 길이 같은 값이고, OSM 가로등(lit) 태그는 서울+경기 도로의
1%도 안 돼서, 좌표가 있는 공공데이터를 구간 단위로 직접 센다.

- CCTV·보안등: scripts/ingest_public_data.py --dump-points
- 상점: scripts/extract_safety_pois.py (OSM) — 거리에 사람 눈이 있는지
- 교통사고 다발지역: ingest_public_data.py --refresh가 저장 — 근처 구간은 감점
- 공원·숲·하천변·공터: scripts/extract_isolated_areas.py (OSM) — 밤에 그 안의 구간은 감점

비상벨·경찰서는 구간 단위로 나눠도 경로가 거의 달라지지 않아(서울·경기 경로의 84%가 이미
비상벨 200m 안) 동 점수에 남긴다. 상점·사고다발지역은 여기서 세므로 경로용 동 점수에서는
뺀다(scoring_profile.route_zone_profile) — 같은 데이터가 두 번 반영되지 않게.

ponytail: 반경·포화 개수·비중은 실험(수원·안산·신림 90쌍) 기반 첫 값 — 실제 귀갓길 피드백으로 조정 필요.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from scipy.spatial import cKDTree

from app.services.poi_factors import Point, to_meters
from app.services.safety_score import Period

logger = logging.getLogger(__name__)

OSM_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "osm"
FACILITY_POINTS_PATH = OSM_DIR / "facility_points.json"
POIS_PATH = OSM_DIR / "safety_pois.json"
ACCIDENT_POINTS_PATH = OSM_DIR / "accident_points.json"
ISOLATED_AREAS_PATH = OSM_DIR / "isolated_areas.json"
ISOLATED_AREA_KINDS = ("park", "forest", "water", "vacant")

CCTV_RADIUS_M = 60.0
LIGHT_RADIUS_M = 40.0
STORE_RADIUS_M = 50.0
ACCIDENT_RADIUS_M = 100.0
# 반경 안에 이 개수 이상이면 만점이다 — 더 많다고 계속 안전해지지는 않는다.
CCTV_SATURATION = 1
LIGHT_SATURATION = 2
STORE_SATURATION = 3

# (cctv 비중, 보안등 비중) — 낮엔 방범 CCTV, 밤엔 즉시 시야를 확보해주는 보안등.
_WEIGHTS: dict[Period, tuple[float, float]] = {"day": (0.7, 0.3), "night": (0.4, 0.6)}
# 구간 점수 안에서 (CCTV·보안등, 상점, 사고다발, 인적 드문 영역) 비중. 밤엔 문 닫은 가게가 많아
# 상점 비중을 낮추고, 낮엔 공원·하천변이 위험하지 않아 그 비중을 0으로 둔다.
_PART_WEIGHTS: dict[Period, tuple[float, float, float, float]] = {
    "day": (0.55, 0.25, 0.20, 0.0),
    "night": (0.50, 0.10, 0.15, 0.25),
}


@dataclass(frozen=True)
class FacilityIndex:
    cctv_tree: cKDTree | None
    light_tree: cKDTree | None
    store_tree: cKDTree | None = None
    accident_tree: cKDTree | None = None
    isolated_tree: shapely.STRtree | None = None


def _tree(points: list[Point]) -> cKDTree | None:
    return cKDTree(to_meters(points)) if len(points) else None


def build_facility_index(
    cctv: list[Point],
    lights: list[Point],
    stores: list[Point] = (),
    accidents: list[Point] = (),
    isolated_areas: list[shapely.Geometry] = (),
) -> FacilityIndex:
    return FacilityIndex(
        cctv_tree=_tree(cctv),
        light_tree=_tree(lights),
        store_tree=_tree(stores),
        accident_tree=_tree(accidents),
        isolated_tree=shapely.STRtree(isolated_areas) if len(isolated_areas) else None,
    )


def _optional_points(path: Path, key: str | None = None) -> list[Point]:
    """상점·사고다발 좌표는 없어도 된다 — 없으면 그 부분만 빼고 CCTV·보안등으로 계산한다."""
    if not path.exists():
        logger.warning("Point file missing, its per-road factor disabled: %s", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data[key] if key else data
    except (OSError, ValueError, KeyError):
        logger.warning("Point file unreadable, its per-road factor disabled: %s", path, exc_info=True)
        return []


def _optional_areas(path: Path) -> list[shapely.Geometry]:
    """공원·하천 영역 파일도 없어도 된다 — 없으면 그 감점만 빠진다."""
    if not path.exists():
        logger.warning("Isolated areas file missing, its per-road factor disabled: %s", path)
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        wkts = [wkt for kind in ISOLATED_AREA_KINDS for wkt in data.get(kind, [])]
        # 한 번에 배열로 넘기면 numpy가 가장 긴 문자열 길이로 고정폭 배열을 잡아 수십 GB가 된다.
        return [shapely.from_wkt(wkt) for wkt in wkts]
    except (OSError, ValueError, shapely.errors.GEOSException):
        logger.warning("Isolated areas unreadable, its per-road factor disabled: %s", path, exc_info=True)
        return []


def load_facility_index(
    path: Path = FACILITY_POINTS_PATH,
    pois_path: Path = POIS_PATH,
    accident_path: Path = ACCIDENT_POINTS_PATH,
    isolated_path: Path = ISOLATED_AREAS_PATH,
) -> FacilityIndex | None:
    """CCTV·보안등 좌표 파일이 없으면 None — 호출부가 구간별 밀도 없이(동 점수만으로) 계산하게 한다."""
    if not path.exists():
        logger.warning("Facility points file missing, per-road density disabled: %s", path)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # lights_geocoded: 좌표 없이 주소만 올린 지자체의 보안등을 주소→좌표 변환으로 복구한 것.
        cctv, lights = data["cctv"], data["lights"] + data.get("lights_geocoded", [])
    except (OSError, ValueError, KeyError):
        logger.warning("Facility points unreadable, per-road density disabled: %s", path, exc_info=True)
        return None
    return build_facility_index(
        cctv,
        lights,
        _optional_points(pois_path, "stores"),
        _optional_points(accident_path),
        _optional_areas(isolated_path),
    )


def _saturating_score(tree: cKDTree | None, meters: np.ndarray, radius_m: float, saturation: int) -> np.ndarray:
    if tree is None:
        return np.zeros(len(meters))
    counts = tree.query_ball_point(meters, r=radius_m, return_length=True)
    return np.minimum(counts / saturation, 1.0) * 100.0


def _inside_any(tree: shapely.STRtree, midpoints) -> np.ndarray:
    coords = np.asarray(midpoints, dtype=float).reshape(-1, 2)
    points = shapely.points(coords[:, 1], coords[:, 0])  # (lat, lng) → x=lng, y=lat
    inside = np.zeros(len(points), dtype=bool)
    inside[tree.query(points, predicate="within")[0]] = True
    return inside


# 보안등 데이터를 못 받은 지역의 구간은 "0개=깜깜함"이 아니라 중간 점수로 본다.
UNKNOWN_LIGHT_SCORE = 50.0


def edge_local_scores(index: FacilityIndex, midpoints, period: Period, lights_known=None) -> list[float]:
    """각 (lat, lng) 구간 중간점 주변 시설로 0~100 점수를 준다.

    CCTV·보안등 개수, 반경 50m 상점 수, 100m 안 교통사고 다발지점(있으면 그 부분 0점),
    공원·숲·하천변·공터 안인지(밤에만, 안이면 그 부분 0점)를 섞는다.
    상점·사고다발·영역 데이터가 없으면 그 비중은 빼고 나머지로 다시 나눈다.
    lights_known(구간마다 bool)이 False인 구간은 보안등 부분을 UNKNOWN_LIGHT_SCORE로 대신한다.
    """
    meters = to_meters(midpoints)
    cctv = _saturating_score(index.cctv_tree, meters, CCTV_RADIUS_M, CCTV_SATURATION)
    light = _saturating_score(index.light_tree, meters, LIGHT_RADIUS_M, LIGHT_SATURATION)
    if lights_known is not None:
        light = np.where(lights_known, light, UNKNOWN_LIGHT_SCORE)
    w_cctv, w_light = _WEIGHTS[period]
    parts = [(_PART_WEIGHTS[period][0], cctv * w_cctv + light * w_light)]
    if index.store_tree is not None:
        parts.append((_PART_WEIGHTS[period][1], _saturating_score(index.store_tree, meters, STORE_RADIUS_M, STORE_SATURATION)))
    if index.accident_tree is not None:
        near = index.accident_tree.query_ball_point(meters, r=ACCIDENT_RADIUS_M, return_length=True) > 0
        parts.append((_PART_WEIGHTS[period][2], np.where(near, 0.0, 100.0)))
    if index.isolated_tree is not None and _PART_WEIGHTS[period][3] > 0:
        parts.append((_PART_WEIGHTS[period][3], np.where(_inside_any(index.isolated_tree, midpoints), 0.0, 100.0)))
    total = sum(w for w, _ in parts)
    return (sum(w * score for w, score in parts) / total).tolist()
