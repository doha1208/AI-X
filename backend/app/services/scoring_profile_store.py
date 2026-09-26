import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.scoring_profile import ScoreBuildRecord, ScoringProfileRecord
from app.schemas.scoring_profile import ScoringProfileDraftIn, ScoringProfileOut, ScoreBuildOut


def _to_output(record: ScoringProfileRecord) -> ScoringProfileOut:
    return ScoringProfileOut(
        id=record.id,
        version=record.version,
        name=record.name,
        description=record.description,
        weights=json.loads(record.weights_json),
        unknown_score=record.unknown_score,
        status=record.status,
        created_at=record.created_at,
        created_by=record.created_by,
    )


def _build_to_output(build: ScoreBuildRecord, profile: ScoringProfileRecord) -> ScoreBuildOut:
    return ScoreBuildOut(
        id=build.id,
        profile_id=build.profile_id,
        profile_version=profile.version,
        status=build.status,
        artifact_version=build.artifact_version,
        error_code=build.error_code,
        created_at=build.created_at,
        started_at=build.started_at,
        finished_at=build.finished_at,
    )


def create_draft(
    db: Session, payload: ScoringProfileDraftIn, *, created_by: str
) -> ScoringProfileOut:
    record = ScoringProfileRecord(
        version=payload.version,
        name=payload.name,
        description=payload.description,
        weights_json=json.dumps(payload.weights, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        unknown_score=payload.unknown_score,
        status="draft",
        created_by=created_by,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_output(record)


def list_profiles(db: Session) -> list[ScoringProfileOut]:
    records = db.query(ScoringProfileRecord).order_by(ScoringProfileRecord.id.desc()).all()
    return [_to_output(record) for record in records]


def get_active_profile(db: Session) -> ScoringProfileOut | None:
    record = (
        db.query(ScoringProfileRecord)
        .filter(ScoringProfileRecord.status == "active")
        .order_by(ScoringProfileRecord.id.desc())
        .first()
    )
    return _to_output(record) if record is not None else None


def list_builds(db: Session, limit: int = 20) -> list[ScoreBuildOut]:
    rows = (
        db.query(ScoreBuildRecord, ScoringProfileRecord)
        .join(ScoringProfileRecord, ScoringProfileRecord.id == ScoreBuildRecord.profile_id)
        .order_by(ScoreBuildRecord.id.desc())
        .limit(limit)
        .all()
    )
    return [_build_to_output(build, profile) for build, profile in rows]


def get_build(db: Session, build_id: int) -> ScoreBuildOut | None:
    row = (
        db.query(ScoreBuildRecord, ScoringProfileRecord)
        .join(ScoringProfileRecord, ScoringProfileRecord.id == ScoreBuildRecord.profile_id)
        .filter(ScoreBuildRecord.id == build_id)
        .first()
    )
    return _build_to_output(*row) if row is not None else None


def claim_next_queued_build(
    db: Session,
) -> tuple[ScoreBuildRecord, ScoringProfileRecord | None] | None:
    build = (
        db.query(ScoreBuildRecord)
        .filter(ScoreBuildRecord.status == "queued")
        .order_by(ScoreBuildRecord.id)
        .first()
    )
    if build is None:
        return None

    build.status = "building"
    build.started_at = datetime.now(UTC)
    profile = db.get(ScoringProfileRecord, build.profile_id)
    if profile is None:
        build.status = "failed"
        build.error_code = "profile_missing"
        build.finished_at = datetime.now(UTC)
        db.commit()
        return build, None

    db.commit()
    return build, profile


def queue_profile_build(db: Session, profile_id: int) -> ScoreBuildOut | None:
    profile = db.get(ScoringProfileRecord, profile_id)
    if profile is None:
        return None
    build = ScoreBuildRecord(profile_id=profile_id, status="queued")
    db.add(build)
    db.commit()
    db.refresh(build)
    return _build_to_output(build, profile)
