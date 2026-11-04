"""Local shadow comparisons; no network requests and no current-manifest writes."""
import argparse
from dataclasses import asdict, replace
from datetime import datetime
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np

from app.core.config import settings
from app.services.route_environment import RouteCandidate, evaluate_route_group
from app.services.route_environment_policy import EnvironmentPolicy
from app.services.route_environment_rank import assess_and_select
from app.services.route_environment_sources import EnvironmentIndex
from app.services.safe_route import RouteArtifactRuntime
from app.services.time_period import KST, period_for


def sensitivity_policies():
    base = EnvironmentPolicy()
    values = [base]
    for name, choices in (("step_m", (10, 40)), ("score_tolerance", (0, 1, 5)), ("bell_radius_m", (100, 300)),
                          ("max_detour_ratio", (0.1, 0.3)), ("max_extra_minutes", (2, 5))):
        values.extend(replace(base, **{name: v}) for v in choices)
    for scale in (0.5, 1.5):
        values.append(replace(base, cctv_radius_m=60*scale, lighting_radius_m=40*scale, open_store_radius_m=50*scale))
    return values


def _point(value):
    if len(value) != 2 or not all(math.isfinite(v) for v in value) or not -90 <= value[0] <= 90 or not -180 <= value[1] <= 180:
        raise ValueError("Invalid case coordinate")
    return tuple(value)


def evaluate_route_pairs(cases, *, runtime, policies):
    rows, latencies = [], []
    snapshot = runtime.environment_snapshot()
    index = snapshot.artifact.environment_index if snapshot else EnvironmentIndex()
    for case in cases:
        start, end = _point(case["start"]), _point(case["end"])
        at = datetime.fromisoformat(case["at"]) if case.get("at") else datetime.now(KST)
        raw = runtime.find_environment_candidates(start, end, at=at, policy=EnvironmentPolicy(), snapshot=snapshot) if snapshot else []
        # Historical geometry is an explicit input, never a call back into the retired engine.
        legacy = [{"points": [_point(p) for p in case["reference_points"]]}] if case.get("reference_points") else []
        general = case.get("general_points")
        if general:
            general = RouteCandidate("general", [_point(p) for p in general], "tmap")
        elif raw:
            general = raw[0]
        elif legacy:
            general = RouteCandidate("general", legacy[0]["points"], "osm")
        else:
            rows.append({"case_id": case["id"], "status": "pedestrian_route_unavailable"})
            continue
        candidates = list(raw or [general])
        if general.candidate_id not in {c.candidate_id for c in candidates}:
            candidates.append(general)
        for policy in policies:
            started = perf_counter()
            ranked, evaluated, baseline = assess_and_select(candidates, baseline_id=general.candidate_id, at=at, policy=policy, indexes=index)
            chosen = ranked[0]
            # Pairwise evidence for comparing the old route must not change the new selector's K.
            comparison = None
            if legacy:
                pair = evaluate_route_group([chosen.candidate, RouteCandidate("legacy",legacy[0]["points"],"osm")],
                                            at=at,policy=policy,indexes=index)
                comparison = {"new":asdict(pair[0].assessment),"legacy":asdict(pair[1].assessment)}
            elapsed = (perf_counter() - started) * 1000
            latencies.append(elapsed)
            limit = baseline.assessment.distance_m + min(baseline.assessment.distance_m * policy.max_detour_ratio, policy.max_extra_minutes*67)
            rows.append(dict(case_id=case["id"], period=period_for(at), policy=asdict(policy),
                             new=asdict(chosen.assessment), comparison=comparison,
                             baseline_source=general.source, detour_limit_passed=chosen.assessment.distance_m <= limit + 1e-6,
                             candidate_count=len(evaluated), evaluation_ms=elapsed))
    return dict(case_count=len(cases), cases=rows, sensitivity_scope="fixed_candidate_pool",
                additional_evaluation_p95_ms=float(np.percentile(latencies,95)) if latencies else None,
                claims="Prototype facility evidence, not crime-risk validation; no operating manifest changed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, default=Path(settings.route_artifact_dir))
    parser.add_argument("--shadow-only", action="store_true", default=True)
    parser.add_argument("--sensitivity", action="store_true")
    args = parser.parse_args()
    runtime = RouteArtifactRuntime()
    if not runtime.load(args.artifact_dir):
        raise SystemExit("A verified local artifact is required; nothing was published")
    result = evaluate_route_pairs(json.loads(args.cases.read_text(encoding="utf-8")), runtime=runtime,
                                  policies=sensitivity_policies() if args.sensitivity else [EnvironmentPolicy()])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
