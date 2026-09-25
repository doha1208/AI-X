"""공개 경로 API가 짧은 시간에 서버·외부 경로 서비스를 독점하지 않게 하는 제한기."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from threading import Lock
import time


@dataclass
class _TokenBucket:
    tokens: float
    updated_at: float


@dataclass
class RouteRequestAdmission:
    granted: bool
    retry_after_seconds: int | None = None
    _gate: "RouteRequestGate | None" = None
    _released: bool = False

    def release(self) -> None:
        if self.granted and not self._released and self._gate is not None:
            self._gate.release()
            self._released = True


class RouteRequestGate:
    def __init__(
        self,
        *,
        max_concurrent: int,
        ip_requests_per_minute: int,
        ip_burst: int,
        user_requests_per_minute: int,
        user_burst: int,
        max_tracked_buckets: int = 10_000,
    ) -> None:
        self.max_concurrent = max_concurrent
        self._limits = {
            "ip": (ip_requests_per_minute / 60, ip_burst),
            "user": (user_requests_per_minute / 60, user_burst),
        }
        self._max_tracked_buckets = max_tracked_buckets
        self._buckets: dict[str, _TokenBucket] = {}
        self._active = 0
        self._lock = Lock()

    def _available_tokens(self, key: str, kind: str, now: float) -> float:
        rate_per_second, capacity = self._limits[kind]
        bucket = self._buckets.get(key)
        if bucket is None:
            return float(capacity)
        elapsed = max(0.0, now - bucket.updated_at)
        return min(float(capacity), bucket.tokens + elapsed * rate_per_second)

    def _retry_after_seconds(self, available_tokens: float, kind: str) -> int:
        rate_per_second, _ = self._limits[kind]
        return max(1, ceil((1 - available_tokens) / rate_per_second))

    def _prune_buckets(self, keys: list[tuple[str, str]], now: float) -> None:
        for key, bucket in list(self._buckets.items()):
            kind = key.split(":", 1)[0]
            if self._available_tokens(key, kind, now) >= self._limits[kind][1]:
                del self._buckets[key]

        new_key_count = sum(1 for key, _ in keys if key not in self._buckets)
        overflow = len(self._buckets) + new_key_count - self._max_tracked_buckets
        if overflow > 0:
            oldest_keys = sorted(self._buckets, key=lambda key: self._buckets[key].updated_at)
            for key in oldest_keys[:overflow]:
                del self._buckets[key]

    def acquire(self, *, client_ip: str, user_id: str | None, now: float | None = None) -> RouteRequestAdmission:
        current_time = time.monotonic() if now is None else now
        keys = [(f"ip:{client_ip}", "ip")]
        if user_id:
            keys.append((f"user:{user_id}", "user"))

        with self._lock:
            if self._active >= self.max_concurrent:
                return RouteRequestAdmission(granted=False, retry_after_seconds=1)

            self._prune_buckets(keys, current_time)
            available = [(key, kind, self._available_tokens(key, kind, current_time)) for key, kind in keys]
            denied = [(kind, tokens) for _, kind, tokens in available if tokens < 1]
            if denied:
                retry_after = max(self._retry_after_seconds(tokens, kind) for kind, tokens in denied)
                return RouteRequestAdmission(granted=False, retry_after_seconds=retry_after)

            for key, _, tokens in available:
                self._buckets[key] = _TokenBucket(tokens=tokens - 1, updated_at=current_time)
            self._active += 1
            return RouteRequestAdmission(granted=True, _gate=self)

    def release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
