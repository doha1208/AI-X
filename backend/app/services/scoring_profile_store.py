import json

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


def queue_profile_build(db: Session, profile_id: int) -> ScoreBuildOut | None:
    if db.get(ScoringProfileRecord, profile_id) is None:
        return None
    build = ScoreBuildRecord(profile_id=profile_id, status="queued")
    db.add(build)
    db.commit()
    db.refresh(build)
    return ScoreBuildOut(id=build.id, profile_id=build.profile_id, status=build.status)
