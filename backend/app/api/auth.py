import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_csrf
from app.core.security import (
    create_access_token,
    create_refresh_session,
    hash_password,
    revoke_refresh_session,
    rotate_refresh_session,
    verify_password,
)
from app.core.config import auth_cookie_secure, settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import CsrfTokenOut, UserCreate, UserLogin, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_options(*, http_only: bool) -> dict:
    return {"httponly": http_only, "secure": auth_cookie_secure(), "samesite": "lax", "path": "/"}


def _set_session_cookies(response: Response, user: User, refresh_token: str, *, remember_me: bool) -> None:
    response.set_cookie("access_token", create_access_token(user.email), **_cookie_options(http_only=True))
    refresh_options = _cookie_options(http_only=True)
    if remember_me:
        refresh_options["max_age"] = settings.refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie("refresh_token", refresh_token, **refresh_options)
    response.set_cookie("csrf_token", secrets.token_urlsafe(32), **_cookie_options(http_only=False))


def _clear_session_cookies(response: Response) -> None:
    for name in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(name, path="/", secure=auth_cookie_secure(), samesite="lax")


@router.get("/csrf", response_model=CsrfTokenOut)
def csrf(response: Response) -> CsrfTokenOut:
    token = secrets.token_urlsafe(32)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie("csrf_token", token, **_cookie_options(http_only=False))
    return CsrfTokenOut(csrf_token=token)


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=UserOut)
def login(payload: UserLogin, response: Response, db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")

    _set_session_cookies(
        response,
        user,
        create_refresh_session(db, user, persistent=payload.remember_me),
        remember_me=payload.remember_me,
    )
    return user


@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    rotated = rotate_refresh_session(db, request.cookies.get("refresh_token", ""))
    if rotated is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user, refresh_token, remember_me = rotated
    _set_session_cookies(response, user, refresh_token, remember_me=remember_me)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db), _: None = Depends(require_csrf)):
    revoke_refresh_session(db, request.cookies.get("refresh_token"))
    _clear_session_cookies(response)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
