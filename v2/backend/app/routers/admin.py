"""Settings and audit-log endpoints (admin)."""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Setting, User
from ..schemas.common import Page
from ..schemas.payroll import SettingsOut, SettingsPatch
from ..security.deps import require
from ..services import audit, settings_store
from ..services.payroll_rules import paise_to_rupees, to_paise

router = APIRouter(tags=["admin"])


def _settings_out(db: Session) -> SettingsOut:
    c = settings_store.load(db)
    return SettingsOut(overtime_rate=paise_to_rupees(c.overtime_rate_paise), high_overtime_hours=c.high_overtime_hours,
                       unusual_salary_change_pct=c.unusual_salary_change_pct, require_separate_finalizer=c.require_separate_finalizer)


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), _: User = Depends(require("settings:read"))):
    return _settings_out(db)


@router.patch("/settings", response_model=SettingsOut)
def patch_settings(body: SettingsPatch, db: Session = Depends(get_db), user: User = Depends(require("settings:write"))):
    ch = body.model_dump(exclude_unset=True)
    mapping = {"overtime_rate": ("overtime_rate_paise", lambda v: str(to_paise(v))),
               "high_overtime_hours": ("high_overtime_hours", str), "unusual_salary_change_pct": ("unusual_salary_change_pct", str),
               "require_separate_finalizer": ("require_separate_finalizer", lambda v: "true" if v else "false")}
    changes = {}
    for k, v in ch.items():
        if v is None:
            continue
        key, conv = mapping[k]
        row = db.get(Setting, key)
        new = conv(v)
        changes[key] = {"old": row.value if row else None, "new": new}
        if row:
            row.value, row.updated_by = new, user.id
        else:
            db.add(Setting(key=key, value=new, updated_by=user.id))
    if changes:
        audit.record(db, "settings.changed", actor=user, entity_type="settings", detail={"changes": changes,
                     "note": "applies to new payroll runs only; existing runs keep their snapshot"})
        db.commit()
    return _settings_out(db)


class AuditOut(BaseModel):
    id: int
    at: datetime
    actor_username: str | None
    action: str
    entity_type: str | None
    entity_id: str | None
    detail: dict


@router.get("/audit-log", response_model=Page[AuditOut])
def audit_log(action: str | None = Query(None, max_length=64), actor: str | None = Query(None, max_length=64),
              entity_type: str | None = Query(None, max_length=40), entity_id: str | None = Query(None, max_length=40),
              page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200),
              db: Session = Depends(get_db), _: User = Depends(require("audit:read"))):
    stmt = select(AuditEvent)
    for col, v in ((AuditEvent.action, action), (AuditEvent.actor_username, actor), (AuditEvent.entity_type, entity_type), (AuditEvent.entity_id, entity_id)):
        if v:
            stmt = stmt.where(col == v)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(AuditEvent.id.desc()).limit(page_size).offset((page - 1) * page_size))
    return Page(items=[AuditOut(id=a.id, at=a.at, actor_username=a.actor_username, action=a.action, entity_type=a.entity_type,
                                entity_id=a.entity_id, detail=json.loads(a.detail)) for a in rows],
                total=total, page=page, page_size=page_size)
