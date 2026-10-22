"""Payslip data + PDF. Everything is read from the finalized payroll snapshot (payroll_run_items);
nothing is recalculated here, so the PDF always equals the stored record."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import PayrollRun, PayrollRunItem
from ..schemas.payslips import PayslipOut
from .payroll_rules import paise_to_rupees

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def fmt_inr(paise: int) -> str:
    """Indian digit grouping, e.g. 123456750 -> '12,34,567.50'. Pure formatting of a stored integer."""
    sign = "-" if paise < 0 else ""
    rupees, p = divmod(abs(paise), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"{sign}{s}.{p:02d}"


def period_label(period: str) -> str:
    return f"{MONTHS[int(period[5:7]) - 1]} {period[:4]}"


def load(db: Session, employee_id: int, run_id: int) -> tuple[PayrollRun, PayrollRunItem]:
    run = db.get(PayrollRun, run_id)
    item = db.scalar(select(PayrollRunItem).where(PayrollRunItem.run_id == run_id, PayrollRunItem.employee_id == employee_id))
    if not run or not item:
        raise HTTPException(404, "Payslip not found")
    if run.status == "reversed":
        raise HTTPException(409, "This payroll run was reversed; its payslips are no longer valid")
    if run.status != "finalized":
        raise HTTPException(409, "Payslips are available only after the payroll run is finalized")
    return run, item


def to_out(run: PayrollRun, i: PayrollRunItem, company: str) -> PayslipOut:
    return PayslipOut(
        run_id=run.id, period=run.period, period_label=period_label(run.period), employee_id=i.employee_id,
        employee_code=i.employee_code, employee_name=i.employee_name, department=i.department, designation=i.designation,
        basic_salary=paise_to_rupees(i.basic_paise), bonus=paise_to_rupees(i.bonus_paise), overtime_hours=Decimal(i.overtime_hours),
        overtime_rate=paise_to_rupees(i.overtime_rate_paise), overtime_pay=paise_to_rupees(i.overtime_pay_paise),
        gross_salary=paise_to_rupees(i.gross_paise), deductions=paise_to_rupees(i.deductions_paise),
        net_salary=paise_to_rupees(i.net_paise), attendance_days=i.attendance_days, finalized_at=run.finalized_at, company_name=company)


def filename(i: PayrollRunItem, run: PayrollRun) -> str:
    return f"payslip_{i.employee_code}_{run.period}.pdf"  # code is validated [A-Za-z0-9._-] at creation


def build_pdf(run: PayrollRun, i: PayrollRunItem, settings: Settings, now: datetime | None = None) -> bytes:
    now = now or datetime.now(timezone.utc)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=16, spaceAfter=2, textColor=colors.HexColor("#1f3a5f"))
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8.5, textColor=colors.HexColor("#5f636c"), leading=11)
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10, leading=13)
    navy, grid, shade = colors.HexColor("#1f3a5f"), colors.HexColor("#c2beb5"), colors.HexColor("#f4f3f0")

    def esc(t: str) -> str:
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Payslip {i.employee_code} {run.period}", author=settings.company_name, invariant=1)
    story = [Paragraph(esc(settings.company_name), h1)]
    if settings.company_address:
        story.append(Paragraph(esc(settings.company_address).replace("\n", "<br/>"), small))
    story += [Spacer(1, 6 * mm), Paragraph(f"<b>PAYSLIP — {period_label(run.period)}</b>", ParagraphStyle("t", parent=body, fontSize=12)), Spacer(1, 3 * mm)]

    info = Table([
        ["Employee ID", i.employee_code, "Pay period", run.period],
        ["Name", i.employee_name, "Attendance", f"{i.attendance_days} days"],
        ["Department", i.department, "Designation", i.designation],
    ], colWidths=[28 * mm, 58 * mm, 28 * mm, 58 * mm])
    info.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9.5), ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#5f636c")),
                              ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#5f636c")), ("BOX", (0, 0), (-1, -1), 0.5, grid),
                              ("INNERGRID", (0, 0), (-1, -1), 0.25, grid), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story += [info, Spacer(1, 5 * mm)]

    ot_desc = f"Overtime pay ({Decimal(i.overtime_hours):.2f} h x INR {fmt_inr(i.overtime_rate_paise)})"
    rows = [["Description", "Amount (INR)"],
            ["EARNINGS", ""], ["Basic salary", fmt_inr(i.basic_paise)], ["Bonus", fmt_inr(i.bonus_paise)], [ot_desc, fmt_inr(i.overtime_pay_paise)],
            ["Gross salary", fmt_inr(i.gross_paise)],
            ["DEDUCTIONS", ""], ["Deductions (as entered)", fmt_inr(i.deductions_paise)],
            ["Total deductions", fmt_inr(i.deductions_paise)],
            ["NET SALARY", fmt_inr(i.net_paise)]]
    t = Table(rows, colWidths=[122 * mm, 50 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 1), (-1, 1), shade), ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("BACKGROUND", (0, 6), (-1, 6), shade), ("FONTNAME", (0, 6), (-1, 6), "Helvetica-Bold"),
        ("FONTNAME", (0, 5), (-1, 5), "Helvetica-Bold"), ("LINEABOVE", (0, 5), (-1, 5), 0.5, grid),
        ("FONTNAME", (0, 8), (-1, 8), "Helvetica-Bold"), ("LINEABOVE", (0, 8), (-1, 8), 0.5, grid),
        ("FONTNAME", (0, 9), (-1, 9), "Helvetica-Bold"), ("FONTSIZE", (0, 9), (-1, 9), 11), ("LINEABOVE", (0, 9), (-1, 9), 1, navy), ("LINEBELOW", (0, 9), (-1, 9), 1, navy),
        ("BOX", (0, 0), (-1, -1), 0.5, grid), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [t, Spacer(1, 8 * mm),
              Paragraph("This payslip reflects the finalized payroll record. Statutory deductions (PF, ESI, tax) are not calculated by this system; "
                        "only the deduction amount entered by HR is shown.", small), Spacer(1, 2 * mm),
              Paragraph(f"Payroll run #{run.id} finalized {run.finalized_at:%Y-%m-%d %H:%M} UTC &nbsp;|&nbsp; Generated {now:%Y-%m-%d %H:%M:%S} UTC", small)]
    doc.build(story)
    return buf.getvalue()
