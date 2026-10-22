# Completed vs deferred

"Completed" means implemented end to end (UI → API → database) **and** covered by automated tests. See the README for what could not be verified.

## Completed

| Area | Delivered |
|---|---|
| V1 preservation | V1 untouched; hash baseline + `verify_v1` script + test; V1 runs independently; V2 uses its own database and refuses V1's |
| Employees | Create, view, edit, deactivate/reactivate (history kept); search, sort, filter (department, status), pagination; unique IDs; CSV import with preview, duplicate detection and row-level errors |
| Payroll runs | Period selection and validation; eligibility; calculation by the V1 rules; reviewable breakdown; flags; draft → reviewed → finalized; duplicate-run prevention; idempotent create and finalize; transactional finalization; immutable snapshots; authorized, audited reversal and corrected re-run |
| Payslips | Itemized PDF generated from the finalized snapshot; preview and download; list and retrieve past payslips; unavailable for drafts and reversed runs |
| Dashboard | Real KPIs for a selected period; department chart; trend only with 3+ periods; recent runs; items needing review with links; sample-data labelling; "how calculated" |
| Analytics | Salary distribution; department spend; monthly trend; average/highest/lowest net; bonus, deductions, overtime and attendance statistics; change over time (adjacent months only); explainable data-quality flags with configurable thresholds |
| Reports & exports | Employee register CSV; payroll register CSV; formatted Excel workbook (summary, register, department sheets); department CSV; filtered analytics CSV; payslip PDF; formula-injection protection; safe predictable filenames |
| Security | Login with argon2; httpOnly session cookie + CSRF; four roles enforced server-side on every endpoint (route-by-route matrix test); login rate limiting; user management; password change/reset with session invalidation; optional separation of duties; security headers; request-size limit; permission-denial and export auditing |
| Admin | Settings (overtime rate, thresholds, separation-of-duties); audit log with filters; users |
| Tooling | Sample-data seeder (V2 DB only); read-only V1 importer; generated API and schema docs kept current by a test |
| Tests | Backend: pytest (formula, parity with V1, CRUD, runs, immutability, concurrency, analytics, exports, PDFs, auth, permissions, scripts). Frontend: Vitest + Testing Library (loading, error, empty and success states, validation, confirmations, role-based UI) |

## Deferred / not done

| Item | Why / note |
|---|---|
| Statutory deductions (PF, ESI, TDS, tax) | No rules, rates or effective dates were provided; deliberately not invented |
| Database migrations (Alembic) | Needed before any schema change on a live database |
| PostgreSQL | SQLAlchemy makes it feasible; not configured or tested |
| Shared login rate limiter / multiple workers | Limiter is in-process memory |
| MFA / SSO / password-reset by email | Local accounts only |
| Bulk payslip ZIP, emailing payslips | Single-payslip download only |
| Proration for partial months, multiple currencies, multiple companies | Out of scope; INR, calendar-month periods, one company |
| Employee salary-history screen | Data is recorded (`employee_salary_history`) and feeds flags; no UI |
| Attendance calendar / working-day rules | Attendance is a number of days; no percentage is shown |
| Browser-level end-to-end tests (e.g. Playwright) | Not available in the build environment |
| Automated accessibility audit (axe) and screen-reader pass | Semantic markup, labels, focus styles and table alternatives for charts are in place but unaudited |
| Visual QA in real browsers | Not performed in the build environment; please review the UI once |
| Backups / scheduled jobs | Copy the SQLite file; no tooling provided |
