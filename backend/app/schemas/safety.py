from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.time_period import Period

RouteMode = Literal["safety_weighted", "tmap", "straight_line"]
RouteDataBasis = Literal[
    "zone_safety_indicators",
    "osm_walking_network",
    "facility_density",
    "tmap_pedestrian_route",
    "straight_line_estimate",
]
RouteMissingDataFactor = Literal[
    "streetlight_data",
    "crime_rate",
    "police_distance",
    "emergency_bell_distance",
    "accident_hotspot_distance",
]
RouteFallbackReason = Literal["none", "safety_weighted_unavailable", "tmap_unavailable"]
MAX_WALKING_DISTANCE_KM = 10.0


def _haversine_km(start_lat: float, start_lng: float, end_lat: float, end_lng: float) -> float:
    lat_delta = radians(end_lat - start_lat)
    lng_delta = radians(end_lng - start_lng)
    a = sin(lat_delta / 2) ** 2 + cos(radians(start_lat)) * cos(radians(end_lat)) * sin(lng_delta / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


class SafetyZoneOut(BaseModel):
    dong_code: str
    dong_name: str
    lat: float
    lng: float
    safety_score: float
    day_safety_score: float
    night_safety_score: float
    period: Period

    class Config:
        from_attributes = True


class RouteRequest(BaseModel):
    start_lat: float = Field(ge=-90, le=90)
    start_lng: float = Field(ge=-180, le=180)
    end_lat: float = Field(ge=-90, le=90)
    end_lng: float = Field(ge=-180, le=180)
    at: datetime | None = None  # 생략 시 서버 현재 KST 시각 기준으로 주/야간 판정
    include_comparison: bool = True

    @model_validator(mode="after")
    def validate_walking_distance(self) -> "RouteRequest":
        distance_km = _haversine_km(self.start_lat, self.start_lng, self.end_lat, self.end_lng)
        if distance_km > MAX_WALKING_DISTANCE_KM:
            raise ValueError("직선거리 10km를 초과하는 보행 경로는 지원하지 않습니다")
        return self


class RoutePoint(BaseModel):
    lat: float
    lng: float


class RouteAlternative(BaseModel):
    route_points: list[RoutePoint]
    safety_score: float
    distance_m: float
    zones_passed: list[SafetyZoneOut]


class RouteMissingData(BaseModel):
    factor: RouteMissingDataFactor
    affected_zone_count: int


class RouteFallback(BaseModel):
    applied: bool
    mode: RouteMode
    reason: RouteFallbackReason


class RouteDataDisclosure(BaseModel):
    # 데이터 원본의 갱신일이 아니라, 검증된 경로 산출물이 게시된 시각이다.
    # 산출물을 쓰지 않은 런타임 점수 계산에서는 None으로 보존한다.
    data_basis: list[RouteDataBasis]
    updated_at: datetime | None
    missing_data: list[RouteMissingData]
    fallback: RouteFallback


class RouteResponse(BaseModel):
    safety_score: float
    zones_passed: list[SafetyZoneOut]
    route_points: list[RoutePoint]
    mode: RouteMode
    # timeMode가 "자동"일 때도 프론트가 실제로 어느 시간대 가중치가 쓰였는지 배지로 보여줄 수 있게.
    period: Period
    data_disclosure: RouteDataDisclosure
    alternatives: list[RouteAlternative]
    # mode가 safety_weighted일 때만 비교용으로 채워짐 — 안전 가중 경로가
    # 실제 최단경로와 다르다는 걸 지도에서 눈으로 확인할 수 있게 한다.
    shortest_route_points: list[RoutePoint] | None = None
    # 최단경로가 지나는 동 — 길안내에서 안전 경로와 최단 경로를 같은 기준(동 안전지수)으로 비교하게 한다.
    shortest_zones_passed: list[SafetyZoneOut] | None = None
