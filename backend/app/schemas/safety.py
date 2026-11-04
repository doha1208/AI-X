from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.time_period import Period

RouteMode = Literal["safety_weighted", "tmap"]
RouteDataBasis = Literal[
    "zone_safety_indicators",
    "osm_walking_network",
    "facility_density",
    "tmap_pedestrian_route",
]
RouteMissingDataFactor = Literal[
    "streetlight_data",
    "cctv_data",
    "crime_rate",
    "police_distance",
    "emergency_bell_distance",
    "accident_hotspot_distance",
    "night_floating_population",
]
RouteFallbackReason = Literal["none", "safety_weighted_unavailable"]
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


class SafetyZoneDetail(SafetyZoneOut):
    """동네 비교용 — 점수와 함께 점수를 만든 원자료와 경기도 안 순위를 보여준다. None은 '모름'."""

    rank: int
    total: int
    cctv_count: int | None
    streetlight_count: int | None
    crime_rate: float | None
    police_dist_m: float | None
    bell_dist_m: float | None
    accident_dist_m: float | None
    night_floating_pop: float | None
    store_count: int


class SafeHaven(BaseModel):
    kind: Literal["police", "convenience", "bell"]
    lat: float
    lng: float
    distance_m: int


class FacilityCounts(BaseModel):
    cctv: int | None
    lights: int | None
    convenience: int | None


class SpotReport(BaseModel):
    """한 지점 주변 요약 — 집 주소 리포트와 실시간 안내의 안심 거점 안내가 함께 쓴다."""

    lat: float
    lng: float
    period: Period
    radius_m: int
    zone: SafetyZoneDetail | None
    # 지금 이 자리의 구간 점수(현재 시간대). 구간 데이터가 없으면 None.
    here_score: float | None
    area_day_score: float | None
    area_night_score: float | None
    counts: FacilityCounts | None
    havens: list[SafeHaven]


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
    safety_score: float | None
    distance_m: float
    zones_passed: list[SafetyZoneOut]
    environment_assessment: "RouteEnvironmentAssessment | None" = None


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


class RouteEnvironmentAssessment(BaseModel):
    model_version: str
    policy_version: str
    status: Literal["available", "degraded", "unavailable"]
    period: Period
    distance_m: float
    score: float | None
    active_factors: list[str]
    used_factors: list[str]
    excluded_factors: dict[str, str]
    factor_coverage: dict[str, float]
    data_factor_availability_ratio: float
    longest_support_gap_m: float | None
    total_support_gap_m: float | None
    gap_intervals: list[dict[str, float]]
    source_versions: dict[str, str]
    comparison_group_id: str
    per_factor_gaps: dict[str, list[dict[str, float]]] = Field(default_factory=dict)
    observed_facility_counts: dict[str, int] = Field(default_factory=dict)
    observed_factor_coverage: dict[str, float] = Field(default_factory=dict)
    evaluation_basis: Literal["multi_factor", "single_factor", "partial_coverage", "observed_only", "unavailable"] = "unavailable"
    reference_score: float | None = None
    reference_factor: str | None = None
    score_bounds: dict[str, float] | None = None
    factor_evaluation_ratio: dict[str, float] = Field(default_factory=dict)
    verified_distance_ratio: float = 0.0
    evidence_factors: list[str] = Field(default_factory=list)


RouteAlternative.model_rebuild()


class RouteResponse(BaseModel):
    safety_score: float | None
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
    environment_assessment: RouteEnvironmentAssessment | None = None
    comparison_environment_assessment: RouteEnvironmentAssessment | None = None
    environment_model_applied: bool = False
    baseline_source: Literal["tmap", "osm_shortest"] | None = None
