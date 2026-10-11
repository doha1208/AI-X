import hmac

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User

def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    token = request.cookies.get("access_token")
    payload = decode_token(token) if token else None
    if payload is None or payload.get("type") != "access":
        raise credentials_error

    user = db.query(User).filter(User.email == payload.get("sub")).first()
    if user is None:
        raise credentials_error
    return user


def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("x-csrf-token")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    admin_emails = {email.strip().casefold() for email in settings.admin_emails.split(",") if email.strip()}
    if current_user.email.casefold() not in admin_emails:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다",
        )
    return current_user
