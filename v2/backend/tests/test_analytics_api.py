from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import update

from app.models import Employee
from app.services.analytics import distribution
from tests.test_payroll_runs_api import emp, make_run
from tests.world import build, finalize, money, tot


@pytest.fixture()
def world(login):
    ids, runs, exp = build(login)
    return ids, runs, exp, login("vic", "viewer")


def D(x):
    return Decimal(x)


# ------------------------------------------------------------------------------------ dashboard
def test_dashboard_without_history_is_an_honest_empty_state(login):
    hr = login("hr", "hr_editor"); emp(hr, "E1")
    d = hr.get("/api/dashboard/summary").json()
    assert d["has_history"] is False and d["selected_period"] is None and d["available_periods"] == []
    assert d["active_employees"] == 1 and d["comparison"] is None and d["trend"] == [] and d["average_net"] is None
    assert D(d["total_net"]) == 0 and d["departments"] == []


def test_dashboard_latest_period_matches_independent_arithmetic(world):
    ids, runs, exp, v = world
    d = v.get("/api/dashboard/summary").json()
    rows = exp["2026-08"]
    assert d["selected_period"] == "2026-08" and d["available_periods"] == ["2026-05", "2026-06", "2026-08"] and d["run_id"] == runs["2026-08"]
    assert d["employee_count"] == 2 and d["active_employees"] == 2 and d["inactive_employees"] == 1   # B1 deactivated
    assert d["total_gross"] == money(tot(rows, "gross")) and d["total_deductions"] == money(tot(rows, "ded")) and d["total_net"] == money(tot(rows, "net"))
    assert d["average_net"] == money(tot(rows, "net") / 2)
    assert d["total_bonus"] == money(tot(rows, "bonus")) and d["total_overtime_pay"] == money(tot(rows, "ot_pay"))
    by = {x["department"]: x for x in d["departments"]}
    assert list(by) == ["Eng"] and by["Eng"]["net"] == money(tot(rows, "net")) and by["Eng"]["employees"] == 2


def test_dashboard_selected_period_and_no_invented_comparison(world):
    ids, runs, exp, v = world
    first = v.get("/api/dashboard/summary?period=2026-05").json()
    assert first["comparison"] is None                                          # nothing earlier: no fabricated previous value
    assert first["employee_count"] == 3 and first["total_net"] == money(tot(exp["2026-05"], "net"))
    june = v.get("/api/dashboard/summary?period=2026-06").json()
    prev, cur = tot(exp["2026-05"], "net"), tot(exp["2026-06"], "net")
    c = june["comparison"]
    assert c["period"] == "2026-05" and c["adjacent_month"] is True and c["net_change"] == money(cur - prev)
    assert c["net_change_pct"] == f"{(cur - prev) * 100 / prev:.1f}"
    aug = v.get("/api/dashboard/summary?period=2026-08").json()["comparison"]
    assert aug["period"] == "2026-06" and aug["adjacent_month"] is False         # gap in history is disclosed, not hidden
    assert aug["employee_count"] == 3


def test_dashboard_trend_uses_all_finalized_periods(world):
    ids, runs, exp, v = world
    t = v.get("/api/dashboard/summary").json()["trend"]
    assert [p["period"] for p in t] == ["2026-05", "2026-06", "2026-08"]
    assert [p["net"] for p in t] == [money(tot(exp[p], "net")) for p in ("2026-05", "2026-06", "2026-08")]
    assert v.get("/api/dashboard/summary").json()["trend_min_periods"] == 3


def test_drafts_and_reversed_runs_never_count(world, login):
    ids, runs, exp, v = world
    hr = login("hr", "hr_editor")
    draft = make_run(hr, "2026-09")                                              # draft: must not appear in figures
    d = v.get("/api/dashboard/summary").json()
    assert "2026-09" not in d["available_periods"] and d["total_net"] == money(tot(exp["2026-08"], "net"))
    att = [a for a in d["attention"] if a["kind"] == "open_run"]
    assert att and att[0]["link"] == f"/payroll-runs/{draft['id']}" and "2026-09" in att[0]["message"]
    assert v.get("/api/dashboard/summary?period=2026-09").status_code == 404
    ap = login("ap", "payroll_approver")
    ap.post(f"/api/payroll-runs/{runs['2026-06']}/reverse", json={"reason": "Bonus entered incorrectly"})
    d2 = login("vic", "viewer").get("/api/dashboard/summary").json()
    assert d2["available_periods"] == ["2026-05", "2026-08"] and [p["period"] for p in d2["trend"]] == ["2026-05", "2026-08"]
    assert d2["comparison"]["period"] == "2026-05"


