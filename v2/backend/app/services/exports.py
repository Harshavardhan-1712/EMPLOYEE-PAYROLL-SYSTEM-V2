"""CSV / Excel exports. Everything is built from finalized snapshots and server-side filters.

Safety: any user-controlled text that could be interpreted as a formula by a spreadsheet
(starts with = + - @ TAB or CR, ignoring leading spaces) is prefixed with an apostrophe.
Numeric columns are written as numbers and are never altered.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Employee, PayrollRun, PayrollRunItem
from .analytics import Rec, dept_rows, records
from .payroll_rules import paise_to_rupees
from .payslips import period_label

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_text(v):
    """Neutralise spreadsheet formula injection in text fields (OWASP CSV-injection guidance)."""
    if isinstance(v, str) and v.lstrip(" ").startswith(_DANGEROUS):
        return "'" + v
    return v


def money(p: int) -> str:
    return f"{paise_to_rupees(p):.2f}"


def _csv(rows: Iterable[Iterable]) -> bytes:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")  # BOM so Excel opens UTF-8 names correctly


def finalized_run(db: Session, run_id: int) -> tuple[PayrollRun, list[PayrollRunItem]]:
    run = db.get(PayrollRun, run_id)
    if not run:
        raise HTTPException(404, "Payroll run not found")
    if run.status == "reversed":
        raise HTTPException(409, "This payroll run was reversed and cannot be exported")
    if run.status != "finalized":
        raise HTTPException(409, "Only finalized payroll runs can be exported")
    items = list(db.scalars(select(PayrollRunItem).where(PayrollRunItem.run_id == run.id).order_by(PayrollRunItem.employee_code)))
    return run, items


REGISTER_HEADER = ["Employee ID", "Name", "Department", "Designation", "Basic salary", "Bonus", "Overtime hours", "Overtime rate", "Overtime pay",
                   "Gross salary", "Deductions", "Net salary", "Attendance days"]


def _register_row(i: PayrollRunItem) -> list:
    return [safe_text(i.employee_code), safe_text(i.employee_name), safe_text(i.department), safe_text(i.designation), money(i.basic_paise), money(i.bonus_paise),
            f"{Decimal(i.overtime_hours):.2f}", money(i.overtime_rate_paise), money(i.overtime_pay_paise), money(i.gross_paise), money(i.deductions_paise),
            money(i.net_paise), i.attendance_days]


def totals_of(items: list[PayrollRunItem]) -> dict[str, int]:
    return {"basic": sum(i.basic_paise for i in items), "bonus": sum(i.bonus_paise for i in items), "ot_pay": sum(i.overtime_pay_paise for i in items),
            "gross": sum(i.gross_paise for i in items), "ded": sum(i.deductions_paise for i in items), "net": sum(i.net_paise for i in items)}


def payroll_csv(run: PayrollRun, items: list[PayrollRunItem]) -> bytes:
    t = totals_of(items)
    total_row = ["TOTAL", f"{len(items)} employees", "", "", money(t["basic"]), money(t["bonus"]), f"{sum((Decimal(i.overtime_hours) for i in items), Decimal(0)):.2f}", "",
                 money(t["ot_pay"]), money(t["gross"]), money(t["ded"]), money(t["net"]), ""]
    return _csv([REGISTER_HEADER, *[_register_row(i) for i in items], total_row])


def department_csv(run: PayrollRun, items: list[PayrollRunItem]) -> bytes:
    recs = [_rec(run, i) for i in items]
    rows = dept_rows(recs)
    out = [["Department", "Employees", "Gross salary", "Deductions", "Net salary"]]
    out += [[safe_text(r.department), r.employees, f"{r.gross:.2f}", f"{r.deductions:.2f}", f"{r.net:.2f}"] for r in rows]
    out.append(["TOTAL", sum(r.employees for r in rows), f"{sum(r.gross for r in rows):.2f}", f"{sum(r.deductions for r in rows):.2f}", f"{sum(r.net for r in rows):.2f}"])
    return _csv(out)


def _rec(run: PayrollRun, i: PayrollRunItem) -> Rec:
    return Rec(run.id, run.period, run.is_sample, i.employee_code, i.employee_name, i.department, i.basic_paise, i.bonus_paise, Decimal(i.overtime_hours),
               i.overtime_pay_paise, i.gross_paise, i.deductions_paise, i.net_paise, i.attendance_days, i.flags)


def employees_csv(db: Session, status: str | None, department: str | None) -> tuple[bytes, int]:
    stmt = select(Employee).order_by(Employee.employee_code)
    if status:
        stmt = stmt.where(Employee.status == status)
    if department:
        stmt = stmt.where(Employee.department == department)
    emps = list(db.scalars(stmt))
    rows = [["Employee ID", "Name", "Department", "Designation", "Joining date", "Status", "Basic salary", "Bonus", "Deductions", "Overtime hours", "Attendance days"]]
    rows += [[safe_text(e.employee_code), safe_text(e.name), safe_text(e.department), safe_text(e.designation), e.joining_date.isoformat() if e.joining_date else "",
              e.status, money(e.basic_salary_paise), money(e.bonus_paise), money(e.deductions_paise), f"{Decimal(e.overtime_hours):.2f}", e.attendance_days] for e in emps]
    return _csv(rows), len(emps)


def analytics_csv(db: Session, p_from: str | None, p_to: str | None, department: str | None) -> tuple[bytes, int]:
    if p_from and p_to and p_from > p_to:
        raise HTTPException(422, "'from' must not be after 'to'")
    recs = records(db, p_from=p_from, p_to=p_to, department=department)
    agg: dict[tuple[str, str], list[int]] = {}
    for r in recs:
        a = agg.setdefault((r.period, r.dept), [0, 0, 0, 0, 0, 0])
        a[0] += 1; a[1] += r.gross; a[2] += r.ded; a[3] += r.net; a[4] += r.bonus; a[5] += r.ot_pay
    rows = [["Period", "Department", "Employees", "Gross salary", "Deductions", "Net salary", "Bonus", "Overtime pay"]]
    rows += [[p, safe_text(d), a[0], money(a[1]), money(a[2]), money(a[3]), money(a[4]), money(a[5])] for (p, d), a in sorted(agg.items())]
    return _csv(rows), len(agg)


# ---------------------------------------------------------------------------------------------- Excel
_NAVY, _ZEBRA, _BORDER = "1F3A5F", "FAF9F7", "C2BEB5"
_NUM = '#,##0.00;[Red]-#,##0.00'


def _header(ws, row: int, labels: list[str]) -> None:
    for c, label in enumerate(labels, 1):
        cell = ws.cell(row=row, column=c, value=label)
        cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor=_NAVY)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _widths(ws, widths: list[int]) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def payroll_xlsx(run: PayrollRun, items: list[PayrollRunItem], settings: Settings, now: datetime | None = None) -> bytes:
    now = now or datetime.now(timezone.utc)
    t = totals_of(items)
    wb = Workbook()
    thin = Side(style="thin", color=_BORDER)

    # --- Summary
    ws = wb.active; ws.title = "Summary"
    ws["A1"] = safe_text(settings.company_name); ws["A1"].font = Font(bold=True, size=14, color=_NAVY)
    ws["A2"] = f"Payroll summary — {period_label(run.period)}"; ws["A2"].font = Font(bold=True, size=12)
    rows = [("Period", run.period), ("Payroll run", f"#{run.id}"), ("Status", run.status.capitalize()), ("Finalized (UTC)", run.finalized_at.strftime("%Y-%m-%d %H:%M") if run.finalized_at else ""),
            ("Overtime rate (INR/hour)", paise_to_rupees(run.overtime_rate_paise)), ("Employees", len(items)),
            ("Total basic salary", paise_to_rupees(t["basic"])), ("Total bonus", paise_to_rupees(t["bonus"])), ("Total overtime pay", paise_to_rupees(t["ot_pay"])),
            ("Total gross salary", paise_to_rupees(t["gross"])), ("Total deductions", paise_to_rupees(t["ded"])), ("Total net salary", paise_to_rupees(t["net"])),
            ("Average net salary", paise_to_rupees(int((Decimal(t["net"]) / len(items)).quantize(Decimal(1), rounding=ROUND_HALF_UP))) if items else None),
            ("Exported (UTC)", now.strftime("%Y-%m-%d %H:%M:%S"))]
    for r, (k, v) in enumerate(rows, 4):
        ws.cell(row=r, column=1, value=k).font = Font(bold=True)
        c = ws.cell(row=r, column=2, value=v)
        if isinstance(v, Decimal):
            c.number_format = _NUM
        c.alignment = Alignment(horizontal="right")
        for col in (1, 2):
            ws.cell(row=r, column=col).border = Border(bottom=thin)
    ws.cell(row=len(rows) + 5, column=1, value="Figures are read from the finalized payroll record. No statutory deductions (PF, ESI, TDS) are calculated.").font = Font(italic=True, color="5F636C")
    _widths(ws, [30, 28])

    # --- Register
    ws = wb.create_sheet("Payroll Register")
    heads = REGISTER_HEADER
    _header(ws, 1, heads); ws.row_dimensions[1].height = 30; ws.freeze_panes = "C2"
    for r, i in enumerate(items, 2):
        vals = [safe_text(i.employee_code), safe_text(i.employee_name), safe_text(i.department), safe_text(i.designation), paise_to_rupees(i.basic_paise), paise_to_rupees(i.bonus_paise),
                Decimal(i.overtime_hours), paise_to_rupees(i.overtime_rate_paise), paise_to_rupees(i.overtime_pay_paise), paise_to_rupees(i.gross_paise),
                paise_to_rupees(i.deductions_paise), paise_to_rupees(i.net_paise), i.attendance_days]
        for c, v in enumerate(vals, 1):
            cell = ws.cell(row=r, column=c, value=v)
            if isinstance(v, Decimal):
                cell.number_format = '#,##0.00' if c == 7 else _NUM
            if r % 2 == 1:
                cell.fill = PatternFill("solid", fgColor=_ZEBRA)
            cell.border = Border(bottom=thin)
    tr = len(items) + 2
    tot = ["TOTAL", f"{len(items)} employees", "", "", paise_to_rupees(t["basic"]), paise_to_rupees(t["bonus"]), sum((Decimal(i.overtime_hours) for i in items), Decimal(0)), "",
           paise_to_rupees(t["ot_pay"]), paise_to_rupees(t["gross"]), paise_to_rupees(t["ded"]), paise_to_rupees(t["net"]), ""]
    for c, v in enumerate(tot, 1):
        cell = ws.cell(row=tr, column=c, value=v); cell.font = Font(bold=True); cell.border = Border(top=Side(style="medium", color=_NAVY))
        if isinstance(v, Decimal):
            cell.number_format = '#,##0.00' if c == 7 else _NUM
    _widths(ws, [13, 24, 18, 20, 14, 12, 10, 12, 13, 14, 13, 14, 11])

    # --- Department report
    ws = wb.create_sheet("By Department")
    _header(ws, 1, ["Department", "Employees", "Gross salary", "Deductions", "Net salary"]); ws.freeze_panes = "A2"
    drows = dept_rows([_rec(run, i) for i in items])
    for r, d in enumerate(drows, 2):
        for c, v in enumerate([safe_text(d.department), d.employees, d.gross, d.deductions, d.net], 1):
            cell = ws.cell(row=r, column=c, value=v); cell.border = Border(bottom=thin)
            if isinstance(v, Decimal):
                cell.number_format = _NUM
            if r % 2 == 1:
                cell.fill = PatternFill("solid", fgColor=_ZEBRA)
    r = len(drows) + 2
    for c, v in enumerate(["TOTAL", sum(d.employees for d in drows), sum(d.gross for d in drows), sum(d.deductions for d in drows), sum(d.net for d in drows)], 1):
        cell = ws.cell(row=r, column=c, value=v); cell.font = Font(bold=True); cell.border = Border(top=Side(style="medium", color=_NAVY))
        if isinstance(v, Decimal):
            cell.number_format = _NUM
    _widths(ws, [24, 12, 16, 16, 16])

    wb.properties.title = f"Payroll {run.period} (run #{run.id})"; wb.properties.creator = settings.company_name
    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()
