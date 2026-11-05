"""Keep one hidden builder alive while the API is running; never build on its event loop."""
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

from app.core.config import settings
from app.services.route_build_state import builder_lock

logger = logging.getLogger(__name__)


class BuilderSupervisor:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.child = None
        self.thread = None
        self.stop = threading.Event()

    def tick(self):
        if self.child is not None and self.child.poll() is None:
            return
        with builder_lock(self.directory) as available:
            if not available:
                return
        self.directory.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, "ROUTE_BUILDER_AUTO_START": "false", "APP_ENV": settings.app_env,
               "DATABASE_URL": settings.database_url, "ROUTE_ARTIFACT_DIR": str(self.directory),
               "ROUTE_ENVIRONMENT_SOURCES_PATH": str(Path(settings.route_environment_sources_path).resolve()),
               "ROUTE_SOURCE_CATALOG_PATH": str(Path(settings.route_source_catalog_path).resolve())}
        executable = sys.executable
        if os.name == "nt":
            # CPython's venv redirector can outlive the interpreter on this host.
            # Launch the interpreter directly while retaining the exact venv path configuration.
            executable = getattr(sys, "_base_executable", sys.executable)
            env["__PYVENV_LAUNCHER__"] = sys.executable
        with (self.directory / "builder-worker.log").open("ab") as log:
            self.child = subprocess.Popen(
                [executable, "-m", "scripts.artifact_builder_worker"],
                cwd=Path(__file__).resolve().parents[2], env=env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

    def start(self):
        def supervise():
            while not self.stop.is_set():
                try:
                    self.tick()
                except OSError:
                    logger.exception("Cannot start route builder")
                self.stop.wait(5)
        self.thread = threading.Thread(target=supervise, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=6)
        if self.child is not None and self.child.poll() is None:
            if os.name == "nt":
                # Windows venv launchers can own another Python child; terminate only our full tree.
                result = subprocess.run(["taskkill", "/PID", str(self.child.pid), "/T", "/F"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode == 0:
                    return
            self.child.terminate()
            try:
                self.child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=5)


def start_builder_supervisor(config=settings):
    if config.app_env.lower() == "test" or not config.route_builder_auto_start:
        return None
    supervisor = BuilderSupervisor(Path(config.route_artifact_dir))
    supervisor.start()
    return supervisor
