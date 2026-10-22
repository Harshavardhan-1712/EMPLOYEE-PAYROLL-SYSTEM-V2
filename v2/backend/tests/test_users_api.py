import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuditEvent, User
from app.services import users as svc
from tests.conftest import PASSWORD

NEW_PW = "a-brand-new-passphrase"


def mk(c, **kw):
    body = dict(username="newhr", full_name="New HR", role="hr_editor", password=NEW_PW)
    body.update(kw)
    return c.post("/api/users", json=body)


def fresh_session(app, username, password):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = c.cookies.get("pv2_csrf")
    return c


def test_list_never_exposes_password_hashes(login):
    ad = login("admin", "admin")
    r = ad.get("/api/users")
    assert r.status_code == 200 and r.json()[0]["username"] == "admin"
    assert "password" not in r.text.lower() and "argon2" not in r.text


@pytest.mark.parametrize("role", ["viewer", "hr_editor", "payroll_approver"])
def test_only_admins_manage_users(login, role):
    c = login("u", role)
    assert c.get("/api/users").status_code == 403
    assert mk(c).status_code == 403
    assert c.patch("/api/users/1", json={"role": "admin"}).status_code == 403
    assert c.post("/api/users/1/reset-password", json={"password": NEW_PW}).status_code == 403


def test_create_user_then_they_can_sign_in(login, app, db):
    ad = login("admin", "admin")
    r = mk(ad)
    assert r.status_code == 201 and r.json()["role"] == "hr_editor" and r.json()["is_active"] is True
    assert fresh_session(app, "newhr", NEW_PW).get("/api/auth/me").json()["role"] == "hr_editor"
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.created"))
    assert NEW_PW not in ev.detail and json.loads(ev.detail) == {"role": "hr_editor", "username": "newhr"}


@pytest.mark.parametrize("bad,code", [(dict(password="short"), 422), (dict(username="a b"), 422), (dict(username="ab"), 422),
                                      (dict(role="superuser"), 422), (dict(full_name=""), 422), (dict(username="NEWHR"), 409), (dict(username="newhr", password="short"), 422)])
def test_create_validation(login, bad, code):
    ad = login("admin", "admin")
    assert mk(ad).status_code == 201                                  # the existing user 'newhr'
    r = mk(ad, **{"username": "second", **bad})
    assert r.status_code == code, r.text


def test_deactivation_kills_the_session_and_blocks_login(login, app):
    ad = login("admin", "admin")
    uid = mk(ad).json()["id"]
    victim = fresh_session(app, "newhr", NEW_PW)
    assert victim.get("/api/auth/me").status_code == 200
    assert ad.patch(f"/api/users/{uid}", json={"is_active": False}).json()["is_active"] is False
    assert victim.get("/api/auth/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"username": "newhr", "password": NEW_PW}).status_code == 401
    assert ad.patch(f"/api/users/{uid}", json={"is_active": True}).status_code == 200
    assert fresh_session(app, "newhr", NEW_PW)


def test_role_change_applies_immediately_and_is_audited(login, app, db):
    ad = login("admin", "admin")
    uid = mk(ad, role="viewer").json()["id"]
    u = fresh_session(app, "newhr", NEW_PW)
    assert u.post("/api/employees", json={"employee_code": "X", "name": "n", "department": "d", "designation": "t", "basic_salary": "1"}).status_code == 403
    ad.patch(f"/api/users/{uid}", json={"role": "hr_editor"})
    assert u.post("/api/employees", json={"employee_code": "X", "name": "n", "department": "d", "designation": "t", "basic_salary": "1"}).status_code == 201
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.updated"))
    assert json.loads(ev.detail)["changes"] == {"role": {"old": "viewer", "new": "hr_editor"}}


def test_patch_rules(login):
    ad = login("admin", "admin")
    me = next(u for u in ad.get("/api/users").json() if u["username"] == "admin")["id"]
    assert ad.patch(f"/api/users/{me}", json={"role": "viewer"}).status_code == 409           # not your own role
    assert ad.patch(f"/api/users/{me}", json={"is_active": False}).status_code == 409         # not yourself
    assert ad.patch(f"/api/users/{me}", json={"full_name": "Admin Renamed"}).status_code == 200
    assert ad.patch(f"/api/users/{me}", json={}).status_code == 422
    assert ad.patch(f"/api/users/{me}", json={"role": None}).status_code == 422
    assert ad.patch(f"/api/users/{me}", json={"password_hash": "x"}).status_code == 422       # extra fields forbidden
    assert ad.patch("/api/users/9999", json={"role": "viewer"}).status_code == 404


def test_last_active_admin_is_protected_in_the_service_layer(db, make_user):
    """Defence in depth: the API actor is always another active admin, but the service must hold on its own."""
    sole = make_user("sole", "admin")
    outsider = make_user("outsider", "viewer")          # (could never reach this via the API; proves the guard itself)
    with pytest.raises(HTTPException) as e:
        svc.update(db, db.get(User, sole.id), svc.UserPatch(is_active=False), db.get(User, outsider.id))
    assert e.value.status_code == 409 and "last active administrator" in e.value.detail
    with pytest.raises(HTTPException):
        svc.update(db, db.get(User, sole.id), svc.UserPatch(role="viewer"), db.get(User, outsider.id))


def test_admin_reset_password_signs_the_user_out(login, app, db):
    ad = login("admin", "admin")
    uid = mk(ad).json()["id"]
    old = fresh_session(app, "newhr", NEW_PW)
    assert ad.post(f"/api/users/{uid}/reset-password", json={"password": "short"}).status_code == 422
    assert ad.post(f"/api/users/{uid}/reset-password", json={"password": "reset-by-admin-123"}).status_code == 204
    assert old.get("/api/auth/me").status_code == 401                       # old session is dead
    assert TestClient(app).post("/api/auth/login", json={"username": "newhr", "password": NEW_PW}).status_code == 401
    assert fresh_session(app, "newhr", "reset-by-admin-123")
    assert ad.post("/api/users/9999/reset-password", json={"password": "reset-by-admin-123"}).status_code == 404
    ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.password_reset"))
    assert "reset-by-admin" not in ev.detail


def test_change_own_password(login, app, db):
    c = login("hr", "hr_editor")
    other = fresh_session(app, "hr", PASSWORD)                              # a second device
    assert c.post("/api/auth/change-password", json={"current_password": "wrong-password-1", "new_password": NEW_PW}).status_code == 400
    assert c.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": PASSWORD}).status_code == 422
    assert c.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": "short"}).status_code == 422
    r = c.post("/api/auth/change-password", json={"current_password": PASSWORD, "new_password": NEW_PW})
    assert r.status_code == 204
    c.headers["X-CSRF-Token"] = c.cookies.get("pv2_csrf")                   # fresh token issued on change
    assert c.get("/api/auth/me").status_code == 200                         # this session continues
    assert other.get("/api/auth/me").status_code == 401                     # every other session is signed out
    assert TestClient(app).post("/api/auth/login", json={"username": "hr", "password": PASSWORD}).status_code == 401
    assert fresh_session(app, "hr", NEW_PW)
    acts = [e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.action.like("auth.password%")))]
    assert acts == ["auth.password_change_failed", "auth.password_changed"]
    assert all(NEW_PW not in e.detail and PASSWORD not in e.detail for e in db.scalars(select(AuditEvent)))


def test_change_password_requires_auth(client):
    assert client.post("/api/auth/change-password", json={"current_password": "x", "new_password": "y"}).status_code == 401
