from app.models.safety_zone import SafetyZone
from app.services.scoring_profile import DEFAULT_SCORING_PROFILE, ScoringProfile
from app.services.safety_score import (
    compute_safety_scores,
    compute_zone_period_scores,
    flag_unknown_streetlights,
    flag_unsubmitted,
)


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


def test_closer_police_station_raises_score():
    records = [
        {"dong_code": "NEAR", "cctv_count": 10, "streetlight_count": 10, "crime_count": 5, "police_dist_m": 200},
        {"dong_code": "FAR", "cctv_count": 10, "streetlight_count": 10, "crime_count": 5, "police_dist_m": 2500},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records)}
    assert scores["NEAR"] > scores["FAR"]


def test_lower_crime_rate_raises_score():
    records = [
        {"dong_code": "SAFE", "cctv_count": 10, "streetlight_count": 10, "crime_rate": 40},
        {"dong_code": "RISKY", "cctv_count": 10, "streetlight_count": 10, "crime_rate": 200},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records)}
    assert scores["SAFE"] > scores["RISKY"]


def test_raw_crime_count_no_longer_drives_the_score():
    # 건수가 아니라 1만 명당 범죄율로 비교한다 — 큰 도시(건수 많음)가 자동으로 불리하지 않다.
    records = [
        {"dong_code": "BIG", "cctv_count": 10, "streetlight_count": 10, "crime_count": 9000, "crime_rate": 50},
        {"dong_code": "SMALL", "cctv_count": 10, "streetlight_count": 10, "crime_count": 100, "crime_rate": 50},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records)}
    assert scores["BIG"] == scores["SMALL"]


def test_unknown_streetlight_count_is_excluded_not_dark():
    # 보안등 데이터를 못 받은 동(None)은 "0개=깜깜함"으로 보지 않고 보안등을 빼고 계산한다
    records = [
        {"dong_code": "LIT", "cctv_count": 10, "streetlight_count": 500, "crime_rate": 50},
        {"dong_code": "DARK", "cctv_count": 10, "streetlight_count": 0, "crime_rate": 50},
        {"dong_code": "UNKNOWN", "cctv_count": 10, "streetlight_count": None, "crime_rate": 50},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records, period="night")}
    assert scores["DARK"] < scores["UNKNOWN"] < scores["LIT"]


def test_unknown_values_do_not_stretch_the_normalisation_range():
    # None은 min/max 계산에서 빠져야 한다 — 남은 동들의 점수가 그대로여야 함
    with_unknown = compute_safety_scores(
        [
            {"dong_code": "A", "cctv_count": 10, "streetlight_count": 100, "crime_rate": 50},
            {"dong_code": "B", "cctv_count": 10, "streetlight_count": 0, "crime_rate": 50},
            {"dong_code": "U", "cctv_count": 10, "streetlight_count": None, "crime_rate": 50},
        ]
    )
    without = compute_safety_scores(
        [
            {"dong_code": "A", "cctv_count": 10, "streetlight_count": 100, "crime_rate": 50},
            {"dong_code": "B", "cctv_count": 10, "streetlight_count": 0, "crime_rate": 50},
        ]
    )
    by_code = {r["dong_code"]: r["safety_score"] for r in with_unknown}
    assert by_code["A"] == without[0]["safety_score"]
    assert by_code["B"] == without[1]["safety_score"]


def test_zone_scores_exclude_missing_lower_is_safer_inputs():
    zones = [
        SafetyZone(
            dong_code="KNOWN",
            dong_name="Known",
            lat=37.5,
            lng=127.0,
            crime_rate=50,
            police_dist_m=300,
            bell_dist_m=100,
        ),
        SafetyZone(
            dong_code="UNKNOWN",
            dong_name="Unknown",
            lat=37.51,
            lng=127.01,
            crime_rate=None,
            police_dist_m=None,
            bell_dist_m=None,
        ),
        SafetyZone(
            dong_code="RISKY",
            dong_name="Risky",
            lat=37.52,
            lng=127.02,
            crime_rate=200,
            police_dist_m=3000,
            bell_dist_m=1200,
        ),
    ]

    scores = compute_zone_period_scores(zones)

    assert scores["RISKY"] < scores["UNKNOWN"] < scores["KNOWN"]


