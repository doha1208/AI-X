from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RouteMode = Literal["safety_weighted", "tmap", "straight_line"]


class SafetyZoneOut(BaseModel):
    dong_code: str
    dong_name: str
    lat: float
    lng: float
    safety_score: float

    class Config:
        from_attributes = True


class RouteRequest(BaseModel):
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    at: datetime | None = None  # 생략 시 서버 현재 KST 시각 기준으로 주/야간 판정


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
