import pytest
from app.config import V1_ROOT, ConfigError, Settings


def mk(**kw):
    kw.setdefault("jwt_secret", "x" * 40)
    return Settings(_env_file=None, **kw)


def test_refuses_v1_database_filename(tmp_path):
    with pytest.raises(ValueError, match="V1"):
        mk(database_path=str(tmp_path / "employee_data.db"))


def test_refuses_v1_directory():
    with pytest.raises(ValueError, match="V1"):
        mk(database_path=str(V1_ROOT / "anything.db"))


def test_default_path_is_inside_v2():
    s = mk()
    assert "v2" in s.db_file.parts and s.db_file.name == "payroll_v2.db"


def test_production_requires_real_secret_and_secure_cookie():
    with pytest.raises(ValueError):
        mk(env="production", jwt_secret="change-me-to-a-random-string-of-at-least-32-characters", cookie_secure=True)
    with pytest.raises(ValueError):
        mk(env="production", cookie_secure=False)
    assert mk(env="production", cookie_secure=True).env == "production"


def test_wildcard_cors_rejected():
    with pytest.raises(ConfigError):
        mk(cors_origins="*").cors_origin_list
