"""Seed and V1-import commands. V1's own database.py / payroll.py are loaded from a temp COPY, never from the real tree."""
from __future__ import annotations

import hashlib
import importlib.util
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import db as dbmod
from app.config import V1_ROOT, Settings
from app.main import create_app, ensure_defaults
from app.models import AuditEvent, Employee, PayrollRun, SalaryHistory, User
from scripts import import_v1, seed_demo


def run_cmd(mod, argv, settings):
    lines: list[str] = []
    rc = mod.main(argv, settings=settings, out=lines.append)
    return rc, "\n".join(lines)


def count(engine, model, *where):
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def client_for(settings, engine, username, password):
    c = TestClient(create_app(settings, engine))
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = c.cookies.get("pv2_csrf")
    return c


# ============================================================================== seed
PW = "a-long-demo-password"


def test_seed_builds_a_coherent_clearly_labelled_demo(settings, engine):
    rc, out = run_cmd(seed_demo, ["--password", PW], settings)
    assert rc == 0 and "flagged as sample data" in out and PW not in out           # a supplied password is never echoed
    assert count(engine, Employee) == 12 and count(engine, Employee, Employee.is_sample.is_(False)) == 0
    assert count(engine, User, User.is_sample.is_(True)) == 4 and count(engine, PayrollRun, PayrollRun.status == "finalized") == 5
    assert count(engine, PayrollRun, PayrollRun.status == "draft") == 1 and count(engine, PayrollRun, PayrollRun.is_sample.is_(False)) == 0
    c = client_for(settings, engine, "demo_viewer", PW)
    d = c.get("/api/dashboard/summary").json()
    assert d["includes_sample_data"] is True and d["has_history"] and len(d["trend"]) == 5 and d["sample_employees"] == 12
    a = c.get("/api/analytics/summary").json()
    assert {"unusual_salary_change", "high_overtime"} <= set(a["flag_counts"])        # the demo exercises the review flags
    counts = [p["employees"] for p in a["trend"]]
    assert counts[0] == 11 and counts[1:] == [12, 12, 12, 12]                         # one employee joins in month 2
    draft = next(r for r in c.get("/api/payroll-runs").json()["items"] if r["status"] == "draft")
    assert draft["employee_count"] == 11 and draft["error_flag_items"] >= 1          # a deactivated employee drops out; a negative net to review
    detail = c.get(f"/api/payroll-runs/{draft['id']}").json()
    assert any(f["code"] == "negative_net" for i in detail["items"] for f in i["flags"])


def test_seeded_finalized_history_is_real_snapshot_data(settings, engine):
    run_cmd(seed_demo, ["--password", PW], settings)
    ad = client_for(settings, engine, "demo_admin", PW)
    fin = [r for r in ad.get("/api/payroll-runs?status=finalized").json()["items"]]
    assert len(fin) == 5 and all(r["totals_source"] == "snapshot" and r["is_sample"] for r in fin)
    r0 = fin[0]
    emp = ad.get(f"/api/payroll-runs/{r0['id']}").json()["items"][0]
    assert ad.get(f"/api/payslips/{emp['employee_id']}/{r0['id']}.pdf").content[:5] == b"%PDF-"
    ad.post("/api/auth/logout")


def test_each_sample_user_has_its_role_and_no_default_password(settings, engine):
    rc, out = run_cmd(seed_demo, [], settings)
    assert rc == 0 and "shown once" in out
    creds = {l.split()[0]: l.split()[1] for l in out.splitlines() if l.startswith("  demo_")}
    assert set(creds) == {"demo_admin", "demo_hr", "demo_approver", "demo_viewer"} and all(len(p) >= 12 for p in creds.values())
    assert len(set(creds.values())) == 4                                              # four different passwords
    with Session(engine) as s:
        roles = {u.username: u.role for u in s.scalars(select(User))}
    assert roles == {"demo_admin": "admin", "demo_hr": "hr_editor", "demo_approver": "payroll_approver", "demo_viewer": "viewer"}
    assert client_for(settings, engine, "demo_approver", creds["demo_approver"]).get("/api/auth/me").json()["role"] == "payroll_approver"


def test_seed_refuses_twice_and_reset_needs_confirmation(settings, engine):
    assert run_cmd(seed_demo, ["--password", PW], settings)[0] == 0
    rc, out = run_cmd(seed_demo, ["--password", PW], settings)
    assert rc == 1 and "already loaded" in out
    rc, out = run_cmd(seed_demo, ["--password", PW, "--reset"], settings)
    assert rc == 1 and "--yes" in out and count(engine, Employee) == 12
    rc, _ = run_cmd(seed_demo, ["--password", "another-long-password", "--reset", "--yes"], settings)
    eng2 = dbmod.make_engine(settings)
    assert rc == 0 and count(eng2, Employee) == 12 and count(eng2, User) == 4        # wiped and reseeded, not doubled
    assert client_for(settings, eng2, "demo_admin", "another-long-password")
    eng2.dispose()


