import json
import sys
from importlib.util import find_spec

import pytest

import networkx as nx
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.session import Base
from app.models.safety_zone import SafetyZone
from app.models.scoring_profile import ScoreBuildRecord, ScoringProfileRecord
from app.services.route_artifact import RouteArtifact, load_current_artifact, publish_artifact
from app.services.scoring_profile import DEFAULT_SCORING_PROFILE
from app.services import scoring_profile_store
from app.services.safe_route import route_input_data_version
from scripts import build_route_artifacts as script


def _artifact(version: str) -> RouteArtifact:
    graph = nx.DiGraph()
    graph.add_node(1, y=37.5, x=127.0)
    graph.add_node(2, y=37.501, x=127.001)
    graph.add_edge(1, 2, length=140.0, edge_score=70.0, safety_cost=210.0)
    return RouteArtifact(
        version=version,
        region="seoul-gyeonggi",
        graph_by_period={"day": graph, "night": graph.copy()},
        node_ids=[1, 2],
        node_points=np.array([(37.5, 100.75587421698687), (37.501, 100.75666757032717)]),
    )


def _profile(version: str, status: str) -> ScoringProfileRecord:
    return ScoringProfileRecord(
        version=version,
        name=version,
        weights_json=json.dumps(
            {period: dict(weights) for period, weights in DEFAULT_SCORING_PROFILE.weights.items()}
        ),
        unknown_score=DEFAULT_SCORING_PROFILE.unknown_score,
        status=status,
        created_by="admin@example.com",
    )


def _session_local(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'builds.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _seed_queued_build(session_local, *, active_version: str = "current-v1") -> int:
    db = session_local()
    current = _profile(active_version, "active")
    candidate = _profile("candidate-v1", "draft")
    db.add_all([current, candidate, SafetyZone(dong_code="TEST1", dong_name="테스트", lat=37.5, lng=127.0)])
    db.flush()
    build = ScoreBuildRecord(profile_id=candidate.id, status="queued")
    db.add(build)
    db.commit()
    build_id = build.id
    db.close()
    return build_id


def test_batch_builder_publishes_the_built_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "build_route_artifact", lambda zones, **kwargs: _artifact(kwargs["version"]))

    artifact_dir = script.build_and_publish_route_artifact(
        zones=[object()], directory=tmp_path, version="v1", region="seoul-gyeonggi"
    )

    assert artifact_dir == tmp_path / "v1"
    assert load_current_artifact(tmp_path).version == "v1"


def test_main_builds_an_artifact_from_scoped_zones_only(monkeypatch, tmp_path):
    captured: dict[str, object] = {}
    engine = create_engine(f"sqlite:///{tmp_path / 'zones.db'}")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_local()
    db.add_all(
        [
            SafetyZone(dong_code="11110101", dong_name="서울", lat=37.5, lng=127.0),
            SafetyZone(dong_code="41110101", dong_name="경기", lat=37.4, lng=127.1),
        ]
    )
    db.commit()
    db.close()

    monkeypatch.setattr(script, "SessionLocal", session_local)
    monkeypatch.setattr(settings, "region_scope_prefix", "11")
    monkeypatch.setattr(
        script,
        "build_and_publish_route_artifact",
        lambda **kwargs: captured.update(kwargs) or tmp_path / "v1",
    )
    monkeypatch.setattr(sys, "argv", ["build_route_artifacts.py", "--directory", str(tmp_path)])

    script.main()

    assert [zone.dong_code for zone in captured["zones"]] == ["11110101"]


def test_main_processes_one_queued_build(monkeypatch, tmp_path):
    called = {}
    monkeypatch.setattr(script, "process_next_queued_build", lambda **kwargs: called.update(kwargs) or True)
    monkeypatch.setattr(sys, "argv", ["build_route_artifacts.py", "--process-next", "--directory", str(tmp_path)])

    script.main()

    assert called["directory"] == tmp_path


def test_queued_build_publishes_then_activates_candidate_profile(monkeypatch, tmp_path):
    session_local = _session_local(tmp_path)
    build_id = _seed_queued_build(session_local)
    publish_artifact(_artifact("stable-v1"), tmp_path)
    monkeypatch.setattr(script, "SessionLocal", session_local)

    def publish_candidate(*, directory, version, profile, **_):
        artifact = _artifact(version)
        object.__setattr__(artifact, "profile_version", profile.version)
        return publish_artifact(artifact, directory)

    monkeypatch.setattr(script, "build_and_publish_route_artifact", publish_candidate)

    assert script.process_next_queued_build(directory=tmp_path, region="seoul-gyeonggi") is True

    db = session_local()
    build = db.get(ScoreBuildRecord, build_id)
    profiles = {profile.version: profile.status for profile in db.query(ScoringProfileRecord).all()}
    db.close()
    current = load_current_artifact(tmp_path)

    assert build.status == "succeeded"
    assert build.started_at is not None
    assert build.finished_at is not None
    assert build.artifact_version == current.version
    assert current.profile_version == "candidate-v1"
    assert profiles == {"current-v1": "draft", "candidate-v1": "active"}


