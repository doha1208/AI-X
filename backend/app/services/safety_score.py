from typing import Literal

Period = Literal["day", "night"]

# 요소별 가중치 — period마다 합 1.0.
# ponytail: MVP 값 — night는 CCTV(사후 확인용)보다 보안등(즉시 시야 확보)
# 비중을 높임. 실제 체감 안전도와 맞춰보며 조정 필요.
_PERIOD_WEIGHTS: dict[Period, dict[str, float]] = {
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

# 값을 모르는(None) 요소에 주는 점수 — 예: 보안등 데이터를 못 받은 지자체의 동.
UNKNOWN_SCORE = 50.0

# 값이 작을수록 안전한 요소(1만 명당 범죄율, 가장 가까운 경찰서·비상벨까지의 거리).
_LOWER_IS_SAFER = {"crime_rate", "police_dist_m", "bell_dist_m"}


# 시·군·구의 동당 평균 보안등 수가 이보다 적으면 그 지역은 데이터를 사실상 못 올린 곳으로 본다.
# (전체 동의 중앙값은 수백 개 — 20개 미만이면 실제로 가로등이 없다기보다 미제출일 가능성이 크다.)
MIN_LIGHTS_PER_DONG = 20


def flag_unknown_streetlights(records: list[dict]) -> list[str]:
    """보안등이 너무 적은 시·군·구(dong_code 앞 5자리)의 동들에 lights_known=False를 표시한다.

    반환값은 표시된 시·군·구 코드. 나머지 동은 lights_known=True.
    """
    by_city: dict[str, list[dict]] = {}
    for record in records:
        by_city.setdefault(record["dong_code"][:5], []).append(record)
    flagged = [
        code
        for code, members in by_city.items()
        if sum(m["streetlight_count"] for m in members) / len(members) < MIN_LIGHTS_PER_DONG
    ]
    for record in records:
        record["lights_known"] = record["dong_code"][:5] not in flagged
    return sorted(flagged)


def _factor_value(record: dict, factor: str):
    """요소 값. 보안등 데이터를 못 받은 지역(lights_known=False)의 보안등은 None(모름)이다."""
    if factor == "streetlight_count" and record.get("lights_known") is False:
        return None
    return record.get(factor)


def _normalize(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100))


def compute_safety_scores(records: list[dict], period: Period = "day") -> list[dict]:
    """요소별 수치(cctv_count/streetlight_count/crime_rate/police_dist_m/store_count)를
    가진 레코드 목록을 받아 0~100 안전 지수(safety_score)를 채워 반환한다. 높을수록 안전.

    같은 동 집합(예: 서울 전체) 안에서의 상대 비교용 min-max 정규화.
    CCTV/보안등/상점은 많을수록, 범죄율(1만 명당)·경찰서 거리는 작을수록 점수가 높다.
    period(day/night)에 따라 요소별 가중치 배분이 달라진다.
    키가 없는 요소와 값이 None인 요소는 "모름"으로 보고 중립 점수를 준다.
    값이 None인 요소는 "모름"이라 정규화 범위에서 빼고 UNKNOWN_SCORE(50점)를 준다.
    """
    if not records:
        return records

    weights = _PERIOD_WEIGHTS[period]
    bounds = {}
    for factor in weights:
        known = [v for v in (_factor_value(r, factor) for r in records) if v is not None]
        bounds[factor] = (min(known), max(known)) if known else (0, 0)

    for record in records:
        total = 0.0
        for factor, weight in weights.items():
            value = _factor_value(record, factor)
            if value is None:
                score = UNKNOWN_SCORE  # 데이터를 못 받은 요소는 좋지도 나쁘지도 않게 본다
            else:
                score = _normalize(value, *bounds[factor])
                score = 100 - score if factor in _LOWER_IS_SAFER else score
            total += weight * score
        record["safety_score"] = round(total, 1)
    return records


def compute_zone_period_scores(zones: list, period: Period = "day") -> dict[str, float]:
    """SafetyZone ORM 목록을 dong_code -> period-가중 안전점수로 변환한다.

    저장된 zone.safety_score 컬럼(day 기준, 거주지 추천용)은 건드리지 않는
    순수 조회용 재계산 — 원본 원시 카운트(cctv/streetlight/crime)만 읽는다.
    """
    if not zones:
        return {}
    records = [
        {
            "dong_code": z.dong_code,
            "cctv_count": z.cctv_count,
            "streetlight_count": z.streetlight_count,
            "lights_known": z.lights_known is not False,
            "crime_rate": z.crime_rate,
            "police_dist_m": z.police_dist_m,
            "store_count": z.store_count,
            "bell_dist_m": z.bell_dist_m,
        }
        for z in zones
    ]
    scored = compute_safety_scores(records, period=period)
    return {r["dong_code"]: r["safety_score"] for r in scored}
