"""Evaluate a clipped walking area and one location from the same prepared snapshot."""
from dataclasses import dataclass
from datetime import datetime

from shapely import points as geo_points
from shapely.geometry import Point

from app.services.facility_assessment import FacilityAssessment, LocalFacilityEvidence, assess_facility_samples, assess_local_facilities
from app.services.poi_factors import to_meters
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_sources import EnvironmentIndex, coverage_known_mask
from app.services.spot_report import nearest_havens
from app.services.time_period import KST, Period
from app.services.walk_environment_samples import sample_area_walk_scope
from app.services.zone_environment_summaries import _common_scope_factors


@dataclass
class AreaEnvironmentReport:
    area_environment: dict[Period, FacilityAssessment] | None
    local_environment: LocalFacilityEvidence | None
    facility_observations: dict
    artifact_version: str | None
    status: str
    unavailable_reason: str | None
    havens: list[dict]
    counts: dict | None = None


def _observed_counts(indexes: EnvironmentIndex, lat: float, lng: float, radius_m: float) -> dict:
    here = to_meters([(lat, lng)])[0]
    center = Point(here[1], here[0])
    location = geo_points([center.coords[0]])
    scope = center.buffer(radius_m, quad_segs=16)
    observations = {}
    for key, factor in (("cctv", "cctv"), ("lighting", "lighting"), ("bell", "bell"),
                        ("store", "open_store"), ("store_with_published_hours", "open_store")):
        schedule_only = key == "store_with_published_hours"
        points, sources = set(), {}
        complete = not schedule_only and bool(coverage_known_mask(indexes, factor, location, radius_m)[0])
        for entry in indexes.sources:
            source = entry.source
            if source.factor != factor or (schedule_only and source.schedule_status != "published_schedule"):
                continue
            hits = entry.tree.query_ball_point(here, radius_m) if entry.tree is not None else []
            if not hits and not (entry.coverage is not None and source.eligible() and entry.coverage.intersects(scope)):
                continue
            points.update(source.points[i] for i in hits)
            sources[source.source_id] = {"version": source.sha256, "url": source.source_url or None}
        observations[key] = {"count": len(points) if points or complete else None,
                             "coverage": "verified_inventory" if complete else "partial" if points else "unknown",
                             "sources": sources}
    return observations


def assess_area_environment(*, snapshot, lat: float, lng: float, radius_m: float,
                            at: datetime | None = None) -> AreaEnvironmentReport:
    moment = at or datetime.now(KST)
    moment = moment.replace(tzinfo=KST) if moment.tzinfo is None else moment.astimezone(KST)
    artifact = snapshot.artifact if snapshot is not None else None
    indexes = artifact.environment_index if artifact is not None else None
    version = artifact.version if artifact is not None else None
    havens = nearest_havens(indexes, lat, lng, at=moment)
    if indexes is None:
        return AreaEnvironmentReport(None, None, {}, version, "pending", "facility_artifact_pending", havens)

    policy = EnvironmentPolicy()
    local = assess_local_facilities((lat, lng), at=moment, policy=policy, indexes=indexes, artifact_version=version)
    observed = _observed_counts(indexes, lat, lng, radius_m)
    counts = {"cctv": observed["cctv"]["count"], "lights": observed["lighting"]["count"], "convenience": None}
    if artifact.schema_version != 4 or artifact.walk_environment_index is None:
        return AreaEnvironmentReport(None, local, observed, version, "pending", "area_artifact_pending", havens, counts)
    try:
        scope = sample_area_walk_scope(artifact.walk_environment_index, lat=lat, lng=lng, radius_m=radius_m, step_m=policy.step_m)
    except ValueError as exc:
        if str(exc) != "walk_sample_limit_exceeded":
            raise
        return AreaEnvironmentReport(None, local, observed, version, "unavailable", str(exc), havens, counts)

    results = {}
    for period, hour in (("day", 12), ("night", 23)):
        reference = moment.replace(hour=hour, minute=0, second=0, microsecond=0)
        common = _common_scope_factors(scope.geometry, indexes=indexes, policy=policy, period=period)
        excluded = {factor: "verified_complete_coverage_required" for factor in policy.active_factors(period) if factor not in common}
        results[period] = assess_facility_samples(
            scope.samples, scope="area", at=reference, reference_at=reference, policy=policy, indexes=indexes,
            common_factors=common, excluded_factors=excluded, artifact_version=version,
        )
    statuses = {value.status for value in results.values()}
    status = statuses.pop() if len(statuses) == 1 else "degraded"
    reason = results["day"].unavailable_reason if status == "unavailable" else None
    return AreaEnvironmentReport(results, local, observed, version, status, reason, havens, counts)
