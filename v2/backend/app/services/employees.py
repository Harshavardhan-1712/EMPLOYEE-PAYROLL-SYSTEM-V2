from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Employee, SalaryHistory, User
from ..schemas.employees import EmployeeIn, EmployeeOut, EmployeePatch
from . import audit
from .payroll_rules import paise_to_rupees, to_paise

SORTABLE = {"employee_code": Employee.employee_code, "name": Employee.name, "department": Employee.department,
            "designation": Employee.designation, "basic_salary": Employee.basic_salary_paise,
            "joining_date": Employee.joining_date, "created_at": Employee.created_at}
MAX_IMPORT_BYTES, MAX_IMPORT_ROWS = 1_000_000, 5000
CSV_ALIASES = {"emp_id": "employee_code", "id": "employee_code", "basic": "basic_salary", "overtime": "overtime_hours",
               "attendance": "attendance_days", "employee_id": "employee_code"}


def to_out(e: Employee) -> EmployeeOut:
    return EmployeeOut(
        id=e.id, employee_code=e.employee_code, name=e.name, department=e.department, designation=e.designation,
        joining_date=e.joining_date, status=e.status, basic_salary=paise_to_rupees(e.basic_salary_paise),
        bonus=paise_to_rupees(e.bonus_paise), deductions=paise_to_rupees(e.deductions_paise),
        overtime_hours=Decimal(e.overtime_hours), attendance_days=e.attendance_days, is_sample=e.is_sample,
        created_at=e.created_at, updated_at=e.updated_at)


def get_or_404(db: Session, emp_id: int) -> Employee:
    e = db.get(Employee, emp_id)
    if not e:
        raise HTTPException(404, "Employee not found")
    return e


def _build(data: EmployeeIn) -> Employee:
    return Employee(
        employee_code=data.employee_code, name=data.name, department=data.department, designation=data.designation,
        joining_date=data.joining_date, basic_salary_paise=to_paise(data.basic_salary), bonus_paise=to_paise(data.bonus),
        deductions_paise=to_paise(data.deductions), overtime_hours=data.overtime_hours, attendance_days=data.attendance_days)


def code_exists(db: Session, code: str) -> bool:
    return db.scalar(select(func.count()).select_from(Employee).where(func.lower(Employee.employee_code) == code.lower())) > 0


def create(db: Session, data: EmployeeIn, actor: User) -> Employee:
    if code_exists(db, data.employee_code):  # case-insensitive: E1 and e1 are the same employee
        raise HTTPException(409, f"Employee ID '{data.employee_code}' already exists")
    e = _build(data)
    db.add(e)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"Employee ID '{data.employee_code}' already exists")
    db.add(SalaryHistory(employee_id=e.id, old_basic_paise=None, new_basic_paise=e.basic_salary_paise, changed_by=actor.id))
    audit.record(db, "employee.created", actor=actor, entity_type="employee", entity_id=e.id,
                 detail={"employee_code": e.employee_code})
    db.commit()
    return e


def update(db: Session, e: Employee, patch: EmployeePatch, actor: User) -> Employee:
    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(422, "No fields to update")
    diff: dict[str, dict] = {}
    money = {"basic_salary": "basic_salary_paise", "bonus": "bonus_paise", "deductions": "deductions_paise"}
    for k, v in changes.items():
        if v is None and k != "joining_date":
            raise HTTPException(422, f"{k} cannot be null")
        col, new = (money[k], to_paise(v)) if k in money else (k, v)
        old = getattr(e, col)
        if old != new:
            diff[k] = {"old": str(old), "new": str(new)}
            setattr(e, col, new)
    if not diff:
        return e
    if "basic_salary" in diff:
        db.add(SalaryHistory(employee_id=e.id, old_basic_paise=int(diff["basic_salary"]["old"]),
                             new_basic_paise=e.basic_salary_paise, changed_by=actor.id))
        audit.record(db, "employee.salary_changed", actor=actor, entity_type="employee", entity_id=e.id,
                     detail={"employee_code": e.employee_code, "old_basic_paise": diff["basic_salary"]["old"],
                             "new_basic_paise": diff["basic_salary"]["new"]})
    audit.record(db, "employee.updated", actor=actor, entity_type="employee", entity_id=e.id,
                 detail={"employee_code": e.employee_code, "fields": sorted(diff)})
    db.commit()
    return e


