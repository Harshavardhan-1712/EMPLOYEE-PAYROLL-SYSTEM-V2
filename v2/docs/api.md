# API reference

_Generated from the running code by `python -m scripts.gen_docs` -- do not edit by hand._

Interactive docs (Swagger UI) are served at `/api/docs` outside production (disabled when `PV2_ENV=production`).

## Conventions

- **Auth:** `POST /api/auth/login` sets an httpOnly session cookie and a readable `pv2_csrf` cookie. Every `POST`/`PATCH`/`DELETE` must send that value in the `X-CSRF-Token` header. A missing or wrong token gives `403`.
- **Errors:** every error is `{"error": {"code", "message", "details"?}}`; `details` is a list of `{field, message}` for `422`. No stack traces or paths are returned. Codes: 400, 401, 403, 404, 409 (conflict / wrong state), 413, 422, 429.
- **Money** is a decimal string in rupees (e.g. `"50000.00"`) in requests and responses. Storage is integer paise. Overtime hours are decimal strings.
- **Pagination:** list endpoints take `page` (from 1) and `page_size` (max 100, audit log 200) and return `{items, total, page, page_size}`.
- **Idempotency:** `POST /api/payroll-runs` accepts an `Idempotency-Key` header (8-64 chars `[A-Za-z0-9_.-]`); replaying the same key returns the same run with `200`.
- **Periods** are calendar months `YYYY-MM`. A permission shown as `signed in` needs only a valid session; `public` needs none.
- Columns: `*` marks a required query parameter.

## Roles and permissions

| Permission | viewer | hr_editor | payroll_approver | admin |
|---|---|---|---|---|
| `analytics:read` | yes | yes | yes | yes |
| `audit:read` | — | — | — | yes |
| `employees:import` | — | yes | — | yes |
| `employees:read` | yes | yes | yes | yes |
| `employees:write` | — | yes | — | yes |
| `payroll:finalize` | — | — | yes | yes |
| `payroll:read` | yes | yes | yes | yes |
| `payroll:reverse` | — | — | yes | yes |
| `payroll:review` | — | — | yes | yes |
| `payroll:run` | — | yes | yes | yes |
| `payslips:read` | yes | yes | yes | yes |
| `reports:export` | — | yes | yes | yes |
| `settings:read` | — | — | — | yes |
| `settings:write` | — | — | — | yes |
| `users:manage` | — | — | — | yes |

Permissions are checked on the server for every request; the UI only hides what a role cannot use.

## Health

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/health` | `public` | — | — | — | 200 object |  |

## Auth

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `POST` | `/api/auth/login` | `public` | — | — | LoginIn | 200 UserOut |  |
| `POST` | `/api/auth/logout` | `public` | — | — | — | 204 no body |  |
| `GET` | `/api/auth/me` | `signed in` | — | — | — | 200 UserOut |  |
| `POST` | `/api/auth/change-password` | `signed in` | — | — | ChangePasswordIn | 204 no body |  |

## Employees

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/employees` | `employees:read` | — | `q`, `department`, `status`, `sort`, `order`, `page`, `page_size` | — | 200 Page_EmployeeOut_ |  |
| `GET` | `/api/employees/departments` | `employees:read` | — | — | — | 200 list[string] |  |
| `POST` | `/api/employees` | `employees:write` | — | — | EmployeeIn | 201 EmployeeOut |  |
| `POST` | `/api/employees/import` | `employees:import` | — | `commit` | multipart file | 200 ImportResult |  |
| `GET` | `/api/employees/{employee_id}` | `employees:read` | `employee_id` | — | — | 200 EmployeeOut |  |
| `PATCH` | `/api/employees/{employee_id}` | `employees:write` | `employee_id` | — | EmployeePatch | 200 EmployeeOut |  |
| `POST` | `/api/employees/{employee_id}/deactivate` | `employees:write` | `employee_id` | — | — | 200 EmployeeOut |  |
| `POST` | `/api/employees/{employee_id}/reactivate` | `employees:write` | `employee_id` | — | — | 200 EmployeeOut |  |