def test_dashboard_attention_flags_missing_joining_date_and_recent_runs(world, login):
    ids, runs, exp, v = world
    hr = login("hr", "hr_editor")
    hr.post("/api/employees", json=dict(employee_code="N1", name="No Date", department="Ops", designation="X", basic_salary="1"))
    d = login("vic", "viewer").get("/api/dashboard/summary").json()
    assert any(a["kind"] == "missing_joining_date" and a["message"].startswith("1 active") for a in d["attention"])
    assert [r["period"] for r in d["recent_runs"]] == ["2026-08", "2026-06", "2026-05"] and d["recent_runs"][0]["status"] == "finalized"


def test_dashboard_marks_sample_data(login, db):
    hr = login("hr", "hr_editor"); emp(hr, "S1")
    db.execute(update(Employee).values(is_sample=True)); db.commit()
    rid = make_run(hr, "2026-05")["id"]; finalize(login, rid)
    d = login("vic", "viewer").get("/api/dashboard/summary").json()
    assert d["includes_sample_data"] is True and d["sample_employees"] == 1


def test_average_is_rounded_half_up_not_bankers(login):
    hr = login("hr", "hr_editor")
    emp(hr, "R1", basic_salary="100.01", bonus="0", deductions="0", overtime_hours="0")
    emp(hr, "R2", basic_salary="100.00", bonus="0", deductions="0", overtime_hours="0")
    finalize(login, make_run(hr, "2026-05")["id"])
    assert login("vic", "viewer").get("/api/dashboard/summary").json()["average_net"] == "100.01"      # 100.005 -> 100.01


def test_dashboard_requires_auth_and_valid_period(world, client):
    ids, runs, exp, v = world
    assert v.get("/api/dashboard/summary?period=2026-13").status_code == 422
    client.post("/api/auth/logout")
    assert client.get("/api/dashboard/summary").status_code == 401


# ------------------------------------------------------------------------------------ analytics
def all_rows(exp):
    return [r for p in exp for r in exp[p]]