def set_status(db: Session, e: Employee, status: str, actor: User) -> Employee:
    if e.status == status:
        return e
    e.status = status
    e.deactivated_at = datetime.now(timezone.utc) if status == "inactive" else None
    audit.record(db, f"employee.{'deactivated' if status == 'inactive' else 'reactivated'}", actor=actor,
                 entity_type="employee", entity_id=e.id, detail={"employee_code": e.employee_code})
    db.commit()
    return e


def _like(s: str) -> str:
    return "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def list_employees(db: Session, *, q: str | None, department: str | None, status: str | None, sort: str, order: str,
                   page: int, page_size: int) -> tuple[list[Employee], int]:
    stmt = select(Employee)
    if q:
        p = _like(q.strip())
        stmt = stmt.where(or_(*[c.like(p, escape="\\") for c in (Employee.name, Employee.employee_code,
                                                                  Employee.department, Employee.designation)]))
    if department:
        stmt = stmt.where(Employee.department == department)
    if status:
        stmt = stmt.where(Employee.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    col = SORTABLE[sort]
    stmt = stmt.order_by(col.desc() if order == "desc" else col.asc(), Employee.id)
    return list(db.scalars(stmt.limit(page_size).offset((page - 1) * page_size))), total


# ---------------------------------------------------------------- CSV import (preview / commit)
def parse_csv(raw: bytes, db: Session) -> list[dict]:
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "File too large (max 1 MB)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "File must be UTF-8 encoded CSV")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(422, "CSV has no header row")
    names = [CSV_ALIASES.get(h.strip().lower(), h.strip().lower()) for h in reader.fieldnames]
    required = {"employee_code", "name", "department", "designation", "basic_salary"}
    missing = required - set(names)
    if missing:
        raise HTTPException(422, f"Missing required column(s): {', '.join(sorted(missing))}")
    if len(set(names)) != len(names):
        raise HTTPException(422, "Duplicate column names in header")
    existing = {c.lower() for c in db.scalars(select(Employee.employee_code))}
    seen: dict[str, int] = {}
    rows: list[dict] = []
    for i, rec in enumerate(reader, start=2):  # line 1 is the header
        if len(rows) >= MAX_IMPORT_ROWS:
            raise HTTPException(413, f"Too many rows (max {MAX_IMPORT_ROWS})")
        row = {n: (v or "").strip() for n, v in zip(names, rec.values()) if n}
        if None in rec:
            rows.append({"line": i, "status": "error", "errors": ["Row has more fields than the header"], "data": None})
            continue
        row = {k: v for k, v in row.items() if v != "" or k in required}
        try:
            data = EmployeeIn.model_validate(row)
        except ValidationError as exc:
            errs = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
            rows.append({"line": i, "status": "error", "errors": errs, "data": None})
            continue
        key = data.employee_code.lower()
        if key in existing:
            rows.append({"line": i, "status": "duplicate", "errors": ["Employee ID already exists (row skipped, not overwritten)"], "data": data})
        elif key in seen:
            rows.append({"line": i, "status": "duplicate", "errors": [f"Duplicate of line {seen[key]} in this file"], "data": data})
        else:
            seen[key] = i
            rows.append({"line": i, "status": "valid", "errors": [], "data": data})
    return rows


def import_rows(db: Session, rows: list[dict], actor: User) -> int:
    n = 0
    for r in rows:
        if r["status"] != "valid":
            continue
        e = _build(r["data"])
        db.add(e)
        db.flush()
        db.add(SalaryHistory(employee_id=e.id, old_basic_paise=None, new_basic_paise=e.basic_salary_paise, changed_by=actor.id))
        n += 1
    skipped = len(rows) - n
    audit.record(db, "employee.imported", actor=actor, entity_type="employee",
                 detail={"imported": n, "skipped": skipped})
    db.commit()  # single transaction: all valid rows or none
    return n
