"""Generate docs/api.md and docs/schema.md from the code itself (so they cannot drift).

    python -m scripts.gen_docs          # rewrite the two files
    python -m scripts.gen_docs --check  # exit 1 if they are out of date (also enforced by the test suite)
"""
from __future__ import annotations

import argparse
import inspect
import sys
import tempfile
from pathlib import Path

from fastapi.routing import APIRoute
from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from app.config import Settings
from app.main import ROUTERS, create_app
from app.models import Base
from app.models.tables import _TRIGGERS
from app.security.permissions import ROLE_PERMISSIONS, ROLES

DOCS = Path(__file__).resolve().parent.parent.parent / "docs"
PUBLIC = {("/api/health", "GET"): "public", ("/api/auth/login", "POST"): "public", ("/api/auth/logout", "POST"): "public",
          ("/api/auth/me", "GET"): "signed in", ("/api/auth/change-password", "POST"): "signed in"}
TAG_ORDER = ["health", "auth", "employees", "payroll", "payslips", "analytics", "reports", "users", "admin"]


def _perm(route: APIRoute) -> str | None:
    def walk(dep):
        for d in dep.dependencies:
            p = getattr(d.call, "__permission__", None)
            if p:
                return p
            r = walk(d)
            if r:
                return r
    return walk(route.dependant)


def _ref(schema: dict | None) -> str:
    if not schema:
        return ""
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    if schema.get("type") == "array":
        return f"list[{_ref(schema.get('items'))}]"
    return schema.get("type", "")