def test_seed_never_touches_real_data(settings, engine):
    with Session(engine) as s:
        s.add(Employee(employee_code="REAL1", name="Real Person", department="HR", designation="Head", basic_salary_paise=1, is_sample=False)); s.commit()
    rc, out = run_cmd(seed_demo, ["--password", PW], settings)
    assert rc == 1 and "real (non-sample)" in out
    assert count(engine, Employee) == 1 and count(engine, User) == 0
    rc, _ = run_cmd(seed_demo, ["--password", PW, "--reset", "--yes"], settings)     # --reset cannot override this guard either
    assert rc == 1 and count(engine, Employee) == 1


@pytest.mark.parametrize("argv,code", [(["--months", "0"], 2), (["--months", "99"], 2), (["--password", "short"], 2)])
def test_seed_argument_validation(settings, engine, argv, code):
    assert run_cmd(seed_demo, argv, settings)[0] == code and count(engine, Employee) == 0


def test_seed_is_deterministic_and_audited(settings, engine, tmp_path):
    run_cmd(seed_demo, ["--password", PW, "--months", "4"], settings)
    other = Settings(env="test", database_path=str(tmp_path / "other.db"), jwt_secret="x" * 40, _env_file=None)
    e2 = dbmod.make_engine(other); ensure_defaults(e2, other)
    run_cmd(seed_demo, ["--password", PW, "--months", "4"], other)
    totals = lambda eng: [(r.period, r.total_net_paise) for r in Session(eng).scalars(select(PayrollRun).where(PayrollRun.status == "finalized").order_by(PayrollRun.period))]  # noqa: E731
    assert totals(engine) == totals(e2) and len(totals(engine)) == 4
    assert count(engine, AuditEvent, AuditEvent.action == "seed.sample_data_loaded") == 1
    e2.dispose()


def test_seed_refuses_to_target_v1(tmp_path):
    with pytest.raises(ValueError, match="V1"):
        Settings(env="test", database_path=str(V1_ROOT / "employee_data.db"), jwt_secret="x" * 40, _env_file=None)


# ============================================================================== V1 import
@pytest.fixture()
def v1(tmp_path):
    """A real V1 database created by V1's own code (database.py copied to a temp dir)."""
    d = tmp_path / "v1copy"; d.mkdir()
    for f in ("database.py", "payroll.py"):
        shutil.copy2(V1_ROOT / f, d / f)
    sys.path.insert(0, str(d))
    mods = {}
    try:
        for name in ("database", "payroll"):
            spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
            m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m); mods[name] = m
        mods["database"].create_table()
        for row in [(101, "Priya Sharma", "Engineering", "Developer", 50000.0, 5000.0, 2500.5, 22, 10), (102, "Arjun Mehta", "Finance", "Analyst", 30000.0, 0.0, 1000.0, 20, 0),
                    (103, "Meera Iyer", "Operations", "Lead", 45000.75, 1000.0, 500.0, 25, 45)]:
            mods["database"].add_employee(*row)
        yield mods, d / "employee_data.db"
    finally:
        sys.path.remove(str(d))
        for n in ("database", "payroll"):
            sys.modules.pop(n, None)


def fingerprint(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns, p.stat().st_size


def test_dry_run_reports_and_writes_nothing(settings, engine, v1):
    mods, path = v1
    before = fingerprint(path)
    rc, out = run_cmd(import_v1, ["--v1-db", str(path)], settings)
    assert rc == 0 and "DRY RUN" in out and "valid: 3" in out and "verified unchanged" in out
    assert count(engine, Employee) == 0 and count(engine, AuditEvent) == 0
    assert fingerprint(path) == before


def test_commit_imports_exact_values_and_leaves_v1_byte_identical(settings, engine, v1):
    mods, path = v1
    before = fingerprint(path)
    rc, out = run_cmd(import_v1, ["--v1-db", str(path), "--commit"], settings)
    assert rc == 0 and "Imported 3" in out
    assert fingerprint(path) == before                                                # hash, mtime and size all unchanged
    with Session(engine) as s:
        e = s.scalar(select(Employee).where(Employee.employee_code == "101"))
        assert (e.name, e.department, e.designation, e.basic_salary_paise, e.bonus_paise, e.deductions_paise, e.attendance_days) == ("Priya Sharma", "Engineering", "Developer", 5_000_000, 500_000, 250_050, 22)
        assert float(e.overtime_hours) == 10 and e.joining_date is None and e.is_sample is False and e.status == "active"
        assert s.scalar(select(Employee.basic_salary_paise).where(Employee.employee_code == "103")) == 4_500_075      # paise-exact, no float drift
        assert s.scalar(select(func.count()).select_from(SalaryHistory)) == 3
        ev = s.scalar(select(AuditEvent).where(AuditEvent.action == "employee.imported_from_v1"))
        assert ev.actor_username == "import_v1" and '"imported": 3' in ev.detail and str(path) not in ev.detail


def test_imported_employees_produce_the_same_pay_as_v1(settings, engine, v1):
    """End to end: import -> V2 payroll run -> compare each net/gross with V1's own formulas."""
    mods, path = v1
    run_cmd(import_v1, ["--v1-db", str(path), "--commit"], settings)
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True); conn.row_factory = sqlite3.Row
    v1_rows = [dict(r) for r in conn.execute("SELECT * FROM employees")]; conn.close()
    with Session(engine) as s:
        from app.models import User as U
        from app.security.passwords import hash_password
        s.add(U(username="hr", full_name="HR", role="hr_editor", password_hash=hash_password("correct-horse-battery"))); s.commit()
    c = client_for(settings, engine, "hr", "correct-horse-battery")
    run = c.post("/api/payroll-runs", json={"period": "2026-05"}).json()
    by = {i["employee_code"]: i for i in run["items"]}
    assert len(by) == 3
    for r in v1_rows:
        expect = mods["payroll"].compute_payroll_for_employee(r)
        got = by[str(r["emp_id"])]
        assert float(got["overtime_pay"]) == pytest.approx(expect["overtime_pay"], abs=0.005)
        assert float(got["gross_salary"]) == pytest.approx(expect["gross_salary"], abs=0.005)
        assert float(got["net_salary"]) == pytest.approx(expect["net_salary"], abs=0.005)
    assert any(f["code"] == "missing_joining_date" for i in run["items"] for f in i["flags"])       # honest about the missing date


