from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..models import User
from ..services import audit
from .permissions import has_permission

SESSION_COOKIE = "pv2_session"
CSRF_COOKIE = "pv2_csrf"
CSRF_HEADER = "X-CSRF-Token"
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def issue_token(user: User, settings: Settings) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"sub": str(user.id), "csrf": csrf, "tv": user.token_version, "iat": now, "exp": now + timedelta(minutes=settings.session_minutes)},
        settings.jwt_secret, algorithm="HS256",
    )
    return token, csrf


def get_settings_dep() -> Settings:
    return get_settings()


def current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    csrf_header: str | None = Header(default=None, alias=CSRF_HEADER),
) -> User:
    unauth = HTTPException(status_code=401, detail="Not authenticated")
    if not session:
        raise unauth
    try:
        claims = jwt.decode(session, settings.jwt_secret, algorithms=["HS256"])
        user_id = int(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauth
    # Re-check the user in the DB on every request so deactivation / role changes take effect immediately.
    user = db.get(User, user_id)
    if user is None or not user.is_active or int(claims.get("tv", 0)) != user.token_version:
        raise unauth          # unknown/deactivated user, or the password changed since this session began
    if request.method in _UNSAFE:
        if not csrf_header or not hmac.compare_digest(csrf_header, str(claims.get("csrf", ""))):
            raise HTTPException(status_code=403, detail="Missing or invalid CSRF token")
    return user


def require(permission: str):
    """Server-side authorization. The permission is exposed as `dep.__permission__` so a test can prove
    that every non-public route declares one."""
    def dep(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if not has_permission(user.role, permission):
            audit.record(db, "access.denied", actor=user, detail={"permission": permission, "method": request.method, "path": request.url.path})
            db.commit()
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    dep.__permission__ = permission  # type: ignore[attr-defined]
    return dep
