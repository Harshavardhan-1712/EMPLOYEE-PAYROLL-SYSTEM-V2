"""DB-level guarantees: duplicate live runs blocked, finalized snapshots immutable, FK/CHECK enforced."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DatabaseError

from app.models import Employee, PayrollRun, PayrollRunItem


def _emp(db, code="E1"):
    e = Employee(employee_code=code, name="A", department="Eng", designation="Dev", basic_salary_paise=100)
    db.add(e); db.commit(); return e


def _run(db, period="2026-04", status="draft"):
    r = PayrollRun(period=period, status=status, overtime_rate_paise=20000)
    db.add(r); db.commit(); return r


def _item(db, run, emp):
    i = PayrollRunItem(run_id=run.id, employee_id=emp.id, employee_code="E1", employee_name="A", department="Eng",
                       designation="Dev", basic_paise=100, bonus_paise=0, overtime_hours=0, overtime_rate_paise=20000,
                       overtime_pay_paise=0, gross_paise=100, deductions_paise=0, net_paise=100)
    db.add(i); db.commit(); return i


def test_duplicate_employee_code_rejected(db):
    _emp(db)
    with pytest.raises(IntegrityError):
        _emp(db)
    db.rollback()


def test_negative_salary_rejected_by_check(db):
    db.add(Employee(employee_code="N", name="n", department="d", designation="x", basic_salary_paise=-1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_one_live_run_per_period_but_reversed_frees_it(db):
    r1 = _run(db)
    with pytest.raises(IntegrityError):
        _run(db)
    db.rollback()
    db.execute(text("UPDATE payroll_runs SET status='reversed' WHERE id=:i"), {"i": r1.id}); db.commit()
    assert _run(db).id != r1.id


def test_bad_period_format_rejected(db):
    with pytest.raises(IntegrityError):
        _run(db, period="April-26")
    db.rollback()


def test_finalized_items_cannot_change(db):
    e = _emp(db); r = _run(db); i = _item(db, r, e)
    db.execute(text("UPDATE payroll_runs SET status='finalized' WHERE id=:i"), {"i": r.id}); db.commit()
    for sql in ("UPDATE payroll_run_items SET net_paise=1 WHERE id=:i", "DELETE FROM payroll_run_items WHERE id=:i"):
        with pytest.raises(DatabaseError, match="immutable"):
            db.execute(text(sql), {"i": i.id})
        db.rollback()
    with pytest.raises(DatabaseError, match="finalized"):
        db.execute(text("INSERT INTO payroll_run_items (run_id, employee_id, employee_code, employee_name, department, designation, basic_paise, bonus_paise, overtime_hours, overtime_rate_paise, overtime_pay_paise, gross_paise, deductions_paise, net_paise, attendance_days, flags) VALUES (:r, :e, 'x','x','x','x',1,0,0,0,0,1,0,1,0,'[]')"), {"r": r.id, "e": e.id})
    db.rollback()


def test_finalized_run_totals_period_and_delete_blocked_but_reversal_allowed(db):
    r = _run(db)
    db.execute(text("UPDATE payroll_runs SET status='finalized', total_net_paise=100, employee_count=1, total_gross_paise=100, total_deductions_paise=0 WHERE id=:i"), {"i": r.id}); db.commit()
    for sql in ("UPDATE payroll_runs SET total_net_paise=999 WHERE id=:i", "UPDATE payroll_runs SET period='2026-05' WHERE id=:i",
                "UPDATE payroll_runs SET status='draft' WHERE id=:i", "DELETE FROM payroll_runs WHERE id=:i"):
        with pytest.raises(DatabaseError):
            db.execute(text(sql), {"i": r.id})
        db.rollback()
    db.execute(text("UPDATE payroll_runs SET status='reversed', reversal_reason='x' WHERE id=:i"), {"i": r.id}); db.commit()
    with pytest.raises(DatabaseError):                 # a reversed run is frozen too
        db.execute(text("UPDATE payroll_runs SET reversal_reason='tamper' WHERE id=:i"), {"i": r.id})
    db.rollback()


def test_cannot_hard_delete_employee_with_payroll_history(db):
    e = _emp(db); r = _run(db); _item(db, r, e)
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM employees WHERE id=:i"), {"i": e.id}); db.commit()
    db.rollback()
