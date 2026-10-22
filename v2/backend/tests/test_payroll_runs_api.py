import json
from datetime import date

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DatabaseError

from app.models import AuditEvent, PayrollRunItem
from app.services import audit as audit_mod

P1, P2 = "2026-08", "2026-09"


def emp(c, code, **kw):
    body = dict(employee_code=code, name=f"Emp {code}", department="Eng", designation="Dev", basic_salary="50000",
                bonus="5000", deductions="2000", overtime_hours="10", attendance_days=22, joining_date="2020-01-01")
    body.update(kw)
    r = c.post("/api/employees", json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def hr(login):
    return login("hr", "hr_editor")


def as_(login, name, role):
    return login(name, role)


def make_run(c, period=P1, **hdr):
    r = c.post("/api/payroll-runs", json={"period": period}, headers=hdr)
    assert r.status_code in (200, 201), r.text
    return r.json()


def finalize_flow(login, run_id):
    ap = as_(login, "ap", "payroll_approver")
    assert ap.post(f"/api/payroll-runs/{run_id}/review").status_code == 200
    return ap.post(f"/api/payroll-runs/{run_id}/finalize")


def test_create_run_uses_v1_formula_and_live_totals(hr):
    emp(hr, "E1")
    run = make_run(hr)
    it = run["items"][0]
    assert (it["overtime_pay"], it["gross_salary"], it["net_salary"]) == ("2000.00", "57000.00", "55000.00")
    assert run["status"] == "draft" and run["totals_source"] == "live" and run["total_net"] == "55000.00"
    assert run["overtime_rate"] == "200.00" and run["employee_count"] == 1


@pytest.mark.parametrize("period,code", [("2026-13", 422), ("26-08", 422), ("2999-01", 422), ("1999-12", 422)])
def test_period_validation(hr, period, code):
    emp(hr, "E1")
    assert hr.post("/api/payroll-runs", json={"period": period}).status_code == code


def test_current_month_allowed_future_month_rejected(hr):
    emp(hr, "E1")
    t = date.today()
    nxt = f"{t.year + (t.month == 12)}-{(t.month % 12) + 1:02d}"
    assert hr.post("/api/payroll-runs", json={"period": nxt}).status_code == 422
    assert hr.post("/api/payroll-runs", json={"period": f"{t.year}-{t.month:02d}"}).status_code == 201


def test_no_eligible_employees(hr):
    assert hr.post("/api/payroll-runs", json={"period": P1}).status_code == 422


def test_eligibility_excludes_inactive_and_not_yet_joined(hr):
    emp(hr, "A"); b = emp(hr, "B"); emp(hr, "C", joining_date="2026-09-01")
    hr.post(f"/api/employees/{b['id']}/deactivate")
    aug = make_run(hr, P1)
    assert [i["employee_code"] for i in aug["items"]] == ["A"]      # C joins after Aug, B inactive
    assert hr.delete(f"/api/payroll-runs/{aug['id']}").status_code == 204
    assert [i["employee_code"] for i in make_run(hr, P2)["items"]] == ["A", "C"]


def test_duplicate_period_blocked_and_idempotency(hr):
    emp(hr, "E1")
    a = hr.post("/api/payroll-runs", json={"period": P1}, headers={"Idempotency-Key": "key-12345"})
    assert a.status_code == 201
    again = hr.post("/api/payroll-runs", json={"period": P1}, headers={"Idempotency-Key": "key-12345"})
    assert again.status_code == 200 and again.json()["id"] == a.json()["id"]            # safe replay
    other = hr.post("/api/payroll-runs", json={"period": P2}, headers={"Idempotency-Key": "key-12345"})
    assert other.status_code == 409
    dup = hr.post("/api/payroll-runs", json={"period": P1})
    assert dup.status_code == 409 and "already exists" in dup.json()["error"]["message"]
    assert hr.get("/api/payroll-runs").json()["total"] == 1


def test_item_edit_recalculates_and_flags_negative_net(hr):
    emp(hr, "E1")
    run = make_run(hr)
    rid, iid = run["id"], run["items"][0]["id"]
    r = hr.patch(f"/api/payroll-runs/{rid}/items/{iid}", json={"deductions": "90000"})
    assert r.status_code == 200 and r.json()["net_salary"] == "-33000.00"
    assert [f["code"] for f in r.json()["flags"]] == ["negative_net"]
    r = hr.patch(f"/api/payroll-runs/{rid}/items/{iid}", json={"overtime_hours": "50", "deductions": "0", "attendance_days": 31})
    codes = {f["code"] for f in r.json()["flags"]}
    assert codes == {"high_overtime"} and r.json()["gross_salary"] == "65000.00"
    assert hr.patch(f"/api/payroll-runs/{rid}/items/{iid}", json={"attendance_days": 31}).json()["flags"]  # still high OT
    r = hr.patch(f"/api/payroll-runs/{rid}/items/{iid}", json={"basic_salary": "1"})
    assert r.status_code == 422                                                          # basic not editable here
    assert hr.patch(f"/api/payroll-runs/{rid}/items/{iid}", json={"bonus": "-1"}).status_code == 422
    assert hr.get(f"/api/payroll-runs/{rid}").json()["warning_flag_items"] == 1


def test_attendance_exceeding_days_in_month_is_error(hr):
    emp(hr, "E1")
    run = make_run(hr, "2026-02")                           # 28 days
    r = hr.patch(f"/api/payroll-runs/{run['id']}/items/{run['items'][0]['id']}", json={"attendance_days": 30})
    assert "attendance_exceeds_period" in [f["code"] for f in r.json()["flags"]]


def test_role_separation_for_review_and_finalize(hr, login):
    emp(hr, "E1")
    rid = make_run(hr)["id"]
    assert hr.post(f"/api/payroll-runs/{rid}/review").status_code == 403
    assert hr.post(f"/api/payroll-runs/{rid}/finalize").status_code == 403
    v = login("vic", "viewer")
    assert v.get(f"/api/payroll-runs/{rid}").status_code == 200
    assert v.post("/api/payroll-runs", json={"period": P2}).status_code == 403
    ap = login("ap", "payroll_approver")
    assert ap.post(f"/api/payroll-runs/{rid}/finalize").status_code == 409              # must be reviewed first
    assert ap.post(f"/api/payroll-runs/{rid}/review").json()["status"] == "reviewed"
    assert ap.patch(f"/api/payroll-runs/{rid}/items/1", json={"bonus": "1"}).status_code == 409  # reviewed = locked
    assert ap.post(f"/api/payroll-runs/{rid}/reopen").json()["status"] == "draft"


def test_finalize_snapshot_totals_and_idempotent(hr, login, db):
    emp(hr, "E1"); emp(hr, "E2", basic_salary="30000")
    rid = make_run(hr)["id"]
    r1 = finalize_flow(login, rid)
    assert r1.status_code == 200 and r1.json()["status"] == "finalized" and r1.json()["totals_source"] == "snapshot"
    assert r1.json()["total_net"] == "90000.00" and r1.json()["employee_count"] == 2
    ap = login("ap", "payroll_approver")
    r2 = ap.post(f"/api/payroll-runs/{rid}/finalize")
    assert r2.status_code == 200 and r2.json()["finalized_at"] == r1.json()["finalized_at"]
    n = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "payroll.run_finalized"))
    assert n == 1                                                                         # repeat request: no second event


