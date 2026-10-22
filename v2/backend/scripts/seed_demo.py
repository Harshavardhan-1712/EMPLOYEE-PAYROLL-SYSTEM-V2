"""Load clearly-labelled SAMPLE data into the V2 database (never V1's).

    python -m scripts.seed_demo                      # 12 sample employees, 5 finalized months + 1 draft, 4 sample users
    python -m scripts.seed_demo --months 8
    python -m scripts.seed_demo --password "a-long-demo-password"
    python -m scripts.seed_demo --reset --yes        # wipe the V2 database file and reseed (only if it holds sample data only)

Everything created is flagged is_sample and shown as sample in the UI. Passwords are generated and printed once
unless you pass --password / PV2_SEED_PASSWORD: there are no default credentials. The seeder refuses to run when the
database contains real (non-sample) employees or payroll runs.
"""
from __future__ import annotations

import argparse
import os
import random
import secrets
import sys
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import db as dbmod
from app.config import Settings, get_settings
from app.main import ensure_defaults
from app.models import Employee, PayrollRun, SalaryHistory, User
from app.security.passwords import MIN_PASSWORD_LENGTH, hash_password
from app.services import audit, payroll_runs as runs
from app.services.payroll_rules import to_paise

EMPLOYEES = [  # code, name, department, designation, basic salary (INR) -- all fictional
    ("S001", "Aarav Mehta", "Engineering", "Senior Developer", "95000"), ("S002", "Diya Nair", "Engineering", "Developer", "68000"),
    ("S003", "Kabir Rao", "Engineering", "Developer", "62000"), ("S004", "Isha Verma", "Engineering", "QA Engineer", "52000"),
    ("S005", "Rohan Das", "Engineering", "DevOps Engineer", "76000"), ("S006", "Meera Iyer", "Finance", "Finance Manager", "88000"),
    ("S007", "Arjun Pillai", "Finance", "Accountant", "46000"), ("S008", "Neha Kapoor", "Finance", "Payroll Analyst", "50000"),
    ("S009", "Vikram Joshi", "Operations", "Operations Lead", "58000"), ("S010", "Sana Khan", "Operations", "Coordinator", "34000"),
    ("S011", "Rahul Menon", "Sales", "Sales Executive", "42000"), ("S012", "Tara Bose", "Sales", "Account Manager", "64000"),
]
USERS = [("demo_admin", "Demo Administrator", "admin"), ("demo_hr", "Demo HR Editor", "hr_editor"),
         ("demo_approver", "Demo Payroll Approver", "payroll_approver"), ("demo_viewer", "Demo Viewer", "viewer")]


def shift(y: int, m: int, delta: int) -> tuple[int, int]:
    i = y * 12 + (m - 1) + delta
    return i // 12, i % 12 + 1


def has_real_data(db: Session) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Employee).where(Employee.is_sample.is_(False)))
                or db.scalar(select(func.count()).select_from(PayrollRun).where(PayrollRun.is_sample.is_(False))))


def has_sample_data(db: Session) -> bool:
    return bool(db.scalar(select(func.count()).select_from(Employee).where(Employee.is_sample.is_(True)))
                or db.scalar(select(func.count()).select_from(User).where(User.is_sample.is_(True))))


