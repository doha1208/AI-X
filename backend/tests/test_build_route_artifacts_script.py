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
from app.services.scoring_profile import DEFAULT_SCORING_PROFILE, ScoringProfile
from app.services.route_environment_sources import EnvironmentIndex
from app.services.route_environment_policy import EnvironmentPolicy
from app.services import scoring_profile_store
from app.services.safe_route import route_input_data_version
from scripts import build_route_artifacts as script


@pytest.fixture(autouse=True)
def isolated_preparation(monkeypatch, tmp_path):
    from app.services import route_environment_inputs
    monkeypatch.setattr(route_environment_inputs, "prepare_environment_inputs", lambda *a, **k: None)
    monkeypatch.setattr(settings, "route_environment_sources_path", str(tmp_path / "sources.json"))
    monkeypatch.setattr(settings, "route_validation_cases_path", str(tmp_path / "cases.json"))


def _raise(exc: BaseException) -> None:
    # 제너레이터 안에서 StopIteration을 던지면(예: 흔한 (_ for _ in ()).throw(...) 트릭)
    # PEP 479에 따라 RuntimeError로 바뀐다 — 평범한 함수에서 던져야 그대로 전파된다.
    raise exc


def _artifact(version: str, schema: int = 4) -> RouteArtifact:
    from app.services.walk_environment_samples import SAMPLING_VERSION, WalkEnvironmentIndex
    graph = nx.DiGraph()
    graph.add_node(1, y=37.5, x=127.0)
    graph.add_node(2, y=37.501, x=127.001)
    graph.add_edge(1, 2, length=140.0, edge_score=70.0, safety_cost=210.0)
    return RouteArtifact(
        version=version,
        schema_version=schema,
        walk_environment_index=WalkEnvironmentIndex((), "test-source") if schema == 4 else None,
        sampling_version=SAMPLING_VERSION if schema == 4 else None,
        boundary_version="test-boundary" if schema == 4 else None,
        region="seoul-gyeonggi",
        graph_by_period={"day": graph, "night": graph.copy()},
        environment_graph=graph, environment_index=EnvironmentIndex(),
        environment_model_version="facility-access-v1", environment_policy_fingerprint=EnvironmentPolicy().fingerprint(),
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
    monkeypatch.setattr(script, "build_route_artifact", lambda zones, **kwargs: _artifact(kwargs["version"], kwargs["target_schema"]))

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
        lambda **kwargs: captured.update({**kwargs, "dong_codes": [z.dong_code for z in kwargs["zones"]]}) or tmp_path / "v1",
    )
    monkeypatch.setattr(sys, "argv", ["build_route_artifacts.py", "--directory", str(tmp_path), "--bootstrap"])

    script.main()

    assert captured["dong_codes"] == ["11110101"]


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

    def publish_candidate(*, directory, version, profile, target_schema, **_):
        artifact = _artifact(version, target_schema)
        object.__setattr__(artifact, "profile_version", profile.version)
        return publish_artifact(artifact, directory)

    monkeypatch.setattr(script, "build_and_publish_route_artifact", publish_candidate)

    assert script.process_next_queued_build(directory=tmp_path, region="seoul-gyeonggi") is True

    db = session_local()
    build = db.get(ScoreBuildRecord, build_id)
    profiles = {profile.version: profile.status for profile in db.query(ScoringProfileRecord).all()}
    assert load_current_artifact(tmp_path).schema_version == 3
    assert db.query(ScoreBuildRecord).filter_by(target_schema=4, status="queued").count() == 1
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
    object.__setattr__(artifact, "data_version", route_input_data_version([zone], profile=ScoringProfile(candidate.version, json.loads(candidate.weights_json), candidate.unknown_score)))
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
    object.__setattr__(artifact, "data_version", route_input_data_version([zone], profile=ScoringProfile(active.version, json.loads(active.weights_json), active.unknown_score)))
    publish_artifact(artifact, tmp_path)

    assert script.queue_rebuild_if_active_artifact_is_stale(db, tmp_path) is False
    assert db.query(ScoreBuildRecord).count() == 0
    db.close()


