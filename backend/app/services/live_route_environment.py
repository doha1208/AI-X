"""Fresh facility evidence for an existing walking polyline; never chooses another route."""
from dataclasses import asdict
from datetime import datetime, timedelta
from hashlib import sha256
import json

import numpy as np

from app.services.facility_assessment import assess_local_facilities
from app.services.poi_factors import to_meters
from app.services.route_environment import evaluate_route_cells, sample_route
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_sources import eligible_factors
from app.services.spot_report import HAVEN_MAX_M, nearest_havens
from app.services.time_period import KST, period_for


def _intervals(cells, observations, factors):
    result = {factor: [] for factor in factors}
    for cell, observation in zip(cells, observations):
        for factor in factors:
            segments = result[factor]
            state = observation.factors[factor].state
            if segments and segments[-1]["state"] == state:
                segments[-1]["end_m"] = cell.end_m
            else:
                segments.append({"start_m": cell.start_m, "end_m": cell.end_m, "state": state})
    return result


def _freshness(moment, version, indexes, cells, position, policy):
    limit = moment + timedelta(seconds=60)
    # Published schedules and service periods change on whole minutes. There is
    # at most one boundary before the 60-second cap, including overnight hours.
    boundary = moment.replace(second=0, microsecond=0) + timedelta(minutes=1)
    expires = boundary if (moment.date(), period_for(moment)) != (boundary.date(), period_for(boundary)) else limit
    schedule = []
    route_meters = to_meters([cell.midpoint for cell in cells])
    local_meters = to_meters([position])[0] if position is not None else None
    for entry in indexes.sources if indexes is not None else ():
        source = entry.source
        if (source.factor != "open_store" or entry.tree is None or not source.opening_hours
                or not source.opening_hours_evidence or not source.presence_eligible()):
            continue
        nearby = bool(np.any(entry.tree.query_ball_point(route_meters, policy.radius("open_store"), return_length=True)))
        if not nearby and local_meters is not None:
            local_radius = HAVEN_MAX_M if source.source_id == "published-hours-emart24" else policy.radius("open_store")
            nearby = bool(entry.tree.query_ball_point(local_meters, local_radius, return_length=True))
        if nearby:
            state = source.is_open(moment)
            schedule.append((source.source_id, state))
            if state != source.is_open(boundary):
                expires = min(expires, boundary)
    key = [version, policy.fingerprint(), moment.date().isoformat(), period_for(moment), sorted(schedule)]
    return expires, sha256(json.dumps(key).encode()).hexdigest()[:24]


def assess_live_route(*, snapshot, points, position=None, at=None, contains):
    moment = at or datetime.now(KST)
    moment = moment.replace(tzinfo=KST) if moment.tzinfo is None else moment.astimezone(KST)
    policy = EnvironmentPolicy()
    cells = sample_route(points, step_m=policy.step_m)
    if any(not contains(*point) for point in points) or any(not contains(*cell.midpoint) for cell in cells):
        raise OutsideLiveServiceArea("route_points")
    if position is not None and not contains(*position):
        raise OutsideLiveServiceArea("position")
    artifact = snapshot.artifact if snapshot is not None else None
    indexes = artifact.environment_index if artifact is not None else None
    version = artifact.version if artifact is not None else None
    valid_until, temporal_key = _freshness(moment, version, indexes, cells, position, policy)
    result = {"assessment": None, "route_evidence": {}, "local_environment": None, "havens": [],
              "artifact_version": version, "evaluated_at": moment, "valid_until": valid_until,
              "temporal_key": temporal_key, "status": "pending", "period": period_for(moment)}
    if position is not None:
        result["havens"] = nearest_havens(indexes, *position, at=moment)
    if indexes is None:
        return result
    common, excluded = eligible_factors(indexes, [points], period_for(moment), policy)
    assessment, observations = evaluate_route_cells(
        cells, at=moment, policy=policy, indexes=indexes, common_factors=common,
        excluded_factors=excluded, comparison_group_id=temporal_key,
    )
    result.update(assessment=asdict(assessment), status=assessment.status,
                  route_evidence=_intervals(cells, observations, assessment.active_factors))
    if position is not None:
        result["local_environment"] = assess_local_facilities(position, at=moment, policy=policy,
                                                              indexes=indexes, artifact_version=version)
    return result


class OutsideLiveServiceArea(ValueError):
    pass
