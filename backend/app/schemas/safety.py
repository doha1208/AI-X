from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RouteMode = Literal["safety_weighted", "tmap", "straight_line"]
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


class RouteResponse(BaseModel):
    safety_score: float
    zones_passed: list[SafetyZoneOut]
    route_points: list[RoutePoint]
    mode: RouteMode
    alternatives: list[RouteAlternative]
    # mode가 safety_weighted일 때만 비교용으로 채워짐 — 안전 가중 경로가
    # 실제 최단경로와 다르다는 걸 지도에서 눈으로 확인할 수 있게 한다.
    shortest_route_points: list[RoutePoint] | None = None
