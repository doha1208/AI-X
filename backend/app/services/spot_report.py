"""Versioned nearby help locations, separate from facility score calculation."""
from app.services.facility_density import FacilityIndex, edge_local_scores
from app.services.safety_score import Period
from app.services.poi_factors import Point

import hashlib
import json
import logging
from datetime import datetime
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from app.services.facility_density import OSM_DIR
from app.services.poi_factors import to_meters
from app.services.route_environment_sources import EnvironmentIndex

logger = logging.getLogger(__name__)

POLICE_POINTS_PATH = OSM_DIR / "police_points.json"
REPORT_RADIUS_M = 300.0
GRID_STEP_M = 50.0
# 이보다 먼 거점은 "가까이 없음"으로 본다 — 걸어서 도움을 청하러 갈 거리가 아니다.
HAVEN_MAX_M = 1500.0

@lru_cache(maxsize=2)
def _police_index(raw: bytes):
    # Equal size and mtime do not imply equal contents on a batch overwrite.
    payload = json.loads(raw)
    points = np.asarray(payload["police"], dtype=float).reshape(-1, 2)
    points = points[np.all(np.isfinite(points) & (np.abs(points) <= (90, 180)), axis=1)]
    label = payload.get("source") or "별도 경찰 시설 좌표 자료"
    url = "https://www.safetydata.go.kr/" if label == "행정안전부_공통POI_경찰" else None
    return points, cKDTree(to_meters(points)), str(label), url, hashlib.sha256(raw).hexdigest()


def load_haven_index():
    """Police is a separately versioned coordinate list, outside the facility score."""
    try:
        return _police_index(POLICE_POINTS_PATH.read_bytes())
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        logger.warning("Police coordinate list could not be loaded", exc_info=True)
        return None


def nearest_havens(indexes: EnvironmentIndex | None, lat: float, lng: float, *, at: datetime,
                   max_m: float = HAVEN_MAX_M) -> list[dict]:
    """One location per kind. Snapshot trees already carry the facility data version."""
    here = to_meters([(lat, lng)])[0]
    found = {}

    def add(kind, tree, points, source_id, label, url, version, *, priority=0,
            schedule="not_applicable", opening="not_applicable"):
        distance, i = tree.query(here)
        order = (float(distance), priority, source_id)
        if distance > max_m or (kind in found and found[kind][0] <= order):
            return
        p_lat, p_lng = points[i]
        found[kind] = (order, {"kind": kind, "lat": float(p_lat), "lng": float(p_lng),
            "distance_m": round(float(distance)), "source_id": source_id, "source_label": label,
            "source_url": url, "source_version": version, "schedule_status": schedule, "opening_status": opening,
            "staffing_status": "not_applicable" if kind == "bell" else "unverified",
            "operation_status": "unverified" if kind == "bell" else "not_applicable"})

    if police := load_haven_index():
        points, tree, label, url, version = police
        add("police", tree, points, "local-police", label, url, version)
    for entry in indexes.sources if indexes is not None else ():
        source = entry.source
        if entry.tree is None:
            continue
        if source.factor == "bell":
            add("bell", entry.tree, source.points, source.source_id,
                "검증된 비상벨 목록" if source.presence_eligible() else "비상벨 위치 자료",
                source.source_url or None, source.sha256, priority=int(not source.presence_eligible()))
        elif source.factor == "open_store" and source.source_id == "published-hours-emart24":
            # The legacy store index mixes businesses and convenience stores; only
            # the explicitly identified convenience-store feed can supply this kind.
            weekly = source.presence_eligible() and bool(source.opening_hours)
            opening = ("scheduled_open" if source.is_open(at) else "scheduled_closed") if weekly else "unverified"
            schedule = "verified_weekly_schedule" if weekly else "published_schedule" if source.schedule_status == "published_schedule" else "unverified"
            add("convenience", entry.tree, source.points, source.source_id, "이마트24 매장 찾기",
                source.source_url or None, source.sha256, schedule=schedule, opening=opening)
    return [record for _, record in sorted(found.values(), key=lambda entry: entry[0])]


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