def seed(db: Session, months: int, password: str | None, today: date | None = None) -> dict:
    today = today or date.today()
    creds: dict[str, str] = {}
    users: dict[str, User] = {}
    for username, full, role in USERS:
        if db.scalar(select(User).where(User.username == username)):
            raise SystemExit(f"error: user '{username}' already exists")
        pw = password or secrets.token_urlsafe(12)
        creds[username] = pw
        u = User(username=username, full_name=full, role=role, password_hash=hash_password(pw), is_sample=True)
        db.add(u); users[role] = u
    db.flush()
    hr, approver = users["hr_editor"], users["payroll_approver"]

    ly, lm = shift(today.year, today.month, -1)                      # last complete month: left as a draft
    periods = [shift(ly, lm, -k) for k in range(months, 0, -1)]      # finalized months before it
    emps: dict[str, Employee] = {}
    for code, name, dept, desig, basic in EMPLOYEES:
        joined = date(periods[1][0], periods[1][1], 1) if code == "S010" and len(periods) > 1 else date(2023, 4, 1)  # S010 joins in month 2
        e = Employee(employee_code=code, name=name, department=dept, designation=desig, joining_date=joined, basic_salary_paise=to_paise(basic), is_sample=True)
        db.add(e); db.flush(); emps[code] = e
        db.add(SalaryHistory(employee_id=e.id, old_basic_paise=None, new_basic_paise=e.basic_salary_paise, changed_by=hr.id))
    db.commit()

    rng = random.Random(7)

    def set_month(raise_now: bool) -> None:
        for code, e in emps.items():
            if e.status != "active":
                continue
            base = Decimal(dict((c, b) for c, _, _, _, b in EMPLOYEES)[code])
            if code == "S001" and raise_now:
                base = base * Decimal("1.4")                                    # a 40% raise: shows the unusual-change flag
            e.basic_salary_paise = to_paise(base)
            e.bonus_paise = to_paise(rng.choice([0, 0, 0, 2500, 5000, 10000]))
            e.overtime_hours = Decimal(40 + rng.randint(0, 8)) if code == "S005" and rng.random() < 0.5 else Decimal(rng.choice([0, 0, 4, 8, 12, 16]))
            e.attendance_days = rng.randint(20, 26)
            e.deductions_paise = to_paise(int(base * Decimal("0.05")))          # sample deduction amounts: NOT statutory rules
        db.commit()

    for idx, (y, m) in enumerate(periods):
        set_month(raise_now=idx >= 3)
        run, _ = runs.create_run(db, f"{y}-{m:02d}", hr, None)
        runs.review(db, run, approver)
        run, _ = runs.finalize(db, run, approver, acknowledge_errors=False, note="sample data")

    emps["S011"].status, emps["S011"].deactivated_at = "inactive", datetime.now(timezone.utc)   # left before the draft month
    db.commit()
    set_month(raise_now=True)
    emps["S010"].deductions_paise = to_paise(60000)                             # draft shows a negative-net error flag to review
    db.commit()
    draft, _ = runs.create_run(db, f"{ly}-{lm:02d}", hr, None)
    audit.record(db, "seed.sample_data_loaded", actor_username="seed_demo", detail={"employees": len(EMPLOYEES), "finalized_months": len(periods), "draft": draft.period})
    db.commit()
    return {"credentials": creds, "finalized": [f"{y}-{m:02d}" for y, m in periods], "draft": draft.period}


def main(argv: list[str] | None = None, settings: Settings | None = None, out=print) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--months", type=int, default=5, help="finalized months of history (1-24, default 5; a trend chart needs 3+)")
    p.add_argument("--password", help="password for all four sample users (default: random, printed once). Also PV2_SEED_PASSWORD")
    p.add_argument("--reset", action="store_true", help="delete the V2 database file first (allowed only if it holds sample data only)")
    p.add_argument("--yes", action="store_true", help="confirm --reset")
    a = p.parse_args(argv)
    if not 1 <= a.months <= 24:
        out("error: --months must be between 1 and 24"); return 2
    pw = a.password or os.environ.get("PV2_SEED_PASSWORD")
    if pw and len(pw) < MIN_PASSWORD_LENGTH:
        out(f"error: password must be at least {MIN_PASSWORD_LENGTH} characters"); return 2
    settings = settings or get_settings()
    engine = dbmod.make_engine(settings)
    ensure_defaults(engine, settings)
    with Session(engine) as db:
        if has_real_data(db):
            out("error: this database contains real (non-sample) employees or payroll runs. The seeder will not touch it."); return 1
        if has_sample_data(db):
            if not a.reset:
                out("error: sample data is already loaded. Use --reset --yes to wipe this V2 database and reseed."); return 1
            if not a.yes:
                out("error: --reset deletes the whole V2 database file, including any user accounts created with create_admin. Add --yes to confirm."); return 1
    if a.reset:
        engine.dispose()
        for suffix in ("", "-wal", "-shm"):
            f = settings.db_file.with_name(settings.db_file.name + suffix)
            if f.exists():
                f.unlink()
        engine = dbmod.make_engine(settings)
        ensure_defaults(engine, settings)
    with Session(engine) as db:
        try:
            res = seed(db, a.months, pw)
        except SystemExit as exc:
            out(str(exc)); return 1
    out(f"Sample data loaded into the V2 database ({len(EMPLOYEES)} employees; finalized {res['finalized'][0]} to {res['finalized'][-1]}; draft {res['draft']}).")
    out("All of it is flagged as sample data. Sample users:")
    for u, pwd in res["credentials"].items():
        out(f"  {u:15} {pwd if not pw else '(the password you supplied)'}")
    if not pw:
        out("These passwords are shown once and are not stored anywhere else.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
