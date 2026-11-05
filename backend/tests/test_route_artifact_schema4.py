from dataclasses import replace
import json

import pytest

from app.services.route_artifact import publish_artifact, load_current_artifact
from app.services.route_artifact_validation import validate_route_artifact
from app.services.safe_route import RouteArtifactRuntime
from app.services.walk_environment_samples import SAMPLING_VERSION
from test_route_environment_runtime import artifact
from test_walk_environment_samples import index, point


def extended():
    return replace(artifact(), schema_version=4, sampling_version=SAMPLING_VERSION, boundary_version="boundary-v1",
                   walk_environment_index=index([(1, 2, point(0, 0), point(0, 100), {})]), zone_facility_summaries={})


def test_schema3_retains_routes_without_advertising_extended_capabilities():
    value = replace(artifact(), schema_version=3)
    runtime = RouteArtifactRuntime()
    runtime.install(value)
    assert runtime.environment_snapshot() is not None
    report = validate_route_artifact(value)
    assert report["walking_ready"] and not report["area_environment_ready"] and not report["zone_environment_ready"]


def test_schema4_roundtrip_keeps_physical_index_and_runtime_snapshot(tmp_path):
    value = extended()
    publish_artifact(value, tmp_path)
    loaded = load_current_artifact(tmp_path)
    assert len(loaded.walk_environment_index.segments) == 1
    runtime = RouteArtifactRuntime()
    assert runtime.load(tmp_path)
    assert runtime.environment_snapshot().artifact.schema_version == 4


def test_malformed_schema4_cannot_replace_current_schema3(tmp_path):
    publish_artifact(replace(artifact(), schema_version=3), tmp_path)
    before = json.loads((tmp_path / "current.json").read_text())
    with pytest.raises(ValueError, match="extended|spatial"):
        publish_artifact(replace(extended(), version="broken", walk_environment_index="invalid"), tmp_path)
    assert json.loads((tmp_path / "current.json").read_text()) == before
