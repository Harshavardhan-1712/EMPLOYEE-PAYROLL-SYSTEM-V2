
from __future__ import annotations

import jwt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import get_db
from ..models import User
from ..security.deps import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    current_user,
    get_settings_dep,
    issue_token,
)
from ..security.passwords import (
    hash_password,
    validate_password_strength,
    verify_password,
)
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


class LoginOut(UserOut):
    csrf_token: str


class CsrfOut(BaseModel):
    csrf_token: str


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        full_name=u.full_name,
        role=u.role,
        permissions=sorted(ROLE_PERMISSIONS[u.role]),
    )


def _set_auth_cookies(
    response: Response,
    token: str,
    csrf: str,
    settings: Settings,
) -> None:
    max_age = settings.session_minutes * 60

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=max_age,
        httponly=True,
        samesite="none",
        secure=True,
        path="/",
    )

    response.set_cookie(
        key=CSRF_COOKIE,
        value=csrf,
        max_age=max_age,
        httponly=False,
        samesite="none",
        secure=True,
        path="/",
    )


@router.post("/login", response_model=LoginOut)
def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> LoginOut:

    limiter = request.app.state.login_limiter

    key = (
        f"{request.client.host if request.client else 'unknown'}"
        f"|{body.username.lower()}"
    )

    wait = limiter.retry_after(key)

    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many failed attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )

    user = db.scalar(
        select(User).where(User.username == body.username)
    )

    ok = verify_password(
        body.password,
        user.password_hash if user else None,
    )

    if not (ok and user and user.is_active):
        limiter.record_failure(key)

        audit.record(
            db,
            "auth.login_failed",
            actor_username=body.username[:64],
        )

        db.commit()

        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
        )

    limiter.reset(key)

    token, csrf = issue_token(user, settings)

    _set_auth_cookies(
        response,
        token,
        csrf,
        settings,
    )

    audit.record(db, "auth.login", actor=user)
    db.commit()

    user_data = _user_out(user)

    return LoginOut(
        id=user_data.id,
        username=user_data.username,
        full_name=user_data.full_name,
        role=user_data.role,
        permissions=user_data.permissions,
        csrf_token=csrf,
    )


@router.get("/csrf", response_model=CsrfOut)
def get_csrf_token(
    request: Request,
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings_dep),
) -> CsrfOut:
    """
    Restore the CSRF token from the authenticated JWT session.
    Used when the frontend reloads and loses its in-memory token.
    """

    session = request.cookies.get(SESSION_COOKIE)

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    try:
        claims = jwt.decode(
            session,
            settings.jwt_secret,
            algorithms=["HS256"],
        )

        csrf = claims.get("csrf")

        if not csrf:
            raise HTTPException(
                status_code=401,
                detail="Invalid session",
            )

        return CsrfOut(csrf_token=str(csrf))

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid session",
        )


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:

    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="none",
    )

    response.delete_cookie(
        key=CSRF_COOKIE,
        path="/",
        secure=True,
        httponly=False,
        samesite="none",
    )

    response.status_code = 204

    return response


@router.get("/me", response_model=UserOut)
def me(
    user: User = Depends(current_user),
) -> UserOut:
    return _user_out(user)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordIn,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings_dep),
) -> Response:

    if not verify_password(
        body.current_password,
        user.password_hash,
    ):
        audit.record(
            db,
            "auth.password_change_failed",
            actor=user,
        )

        db.commit()

        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect",
        )

    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=422,
            detail="The new password must be different from the current one",
        )

    try:
        validate_password_strength(body.new_password)

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    user.password_hash = hash_password(body.new_password)
    user.token_version += 1

    audit.record(
        db,
        "auth.password_changed",
        actor=user,
    )

    db.commit()

    token, csrf = issue_token(user, settings)

    _set_auth_cookies(
        response,
        token,
        csrf,
        settings,
    )

    response.status_code = 204

    return response
