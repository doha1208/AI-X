from datetime import datetime

import pytest
from pydantic import ValidationError

from app.core.config import Settings, validate_runtime_settings
from app.core.security import create_access_token
from app.schemas.safety import RouteRequest
from app.services.route_request_limit import RouteRequestGate
from app.api.safety import _authenticated_user_id, _client_ip
from starlette.requests import Request


def _request(client_ip: str, headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "client": (client_ip, 12345),
            "headers": [(name.encode(), value.encode()) for name, value in (headers or {}).items()],
        }
    )


def test_route_request_accepts_nationwide_coordinates_within_walking_limit():
    request = RouteRequest(
        start_lat=35.1796,
        start_lng=129.0756,
        end_lat=35.2150,
        end_lng=129.0900,
        at=datetime(2026, 9, 25, 21, 0),
    )

    assert request.start_lat == 35.1796
    assert request.end_lat == 35.2150


def test_route_request_rejects_straight_line_distance_over_ten_kilometers():
    with pytest.raises(ValidationError, match="10km"):
        RouteRequest(
            start_lat=37.5000,
            start_lng=127.0000,
            end_lat=37.6000,
            end_lng=127.0000,
        )


def test_production_rejects_default_jwt_secret():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_runtime_settings(Settings(app_env="production"))


def test_development_allows_default_jwt_secret_for_local_startup():
    validate_runtime_settings(Settings(app_env="development"))


def test_route_request_gate_rejects_requests_above_the_ip_limit():
    gate = RouteRequestGate(
        max_concurrent=2,
        ip_requests_per_minute=2,
        ip_burst=2,
        user_requests_per_minute=10,
        user_burst=10,
    )

    first = gate.acquire(client_ip="203.0.113.10", user_id=None, now=0.0)
    second = gate.acquire(client_ip="203.0.113.10", user_id=None, now=0.0)
    first.release()
    second.release()
    denied = gate.acquire(client_ip="203.0.113.10", user_id=None, now=0.0)

    assert denied.granted is False
    assert denied.retry_after_seconds == 30


def test_route_request_gate_rejects_when_global_route_slots_are_busy():
    gate = RouteRequestGate(
        max_concurrent=2,
        ip_requests_per_minute=10,
        ip_burst=10,
        user_requests_per_minute=10,
        user_burst=10,
    )

    first = gate.acquire(client_ip="203.0.113.10", user_id=None, now=0.0)
    second = gate.acquire(client_ip="203.0.113.11", user_id=None, now=0.0)
    denied = gate.acquire(client_ip="203.0.113.12", user_id=None, now=0.0)

    assert first.granted is True
    assert second.granted is True
    assert denied.granted is False
    assert denied.retry_after_seconds == 1

    first.release()
    second.release()


def test_route_request_gate_keeps_the_number_of_tracked_clients_bounded():
    gate = RouteRequestGate(
        max_concurrent=2,
        ip_requests_per_minute=10,
        ip_burst=10,
        user_requests_per_minute=10,
        user_burst=10,
        max_tracked_buckets=2,
    )

    for client_ip in ("203.0.113.10", "203.0.113.11", "203.0.113.12"):
        admission = gate.acquire(client_ip=client_ip, user_id=None, now=0.0)
        admission.release()

    assert len(gate._buckets) == 2


def test_route_request_gate_applies_the_user_limit_separately_from_ip_limit():
    gate = RouteRequestGate(
        max_concurrent=2,
        ip_requests_per_minute=10,
        ip_burst=10,
        user_requests_per_minute=1,
        user_burst=1,
    )

    first = gate.acquire(client_ip="203.0.113.10", user_id="member@example.com", now=0.0)
    first.release()
    denied = gate.acquire(client_ip="203.0.113.11", user_id="member@example.com", now=0.0)

    assert denied.granted is False
    assert denied.retry_after_seconds == 60


def test_untrusted_direct_request_cannot_choose_its_ip_with_forwarded_for(monkeypatch):
    from app.api import safety as safety_api

    monkeypatch.setattr(safety_api.settings, "trusted_proxy_ips", "127.0.0.1")
    request = _request("203.0.113.10", {"x-forwarded-for": "198.51.100.25"})

    assert _client_ip(request) == "203.0.113.10"


def test_trusted_proxy_uses_the_first_forwarded_client_ip(monkeypatch):
    from app.api import safety as safety_api

    monkeypatch.setattr(safety_api.settings, "trusted_proxy_ips", "127.0.0.1")
    request = _request("127.0.0.1", {"x-forwarded-for": "198.51.100.25, 127.0.0.1"})

    assert _client_ip(request) == "198.51.100.25"


def test_access_token_subject_is_used_for_the_user_limit():
    request = _request(
        "203.0.113.10",
        {"authorization": f"Bearer {create_access_token('member@example.com')}"},
    )

    assert _authenticated_user_id(request) == "member@example.com"
