from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import db as dbmod
from app.config import Settings
from app.main import create_app, ensure_defaults
from app.models import User
from app.security.passwords import hash_password

PASSWORD = "correct-horse-battery"


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(env="test", database_path=str(tmp_path / "test.db"), jwt_secret="x" * 40,
                    login_max_failures=3, _env_file=None)


@pytest.fixture()
def engine(settings):
    eng = dbmod.make_engine(settings)
    ensure_defaults(eng, settings)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def make_user(engine):
    def _mk(username: str, role: str) -> User:
        with Session(engine) as s:
            existing = s.scalar(select(User).where(User.username == username))
            if existing:
                return existing
            u = User(username=username, full_name=username.title(), role=role, password_hash=hash_password(PASSWORD))
            s.add(u); s.commit(); s.refresh(u)
            return u
    return _mk


@pytest.fixture()
def app(settings, engine):
    return create_app(settings, engine)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def login(client, make_user):
    """login('alice','admin') -> TestClient authenticated as that role, with CSRF header preset."""
    def _login(username: str, role: str) -> TestClient:
        make_user(username, role)
        r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
        client.headers["X-CSRF-Token"] = client.cookies.get("pv2_csrf")
        return client
    return _login
