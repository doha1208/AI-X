from types import SimpleNamespace
import os
import sys

from app.services import route_builder_supervisor as supervisor


def test_server_starts_one_hidden_builder_and_stops_its_child(monkeypatch, tmp_path):
    calls = []
    child = SimpleNamespace(pid=12345, poll=lambda: None, terminate=lambda: calls.append("terminate"), wait=lambda timeout: calls.append("wait"))
    def spawn(command, **kwargs):
        calls.append((command, kwargs))
        return child
    monkeypatch.setattr(supervisor.subprocess, "Popen", spawn)
    monkeypatch.setattr(supervisor.subprocess, "run", lambda command, **kwargs: calls.append(command) or SimpleNamespace(returncode=0))
    builder = supervisor.BuilderSupervisor(tmp_path)
    builder.tick()
    builder.tick()
    assert len(calls) == 1
    assert "scripts.artifact_builder_worker" in calls[0][0]
    assert calls[0][1]["env"]["ROUTE_BUILDER_AUTO_START"] == "false"
    if os.name == "nt":
        assert calls[0][0][0] == sys._base_executable
        assert calls[0][1]["env"]["__PYVENV_LAUNCHER__"] == sys.executable
    builder.close()
    if os.name == "nt":
        assert calls[-1] == ["taskkill", "/PID", "12345", "/T", "/F"]
    else:
        assert calls[-2:] == ["terminate", "wait"]


def test_testing_or_external_builder_configuration_does_not_spawn(monkeypatch):
    monkeypatch.setattr(supervisor.BuilderSupervisor, "start", lambda self: (_ for _ in ()).throw(AssertionError("must not spawn")))
    assert supervisor.start_builder_supervisor(SimpleNamespace(app_env="test", route_builder_auto_start=True)) is None
    assert supervisor.start_builder_supervisor(SimpleNamespace(app_env="production", route_builder_auto_start=False)) is None