def test_failed_queued_build_keeps_current_artifact_and_active_profile(monkeypatch, tmp_path):
    session_local = _session_local(tmp_path)
    build_id = _seed_queued_build(session_local)
    publish_artifact(_artifact("stable-v1"), tmp_path)
    monkeypatch.setattr(script, "SessionLocal", session_local)
    monkeypatch.setattr(
        script,
        "build_and_publish_route_artifact",
        lambda **_: (_ for _ in ()).throw(RuntimeError("graph unavailable")),
    )

    assert script.process_next_queued_build(directory=tmp_path, region="seoul-gyeonggi") is True

    db = session_local()
    build = db.get(ScoreBuildRecord, build_id)
    profiles = {profile.version: profile.status for profile in db.query(ScoringProfileRecord).all()}
    db.close()

    assert build.status == "failed"
    assert build.error_code == "build_failed"
    assert build.started_at is not None
    assert build.finished_at is not None
    assert load_current_artifact(tmp_path).version == "stable-v1"
    assert profiles == {"current-v1": "active", "candidate-v1": "draft"}


def test_claim_next_queued_build_marks_it_building_before_expensive_work(tmp_path):
    session_local = _session_local(tmp_path)
    build_id = _seed_queued_build(session_local)
    db = session_local()

    claim_next = getattr(scoring_profile_store, "claim_next_queued_build", None)
    assert callable(claim_next)
    claimed = claim_next(db)

    assert claimed is not None
    build, profile = claimed
    assert build.id == build_id
    assert profile.version == "candidate-v1"
    assert build.status == "building"
    assert build.started_at is not None
    assert claim_next(db) is None
    db.close()


def test_reconcile_published_artifact_completes_interrupted_build(tmp_path):
    session_local = _session_local(tmp_path)
    build_id = _seed_queued_build(session_local)
    db = session_local()
    build = db.get(ScoreBuildRecord, build_id)
    build.status = "building"
    db.commit()
    candidate = db.get(ScoringProfileRecord, build.profile_id)
    zone = db.query(SafetyZone).one()
    db.close()
    artifact = _artifact("published-v2")
    object.__setattr__(artifact, "profile_version", candidate.version)
    object.__setattr__(artifact, "data_version", route_input_data_version([zone]))
    publish_artifact(artifact, tmp_path)

    db = session_local()
    assert script.reconcile_published_build(db, tmp_path) is True
    recovered = db.get(ScoreBuildRecord, build_id)
    statuses = {record.version: record.status for record in db.query(ScoringProfileRecord).all()}
    db.close()

    assert recovered.status == "succeeded"
    assert recovered.artifact_version == "published-v2"
    assert recovered.finished_at is not None
    assert statuses == {"current-v1": "draft", "candidate-v1": "active"}


def test_unchanged_active_artifact_does_not_queue_periodic_rebuild(tmp_path):
    session_local = _session_local(tmp_path)
    db = session_local()
    active = _profile("active-v1", "active")
    zone = SafetyZone(dong_code="TEST1", dong_name="테스트", lat=37.5, lng=127.0)
    db.add_all([active, zone])
    db.commit()
    artifact = _artifact("active-artifact")
    object.__setattr__(artifact, "profile_version", active.version)
    object.__setattr__(artifact, "data_version", route_input_data_version([zone]))
    publish_artifact(artifact, tmp_path)

    assert script.queue_rebuild_if_active_artifact_is_stale(db, tmp_path) is False
    assert db.query(ScoreBuildRecord).count() == 0
    db.close()


def test_worker_processes_queue_and_runs_one_freshness_check(monkeypatch, tmp_path):
    assert find_spec("scripts.artifact_builder_worker") is not None
    from scripts import artifact_builder_worker as worker

    calls: list[str] = []
    monkeypatch.setattr(worker, "process_next_queued_build", lambda **_: calls.append("process") or False)
    monkeypatch.setattr(worker, "reconcile_published_build", lambda *_: calls.append("reconcile") or False)
    monkeypatch.setattr(
        worker, "queue_rebuild_if_active_artifact_is_stale", lambda *_: calls.append("freshness") or False
    )
    monkeypatch.setattr(worker, "SessionLocal", lambda: _WorkerSession(calls))
    monkeypatch.setattr(worker.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(worker.time, "sleep", lambda _: (_ for _ in ()).throw(StopIteration))

    with pytest.raises(StopIteration):
        worker.run_worker(directory=tmp_path, region="seoul-gyeonggi", poll_seconds=1, refresh_seconds=1800)

    assert calls == ["process", "reconcile", "freshness", "close"]


class _WorkerSession:
    def __init__(self, calls: list[str]):
        self.calls = calls

    def close(self) -> None:
        self.calls.append("close")
