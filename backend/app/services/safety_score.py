from app.services.scoring_profile import (
    DEFAULT_SCORING_PROFILE,
    Period,
    ScoringProfile,
    validate_profile,
)
from app.services.dong_area import load_dong_areas_km2

# 값이 작을수록 안전한 요소(1만 명당 범죄율, 가장 가까운 경찰서·비상벨까지의 거리).
# accident_dist_m은 반대다 — 사고다발지역은 가까울수록 위험하므로 멀수록(값이 클수록) 안전하다.
_LOWER_IS_SAFER = {"crime_rate", "police_dist_m", "bell_dist_m"}

# 이 값이 바뀌면 동일한 원시 데이터와 가중치라도 점수 의미가 달라진다. 경로 산출물
# fingerprint에 포함해 이전 계산 방식의 그래프가 최신으로 오인되지 않게 한다.
SCORING_SEMANTICS_VERSION = "facility-density-v3-exclude-unsubmitted"

# 행정동 크기에 따라 자연스럽게 커지는 원시 개수. 점수 계산에서는 km²당 밀도로
# 변환하되 DB와 API 내부 원본 값은 그대로 보존한다.
_AREA_DENSITY_FACTORS = {"cctv_count", "streetlight_count", "store_count", "night_floating_pop"}


# 시·군·구의 동당 평균 보안등 수가 이보다 적으면 그 지역은 데이터를 사실상 못 올린 곳으로 본다.
# (전체 동의 중앙값은 수백 개 — 20개 미만이면 실제로 가로등이 없다기보다 미제출일 가능성이 크다.)
MIN_LIGHTS_PER_DONG = 20
# CCTV·비상벨은 시 단위로 공공데이터를 올린다. 동당 10개 미만인 시는 미제출로 본다 — 경기도에서
# 제출한 시는 동당 CCTV 34대·비상벨 15개 이상이고, 안 올린 시(화성·부천·광명 등)는 1~9개라 갈린다.
MIN_SUBMITTED_PER_DONG = 10
CITY_PREFIX_LEN = 4  # dong_code 앞 4자리 = 시·군 (수원시 장안구·권선구 등 구를 하나로 묶는다)

# 요소 -> 그 요소의 데이터를 받았는지 표시하는 레코드 키. False면 그 동은 이 요소를 빼고 계산한다.
_SUBMITTED_FLAGS = {"streetlight_count": "lights_known", "cctv_count": "cctv_known", "bell_dist_m": "bell_known"}


def flag_unsubmitted(
    records: list[dict],
    counts: dict[str, float],
    flag_key: str,
    min_per_dong: float = MIN_SUBMITTED_PER_DONG,
    prefix_len: int = CITY_PREFIX_LEN,
) -> list[str]:
    """시설 수(counts: dong_code -> 개수)가 동당 min_per_dong 미만인 지역의 동에 flag_key=False를 표시한다.

    실제로 시설이 없다기보다 지자체가 공공데이터에 올리지 않은 경우라, 0개로 계산하면 부당하게 깎인다.
    반환값은 표시된 지역 코드(dong_code 앞 prefix_len자리). 나머지 동은 True.
    """
    by_area: dict[str, list[str]] = {}
    for record in records:
        by_area.setdefault(record["dong_code"][:prefix_len], []).append(record["dong_code"])
    flagged = {
        area
        for area, codes in by_area.items()
        if sum(counts.get(code, 0) for code in codes) / len(codes) < min_per_dong
    }
    for record in records:
        record[flag_key] = record["dong_code"][:prefix_len] not in flagged
    return sorted(flagged)


def flag_unknown_streetlights(records: list[dict]) -> list[str]:
    """보안등이 너무 적은 시·군·구(dong_code 앞 5자리)의 동들에 lights_known=False를 표시한다."""
    counts = {r["dong_code"]: r["streetlight_count"] for r in records}
    return flag_unsubmitted(records, counts, "lights_known", MIN_LIGHTS_PER_DONG, prefix_len=5)


