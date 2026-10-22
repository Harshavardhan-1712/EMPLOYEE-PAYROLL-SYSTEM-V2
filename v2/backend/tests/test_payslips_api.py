import io
import re

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.models import AuditEvent
from app.services.payslips import fmt_inr, period_label
from tests.test_payroll_runs_api import emp, finalize_flow, make_run, P1


def pdf_text(resp) -> str:
    assert resp.headers["content-type"] == "application/pdf" and resp.content[:5] == b"%PDF-"
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(resp.content)).pages)


@pytest.fixture()
def finalized(login):
    hr = login("hr", "hr_editor")
    e = emp(hr, "E1", name="Priya Sharma", department="Engineering", basic_salary="1234567.50", bonus="5000.25", deductions="2500.50", overtime_hours="7.5")
    rid = make_run(hr)["id"]
    assert finalize_flow(login, rid).status_code == 200
    return login("hr", "hr_editor"), e, rid


@pytest.mark.parametrize("paise,out", [(0, "0.00"), (5, "0.05"), (99999, "999.99"), (100000, "1,000.00"), (12345678, "1,23,456.78"),
                                       (123456750, "12,34,567.50"), (1000000000, "1,00,00,000.00"), (-3300000, "-33,000.00"), (-5, "-0.05")])
def test_indian_grouping(paise, out):
    assert fmt_inr(paise) == out


def test_period_label():
    assert period_label("2026-09") == "September 2026" and period_label("2026-01") == "January 2026"


def test_pdf_contains_exactly_the_snapshot_figures(finalized):
    c, e, rid = finalized
    js = c.get(f"/api/payslips/{e['id']}/{rid}").json()
    t = pdf_text(c.get(f"/api/payslips/{e['id']}/{rid}.pdf"))
    # every figure on the PDF is the stored one (and the JSON says the same)
    assert js["gross_salary"] == "1241067.75"        # 1,234,567.50 + 5,000.25 + (7.5 h x 200 = 1,500.00)
    assert js["net_salary"] == "1238567.25"         # gross - 2,500.50
    for needle in ("12,34,567.50", "5,000.25", "1,500.00", "12,41,067.75", "2,500.50", "12,38,567.25",
                   "E1", "Priya Sharma", "Engineering", "August 2026", "Payroll run #"):
        assert needle in t, needle
    assert "7.50 h x INR 200.00" in t
    assert re.search(r"Generated \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC", t)
    assert "not calculated by this system" in t       # no statutory deductions claimed


def test_pdf_unchanged_by_later_employee_or_settings_edits(finalized, login):
    c, e, rid = finalized
    before = pdf_text(c.get(f"/api/payslips/{e['id']}/{rid}.pdf"))
    c.patch(f"/api/employees/{e['id']}", json={"basic_salary": "99999", "name": "Someone Else", "department": "Legal"})
    login("admin", "admin").patch("/api/settings", json={"overtime_rate": "999"})
    c = login("hr", "hr_editor")
    after = pdf_text(c.get(f"/api/payslips/{e['id']}/{rid}.pdf"))
    strip = lambda s: re.sub(r"Generated .*", "", s)  # noqa: E731  (timestamp is the only legitimate difference)
    assert strip(before) == strip(after)
    assert "Priya Sharma" in after and "Someone Else" not in after and "99,999" not in after


def test_negative_net_is_shown_as_stored(login):
    hr = login("hr", "hr_editor")
    emp(hr, "E1", basic_salary="1000", bonus="0", deductions="3000", overtime_hours="0")
    run = make_run(hr)
    ap = login("ap", "payroll_approver")
    ap.post(f"/api/payroll-runs/{run['id']}/review")
    assert ap.post(f"/api/payroll-runs/{run['id']}/finalize", json={"acknowledge_errors": True}).status_code == 200
    t = pdf_text(ap.get(f"/api/payslips/{run['items'][0]['employee_id']}/{run['id']}.pdf"))
    assert "-2,000.00" in t


