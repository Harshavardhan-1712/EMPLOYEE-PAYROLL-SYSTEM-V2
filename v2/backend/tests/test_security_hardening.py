import re
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text

from app import db as dbmod
from app.config import Settings
from app.main import ROUTERS, create_app, ensure_defaults
from app.models import AuditEvent, PayrollRun, User
from app.security.deps import current_user
from app.security.passwords import hash_password
from app.security.permissions import ROLES, has_permission
from tests.conftest import PASSWORD
from tests.test_payroll_runs_api import emp, make_run


# ------------------------------------------------------------------------------ headers, docs, size
def test_security_headers_on_success_and_error_responses(client, login):
    for r in (client.get("/api/health"), client.get("/api/auth/me")):          # 200 and 401
        h = r.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "SAMEORIGIN" and h["referrer-policy"] == "no-referrer"
        assert h["content-security-policy"] == "frame-ancestors 'self'" and h["cache-control"] == "no-store"
        assert "camera=()" in h["permissions-policy"] and "strict-transport-security" not in h   # no HSTS over plain http dev
    c = login("hr", "hr_editor")
    assert c.get("/api/employees").headers["cache-control"] == "no-store"


def test_endpoint_specific_cache_header_is_not_overridden(login):
    hr = login("hr", "hr_editor")
    e = emp(hr, "E1"); rid = make_run(hr)["id"]
    ap = login("ap", "payroll_approver"); ap.post(f"/api/payroll-runs/{rid}/review"); ap.post(f"/api/payroll-runs/{rid}/finalize")
    r = ap.get(f"/api/payslips/{e['id']}/{rid}.pdf")
    assert r.headers["cache-control"] == "private, no-store" and r.headers["x-frame-options"] == "SAMEORIGIN"


def _prod(tmp_path, **kw):
    return Settings(env="production", database_path=str(tmp_path / "p.db"), jwt_secret="p" * 48, cookie_secure=True, _env_file=None, **kw)


def test_production_has_hsts_and_no_api_docs(tmp_path):
    s = _prod(tmp_path)
    eng = dbmod.make_engine(s); ensure_defaults(eng, s)
    with TestClient(create_app(s, eng)) as c:
        assert "max-age=31536000" in c.get("/api/health").headers["strict-transport-security"]
        assert c.get("/api/docs").status_code == 404 and c.get("/api/openapi.json").status_code == 404
    eng.dispose()


def test_docs_are_available_in_development(client):
    assert client.get("/api/docs").status_code == 200