def test_finalized_history_is_immutable_via_api_and_db(hr, login, db):
    e = emp(hr, "E1")
    run = make_run(hr)
    rid, iid = run["id"], run["items"][0]["id"]
    finalize_flow(login, rid)
    hr = login("hr", "hr_editor")
    hr.patch(f"/api/employees/{e['id']}", json={"basic_salary": "99999", "name": "Renamed"})   # employee changes later
    d = hr.get(f"/api/payroll-runs/{rid}").json()
    assert d["items"][0]["basic_salary"] == "50000.00" and d["items"][0]["employee_name"] == "Emp E1"
    assert hr.patch(f"/api/payroll-runs/{rid}/items/{iid}", json={"bonus": "1"}).status_code == 409
    assert hr.delete(f"/api/payroll-runs/{rid}").status_code == 409
    with pytest.raises(DatabaseError, match="immutable"):
        db.execute(text("UPDATE payroll_run_items SET net_paise = 1 WHERE run_id = :r"), {"r": rid})
    db.rollback()
    assert make_run_attempt(hr, P1).status_code == 409                                      # period still taken


def make_run_attempt(c, period):
    return c.post("/api/payroll-runs", json={"period": period})


def test_error_flags_block_finalize_unless_acknowledged_and_audited(hr, login, db):
    emp(hr, "E1")
    run = make_run(hr)
    hr.patch(f"/api/payroll-runs/{run['id']}/items/{run['items'][0]['id']}", json={"deductions": "90000"})
    ap = login("ap", "payroll_approver")
    ap.post(f"/api/payroll-runs/{run['id']}/review")
    blocked = ap.post(f"/api/payroll-runs/{run['id']}/finalize")
    assert blocked.status_code == 409 and "error-level" in blocked.json()["error"]["message"]
    ok = ap.post(f"/api/payroll-runs/{run['id']}/finalize", json={"acknowledge_errors": True, "note": "approved by CFO"})
    assert ok.status_code == 200 and ok.json()["total_net"] == "-33000.00"                  # stored as-is, never clamped
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "payroll.run_finalized"))
    assert json.loads(ev.detail)["acknowledged_error_items"] == 1


