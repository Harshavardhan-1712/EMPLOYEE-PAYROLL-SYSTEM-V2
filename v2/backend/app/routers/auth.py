from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import get_db
from ..models import User
from ..security.deps import CSRF_COOKIE, SESSION_COOKIE, current_user, get_settings_dep, issue_token
from ..security.passwords import hash_password, validate_password_strength, verify_password
from ..security.permissions import ROLE_PERMISSIONS
from ..services import audit
from ..services.users import ChangePasswordIn

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    permissions: list[str]


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, username=u.username, full_name=u.full_name, role=u.role,
                   permissions=sorted(ROLE_PERMISSIONS[u.role]))


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db),
          settings: Settings = Depends(get_settings_dep)) -> UserOut:
    limiter = request.app.state.login_limiter
    key = f"{request.client.host if request.client else 'unknown'}|{body.username.lower()}"
    wait = limiter.retry_after(key)
    if wait:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.",
                            headers={"Retry-After": str(wait)})
    user = db.scalar(select(User).where(User.username == body.username))
    ok = verify_password(body.password, user.password_hash if user else None)
    if not (ok and user and user.is_active):
        limiter.record_failure(key)
        audit.record(db, "auth.login_failed", actor_username=body.username[:64])
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    limiter.reset(key)
    token, csrf = issue_token(user, settings)
    max_age = settings.session_minutes * 60
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="lax",
                        secure=settings.cookie_secure, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, samesite="lax",
                        secure=settings.cookie_secure, path="/")
    audit.record(db, "auth.login", actor=user)
    db.commit()
    return _user_out(user)


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> UserOut:
    return _user_out(user)


@router.post("/change-password", status_code=204)
def change_password(body: ChangePasswordIn, response: Response, db: Session = Depends(get_db), user: User = Depends(current_user),
                    settings: Settings = Depends(get_settings_dep)) -> Response:
    if not verify_password(body.current_password, user.password_hash):
        audit.record(db, "auth.password_change_failed", actor=user)
        db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail="The new password must be different from the current one")
    try:
        validate_password_strength(body.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1                      # signs out every other session
    audit.record(db, "auth.password_changed", actor=user)
    db.commit()
    token, csrf = issue_token(user, settings)    # keep *this* session alive with a fresh token
    max_age = settings.session_minutes * 60
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, samesite="lax", secure=settings.cookie_secure, path="/")
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, samesite="lax", secure=settings.cookie_secure, path="/")
    response.status_code = 204
    return response
