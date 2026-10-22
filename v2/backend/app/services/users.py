from __future__ import annotations

import re
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import User
from ..security.passwords import hash_password, validate_password_strength
from ..security.permissions import ROLES
from . import audit

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


class UserCreate(BaseModel):
    username: str
    full_name: str = Field(min_length=1, max_length=120)
    role: str
    password: str = Field(min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def _u(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError("Username must be 3-64 characters: letters, numbers, . _ -")
        return v

    @field_validator("role")
    @classmethod
    def _r(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        return v


class UserPatch(BaseModel):
    model_config = {"extra": "forbid"}
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: str | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def _r(cls, v: str | None) -> str | None:
        if v is not None and v not in ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ROLES)}")
        return v


class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserAdminOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    is_sample: bool
    created_at: datetime


def get_or_404(db: Session, user_id: int) -> User:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    return u


def _strength(pw: str) -> None:
    try:
        validate_password_strength(pw)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _other_active_admins(db: Session, exclude_id: int) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True), User.id != exclude_id)) or 0


def create(db: Session, data: UserCreate, actor: User) -> User:
    _strength(data.password)                      # cheap validation first, then the uniqueness check
    if db.scalar(select(func.count()).select_from(User).where(func.lower(User.username) == data.username.lower())):
        raise HTTPException(409, f"Username '{data.username}' is already taken")
    u = User(username=data.username, full_name=data.full_name.strip(), role=data.role, password_hash=hash_password(data.password))
    db.add(u)
    db.flush()
    audit.record(db, "user.created", actor=actor, entity_type="user", entity_id=u.id, detail={"username": u.username, "role": u.role})
    db.commit()
    return u


def update(db: Session, u: User, patch: UserPatch, actor: User) -> User:
    ch = patch.model_dump(exclude_unset=True)
    if any(v is None for v in ch.values()):
        raise HTTPException(422, "Fields cannot be null")
    if not ch:
        raise HTTPException(422, "No fields to update")
    if u.id == actor.id and ({"role", "is_active"} & ch.keys()):
        raise HTTPException(409, "You cannot change your own role or deactivate yourself. Ask another administrator.")
    leaving_admin = u.role == "admin" and u.is_active and (ch.get("role", u.role) != "admin" or ch.get("is_active", u.is_active) is False)
    if leaving_admin and _other_active_admins(db, u.id) == 0:
        raise HTTPException(409, "This is the last active administrator. Create or keep another administrator first.")
    diff = {k: {"old": getattr(u, k), "new": v} for k, v in ch.items() if getattr(u, k) != v}
    if not diff:
        return u
    for k, d in diff.items():
        setattr(u, k, d["new"])
    audit.record(db, "user.updated", actor=actor, entity_type="user", entity_id=u.id, detail={"username": u.username, "changes": diff})
    db.commit()
    return u


def reset_password(db: Session, u: User, password: str, actor: User) -> None:
    _strength(password)
    u.password_hash = hash_password(password)
    u.token_version += 1                       # every existing session of this user stops working
    audit.record(db, "user.password_reset", actor=actor, entity_type="user", entity_id=u.id, detail={"username": u.username})
    db.commit()
