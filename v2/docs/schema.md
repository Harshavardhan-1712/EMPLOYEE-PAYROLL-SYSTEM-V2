# Database schema (V2)

_Generated from the SQLAlchemy models by `python -m scripts.gen_docs` -- do not edit by hand._

SQLite, stored at `PV2_DATABASE_PATH` (default `backend/data/payroll_v2.db`). **Separate from V1's `employee_data.db`**: V2 refuses to open that file or any file in V1's directory.
All money columns are **integer paise** (1/100 rupee). Timestamps are UTC. Foreign keys are enforced (`PRAGMA foreign_keys=ON`).

## Tables

### `employees`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | — | primary key |
| `employee_code` | VARCHAR(32) | no | — | unique |
| `name` | VARCHAR(120) | no | — | — |
| `department` | VARCHAR(80) | no | — | — |
| `designation` | VARCHAR(80) | no | — | — |
| `joining_date` | DATE | yes | — | — |
| `status` | VARCHAR(10) | no | `active` | — |
| `basic_salary_paise` | INTEGER | no | — | — |
| `bonus_paise` | INTEGER | no | `0` | — |
| `deductions_paise` | INTEGER | no | `0` | — |
| `overtime_hours` | NUMERIC(8, 2) | no | `0` | — |
| `attendance_days` | INTEGER | no | `0` | — |
| `is_sample` | BOOLEAN | no | `False` | — |
| `created_at` | DATETIME (UTC) | no | — | — |
| `updated_at` | DATETIME (UTC) | no | — | — |
| `deactivated_at` | DATETIME (UTC) | yes | — | — |

- check `ck_emp_counts_nonneg`: `overtime_hours >= 0 AND attendance_days >= 0`
- check `ck_emp_money_nonneg`: `basic_salary_paise >= 0 AND bonus_paise >= 0 AND deductions_paise >= 0`
- check `ck_emp_status`: `status IN ('active','inactive')`
- index `ix_emp_dept_status` on (department, status)

### `users`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | — | primary key |
| `username` | VARCHAR(64) | no | — | unique |
| `full_name` | VARCHAR(120) | no | — | — |
| `password_hash` | VARCHAR(255) | no | — | — |
| `role` | VARCHAR(20) | no | — | — |
| `is_active` | BOOLEAN | no | `True` | — |
| `is_sample` | BOOLEAN | no | `False` | — |
| `token_version` | INTEGER | no | `0` | — |
| `created_at` | DATETIME (UTC) | no | — | — |

- check `ck_user_role`: `role IN ('viewer','hr_editor','payroll_approver','admin')`

### `audit_events`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | — | primary key |
| `at` | DATETIME (UTC) | no | — | — |
| `actor_id` | INTEGER | yes | — | → `users.id` |
| `actor_username` | VARCHAR(64) | yes | — | — |
| `action` | VARCHAR(64) | no | — | — |
| `entity_type` | VARCHAR(40) | yes | — | — |
| `entity_id` | VARCHAR(40) | yes | — | — |
| `detail` | TEXT | no | `{}` | — |

- index `ix_audit_events_action` on (action)
- index `ix_audit_events_at` on (at)

### `employee_salary_history`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | — | primary key |
| `employee_id` | INTEGER | no | — | → `employees.id` (RESTRICT) |
| `old_basic_paise` | INTEGER | yes | — | — |
| `new_basic_paise` | INTEGER | no | — | — |
| `changed_by` | INTEGER | yes | — | → `users.id` |
| `changed_at` | DATETIME (UTC) | no | — | — |

- index `ix_employee_salary_history_employee_id` on (employee_id)

