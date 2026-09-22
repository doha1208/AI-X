"""도로 구간(edge) 주변의 CCTV·보안등 개수로 구간별 안전 점수(0~100)를 계산한다.

동 단위 점수는 같은 동 안의 모든 길이 같은 값이고, OSM 가로등(lit) 태그는 서울+경기 도로의
1%도 안 돼서, 좌표가 있는 공공데이터(scripts/ingest_public_data.py --dump-points)를 구간
단위로 직접 센다.

ponytail: 반경·포화 개수·주야 비중은 체감 기반 MVP 값 — 실제 귀갓길 피드백으로 조정 필요.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from app.services.poi_factors import Point, to_meters
from app.services.safety_score import Period

logger = logging.getLogger(__name__)

FACILITY_POINTS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "osm" / "facility_points.json"

CCTV_RADIUS_M = 60.0
LIGHT_RADIUS_M = 40.0
# 반경 안에 이 개수 이상이면 만점 — 더 많다고 계속 안전해지지는 않는다.
CCTV_SATURATION = 1
LIGHT_SATURATION = 2

# (cctv 비중, 보안등 비중) — 낮엔 방범 CCTV, 밤엔 즉시 시야를 확보해주는 보안등.
_WEIGHTS: dict[Period, tuple[float, float]] = {"day": (0.7, 0.3), "night": (0.4, 0.6)}


@dataclass(frozen=True)
class FacilityIndex:
    cctv_tree: cKDTree | None
    light_tree: cKDTree | None


def _tree(points: list[Point]) -> cKDTree | None:
    return cKDTree(to_meters(points)) if len(points) else None


def build_facility_index(cctv: list[Point], lights: list[Point]) -> FacilityIndex:
    return FacilityIndex(cctv_tree=_tree(cctv), light_tree=_tree(lights))


def load_facility_index(path: Path = FACILITY_POINTS_PATH) -> FacilityIndex | None:
    """좌표 파일이 없으면 None — 호출부가 구간별 밀도 없이(동 점수만으로) 계산하게 한다."""
    if not path.exists():
        logger.warning("Facility points file missing, per-road density disabled: %s", path)
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # lights_geocoded: 좌표 없이 주소만 올린 지자체의 보안등을 주소→좌표 변환으로 복구한 것.
        return build_facility_index(data["cctv"], data["lights"] + data.get("lights_geocoded", []))
    except (OSError, ValueError, KeyError):
        logger.warning("Facility points unreadable, per-road density disabled: %s", path, exc_info=True)
        return None


def _saturating_score(tree: cKDTree | None, meters: np.ndarray, radius_m: float, saturation: int) -> np.ndarray:
    if tree is None:
        return np.zeros(len(meters))
    counts = tree.query_ball_point(meters, r=radius_m, return_length=True)
    return np.minimum(counts / saturation, 1.0) * 100.0


# 보안등 데이터를 못 받은 지역의 구간은 "0개=깜깜함"이 아니라 중간 점수로 본다.
UNKNOWN_LIGHT_SCORE = 50.0


def edge_local_scores(index: FacilityIndex, midpoints, period: Period, lights_known=None) -> list[float]:
    """각 (lat, lng) 구간 중간점 주변의 CCTV·보안등 개수로 0~100 점수를 준다.

    lights_known(구간마다 bool)이 False인 구간은 보안등 부분을 UNKNOWN_LIGHT_SCORE로 대신한다.
    """
    meters = to_meters(midpoints)
    cctv = _saturating_score(index.cctv_tree, meters, CCTV_RADIUS_M, CCTV_SATURATION)
    light = _saturating_score(index.light_tree, meters, LIGHT_RADIUS_M, LIGHT_SATURATION)
    if lights_known is not None:
        light = np.where(lights_known, light, UNKNOWN_LIGHT_SCORE)
    w_cctv, w_light = _WEIGHTS[period]
    return (cctv * w_cctv + light * w_light).tolist()