def test_bootstrap_registers_default_draft_and_deduplicates_request(tmp_path):
    session_local = _session_local(tmp_path)
    db = session_local()
    profile = script.ensure_build_profile(db, bootstrap=True, current_profile_version="default-v3")
    assert profile.status == "draft"
    again = script.ensure_build_profile(db, bootstrap=True, current_profile_version="default-v3")
    assert again.id == profile.id
    a = scoring_profile_store.queue_route_build(db, profile_id=profile.id, input_fingerprint="inputs-v1", region="gyeonggi", target_schema=3, reason="bootstrap")
    b = scoring_profile_store.queue_route_build(db, profile_id=profile.id, input_fingerprint="inputs-v1", region="gyeonggi", target_schema=3, reason="changed")
    assert a.id == b.id
    assert db.query(ScoreBuildRecord).count() == 1
    assert db.get(ScoringProfileRecord, profile.id).status == "draft"
    db.close()


def test_bootstrap_does_not_replace_an_unknown_existing_profile(tmp_path):
    session_local = _session_local(tmp_path)
    with session_local() as db, pytest.raises(ValueError, match="profile_unresolved"):
        script.ensure_build_profile(db, bootstrap=True, current_profile_version="unknown-custom")


def test_interrupted_build_is_requeued_immediately_after_restart(tmp_path):
    from datetime import UTC, datetime
    session_local = _session_local(tmp_path)
    with session_local() as db:
        profile = _profile("default-v3", "active")
        zone = SafetyZone(dong_code="TEST1", dong_name="테스트", lat=37.5, lng=127)
        db.add_all([profile, zone])
        db.commit()
        fingerprint = route_input_data_version([zone])
        db.add(ScoreBuildRecord(profile_id=profile.id, status="failed", input_fingerprint=fingerprint,
                                error_code="interrupted", finished_at=datetime.now(UTC)))
        db.commit()
        assert script.queue_rebuild_if_active_artifact_is_stale(db, tmp_path) is True


def test_corrupt_unchanged_artifact_triggers_automatic_repair(tmp_path):
    session_local = _session_local(tmp_path)
    with session_local() as db:
        profile = _profile("default-v3", "active")
        zone = SafetyZone(dong_code="TEST1", dong_name="테스트", lat=37.5, lng=127)
        db.add_all([profile, zone])
        db.commit()
        artifact = _artifact("stable")
        object.__setattr__(artifact, "profile_version", profile.version)
        object.__setattr__(artifact, "data_version", route_input_data_version([zone]))
        publish_artifact(artifact, tmp_path)
        assert script.queue_rebuild_if_active_artifact_is_stale(db, tmp_path) is False
        (tmp_path / "stable" / "route-artifact.pickle").write_bytes(b"truncated")
        assert script.queue_rebuild_if_active_artifact_is_stale(db, tmp_path) is True


def test_worker_prepares_inputs_before_freshness_check_and_processing(monkeypatch, tmp_path):
    from scripts import artifact_builder_worker as worker
    from app.services import route_environment_inputs
    from types import SimpleNamespace
    calls = []
    monkeypatch.setattr(worker, "process_next_queued_build", lambda **_: calls.append("process") or False)
    monkeypatch.setattr(worker, "reconcile_published_build", lambda *_: calls.append("reconcile") or False)
    monkeypatch.setattr(worker, "queue_rebuild_if_active_artifact_is_stale", lambda *a, **k: calls.append("freshness") or False)
    monkeypatch.setattr(route_environment_inputs, "prepare_environment_inputs", lambda *a: calls.append("prepare") or SimpleNamespace(snapshot_id="fixture",diagnostics=[]))
    monkeypatch.setattr(worker, "SessionLocal", _session_local(tmp_path))
    monkeypatch.setattr(worker.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(worker.time, "sleep", lambda _: _raise(StopIteration()))
    with pytest.raises(StopIteration):
        worker.run_worker(directory=tmp_path, region="gyeonggi", poll_seconds=1, refresh_seconds=1800)
    assert calls.index("prepare") < calls.index("freshness") < calls.index("process")
    assert "reconcile" in calls
