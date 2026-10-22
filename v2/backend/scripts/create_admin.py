"""Create (or reset) a V2 user. Password is read from a prompt or PV2_ADMIN_PASSWORD; never from argv.

    python -m scripts.create_admin --username alice --full-name "Alice Rao" [--role admin]
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import db as dbmod
from app.config import get_settings
from app.main import ensure_defaults
from app.models import User
from app.security.passwords import hash_password
from app.security.permissions import ROLES
from app.services import audit


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--username", required=True)
    p.add_argument("--full-name", required=True)
    p.add_argument("--role", default="admin", choices=ROLES)
    p.add_argument("--reset-password", action="store_true", help="update password if the user already exists")
    a = p.parse_args(argv)
    settings = get_settings()
    engine = dbmod.make_engine(settings)
    ensure_defaults(engine, settings)
    pw = os.environ.get("PV2_ADMIN_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    try:
        pw_hash = hash_password(pw)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    with Session(engine) as s:
        u = s.scalar(select(User).where(User.username == a.username))
        if u and not a.reset_password:
            print("error: user exists (use --reset-password)", file=sys.stderr)
            return 1
        if u:
            u.password_hash, u.role, u.full_name, u.is_active = pw_hash, a.role, a.full_name, True
            act = "user.password_reset"
        else:
            u = User(username=a.username, full_name=a.full_name, role=a.role, password_hash=pw_hash)
            s.add(u); s.flush(); act = "user.created"
        audit.record(s, act, entity_type="user", entity_id=u.id, detail={"username": u.username, "role": u.role, "via": "cli"})
        s.commit()
    print(f"ok: {a.username} ({a.role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
