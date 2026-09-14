def compute_safety_score(cctv_count: int, streetlight_count: int, crime_count: int) -> float:
    """0~100 안전 지수. 높을수록 안전.

    ponytail: 단순 가중합 MVP 공식, 지역 간 상대 비교용 min-max 정규화로 고도화 필요.
    """
    raw = cctv_count * 0.5 + streetlight_count * 0.2 - crime_count * 3
    return max(0.0, min(100.0, 50 + raw))
