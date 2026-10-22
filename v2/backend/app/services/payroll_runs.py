from __future__ import annotations

import calendar
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Employee, PayrollRun, PayrollRunItem, User
from ..schemas.payroll import FlagOut, ItemOut, ItemPatch, RunDetail, RunOut
from . import audit, flags as flagmod, settings_store
from .payroll_rules import PayrollInputError, compute_payroll, paise_to_rupees, to_paise


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_404(db: Session, run_id: int) -> PayrollRun:
    r = db.get(PayrollRun, run_id)
    if not r:
        raise HTTPException(404, "Payroll run not found")
    return r


def validate_period(period: str, today: date | None = None) -> None:
    today = today or date.today()
    y, m = int(period[:4]), int(period[5:7])
    if (y, m) > (today.year, today.month):
        raise HTTPException(422, "Payroll period cannot be in the future")
    if y < 2000:
        raise HTTPException(422, "Payroll period is too far in the past")


def _previous_basics(db: Session, period: str) -> dict[int, int]:
    """employee_id -> basic from that employee's latest finalized item in an earlier period."""
    rows = db.execute(
        select(PayrollRunItem.employee_id, PayrollRunItem.basic_paise, PayrollRun.period)
        .join(PayrollRun).where(PayrollRun.status == "finalized", PayrollRun.period < period)
        .order_by(PayrollRun.period)).all()
    return {emp: basic for emp, basic, _ in rows}  # later periods overwrite earlier ones


def _flags(period, res, joining, prev, cfg, attendance) -> str:
    fl = flagmod.evaluate(period=period, net_paise=res.net_paise, overtime_hours=res.overtime_hours,
                          attendance_days=attendance, basic_paise=res.basic_paise, joining_date=joining,
                          previous_basic_paise=prev, cfg=cfg)
    return json.dumps([f.as_dict() for f in fl])


def create_run(db: Session, period: str, actor: User, idem_key: str | None) -> tuple[PayrollRun, bool]:
    if idem_key:
        existing = db.scalar(select(PayrollRun).where(PayrollRun.idempotency_key == idem_key))
        if existing:
            if existing.period != period:
                raise HTTPException(409, "Idempotency-Key was already used for a different request")
            return existing, False
    validate_period(period)
    live = db.scalar(select(PayrollRun).where(PayrollRun.period == period, PayrollRun.status != "reversed"))
    if live:
        raise HTTPException(409, f"A payroll run for {period} already exists (run #{live.id}, {live.status})")
    y, m = int(period[:4]), int(period[5:7])
    last_day = date(y, m, calendar.monthrange(y, m)[1])
    emps = db.scalars(select(Employee).where(Employee.status == "active").order_by(Employee.employee_code)).all()
    emps = [e for e in emps if e.joining_date is None or e.joining_date <= last_day]  # eligibility rule
    if not emps:
        raise HTTPException(422, "No eligible employees for this period")
    cfg = settings_store.load(db)
    prev = _previous_basics(db, period)
    run = PayrollRun(period=period, status="draft", overtime_rate_paise=cfg.overtime_rate_paise,
                     idempotency_key=idem_key, created_by=actor.id, is_sample=all(e.is_sample for e in emps))
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"A payroll run for {period} already exists")
    for e in emps:
        res = compute_payroll(basic_paise=e.basic_salary_paise, bonus_paise=e.bonus_paise, overtime_hours=e.overtime_hours,
                              deductions_paise=e.deductions_paise, overtime_rate_paise=cfg.overtime_rate_paise)
        db.add(PayrollRunItem(
            run_id=run.id, employee_id=e.id, employee_code=e.employee_code, employee_name=e.name, department=e.department,
            designation=e.designation, basic_paise=res.basic_paise, bonus_paise=res.bonus_paise,
            overtime_hours=res.overtime_hours, overtime_rate_paise=res.overtime_rate_paise,
            overtime_pay_paise=res.overtime_pay_paise, gross_paise=res.gross_paise, deductions_paise=res.deductions_paise,
            net_paise=res.net_paise, attendance_days=e.attendance_days,
            flags=_flags(period, res, e.joining_date, prev.get(e.id), cfg, e.attendance_days)))
    audit.record(db, "payroll.run_created", actor=actor, entity_type="payroll_run", entity_id=run.id,
                 detail={"period": period, "employees": len(emps)})
    db.commit()
    return run, True


def _require_status(run: PayrollRun, *allowed: str, action: str) -> None:
    if run.status not in allowed:
        raise HTTPException(409, f"Cannot {action}: run is {run.status}")


