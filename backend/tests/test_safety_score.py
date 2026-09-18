from app.services.safety_score import compute_safety_scores


def test_night_weights_favor_streetlight_over_cctv():
    # cctv-강세 동 vs streetlight-강세 동: day는 A가 우세, night는 B가 우세해야 함
    records_a = [
        {"dong_code": "A", "cctv_count": 100, "streetlight_count": 0, "crime_count": 0},
        {"dong_code": "B", "cctv_count": 0, "streetlight_count": 100, "crime_count": 0},
    ]
    day = {
        r["dong_code"]: r["safety_score"]
        for r in compute_safety_scores([dict(r) for r in records_a], period="day")
    }
    night = {
        r["dong_code"]: r["safety_score"]
        for r in compute_safety_scores([dict(r) for r in records_a], period="night")
    }

    assert day["A"] > day["B"]
    assert night["B"] > night["A"]


def test_default_period_matches_existing_day_weights():
    records = [{"dong_code": "X", "cctv_count": 40, "streetlight_count": 80, "crime_count": 2}]
    default = compute_safety_scores([dict(r) for r in records])
    explicit_day = compute_safety_scores([dict(r) for r in records], period="day")
    assert default[0]["safety_score"] == explicit_day[0]["safety_score"]
