import math
import time
from dataclasses import asdict

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
    RouteRequest,
    RoutePoint,
    RouteResponse,
    SafetyZoneDetail,
    SafetyZoneOut,
    SpotReport,
)
from app.services.bells import DEFAULT_BELL_LIMIT, nearby_bells
from app.services.geo import haversine_km
from app.services.safe_route import _facility_index, route_artifact_runtime
from app.services.spot_report import (
    REPORT_RADIUS_M,
    area_scores,
    facility_counts,
    load_haven_index,
    nearest_havens,
    point_score,
)
from app.services.safety_score import compute_zone_period_scores
from app.services.service_area import is_in_service_area
from app.services.time_period import period_for
from app.services.tmap import get_pedestrian_route
from app.services.route_request_limit import RouteRequestGate
from app.observability import log_route, metrics
from app.services.route_environment_service import calculate_environment_routes

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






@router.get("/zones", response_model=list[SafetyZoneOut])
def nearby_zones(
    lat: float,
    lng: float,
    radius_km: float = Query(2.0, gt=0),
    db: Session = Depends(get_db),
):
    """반경 안의 동을 찾아 반환한다.

    점수는 조회된(scoped) 동 전체를 기준으로 그때그때 다시 정규화한다. DB의
    safety_score는 적재 시점 범위를 기준으로 계산되므로, 조회 범위나 점수 프로필이
    달라지면 저장된 값을 그대로 사용하는 대신 현재 범위의 점수를 계산한다.
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
    if not is_in_service_area(lat, lng, region_scope_prefix=settings.region_scope_prefix):
        return []
    return nearby_bells(
        lat,
        lng,
        radius_km,
        limit=limit,
        allowed=lambda bell_lat, bell_lng: is_in_service_area(
            bell_lat, bell_lng, region_scope_prefix=settings.region_scope_prefix
        ),
    )


@router.get("/residence-recommend", response_model=list[SafetyZoneOut])
def residence_recommend(limit: int = Query(5, gt=0, le=50), db: Session = Depends(get_db)):
    zones = scoped_zones_query(db).all()
    period = period_for()
    score_maps, _ = _period_score_maps(zones)
    top = sorted(zones, key=lambda zone: score_maps[period][zone.dong_code], reverse=True)[:limit]
    return [_zone_out(zone, score_maps, period) for zone in top]


def _zone_detail(
    zone: SafetyZone, score_maps: dict[str, dict[str, float]], period: str, zones: list[SafetyZone]
) -> SafetyZoneDetail:
    """점수와 원자료를 함께. 지자체가 데이터를 안 올린 요소는 0이 아니라 None(모름)으로 내려준다."""
    score_map = score_maps[period]
    rank = 1 + sum(score_map[z.dong_code] > score_map[zone.dong_code] for z in zones)
    return SafetyZoneDetail(
        **_zone_out(zone, score_maps, period).model_dump(),
        rank=rank,
        total=len(zones),
        cctv_count=zone.cctv_count if zone.cctv_known is not False else None,
        streetlight_count=zone.streetlight_count if zone.lights_known is not False else None,
        crime_rate=zone.crime_rate,
        police_dist_m=zone.police_dist_m,
        bell_dist_m=zone.bell_dist_m if zone.bell_known is not False else None,
        accident_dist_m=zone.accident_dist_m,
        night_floating_pop=zone.night_floating_pop,
        store_count=zone.store_count,
    )


@router.get("/zones/{dong_code}", response_model=SafetyZoneDetail)
def zone_detail(dong_code: str, db: Session = Depends(get_db)):
    """동네 비교 화면용 — 한 동의 점수·순위와 요소별 원자료."""
    zones = scoped_zones_query(db).all()
    zone = next((z for z in zones if z.dong_code == dong_code), None)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 동네를 찾을 수 없어요.")
    score_maps, _ = _period_score_maps(zones)
    return _zone_detail(zone, score_maps, period_for(), zones)


@router.get("/spot", response_model=SpotReport)
def spot_report(
    lat: float = Query(ge=-90, le=90),
    lng: float = Query(ge=-180, le=180),
    radius_m: int = Query(int(REPORT_RADIUS_M), ge=100, le=1000),
    db: Session = Depends(get_db),
):
    """한 지점 주변 요약 — 집 주소 안전 리포트와 실시간 안내의 안심 거점 안내가 함께 쓴다."""
    if not is_in_service_area(lat, lng, region_scope_prefix=settings.region_scope_prefix):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"reason": "outside_service_area", "action": "안전 리포트는 경기도 지역에서만 지원합니다."},
        )
    period = period_for()
    zones = scoped_zones_query(db).all()
    zone = min(zones, key=lambda z: haversine_km(lat, lng, z.lat, z.lng)) if zones else None
    lights_known = zone is None or zone.lights_known is not False
    cctv_known = zone is None or zone.cctv_known is not False
    facilities = _facility_index()
    area = area_scores(facilities, lat, lng, lights_known, cctv_known, radius_m) if facilities else None
    zone_detail_out = None
    if zone is not None:
        score_maps, _ = _period_score_maps(zones)
        zone_detail_out = _zone_detail(zone, score_maps, period, zones)
    return SpotReport(
        lat=lat,
        lng=lng,
        period=period,
        radius_m=radius_m,
        zone=zone_detail_out,
        here_score=point_score(facilities, lat, lng, period, lights_known, cctv_known) if facilities else None,
        area_day_score=area["day"] if area else None,
        area_night_score=area["night"] if area else None,
        counts=facility_counts(facilities, lat, lng, lights_known, cctv_known, radius_m) if facilities else None,
        havens=nearest_havens(load_haven_index(), lat, lng),
    )


@router.post("/route", response_model=RouteResponse)
async def route_safety(
    payload: RouteRequest,
    _request_limit: None = Depends(limit_route_requests),
):
    """Evaluate every walking candidate with facility access and continuous gaps."""
    started_at = time.perf_counter()
    unsupported = [name for name, lat, lng in (
        ("start", payload.start_lat, payload.start_lng),
        ("end", payload.end_lat, payload.end_lng),
    ) if not is_in_service_area(lat, lng, region_scope_prefix=settings.region_scope_prefix)]
    if unsupported:
        metrics.record_route(status_code=422, duration_seconds=time.perf_counter() - started_at,
                             mode="failed", fallback_reason="outside_service_area")
        raise HTTPException(status_code=422, detail={
            "reason": "outside_service_area", "action": "현재 길찾기는 경기도 지역에서만 지원합니다.", "points": unsupported,
        })
    result = await calculate_environment_routes(payload, runtime=route_artifact_runtime, tmap_provider=get_pedestrian_route)
    if result is None:
        metrics.record_route(status_code=503, duration_seconds=time.perf_counter() - started_at,
                             mode="failed", fallback_reason="tmap_unavailable")
        raise HTTPException(status_code=503, detail={
            "reason": "pedestrian_route_unavailable", "action": "현재 보행 경로를 찾을 수 없습니다. 잠시 후 다시 시도해 주세요.",
        })
    best = result.selected[0]
    mode = "safety_weighted" if best.candidate.source == "osm" else "tmap"
    alternatives = [RouteAlternative(
        route_points=[RoutePoint(lat=a, lng=b) for a, b in route.candidate.points],
        safety_score=None, distance_m=route.assessment.distance_m, zones_passed=[],
        environment_assessment=asdict(route.assessment),
    ) for route in result.selected]
    comparison = result.comparison
    basis = ["osm_walking_network" if mode == "safety_weighted" else "tmap_pedestrian_route"]
    if best.assessment.used_factors:
        basis.append("facility_density")
    fallback = mode == "tmap" and not result.osm_available
    response = RouteResponse(
        safety_score=None, zones_passed=[], route_points=alternatives[0].route_points,
        mode=mode, period=period_for(payload.at), alternatives=alternatives,
        environment_assessment=asdict(best.assessment),
        comparison_environment_assessment=asdict(comparison.assessment) if comparison else None,
        environment_model_applied=True, baseline_source=result.baseline_source,
        shortest_route_points=[RoutePoint(lat=a, lng=b) for a, b in comparison.candidate.points] if comparison else None,
        shortest_zones_passed=[] if comparison else None,
        data_disclosure=RouteDataDisclosure(
            data_basis=basis, updated_at=route_artifact_runtime.published_at() if result.artifact_used else None,
            missing_data=[], fallback=RouteFallback(applied=fallback, mode=mode,
                                                  reason="safety_weighted_unavailable" if fallback else "none"),
        ),
    )
    reason = "safe_route_unavailable" if fallback else "none"
    metrics.record_route(status_code=200, duration_seconds=time.perf_counter() - started_at, mode=mode, fallback_reason=reason)
    log_route(status_code=200, duration_seconds=time.perf_counter() - started_at, mode=mode, fallback_reason=reason)
    return response