def test_safety_zone_persists_missing_lower_is_safer_inputs_as_null():
    table = SafetyZone.__table__

    assert table.c.crime_rate.nullable is True
    assert table.c.police_dist_m.nullable is True
    assert table.c.bell_dist_m.nullable is True


def test_absent_factor_is_excluded_instead_of_known_zero():
    rows = [
        {"dong_code": "KNOWN", "crime_rate": 50},
        {"dong_code": "MISSING"},
        {"dong_code": "RISKY", "crime_rate": 200},
    ]

    scores = {row["dong_code"]: row["safety_score"] for row in compute_safety_scores(rows)}

    assert scores["RISKY"] < scores["MISSING"] < scores["KNOWN"]


def test_city_with_almost_no_lights_is_flagged_as_unknown_not_dark():
    records = [
        {"dong_code": "1111010100", "streetlight_count": 300},  # 정상 지역
        {"dong_code": "1111010200", "streetlight_count": 250},
        {"dong_code": "1117010100", "streetlight_count": 0},  # 데이터를 못 올린 시군구
        {"dong_code": "1117010200", "streetlight_count": 3},
    ]

    flagged = flag_unknown_streetlights(records)

    assert flagged == ["11170"]
    assert [r["lights_known"] for r in records] == [True, True, False, False]


def test_flagged_dongs_are_scored_without_lights():
    records = [
        {"dong_code": "1111010100", "cctv_count": 10, "streetlight_count": 500, "crime_rate": 50, "lights_known": True},
        {"dong_code": "1111010200", "cctv_count": 10, "streetlight_count": 0, "crime_rate": 50, "lights_known": True},
        {"dong_code": "1117010100", "cctv_count": 10, "streetlight_count": 0, "crime_rate": 50, "lights_known": False},
    ]

    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records, period="night")}

    assert scores["1111010200"] < scores["1117010100"] < scores["1111010100"]


def test_missing_factor_weight_is_spread_over_known_factors_only():
    # 모르는 요소는 중간 점수를 받지 않는다 — 아는 요소의 점수만 비중대로 다시 나눠 평균낸다.
    records = [
        {"dong_code": "LOW", "cctv_count": 0, "crime_rate": 100, "night_floating_pop": 0},
        {"dong_code": "HIGH", "cctv_count": 100, "crime_rate": 0, "night_floating_pop": 1000},
        {"dong_code": "NO_POP", "cctv_count": 100, "crime_rate": 0, "night_floating_pop": None},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records, period="night")}

    # 유동인구를 모르는 동도 아는 요소(CCTV·범죄율)가 모두 최고라면 만점이다 — 50점이 섞여 깎이지 않는다.
    assert scores["NO_POP"] == scores["HIGH"] == 100.0


def test_closer_bell_raises_score():
    records = [
        {"dong_code": "NEAR", "cctv_count": 10, "streetlight_count": 10, "crime_rate": 50, "bell_dist_m": 50},
        {"dong_code": "FAR", "cctv_count": 10, "streetlight_count": 10, "crime_rate": 50, "bell_dist_m": 900},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records)}
    assert scores["NEAR"] > scores["FAR"]


def test_further_from_accident_hotspot_raises_score():
    records = [
        {"dong_code": "NEAR", "cctv_count": 10, "streetlight_count": 10, "crime_rate": 50, "accident_dist_m": 50},
        {"dong_code": "FAR", "cctv_count": 10, "streetlight_count": 10, "crime_rate": 50, "accident_dist_m": 1400},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records)}
    assert scores["FAR"] > scores["NEAR"]


def test_more_shops_raise_score():
    records = [
        {"dong_code": "BUSY", "cctv_count": 10, "streetlight_count": 10, "crime_count": 5, "store_count": 300},
        {"dong_code": "QUIET", "cctv_count": 10, "streetlight_count": 10, "crime_count": 5, "store_count": 3},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records)}
    assert scores["BUSY"] > scores["QUIET"]


def test_records_without_new_factors_still_score():
    # police_dist_m/store_count가 없는 기존 레코드도 있는 요소만으로 계산돼야 한다
    scored = compute_safety_scores([{"dong_code": "X", "cctv_count": 1, "streetlight_count": 1, "crime_count": 1}])
    assert 0 <= scored[0]["safety_score"] <= 100


