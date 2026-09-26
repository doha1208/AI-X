"""적재된 안전 데이터와 로컬 OSM 도로망으로 경로 산출물을 게시한다.

사용법:
    backend/.venv/Scripts/python.exe scripts/build_route_artifacts.py
    backend/.venv/Scripts/python.exe scripts/build_route_artifacts.py --region seoul-gyeonggi

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
from app.services.safe_route import _zone_data_version, build_route_artifact
from app.services.scoring_profile import ScoringProfile
from app.services.scoring_profile_store import claim_next_queued_build
import json


def _default_version() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def build_and_publish_route_artifact(
    *, zones: list[SafetyZone], directory: Path, version: str, region: str, profile: ScoringProfile = None
) -> Path:
    """주어진 안전구역 데이터로 산출물을 만들고, 성공했을 때만 최신 버전으로 게시한다."""

    artifact = build_route_artifact(zones, version=version, region=region, **({"profile": profile} if profile else {}))
    return publish_artifact(artifact, directory)


def process_next_queued_build(*, directory: Path, region: str) -> bool:
    db = SessionLocal()
    try:
        claimed = claim_next_queued_build(db)
        if claimed is None:
            return False
        build, profile_record = claimed
        if profile_record is None:
            return True
        profile = ScoringProfile(profile_record.version, json.loads(profile_record.weights_json), profile_record.unknown_score)
        zones = scoped_zones_query(db).all()
        version = f"{_default_version()}-{profile.version}"
        try:
            build_and_publish_route_artifact(zones=zones, directory=directory, version=version, region=region, profile=profile)
        except Exception:
            build.status, build.error_code, build.finished_at = "failed", "build_failed", datetime.now(UTC)
            db.commit()
            return True
        build.status, build.artifact_version, build.finished_at = "succeeded", version, datetime.now(UTC)
        db.query(ScoringProfileRecord).filter(ScoringProfileRecord.status == "active").update({"status": "draft"})
        profile_record.status = "active"
        db.commit()
        return True
    finally:
        db.close()


def _activate_profile(db: Session, profile_id: int) -> None:
    db.query(ScoringProfileRecord).filter(ScoringProfileRecord.status == "active").update(
        {"status": "draft"}
    )
    db.get(ScoringProfileRecord, profile_id).status = "active"


def reconcile_published_build(db: Session, directory: Path) -> bool:
    artifact = load_current_artifact(directory)
    if artifact is None:
        return False
    row = (
        db.query(ScoreBuildRecord, ScoringProfileRecord)
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
    build.status = "succeeded"
    build.artifact_version = artifact.version
    build.finished_at = datetime.now(UTC)
    _activate_profile(db, profile.id)
    db.commit()
    return True


def queue_rebuild_if_active_artifact_is_stale(db: Session, directory: Path) -> bool:
    active = (
        db.query(ScoringProfileRecord)
        .filter(ScoringProfileRecord.status == "active")
        .order_by(ScoringProfileRecord.id.desc())
        .first()
    )
    if active is None:
        return False
    zones = scoped_zones_query(db).all()
    artifact = load_current_artifact(directory)
    if (
        artifact is not None
        and artifact.profile_version == active.version
        and artifact.data_version == _zone_data_version(zones)
    ):
        return False
    pending = (
        db.query(ScoreBuildRecord)
        .filter(
            ScoreBuildRecord.profile_id == active.id,
            ScoreBuildRecord.status.in_(("queued", "building")),
        )
        .first()
    )
    if pending is not None:
        return False
    db.add(ScoreBuildRecord(profile_id=active.id, status="queued"))
    db.commit()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and publish a safe-route artifact")
    parser.add_argument("--version", default=_default_version())
    parser.add_argument("--region", default="seoul-gyeonggi")
    parser.add_argument("--directory", type=Path, default=Path(settings.route_artifact_dir))
    parser.add_argument("--process-next", action="store_true")
    args = parser.parse_args()

    if args.process_next:
        if process_next_queued_build(directory=args.directory, region=args.region):
            print("Processed one queued scoring-profile build")
        return

    db = SessionLocal()
    try:
        zones = scoped_zones_query(db).all()
    finally:
        db.close()
    if not zones:
        raise RuntimeError("Safety zones are required before building route artifacts")

    artifact_dir = build_and_publish_route_artifact(
        zones=zones,
        directory=args.directory,
        version=args.version,
        region=args.region,
    )
    print(f"Published route artifact {args.version} to {artifact_dir}")


if __name__ == "__main__":
    main()
