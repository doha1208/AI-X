import asyncio
import math
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.safety_zone import SafetyZone, scoped_zones_query
from app.core.config import settings
from app.core.security import decode_token
from app.schemas.safety import (
    RouteAlternative,
    RouteDataDisclosure,
    RouteFallback,
    RouteFallbackReason,
    RouteMissingData,
    RouteMode,
    RouteRequest,
    RoutePoint,
    RouteResponse,
    SafetyZoneOut,
)
from app.services.bells import DEFAULT_BELL_LIMIT, nearby_bells
from app.services.geo import haversine_km
from app.services.safe_route import find_safe_routes, route_artifact_runtime
from app.services.safety_score import compute_zone_period_scores
from app.services.service_area import is_in_service_area
from app.services.time_period import period_for
from app.services.tmap import get_pedestrian_route
from app.services.route_request_limit import RouteRequestGate
from app.observability import log_route, metrics

router = APIRouter(prefix="/safety", tags=["safety"])

Point = tuple[float, float]

route_request_gate = RouteRequestGate(
    max_concurrent=settings.route_max_concurrent,
    ip_requests_per_minute=settings.route_ip_requests_per_minute,
    ip_burst=settings.route_ip_burst,
    user_requests_per_minute=settings.route_user_requests_per_minute,
    user_burst=settings.route_user_burst,
    max_tracked_buckets=settings.route_request_max_tracked_buckets,
)


def _client_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    trusted_proxies = {ip.strip() for ip in settings.trusted_proxy_ips.split(",") if ip.strip()}
    forwarded_for = request.headers.get("x-forwarded-for")
    if direct_ip in trusted_proxies and forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return direct_ip


def _authenticated_user_id(request: Request) -> str | None:
    token = request.cookies.get("access_token")
    payload = decode_token(token) if token else None
    if payload and payload.get("type") == "access" and isinstance(payload.get("sub"), str):
        return payload["sub"]
    return None


async def limit_route_requests(request: Request):
    admission = route_request_gate.acquire(
        client_ip=_client_ip(request),
        user_id=_authenticated_user_id(request),
    )
    if not admission.granted:
        retry_after = admission.retry_after_seconds or 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="경로 요청이 잠시 많습니다. 잠시 후 다시 시도해 주세요.",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        yield
    finally:
        admission.release()


def _route_distance_m(points: list[Point]) -> float:
    return sum(
        haversine_km(a[0], a[1], b[0], b[1]) * 1000 for a, b in zip(points[:-1], points[1:])
    )


