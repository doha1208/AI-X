from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_csrf
from app.db.session import get_db
from app.models.user import RouteHistory, User
from app.schemas.route_history import RouteHistoryCreate, RouteHistoryItem, RouteHistoryOut, RouteHistorySettings

router = APIRouter(prefix="/me/route-history", tags=["route-history"])

def output(user: User, db: Session) -> RouteHistoryOut:
    rows = db.query(RouteHistory).filter(RouteHistory.user_id == user.id).order_by(RouteHistory.last_used_at.desc()).limit(10).all()
    return RouteHistoryOut(remember_route_history=user.remember_route_history, items=[RouteHistoryItem(start={"label": r.start_label, "lat": r.start_lat, "lng": r.start_lng}, end={"label": r.end_label, "lat": r.end_lat, "lng": r.end_lng}, last_used_at=r.last_used_at) for r in rows])

@router.get("", response_model=RouteHistoryOut)
def list_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return output(user, db)

@router.post("", response_model=RouteHistoryOut, dependencies=[Depends(require_csrf)])
def save_history(payload: RouteHistoryCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.remember_route_history:
        row = db.query(RouteHistory).filter_by(user_id=user.id, start_lat=payload.start.lat, start_lng=payload.start.lng, end_lat=payload.end.lat, end_lng=payload.end.lng).first()
        if row is None:
            row = RouteHistory(user_id=user.id, start_label=payload.start.label, start_lat=payload.start.lat, start_lng=payload.start.lng, end_label=payload.end.label, end_lat=payload.end.lat, end_lng=payload.end.lng)
            db.add(row)
        else:
            row.start_label, row.end_label = payload.start.label, payload.end.label
        row.last_used_at = datetime.now(timezone.utc)
        db.flush()
        stale = db.query(RouteHistory).filter(RouteHistory.user_id == user.id).order_by(RouteHistory.last_used_at.desc()).offset(10).all()
        for item in stale: db.delete(item)
        db.commit()
    return output(user, db)

@router.patch("/settings", response_model=RouteHistoryOut, dependencies=[Depends(require_csrf)])
def settings(payload: RouteHistorySettings, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.remember_route_history = payload.remember_route_history
    db.commit()
    return output(user, db)

@router.delete("", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)])
def clear_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(RouteHistory).filter(RouteHistory.user_id == user.id).delete()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
