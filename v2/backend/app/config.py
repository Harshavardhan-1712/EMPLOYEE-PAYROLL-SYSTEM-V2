"""Environment-driven configuration with guards that protect V1 data and production secrets."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
# <repo>/v2/backend -> <repo> is where V1's files and employee_data.db live.
V1_ROOT = BACKEND_DIR.parent.parent
V1_DB_NAME = "employee_data.db"
_PLACEHOLDER_SECRET = "change-me-to-a-random-string-of-at-least-32-characters"


class ConfigError(ValueError):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PV2_", env_file=".env", extra="ignore")

    env: str = "development"
    database_path: str = "data/payroll_v2.db"
    jwt_secret: str = _PLACEHOLDER_SECRET
    session_minutes: int = 480
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173"
    company_name: str = "HArsha's PVT LTD."
    company_address: str = ""
    default_overtime_rate: int = 200
    login_max_failures: int = 5
    login_window_seconds: int = 900
    max_body_bytes: int = 2_097_152   # hard cap on any request body (CSV import has its own 1 MB limit)

    @field_validator("env")
    @classmethod
    def _env(cls, v: str) -> str:
        if v not in {"development", "production", "test"}:
            raise ValueError("PV2_ENV must be development, production or test")
        return v

    @property
    def db_file(self) -> Path:
        p = Path(self.database_path)
        return (p if p.is_absolute() else BACKEND_DIR / p).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if "*" in origins:
            raise ConfigError("PV2_CORS_ORIGINS must list explicit origins, not '*'")
        return origins

    @model_validator(mode="after")
    def _guards(self) -> "Settings":
        db = self.db_file
        # Hard guard: V2 must never open V1's database.
        if db.name == V1_DB_NAME or db.parent == V1_ROOT:
            raise ConfigError(
                "PV2_DATABASE_PATH points at V1's location/database. V2 uses its own database."
            )
        if self.env == "production":
            if self.jwt_secret == _PLACEHOLDER_SECRET or len(self.jwt_secret) < 32:
                raise ConfigError("PV2_JWT_SECRET must be a unique random string (>=32 chars) in production")
            if not self.cookie_secure:
                raise ConfigError("PV2_COOKIE_SECURE must be true in production")
        elif len(self.jwt_secret) < 16:
            raise ConfigError("PV2_JWT_SECRET is too short")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