def test_body_size_limit_by_content_length_and_by_stream(tmp_path):
    s = Settings(env="test", database_path=str(tmp_path / "t.db"), jwt_secret="x" * 40, max_body_bytes=2000, _env_file=None)
    eng = dbmod.make_engine(s); ensure_defaults(eng, s)
    with TestClient(create_app(s, eng)) as c:
        big = {"username": "u", "password": "p" * 5000}
        r = c.post("/api/auth/login", json=big)                                        # Content-Length path
        assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
        def chunks():                                                                   # chunked: no Content-Length, counted as it streams
            for _ in range(10):
                yield b"x" * 500
        r = c.post("/api/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
        assert r.status_code == 413 and r.json()["error"]["code"] == "payload_too_large"
        assert c.post("/api/auth/login", json={"username": "u", "password": "p"}).status_code == 401   # small bodies unaffected
    eng.dispose()


# ------------------------------------------------------------------------------ permission matrix
PUBLIC = {("/api/health", "GET"), ("/api/auth/login", "POST"), ("/api/auth/logout", "POST")}
AUTH_ONLY = {("/api/auth/me", "GET"), ("/api/auth/change-password", "POST")}


def _walk(dep, out):
    for d in dep.dependencies:
        if getattr(d.call, "__permission__", None):
            out.add(d.call.__permission__)
        if d.call is current_user:
            out.add("__auth__")
        _walk(d, out)


def _routes(app):
    """(path, method, permissions-found) for every route of every mounted router -- public attributes only."""
    for router in ROUTERS:
        for r in router.routes:
            if isinstance(r, APIRoute):
                for m in r.methods - {"HEAD", "OPTIONS"}:
                    found: set = set()
                    _walk(r.dependant, found)
                    yield "/api" + r.path, m, found


def test_router_list_matches_what_the_app_really_serves(app):
    """Guards the walker itself: a router mounted but missing from ROUTERS would escape the matrix test."""
    served = {(p, m.upper()) for p, ops in app.openapi()["paths"].items() if p.startswith("/api/") for m in ops}
    walked = {(p, m) for p, m, _ in _routes(app)}
    assert served == walked, f"drift between OpenAPI and ROUTERS: {served ^ walked}"


def test_every_api_route_is_protected_and_the_role_matrix_is_enforced(app, login):
    table = []
    for path, method, found in _routes(app):
        if (path, method) in PUBLIC:
            continue
        perms = {p for p in found if p != "__auth__"}
        if not perms:
            assert (path, method) in AUTH_ONLY and "__auth__" in found, f"UNPROTECTED ROUTE: {method} {path}"
            continue
        assert len(perms) == 1, f"{method} {path} declares several permissions: {perms}"
        table.append((path, method, perms.pop()))
    served = {(p, m.upper()) for p, ops in app.openapi()["paths"].items() if p.startswith("/api/") for m in ops}
    expected = len(served - PUBLIC - AUTH_ONLY)                              # independent count from the public OpenAPI schema
    assert len(table) == expected > 0, f"matrix covers {len(table)} routes but the app serves {expected} permissioned routes"

    def call(c, path, method):
        url = re.sub(r"\{[^}]+\}", "1", path)
        return c.request(method, url, json={} if method in ("POST", "PATCH", "PUT") else None)

    for role in ROLES:
        c = login(f"{role}_user", role)
        for path, method, perm in table:
            status = call(c, path, method).status_code
            if has_permission(role, perm):
                assert status not in (401, 403), f"{role} should be allowed {method} {path} ({perm}) but got {status}"
            else:
                assert status == 403, f"{role} must be denied {method} {path} ({perm}) but got {status}"
    anon = TestClient(app)
    for path, method, perm in table:
        assert call(anon, path, method).status_code == 401, f"anonymous reached {method} {path}"


def test_every_permission_in_the_matrix_is_used_by_some_route(app):
    used = {p for _, _, found in _routes(app) for p in found if p != "__auth__"}
    from app.security.permissions import ROLE_PERMISSIONS
    granted = set().union(*ROLE_PERMISSIONS.values())
    assert granted - used == set(), f"permissions granted but unused (dead grants): {granted - used}"
    assert used - granted == set(), f"routes require permissions no role has: {used - granted}"


# ------------------------------------------------------------------------------ denial auditing
def test_permission_denials_are_audited_without_query_strings(login, db):
    v = login("vic", "viewer")
    assert v.get("/api/audit-log?actor=secret-person").status_code == 403
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "access.denied"))
    assert ev.actor_username == "vic" and '"permission": "audit:read"' in ev.detail and '"path": "/api/audit-log"' in ev.detail
    assert "secret-person" not in ev.detail


# ------------------------------------------------------------------------------ separation of duties
def test_separate_finalizer_rule(login, db):
    hr = login("hr", "hr_editor"); emp(hr, "E1")
    ap1 = login("ap1", "payroll_approver")
    rid = make_run(ap1)["id"]                                               # ap1 creates the run
    ap1.post(f"/api/payroll-runs/{rid}/review")
    assert login("admin", "admin").patch("/api/settings", json={"require_separate_finalizer": True}).json()["require_separate_finalizer"] is True
    ap1 = login("ap1", "payroll_approver")
    r = ap1.post(f"/api/payroll-runs/{rid}/finalize")
    assert r.status_code == 403 and "Separation of duties" in r.json()["error"]["message"]
    assert ap1.get(f"/api/payroll-runs/{rid}").json()["status"] == "reviewed"
    assert login("admin", "admin").post(f"/api/payroll-runs/{rid}/finalize").status_code == 200   # a different person may finalize
    ev = [e for e in db.scalars(select(AuditEvent).where(AuditEvent.action == "access.denied"))]
    assert any('"rule": "separate_finalizer"' in e.detail for e in ev)


