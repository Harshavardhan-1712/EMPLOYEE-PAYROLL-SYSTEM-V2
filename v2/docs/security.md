# Security notes

This describes what is implemented and tested. **It is not a claim of production-grade security**: there has been no penetration test, no dependency-vulnerability scan, and no review of a real deployment's TLS or network configuration.

## Implemented and tested

| Control | Detail |
|---|---|
| Authentication | Local accounts; argon2id hashes; minimum 12-character passwords; login for unknown and known users takes the same path and message |
| Sessions | JWT (HS256) in an **httpOnly, SameSite=Lax** cookie (`Secure` required in production); expiry configurable; the user is re-read from the database on every request, so deactivation and role changes apply immediately; password change/reset invalidates every older session |
| CSRF | Every POST/PATCH/DELETE must carry `X-CSRF-Token` matching the value inside the session |
| Authorization | Role → permission matrix; every API route declares a permission. A test walks all routes and checks each role's allow/deny exactly, and fails if a route is unprotected or the router list drifts from OpenAPI |
| Brute force | Per-IP+username failed-login limiter (429 + Retry-After), in-memory |
| Input handling | Pydantic validation with explicit limits; SQLAlchemy parameterized queries (LIKE wildcards escaped; sort columns whitelisted); control characters rejected in text fields |
| Request size | Bodies over `PV2_MAX_BODY_BYTES` (default 2 MiB) get 413, by Content-Length and while streaming; CSV import capped at 1 MB / 5,000 rows |
| Headers | nosniff, X-Frame-Options SAMEORIGIN, frame-ancestors 'self', no-referrer, no-store caching of API responses, HSTS when secure cookies are on |
| Errors | One envelope; no stack traces, paths or SQL in responses |
| Secrets | `.env` is git-ignored; `.env.example` has placeholders; production refuses a default/short JWT secret or non-secure cookies; the app refuses CORS `*` |
| Data separation | V2 refuses to open `employee_data.db` or any file in V1's directory; sample records are flagged and labelled; the seeder refuses a database holding real data |
| Auditing | Sign-ins and failures, employee/salary changes, imports, every payroll step, payslip views/downloads, exports, settings and user changes, and permission denials (path only, never query strings). No passwords or tokens are ever written |
| Export safety | Text beginning with `=`, `+`, `-`, `@`, tab or CR is prefixed with `'` in CSV and Excel; numbers are never altered; the workbook is verified to contain no formula cells |
| Payroll integrity | Finalized rows are immutable at the database level; finalization re-verifies every figure; payslips and exports read only the snapshot |
| API docs | Swagger UI is disabled when `PV2_ENV=production` |

## Known gaps

- Login limiter is per-process; run a single worker or add a shared store.
- No MFA, no email-based recovery, no account-lockout beyond the rate limit.
- No encryption of the SQLite file at rest; protect the file system and backups.
- Salary data appears in audit-log detail for salary changes (visible to administrators only).
- Any role with `payslips:read` (including viewers) can read all payslips; change the matrix in `security/permissions.py` if that is too broad.
- uvicorn's access log records URLs including query strings (which can contain search terms such as employee names). Run with `--no-access-log` or log to a restricted location.

## Deployment checklist

1. `PV2_ENV=production`, a random `PV2_JWT_SECRET` (32+ characters), `PV2_COOKIE_SECURE=true`, `PV2_CORS_ORIGINS` set to the real origin (or serve everything same-origin and leave it unused).
2. Serve over **HTTPS** behind a reverse proxy that serves `frontend/dist` and forwards `/api` to uvicorn on the same origin; enforce its own request-size limit.
3. Run uvicorn with `--no-access-log` and a single worker.
4. Create the first administrator with `python -m scripts.create_admin`; never run the seeder against a real database.
5. Back up `payroll_v2.db` (and its `-wal`/`-shm` files while running) regularly; restrict file permissions.
6. Review the permission matrix (`docs/api.md`) against your organization's duties; enable separation of duties in Settings if more than one approver exists.
