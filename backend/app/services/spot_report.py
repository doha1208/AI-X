"""Versioned nearby help locations, separate from facility score calculation."""
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
