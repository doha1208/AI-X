import io
import urllib.error

import pytest

from scripts import ingest_public_data as ing
from scripts.ingest_public_data import resolve_crime_by_gu


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, outcomes):
    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return _Resp(outcome)

    monkeypatch.setattr(ing.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(ing.time, "sleep", lambda _s: None)
    return calls


def test_fetch_json_retries_transient_errors_then_succeeds(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [urllib.error.URLError("boom"), TimeoutError(), b'{"ok": 1}'])
    assert ing.fetch_json_with_retry("http://x") == {"ok": 1}
    assert len(calls) == 3


def test_fetch_json_raises_after_max_attempts(monkeypatch):
    calls = _patch_urlopen(monkeypatch, [urllib.error.URLError("boom")] * ing.MAX_ATTEMPTS)
    with pytest.raises(urllib.error.URLError):
        ing.fetch_json_with_retry("http://x")
    assert len(calls) == ing.MAX_ATTEMPTS


def test_exact_gu_name_uses_its_own_total():
    assert resolve_crime_by_gu({"강남구": 500}, {"강남구"}) == {"강남구": 500}


def test_city_total_is_split_across_its_districts():
    # 경찰청 통계는 시 단위(수원시), 카카오는 구 단위(수원시 장안구)로 준다.
    crime = {"수원시": 400}
    gus = {"수원시 장안구", "수원시 권선구", "수원시 팔달구", "수원시 영통구"}
    assert resolve_crime_by_gu(crime, gus) == {gu: 100 for gu in gus}


def test_city_without_districts_keeps_full_total():
    assert resolve_crime_by_gu({"평택시": 300}, {"평택시"}) == {"평택시": 300}


def test_unknown_region_is_left_out_not_zero():
    # 통계에 없는 지역을 0으로 채우면 "가장 안전"으로 오인된다 — 결과에서 빼서 호출부가 알게 한다.
    assert resolve_crime_by_gu({"강남구": 500}, {"강남구", "알수없는구"}) == {"강남구": 500}
