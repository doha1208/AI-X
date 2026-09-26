from dataclasses import replace

import pytest

from app.services.scoring_profile import DEFAULT_SCORING_PROFILE, ScoringProfile, validate_profile


def test_default_profile_preserves_day_and_night_priorities():
    profile = DEFAULT_SCORING_PROFILE

    assert profile.weights["day"]["cctv_count"] > profile.weights["day"]["streetlight_count"]
    assert profile.weights["night"]["streetlight_count"] > profile.weights["night"]["cctv_count"]
    assert profile.unknown_score == 50.0


def test_default_profile_adds_accident_distance_without_rejecting_legacy_profiles():
    assert "accident_dist_m" in DEFAULT_SCORING_PROFILE.weights["day"]

    legacy_weights = {
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
    validate_profile(ScoringProfile(version="legacy-v1", weights=legacy_weights, unknown_score=50.0))


def test_profile_rejects_a_period_weight_sum_other_than_one():
    invalid = replace(
        DEFAULT_SCORING_PROFILE,
        weights={
            **DEFAULT_SCORING_PROFILE.weights,
            "day": {**DEFAULT_SCORING_PROFILE.weights["day"], "cctv_count": 0.26},
        },
    )

    with pytest.raises(ValueError, match="합계"):
        validate_profile(invalid)


def test_profile_rejects_negative_factor_weight():
    invalid = replace(
        DEFAULT_SCORING_PROFILE,
        weights={
            **DEFAULT_SCORING_PROFILE.weights,
            "night": {**DEFAULT_SCORING_PROFILE.weights["night"], "bell_dist_m": -0.15},
        },
    )

    with pytest.raises(ValueError, match="0 이상"):
        validate_profile(invalid)


def test_profile_rejects_unknown_factor_and_invalid_neutral_score():
    invalid_factor = replace(
        DEFAULT_SCORING_PROFILE,
        weights={
            **DEFAULT_SCORING_PROFILE.weights,
            "day": {**DEFAULT_SCORING_PROFILE.weights["day"], "unknown_factor": 0.0},
        },
    )
    invalid_score = replace(DEFAULT_SCORING_PROFILE, unknown_score=101.0)

    with pytest.raises(ValueError, match="요인"):
        validate_profile(invalid_factor)
    with pytest.raises(ValueError, match="0~100"):
        validate_profile(invalid_score)
