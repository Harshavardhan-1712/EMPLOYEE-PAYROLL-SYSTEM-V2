from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from . import db as dbmod
from . import errors
from .config import Settings, get_settings
from .models import Base, Setting
from .middleware import BodyLimitMiddleware, SecurityHeadersMiddleware
from .routers import admin, analytics, auth, employees, health, payroll_runs, payslips, reports, users
from .security.deps import get_settings_dep
from .security.ratelimit import LoginLimiter
from .services.payroll_rules import to_paise
from .services.settings_store import DEFAULTS


# Every router mounted under /api. The permission-matrix test walks this list (and cross-checks it against OpenAPI).
ROUTERS = [health.router, auth.router, employees.router, payroll_runs.router, payslips.router, analytics.router, reports.router, users.router, admin.router]


def ensure_defaults(engine: Engine, settings: Settings) -> None:
    """Create tables (idempotent) and seed the default overtime rate (V1 default Rs 200/hr)."""
    Base.metadata.create_all(engine)
    # Minimal forward-compat step (no Alembic yet): add columns introduced after a database was first created.
    if "token_version" not in {c["name"] for c in inspect(engine).get_columns("users")}:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
    with Session(engine) as s:
        for key, default in DEFAULTS.items():
            if s.get(Setting, key) is None:
                value = str(to_paise(settings.default_overtime_rate)) if key == "overtime_rate_paise" else default
                s.add(Setting(key=key, value=value))
        s.commit()


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    engine = engine or dbmod.make_engine(settings)
    dbmod.init_engine(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        ensure_defaults(engine, settings)
        yield

    app = FastAPI(title="Employee Payroll Management System V2", version="2.0.0-dev", lifespan=lifespan,
                  docs_url=None if settings.env == "production" else "/api/docs",
                  openapi_url=None if settings.env == "production" else "/api/openapi.json", redoc_url=None)   # API docs are off in production
    app.state.settings = settings
    app.state.login_limiter = LoginLimiter(settings.login_max_failures, settings.login_window_seconds)
    app.dependency_overrides[get_settings_dep] = lambda: settings
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
    )
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.cookie_secure)
    errors.install(app)
    api = APIRouter(prefix="/api")
    for r in ROUTERS:
        api.include_router(r)
    app.include_router(api)
    return app


def create_default() -> FastAPI:
    """uvicorn entry point: uvicorn app.main:create_default --factory"""
    return create_app()
