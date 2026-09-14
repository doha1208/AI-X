from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.safety_zone import SafetyZone
from app.schemas.safety import RouteRequest, RouteResponse, SafetyZoneOut
from app.services.geo import haversine_km

router = APIRouter(prefix="/safety", tags=["safety"])


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
def route_safety(payload: RouteRequest, db: Session = Depends(get_db)):
    """직선 경로 위 표본점 5개에서 가장 가까운 안전 구역을 찾아 평균 점수 산출.

    ponytail: 실제 도로망 경로(카카오맵 길찾기 API) 연동 전 단계의 단순화.
    가중치 반영 최적 경로 탐색은 실제 라우팅 API 응답을 받은 뒤 고도화.
    """
    zones = db.query(SafetyZone).all()
    passed: list[SafetyZone] = []
    seen_codes: set[str] = set()

    for i in range(5):
        t = i / 4
        sample_lat = payload.start_lat + (payload.end_lat - payload.start_lat) * t
        sample_lng = payload.start_lng + (payload.end_lng - payload.start_lng) * t
        nearest = min(
            zones, key=lambda z: haversine_km(sample_lat, sample_lng, z.lat, z.lng)
        )
        if nearest.dong_code not in seen_codes:
            seen_codes.add(nearest.dong_code)
            passed.append(nearest)

    avg_score = sum(z.safety_score for z in passed) / len(passed) if passed else 0.0
    return RouteResponse(safety_score=avg_score, zones_passed=passed)
