from dataclasses import replace

import pytest

from app.services.route_artifact_validation import validate_route_artifact, require_publishable
from test_route_environment_runtime import artifact


def test_empty_environment_is_walking_ready_but_not_evaluation_ready():
    report = validate_route_artifact(artifact())
    assert report["walking_ready"] is True
    assert report["environment_ready"] is False
    assert "evaluation_sources_unavailable" in report["reason_codes"]
    require_publishable(report, previous=None)


def test_cannot_replace_evaluation_ready_artifact_with_empty_evidence():
    with pytest.raises(ValueError, match="evaluation_readiness_regressed"):
        require_publishable(validate_route_artifact(artifact()), previous={"environment_ready": True})


def test_schema_and_policy_mismatch_are_not_walking_ready():
    report = validate_route_artifact(replace(artifact(), environment_policy_fingerprint="old"))
    assert not report["walking_ready"]
    with pytest.raises(ValueError):
        require_publishable(report, previous=None)