def test_finalize_is_atomic_when_a_step_fails(hr, login, db, monkeypatch):
    emp(hr, "E1")
    rid = make_run(hr)["id"]
    ap = login("ap", "payroll_approver")
    ap.post(f"/api/payroll-runs/{rid}/review")
    real = audit_mod.record

    def boom(db_, action, **kw):
        if action == "payroll.run_finalized":
            raise RuntimeError("simulated failure mid-transaction")
        return real(db_, action, **kw)
    monkeypatch.setattr(audit_mod, "record", boom)
    from fastapi.testclient import TestClient
    with TestClient(ap.app, raise_server_exceptions=False, cookies=ap.cookies) as c2:
        r = c2.post(f"/api/payroll-runs/{rid}/finalize", headers={"X-CSRF-Token": ap.headers["X-CSRF-Token"]})
    assert r.status_code == 500
    monkeypatch.undo()
    db.expire_all()
    d = ap.get(f"/api/payroll-runs/{rid}").json()
    assert d["status"] == "reviewed" and d["finalized_at"] is None and d["totals_source"] == "live"   # fully rolled back


def test_reverse_requires_reason_and_permission_then_allows_correction(hr, login, db):
    emp(hr, "E1")
    rid = make_run(hr)["id"]
    finalize_flow(login, rid)
    hr = login("hr", "hr_editor")          # same TestClient is shared; switch identity explicitly
    assert hr.post(f"/api/payroll-runs/{rid}/reverse", json={"reason": "wrong bonus entered"}).status_code == 403
    ap = login("ap", "payroll_approver")
    assert ap.post(f"/api/payroll-runs/{rid}/reverse", json={"reason": "short"}).status_code == 422
    r = ap.post(f"/api/payroll-runs/{rid}/reverse", json={"reason": "Bonus entered incorrectly"})
    assert r.status_code == 200 and r.json()["status"] == "reversed" and r.json()["totals_source"] == "snapshot"
    assert ap.get(f"/api/payroll-runs/{rid}").json()["items"]                           # history retained
    new = ap.post("/api/payroll-runs", json={"period": P1})
    assert new.status_code == 201 and new.json()["id"] != rid                            # correction run allowed
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "payroll.run_reversed"))
    assert "Bonus entered incorrectly" in ev.detail and ev.actor_username == "ap"
    assert ap.post(f"/api/payroll-runs/{rid}/reverse", json={"reason": "reverse again please"}).status_code == 409


def test_unusual_salary_change_flag_uses_finalized_history(hr, login):
    e = emp(hr, "E1")
    finalize_flow(login, make_run(hr, P1)["id"])
    hr = login("hr", "hr_editor")
    hr.patch(f"/api/employees/{e['id']}", json={"basic_salary": "80000"})                # +60%
    run2 = make_run(hr, P2)
    flags = run2["items"][0]["flags"]
    assert [f["code"] for f in flags] == ["unusual_salary_change"] and "+60.0%" in flags[0]["message"]


def test_rate_change_affects_only_new_runs(hr, login):
    emp(hr, "E1")
    r1 = make_run(hr, P1)
    ad = login("admin", "admin")
    assert ad.patch("/api/settings", json={"overtime_rate": "250"}).json()["overtime_rate"] == "250.00"
    hr = login("hr", "hr_editor")
    r2 = make_run(hr, P2)
    assert r2["items"][0]["overtime_pay"] == "2500.00" and r2["overtime_rate"] == "250.00"
    assert hr.get(f"/api/payroll-runs/{r1['id']}").json()["items"][0]["overtime_pay"] == "2000.00"


def test_settings_and_audit_log_are_admin_only(hr, login):
    assert hr.get("/api/settings").status_code == 403 and hr.get("/api/audit-log").status_code == 403
    ad = login("admin", "admin")
    assert ad.patch("/api/settings", json={"overtime_rate": "-1"}).status_code == 422
    assert ad.patch("/api/settings", json={"bogus": 1}).status_code == 422
    emp(ad, "E1")
    log = ad.get("/api/audit-log?action=employee.created").json()
    assert log["total"] == 1 and log["items"][0]["detail"]["employee_code"] == "E1"
    assert "password" not in json.dumps(ad.get("/api/audit-log").json()).lower()


def test_run_items_match_rules_engine_exactly(hr):
    from app.services.payroll_rules import compute_payroll, to_paise
    emp(hr, "E1", basic_salary="41234.57", bonus="333.33", deductions="1999.99", overtime_hours="7.5")
    it = make_run(hr)["items"][0]
    r = compute_payroll(basic_paise=to_paise("41234.57"), bonus_paise=to_paise("333.33"), overtime_hours="7.5",
                        deductions_paise=to_paise("1999.99"))
    assert it["net_salary"] == f"{r.net_paise / 100:.2f}" and it["overtime_pay"] == "1500.00"
