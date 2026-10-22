from app.models import AuditEvent
from sqlalchemy import select
from tests.conftest import PASSWORD


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_me_requires_auth_with_structured_error(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthenticated"


def test_login_sets_httponly_session_and_readable_csrf(client, make_user):
    make_user("alice", "admin")
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 200 and r.json()["role"] == "admin"
    cookies = r.headers.get_list("set-cookie")
    sess = next(c for c in cookies if c.startswith("pv2_session"))
    csrf = next(c for c in cookies if c.startswith("pv2_csrf"))
    assert "HttpOnly" in sess and "samesite=lax" in sess.lower()
    assert "HttpOnly" not in csrf
    assert "password_hash" not in r.text


def test_wrong_password_and_unknown_user_look_identical(client, make_user):
    make_user("alice", "admin")
    a = client.post("/api/auth/login", json={"username": "alice", "password": "wrong-password-1"})
    b = client.post("/api/auth/login", json={"username": "nobody", "password": "wrong-password-1"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_login_rate_limit(client, make_user):
    make_user("alice", "admin")
    for _ in range(3):
        assert client.post("/api/auth/login", json={"username": "alice", "password": "bad-password-xx"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 429 and "retry-after" in r.headers


def test_login_events_are_audited_without_secrets(client, make_user, db):
    make_user("alice", "admin")
    client.post("/api/auth/login", json={"username": "alice", "password": "bad-password-xx"})
    client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    rows = db.scalars(select(AuditEvent)).all()
    assert [e.action for e in rows] == ["auth.login_failed", "auth.login"]
    assert all(PASSWORD not in e.detail and "bad-password" not in e.detail for e in rows)


def test_deactivated_user_session_stops_working(client, login, db):
    from app.models import User
    c = login("alice", "admin")
    assert c.get("/api/auth/me").status_code == 200
    u = db.scalar(select(User).where(User.username == "alice")); u.is_active = False; db.commit()
    assert c.get("/api/auth/me").status_code == 401


def test_tampered_token_rejected(client, login):
    c = login("alice", "admin")
    c.cookies.set("pv2_session", c.cookies.get("pv2_session")[:-3] + "abc")
    assert c.get("/api/auth/me").status_code == 401


def test_csrf_required_on_unsafe_methods(client, login):
    from app.security.deps import current_user  # noqa: F401
    c = login("alice", "admin")
    # use a throwaway unsafe route protected by current_user
    from fastapi import Depends
    @c.app.post("/api/_probe")
    def probe(u=Depends(current_user)):
        return {"ok": True}
    assert c.post("/api/_probe").status_code == 200              # header preset by fixture
    del c.headers["X-CSRF-Token"]
    r = c.post("/api/_probe")
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    c.headers["X-CSRF-Token"] = "wrong"
    assert c.post("/api/_probe").status_code == 403


def test_role_permissions_enforced(client, login):
    from fastapi import Depends
    from app.security.deps import require
    c = login("vic", "viewer")
    @c.app.get("/api/_final")
    def final(u=Depends(require("payroll:finalize"))):
        return {"ok": True}
    assert c.get("/api/_final").status_code == 403


def test_logout_clears_session(client, login):
    c = login("alice", "admin")
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_internal_errors_do_not_leak(app):
    from fastapi.testclient import TestClient
    @app.get("/api/_boom")
    def boom():
        raise RuntimeError("secret /home/claude/path")
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    assert r.status_code == 500 and "secret" not in r.text and "/home" not in r.text
