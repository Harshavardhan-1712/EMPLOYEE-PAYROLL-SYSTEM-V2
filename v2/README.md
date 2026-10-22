# Employee Payroll Management System — V2

A web-based payroll and analytics application built **alongside** the original V1 console app. V1 is untouched and still runs exactly as before; V2 lives entirely in this `v2/` folder with its own dependencies, configuration and database.

- **Backend:** Python, FastAPI, Pydantic, SQLAlchemy, SQLite
- **Frontend:** React, TypeScript, Vite, Radix UI primitives, Recharts, lucide icons
- **Docs:** [architecture](docs/architecture.md) · [features: done vs deferred](docs/features.md) · [security](docs/security.md) · [API reference](docs/api.md) · [database schema](docs/schema.md) · [design system](docs/design-system.md) · [V1 preservation record](docs/v1-preservation.md)

## What it does

Employees (CRUD, deactivation, CSV import) · payroll runs with review, finalization, reversal and immutable history · itemized payslip PDFs · dashboard and analytics from finalized data · CSV/Excel exports · audit log, users and settings · role-based access. Payroll uses the V1 formulas unchanged:

```
overtime pay = overtime hours × rate (default ₹200/hour, configurable)
gross        = basic + bonus + overtime pay
net          = gross − deductions
```

**Statutory deductions (PF, ESI, TDS, tax) are intentionally not calculated** — no rules were provided. Deductions are an amount entered by HR.

## Repository layout

```
<repo root>/        V1 (main.py, database.py, payroll.py, analytics.py, export.py, index.html, …) — unchanged
└── v2/
    ├── backend/    API, services, scripts, tests        (own requirements.txt, .env.example)
    ├── frontend/   web app                              (own package.json, .env.example)
    └── docs/
```

## Requirements

Python 3.12+ and Node.js 20+ (built and tested with Python 3.12 and Node 22, npm 10). Nothing else.

## Run V1 (unchanged)

From the repository root, exactly as V1 always worked:

```bash
pip install pandas tabulate matplotlib openpyxl      # V1's original instruction (the code itself does not import pandas)
python main.py
```
V1 creates `employee_data.db`, `exports/` and `reports/` next to itself. **V2 never reads or writes them** (except the explicit, read-only import described below).

## Run V2

### 1. Backend

```bash
cd v2/backend
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env   — then edit PV2_JWT_SECRET
python -m scripts.create_admin --username admin --full-name "Your Name"      # prompts for a password (min 12 chars)
uvicorn app.main:create_default --factory --port 8000 --no-access-log
```
Run these from `v2/backend` (the `.env` file is read from the current directory). The database is created at `v2/backend/data/payroll_v2.db`. Interactive API docs: <http://127.0.0.1:8000/api/docs> (development only).

### 2. Frontend

```bash
cd v2/frontend
npm install                          # the bundled .npmrc is needed; see Troubleshooting
npm run dev                          # http://localhost:5173  (proxies /api to the backend on :8000)
```
Open <http://localhost:5173> and sign in with the account you created.

### 3. Try it with sample data (optional)

```bash
cd v2/backend
python -m scripts.seed_demo          # 12 fictional employees, 5 finalized months, 1 draft run, 4 sample users
```
The command prints a generated password for each sample user **once** (`demo_admin`, `demo_hr`, `demo_approver`, `demo_viewer`) — there are no default credentials. Everything it creates is flagged and labelled **sample** in the UI. It writes only to the V2 database and refuses to run if the database holds real data. `--reset --yes` wipes a sample-only V2 database and reseeds.

### 4. Bring over V1 employees (optional)

```bash
cd v2/backend
python -m scripts.import_v1 --v1-db ../../employee_data.db              # dry run: validate and report only
python -m scripts.import_v1 --v1-db ../../employee_data.db --commit     # import the valid rows
```
V1's file is opened **read-only**, hashed before and after, and the command fails loudly if it changed. V1 `emp_id` becomes the V2 employee ID; V1 has no joining date, so it is left empty (the review flags mention it). IDs that already exist in V2 are skipped, never overwritten. `--strict` imports nothing if any row is invalid.

### Check that V1 is still intact (any time)

```bash
cd v2/backend && python -m scripts.verify_v1
```
Compares every V1 file with the SHA-256 baseline recorded before V2 was built (`docs/v1-baseline.sha256`).

## Roles

| Role | Can |
|---|---|
| Viewer | Read employees, payroll, payslips, dashboard, analytics |
| HR editor | + manage employees, import, create/adjust payroll runs, export |
| Payroll approver | Read, create/adjust, **review, finalize, reverse** payroll runs, export |
| Administrator | Everything, plus settings, users and the audit log |

The full permission matrix is in [docs/api.md](docs/api.md). The server enforces it on every request.

## Configuration (`backend/.env`, all `PV2_*`)