def _sample_route_score(
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


def _period_score_maps(
    zones: list[SafetyZone],
) -> tuple[dict[str, dict[str, float]], dict[str, bool]]:
    score_maps: dict[str, dict[str, float]] = {}
    artifact_used: dict[str, bool] = {}
    for period in ("day", "night"):
        scores = _artifact_score_map_for_zones(zones, period)
        artifact_used[period] = scores is not None
        score_maps[period] = scores if scores is not None else compute_zone_period_scores(zones, period)
    return score_maps, artifact_used


def _zone_out(
    zone: SafetyZone,
    score_maps: dict[str, dict[str, float]],
    period: str,
) -> SafetyZoneOut:
    return SafetyZoneOut(
        dong_code=zone.dong_code,
        dong_name=zone.dong_name,
        lat=zone.lat,
        lng=zone.lng,
        safety_score=score_maps[period][zone.dong_code],
        day_safety_score=score_maps["day"][zone.dong_code],
        night_safety_score=score_maps["night"][zone.dong_code],
        period=period,
    )


def _artifact_score_map_for_zones(
    zones: list[SafetyZone], period: str
) -> dict[str, float] | None:
    scores = route_artifact_runtime.score_map(period)
    if scores is None:
        return None
    if any(
        zone.dong_code not in scores
        or not isinstance(scores[zone.dong_code], (int, float))
        or not math.isfinite(scores[zone.dong_code])
        for zone in zones
    ):
        return None
    return scores


def _missing_route_data(zones: list[SafetyZone]) -> list[RouteMissingData]:
    checks = {
        "streetlight_data": lambda zone: not zone.lights_known,
        "crime_rate": lambda zone: zone.crime_rate is None,
        "police_distance": lambda zone: zone.police_dist_m is None,
        "emergency_bell_distance": lambda zone: zone.bell_dist_m is None,
        "accident_hotspot_distance": lambda zone: zone.accident_dist_m is None,
    }
    return [
        RouteMissingData(factor=factor, affected_zone_count=sum(check(zone) for zone in zones))
        for factor, check in checks.items()
        if any(check(zone) for zone in zones)
    ]


def _route_data_disclosure(
    *,
    mode: RouteMode,
    zones_passed: list[SafetyZone],
    artifact_used: bool,
) -> RouteDataDisclosure:
    data_basis = ["zone_safety_indicators"]
    if mode == "safety_weighted":
        data_basis.extend(["osm_walking_network", "facility_density"])
    elif mode == "tmap":
        data_basis.insert(0, "tmap_pedestrian_route")
    else:
        raise ValueError(f"Unsupported route mode for disclosure: {mode}")

    reason: RouteFallbackReason = "none"
    if mode == "tmap":
        reason = "safety_weighted_unavailable"

    return RouteDataDisclosure(
        data_basis=data_basis,
        updated_at=route_artifact_runtime.published_at() if artifact_used else None,
        missing_data=_missing_route_data(zones_passed),
        fallback=RouteFallback(applied=mode != "safety_weighted", mode=mode, reason=reason),
    )


@router.get("/zones", response_model=list[SafetyZoneOut])
def nearby_zones(
    lat: float,
    lng: float,
    radius_km: float = Query(2.0, gt=0),
    db: Session = Depends(get_db),
):
    """반경 안의 동을 찾아 반환한다.

    점수는 조회된(scoped) 동 전체를 기준으로 그때그때 다시 정규화한다 — DB에 저장된
    safety_score 컬럼은 ingest 시점의 전체(서울+경기) 범위로 정규화돼 있어, REGION_SCOPE_PREFIX로
    경기도만 보여줄 때 그 컬럼을 그대로 쓰면 경기도 안에서의 상대 순위와 어긋날 수 있다.
    """
    zones = scoped_zones_query(db).all()
    period = period_for()
    score_maps, _ = _period_score_maps(zones)
    nearby = [z for z in zones if haversine_km(lat, lng, z.lat, z.lng) <= radius_km]
    return [_zone_out(z, score_maps, period) for z in nearby]


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
    zones = scoped_zones_query(db).all()
    period = period_for()
    score_maps, _ = _period_score_maps(zones)
    top = sorted(zones, key=lambda zone: score_maps[period][zone.dong_code], reverse=True)[:limit]
    return [_zone_out(zone, score_maps, period) for zone in top]


@router.post("/route", response_model=RouteResponse)
async def route_safety(
    payload: RouteRequest,
    db: Session = Depends(get_db),
    _request_limit: None = Depends(limit_route_requests),
):
    """출발지→도착지 경로를 3단계 우선순위로 계산한다.

    1) safety_weighted: OSM 도로망 그래프 위에서 안전점수를 비용으로 반영해
       실제로 더 안전한 길을 고르는 자체 경로 탐색. 대안 경로 여러 개를
       안전점수 순으로 함께 반환한다.
    2) tmap: 위 그래프 탐색이 실패(지역 미지원/네트워크 오류)하면 Tmap
       보행자 최단경로를 받아 그 위에 안전점수만 표시(대안 없음).
    둘 다 실패하면 직선을 보행 경로처럼 반환하지 않고 503 오류를 반환한다.
    """
    started_at = time.perf_counter()
    points = {
        "start": (payload.start_lat, payload.start_lng),
        "end": (payload.end_lat, payload.end_lng),
    }
    unsupported_points = [
        name
        for name, (lat, lng) in points.items()
        if not is_in_service_area(
            lat,
            lng,
            region_scope_prefix=settings.region_scope_prefix,
        )
    ]
    if unsupported_points:
        metrics.record_route(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            duration_seconds=time.perf_counter() - started_at,
            mode="failed",
            fallback_reason="outside_service_area",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "outside_service_area",
                "action": "현재 길찾기는 서울·경기 지역에서만 지원합니다.",
                "points": unsupported_points,
            },
        )
    zones = scoped_zones_query(db).all()
    if not zones:
        metrics.record_route(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            duration_seconds=time.perf_counter() - started_at,
            mode="failed",
            fallback_reason="safety_zones_unavailable",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "reason": "safety_zones_unavailable",
                "action": "안전 데이터가 준비될 때까지 잠시 후 다시 시도해 주세요.",
            },
        )
    period = period_for(payload.at)
    score_maps, artifact_scores_used = _period_score_maps(zones)
    score_map = score_maps[period]

    safe_route_task = asyncio.to_thread(
        find_safe_routes,
        payload.start_lat,
        payload.start_lng,
        payload.end_lat,
        payload.end_lng,
        zones,
        period=period,
    )
    if payload.include_comparison:
        # 직접 검색은 비교선을 유지하므로 두 경로를 병렬로 가져온다.
        safe_routes, tmap_points = await asyncio.gather(
            safe_route_task,
            get_pedestrian_route(payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng),
        )
    else:
        # 실시간 재경로는 안전 경로만 요청한다. 자체 경로가 없을 때만 Tmap 폴백을 쓴다.
        safe_routes = await safe_route_task
        tmap_points = None
        if not safe_routes:
            tmap_points = await get_pedestrian_route(
                payload.start_lat, payload.start_lng, payload.end_lat, payload.end_lng
            )

    shortest_route_points: list[RoutePoint] | None = None
    shortest_zones_passed: list[SafetyZoneOut] | None = None
    candidates: list[dict]
    if safe_routes:
        mode: RouteMode = "safety_weighted"
        candidates = safe_routes
        # 안전 가중 경로가 실제 최단경로와 다르다는 걸 지도에서 비교해 보여주는 참고선.
        if tmap_points:
            shortest_route_points = [RoutePoint(lat=lat, lng=lng) for lat, lng in tmap_points]
            shortest_zones_passed = [
                _zone_out(z, score_maps, period) for z in _zones_passed(tmap_points, zones)
            ]
    else:
        if tmap_points:
            mode = "tmap"
            sample_points = tmap_points
        else:
            duration_seconds = time.perf_counter() - started_at
            metrics.record_route(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                duration_seconds=duration_seconds,
                mode="failed",
                fallback_reason="tmap_unavailable",
            )
            log_route(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                duration_seconds=duration_seconds,
                mode="failed",
                fallback_reason="tmap_unavailable",
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "reason": "pedestrian_route_unavailable",
                    "action": "현재 보행 경로를 찾을 수 없습니다. 잠시 후 다시 시도해 주세요.",
                },
            )
        candidates = [
            {
                "points": sample_points,
                "score": _sample_route_score(sample_points, zones, score_map),
                "distance_m": _route_distance_m(sample_points),
            }
        ]

    best = candidates[0]
    passed = [_zone_out(z, score_maps, period) for z in _zones_passed(best["points"], zones)]
    alternatives = [
        RouteAlternative(
            route_points=[RoutePoint(lat=lat, lng=lng) for lat, lng in c["points"]],
            safety_score=c["score"],
            distance_m=c["distance_m"],
            zones_passed=[
                _zone_out(z, score_maps, period)
                for z in _zones_passed(c["points"], zones)
            ],
        )
        for c in candidates
    ]

    response = RouteResponse(
        safety_score=best["score"],
        zones_passed=passed,
        route_points=[RoutePoint(lat=lat, lng=lng) for lat, lng in best["points"]],
        mode=mode,
        period=period,
        data_disclosure=_route_data_disclosure(
            mode=mode,
            zones_passed=_zones_passed(best["points"], zones),
            artifact_used=mode == "safety_weighted" or artifact_scores_used[period],
        ),
        alternatives=alternatives,
        shortest_route_points=shortest_route_points,
        shortest_zones_passed=shortest_zones_passed,
    )
    fallback_reason = "none" if mode == "safety_weighted" else "safe_route_unavailable"
    metrics.record_route(
        status_code=status.HTTP_200_OK,
        duration_seconds=time.perf_counter() - started_at,
        mode=mode,
        fallback_reason=fallback_reason,
    )
    log_route(
        status_code=status.HTTP_200_OK,
        duration_seconds=time.perf_counter() - started_at,
        mode=mode,
        fallback_reason=fallback_reason,
    )
    return response
