"""Privacy-safe route telemetry and Prometheus rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fastapi import Response
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

RouteMode = Literal["safety_weighted", "tmap", "straight_line", "failed"]
FallbackReason = Literal[
    "none", "artifact_unavailable", "safe_route_unavailable", "tmap_unavailable", "safety_zones_unavailable"
]
RouteOutcome = Literal["success", "safety_zones_unavailable"]
TmapFailureReason = Literal["http_error", "invalid_response"]
CacheResult = Literal["hit", "miss"]


@dataclass
class RouteMetrics:
    registry: CollectorRegistry
    duration: Histogram
    requests: Counter
    tmap_failures: Counter
    cache_results: Counter

    def record_route(
        self, *, status_code: int, duration_seconds: float, mode: RouteMode, fallback_reason: FallbackReason
    ) -> None:
        outcome: RouteOutcome = "success" if status_code < 400 else "safety_zones_unavailable"
        self.duration.labels(outcome=outcome).observe(duration_seconds)
        self.requests.labels(mode=mode, fallback_reason=fallback_reason).inc()

    def record_tmap_failure(self, reason: TmapFailureReason) -> None:
        self.tmap_failures.labels(reason=reason).inc()

    def record_route_cache(self, result: CacheResult) -> None:
        self.cache_results.labels(result=result).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)


def create_metrics(registry: CollectorRegistry | None = None) -> RouteMetrics:
    registry = registry or CollectorRegistry()
    return RouteMetrics(
        registry=registry,
        duration=Histogram("route_duration_seconds", "Route request duration", ["outcome"], registry=registry),
        requests=Counter("route_requests", "Route request outcomes", ["mode", "fallback_reason"], registry=registry),
        tmap_failures=Counter("tmap_failures", "Tmap failures", ["reason"], registry=registry),
        cache_results=Counter("route_result_cache", "Route result cache outcomes", ["result"], registry=registry),
    )


metrics = create_metrics()


def metrics_response() -> Response:
    return Response(metrics.render(), media_type=CONTENT_TYPE_LATEST)
