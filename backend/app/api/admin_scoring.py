from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.scoring_profile import ScoringProfileDraftIn, ScoringProfileOut
from app.services.scoring_profile_store import create_draft, get_active_profile, list_profiles


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


@router.post("", response_model=ScoringProfileOut, status_code=status.HTTP_201_CREATED)
def create_scoring_profile_draft(
    payload: ScoringProfileDraftIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ScoringProfileOut:
    try:
        return create_draft(db, payload, created_by=current_user.email)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 사용 중인 프로필 버전입니다")
