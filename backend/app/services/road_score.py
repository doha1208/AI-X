"""OSM 도로 태그로 구간(edge) 단위 안전 점수(0~100, 높을수록 안전)를 계산한다.

동 단위 점수(CCTV·보안등 등)는 같은 동 안의 모든 길이 같은 값이라 큰길과 골목을
구분하지 못한다 — 이 점수가 그 차이를 메운다.

ponytail: 아래 점수표는 체감 기반 MVP 값. 실제 귀갓길 피드백으로 조정 필요.
"""
from typing import Any

from app.services.safety_score import Period

DEFAULT_HIGHWAY_SCORE = 50.0

# 사람·차 통행이 많은 큰길이 외진 길보다 안전하다고 본다.
_HIGHWAY_SCORE: dict[str, float] = {
    "pedestrian": 85,
    "living_street": 80,
    "primary": 75,
    "secondary": 75,
    "tertiary": 70,
    "residential": 65,
    "trunk": 60,
    "unclassified": 55,
    "footway": 55,
    "service": 40,
    "steps": 35,
    "path": 30,
    "track": 20,
}

# (yes 보너스, no 페널티) — 가로등은 밤에만 크게 작용한다.
_LIT_ADJUST: dict[Period, tuple[float, float]] = {"day": (5, -5), "night": (15, -25)}
_SIDEWALK_ADJUST = (10, -10)
_DEAD_END_PENALTY: dict[Period, float] = {"day": -5, "night": -15}

_SIDEWALK_YES = {"both", "left", "right", "yes"}
_SIDEWALK_NO = {"no", "none"}


def _values(raw: Any) -> list[str]:
    # osmnx는 간선을 합칠 때 서로 다른 값을 리스트로 보관한다.
    if raw is None:
        return []
    return [str(v) for v in raw] if isinstance(raw, list) else [str(raw)]


def _highway_score(raw: Any) -> float:
    scores = [_HIGHWAY_SCORE.get(v.removesuffix("_link"), DEFAULT_HIGHWAY_SCORE) for v in _values(raw)]
    return min(scores) if scores else DEFAULT_HIGHWAY_SCORE


def _lit_adjust(raw: Any, period: Period) -> float:
    values = _values(raw)
    bonus, penalty = _LIT_ADJUST[period]
    if "no" in values:
        return penalty
    return bonus if "yes" in values else 0.0


def _sidewalk_adjust(raw: Any) -> float:
    values = set(_values(raw))
    bonus, penalty = _SIDEWALK_ADJUST
    if values & _SIDEWALK_NO:
        return penalty
    return bonus if values & _SIDEWALK_YES else 0.0


def road_safety_score(tags: dict[str, Any], period: Period, dead_end: bool = False) -> float:
    score = _highway_score(tags.get("highway"))
    score += _lit_adjust(tags.get("lit"), period)
    score += _sidewalk_adjust(tags.get("sidewalk"))
    if dead_end:
        score += _DEAD_END_PENALTY[period]
    return max(0.0, min(100.0, score))
