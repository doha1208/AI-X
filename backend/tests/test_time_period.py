from datetime import datetime

from app.services.time_period import KST, period_for


def test_late_night_is_night():
    assert period_for(datetime(2026, 1, 1, 23, 0, tzinfo=KST)) == "night"


def test_early_morning_is_night():
    assert period_for(datetime(2026, 1, 1, 5, 59, tzinfo=KST)) == "night"


def test_boundary_6am_is_day():
    assert period_for(datetime(2026, 1, 1, 6, 0, tzinfo=KST)) == "day"


def test_noon_is_day():
    assert period_for(datetime(2026, 1, 1, 12, 0, tzinfo=KST)) == "day"


def test_naive_datetime_assumed_kst():
    assert period_for(datetime(2026, 1, 1, 23, 0)) == "night"
