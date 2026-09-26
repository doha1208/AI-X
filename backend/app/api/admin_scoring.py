from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin, require_csrf
from app.db.session import get_db
from app.models.user import User
from app.schemas.scoring_profile import ScoreBuildOut, ScoringProfileDraftIn, ScoringProfileOut
from app.services.scoring_profile_store import (
    create_draft,
    get_active_profile,
    get_build,
    list_builds,
    list_profiles,
    queue_profile_build,
)


router = APIRouter(prefix="/admin/scoring-profiles", tags=["admin-scoring"])


@router.get("", response_model=list[ScoringProfileOut])
def read_profiles(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[ScoringProfileOut]:
    return list_profiles(db)


@router.get("/active", response_model=ScoringProfileOut | None)
def read_active_profile(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> ScoringProfileOut | None:
    return get_active_profile(db)


@router.get("/builds", response_model=list[ScoreBuildOut])
def read_builds(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> list[ScoreBuildOut]:
    return list_builds(db)


@router.get("/builds/{build_id}", response_model=ScoreBuildOut)
def read_build(
    build_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ScoreBuildOut:
    build = get_build(db, build_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="빌드 작업을 찾을 수 없습니다")
    return build


@router.post("", response_model=ScoringProfileOut, status_code=status.HTTP_201_CREATED)
def create_scoring_profile_draft(
    payload: ScoringProfileDraftIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _: None = Depends(require_csrf),
) -> ScoringProfileOut:
    try:
        return create_draft(db, payload, created_by=current_user.email)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 프로필 버전입니다")


@router.post("/{profile_id}/apply", response_model=ScoreBuildOut, status_code=status.HTTP_202_ACCEPTED)
def apply_scoring_profile(
    profile_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    _csrf: None = Depends(require_csrf),
) -> ScoreBuildOut:
    build = queue_profile_build(db, profile_id)
    if build is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="점수 프로필을 찾을 수 없습니다")
    return build
