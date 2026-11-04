import hashlib
import json

import pytest

from scripts.build_route_environment_sources import build_manifest
from scripts.evaluate_route_environment import evaluate_route_pairs, sensitivity_policies
from app.services.route_environment_policy import EnvironmentPolicy
from test_route_environment_runtime import artifact
from app.services.safe_route import RouteArtifactRuntime


def test_batch_manifest_records_digest_without_inventing_verified_completeness(tmp_path):
    points = tmp_path / "points.json"
    points.write_text("[[37.5,127]]")
    descriptor = tmp_path / "input.json"
    descriptor.write_text(json.dumps({"sources": [dict(source_id="cctv",factor="cctv",source_url="https://data.go.kr/test",observed_at="2026-06-30",retrieved_at="2026-11-04",points_file="points.json",purpose="crime_prevention",coordinate_crs="EPSG:4326",completeness="partial")]}))
    output = tmp_path / "output.json"
    result = build_manifest(descriptor, output)
    assert result["sources"][0]["sha256"] == hashlib.sha256(points.read_bytes()).hexdigest()
    assert result["sources"][0]["completeness"] == "partial"


def test_shadow_evaluation_reports_missing_evidence_without_changing_current():
    runtime = RouteArtifactRuntime()
    runtime.install(artifact())
    result = evaluate_route_pairs([{"id":"test", "start":[37.5,127], "end":[37.501,127], "at":"2026-11-04T23:00:00+09:00"}], runtime=runtime, policies=[EnvironmentPolicy()])
    assert result["cases"][0]["new"]["score"] is None
    assert result["cases"][0]["detour_limit_passed"] is True
    assert result["case_count"] == 1
    assert runtime.status()["version"] == "env"


def test_sensitivity_policies_cover_policy_choices_instead_of_only_score_increases():
    policies = sensitivity_policies()
    assert {p.step_m for p in policies} >= {10,20,40}
    assert {p.score_tolerance for p in policies} >= {0,1,3,5}
    assert {p.bell_radius_m for p in policies} >= {100,200,300}


def test_invalid_case_rejects_nonfinite_coordinates():
    with pytest.raises(ValueError):
        evaluate_route_pairs([{"id":"bad", "start":[float("nan"),127], "end":[37.5,127]}], runtime=RouteArtifactRuntime(),policies=[EnvironmentPolicy()])


def test_offline_uses_feasible_production_pool_before_freezing_common_factors():
    from types import SimpleNamespace
    from app.services.route_environment import RouteCandidate
    from app.services.route_environment_sources import build_environment_index
    from test_route_environment import source, POINTS
    sources = [source("cctv",[(37.5009,127)]),source("bell",[(37.5009,127)])]
    for s in sources:
        s.coverage_geometry = {"type":"Polygon","coordinates":[[[126.99,37.49],[127.01,37.49],[127.01,37.51],[126.99,37.51],[126.99,37.49]]]}
    detour = [POINTS[0],(37.5,127.02),(37.5018,127.02),POINTS[1]]
    candidates = [RouteCandidate("osm-0",POINTS,"osm"),RouteCandidate("outside",detour,"osm")]
    class Runtime:
        def environment_snapshot(self):
            return SimpleNamespace(artifact=SimpleNamespace(environment_index=build_environment_index(sources)))
        def find_environment_candidates(self,*a,**kw):
            return candidates
        def find_routes(self,*a,**kw):
            raise AssertionError("retired route engine must not run")
    report = evaluate_route_pairs([{"id":"coverage","start":POINTS[0],"end":POINTS[-1],"at":"2026-11-04T23:00:00+09:00","reference_points":detour}],runtime=Runtime(),policies=[EnvironmentPolicy()])
    assert report["cases"][0]["new"]["score"] is not None
    assert report["cases"][0]["new"]["used_factors"] == ["bell","cctv"]
    assert report["cases"][0]["comparison"]["new"]["score"] is None