def edit_item(db: Session, run: PayrollRun, item: PayrollRunItem, patch: ItemPatch, actor: User) -> PayrollRunItem:
    _require_status(run, "draft", action="edit items")
    ch = patch.model_dump(exclude_unset=True)
    if not ch or any(v is None for v in ch.values()):
        raise HTTPException(422, "Provide at least one non-null field")
    old = {"bonus": item.bonus_paise, "deductions": item.deductions_paise, "overtime_hours": str(item.overtime_hours),
           "attendance_days": item.attendance_days}
    bonus = to_paise(ch["bonus"]) if "bonus" in ch else item.bonus_paise
    ded = to_paise(ch["deductions"]) if "deductions" in ch else item.deductions_paise
    ot = ch.get("overtime_hours", item.overtime_hours)
    att = ch.get("attendance_days", item.attendance_days)
    try:
        res = compute_payroll(basic_paise=item.basic_paise, bonus_paise=bonus, overtime_hours=ot, deductions_paise=ded,
                              overtime_rate_paise=item.overtime_rate_paise)
    except PayrollInputError as exc:
        raise HTTPException(422, str(exc))
    emp = db.get(Employee, item.employee_id)
    cfg = settings_store.load(db)
    item.bonus_paise, item.deductions_paise, item.overtime_hours = res.bonus_paise, res.deductions_paise, res.overtime_hours
    item.overtime_pay_paise, item.gross_paise, item.net_paise, item.attendance_days = res.overtime_pay_paise, res.gross_paise, res.net_paise, att
    item.flags = _flags(run.period, res, emp.joining_date if emp else None, _previous_basics(db, run.period).get(item.employee_id), cfg, att)
    audit.record(db, "payroll.item_edited", actor=actor, entity_type="payroll_run", entity_id=run.id,
                 detail={"employee_code": item.employee_code, "fields": sorted(ch), "before": old,
                         "after": {"bonus": bonus, "deductions": ded, "overtime_hours": str(res.overtime_hours), "attendance_days": att}})
    db.commit()
    return item


def review(db: Session, run: PayrollRun, actor: User) -> PayrollRun:
    _require_status(run, "draft", action="review")
    run.status, run.reviewed_by, run.reviewed_at = "reviewed", actor.id, _now()
    audit.record(db, "payroll.run_reviewed", actor=actor, entity_type="payroll_run", entity_id=run.id, detail={"period": run.period})
    db.commit()
    return run


def reopen(db: Session, run: PayrollRun, actor: User) -> PayrollRun:
    _require_status(run, "reviewed", action="reopen")
    run.status, run.reviewed_by, run.reviewed_at = "draft", None, None
    audit.record(db, "payroll.run_reopened", actor=actor, entity_type="payroll_run", entity_id=run.id, detail={"period": run.period})
    db.commit()
    return run


def finalize(db: Session, run: PayrollRun, actor: User, acknowledge_errors: bool, note: str | None) -> tuple[PayrollRun, bool]:
    """Returns (run, changed). Re-finalizing an already-finalized run is a safe no-op (idempotent)."""
    if run.status == "finalized":
        return run, False
    _require_status(run, "reviewed", action="finalize (review it first)")
    if settings_store.load(db).require_separate_finalizer and run.created_by == actor.id:
        audit.record(db, "access.denied", actor=actor, entity_type="payroll_run", entity_id=run.id, detail={"rule": "separate_finalizer"})
        db.commit()
        raise HTTPException(403, "Separation of duties is enabled: the person who created a run cannot finalize it. Ask another approver.")
    items = db.scalars(select(PayrollRunItem).where(PayrollRunItem.run_id == run.id)).all()
    if not items:
        raise HTTPException(409, "Run has no items")
    err_items = [i for i in items if any(f["severity"] == "error" for f in json.loads(i.flags))]
    if err_items and not acknowledge_errors:
        raise HTTPException(409, f"{len(err_items)} item(s) have error-level flags "
                                 f"({', '.join(sorted({i.employee_code for i in err_items})[:10])}). "
                                 "Fix them or finalize with acknowledge_errors=true.")
    for i in items:  # integrity: stored figures must equal a fresh calculation from stored inputs
        r = compute_payroll(basic_paise=i.basic_paise, bonus_paise=i.bonus_paise, overtime_hours=i.overtime_hours,
                            deductions_paise=i.deductions_paise, overtime_rate_paise=i.overtime_rate_paise)
        if (r.overtime_pay_paise, r.gross_paise, r.net_paise) != (i.overtime_pay_paise, i.gross_paise, i.net_paise):
            raise HTTPException(409, f"Integrity check failed for {i.employee_code}; run not finalized")
    now = _now()
    t_g, t_d, t_n = sum(i.gross_paise for i in items), sum(i.deductions_paise for i in items), sum(i.net_paise for i in items)
    res = db.execute(update(PayrollRun).where(PayrollRun.id == run.id, PayrollRun.status == "reviewed").values(
        status="finalized", finalized_by=actor.id, finalized_at=now, employee_count=len(items),
        total_gross_paise=t_g, total_deductions_paise=t_d, total_net_paise=t_n))
    if res.rowcount != 1:  # lost a race with another request
        db.rollback()
        db.refresh(run)
        if run.status == "finalized":
            return run, False
        raise HTTPException(409, "Run changed state during finalization")
    audit.record(db, "payroll.run_finalized", actor=actor, entity_type="payroll_run", entity_id=run.id,
                 detail={"period": run.period, "employees": len(items), "total_net_paise": t_n,
                         "acknowledged_error_items": len(err_items) if acknowledge_errors else 0, "note": note})
    db.commit()
    db.refresh(run)
    return run, True


