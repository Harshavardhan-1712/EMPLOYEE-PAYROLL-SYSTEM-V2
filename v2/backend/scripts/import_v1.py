"""Import employees from a V1 database (employee_data.db) into V2. READ-ONLY on the V1 file.

    python -m scripts.import_v1 --v1-db ../../employee_data.db            # dry run: validate and report, write nothing
    python -m scripts.import_v1 --v1-db ../../employee_data.db --commit   # import the valid rows into the V2 database
    python -m scripts.import_v1 --v1-db ... --commit --strict             # refuse to import anything if any row has a problem

Safety: the V1 file is opened with SQLite's read-only mode, is hashed before and after (and its modification time
compared), and the run fails loudly if it changed. V1's emp_id becomes the V2 employee ID. V1 has no joining date,
so it is left empty (the review flags will say so). Rows are validated with the same rules as the employee form;
IDs that already exist in V2 are skipped, never overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import db as dbmod
from app.config import Settings, get_settings
from app.main import ensure_defaults
from app.models import Employee, SalaryHistory
from app.schemas.employees import EmployeeIn
from app.services import audit
from app.services.payroll_rules import to_paise

EXPECTED = {"emp_id", "name", "department", "designation", "basic_salary", "bonus", "deductions", "attendance", "overtime"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def open_readonly(path: Path) -> sqlite3.Connection:
    """SQLite read-only URI connection: any write attempt raises 'attempt to write a readonly database'."""
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def read_v1(path: Path) -> list[dict]:
    with open(path, "rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise ValueError("not a SQLite database")
    conn = open_readonly(path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(employees)")}
        if not cols:
            raise ValueError("no 'employees' table found")
        if EXPECTED - cols:
            raise ValueError(f"the employees table is missing column(s): {', '.join(sorted(EXPECTED - cols))}")
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM employees ORDER BY emp_id")]
    finally:
        conn.close()


def _num(v) -> str:
    return "0" if v is None else str(Decimal(str(v)))


def map_row(r: dict) -> EmployeeIn:
    return EmployeeIn.model_validate({
        "employee_code": str(r["emp_id"]), "name": (r["name"] or "").strip(), "department": (r["department"] or "").strip(),
        "designation": (r["designation"] or "").strip(), "basic_salary": _num(r["basic_salary"]), "bonus": _num(r["bonus"]),
        "deductions": _num(r["deductions"]), "overtime_hours": _num(r["overtime"]), "attendance_days": int(r["attendance"] or 0),
    })


def analyse(rows: list[dict], existing: set[str]) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        item = {"v1_id": r["emp_id"], "status": "valid", "problems": [], "data": None}
        try:
            data = map_row(r)
        except (ValidationError, ValueError, ArithmeticError) as exc:
            item["status"] = "error"
            item["problems"] = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()] if isinstance(exc, ValidationError) else [str(exc)]
        else:
            key = data.employee_code.lower()
            if key in existing:
                item["status"], item["problems"] = "duplicate", ["already exists in V2 (skipped, not overwritten)"]
            elif key in seen:
                item["status"], item["problems"] = "duplicate", ["repeated emp_id in the V1 file"]
            else:
                seen.add(key)
            item["data"] = data
        out.append(item)
    return out


def main(argv: list[str] | None = None, settings: Settings | None = None, out=print) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--v1-db", required=True, help="path to V1's employee_data.db")
    p.add_argument("--commit", action="store_true", help="write the valid rows into V2 (default: dry run)")
    p.add_argument("--strict", action="store_true", help="with --commit: import nothing if any row is invalid or duplicate")
    a = p.parse_args(argv)
    settings = settings or get_settings()
    src = Path(a.v1_db).expanduser().resolve()
    if not src.is_file():
        out(f"error: V1 database not found: {src}"); return 2
    if src == settings.db_file:
        out("error: --v1-db points at the V2 database. Give the path of V1's employee_data.db."); return 2

    before, mtime = sha256(src), src.stat().st_mtime_ns
    try:
        rows = read_v1(src)
    except (ValueError, sqlite3.DatabaseError) as exc:
        out(f"error: {src.name} is not a usable V1 database: {exc}"); return 2

    engine = dbmod.make_engine(settings)
    ensure_defaults(engine, settings)
    imported = 0
    with Session(engine) as db:
        existing = {c.lower() for c in db.scalars(select(Employee.employee_code))}
        items = analyse(rows, existing)
        valid = [i for i in items if i["status"] == "valid"]
        bad = [i for i in items if i["status"] != "valid"]
        out(f"V1 file: {src.name}  ({len(rows)} employee row(s))   mode: {'COMMIT' if a.commit else 'DRY RUN (nothing is written)'}")
        out(f"  valid: {len(valid)}   duplicates: {sum(i['status'] == 'duplicate' for i in items)}   errors: {sum(i['status'] == 'error' for i in items)}")
        for i in bad:
            out(f"  - emp_id {i['v1_id']}: {i['status']}: {'; '.join(i['problems'])}")
        if a.commit:
            if a.strict and bad:
                out("error: --strict was given and some rows have problems. Nothing was imported."); imported = -1
            else:
                for i in valid:
                    d: EmployeeIn = i["data"]
                    e = Employee(employee_code=d.employee_code, name=d.name, department=d.department, designation=d.designation, joining_date=None,
                                 basic_salary_paise=to_paise(d.basic_salary), bonus_paise=to_paise(d.bonus), deductions_paise=to_paise(d.deductions),
                                 overtime_hours=d.overtime_hours, attendance_days=d.attendance_days, is_sample=False)
                    db.add(e); db.flush()
                    db.add(SalaryHistory(employee_id=e.id, old_basic_paise=None, new_basic_paise=e.basic_salary_paise, changed_by=None))
                    imported += 1
                audit.record(db, "employee.imported_from_v1", actor_username="import_v1", entity_type="employee",
                             detail={"imported": imported, "skipped": len(bad), "source_sha256": before[:12]})
                db.commit()                                                  # one transaction: all valid rows or none
                out(f"Imported {imported} employee(s). Joining dates are empty (V1 did not store them).")
        else:
            out("Dry run only. Re-run with --commit to import the valid rows.")

    after, mtime_after = sha256(src), src.stat().st_mtime_ns
    if after != before or mtime_after != mtime:
        out("FATAL: the V1 database file changed during this run. This should be impossible; stop and investigate."); return 3
    out(f"V1 database verified unchanged (sha256 {before[:16]}…).")
    return 1 if imported == -1 else 0


if __name__ == "__main__":
    raise SystemExit(main())
