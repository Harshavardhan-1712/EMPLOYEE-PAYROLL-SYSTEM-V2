# V1 preservation record

Baseline: SHA-256 of every V1 file at the time of inspection is in `v1-baseline.sha256`
(verify from the repo root: `sha256sum -c v2/docs/v1-baseline.sha256`).

| Check | Phase | Result |
|---|---|---|
| Baseline hashes recorded before any V2 work | 1 | done |
| V1 hashes re-verified after backend foundation (7/7 files OK) | 2 | pass |
| No `employee_data.db`, `exports/` or `reports/` created in the V1 tree by V2 code or tests | 2 | pass |
| V1 run with original entry point (`python main.py`) from a throwaway copy: table created, 10 sample rows seeded, menu rendered | 2 | pass |
| V2 refuses a database path named `employee_data.db` or located in the V1 directory (unit-tested) | 2 | pass |
| V1 hashes re-verified after frontend phase (7/7 OK); V2 frontend and backend added only under `v2/` | 4 | pass |
| V1 hashes re-verified after payroll runs + payslips phase (7/7 OK) | 5 | pass |
| V1 hashes re-verified after dashboard / analytics / reports phase (7/7 OK) | 6 | pass |
| V1 hashes re-verified after security / admin phase (7/7 OK) | 7 | pass |
| V1 parity: 500 random employees, V2 rules == V1 `compute_payroll_for_employee` | 2 | pass |

### Final package checks (phase 8)

Performed on the **delivered zip, extracted into a fresh folder** (not on the working tree):

| Check | Result |
|---|---|
| All 7 V1 files compared with the baseline: `sha256sum -c v2/docs/v1-baseline.sha256` and `python -m scripts.verify_v1` | 7/7 identical |
| V1 run with its original instructions (`python main.py`, from a copy of the extracted package): table created, 10 sample employees seeded, menu rendered | pass; V1 created `employee_data.db`, `exports/`, `reports/` only inside the copy |
| Extracted package root afterwards contains no database, `exports/` or `reports/` | pass |
| V1 database imported into a fresh V2 database with `scripts.import_v1` (dry run, commit, repeat commit) | V1 file hash identical before and after all three runs; second commit skipped all 10 as duplicates |
| Sample-data seeder run against a separate V2 database | wrote only to the V2 database; refused to target V1's file name or folder (unit-tested) |
| Clean install: new virtualenv from `requirements.txt`, `npm ci` from the lockfile | backend 207/207 tests, frontend 124/124 tests, type-check and production build pass |
| Built app served (API + built frontend), signed in, dashboard, Excel workbook, payslip PDF, audit log | pass; server logs contained no passwords or secrets |
| Package contents: no `.env`, databases, virtualenv, `node_modules`, caches | pass |

Ongoing protection: `tests/test_v1_unchanged.py` (part of the backend suite) fails if any V1 file differs from the baseline, and
`python -m scripts.verify_v1` can be run at any time (it also reports, without failing, the run-time files V1 creates when it is run).

Notes
- V1 creates `employee_data.db`, `exports/`, `reports/` next to itself when run. That is V1's own behaviour, so every smoke run
  used a temp copy to keep the repository tree clean. V2 never reads or writes those files, except `scripts.import_v1`, which opens
  the database read-only and verifies it was not modified.
