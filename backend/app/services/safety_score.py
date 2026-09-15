def _normalize(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100))


def compute_safety_scores(records: list[dict]) -> list[dict]:
    """cctv_count/streetlight_count/crime_count를 가진 레코드 목록을 받아
    0~100 안전 지수(safety_score)를 채워 반환한다. 높을수록 안전.

    같은 동 집합(예: 서울 전체) 안에서의 상대 비교용 min-max 정규화.
    CCTV/보안등은 많을수록, 범죄는 적을수록 점수가 높다.

    ponytail: 방범시설(CCTV 40% + 보안등 20%) : 범죄 역수(40%) 가중치는
    임시 MVP 값. 실제 체감 안전도와 맞춰보며 조정 필요.
    """
    if not records:
        return records

    cctv_vals = [r["cctv_count"] for r in records]
    light_vals = [r["streetlight_count"] for r in records]
    crime_vals = [r["crime_count"] for r in records]
    c_lo, c_hi = min(cctv_vals), max(cctv_vals)
    l_lo, l_hi = min(light_vals), max(light_vals)
    r_lo, r_hi = min(crime_vals), max(crime_vals)

    for record in records:
        cctv_score = _normalize(record["cctv_count"], c_lo, c_hi)
        light_score = _normalize(record["streetlight_count"], l_lo, l_hi)
        crime_score = 100 - _normalize(record["crime_count"], r_lo, r_hi)
        record["safety_score"] = round(cctv_score * 0.4 + light_score * 0.2 + crime_score * 0.4, 1)
    return records