def build_api() -> str:
    with tempfile.TemporaryDirectory() as d:
        app = create_app(Settings(env="test", database_path=str(Path(d) / "docs.db"), jwt_secret="d" * 40, _env_file=None))
        spec = app.openapi()
    rows: dict[str, list[str]] = {}
    for router in ROUTERS:
        for r in router.routes:
            if not isinstance(r, APIRoute):
                continue
            path = "/api" + r.path
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                op = spec["paths"][path][m.lower()]
                perm = _perm(r) or PUBLIC.get((path, m), "?")
                params = ", ".join(f"`{p['name']}`{'*' if p.get('required') else ''}" for p in op.get("parameters", []) if p["in"] in ("query",))
                path_params = ", ".join(f"`{p['name']}`" for p in op.get("parameters", []) if p["in"] == "path")
                body = _ref(op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema"))
                if not body and "multipart/form-data" in op.get("requestBody", {}).get("content", {}):
                    body = "multipart file"
                ok = next((c for c in op["responses"] if c.startswith("2")), "")
                resp = _ref(op["responses"].get(ok, {}).get("content", {}).get("application/json", {}).get("schema")) or ("file download" if op["responses"].get(ok, {}).get("content") else "no body")
                doc = (inspect.getdoc(r.endpoint) or "").splitlines()
                note = doc[0] if doc else ""
                tag = (r.tags or ["other"])[0]
                rows.setdefault(tag, []).append(f"| `{m}` | `{path}` | `{perm}` | {path_params or '—'} | {params or '—'} | {body or '—'} | {ok} {resp} | {note} |")
    out = ["# API reference", "", "_Generated from the running code by `python -m scripts.gen_docs` -- do not edit by hand._", "",
           "Interactive docs (Swagger UI) are served at `/api/docs` outside production (disabled when `PV2_ENV=production`).", "",
           "## Conventions", "",
           "- **Auth:** `POST /api/auth/login` sets an httpOnly session cookie and a readable `pv2_csrf` cookie. Every `POST`/`PATCH`/`DELETE` must send that value in the `X-CSRF-Token` header. A missing or wrong token gives `403`.",
           "- **Errors:** every error is `{\"error\": {\"code\", \"message\", \"details\"?}}`; `details` is a list of `{field, message}` for `422`. No stack traces or paths are returned. Codes: 400, 401, 403, 404, 409 (conflict / wrong state), 413, 422, 429.",
           "- **Money** is a decimal string in rupees (e.g. `\"50000.00\"`) in requests and responses. Storage is integer paise. Overtime hours are decimal strings.",
           "- **Pagination:** list endpoints take `page` (from 1) and `page_size` (max 100, audit log 200) and return `{items, total, page, page_size}`.",
           "- **Idempotency:** `POST /api/payroll-runs` accepts an `Idempotency-Key` header (8-64 chars `[A-Za-z0-9_.-]`); replaying the same key returns the same run with `200`.",
           "- **Periods** are calendar months `YYYY-MM`. A permission shown as `signed in` needs only a valid session; `public` needs none.",
           "- Columns: `*` marks a required query parameter.", "", "## Roles and permissions", "",
           "| Permission | " + " | ".join(ROLES) + " |", "|---|" + "---|" * len(ROLES)]
    for perm in sorted(set().union(*ROLE_PERMISSIONS.values())):
        out.append(f"| `{perm}` | " + " | ".join("yes" if perm in ROLE_PERMISSIONS[r] else "—" for r in ROLES) + " |")
    out += ["", "Permissions are checked on the server for every request; the UI only hides what a role cannot use.", ""]
    for tag in TAG_ORDER + sorted(set(rows) - set(TAG_ORDER)):
        if tag not in rows:
            continue
        out += [f"## {tag.capitalize()}", "", "| Method | Path | Permission | Path params | Query | Body | Success | Notes |", "|---|---|---|---|---|---|---|---|", *rows[tag], ""]
    return "\n".join(out)


def _col_type(c) -> str:
    t = str(c.type)
    return t.replace("DATETIME", "DATETIME (UTC)")


def build_schema() -> str:
    out = ["# Database schema (V2)", "", "_Generated from the SQLAlchemy models by `python -m scripts.gen_docs` -- do not edit by hand._", "",
           "SQLite, stored at `PV2_DATABASE_PATH` (default `backend/data/payroll_v2.db`). **Separate from V1's `employee_data.db`**: V2 refuses to open that file or any file in V1's directory.",
           "All money columns are **integer paise** (1/100 rupee). Timestamps are UTC. Foreign keys are enforced (`PRAGMA foreign_keys=ON`).", "",
           "## Tables", ""]
    for t in Base.metadata.sorted_tables:
        out += [f"### `{t.name}`", "", "| Column | Type | Null | Default | Notes |", "|---|---|---|---|---|"]
        for c in t.columns:
            notes = []
            if c.primary_key:
                notes.append("primary key")
            for fk in c.foreign_keys:
                notes.append(f"→ `{fk.target_fullname}`" + (f" ({fk.ondelete})" if fk.ondelete else ""))
            if c.unique:
                notes.append("unique")
            d = ""
            if c.default is not None and getattr(c.default, "arg", None) is not None and not callable(c.default.arg):
                d = f"`{c.default.arg}`"
            elif c.server_default is not None:
                d = f"`{c.server_default.arg}`"
            out.append(f"| `{c.name}` | {_col_type(c)} | {'yes' if c.nullable else 'no'} | {d or '—'} | {'; '.join(notes) or '—'} |")
        extras = []
        for con in sorted(t.constraints, key=lambda x: str(x.name)):
            if isinstance(con, CheckConstraint):
                extras.append(f"- check `{con.name}`: `{str(con.sqltext)}`")
            elif isinstance(con, UniqueConstraint) and len(con.columns) > 1:
                extras.append(f"- unique `{con.name}`: ({', '.join(c.name for c in con.columns)})")
        for ix in sorted(t.indexes, key=lambda x: x.name):
            where = ix.dialect_options["sqlite"].get("where")
            extras.append(f"- {'unique ' if ix.unique else ''}index `{ix.name}` on ({', '.join(c.name for c in ix.columns)})" + (f" **where** `{where}`" if where is not None else ""))
        if extras:
            out += ["", *extras]
        out.append("")
    out += ["## Immutability triggers", "", "Finalized payroll cannot be changed even by raw SQL. These triggers are created with the tables:", ""]
    for sql in _TRIGGERS:
        name = sql.split("trg_", 1)[1].split()[0]
        msg = sql.split("RAISE(ABORT, '", 1)[1].split("'", 1)[0]
        out.append(f"- `trg_{name}` — aborts with: _{msg}_")
    out += ["", "## Correction policy for finalized payroll", "",
            "1. A finalized run and its items are never edited or deleted (enforced by the triggers above).",
            "2. A user with `payroll:reverse` reverses the run with a written reason (≥10 characters). The run becomes `reversed`, its figures stay on record, and its payslips stop being valid.",
            "3. The partial unique index `uq_run_period_live` then frees the period, and a corrected run can be created, reviewed and finalized.",
            "4. Reversal, the reason, and the actor are recorded in `audit_events`. Reports and analytics count only `finalized` runs.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    files = {DOCS / "api.md": build_api(), DOCS / "schema.md": build_schema()}
    stale = [p.name for p, text in files.items() if not p.exists() or p.read_text(encoding="utf-8") != text + "\n"]
    if a.check:
        if stale:
            print("out of date:", ", ".join(stale), "- run: python -m scripts.gen_docs"); return 1
        print("docs are up to date"); return 0
    for p, text in files.items():
        p.write_text(text + "\n", encoding="utf-8")
        print("wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
