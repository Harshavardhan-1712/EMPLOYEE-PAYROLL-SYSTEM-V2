import io

import pytest
from sqlalchemy import select

from app.models import AuditEvent, SalaryHistory

EMP = dict(employee_code="E001", name="Priya Sharma", department="Engineering", designation="Developer",
           basic_salary="50000.00", bonus="5000", deductions="2500.50", overtime_hours="10", attendance_days=22)


def mk(c, **kw):
    r = c.post("/api/employees", json={**EMP, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_get(login):
    c = login("hr", "hr_editor")
    e = mk(c)
    assert e["basic_salary"] == "50000.00" and e["deductions"] == "2500.50" and e["status"] == "active"
    assert c.get(f"/api/employees/{e['id']}").json()["employee_code"] == "E001"
    assert c.get("/api/employees/999").status_code == 404


def test_duplicate_id_case_insensitive_409(login):
    c = login("hr", "hr_editor")
    mk(c)
    r = c.post("/api/employees", json={**EMP, "employee_code": "e001"})
    assert r.status_code == 409 and "already exists" in r.json()["error"]["message"]


@pytest.mark.parametrize("bad", [
    dict(basic_salary="-1"), dict(bonus="-5"), dict(deductions="abc"), dict(overtime_hours="-1"), dict(overtime_hours="800"),
    dict(attendance_days=32), dict(employee_code="bad id!"), dict(name="  "), dict(basic_salary="1.234"),
    dict(name="x\x00y"), dict(basic_salary="99999999"),
])
def test_validation_rejected_with_field_details(login, bad):
    c = login("hr", "hr_editor")
    r = c.post("/api/employees", json={**EMP, **bad})
    assert r.status_code == 422 and r.json()["error"]["details"]


def test_patch_audits_salary_change_and_history(login, db):
    c = login("hr", "hr_editor")
    e = mk(c)
    r = c.patch(f"/api/employees/{e['id']}", json={"basic_salary": "60000", "designation": "Senior Developer"})
    assert r.status_code == 200 and r.json()["basic_salary"] == "60000.00"
    acts = [a.action for a in db.scalars(select(AuditEvent))]
    assert "employee.salary_changed" in acts and "employee.updated" in acts
    hist = db.scalars(select(SalaryHistory).order_by(SalaryHistory.id)).all()
    assert [h.new_basic_paise for h in hist] == [5_000_000, 6_000_000] and hist[1].old_basic_paise == 5_000_000


def test_patch_rejects_code_change_empty_and_nulls(login):
    c = login("hr", "hr_editor")
    e = mk(c)
    assert c.patch(f"/api/employees/{e['id']}", json={"employee_code": "X"}).status_code == 422
    assert c.patch(f"/api/employees/{e['id']}", json={}).status_code == 422
    assert c.patch(f"/api/employees/{e['id']}", json={"name": None}).status_code == 422


def test_deactivate_keeps_record_and_filters(login):
    c = login("hr", "hr_editor")
    a, b = mk(c), mk(c, employee_code="E002", name="Arjun Mehta", department="Finance")
    assert c.post(f"/api/employees/{b['id']}/deactivate").json()["status"] == "inactive"
    assert c.get("/api/employees?status=active").json()["total"] == 1
    assert c.get("/api/employees?status=inactive").json()["items"][0]["employee_code"] == "E002"
    assert c.get(f"/api/employees/{b['id']}").status_code == 200       # still retrievable
    assert c.post(f"/api/employees/{b['id']}/reactivate").json()["status"] == "active"
    assert c.delete(f"/api/employees/{a['id']}").status_code == 405     # no hard delete endpoint


def test_search_sort_filter_paginate(login):
    c = login("hr", "hr_editor")
    for i, (n, d, s) in enumerate([("Zed", "Eng", "30000"), ("Amy", "Eng", "90000"), ("Bob", "Ops", "60000")]):
        mk(c, employee_code=f"C{i}", name=n, department=d, basic_salary=s)
    names = lambda r: [x["name"] for x in r.json()["items"]]  # noqa: E731
    assert names(c.get("/api/employees?sort=name")) == ["Amy", "Bob", "Zed"]
    assert names(c.get("/api/employees?sort=basic_salary&order=desc")) == ["Amy", "Bob", "Zed"]
    assert names(c.get("/api/employees?department=Ops")) == ["Bob"]
    assert names(c.get("/api/employees?q=am")) == ["Amy"]
    p = c.get("/api/employees?page=2&page_size=2&sort=name").json()
    assert p["total"] == 3 and [x["name"] for x in p["items"]] == ["Zed"]
    assert c.get("/api/employees?q=%25").json()["total"] == 0           # wildcard is escaped, not matched
    assert c.get("/api/employees?page_size=1000").status_code == 422
    assert c.get("/api/employees?sort=password_hash").status_code == 422  # sort is whitelisted
    assert c.get("/api/employees/departments").json() == ["Eng", "Ops"]


def test_viewer_can_read_not_write(login):
    c = login("v", "viewer")
    assert c.get("/api/employees").status_code == 200
    assert c.post("/api/employees", json=EMP).status_code == 403
    assert c.post("/api/employees/import", files={"file": ("a.csv", b"x")}).status_code == 403


def test_unauthenticated_blocked(client):
    assert client.get("/api/employees").status_code == 401


CSV = ("emp_id,name,department,designation,basic_salary,bonus,overtime,attendance\n"
       "A1,Meera Iyer,Finance,Analyst,45000,1000,5,20\n"
       "A2,Karan Joshi,Eng,Dev,-5,0,0,0\n"
       "A1,Dup Inside,Eng,Dev,1000,0,0,0\n"
       "A3,Divya Nair,Ops,Lead,52000,,,\n")


def _up(c, body: str, commit=False):
    return c.post(f"/api/employees/import?commit={'true' if commit else 'false'}",
                  files={"file": ("emps.csv", io.BytesIO(body.encode()), "text/csv")})


def test_import_preview_does_not_write_then_commit(login):
    c = login("hr", "hr_editor")
    mk(c, employee_code="A3")                                       # pre-existing -> duplicate
    r = _up(c, CSV).json()
    assert (r["valid"], r["duplicates"], r["errors"], r["imported"]) == (1, 2, 1, 0)
    by = {x["line"]: x for x in r["rows"]}
    assert by[2]["status"] == "valid" and by[3]["status"] == "error" and "basic_salary" in by[3]["errors"][0]
    assert "line 2" in by[4]["errors"][0] and by[5]["status"] == "duplicate"
    assert c.get("/api/employees").json()["total"] == 1             # preview wrote nothing
    r = _up(c, CSV, commit=True).json()
    assert r["imported"] == 1 and c.get("/api/employees").json()["total"] == 2
    assert c.get("/api/employees?q=Meera").json()["items"][0]["basic_salary"] == "45000.00"


def test_import_rejects_bad_files(login):
    c = login("hr", "hr_editor")
    assert _up(c, "name,department\nx,y\n").status_code == 422                    # missing columns
    assert c.post("/api/employees/import", files={"file": ("a.csv", b"\xff\xfe\x00bad")}).status_code == 422
    big = "employee_code,name,department,designation,basic_salary\n" + "A,b,c,d,1\n" * 200_000
    assert _up(c, big).status_code == 413
