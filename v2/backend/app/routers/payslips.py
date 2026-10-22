from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import get_db
from ..models import PayrollRun, PayrollRunItem, User
from ..schemas.common import Page
from ..schemas.payslips import PayslipOut, PayslipRow
from ..security.deps import get_settings_dep, require
from ..services import audit, payslips as svc
from ..services.payroll_rules import paise_to_rupees

router = APIRouter(prefix="/payslips", tags=["payslips"])


@router.get("", response_model=Page[PayslipRow])
def list_payslips(run_id: int | None = None, period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
                  employee_id: int | None = None, q: str | None = Query(None, max_length=100),
                  page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                  db: Session = Depends(get_db), _: User = Depends(require("payslips:read"))):
    """Payslips exist only for finalized runs."""
    stmt = select(PayrollRunItem, PayrollRun.period).join(PayrollRun).where(PayrollRun.status == "finalized")
    if run_id:
        stmt = stmt.where(PayrollRun.id == run_id)
    if period:
        stmt = stmt.where(PayrollRun.period == period)
    if employee_id:
        stmt = stmt.where(PayrollRunItem.employee_id == employee_id)
    if q:
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(PayrollRunItem.employee_name.like(like, escape="\\"), PayrollRunItem.employee_code.like(like, escape="\\"),
                              PayrollRunItem.department.like(like, escape="\\")))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(PayrollRun.period.desc(), PayrollRunItem.employee_code).limit(page_size).offset((page - 1) * page_size)).all()
    return Page(items=[PayslipRow(run_id=i.run_id, employee_id=i.employee_id, period=p, employee_code=i.employee_code, employee_name=i.employee_name,
                                  department=i.department, gross_salary=paise_to_rupees(i.gross_paise), deductions=paise_to_rupees(i.deductions_paise),
                                  net_salary=paise_to_rupees(i.net_paise)) for i, p in rows], total=total, page=page, page_size=page_size)


# NB: the .pdf route is registered first so "/{employee_id}/5.pdf" is never parsed by the JSON route.
@router.get("/{employee_id}/{run_id}.pdf")
def payslip_pdf(employee_id: int, run_id: int, download: bool = False, db: Session = Depends(get_db),
                user: User = Depends(require("payslips:read")), settings: Settings = Depends(get_settings_dep)):
    run, item = svc.load(db, employee_id, run_id)
    pdf = svc.build_pdf(run, item, settings)
    audit.record(db, "payslip.downloaded" if download else "payslip.viewed", actor=user, entity_type="payroll_run", entity_id=run.id,
                 detail={"employee_code": item.employee_code, "period": run.period})
    db.commit()
    disp = "attachment" if download else "inline"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'{disp}; filename="{svc.filename(item, run)}"',
                                                                 "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/{employee_id}/{run_id}", response_model=PayslipOut)
def payslip_json(employee_id: int, run_id: int, db: Session = Depends(get_db), _: User = Depends(require("payslips:read")),
                 settings: Settings = Depends(get_settings_dep)):
    run, item = svc.load(db, employee_id, run_id)
    return svc.to_out(run, item, settings.company_name)
