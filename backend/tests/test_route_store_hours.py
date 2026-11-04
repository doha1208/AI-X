import pytest

from scripts import collect_route_store_hours as hours


def test_keeps_published_hours_without_inventing_weekdays_or_staffing():
    place = hours.normalize_place({"CODE": "1", "TITLE": "금촌점", "ADDRESS": "경기도 파주시", "LATITUDE": "37.75", "LONGITUDE": "126.77", "START_HHMM": "0700", "END_HHMM": "2300", "SVR_24": 0, "SVR_AUTO": 0})
    assert place["hours_status"] == "published_schedule"
    assert place["published_hours"] == ["07:00", "23:00"]
    assert place["weekdays"] is None and place["staffed"] is None


def test_midnight_placeholders_are_not_assumed_twenty_four_hours():
    place = hours.normalize_place({"CODE": "1", "START_HHMM": "0000", "END_HHMM": "0000", "SVR_24": 0})
    assert place["hours_status"] == "unknown"
    assert place["published_hours"] is None


def test_twenty_four_hours_does_not_imply_staffed():
    place = hours.normalize_place({"CODE": "1", "SVR_24": 1, "SVR_AUTO": 1})
    assert place["published_hours"] == ["00:00", "24:00"]
    assert place["unmanned_capable"] is True and place["staffed"] is None


def test_store_hours_pagination_rejects_missing_or_duplicate_rows():
    pages = {1: {"error": 0, "count": 3, "data": [{"CODE": "1"}, {"CODE": "2"}]}, 2: {"error": 0, "count": 3, "data": []}}
    with pytest.raises(ValueError, match="incomplete"):
        hours.collect_pages(lambda page: pages[page])


def test_store_hours_pagination_fetches_all_advertised_rows():
    pages = {1: {"error": 0, "count": 3, "data": [{"CODE": "1"}, {"CODE": "2"}]}, 2: {"error": 0, "count": 3, "data": [{"CODE": "3"}]}}
    assert len(hours.collect_pages(lambda page: pages[page])) == 3
