"""적재된 안전 데이터와 로컬 OSM 도로망으로 경로 산출물을 게시한다.

사용법:
    backend/.venv/Scripts/python.exe -m scripts.build_route_artifacts
    backend/.venv/Scripts/python.exe -m scripts.build_route_artifacts --region gyeonggi

공공데이터 적재가 성공한 뒤 실행한다. 산출물 생성에 실패하면 기존 current 매니페스트는
그대로 유지되므로, API 워커는 직전에 검증된 산출물을 계속 사용한다.
"""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.safety_zone import SafetyZone, scoped_zones_query
from app.models.scoring_profile import ScoreBuildRecord, ScoringProfileRecord
from app.services.route_artifact import load_current_artifact, publish_artifact
from app.services.safe_route import build_route_artifact, route_input_data_version
from app.services.scoring_profile import ScoringProfile, DEFAULT_SCORING_PROFILE
from app.services.scoring_profile_store import claim_next_queued_build, queue_route_build
import json
from app.services.route_artifact_validation import validate_route_artifact, require_publishable
from app.services.route_build_state import builder_lock, update_builder_state, utc_now


def current_metadata(directory: Path) -> dict:
    try:
        value = json.loads((directory / "current.json").read_text(encoding="utf-8"))
        version = value["version"]
        if not isinstance(version, str) or Path(version).name != version or version in (".", ".."):
            return {}
        return value
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def current_validation(directory: Path) -> dict | None:
    metadata = current_metadata(directory)
    try:
        return json.loads((directory / metadata["version"] / "validation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def current_artifact_is_healthy(directory: Path) -> bool:
    # Verify checksum and supported contents, not just the existence of a pickle file.
    artifact = load_current_artifact(directory)
    if artifact is None:
        return False
    try:
        return validate_route_artifact(artifact)["walking_ready"]
    except (AttributeError, TypeError, ValueError):
        return False


def _default_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def ensure_build_profile(db: Session, *, bootstrap: bool, current_profile_version: str | None) -> ScoringProfileRecord:
    active = db.query(ScoringProfileRecord).filter(ScoringProfileRecord.status == "active").first()
    if active is not None:
        return active
    default = DEFAULT_SCORING_PROFILE
    if not bootstrap:
        raise ValueError("bootstrap_required")
    if current_profile_version not in (None, default.version):
        raise ValueError("profile_unresolved")
    record = db.query(ScoringProfileRecord).filter(ScoringProfileRecord.version == default.version).first()
    if record is None:
        record = ScoringProfileRecord(version=default.version, name="기본 거주지 점수 프로필", status="draft",
                                      weights_json=json.dumps({k: dict(v) for k, v in default.weights.items()}),
                                      unknown_score=default.unknown_score, created_by="system:bootstrap")
        db.add(record)
        db.commit()
        db.refresh(record)
    return record


def build_and_publish_route_artifact(
    *, zones: list[SafetyZone], directory: Path, version: str, region: str, profile: ScoringProfile = None,
    build_id: int | None = None, expected_input_fingerprint: str | None = None,
) -> Path:
    """주어진 안전구역 데이터로 산출물을 만들고, 성공했을 때만 최신 버전으로 게시한다."""

    artifact = build_route_artifact(zones, version=version, region=region, **({"profile": profile} if profile else {}))
    if expected_input_fingerprint is not None and artifact.data_version != expected_input_fingerprint:
        raise ValueError("input_changed_during_build")
    cases_path = Path(settings.route_validation_cases_path)
    cases = json.loads(cases_path.read_text(encoding="utf-8")) if cases_path.exists() else []
    report = validate_route_artifact(artifact, reference_cases=cases)
    report.update(build_id=build_id, source_snapshot_id=_source_snapshot_id())
    require_publishable(report, previous=current_validation(directory))
    if expected_input_fingerprint is not None and route_input_data_version(zones, profile=profile or DEFAULT_SCORING_PROFILE) != expected_input_fingerprint:
        raise ValueError("input_changed_during_build")
    result = publish_artifact(artifact, directory, validation_report=report)
    update_builder_state(directory, environment_ready=report["environment_ready"],
                         environment_inputs_ready=report["environment_inputs_ready"], last_success_at=utc_now(),
                         stale_reason=None if report["environment_ready"] else "evaluation_evidence_incomplete")
    return result


def _source_snapshot_id() -> str:
    from app.services.safe_route import _file_sha256
    return _file_sha256(Path(settings.route_environment_sources_path))


def process_next_queued_build(*, directory: Path, region: str, version_override: str | None = None) -> bool:
    db = SessionLocal()
    try:
        claimed = claim_next_queued_build(db)
        if claimed is None:
            return False
        build, profile_record = claimed
        if profile_record is None:
            return True
        build_id = build.id
        profile = ScoringProfile(profile_record.version, json.loads(profile_record.weights_json), profile_record.unknown_score)
        try:
            # Admin/manual jobs must consume fresh prepared inputs too, not only periodic jobs.
            from app.services.route_environment_inputs import prepare_environment_inputs
            prepare_environment_inputs(Path("data/osm"), Path(settings.route_source_catalog_path),
                                       Path(settings.route_environment_sources_path).parent)
            zones = scoped_zones_query(db).all()
            fingerprint = route_input_data_version(zones, profile=profile)
            db.query(ScoreBuildRecord).filter(ScoreBuildRecord.id != build.id, ScoreBuildRecord.profile_id == build.profile_id,
                                             ScoreBuildRecord.input_fingerprint == fingerprint, ScoreBuildRecord.status == "queued").update(
                {"status": "failed", "error_code": "superseded", "finished_at": datetime.now(UTC)})
            build.input_fingerprint = fingerprint
            db.commit()
            version = version_override or f"{_default_version()}-{profile.version}"
            update_builder_state(directory, status="building")
            build_and_publish_route_artifact(zones=zones, directory=directory, version=version, region=region, profile=profile,
                                             build_id=build_id, expected_input_fingerprint=fingerprint)
        except Exception as error:
            import logging
            logging.getLogger(__name__).exception("Route artifact build failed")
            db.rollback()
            build = db.get(ScoreBuildRecord, build_id)
            reason = str(error) if isinstance(error, ValueError) and str(error) in (
                "input_changed_during_build", "walking_artifact_invalid", "evaluation_readiness_regressed") else "build_failed"
            build.status, build.error_code, build.finished_at = "failed", reason, datetime.now(UTC)
            db.commit()
            update_builder_state(directory, status="failed", stale_reason=reason)
            return True
        build.status, build.artifact_version, build.finished_at = "succeeded", version, datetime.now(UTC)
        db.query(ScoringProfileRecord).filter(ScoringProfileRecord.status == "active").update({"status": "draft"})
        profile_record.status = "active"
        db.commit()
        update_builder_state(directory, status="idle")
        return True
    finally:
        db.close()


def _activate_profile(db: Session, profile_id: int) -> None:
    db.query(ScoringProfileRecord).filter(ScoringProfileRecord.status == "active").update(
        {"status": "draft"}
    )
    db.get(ScoringProfileRecord, profile_id).status = "active"


def reconcile_published_build(db: Session, directory: Path) -> bool:
    if db.query(ScoreBuildRecord.id).filter(ScoreBuildRecord.status == "building").first() is None:
        return False
    artifact = load_current_artifact(directory)
    if artifact is None:
        return False
    report = current_validation(directory)
    query = db.query(ScoreBuildRecord, ScoringProfileRecord)
    if report and report.get("build_id") is not None:
        query = query.filter(ScoreBuildRecord.id == report["build_id"])
    row = (
        query
        .join(ScoringProfileRecord, ScoringProfileRecord.id == ScoreBuildRecord.profile_id)
        .filter(
            ScoreBuildRecord.status == "building",
            ScoringProfileRecord.version == artifact.profile_version,
        )
        .order_by(ScoreBuildRecord.id)
        .first()
    )
    if row is None:
        return False
    build, profile = row
    report = current_validation(directory)
    if build.input_fingerprint is not None and (not report or report.get("build_id") != build.id or report.get("input_fingerprint") != build.input_fingerprint):
        return False
    build.status = "succeeded"
    build.artifact_version = artifact.version
    build.finished_at = datetime.now(UTC)
    _activate_profile(db, profile.id)
    db.commit()
    return True


def queue_rebuild_if_active_artifact_is_stale(db: Session, directory: Path, *, region: str = "gyeonggi", force: bool = False) -> bool:
    metadata = current_metadata(directory)
    active = ensure_build_profile(db, bootstrap=True, current_profile_version=metadata.get("profile_version"))
    zones = scoped_zones_query(db).all()
    if not zones:
        raise ValueError("safety_zones_unavailable")
    profile = ScoringProfile(active.version, json.loads(active.weights_json), active.unknown_score)
    fingerprint = route_input_data_version(zones, profile=profile)
    if (
        not force and active.status == "active" and metadata.get("schema_version") == 3
        and metadata.get("profile_version") == active.version
        and metadata.get("data_version") == fingerprint
        and (directory / metadata["version"] / "route-artifact.pickle").exists()
        and current_artifact_is_healthy(directory)
    ):
        return False
    pending = (
        db.query(ScoreBuildRecord)
        .filter(
            ScoreBuildRecord.profile_id == active.id, ScoreBuildRecord.input_fingerprint == fingerprint,
            ScoreBuildRecord.status.in_(("queued", "building")),
        )
        .first()
    )
    if pending is not None:
        return False
    last_failed = db.query(ScoreBuildRecord).filter(ScoreBuildRecord.input_fingerprint == fingerprint,
                                                 ScoreBuildRecord.status == "failed").order_by(ScoreBuildRecord.id.desc()).first()
    if last_failed is not None and not force and last_failed.finished_at:
        # Invalid unchanged inputs must not create an endless queue. Retry transient failures after 30 minutes.
        permanent = last_failed.error_code in ("evaluation_readiness_regressed", "walking_artifact_invalid")
        age = datetime.now(UTC) - last_failed.finished_at.replace(tzinfo=UTC)
        if permanent or (last_failed.error_code not in ("interrupted", "input_changed_during_build") and age.total_seconds() < 1800):
            return False
    queue_route_build(db, profile_id=active.id, input_fingerprint=fingerprint, region=region,
                      target_schema=3, reason="manual" if force else "inputs_changed")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and publish a safe-route artifact")
    parser.add_argument("--version", default=_default_version())
    parser.add_argument("--region", default="gyeonggi")
    parser.add_argument("--directory", type=Path, default=Path(settings.route_artifact_dir))
    parser.add_argument("--process-next", action="store_true")
    parser.add_argument("--bootstrap", action="store_true", help="Initialize the default profile when the registry is empty")
    parser.add_argument("--check-only", action="store_true", help="Inspect metadata without preparing files or creating jobs")
    parser.add_argument("--force", action="store_true", help="Rebuild unchanged valid inputs; validation and locking still apply")
    parser.add_argument("--queue-only", action="store_true", help="Request a build from the already running worker")
    args = parser.parse_args()
    if args.check_only:
        print(json.dumps({"current": current_metadata(args.directory), "validation": current_validation(args.directory)}))
        return
    if args.queue_only:
        with SessionLocal() as db:
            ensure_build_profile(db, bootstrap=args.bootstrap, current_profile_version=current_metadata(args.directory).get("profile_version"))
            queued = queue_rebuild_if_active_artifact_is_stale(db, args.directory, region=args.region, force=args.force)
        print("Build requested from the running worker" if queued else "No additional build needed")
        return
    with builder_lock(args.directory) as acquired:
        if not acquired:
            raise RuntimeError("builder_already_running")
        from app.services.route_environment_inputs import prepare_environment_inputs
        prepare_environment_inputs(Path("data/osm"), Path(settings.route_source_catalog_path), Path(settings.route_environment_sources_path).parent)
        if args.process_next:
            process_next_queued_build(directory=args.directory, region=args.region)
            return
        with SessionLocal() as db:
            ensure_build_profile(db, bootstrap=args.bootstrap, current_profile_version=current_metadata(args.directory).get("profile_version"))
            queue_rebuild_if_active_artifact_is_stale(db, args.directory, region=args.region, force=args.force)
        if process_next_queued_build(directory=args.directory, region=args.region, version_override=args.version):
            print(f"Processed route artifact build; inspect {args.directory / 'builder-state.json'} for the outcome")


if __name__ == "__main__":
    main()
