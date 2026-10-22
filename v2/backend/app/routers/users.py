from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..security.deps import require
from ..services import users as svc
from ..services.users import PasswordIn, UserAdminOut, UserCreate, UserPatch

router = APIRouter(prefix="/users", tags=["users"])


def _out(u: User) -> UserAdminOut:
    return UserAdminOut(id=u.id, username=u.username, full_name=u.full_name, role=u.role, is_active=u.is_active, is_sample=u.is_sample, created_at=u.created_at)


@router.get("", response_model=list[UserAdminOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require("users:manage"))):
    return [_out(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("", response_model=UserAdminOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require("users:manage"))):
    return _out(svc.create(db, body, actor))


@router.patch("/{user_id}", response_model=UserAdminOut)
def patch_user(user_id: int, body: UserPatch, db: Session = Depends(get_db), actor: User = Depends(require("users:manage"))):
    return _out(svc.update(db, svc.get_or_404(db, user_id), body, actor))


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: int, body: PasswordIn, db: Session = Depends(get_db), actor: User = Depends(require("users:manage"))):
    svc.reset_password(db, svc.get_or_404(db, user_id), body.password, actor)
    return Response(status_code=204)
