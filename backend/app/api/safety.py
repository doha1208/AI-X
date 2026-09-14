import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.safety_zone import SafetyZone
from app.schemas.safety import (
    RouteAlternative,
    RouteMode,
    RouteRequest,
    RoutePoint,
    RouteResponse,
    SafetyZoneOut,
)
from app.services.geo import haversine_km
from app.services.safe_route import find_safe_routes
from app.services.tmap import get_pedestrian_route

router = APIRouter(prefix="/safety", tags=["safety"])

Point = tuple[float, float]


def _path_distance_m(points: list[Point]) -> float:
    return sum(
        haversine_km(a[0], a[1], b[0], b[1]) * 1000 for a, b in zip(points[:-1], points[1:])
    )


def _point_sample_score(points: list[Point], zones: list[SafetyZone]) -> float:
    scores = [
        min(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng)).safety_score
        for lat, lng in points
    ]
    return sum(scores) / len(scores) if scores else 0.0


def _zones_passed(points: list[Point], zones: list[SafetyZone]) -> list[SafetyZone]:
    passed: list[SafetyZone] = []
    seen_codes: set[str] = set()
    for lat, lng in points:
        nearest = min(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng))
        if nearest.dong_code not in seen_codes:
            seen_codes.add(nearest.dong_code)
            passed.append(nearest)
    return passed


@router.get("/zones", response_model=list[SafetyZoneOut])
def nearby_zones(
    lat: float,
    lng: float,
    radius_km: float = Query(2.0, gt=0),
    db: Session = Depends(get_db),
):
    zones = db.query(SafetyZone).all()
    return [z for z in zones if haversine_km(lat, lng, z.lat, z.lng) <= radius_km]


@router.get("/residence-recommend", response_model=list[SafetyZoneOut])
def residence_recommend(limit: int = Query(5, gt=0, le=50), db: Session = Depends(get_db)):
    return (
        db.query(SafetyZone)
        .order_by(SafetyZone.safety_score.desc())
        .limit(limit)
        .all()
    )


@router.post("/route", response_model=RouteResponse)
async def route_safety(payload: RouteRequest, db: Session = Depends(get_db)):
    """출발지→도착지 경로를 3단계 우선순위로 계산한다.

    1) safety_weighted: OSM 도로망 그래프 위에서 안전점수를 비용으로 반영해
       실제로 더 안전한 길을 고르는 자체 경로 탐색. 대안 경로 여러 개를
       안전점수 순으로 함께 반환한다.
    2) tmap: 위 그래프 탐색이 실패(지역 미지원/네트워크 오류)하면 Tmap
       보행자 최단경로를 받아 그 위에 안전점수만 표시(대안 없음).
    3) straight_line: 그마저 실패하면 직선 5구간 샘플링으로 대략 추정(대안 없음).
    """
    zones = db.query(SafetyZone).all()

    safe_routes = await asyncio.to_thread(
        find_safe_routes,
        payload.start_lat,
        payload.start_lng,
        payload.end_lat,
        payload.end_lng,
        zones,
    )

    candidates: list[dict]
    if safe_routes:
        mode: RouteMode = "safety_weighted"
        candidates = safe_routes
    else:
        tmap_points = await get_pedestrian_route(
            payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng
        )
        if tmap_points:
            mode = "tmap"
            sample_points = tmap_points
        else:
            mode = "straight_line"
            sample_points = [
                (
                    payload.start_lat + (payload.end_lat - payload.start_lat) * (i / 4),
                    payload.start_lng + (payload.end_lng - payload.start_lng) * (i / 4),
                )
                for i in range(5)
            ]
        candidates = [
            {
                "points": sample_points,
                "score": _point_sample_score(sample_points, zones),
                "distance_m": _path_distance_m(sample_points),
            }
        ]

    best = candidates[0]
    passed = _zones_passed(best["points"], zones)
    alternatives = [
        RouteAlternative(
            route_points=[RoutePoint(lat=lat, lng=lng) for lat, lng in c["points"]],
            safety_score=c["score"],
            distance_m=c["distance_m"],
        )
        for c in candidates
    ]

    return RouteResponse(
        safety_score=best["score"],
        zones_passed=passed,
        route_points=[RoutePoint(lat=lat, lng=lng) for lat, lng in best["points"]],
        mode=mode,
        alternatives=alternatives,
    )
