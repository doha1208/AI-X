"""Compose prepared OSM/Tmap candidates and evaluate/rank once per request."""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time

from app.core.config import settings
from app.services.route_environment import RouteCandidate
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_rank import assess_and_select
from app.services.route_environment_sources import EnvironmentIndex
from app.services.time_period import KST


@dataclass
class EnvironmentRouteResult:
    selected: list
    comparison: object | None
    baseline_source: str
    artifact_used: bool
    osm_available: bool
    artifact_version: str | None
    evaluated_at: datetime


async def calculate_environment_routes(payload, *, runtime, tmap_provider):
    at = payload.at or datetime.now(KST)
    policy = EnvironmentPolicy()
    await asyncio.to_thread(runtime.reload_if_changed, Path(settings.route_artifact_dir), now=time.monotonic())
    snapshot = runtime.environment_snapshot()
    indexes = snapshot.artifact.environment_index if snapshot is not None else EnvironmentIndex()
    start, end = (payload.start_lat, payload.start_lng), (payload.end_lat, payload.end_lng)

    async def osm():
        if snapshot is None:
            return []
        result = await asyncio.to_thread(runtime.find_environment_candidates, start, end, at=at, policy=policy, snapshot=snapshot) or []
        return [c for c in result if len(c.points) > 1 and any(a != b for a, b in zip(c.points, c.points[1:]))]

    if payload.include_comparison:
        candidates, tmap_points = await asyncio.gather(osm(), tmap_provider(*start, *end))
    else:
        candidates = await osm()
        tmap_points = await tmap_provider(*start, *end) if not candidates else None
    # Reject degenerate provider geometries rather than advertising a zero-distance walking route.
    candidates = [c for c in candidates if len(c.points) > 1 and any(a != b for a, b in zip(c.points, c.points[1:]))]
    osm_available = bool(candidates)
    if tmap_points and len(tmap_points) > 1 and any(a != b for a, b in zip(tmap_points, tmap_points[1:])):
        candidates.append(RouteCandidate("tmap", tmap_points, "tmap"))
    if not candidates:
        return None
    general = next((c for c in candidates if c.source == "tmap"), candidates[0])
    selected, evaluated, baseline = await asyncio.to_thread(assess_and_select, candidates, baseline_id=general.candidate_id,
                                                          at=at, policy=policy, indexes=indexes)
    comparison = next((r for r in evaluated if r.candidate.source == "tmap"), None)
    return EnvironmentRouteResult(selected, comparison if payload.include_comparison else None,
                                  "tmap" if comparison else "osm_shortest", snapshot is not None, osm_available,
                                  snapshot.artifact.version if snapshot else None, at if at.tzinfo else at.replace(tzinfo=KST))
