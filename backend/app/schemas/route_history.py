from datetime import datetime
from pydantic import BaseModel

class RoutePlaceIn(BaseModel):
    label: str
    lat: float
    lng: float

class RouteHistoryCreate(BaseModel):
    start: RoutePlaceIn
    end: RoutePlaceIn

class RouteHistorySettings(BaseModel):
    remember_route_history: bool

class RouteHistoryItem(BaseModel):
    start: RoutePlaceIn
    end: RoutePlaceIn
    last_used_at: datetime

class RouteHistoryOut(BaseModel):
    remember_route_history: bool
    items: list[RouteHistoryItem]
