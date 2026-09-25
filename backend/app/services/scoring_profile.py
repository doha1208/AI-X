from dataclasses import dataclass
from math import isclose, isfinite
from types import MappingProxyType
from typing import Literal, Mapping


Period = Literal["day", "night"]
FACTOR_NAMES = (
    "cctv_count",
    "streetlight_count",
    "crime_rate",
    "police_dist_m",
    "store_count",
    "bell_dist_m",
)


@dataclass(frozen=True)
class ScoringProfile:
    version: str
    weights: Mapping[Period, Mapping[str, float]]
    unknown_score: float


def _readonly_weights(weights: dict[Period, dict[str, float]]) -> Mapping[Period, Mapping[str, float]]:
    return MappingProxyType({period: MappingProxyType(values) for period, values in weights.items()})


DEFAULT_SCORING_PROFILE = ScoringProfile(
    version="default-v1",
    weights=_readonly_weights(
        {
            "day": {
                "cctv_count": 0.25,
                "streetlight_count": 0.10,
                "crime_rate": 0.30,
                "police_dist_m": 0.10,
                "store_count": 0.15,
                "bell_dist_m": 0.10,
            },
            "night": {
                "cctv_count": 0.15,
                "streetlight_count": 0.25,
                "crime_rate": 0.25,
                "police_dist_m": 0.10,
                "store_count": 0.10,
                "bell_dist_m": 0.15,
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
        if set(weights) != set(FACTOR_NAMES):
            raise ValueError("지원하지 않는 점수 요인이 있습니다")
        if not all(isinstance(weight, (int, float)) and isfinite(weight) and weight >= 0 for weight in weights.values()):
            raise ValueError("가중치는 0 이상인 숫자여야 합니다")
        if not isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
            raise ValueError(f"{period} 가중치 합계는 1.0이어야 합니다")