def test_headers_filename_and_download_flag(finalized):
    c, e, rid = finalized
    r = c.get(f"/api/payslips/{e['id']}/{rid}.pdf")
    assert r.headers["content-disposition"] == 'inline; filename="payslip_E1_2026-08.pdf"'
    assert r.headers["cache-control"] == "private, no-store" and r.headers["x-content-type-options"] == "nosniff"
    d = c.get(f"/api/payslips/{e['id']}/{rid}.pdf?download=true")
    assert d.headers["content-disposition"] == 'attachment; filename="payslip_E1_2026-08.pdf"'


def test_unavailable_until_finalized_and_after_reversal(login):
    hr = login("hr", "hr_editor")
    e = emp(hr, "E1")
    rid = make_run(hr)["id"]
    r = hr.get(f"/api/payslips/{e['id']}/{rid}.pdf")
    assert r.status_code == 409 and "finalized" in r.json()["error"]["message"]
    finalize_flow(login, rid)
    ap = login("ap", "payroll_approver")
    assert ap.get(f"/api/payslips/{e['id']}/{rid}.pdf").status_code == 200
    assert ap.post(f"/api/payroll-runs/{rid}/reverse", json={"reason": "Bonus entered incorrectly"}).status_code == 200
    r = ap.get(f"/api/payslips/{e['id']}/{rid}.pdf")
    assert r.status_code == 409 and "reversed" in r.json()["error"]["message"]
    assert ap.get(f"/api/payslips/{e['id']}/{rid}").status_code == 409
    assert ap.get("/api/payslips").json()["total"] == 0                  # reversed runs drop out of the list


def test_not_found_and_auth(finalized, client):
    c, e, rid = finalized
    assert c.get(f"/api/payslips/{e['id']}/9999.pdf").status_code == 404
    assert c.get(f"/api/payslips/9999/{rid}").status_code == 404
    assert c.get(f"/api/payslips/abc/{rid}.pdf").status_code == 422
    c.post("/api/auth/logout")
    assert c.get(f"/api/payslips/{e['id']}/{rid}.pdf").status_code == 401
    assert c.get("/api/payslips").status_code == 401


def test_list_filters_search_pagination(login):
    hr = login("hr", "hr_editor")
    emp(hr, "A1", name="Amy Rao", department="Eng"); emp(hr, "B1", name="Bob Das", department="Ops"); emp(hr, "C1", name="Cy Jain", department="Eng")
    r1 = make_run(hr, "2026-08")["id"]; finalize_flow(login, r1)
    hr = login("hr", "hr_editor"); r2 = make_run(hr, "2026-09")["id"]; finalize_flow(login, r2)
    v = login("vic", "viewer")                                              # viewers may read payslips (documented policy)
    assert v.get("/api/payslips").json()["total"] == 6
    assert v.get(f"/api/payslips?run_id={r1}").json()["total"] == 3
    assert v.get("/api/payslips?period=2026-09&q=bob").json()["items"][0]["employee_code"] == "B1"
    assert v.get("/api/payslips?q=Eng").json()["total"] == 4
    assert v.get("/api/payslips?q=%25").json()["total"] == 0
    p = v.get("/api/payslips?page=2&page_size=4").json()
    assert p["total"] == 6 and len(p["items"]) == 2
    top = v.get("/api/payslips").json()["items"][0]
    assert top["period"] == "2026-09" and top["net_salary"] == "55000.00"


def test_views_and_downloads_are_audited_without_pay_data(finalized, db):
    c, e, rid = finalized
    c.get(f"/api/payslips/{e['id']}/{rid}.pdf"); c.get(f"/api/payslips/{e['id']}/{rid}.pdf?download=true")
    ev = db.scalars(select(AuditEvent).where(AuditEvent.action.like("payslip.%")).order_by(AuditEvent.id)).all()
    assert [x.action for x in ev] == ["payslip.viewed", "payslip.downloaded"]
    assert all("employee_code" in x.detail and "1234567" not in x.detail for x in ev)


def test_json_matches_run_snapshot(finalized):
    c, e, rid = finalized
    js = c.get(f"/api/payslips/{e['id']}/{rid}").json()
    item = next(i for i in c.get(f"/api/payroll-runs/{rid}").json()["items"] if i["employee_id"] == e["id"])
    for k in ("basic_salary", "bonus", "overtime_hours", "overtime_rate", "overtime_pay", "gross_salary", "deductions", "net_salary", "attendance_days"):
        assert js[k] == item[k], k
