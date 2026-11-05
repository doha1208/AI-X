"""Walking availability and verified assessment readiness are separate guarantees."""
from datetime import datetime

from app.services.route_environment import evaluate_route_group
from app.services.route_environment_policy import EnvironmentPolicy


def validate_route_artifact(artifact, *, reference_cases=None) -> dict:
    from app.services.route_artifact import extended_artifact_valid
    policy = EnvironmentPolicy()
    graph = artifact.environment_graph
    walking = bool(artifact.schema_version in (3, 4) and artifact.environment_model_version == "facility-access-v1"
                   and artifact.environment_policy_fingerprint == policy.fingerprint()
                   and graph is not None and len(graph) and graph.number_of_edges() and extended_artifact_valid(artifact))
    indexes = artifact.environment_index
    sources = indexes.sources if indexes is not None else []
    reasons = [] if walking else ["walking_artifact_invalid"]
    if not any(e.source.eligible() for e in sources):
        reasons.append("evaluation_sources_unavailable")
    results = []
    if walking and reference_cases:
        from app.services.safe_route import RouteArtifactRuntime
        runtime = RouteArtifactRuntime()
        runtime.install(artifact)
        for case in reference_cases:
            at = datetime.fromisoformat(case["at"])
            candidates = runtime.find_environment_candidates(tuple(case["start"]), tuple(case["end"]), at=at, policy=policy) or []
            assessed = evaluate_route_group(candidates[:1], at=at, policy=policy, indexes=indexes)
            value = assessed[0].assessment if assessed else None
            results.append({"id": case["id"], "period": value.period if value else None,
                            "score": value.score if value else None, "used_factors": value.used_factors if value else []})
    ready = walking and bool(results) and {r["period"] for r in results} == {"day", "night"} and all(r["score"] is not None for r in results)
    if not results:
        reasons.append("reference_validation_required")
    elif not ready:
        reasons.append("reference_evaluation_incomplete")
    spatial = getattr(artifact, "walk_environment_index", None)
    area_ready = bool(walking and artifact.schema_version == 4 and extended_artifact_valid(artifact) and spatial is not None
                      and len(spatial.segments) and any(e.source.presence_eligible() for e in sources))
    summaries = getattr(artifact, "zone_facility_summaries", {})
    zone_ready = area_ready and any(row.get("status") in {"available", "degraded"} for row in summaries.values())
    return {"walking_ready": walking, "environment_inputs_ready": bool(sources), "environment_ready": ready,
            "area_environment_ready": area_ready, "zone_environment_ready": zone_ready,
            "physical_walk_segments": len(spatial.segments) if hasattr(spatial, "segments") else 0,
            "zone_summary_count": len(summaries), "boundary_diagnostics": getattr(artifact, "boundary_diagnostics", {}),
            "input_fingerprint": artifact.data_version, "source_counts": {e.source.source_id: len(e.source.points) for e in sources},
            "reason_codes": reasons, "reference_case_results": results}


def require_publishable(report: dict, *, previous: dict | None) -> None:
    if not report["walking_ready"]:
        raise ValueError("walking_artifact_invalid")
    if previous and previous.get("environment_ready") and not report["environment_ready"]:
        raise ValueError("evaluation_readiness_regressed")
    for feature in ("area", "zone"):
        if previous and previous.get(f"{feature}_environment_ready") and not report.get(f"{feature}_environment_ready"):
            raise ValueError(f"{feature}_evaluation_readiness_regressed")
