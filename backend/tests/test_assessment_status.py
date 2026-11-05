from types import SimpleNamespace

from app.main import health
from app.services import safe_route


def test_health_distinguishes_loaded_facility_policy_from_process_health(monkeypatch):
    runtime = safe_route.route_artifact_runtime
    monkeypatch.setattr(runtime, "status", lambda: {"available": True, "version": "test-artifact"})
    monkeypatch.setattr(runtime, "environment_snapshot", lambda: SimpleNamespace(artifact=SimpleNamespace(
        version="test-artifact", environment_model_version="facility-access-v1")))
    result = health()
    assert result["facility_assessment"] == {
        "model_version": "facility-access-v1", "policy_version": "environment-v1-draft",
        "artifact_version": "test-artifact", "applied": True,
    }
    monkeypatch.setattr(runtime, "environment_snapshot", lambda: None)
    assert health()["facility_assessment"]["applied"] is False
    assert health()["facility_assessment"]["artifact_version"] is None
    assert health()["status"] == "ok"
