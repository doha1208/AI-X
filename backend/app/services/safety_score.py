from typing import Literal

Period = Literal["day", "night"]

# (cctv_weight, streetlight_weight, crime_weight) — 합 1.0.
# ponytail: MVP 값 — night는 CCTV(사후 확인용)보다 보안등(즉시 시야 확보)
# 비중을 높임. 실제 체감 안전도와 맞춰보며 조정 필요.
_PERIOD_WEIGHTS: dict[Period, tuple[float, float, float]] = {
    "day": (0.4, 0.2, 0.4),
    "night": (0.25, 0.35, 0.4),
}


def _normalize(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100))


def compute_safety_scores(records: list[dict], period: Period = "day") -> list[dict]:
    """cctv_count/streetlight_count/crime_count를 가진 레코드 목록을 받아
    0~100 안전 지수(safety_score)를 채워 반환한다. 높을수록 안전.

    같은 동 집합(예: 서울 전체) 안에서의 상대 비교용 min-max 정규화.
    CCTV/보안등은 많을수록, 범죄는 적을수록 점수가 높다.
    period(day/night)에 따라 방범시설 가중치 배분이 달라진다.
    """
    if not records:
        return records

    cctv_vals = [r["cctv_count"] for r in records]
    light_vals = [r["streetlight_count"] for r in records]
    crime_vals = [r["crime_count"] for r in records]
    c_lo, c_hi = min(cctv_vals), max(cctv_vals)
    l_lo, l_hi = min(light_vals), max(light_vals)
    r_lo, r_hi = min(crime_vals), max(crime_vals)
    w_cctv, w_light, w_crime = _PERIOD_WEIGHTS[period]

    for record in records:
        cctv_score = _normalize(record["cctv_count"], c_lo, c_hi)
        light_score = _normalize(record["streetlight_count"], l_lo, l_hi)
        crime_score = 100 - _normalize(record["crime_count"], r_lo, r_hi)
        record["safety_score"] = round(cctv_score * w_cctv + light_score * w_light + crime_score * w_crime, 1)
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
            "crime_count": z.crime_count,
        }
        for z in zones
    ]
    scored = compute_safety_scores(records, period=period)
    return {r["dong_code"]: r["safety_score"] for r in scored}