### `payroll_runs`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | — | primary key |
| `period` | VARCHAR(7) | no | — | — |
| `status` | VARCHAR(10) | no | `draft` | — |
| `overtime_rate_paise` | INTEGER | no | — | — |
| `idempotency_key` | VARCHAR(64) | yes | — | unique |
| `is_sample` | BOOLEAN | no | `False` | — |
| `employee_count` | INTEGER | yes | — | — |
| `total_gross_paise` | INTEGER | yes | — | — |
| `total_deductions_paise` | INTEGER | yes | — | — |
| `total_net_paise` | INTEGER | yes | — | — |
| `created_by` | INTEGER | yes | — | → `users.id` |
| `created_at` | DATETIME (UTC) | no | — | — |
| `reviewed_by` | INTEGER | yes | — | → `users.id` |
| `reviewed_at` | DATETIME (UTC) | yes | — | — |
| `finalized_by` | INTEGER | yes | — | → `users.id` |
| `finalized_at` | DATETIME (UTC) | yes | — | — |
| `reversed_by` | INTEGER | yes | — | → `users.id` |
| `reversed_at` | DATETIME (UTC) | yes | — | — |
| `reversal_reason` | VARCHAR(500) | yes | — | — |

- check `ck_run_period_fmt`: `period GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'`
- check `ck_run_rate`: `overtime_rate_paise >= 0`
- check `ck_run_status`: `status IN ('draft','reviewed','finalized','reversed')`
- unique index `uq_run_period_live` on (period) **where** `status != 'reversed'`

### `payroll_settings`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `key` | VARCHAR(64) | no | — | primary key |
| `value` | VARCHAR(255) | no | — | — |
| `updated_by` | INTEGER | yes | — | → `users.id` |
| `updated_at` | DATETIME (UTC) | no | — | — |

### `payroll_run_items`

| Column | Type | Null | Default | Notes |
|---|---|---|---|---|
| `id` | INTEGER | no | — | primary key |
| `run_id` | INTEGER | no | — | → `payroll_runs.id` (RESTRICT) |
| `employee_id` | INTEGER | no | — | → `employees.id` (RESTRICT) |
| `employee_code` | VARCHAR(32) | no | — | — |
| `employee_name` | VARCHAR(120) | no | — | — |
| `department` | VARCHAR(80) | no | — | — |
| `designation` | VARCHAR(80) | no | — | — |
| `basic_paise` | INTEGER | no | — | — |
| `bonus_paise` | INTEGER | no | — | — |
| `overtime_hours` | NUMERIC(8, 2) | no | — | — |
| `overtime_rate_paise` | INTEGER | no | — | — |
| `overtime_pay_paise` | INTEGER | no | — | — |
| `gross_paise` | INTEGER | no | — | — |
| `deductions_paise` | INTEGER | no | — | — |
| `net_paise` | INTEGER | no | — | — |
| `attendance_days` | INTEGER | no | `0` | — |
| `flags` | TEXT | no | `[]` | — |

- unique `uq_item_run_emp`: (run_id, employee_id)
- index `ix_payroll_run_items_employee_id` on (employee_id)
- index `ix_payroll_run_items_run_id` on (run_id)

## Immutability triggers

Finalized payroll cannot be changed even by raw SQL. These triggers are created with the tables:

- `trg_items_no_update` — aborts with: _finalized payroll items are immutable_
- `trg_items_no_delete` — aborts with: _finalized payroll items are immutable_
- `trg_items_no_insert` — aborts with: _cannot add items to a finalized payroll run_
- `trg_runs_no_delete` — aborts with: _finalized payroll runs cannot be deleted_
- `trg_runs_frozen` — aborts with: _finalized payroll runs are immutable; reverse explicitly instead_

## Correction policy for finalized payroll

1. A finalized run and its items are never edited or deleted (enforced by the triggers above).
2. A user with `payroll:reverse` reverses the run with a written reason (≥10 characters). The run becomes `reversed`, its figures stay on record, and its payslips stop being valid.
3. The partial unique index `uq_run_period_live` then frees the period, and a corrected run can be created, reviewed and finalized.
4. Reversal, the reason, and the actor are recorded in `audit_events`. Reports and analytics count only `finalized` runs.
