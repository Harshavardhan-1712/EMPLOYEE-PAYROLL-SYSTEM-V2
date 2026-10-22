from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import PayrollRun, PayrollRunItem, User
from ..schemas.common import Page
from ..schemas.payroll import FinalizeIn, ItemOut, ItemPatch, ReverseIn, RunCreate, RunDetail, RunOut
from ..security.deps import require
from ..services import payroll_runs as svc

router = APIRouter(prefix="/payroll-runs", tags=["payroll"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")]


@router.get("", response_model=Page[RunOut])
def list_runs(status: Literal["draft", "reviewed", "finalized", "reversed"] | None = None, period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
              page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
              db: Session = Depends(get_db), _: User = Depends(require("payroll:read"))):
    stmt = select(PayrollRun)
    if status:
        stmt = stmt.where(PayrollRun.status == status)
    if period:
        stmt = stmt.where(PayrollRun.period == period)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(PayrollRun.period.desc(), PayrollRun.id.desc()).limit(page_size).offset((page - 1) * page_size))
    return Page(items=[svc.run_out(db, r) for r in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=RunDetail, status_code=201)
def create_run(body: RunCreate, response: Response, idempotency_key: IdemKey = None, db: Session = Depends(get_db),
               user: User = Depends(require("payroll:run"))):
    run, created = svc.create_run(db, body.period, user, idempotency_key)
    response.status_code = 201 if created else 200
    return svc.run_detail(db, run)


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: int, db: Session = Depends(get_db), _: User = Depends(require("payroll:read"))):
    return svc.run_detail(db, svc.get_or_404(db, run_id))


@router.patch("/{run_id}/items/{item_id}", response_model=ItemOut)
def edit_item(run_id: int, item_id: int, body: ItemPatch, db: Session = Depends(get_db), user: User = Depends(require("payroll:run"))):
    run = svc.get_or_404(db, run_id)
    item = db.get(PayrollRunItem, item_id)
    if not item or item.run_id != run.id:
        raise HTTPException(404, "Payroll item not found")
    return svc._item_out(svc.edit_item(db, run, item, body, user))


@router.post("/{run_id}/review", response_model=RunOut)
def review(run_id: int, db: Session = Depends(get_db), user: User = Depends(require("payroll:review"))):
    return svc.run_out(db, svc.review(db, svc.get_or_404(db, run_id), user))


@router.post("/{run_id}/reopen", response_model=RunOut)
def reopen(run_id: int, db: Session = Depends(get_db), user: User = Depends(require("payroll:review"))):
    return svc.run_out(db, svc.reopen(db, svc.get_or_404(db, run_id), user))


@router.post("/{run_id}/finalize", response_model=RunOut)
def finalize(run_id: int, body: FinalizeIn | None = None, db: Session = Depends(get_db), user: User = Depends(require("payroll:finalize"))):
    body = body or FinalizeIn()
    run, _ = svc.finalize(db, svc.get_or_404(db, run_id), user, body.acknowledge_errors, body.note)
    return svc.run_out(db, run)


@router.post("/{run_id}/reverse", response_model=RunOut)
def reverse(run_id: int, body: ReverseIn, db: Session = Depends(get_db), user: User = Depends(require("payroll:reverse"))):
    return svc.run_out(db, svc.reverse(db, svc.get_or_404(db, run_id), body.reason, user))


@router.delete("/{run_id}", status_code=204)
def delete_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require("payroll:run"))):
    svc.delete_run(db, svc.get_or_404(db, run_id), user)
    return Response(status_code=204)
