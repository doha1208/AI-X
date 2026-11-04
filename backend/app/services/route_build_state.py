"""One writer per artifact directory, shared by embedded, Docker and manual builders."""
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import threading

from app.services.route_environment_inputs import atomic_json

_state_lock = threading.RLock()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def builder_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".builder.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        acquired = False
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, BlockingIOError):
            pass
        try:
            yield acquired
        finally:
            if acquired:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)


def read_builder_state(directory: Path) -> dict:
    try:
        state = json.loads((directory / "builder-state.json").read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def update_builder_state(directory: Path, **changes) -> None:
    with _state_lock:
        state = read_builder_state(directory)
        state.update(changes)
        atomic_json(directory / "builder-state.json", state)


def public_builder_status(directory: Path) -> dict:
    state = read_builder_state(directory)
    allowed = ("status", "last_worker_heartbeat_at", "last_checked_at", "last_success_at", "environment_ready",
               "environment_inputs_ready", "stale_reason", "source_snapshot_id", "source_counts", "source_diagnostics")
    result = {key: state[key] for key in allowed if key in state}
    try:
        age = (datetime.now(UTC) - datetime.fromisoformat(state["last_worker_heartbeat_at"])).total_seconds()
        result["worker_alive"] = 0 <= age < 60
    except (KeyError, TypeError, ValueError):
        result["worker_alive"] = False
    if not result["worker_alive"]:
        result["stale_reason"] = "worker_not_running"
    return result