| Variable | Default | Meaning |
|---|---|---|
| `PV2_ENV` | `development` | `development`, `test` or `production` (production enforces secrets and secure cookies, disables API docs) |
| `PV2_DATABASE_PATH` | `data/payroll_v2.db` | V2 database. **Refuses** `employee_data.db` or anything in V1's folder |
| `PV2_JWT_SECRET` | placeholder | Signing key. Set a unique random 32+ character value |
| `PV2_SESSION_MINUTES` | `480` | Session lifetime |
| `PV2_COOKIE_SECURE` | `false` | Must be `true` over HTTPS / in production |
| `PV2_CORS_ORIGINS` | `http://localhost:5173` | Only needed if the frontend is on a different origin |
| `PV2_COMPANY_NAME`, `PV2_COMPANY_ADDRESS` | placeholder | Printed on payslips and Excel reports |
| `PV2_DEFAULT_OVERTIME_RATE` | `200` | Initial rate; afterwards edit it in Settings |
| `PV2_LOGIN_MAX_FAILURES`, `PV2_LOGIN_WINDOW_SECONDS` | `5`, `900` | Login rate limit |
| `PV2_MAX_BODY_BYTES` | `2097152` | Request-size cap (413 above it) |

Frontend (`frontend/.env`): `VITE_API_PROXY_TARGET` (dev proxy target) and optionally `VITE_API_BASE`.

## Tests

```bash
cd v2/backend  && pytest                       # 207 tests; ≈3 minutes on a single core
cd v2/frontend && npm test                     # 124 tests in 13 files
cd v2/frontend && npm run build                # type-checks, then builds
cd v2/backend  && python -m scripts.gen_docs   # regenerates docs/api.md and docs/schema.md (a test fails if they are stale)
```
Backend tests use isolated temporary databases and never touch V1's. Coverage includes: payroll formulas and V1 parity, zero/negative/invalid inputs, negative net pay, duplicate IDs, employee CRUD, period validation, duplicate-run prevention, immutability (API and raw SQL), transactional finalization, concurrency races, dashboard and filtered analytics, CSV/Excel exports and injection safety, PDF-versus-snapshot consistency, API validation, the full role/permission matrix, the seed and import commands, and V1 file integrity. Frontend tests cover loading, error, empty and success states, validation, confirmations and role-based UI against a mocked API.

**Could not be run in the build environment:** browser-level end-to-end tests and visual checks (no browser was available), an automated accessibility audit, and a deployment on HTTPS. See [docs/features.md](docs/features.md).

## Production notes (summary — full checklist in [docs/security.md](docs/security.md))

Build the frontend (`npm run build`), serve `frontend/dist` and forward `/api` to uvicorn **from the same origin** over HTTPS; set `PV2_ENV=production`, a random secret and `PV2_COOKIE_SECURE=true`; run a single uvicorn worker with `--no-access-log`; back up the SQLite file. Example nginx layout (illustrative, not tested here):

```nginx
location /api/ { proxy_pass http://127.0.0.1:8000; client_max_body_size 2m; }
location /     { root /srv/payroll/frontend/dist; try_files $uri /index.html; }
```

## Known limitations

SQLite and no migration tool yet (schema changes need Alembic); one in-process login limiter; no MFA/SSO/email; no statutory deductions; INR and calendar-month periods only; no salary-history screen; no bulk payslip ZIP; single company. UI not visually reviewed in a real browser or audited for accessibility by me. Full list in [docs/features.md](docs/features.md).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `npm install` fails with `Cannot read properties of null (reading 'edgesOut')` | npm 10.9 bug with vitest's optional peers. The bundled `frontend/.npmrc` (`legacy-peer-deps=true`) avoids it — run `npm install` inside `v2/frontend`. Required peers were verified manually |
| Backend exits: *"PV2_DATABASE_PATH points at V1's location/database"* | The guard working: choose a path outside V1's folder and not named `employee_data.db` |
| Backend exits: *"PV2_JWT_SECRET must be a unique random string"* | `PV2_ENV=production` needs a real secret (≥32 chars) and `PV2_COOKIE_SECURE=true` |
| Signed out after restarting with a different `PV2_JWT_SECRET` | Expected: sessions are signed with that secret |
| Sign-in works but every action returns 403 "CSRF" | The frontend must be served from the origin the cookies belong to (use the dev proxy or a same-origin reverse proxy); a cross-origin setup needs `PV2_CORS_ORIGINS` and cookie review |
| 429 on sign-in | Too many failed attempts for that user/IP; wait for `Retry-After` |
| Payslip preview blank | Open the PDF with the download button; the preview needs the same-origin `/api` path and a browser PDF viewer |
| Uploading a very large file through the Vite dev proxy gives 502 | Dev-proxy artifact when the backend rejects early with 413; the backend itself returns 413 correctly |
| "database is locked" | SQLite allows one writer; avoid multiple uvicorn workers and long-running external writers |
| An older V2 database after upgrading | A missing `users.token_version` column is added automatically; for other schema changes recreate the dev database (there is no migration tool yet) |
| Tests collide with a running server | Tests use temporary databases; stop other uvicorn instances only if port 8000 is needed |
| Windows: `Activate.ps1` blocked | `Set-ExecutionPolicy -Scope Process RemoteSigned`, then activate again |
