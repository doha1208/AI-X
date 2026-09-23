import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.safety_zone import SafetyZone, scoped_zones_query
from app.schemas.safety import (
    RouteAlternative,
    RouteMode,
    RouteRequest,
    RoutePoint,
    RouteResponse,
    SafetyZoneOut,
)
from app.services.bells import DEFAULT_BELL_LIMIT, nearby_bells
from app.services.geo import haversine_km
from app.services.safe_route import find_safe_routes
from app.services.safety_score import compute_zone_period_scores
from app.services.time_period import period_for
from app.services.tmap import get_pedestrian_route

router = APIRouter(prefix="/safety", tags=["safety"])

Point = tuple[float, float]


def _path_distance_m(points: list[Point]) -> float:
    return sum(
        haversine_km(a[0], a[1], b[0], b[1]) * 1000 for a, b in zip(points[:-1], points[1:])
    )


def _point_sample_score(
    points: list[Point], zones: list[SafetyZone], score_map: dict[str, float]
) -> float:
    scores = [
        score_map[min(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng)).dong_code]
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
    zones = scoped_zones_query(db).all()
    return [z for z in zones if haversine_km(lat, lng, z.lat, z.lng) <= radius_km]


@router.get("/bells", response_model=list[RoutePoint])
def nearby_bells_endpoint(
    lat: float,
    lng: float,
    radius_km: float = Query(1.0, gt=0),
    limit: int = Query(DEFAULT_BELL_LIMIT, gt=0, le=1000),
):
    """지도 표시용 — 반경 안의 안전비상벨 좌표(안전 지수 계산과는 별개 조회).

    limit을 넉넉하게 올려 받은 뒤 프론트에서 실제 경로 선 근처만 다시 거르는
    용도(귀갓길)로도 쓴다 — le=1000은 그 상한.
    """
    return nearby_bells(lat, lng, radius_km, limit=limit)


@router.get("/residence-recommend", response_model=list[SafetyZoneOut])
def residence_recommend(limit: int = Query(5, gt=0, le=50), db: Session = Depends(get_db)):
    return (
        scoped_zones_query(db)
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
    zones = scoped_zones_query(db).all()
    period = period_for(payload.at)
    score_map = compute_zone_period_scores(zones, period)

    # 안전 가중 탐색과 Tmap 최단경로를 동시에 돌린다 — Tmap은 safety_weighted일 때
    # 비교선으로, 실패했을 때는 폴백 경로로 쓰이니 순서와 무관하게 항상 필요하다.
    # 순차로 기다리면(특히 실시간 재경로 폴링 중) Tmap 응답 지연(최대 8초)이
    # 그대로 사용자 대기 시간에 더해지므로 asyncio.gather로 병렬화한다.
    safe_routes, tmap_points = await asyncio.gather(
        asyncio.to_thread(
            find_safe_routes,
            payload.start_lat,
            payload.start_lng,
            payload.end_lat,
            payload.end_lng,
            zones,
            period=period,
        ),
        get_pedestrian_route(payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng),
    )

    shortest_route_points: list[RoutePoint] | None = None
    candidates: list[dict]
    if safe_routes:
        mode: RouteMode = "safety_weighted"
        candidates = safe_routes
        # 안전 가중 경로가 실제 최단경로와 다르다는 걸 지도에서 비교해 보여주는 참고선.
        if tmap_points:
            shortest_route_points = [RoutePoint(lat=lat, lng=lng) for lat, lng in tmap_points]
    else:
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
                "score": _point_sample_score(sample_points, zones, score_map),
                "distance_m": _path_distance_m(sample_points),
            }
        ]

    best = candidates[0]
    passed = [
        SafetyZoneOut(
            dong_code=z.dong_code,
            dong_name=z.dong_name,
            lat=z.lat,
            lng=z.lng,
            safety_score=score_map[z.dong_code],
        )
        for z in _zones_passed(best["points"], zones)
    ]
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
        shortest_route_points=shortest_route_points,
    )
