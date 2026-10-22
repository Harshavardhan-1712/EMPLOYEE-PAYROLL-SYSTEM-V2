"""Shared dataset: three finalized months (05, 06, 08 -- note the gap), two departments.
Expected figures are computed here with plain Decimal arithmetic, independent of the app's payroll engine."""
from __future__ import annotations

from decimal import Decimal

from tests.test_payroll_runs_api import emp, make_run

RATE = Decimal(200)
EMPS = [  # code, name, dept, basic, bonus, deductions, overtime hours, attendance
    ("A1", "Amy Rao", "Eng", "50000", "5000", "2000", "10", 22),
    ("A2", "Arun Das", "Eng", "70000", "0", "5000", "45", 20),
    ("B1", "Bela Nair", "Ops", "30000", "1000", "1000", "0", 25),
]


def figures(code, name, dept, basic, bonus, ded, ot, att, period, bonus_override=None):
    b = Decimal(bonus_override if bonus_override is not None else bonus)
    ot_pay = Decimal(ot) * RATE
    gross = Decimal(basic) + b + ot_pay
    return dict(code=code, name=name, dept=dept, period=period, bonus=b, ot_hours=Decimal(ot), ot_pay=ot_pay, gross=gross, ded=Decimal(ded), net=gross - Decimal(ded), att=att)


def finalize(login, rid):
    ap = login("ap", "payroll_approver")
    assert ap.post(f"/api/payroll-runs/{rid}/review").status_code == 200
    r = ap.post(f"/api/payroll-runs/{rid}/finalize", json={"acknowledge_errors": True})
    assert r.status_code == 200, r.text
    return r.json()


def build(login):
    hr = login("hr", "hr_editor")
    ids = {}
    for code, name, dept, basic, bonus, ded, ot, att in EMPS:
        ids[code] = emp(hr, code, name=name, department=dept, basic_salary=basic, bonus=bonus, deductions=ded, overtime_hours=ot, attendance_days=att)["id"]
    exp: dict[str, list[dict]] = {}
    runs: dict[str, int] = {}

    r = make_run(hr, "2026-05"); runs["2026-05"] = r["id"]
    exp["2026-05"] = [figures(*e, "2026-05") for e in EMPS]
    finalize(login, r["id"])

    hr = login("hr", "hr_editor")
    r = make_run(hr, "2026-06"); runs["2026-06"] = r["id"]
    a1 = next(i for i in r["items"] if i["employee_code"] == "A1")
    assert hr.patch(f"/api/payroll-runs/{r['id']}/items/{a1['id']}", json={"bonus": "7000"}).status_code == 200
    exp["2026-06"] = [figures(*e, "2026-06", bonus_override="7000" if e[0] == "A1" else None) for e in EMPS]
    finalize(login, r["id"])

    hr = login("hr", "hr_editor")
    assert hr.post(f"/api/employees/{ids['B1']}/deactivate").status_code == 200
    r = make_run(hr, "2026-08"); runs["2026-08"] = r["id"]
    exp["2026-08"] = [figures(*e, "2026-08") for e in EMPS if e[0] != "B1"]
    finalize(login, r["id"])
    return ids, runs, exp


def tot(rows, key):
    return sum((r[key] for r in rows), Decimal(0))


def money(d: Decimal) -> str:
    return f"{d:.2f}"
