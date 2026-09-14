from pydantic import BaseModel


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


class RouteResponse(BaseModel):
    safety_score: float
    zones_passed: list[SafetyZoneOut]
