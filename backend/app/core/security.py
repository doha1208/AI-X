import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.models.user import AuthSession, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "exp": expire, "type": token_type}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: str) -> str:
    return _create_token(
        subject, timedelta(minutes=settings.access_token_expire_minutes), "access"
    )


def _refresh_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_refresh_token() -> tuple[str, str]:
    session_id = secrets.token_urlsafe(18)
    secret = secrets.token_urlsafe(32)
    return session_id, f"{session_id}.{secret}"


def _refresh_session_for_token(db: Session, token: str) -> AuthSession | None:
    session_id, separator, _ = token.partition(".")
    if not separator or not session_id:
        return None
    session = db.get(AuthSession, session_id)
    # SQLite stores DATETIME without timezone information, so refresh-session
    # persistence and comparison both use a UTC-naive representation.
    if session is None or session.revoked_at is not None or session.expires_at <= datetime.utcnow():
        return None
    if not hmac.compare_digest(session.token_hash, _refresh_token_hash(token)):
        return None
    return session


def create_refresh_session(db: Session, user: User, *, persistent: bool) -> str:
    session_id, token = _new_refresh_token()
    db.add(
        AuthSession(
            id=session_id,
            user_id=user.id,
            token_hash=_refresh_token_hash(token),
            persistent=persistent,
            expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return token


def rotate_refresh_session(db: Session, token: str) -> tuple[User, str, bool] | None:
    session = _refresh_session_for_token(db, token)
    if session is None:
        return None
    user = db.get(User, session.user_id)
    if user is None:
        return None
    session.revoked_at = datetime.utcnow()
    session_id, rotated_token = _new_refresh_token()
    db.add(
        AuthSession(
            id=session_id,
            user_id=user.id,
            token_hash=_refresh_token_hash(rotated_token),
            persistent=session.persistent,
            expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    db.commit()
    return user, rotated_token, session.persistent


def revoke_refresh_session(db: Session, token: str | None) -> None:
    if not token:
        return
    session = _refresh_session_for_token(db, token)
    if session is not None:
        session.revoked_at = datetime.utcnow()
        db.commit()


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