def _tamper(path: Path, rows):
    conn = sqlite3.connect(path)
    for r in rows:
        conn.execute("INSERT INTO employees VALUES (?,?,?,?,?,?,?,?,?)", r)
    conn.commit(); conn.close()


def test_bad_and_duplicate_rows_are_reported_and_skipped(settings, engine, v1):
    mods, path = v1
    _tamper(path, [(201, "Neg Pay", "Eng", "Dev", -5.0, 0, 0, 0, 0), (202, "", "Eng", "Dev", 1000.0, 0, 0, 0, 0), (203, "Too Present", "Eng", "Dev", 1000.0, 0, 0, 99, 0),
                   (204, "Odd Cents", "Eng", "Dev", 1000.123, 0, 0, 0, 0), (205, "Nulls", "Eng", "Dev", 1000.0, None, None, None, None)])
    with Session(engine) as s:
        s.add(Employee(employee_code="102", name="Already Here", department="X", designation="Y", basic_salary_paise=1)); s.commit()
    rc, out = run_cmd(import_v1, ["--v1-db", str(path), "--commit"], settings)
    assert rc == 0 and "valid: 3" in out and "duplicates: 1" in out and "errors: 4" in out
    assert "emp_id 201: error" in out and "emp_id 203: error" in out and "emp_id 102: duplicate" in out
    codes = {c for c in Session(engine).scalars(select(Employee.employee_code))}
    assert codes == {"101", "102", "103", "205"}                                       # 102 kept as it was; NULLs treated as 0
    with Session(engine) as s:
        assert s.scalar(select(Employee.name).where(Employee.employee_code == "102")) == "Already Here"      # never overwritten


def test_strict_mode_imports_nothing_if_any_row_is_bad(settings, engine, v1):
    mods, path = v1
    _tamper(path, [(201, "Neg Pay", "Eng", "Dev", -5.0, 0, 0, 0, 0)])
    rc, out = run_cmd(import_v1, ["--v1-db", str(path), "--commit", "--strict"], settings)
    assert rc == 1 and "Nothing was imported" in out and count(engine, Employee) == 0


def test_the_v1_connection_cannot_write(v1):
    mods, path = v1
    conn = import_v1.open_readonly(path)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("INSERT INTO employees VALUES (999,'x','y','z',1,0,0,0,0)")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM employees")
    conn.close()


def test_refuses_bad_sources(settings, engine, tmp_path, v1):
    mods, path = v1
    assert run_cmd(import_v1, ["--v1-db", str(tmp_path / "missing.db")], settings)[0] == 2
    assert run_cmd(import_v1, ["--v1-db", str(settings.db_file)], settings)[0] == 2           # the V2 database itself
    junk = tmp_path / "junk.db"; junk.write_text("this is not sqlite")
    rc, out = run_cmd(import_v1, ["--v1-db", str(junk)], settings)
    assert rc == 2 and "not a usable V1 database" in out
    other = tmp_path / "other.db"; c = sqlite3.connect(other); c.execute("CREATE TABLE employees (emp_id INTEGER, name TEXT)"); c.commit(); c.close()
    rc, out = run_cmd(import_v1, ["--v1-db", str(other)], settings)
    assert rc == 2 and "missing column" in out
    empty = tmp_path / "empty.db"; sqlite3.connect(empty).close()
    assert run_cmd(import_v1, ["--v1-db", str(empty)], settings)[0] == 2
    assert count(engine, Employee) == 0
