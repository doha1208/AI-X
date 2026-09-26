import asyncio

from app.core.config import settings
from app.services import tmap


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "features": [
                {"geometry": {"type": "LineString", "coordinates": [[127.0, 37.5], [127.01, 37.51]]}}
            ]
        }


class _Client:
    calls = 0

    def __init__(self, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        self.__class__.calls += 1
        return _Response()


def test_successful_tmap_route_is_reused_within_ttl(monkeypatch):
    monkeypatch.setattr(settings, "tmap_app_key", "test-key")
    monkeypatch.setattr(tmap.httpx, "AsyncClient", _Client)
    tmap._route_cache.clear()
    _Client.calls = 0

    first = asyncio.run(tmap.get_pedestrian_route(37.5, 127.0, 37.51, 127.01))
    second = asyncio.run(tmap.get_pedestrian_route(37.5, 127.0, 37.51, 127.01))

    assert first == [(37.5, 127.0), (37.51, 127.01)]
    assert second == first
    assert _Client.calls == 1
