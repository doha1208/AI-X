"""한 지점 주변의 안전 요약 — 집 주소 안전 리포트와 실시간 안내의 '안심 거점' 안내가 함께 쓴다.

- 주변 점수: 반경 안을 격자로 찍어 구간 점수(edge_local_scores)를 평균한다 — 귀갓길 경로가 쓰는 것과 같은 계산.
- 지금 이 자리 점수: 그 지점 하나의 구간 점수.
- 안심 거점: 가장 가까운 경찰서·지구대·파출소, 24시 편의점, 안전비상벨.
- 시설 수: 반경 안 CCTV·보안등·편의점 개수.

ponytail: 격자 50m 간격의 평균 — 도로가 없는 땅(논밭·건물 안)도 같이 센다. 실제 도로만 보려면
보행 그래프 간선 중간점으로 바꾸면 되지만, 그래프를 메모리에 올리는 비용이 커서 첫 버전은 격자로 둔다.
"""
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
from scipy.spatial import cKDTree

from app.services.bells import load_bell_points
from app.services.facility_density import OSM_DIR, STORE_POINTS_PATH, FacilityIndex, edge_local_scores
from app.services.poi_factors import Point, to_meters
from app.services.safety_score import Period

logger = logging.getLogger(__name__)

POLICE_POINTS_PATH = OSM_DIR / "police_points.json"
REPORT_RADIUS_M = 300.0
GRID_STEP_M = 50.0
# 이보다 먼 거점은 "가까이 없음"으로 본다 — 걸어서 도움을 청하러 갈 거리가 아니다.
HAVEN_MAX_M = 1500.0

HavenKind = Literal["police", "convenience", "bell"]


@dataclass(frozen=True)
class HavenIndex:
    """거점 종류별 좌표와 KD-tree. 좌표를 돌려줘야 해서 FacilityIndex와 따로 둔다."""

    points: dict[HavenKind, np.ndarray]
    trees: dict[HavenKind, cKDTree]


def build_haven_index(police: list[Point], convenience: list[Point], bells: list[Point]) -> HavenIndex:
    raw: dict[HavenKind, list[Point]] = {"police": police, "convenience": convenience, "bell": bells}
    points = {kind: np.asarray(pts, dtype=float).reshape(-1, 2) for kind, pts in raw.items() if len(pts)}
    return HavenIndex(points=points, trees={kind: cKDTree(to_meters(pts)) for kind, pts in points.items()})


def _points_from(path: Path, key: str) -> list[Point]:
    if not path.exists():
        logger.warning("Haven points file missing, that haven kind is skipped: %s", path)
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))[key]
    except (OSError, ValueError, KeyError):
        logger.warning("Haven points unreadable, that haven kind is skipped: %s", path, exc_info=True)
        return []


@lru_cache(maxsize=1)
def load_haven_index() -> HavenIndex:
    return build_haven_index(
        _points_from(POLICE_POINTS_PATH, "police"),
        _points_from(STORE_POINTS_PATH, "convenience"),
        list(load_bell_points()),
    )


def nearest_havens(index: HavenIndex, lat: float, lng: float, max_m: float = HAVEN_MAX_M) -> list[dict]:
    """종류마다 가장 가까운 거점 하나씩, 가까운 순으로. max_m보다 먼 종류는 뺀다."""
    here = to_meters([(lat, lng)])[0]
    found = []
    for kind, tree in index.trees.items():
        dist, i = tree.query(here)
        if dist <= max_m:
            p_lat, p_lng = index.points[kind][i]
            found.append({"kind": kind, "lat": float(p_lat), "lng": float(p_lng), "distance_m": round(float(dist))})
    return sorted(found, key=lambda h: h["distance_m"])


def grid_around(lat: float, lng: float, radius_m: float = REPORT_RADIUS_M, step_m: float = GRID_STEP_M) -> list[Point]:
    """중심에서 radius_m 안의 격자점(위경도). 중심점도 항상 들어간다."""
    m_per_deg_lat = 111_320.0
    m_per_deg_lng = m_per_deg_lat * np.cos(np.radians(lat))
    steps = np.arange(-radius_m, radius_m + 1e-9, step_m)
    dy, dx = np.meshgrid(steps, steps)
    inside = dx**2 + dy**2 <= radius_m**2
    return list(zip((lat + dy[inside] / m_per_deg_lat).tolist(), (lng + dx[inside] / m_per_deg_lng).tolist()))


def area_scores(
    facilities: FacilityIndex, lat: float, lng: float, lights_known: bool, cctv_known: bool,
    radius_m: float = REPORT_RADIUS_M,
) -> dict[Period, float]:
    """반경 안 격자점 구간 점수의 평균(낮·밤)."""
    grid = grid_around(lat, lng, radius_m)
    flags = ([lights_known] * len(grid), [cctv_known] * len(grid))
    return {
        period: round(float(np.mean(edge_local_scores(facilities, grid, period, *flags))), 1)
        for period in ("day", "night")
    }


def point_score(facilities: FacilityIndex, lat: float, lng: float, period: Period, lights_known: bool, cctv_known: bool) -> float:
    return round(edge_local_scores(facilities, [(lat, lng)], period, [lights_known], [cctv_known])[0], 1)


def _count(tree: cKDTree | None, here: np.ndarray, radius_m: float) -> int | None:
    return None if tree is None else int(tree.query_ball_point(here, r=radius_m, return_length=True))


def facility_counts(
    facilities: FacilityIndex, lat: float, lng: float, lights_known: bool, cctv_known: bool,
    radius_m: float = REPORT_RADIUS_M,
) -> dict[str, int | None]:
    """반경 안 시설 수. 그 지역이 데이터를 안 올렸으면(…_known=False) 0개가 아니라 None(모름)."""
    here = to_meters([(lat, lng)])[0]
    return {
        "cctv": _count(facilities.cctv_tree, here, radius_m) if cctv_known else None,
        "lights": _count(facilities.light_tree, here, radius_m) if lights_known else None,
        "convenience": _count(facilities.convenience_tree, here, radius_m),
    }
