from dataclasses import dataclass
from math import isclose, isfinite
from types import MappingProxyType
from typing import Literal, Mapping


Period = Literal["day", "night"]
LEGACY_FACTOR_NAMES = (
    "cctv_count",
    "streetlight_count",
    "crime_rate",
    "police_dist_m",
    "store_count",
    "bell_dist_m",
)
FACTOR_NAMES = (*LEGACY_FACTOR_NAMES, "accident_dist_m")


@dataclass(frozen=True)
class ScoringProfile:
    version: str
    weights: Mapping[Period, Mapping[str, float]]
    unknown_score: float


def _readonly_weights(weights: dict[Period, dict[str, float]]) -> Mapping[Period, Mapping[str, float]]:
    return MappingProxyType({period: MappingProxyType(values) for period, values in weights.items()})


DEFAULT_SCORING_PROFILE = ScoringProfile(
    version="default-v2",
    weights=_readonly_weights(
        {
            "day": {
                "cctv_count": 0.20,
                "streetlight_count": 0.15,
                "crime_rate": 0.20,
                "police_dist_m": 0.10,
                "store_count": 0.15,
                "bell_dist_m": 0.10,
                "accident_dist_m": 0.10,
            },
            "night": {
                "cctv_count": 0.15,
                "streetlight_count": 0.30,
                "crime_rate": 0.20,
                "police_dist_m": 0.05,
                "store_count": 0.05,
                "bell_dist_m": 0.15,
                "accident_dist_m": 0.10,
            },
        }
    ),
    unknown_score=50.0,
)


def validate_profile(profile: ScoringProfile) -> None:
    if not profile.version.strip():
        raise ValueError("프로필 버전이 필요합니다")
    if set(profile.weights) != {"day", "night"}:
        raise ValueError("낮과 밤 가중치가 모두 필요합니다")
    if not isinstance(profile.unknown_score, (int, float)) or not isfinite(profile.unknown_score):
        raise ValueError("중립 점수는 0~100 사이 숫자여야 합니다")
    if not 0 <= profile.unknown_score <= 100:
        raise ValueError("중립 점수는 0~100 사이여야 합니다")

    for period in ("day", "night"):
        weights = profile.weights[period]
        if set(weights) not in (set(LEGACY_FACTOR_NAMES), set(FACTOR_NAMES)):
            raise ValueError("지원하지 않는 점수 요인이 있습니다")
        if not all(isinstance(weight, (int, float)) and isfinite(weight) and weight >= 0 for weight in weights.values()):
            raise ValueError("가중치는 0 이상인 숫자여야 합니다")
        if not isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError(f"{period} 가중치 합계는 1.0이어야 합니다")


# 경로 간선의 동 점수에 남기는 요인. CCTV·보안등·상점·사고다발지역은 도로 구간 단위로
# 따로 세므로(facility_density) 동 점수에도 넣으면 같은 데이터가 두 번 반영된다.
ROUTE_ZONE_FACTORS = ("crime_rate", "police_dist_m", "bell_dist_m")


def route_zone_profile(profile: ScoringProfile) -> ScoringProfile:
    """프로필 가중치에서 ROUTE_ZONE_FACTORS만 남겨 합이 1이 되게 다시 나눈 새 프로필.

    셋 다 0이면 범죄율만 쓴다.
    """
    weights: dict[Period, dict[str, float]] = {}
    for period in ("day", "night"):
        kept = {f: profile.weights[period].get(f, 0.0) for f in ROUTE_ZONE_FACTORS}
        total = sum(kept.values())
        normalized = {f: w / total for f, w in kept.items()} if total > 0 else {"crime_rate": 1.0}
        weights[period] = {f: normalized.get(f, 0.0) for f in FACTOR_NAMES}
    return ScoringProfile(f"{profile.version}:route-zone", _readonly_weights(weights), profile.unknown_score)