def test_analytics_totals_and_extremes(world):
    ids, runs, exp, v = world
    a = v.get("/api/analytics/summary").json()
    rows = all_rows(exp)
    assert a["record_count"] == len(rows) == 8 and a["periods_in_scope"] == 3
    for k, src in (("gross", "gross"), ("deductions", "ded"), ("net", "net"), ("bonus", "bonus"), ("overtime_pay", "ot_pay")):
        assert a["totals"][k] == money(tot(rows, src)), k
    assert D(a["totals"]["overtime_hours"]) == tot(rows, "ot_hours")
    assert a["average_net"] == money((tot(rows, "net") / len(rows)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    hi, lo = max(rows, key=lambda r: (r["net"], r["period"], r["code"])), min(rows, key=lambda r: (r["net"], r["period"], r["code"]))
    assert (a["highest_net"]["employee_code"], a["highest_net"]["period"], a["highest_net"]["net"]) == (hi["code"], hi["period"], money(hi["net"]))
    assert (a["lowest_net"]["employee_code"], a["lowest_net"]["net"]) == (lo["code"], money(lo["net"]))


def test_analytics_department_trend_and_changes(world):
    ids, runs, exp, v = world
    a = v.get("/api/analytics/summary").json()
    rows = all_rows(exp)
    by = {d["department"]: d for d in a["by_department"]}
    assert by["Eng"]["net"] == money(tot([r for r in rows if r["dept"] == "Eng"], "net")) and by["Ops"]["employees"] == 2     # B1 appears in May and June
    assert [t["period"] for t in a["trend"]] == ["2026-05", "2026-06", "2026-08"] and a["trend"][0]["employees"] == 3
    # only calendar-adjacent months are compared: 05->06 yes, 06->08 (a gap) no
    assert len(a["changes"]) == 1
    ch = a["changes"][0]
    assert (ch["period"], ch["prior_period"], ch["employee_count_change"]) == ("2026-06", "2026-05", 0)
    assert ch["net_change"] == money(tot(exp["2026-06"], "net") - tot(exp["2026-05"], "net"))


def test_analytics_attendance_overtime_and_flags(world):
    ids, runs, exp, v = world
    a = v.get("/api/analytics/summary").json()
    rows = all_rows(exp)
    atts = [r["att"] for r in rows]
    assert (a["attendance"]["min"], a["attendance"]["max"], a["attendance"]["records"]) == (min(atts), max(atts), len(atts))
    assert D(a["attendance"]["average"]) == (Decimal(sum(atts)) / len(atts)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    ot = [r for r in rows if r["ot_hours"] > 0]
    assert a["overtime_records"] == len(ot) == 6
    assert a["overtime_top"][0]["employee_code"] == "A2" and D(a["overtime_top"][0]["hours"]) == 45
    by = {d["department"]: d for d in a["overtime_by_department"]}
    assert list(by) == ["Eng"] and D(by["Eng"]["hours"]) == tot(ot, "ot_hours")
    assert a["flag_counts"] == {"high_overtime": 3}                                  # A2 each month: 45 h > 40 h threshold
    assert {f["employee_code"] for f in a["flagged_records"]} == {"A2"} and "exceeds the review threshold" in a["flagged_records"][0]["message"]
    assert a["thresholds"]["high_overtime_hours"] == "40"


def test_analytics_filters(world):
    ids, runs, exp, v = world
    eng = v.get("/api/analytics/summary?department=Eng").json()
    assert eng["record_count"] == 6 and eng["by_department"][0]["department"] == "Eng" and len(eng["by_department"]) == 1
    rng = v.get("/api/analytics/summary?from=2026-06&to=2026-08").json()
    assert rng["periods_in_scope"] == 2 and rng["record_count"] == 5
    assert rng["totals"]["net"] == money(tot(exp["2026-06"] + exp["2026-08"], "net"))
    assert rng["departments"] == ["Eng", "Ops"] and rng["available_periods"] == ["2026-05", "2026-06", "2026-08"]      # option lists are unfiltered
    assert v.get("/api/analytics/summary?from=2026-08&to=2026-05").status_code == 422
    empty = v.get("/api/analytics/summary?from=2027-01").json()
    assert empty["record_count"] == 0 and empty["average_net"] is None and empty["distribution"] == [] and empty["highest_net"] is None


def test_distribution_counts_every_record_once(world):
    ids, runs, exp, v = world
    a = v.get("/api/analytics/summary").json()
    assert sum(b["count"] for b in a["distribution"]) == a["record_count"]
    assert all(D(b["end"]) > D(b["start"]) for b in a["distribution"])
    nets = sorted(r["net"] for r in all_rows(exp))
    assert D(a["distribution"][0]["start"]) <= nets[0] and D(a["distribution"][-1]["end"]) > nets[-1]


@pytest.mark.parametrize("nets", [[], [5000], [5000, 5000, 5000], [-300000, 0, 250000, 999999], list(range(100, 100_000, 733)), [1, 2]])
def test_distribution_unit(nets):
    b = distribution(nets)
    assert sum(x.count for x in b) == len(nets)
    if nets:
        assert b[0].start <= Decimal(min(nets)) / 100 and b[-1].end >= Decimal(max(nets)) / 100
        assert all(b[i].end == b[i + 1].start for i in range(len(b) - 1))             # contiguous, non-overlapping


def test_analytics_data_quality_employee_checks(world, login):
    ids, runs, exp, v = world
    hr = login("hr", "hr_editor")
    hr.post("/api/employees", json=dict(employee_code="Z0", name="Zero Basic", department="Ops", designation="X", basic_salary="0"))
    a = login("vic", "viewer").get("/api/analytics/summary").json()
    codes = {c["code"]: c["count"] for c in a["employee_checks"]}
    assert codes == {"missing_joining_date": 1, "zero_basic_salary": 1}