## Payroll

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/payroll-runs` | `payroll:read` | — | `status`, `period`, `page`, `page_size` | — | 200 Page_RunOut_ |  |
| `POST` | `/api/payroll-runs` | `payroll:run` | — | — | RunCreate | 201 RunDetail |  |
| `GET` | `/api/payroll-runs/{run_id}` | `payroll:read` | `run_id` | — | — | 200 RunDetail |  |
| `PATCH` | `/api/payroll-runs/{run_id}/items/{item_id}` | `payroll:run` | `run_id`, `item_id` | — | ItemPatch | 200 ItemOut |  |
| `POST` | `/api/payroll-runs/{run_id}/review` | `payroll:review` | `run_id` | — | — | 200 RunOut |  |
| `POST` | `/api/payroll-runs/{run_id}/reopen` | `payroll:review` | `run_id` | — | — | 200 RunOut |  |
| `POST` | `/api/payroll-runs/{run_id}/finalize` | `payroll:finalize` | `run_id` | — | — | 200 RunOut |  |
| `POST` | `/api/payroll-runs/{run_id}/reverse` | `payroll:reverse` | `run_id` | — | ReverseIn | 200 RunOut |  |
| `DELETE` | `/api/payroll-runs/{run_id}` | `payroll:run` | `run_id` | — | — | 204 no body |  |

## Payslips

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/payslips` | `payslips:read` | — | `run_id`, `period`, `employee_id`, `q`, `page`, `page_size` | — | 200 Page_PayslipRow_ | Payslips exist only for finalized runs. |
| `GET` | `/api/payslips/{employee_id}/{run_id}.pdf` | `payslips:read` | `employee_id`, `run_id` | `download` | — | 200 file download |  |
| `GET` | `/api/payslips/{employee_id}/{run_id}` | `payslips:read` | `employee_id`, `run_id` | — | — | 200 PayslipOut |  |

## Analytics

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/dashboard/summary` | `analytics:read` | — | `period` | — | 200 DashboardSummary |  |
| `GET` | `/api/analytics/summary` | `analytics:read` | — | `from`, `to`, `department` | — | 200 AnalyticsSummary |  |

## Reports

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/reports/employees.csv` | `reports:export` | — | `status`, `department` | — | 200 file download |  |
| `GET` | `/api/reports/payroll.csv` | `reports:export` | — | `run_id`* | — | 200 file download |  |
| `GET` | `/api/reports/payroll.xlsx` | `reports:export` | — | `run_id`* | — | 200 file download |  |
| `GET` | `/api/reports/department.csv` | `reports:export` | — | `run_id`* | — | 200 file download |  |
| `GET` | `/api/reports/analytics.csv` | `reports:export` | — | `from`, `to`, `department` | — | 200 file download |  |

## Users

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/users` | `users:manage` | — | — | — | 200 list[UserAdminOut] |  |
| `POST` | `/api/users` | `users:manage` | — | — | UserCreate | 201 UserAdminOut |  |
| `PATCH` | `/api/users/{user_id}` | `users:manage` | `user_id` | — | UserPatch | 200 UserAdminOut |  |
| `POST` | `/api/users/{user_id}/reset-password` | `users:manage` | `user_id` | — | PasswordIn | 204 no body |  |

## Admin

| Method | Path | Permission | Path params | Query | Body | Success | Notes |
|---|---|---|---|---|---|---|---|
| `GET` | `/api/settings` | `settings:read` | — | — | — | 200 SettingsOut |  |
| `PATCH` | `/api/settings` | `settings:write` | — | — | SettingsPatch | 200 SettingsOut |  |
| `GET` | `/api/audit-log` | `audit:read` | — | `action`, `actor`, `entity_type`, `entity_id`, `page`, `page_size` | — | 200 Page_AuditOut_ |  |
