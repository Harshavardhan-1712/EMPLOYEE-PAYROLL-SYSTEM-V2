# Architecture

## 1. What V1 is (inspected before any V2 work)

V1 is a flat, menu-driven **console application** (Python + SQLite). Nothing in it was modified.

| File | Role |
|---|---|
| `main.py` | Console menu (9 options). Creates the table and seeds 10 demo employees on first run. |
| `database.py` | SQLite access. DB path is fixed next to the file (`employee_data.db`). CRUD functions that `print()` as they run. |
| `payroll.py` | Payroll formulas, payslip printing, department report. Imports `database` and `tabulate`. |
| `analytics.py` | Four matplotlib charts and a text KPI summary. Calls `plt.show()`; creates `reports/` on import. |
| `export.py` | CSV and Excel export (openpyxl). Creates `exports/` on import. |
| `index.html` | A static showcase page (mostly base64 chart images). No application logic; its counters are hard-coded text. |
| `Employee pay roll system -internship.zip` | Nested archive holding the same five `.py` files (byte-identical) plus a README and chart images. |

**Schema** (one table): `employees(emp_id INTEGER PK, name, department, designation, basic_salary REAL, bonus REAL=0, deductions REAL=0, attendance INTEGER=0, overtime INTEGER=0)`.

**Payroll rules** (the single source of truth, preserved unchanged in V2):

```
overtime_pay = overtime_hours x 200          (V1 constant OVERTIME_RATE; configurable in V2)
gross        = basic + bonus + overtime_pay
net          = gross - deductions
```

**Why V2 does not import V1's modules directly:** importing `payroll` pulls in `database`, whose path is fixed to V1's own file; `analytics` and `export` create directories on import and change global matplotlib state; and the functions mix printing with logic. Only the formulas are pure. So V2 re-implements the three rules once, in `backend/app/services/payroll_rules.py`, and a **parity test** (`tests/test_v1_parity.py`) loads V1's real `payroll.py` from a temp *copy* and checks 500 random employees give identical results. There is one rule set, verified against V1, not two competing ones.

**V1 limitations V2 addresses (and V1 keeps):** floating-point money; no validation of negative values or negative net pay; hard delete of employees; no per-month history (current values only); no users, roles or audit trail; no joining date or status; no duplicate-run protection.

## 2. V2 layout

```
repository root/           V1 files, untouched
└── v2/
    ├── backend/           FastAPI + SQLAlchemy + SQLite
    │   ├── app/
    │   │   ├── main.py            app factory, middleware, router list
    │   │   ├── config.py          PV2_* settings + guards (never V1's DB; production secrets)
    │   │   ├── models/tables.py   schema + immutability triggers
    │   │   ├── schemas/           Pydantic request/response models
    │   │   ├── services/          business logic (payroll_rules, payroll_runs, flags, analytics, exports, payslips, users, audit)
    │   │   ├── routers/           thin HTTP layer; one permission per endpoint
    │   │   └── security/          argon2 passwords, JWT cookie + CSRF, role matrix, login limiter
    │   ├── scripts/               create_admin, seed_demo, import_v1, verify_v1, gen_docs
    │   └── tests/
    ├── frontend/          React + TypeScript + Vite (own package.json)
    └── docs/
```

**Layering:** routers validate input and check permission; services hold all rules and run in one transaction per operation; models enforce what must never break even if code is wrong (CHECK constraints, unique indexes, triggers).

**Money:** integer **paise** everywhere in storage and logic; decimal strings at the API edge; the browser only formats for display and never calculates pay. Rounding (half-up) happens in one place (overtime pay) and in averages.

## 3. Payroll lifecycle

```
draft ──review──▶ reviewed ──finalize──▶ finalized ──reverse (reason)──▶ reversed
  ▲                  │                       │
  └──── reopen ──────┘                       └─ a corrected run may then be created for the same period
```

- **Create:** one live run per calendar month (partial unique index + `Idempotency-Key` for repeats). Eligible = active employees whose joining date is on/before the period end. Each employee's standing inputs are copied into a *snapshot row* with the overtime rate used.
- **Draft:** per-employee adjustments (bonus, deductions, overtime hours, attendance); the server recalculates and re-flags.
- **Review flags** (explainable, thresholds configurable): negative net pay and attendance above the days in the month are *errors* (finalization needs an explicit, audited acknowledgement); high overtime, unusual basic-salary change versus the last finalized run, and missing joining date are *warnings*. Flags are review indicators, never findings of fraud.
- **Finalize:** one transaction. Re-calculates every item from its stored inputs and refuses on any mismatch, writes totals, records who/when. Repeating the request is a safe no-op. Optional rule: the creator cannot finalize.
- **Immutability:** SQLite triggers reject UPDATE/DELETE/INSERT on finalized items and on a finalized run's period, rate, totals and finalizer. Employee edits later never change history because identity fields are copied into the snapshot.
- **Correction policy:** see `schema.md`. Reverse (authorized, written reason, audited) → create a corrected run. Nothing is silently modified.

## 4. Where each number comes from

| Screen / file | Source |
|---|---|
| Dashboard, Analytics | finalized snapshots only (drafts, reviewed, reversed excluded); current headcount from the employee table is labelled as current |
| Payslip PDF, payroll CSV/Excel, department report | the finalized snapshot of the chosen run; totals recomputed from the exported rows and tested equal to the stored totals |
| Employee register CSV | the current employee directory |

## 5. Not implemented on purpose

**Statutory deductions (PF, ESI, TDS, tax)** are not calculated. Their rates, eligibility rules and effective dates were not provided, and inventing them would be wrong. Deductions are an amount entered by HR. Payslips and the UI say so.

## 6. Key decisions and trade-offs

- **SQLite** for the initial V2 (single file, easy to run). One writer at a time; adequate for a small HR team. The data layer is SQLAlchemy, so moving to PostgreSQL is a configuration and migration task, not a rewrite (not done or tested here).
- **No migration tool yet.** Tables are created on startup; one added column is handled by a small startup step. A real schema change needs Alembic.
- **Server-side everything that matters:** pay calculation, flags, totals, PDFs and exports are server-generated; the client sends inputs and renders results.
- **Cookie sessions + CSRF header** (not tokens in localStorage), same-origin via a reverse proxy in production.
