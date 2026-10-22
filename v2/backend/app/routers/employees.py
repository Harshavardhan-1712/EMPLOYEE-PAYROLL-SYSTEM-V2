from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas.common import Page
from ..schemas.employees import EmployeeIn, EmployeeOut, EmployeePatch
from ..security.deps import require
from ..services import employees as svc

router = APIRouter(prefix="/employees", tags=["employees"])


class ImportRow(BaseModel):
    line: int
    status: Literal["valid", "duplicate", "error"]
    errors: list[str]
    employee_code: str | None = None
    name: str | None = None


class ImportResult(BaseModel):
    committed: bool
    total_rows: int
    valid: int
    duplicates: int
    errors: int
    imported: int
    rows: list[ImportRow]


@router.get("", response_model=Page[EmployeeOut])
def list_employees(
    q: str | None = Query(None, max_length=100), department: str | None = None,
    status: Literal["active", "inactive"] | None = None,
    sort: Literal["employee_code", "name", "department", "designation", "basic_salary", "joining_date", "created_at"] = "employee_code",
    order: Literal["asc", "desc"] = "asc", page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db), _: User = Depends(require("employees:read")),
):
    rows, total = svc.list_employees(db, q=q, department=department, status=status, sort=sort, order=order,
                                     page=page, page_size=page_size)
    return Page(items=[svc.to_out(e) for e in rows], total=total, page=page, page_size=page_size)


@router.get("/departments", response_model=list[str])
def departments(db: Session = Depends(get_db), _: User = Depends(require("employees:read"))):
    from sqlalchemy import select
    from ..models import Employee
    return list(db.scalars(select(Employee.department).distinct().order_by(Employee.department)))


@router.post("", response_model=EmployeeOut, status_code=201)
def create_employee(body: EmployeeIn, db: Session = Depends(get_db), user: User = Depends(require("employees:write"))):
    return svc.to_out(svc.create(db, body, user))


@router.post("/import", response_model=ImportResult)
async def import_employees(
    file: UploadFile = File(...), commit: bool = Query(False, description="false = preview only"),
    db: Session = Depends(get_db), user: User = Depends(require("employees:import")),
):
    rows = svc.parse_csv(await file.read(svc.MAX_IMPORT_BYTES + 1), db)
    imported = svc.import_rows(db, rows, user) if commit else 0
    count = lambda s: sum(1 for r in rows if r["status"] == s)  # noqa: E731
    return ImportResult(
        committed=commit, total_rows=len(rows), valid=count("valid"), duplicates=count("duplicate"), errors=count("error"),
        imported=imported,
        rows=[ImportRow(line=r["line"], status=r["status"], errors=r["errors"],
                        employee_code=r["data"].employee_code if r["data"] else None,
                        name=r["data"].name if r["data"] else None) for r in rows])


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db), _: User = Depends(require("employees:read"))):
    return svc.to_out(svc.get_or_404(db, employee_id))


@router.patch("/{employee_id}", response_model=EmployeeOut)
def patch_employee(employee_id: int, body: EmployeePatch, db: Session = Depends(get_db),
                   user: User = Depends(require("employees:write"))):
    return svc.to_out(svc.update(db, svc.get_or_404(db, employee_id), body, user))


@router.post("/{employee_id}/deactivate", response_model=EmployeeOut)
def deactivate(employee_id: int, db: Session = Depends(get_db), user: User = Depends(require("employees:write"))):
    return svc.to_out(svc.set_status(db, svc.get_or_404(db, employee_id), "inactive", user))


@router.post("/{employee_id}/reactivate", response_model=EmployeeOut)
def reactivate(employee_id: int, db: Session = Depends(get_db), user: User = Depends(require("employees:write"))):
    return svc.to_out(svc.set_status(db, svc.get_or_404(db, employee_id), "active", user))