def test_default_period_matches_existing_day_weights():
    records = [{"dong_code": "X", "cctv_count": 40, "streetlight_count": 80, "crime_count": 2}]
    default = compute_safety_scores([dict(r) for r in records])
    explicit_day = compute_safety_scores([dict(r) for r in records], period="day")
    assert default[0]["safety_score"] == explicit_day[0]["safety_score"]


def test_a_single_outlier_does_not_crush_everyone_else_near_zero():
    # 캡이 없는 요소(cctv_count)에 극단값 하나가 섞여도, 나머지 동들끼리는 여전히
    # 값 차이만큼 점수가 벌어져야 한다 — min-max 폭 전체가 그 값에 맞춰지면 안 된다.
    normal_records = [
        {"dong_code": f"N{i}", "cctv_count": i * 5, "streetlight_count": 10, "crime_rate": 50}
        for i in range(20)  # 0, 5, 10, ..., 95
    ]
    outlier = {"dong_code": "OUTLIER", "cctv_count": 5000, "streetlight_count": 10, "crime_rate": 50}

    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(normal_records + [outlier])}

    # 정상 범위 안의 가장 큰 값(N19=95)이 극단값 하나 때문에 0 근처로 뭉개지지 않아야 한다.
    assert scores["N19"] > scores["N0"] + 10


def test_facility_counts_are_compared_as_density_when_area_is_available():
    rows = [
        {
            "dong_code": "LARGE",
            "cctv_count": 100,
            "streetlight_count": 100,
            "store_count": 100,
        },
        {
            "dong_code": "SMALL",
            "cctv_count": 10,
            "streetlight_count": 10,
            "store_count": 10,
        },
    ]

    scores = {
        row["dong_code"]: row["safety_score"]
        for row in compute_safety_scores(
            rows,
            area_by_dong={"LARGE": 100.0, "SMALL": 1.0},
        )
    }

    assert scores["SMALL"] > scores["LARGE"]


def test_explicit_profile_changes_the_score_weights():
    weights = {
        **DEFAULT_SCORING_PROFILE.weights,
        "day": {
            **DEFAULT_SCORING_PROFILE.weights["day"],
            "cctv_count": 0.10,
            "streetlight_count": 0.25,
        },
    }
    profile = ScoringProfile(version="streetlight-priority", weights=weights, unknown_score=50.0)
    rows = [
        {"dong_code": "CCTV", "cctv_count": 100, "streetlight_count": 0},
        {"dong_code": "LIGHT", "cctv_count": 0, "streetlight_count": 100},
    ]

    scores = {
        row["dong_code"]: row["safety_score"]
        for row in compute_safety_scores(rows, profile=profile)
    }

    assert scores["LIGHT"] > scores["CCTV"]


def test_city_that_did_not_submit_cctv_is_flagged_by_city_not_gu():
    # 화성시처럼 시 전체가 CCTV를 거의 안 올린 경우 — 시(앞 4자리) 단위로 판단한다.
    records = [
        {"dong_code": "4159010100", "cctv_count": 1},
        {"dong_code": "4159110100", "cctv_count": 0},  # 같은 화성시의 다른 구
        {"dong_code": "4146110100", "cctv_count": 60},
    ]
    counts = {r["dong_code"]: r["cctv_count"] for r in records}

    flagged = flag_unsubmitted(records, counts, "cctv_known")

    assert flagged == ["4159"]
    assert [r["cctv_known"] for r in records] == [False, False, True]


def test_unsubmitted_cctv_and_bells_are_left_out_of_the_score():
    # CCTV·비상벨을 안 올린 동은 "0대·멀다"로 깎이지 않는다 — 두 요소를 빼고 계산한다.
    base = {"streetlight_count": 100, "crime_rate": 10}
    records = [
        {"dong_code": "GOOD", **base, "cctv_count": 50, "bell_dist_m": 50},
        {"dong_code": "BAD", **base, "cctv_count": 0, "bell_dist_m": 1000},
        {"dong_code": "UNSUBMITTED", **base, "cctv_count": 0, "bell_dist_m": 1000,
         "cctv_known": False, "bell_known": False},
    ]
    scores = {r["dong_code"]: r["safety_score"] for r in compute_safety_scores(records)}

    assert scores["UNSUBMITTED"] > scores["BAD"]