def reverse(db: Session, run: PayrollRun, reason: str, actor: User) -> PayrollRun:
    _require_status(run, "finalized", action="reverse")
    run.status, run.reversed_by, run.reversed_at, run.reversal_reason = "reversed", actor.id, _now(), reason.strip()
    audit.record(db, "payroll.run_reversed", actor=actor, entity_type="payroll_run", entity_id=run.id,
                 detail={"period": run.period, "reason": reason.strip(), "total_net_paise": run.total_net_paise})
    db.commit()
    return run


def delete_run(db: Session, run: PayrollRun, actor: User) -> None:
    _require_status(run, "draft", "reviewed", action="delete")
    db.execute(delete(PayrollRunItem).where(PayrollRunItem.run_id == run.id))
    db.delete(run)
    audit.record(db, "payroll.run_deleted", actor=actor, entity_type="payroll_run", entity_id=run.id, detail={"period": run.period})
    db.commit()


# ------------------------------------------------------------------------------------- presenters
def _item_out(i: PayrollRunItem) -> ItemOut:
    return ItemOut(
        id=i.id, employee_id=i.employee_id, employee_code=i.employee_code, employee_name=i.employee_name,
        department=i.department, designation=i.designation, basic_salary=paise_to_rupees(i.basic_paise),
        bonus=paise_to_rupees(i.bonus_paise), overtime_hours=Decimal(i.overtime_hours),
        overtime_rate=paise_to_rupees(i.overtime_rate_paise), overtime_pay=paise_to_rupees(i.overtime_pay_paise),
        gross_salary=paise_to_rupees(i.gross_paise), deductions=paise_to_rupees(i.deductions_paise),
        net_salary=paise_to_rupees(i.net_paise), attendance_days=i.attendance_days,
        flags=[FlagOut(**f) for f in json.loads(i.flags)])


def run_out(db: Session, r: PayrollRun) -> RunOut:
    items = db.scalars(select(PayrollRunItem).where(PayrollRunItem.run_id == r.id)).all()
    snap = r.status in ("finalized", "reversed") and r.total_net_paise is not None
    g, d, n, c = ((r.total_gross_paise, r.total_deductions_paise, r.total_net_paise, r.employee_count) if snap else
                  (sum(i.gross_paise for i in items), sum(i.deductions_paise for i in items),
                   sum(i.net_paise for i in items), len(items)))
    sev = [{f["severity"] for f in json.loads(i.flags)} for i in items]
    return RunOut(
        id=r.id, period=r.period, status=r.status, is_sample=r.is_sample, overtime_rate=paise_to_rupees(r.overtime_rate_paise),
        employee_count=c, total_gross=paise_to_rupees(g), total_deductions=paise_to_rupees(d), total_net=paise_to_rupees(n),
        error_flag_items=sum("error" in s for s in sev), warning_flag_items=sum("warning" in s for s in sev),
        created_at=r.created_at, reviewed_at=r.reviewed_at, finalized_at=r.finalized_at, reversed_at=r.reversed_at,
        reversal_reason=r.reversal_reason, totals_source="snapshot" if snap else "live")


def run_detail(db: Session, r: PayrollRun) -> RunDetail:
    items = db.scalars(select(PayrollRunItem).where(PayrollRunItem.run_id == r.id).order_by(PayrollRunItem.employee_code)).all()
    return RunDetail(**run_out(db, r).model_dump(), items=[_item_out(i) for i in items])