def _factor_value(record: dict, factor: str, area_by_dong: dict[str, float] | None = None):
    """요소 값. 데이터를 못 받은 지역(lights_known·cctv_known·bell_known=False)의 그 요소는 None(모름)이다."""
    flag = _SUBMITTED_FLAGS.get(factor)
    if flag and record.get(flag) is False:
        return None
    value = record.get(factor)
    if value is None or factor not in _AREA_DENSITY_FACTORS or area_by_dong is None:
        return value
    area_km2 = area_by_dong.get(record.get("dong_code"))
    if not area_km2 or area_km2 <= 0:
        return None
    return value / area_km2


def _normalize(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100))


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (percentile / 100) * (len(sorted_values) - 1)
    lower_index, upper_index = int(index), min(int(index) + 1, len(sorted_values) - 1)
    return sorted_values[lower_index] + (sorted_values[upper_index] - sorted_values[lower_index]) * (index - lower_index)


_OUTLIER_CLIP_PERCENTILE = 5


def compute_safety_scores(
    records: list[dict],
    period: Period = "day",
    profile: ScoringProfile | None = None,
    area_by_dong: dict[str, float] | None = None,
) -> list[dict]:
    """요소별 수치(cctv_count/streetlight_count/crime_rate/police_dist_m/store_count)를
    가진 레코드 목록을 받아 0~100 안전 지수(safety_score)를 채워 반환한다. 높을수록 안전.

    같은 동 집합(예: 서울 전체) 안에서의 상대 비교용 min-max 정규화.
    CCTV/보안등/상점은 area_by_dong이 주어지면 km²당 밀도로 비교하며 많을수록,
    범죄율(1만 명당)·경찰서 거리는 작을수록 점수가 높다.
    period(day/night)에 따라 요소별 가중치 배분이 달라진다.
    키가 없거나 값이 None인 요소(데이터를 못 받은 지역)는 정규화 범위에서도, 그 동의 점수
    계산에서도 빼고 남은 요소의 비중만으로 다시 나눈다 — 모르는 값을 중간 점수로 지어내지 않는다.
    """
    if not records:
        return records

    profile = profile or DEFAULT_SCORING_PROFILE
    validate_profile(profile)
    weights = profile.weights[period]
    bounds = {}
    for factor in weights:
        known = sorted(
            v for v in (_factor_value(r, factor, area_by_dong) for r in records) if v is not None
        )
        if not known:
            bounds[factor] = (0, 0)
            continue
        lower = _percentile(known, _OUTLIER_CLIP_PERCENTILE)
        upper = _percentile(known, 100 - _OUTLIER_CLIP_PERCENTILE)
        bounds[factor] = (lower, upper) if upper > lower else (known[0], known[-1])

    for record in records:
        total = known_weight = 0.0
        for factor, weight in weights.items():
            value = _factor_value(record, factor, area_by_dong)
            if value is None:
                continue  # 데이터가 없는 요소는 점수를 지어내지 않고 계산에서 뺀다
            score = _normalize(value, *bounds[factor])
            score = 100 - score if factor in _LOWER_IS_SAFER else score
            total += weight * score
            known_weight += weight
        # 남은 요소의 비중만으로 다시 나눈다. 모든 요소를 모르는 동은 실데이터에 없지만, 있으면 중립값.
        record["safety_score"] = round(total / known_weight, 1) if known_weight else profile.unknown_score
    return records


def compute_zone_period_scores(
    zones: list, period: Period = "day", profile: ScoringProfile | None = None
) -> dict[str, float]:
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
            "cctv_known": getattr(z, "cctv_known", None) is not False,
            "bell_known": getattr(z, "bell_known", None) is not False,
            "crime_rate": z.crime_rate,
            "police_dist_m": z.police_dist_m,
            "store_count": z.store_count,
            "bell_dist_m": z.bell_dist_m,
            "accident_dist_m": getattr(z, "accident_dist_m", None),
            "night_floating_pop": getattr(z, "night_floating_pop", None),
        }
        for z in zones
    ]
    scored = compute_safety_scores(
        records,
        period=period,
        profile=profile,
        area_by_dong=load_dong_areas_km2(),
    )
    return {r["dong_code"]: r["safety_score"] for r in scored}
