"""Analytics and dashboard figures.

Source of truth: finalized payroll snapshots (payroll_run_items of runs with status 'finalized').
Draft, reviewed and reversed runs are never counted. The employees table is used only for *current*
headcount and data-quality checks. Money stays in integer paise until the final conversion.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Employee, PayrollRun, PayrollRunItem
from ..schemas.analytics import (AnalyticsSummary, AttentionItem, Bucket, ChangeRow, Comparison, DashboardSummary, DeptRow, Extreme,
                                 OvertimeDept, OvertimeRow, QualityCheck, QualityFlag, RunBrief, TrendPoint)
from . import settings_store
from .payroll_rules import paise_to_rupees

TREND_MIN_PERIODS = 3
D0 = Decimal(0)


@dataclass(frozen=True)
class Rec:  # one finalized pay record (employee x period)
    run_id: int
    period: str
    sample: bool
    code: str
    name: str
    dept: str
    basic: int
    bonus: int
    ot_hours: Decimal
    ot_pay: int
    gross: int
    ded: int
    net: int
    att: int
    flags: str


def rupees(p: int) -> Decimal:
    return paise_to_rupees(p)


def pct(change: int, base: int) -> Decimal | None:
    if base <= 0:
        return None
    return (Decimal(change) * 100 / Decimal(base)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def avg_paise(total: int, n: int) -> int:
    """Mean in paise, rounded half-up (same rule as the payroll engine; Python round() would be half-even)."""
    return int((Decimal(total) / n).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def month_index(period: str) -> int:
    return int(period[:4]) * 12 + int(period[5:7])


def records(db: Session, *, p_from: str | None = None, p_to: str | None = None, department: str | None = None, period: str | None = None) -> list[Rec]:
    stmt = (select(PayrollRunItem, PayrollRun.period, PayrollRun.is_sample).join(PayrollRun, PayrollRun.id == PayrollRunItem.run_id)
            .where(PayrollRun.status == "finalized"))
    if period:
        stmt = stmt.where(PayrollRun.period == period)
    if p_from:
        stmt = stmt.where(PayrollRun.period >= p_from)
    if p_to:
        stmt = stmt.where(PayrollRun.period <= p_to)
    if department:
        stmt = stmt.where(PayrollRunItem.department == department)
    stmt = stmt.order_by(PayrollRun.period, PayrollRunItem.employee_code)
    return [Rec(i.run_id, per, samp, i.employee_code, i.employee_name, i.department, i.basic_paise, i.bonus_paise, Decimal(i.overtime_hours),
                i.overtime_pay_paise, i.gross_paise, i.deductions_paise, i.net_paise, i.attendance_days, i.flags) for i, per, samp in db.execute(stmt)]


def finalized_periods(db: Session) -> list[str]:
    return list(db.scalars(select(PayrollRun.period).where(PayrollRun.status == "finalized").order_by(PayrollRun.period)))


def dept_rows(recs: list[Rec]) -> list[DeptRow]:
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for r in recs:
        a = agg[r.dept]; a[0] += 1; a[1] += r.gross; a[2] += r.ded; a[3] += r.net
    return [DeptRow(department=d, employees=a[0], gross=rupees(a[1]), deductions=rupees(a[2]), net=rupees(a[3])) for d, a in sorted(agg.items())]


def trend_points(recs: list[Rec]) -> list[TrendPoint]:
    by: dict[str, list[Rec]] = defaultdict(list)
    for r in recs:
        by[r.period].append(r)
    out = []
    for per in sorted(by):
        rs = by[per]
        out.append(TrendPoint(period=per, employees=len(rs), gross=rupees(sum(r.gross for r in rs)), deductions=rupees(sum(r.ded for r in rs)),
                              net=rupees(sum(r.net for r in rs)), bonus=rupees(sum(r.bonus for r in rs)), overtime_pay=rupees(sum(r.ot_pay for r in rs)),
                              overtime_hours=sum((r.ot_hours for r in rs), D0)))
    return out


def _raw_net(recs: list[Rec], per: str) -> tuple[int, int]:
    rs = [r for r in recs if r.period == per]
    return sum(r.net for r in rs), len(rs)


# --------------------------------------------------------------------------------- dashboard
def dashboard(db: Session, period: str | None) -> DashboardSummary:
    periods = finalized_periods(db)
    if period and period not in periods:
        raise HTTPException(404, f"No finalized payroll for {period}")
    sel = period or (periods[-1] if periods else None)
    active = db.scalar(select(func.count()).select_from(Employee).where(Employee.status == "active")) or 0
    inactive = db.scalar(select(func.count()).select_from(Employee).where(Employee.status == "inactive")) or 0
    sample_emps = db.scalar(select(func.count()).select_from(Employee).where(Employee.is_sample.is_(True))) or 0

    recent = [RunBrief(id=r.id, period=r.period, status=r.status, employee_count=len(r.items) if r.employee_count is None else r.employee_count,
                       total_net=rupees(r.total_net_paise if r.total_net_paise is not None else sum(i.net_paise for i in r.items)),
                       is_sample=r.is_sample, created_at=r.created_at)
              for r in db.scalars(select(PayrollRun).order_by(PayrollRun.id.desc()).limit(5))]

    attention: list[AttentionItem] = []
    for r in db.scalars(select(PayrollRun).where(PayrollRun.status.in_(("draft", "reviewed"))).order_by(PayrollRun.period)):
        flags = [json.loads(i.flags) for i in r.items]
        errs = sum(any(f["severity"] == "error" for f in fl) for fl in flags)
        warns = sum(any(f["severity"] == "warning" for f in fl) for fl in flags)
        extra = f" {errs} item(s) with error flags." if errs else (f" {warns} item(s) with warnings." if warns else "")
        attention.append(AttentionItem(kind="open_run", severity="error" if errs else ("warning" if warns else "info"), link=f"/payroll-runs/{r.id}",
                                       message=f"{r.period} payroll is {r.status} and not finalized.{extra}"))
    missing = db.scalar(select(func.count()).select_from(Employee).where(Employee.status == "active", Employee.joining_date.is_(None))) or 0
    if missing:
        attention.append(AttentionItem(kind="missing_joining_date", severity="warning", link="/employees?status=active",
                                       message=f"{missing} active employee(s) have no joining date recorded."))

    base = dict(active_employees=active, inactive_employees=inactive, sample_employees=sample_emps, available_periods=periods, selected_period=sel,
                trend_min_periods=TREND_MIN_PERIODS, recent_runs=recent, attention=attention)
    if not sel:
        return DashboardSummary(**base, has_history=False, run_id=None, employee_count=0, total_gross=D0, total_deductions=D0, total_net=D0,
                                average_net=None, total_bonus=D0, total_overtime_pay=D0, comparison=None, departments=[], trend=[], includes_sample_data=False)

    cur = records(db, period=sel)
    allrecs = records(db)
    g, d, n = (sum(r.gross for r in cur), sum(r.ded for r in cur), sum(r.net for r in cur))
    prior = [p for p in periods if p < sel]
    comparison = None
    if prior:
        pp = prior[-1]
        pn, pc = _raw_net(allrecs, pp)
        comparison = Comparison(period=pp, employee_count=pc, total_net=rupees(pn), net_change=rupees(n - pn), net_change_pct=pct(n - pn, pn),
                                adjacent_month=month_index(sel) - month_index(pp) == 1)
    avg = rupees(avg_paise(n, len(cur))) if cur else None
    return DashboardSummary(**base, has_history=True, run_id=cur[0].run_id if cur else None, employee_count=len(cur), total_gross=rupees(g),
                            total_deductions=rupees(d), total_net=rupees(n), average_net=avg, total_bonus=rupees(sum(r.bonus for r in cur)),
                            total_overtime_pay=rupees(sum(r.ot_pay for r in cur)), comparison=comparison, departments=dept_rows(cur),
                            trend=trend_points(allrecs), includes_sample_data=any(r.sample for r in cur))


# --------------------------------------------------------------------------------- analytics
def distribution(nets: list[int], buckets: int = 6) -> list[Bucket]:
    if not nets:
        return []
    lo, hi = min(nets), max(nets)
    if lo == hi:
        return [Bucket(start=rupees(lo), end=rupees(hi), count=len(nets))]
    span = hi - lo + 1
    raw = -(-span // buckets)                                  # ceil
    step = 10 ** max(2, len(str(raw)) - 1)                      # nice round width in paise (>= Rs 1)
    width = -(-raw // step) * step
    start = (lo // width) * width
    n_b = (hi - start) // width + 1
    counts = [0] * n_b
    for v in nets:
        counts[(v - start) // width] += 1
    return [Bucket(start=rupees(start + i * width), end=rupees(start + (i + 1) * width), count=c) for i, c in enumerate(counts)]


def analytics(db: Session, p_from: str | None, p_to: str | None, department: str | None) -> AnalyticsSummary:
    if p_from and p_to and p_from > p_to:
        raise HTTPException(422, "'from' must not be after 'to'")
    cfg = settings_store.load(db)
    periods = finalized_periods(db)
    all_depts = sorted({r for r in db.scalars(select(PayrollRunItem.department).join(PayrollRun).where(PayrollRun.status == "finalized").distinct())})
    recs = records(db, p_from=p_from, p_to=p_to, department=department)
    trend = trend_points(recs)

    nets = [r.net for r in recs]
    ext = lambda r: Extreme(employee_code=r.code, employee_name=r.name, period=r.period, net=rupees(r.net))  # noqa: E731
    hi = max(recs, key=lambda r: (r.net, r.period, r.code)) if recs else None
    lo = min(recs, key=lambda r: (r.net, r.period, r.code)) if recs else None

    totals = {"gross": rupees(sum(r.gross for r in recs)), "deductions": rupees(sum(r.ded for r in recs)), "net": rupees(sum(r.net for r in recs)),
              "bonus": rupees(sum(r.bonus for r in recs)), "overtime_pay": rupees(sum(r.ot_pay for r in recs)),
              "overtime_hours": sum((r.ot_hours for r in recs), D0)}

    changes: list[ChangeRow] = []
    for prev, cur in zip(trend, trend[1:]):                      # only calendar-adjacent periods are compared
        if month_index(cur.period) - month_index(prev.period) == 1:
            pn, cn = sum(r.net for r in recs if r.period == prev.period), sum(r.net for r in recs if r.period == cur.period)
            changes.append(ChangeRow(period=cur.period, prior_period=prev.period, employee_count=cur.employees, employee_count_change=cur.employees - prev.employees,
                                     net=cur.net, net_change=rupees(cn - pn), net_change_pct=pct(cn - pn, pn)))

    atts = [r.att for r in recs]
    attendance = {"average": (Decimal(sum(atts)) / len(atts)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if atts else None,
                  "min": min(atts) if atts else None, "max": max(atts) if atts else None, "records": len(atts)}

    ot = [r for r in recs if r.ot_hours > 0]
    ot_dept: dict[str, list] = defaultdict(lambda: [D0, 0])
    for r in ot:
        ot_dept[r.dept][0] += r.ot_hours; ot_dept[r.dept][1] += r.ot_pay
    top = sorted(ot, key=lambda r: (-r.ot_hours, r.period, r.code))[:5]

    flag_counts: dict[str, int] = defaultdict(int)
    flagged: list[QualityFlag] = []
    for r in recs:
        for f in json.loads(r.flags):
            flag_counts[f["code"]] += 1
            if len(flagged) < 100:
                flagged.append(QualityFlag(run_id=r.run_id, period=r.period, employee_code=r.code, employee_name=r.name, code=f["code"], severity=f["severity"], message=f["message"]))

    emp_q = select(func.count()).select_from(Employee).where(Employee.status == "active")
    if department:
        emp_q = emp_q.where(Employee.department == department)
    checks = []
    miss = db.scalar(emp_q.where(Employee.joining_date.is_(None))) or 0
    zero = db.scalar(emp_q.where(Employee.basic_salary_paise == 0)) or 0
    if miss:
        checks.append(QualityCheck(code="missing_joining_date", count=miss, message="Active employees without a joining date"))
    if zero:
        checks.append(QualityCheck(code="zero_basic_salary", count=zero, message="Active employees with a basic salary of 0"))

    return AnalyticsSummary(
        from_period=p_from, to_period=p_to, department=department, available_periods=periods, departments=all_depts,
        periods_in_scope=len(trend), record_count=len(recs), includes_sample_data=any(r.sample for r in recs), totals=totals,
        average_net=rupees(avg_paise(sum(nets), len(nets))) if nets else None, highest_net=ext(hi) if hi else None, lowest_net=ext(lo) if lo else None,
        distribution=distribution(nets), by_department=dept_rows(recs), trend=trend, changes=changes, attendance=attendance,
        overtime_records=len(ot), overtime_avg_hours=(sum((r.ot_hours for r in ot), D0) / len(ot)).quantize(Decimal("0.01")) if ot else None,
        overtime_top=[OvertimeRow(employee_code=r.code, employee_name=r.name, period=r.period, hours=r.ot_hours, pay=rupees(r.ot_pay)) for r in top],
        overtime_by_department=[OvertimeDept(department=d, hours=v[0], pay=rupees(v[1])) for d, v in sorted(ot_dept.items())],
        flag_counts=dict(sorted(flag_counts.items())), flagged_records=flagged, employee_checks=checks,
        thresholds={"high_overtime_hours": cfg.high_overtime_hours, "unusual_salary_change_pct": cfg.unusual_salary_change_pct})
