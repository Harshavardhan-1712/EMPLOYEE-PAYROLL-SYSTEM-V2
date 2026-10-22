from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import get_db
from ..models import User
from ..security.deps import get_settings_dep, require
from ..services import audit, exports as svc

router = APIRouter(prefix="/reports", tags=["reports"])
PERIOD = r"^\d{4}-(0[1-9]|1[0-2])$"
CSV, XLSX = "text/csv; charset=utf-8", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _file(content: bytes, media: str, name: str) -> Response:
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store",
                                                        "X-Content-Type-Options": "nosniff"})


def _audit(db: Session, user: User, report: str, rows: int, **detail) -> None:
    audit.record(db, "report.exported", actor=user, entity_type="report", entity_id=report, detail={"report": report, "rows": rows, **detail})
    db.commit()


@router.get("/employees.csv")
def employees_csv(status: Literal["active", "inactive"] | None = None, department: str | None = Query(None, max_length=80),
                  db: Session = Depends(get_db), user: User = Depends(require("reports:export"))):
    data, n = svc.employees_csv(db, status, department)
    _audit(db, user, "employees.csv", n, status=status, department=department)
    return _file(data, CSV, f"employee_register_{status or 'all'}.csv")


@router.get("/payroll.csv")
def payroll_csv(run_id: int, db: Session = Depends(get_db), user: User = Depends(require("reports:export"))):
    run, items = svc.finalized_run(db, run_id)
    _audit(db, user, "payroll.csv", len(items), run_id=run.id, period=run.period)
    return _file(svc.payroll_csv(run, items), CSV, f"payroll_register_{run.period}_run{run.id}.csv")


@router.get("/payroll.xlsx")
def payroll_xlsx(run_id: int, db: Session = Depends(get_db), user: User = Depends(require("reports:export")), settings: Settings = Depends(get_settings_dep)):
    run, items = svc.finalized_run(db, run_id)
    _audit(db, user, "payroll.xlsx", len(items), run_id=run.id, period=run.period)
    return _file(svc.payroll_xlsx(run, items, settings), XLSX, f"payroll_report_{run.period}_run{run.id}.xlsx")


@router.get("/department.csv")
def department_csv(run_id: int, db: Session = Depends(get_db), user: User = Depends(require("reports:export"))):
    run, items = svc.finalized_run(db, run_id)
    _audit(db, user, "department.csv", len({i.department for i in items}), run_id=run.id, period=run.period)
    return _file(svc.department_csv(run, items), CSV, f"department_payroll_{run.period}_run{run.id}.csv")


@router.get("/analytics.csv")
def analytics_csv(period_from: str | None = Query(None, alias="from", pattern=PERIOD), period_to: str | None = Query(None, alias="to", pattern=PERIOD),
                  department: str | None = Query(None, max_length=80), db: Session = Depends(get_db), user: User = Depends(require("reports:export"))):
    data, n = svc.analytics_csv(db, period_from, period_to, department)
    _audit(db, user, "analytics.csv", n, period_from=period_from, period_to=period_to, department=department)
    return _file(data, CSV, f"analytics_{period_from or 'start'}_to_{period_to or 'latest'}.csv")