def test_rule_is_off_by_default_and_toggle_is_audited(login, db):
    ad = login("admin", "admin")
    assert ad.get("/api/settings").json()["require_separate_finalizer"] is False
    hr = login("ap", "payroll_approver"); emp(login("hr", "hr_editor"), "E1")
    rid = make_run(login("ap", "payroll_approver"))["id"]
    ap = login("ap", "payroll_approver")
    ap.post(f"/api/payroll-runs/{rid}/review")
    assert ap.post(f"/api/payroll-runs/{rid}/finalize").status_code == 200  # creator may finalize when the rule is off
    ad = login("admin", "admin")
    ad.patch("/api/settings", json={"require_separate_finalizer": True})
    ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "settings.changed")).all()
    assert '"require_separate_finalizer"' in ev[-1].detail and '"new": "true"' in ev[-1].detail


# ------------------------------------------------------------------------------ forward-compat column
def test_old_database_without_token_version_is_upgraded_in_place(tmp_path):
    s = Settings(env="test", database_path=str(tmp_path / "old.db"), jwt_secret="x" * 40, _env_file=None)
    eng = dbmod.make_engine(s); ensure_defaults(eng, s)
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO users (username, full_name, password_hash, role, is_active, is_sample, created_at) VALUES ('old','Old','x','viewer',1,0,'2026-01-01')"))
        conn.execute(text("ALTER TABLE users DROP COLUMN token_version"))
    ensure_defaults(eng, s)                                                  # simulates starting a newer app on an older file
    with eng.connect() as conn:
        assert conn.execute(text("SELECT token_version FROM users WHERE username='old'")).scalar() == 0
    eng.dispose()


# ------------------------------------------------------------------------------ concurrency
def _sessions(app, n, username, role, engine):
    from sqlalchemy.orm import Session
    with Session(engine) as s:
        if not s.scalar(select(User).where(User.username == username)):
            s.add(User(username=username, full_name=username, role=role, password_hash=hash_password(PASSWORD))); s.commit()
    out = []
    for _ in range(n):
        c = TestClient(app)
        assert c.post("/api/auth/login", json={"username": username, "password": PASSWORD}).status_code == 200
        c.headers["X-CSRF-Token"] = c.cookies.get("pv2_csrf"); out.append(c)
    return out


def test_two_simultaneous_creates_for_one_period_yield_exactly_one_run(app, engine, login, db):
    emp(login("hr", "hr_editor"), "E1")
    clients = _sessions(app, 4, "racer", "hr_editor", engine)
    gate = threading.Barrier(len(clients))
    def go(c):
        gate.wait()
        return c.post("/api/payroll-runs", json={"period": "2026-05"}).status_code
    with ThreadPoolExecutor(len(clients)) as ex:
        codes = sorted(ex.map(go, clients))
    assert codes == [201, 409, 409, 409], codes
    assert db.scalar(select(func.count()).select_from(PayrollRun).where(PayrollRun.period == "2026-05")) == 1


def test_simultaneous_finalize_requests_finalize_once_and_audit_once(app, engine, login, db):
    emp(login("hr", "hr_editor"), "E1")
    rid = make_run(login("hr", "hr_editor"))["id"]
    login("ap", "payroll_approver").post(f"/api/payroll-runs/{rid}/review")
    clients = _sessions(app, 4, "finalizer", "payroll_approver", engine)
    gate = threading.Barrier(len(clients))
    def go(c):
        gate.wait()
        r = c.post(f"/api/payroll-runs/{rid}/finalize")
        return r.status_code, r.json().get("status")
    with ThreadPoolExecutor(len(clients)) as ex:
        res = list(ex.map(go, clients))
    assert all(code in (200, 409) for code, _ in res), res                  # never a 500
    assert sum(code == 200 for code, _ in res) >= 1
    db.expire_all()
    assert db.get(PayrollRun, rid).status == "finalized"
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "payroll.run_finalized")) == 1
