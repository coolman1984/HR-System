# Migration record: Department-automation → HR-System

Date: 2026-09-27. Status: **stage 1 (migrate and prove HR alone) done; stage 2 (shared employee contract) done;
stage 3 (GMES connected) done behind a switch.** Deeper integrations not started (see "Next").

## 1. Where the old HR source was found
The owner's account was scanned (file lists of every branch, 32 repositories incl. the likely private ones)
for HR signs (employee, attendance, payroll, leave, roster, shift, personnel). Exactly one HR system exists:

**`coolman1984/Department-automation`** — product name *HR Attendance Control* (V1.0), Python 3.10+ standard
library + bundled `openpyxl` (`vendor.zip`), offline, `START.bat` → local browser dashboard.
It is NOT `Mr.Ayman-HR` (that is BAMS, a break-area app, deliberately left untouched and independent).

The source repository was **read only**: nothing was pushed, renamed, moved or changed there
(its `main` is still `e509b86`, its branch still `58a2298`).

## 2. Which branch/version and why
| Branch | Tip | vs `main` | Content |
|---|---|---|---|
| `main` | `e509b86` | — | Foundation only (attendance import, 2 commits) |
| `claude/sonnet-5-high-execution-brief-wttlo5` | **`58a2298`** | **+5 / −0** | Foundation + BLD-01 + INT-01 (employee link) + INT-02 (roster and leave link) + INT-03 (4-file upload UI) |

The feature branch is a strict fast-forward of `main` (nothing on `main` is missing from it), carries all tested work
and a clean handoff (`.workflow/HANDOFF_AR.md`). **Selected: `58a2298`.** No unfinished work existed elsewhere;
the open items are decisions, not code (see §8).

## 3. What was copied — with history
Git history was preserved, not re-committed: all 7 commits with original authors, dates and messages.
- `HR-System/main` = `58a2298` (identical commit ids to the source).
- `HR-System/archive/department-automation-main` = `e509b86` (the old `main`, for traceability).
- A tag `import/department-automation-58a2298` exists locally but the session's Git proxy refuses tag pushes (HTTP 403); this record replaces it.

Migration work lives on branch `claude/zen-maxwell-2giusj`, on top of the imported `main`.

## 4. What was intentionally excluded
Nothing had to be removed from history: a scan of every commit found **no secrets** (no passwords, tokens, keys,
private hosts or user paths), and all spreadsheets are the **synthetic** dataset ("لا توجد بيانات حقيقية لأي شركة أو
موظف" — `inputs/hr-factory-synthetic-dataset/START_HERE_AR.txt`).

Never copied, and kept out by `.gitignore` (already in the source): the runtime folders a real installation creates —
`data/` (history.db with real attendance, uploads archive, app.log), `runtime-data/`, `incoming/`, `quarantine/`,
`*.db`, `*.log`, `__pycache__/` — and the built delivery ZIP (written OUTSIDE the repository by `BUILD_PROJECT.py`).
**If an installed copy exists on a Windows PC, its `data/` folder holds real employee data and must never be committed.**

## 5. Tests before and after
| Check | Source @58a2298 | HR-System (this branch) |
|---|---|---|
| `CHECK_ENVIRONMENT.py` | pass | pass |
| `SMOKE_TEST.py` | pass | pass |
| `TEST_HR_FOUNDATION.py` | pass* | pass* |
| `TEST_INT01_MULTI_SOURCE.py` | pass* | pass* |
| `TEST_INT02_ROSTER_LEAVE_LINK.py` | pass* | pass* |
| `TEST_INT03_HTTP_MULTI_UPLOAD.py` | pass* | pass* |
| `BUILD_PROJECT.py` (ZIP 0.40 MB, 27 files) | pass | pass, same file list |
| **new** `TEST_MIGRATION_EQUIVALENCE.py` | golden produced here | **0 differences** in 5 scenarios |
| **new** `TEST_ECO_PUBLISHER.py` | — | 9/9 |
| **new** `migration/mutations.py` | — | 6/6 planted bugs caught |

\* These four import `openpyxl` directly, which the original author had installed system-wide; the application itself
loads it from `vendor.zip`. They pass with `PYTHONPATH=vendor.zip` (what CI sets). Recorded, not changed.

**Equivalence method:** `TEST_MIGRATION_EQUIVALENCE.py` ran against the ORIGINAL checkout to write
`migration/golden_behaviour.json` (every KPI, chart value, warning, reconciliation, auxiliary report and a SHA-256
of every stored row, over five scenarios: clean import, same bytes renamed, delta correction, 4-file upload,
stress-dirty 4-file upload). The migrated tree reproduces it exactly.

### Behaviour found and pinned, NOT changed (preserve first, fix later by decision)
1. **Re-uploading the same attendance bytes together with new employee/roster/leave files is treated as an
   already-processed upload; the new auxiliary files are ignored** (scenario 4 in the golden file). The notice says
   "already processed", which is true for attendance but hides that the enrichment did not happen.
2. `TEST_HR_FOUNDATION.py` rewrites the tracked file `sample/HR_Attendance_Delta_Demo.xlsx` every run.
3. Employee enrichment on merged rows comes from the upload that last touched each row, so two rows of the same
   employee can carry different employment statuses; the publisher picks the row with the latest work date.

## 6. New HR-System architecture (unchanged core + one additive boundary)
```
  Excel uploads ──► engine.py / calculation_engine.py (LOCKED CORE, unchanged) ──► data/history.db
                                                                                        │ engine.current_rows()
                                                                   eco_publisher.py ◄───┘  (reads only)
                                                                        │ stage: snapshot + version
                                                                        ▼
                                                              data/eco_outbox.db  (pending | delivered | rejected)
                                                                        │ POST /eco/v1/inbox (retry, same stored bytes)
                                                                        ▼
                                                              GMES (manufacturing) read-only mirror
```
- HR stays **independently installable**: without `ECO_GMES_URL` the publisher is disabled and touches nothing.
- The contract schemas are vendored from the single source (`GMES/packages/eco-contracts`) in `eco_schemas/` and
  checked by a standard-library validator (`eco_contract.py`) that refuses unknown schema keywords.
- The delivery ZIP is unchanged (`BUILD_PROJECT.py` has an explicit file list); packaging the publisher is a next step.

## 7. HR ↔ GMES contracts
| Contract | Owner | Consumer | Carries | Identity |
|---|---|---|---|---|
| `eco.employee.v1` | HR-System | GMES (mirror), later Mizan, 3D | code (Employee_ID), employment status, active, hire/termination date, optional department/position/plant codes. **No personal data.** | UUIDv5(company, `hr:employee:<Employee_ID>`) |
| `eco.attendance_day.v1` | HR-System | GMES (mirror) | employee ref, work date, status, scheduled shift, roster shift/status, leave, worked minutes | UUIDv5(company, `hr:attendance:<Attendance_ID>`) |
| `mes.*` facts (`performed_by.person`) | GMES | HR (later: labour hours per employee) | who did what, where, in which shift | shared employee id |

GMES checks every production command that names a person against its HR mirror (unknown → `person.unknown`,
not active → `person.inactive`) when `ownership.person = 'hr'`. With `'none'` it behaves exactly as before
(the rollback switch; nothing was deleted).

## 8. Payroll — one truth
- **HR-System owns workforce and payroll CALCULATION data**: base pay, allowances, deductions, overtime pay,
  bonuses, gross/net per employee and period (the `08_Payroll_Compensation` domain of the data dictionary).
- **Mizan owns the accounting ENTRIES and the books**: it receives one posting per payroll period (totals per
  cost center and account: gross salaries, employer contributions, deductions payable, net payable) and books it.
- Mizan never stores employees and never recalculates pay; HR never posts journals. Mizan's roadmap item
  "Payroll (basic): employees" must become "Payroll posting from HR" (proposal for that repository).
- Contract to add when HR computes payroll: `hr.payroll_period.v1` (📐 not built).

## 9. Remaining gaps and next safest step
- HR does not yet keep an employee master of its own: employees exist as enrichment of attendance rows. Next: an
  explicit ADR + test to import `EMP_01_EmployeeMaster` as its own entity (then every employee is published, not
  only those with attendance), plus departments/positions (`eco.org_unit.v1`).
- Fix quirk 1 (§5) behind a test that first reproduces it.
- Package `eco_publisher.py` in the delivery ZIP and start it with `START.bat` (ADR first).
- Windows run of `START.bat` and protected-workbook COM path: still unverified (as in the source); CI now runs the
  Python tests on Windows.
- Shifts catalogue (`SCH_01_ShiftDefinitions`), skills and station qualifications (`SKL_*`) → contracts for GMES's
  labour module; HR work-center codes ↔ GMES station codes ↔ 3D `meta["eco.ref"]`.

**Done 2026-09-27 (phase 1 of docs/HR_SYSTEM_DESIGN.md):** HR now has its own employee registry and organisation in
`hr_core/` (beside the locked engine), and the publisher takes employees from it. **Next safest step:** users,
permissions, device identity and verified backups (phase 2), before any new domain module.

## 10. Safety fix made during migration
The source `.gitignore` did not exclude `data/`. A real installation keeps `data/last_result.json` (the current
attendance table) and `data/uploads/` (every uploaded workbook) there — real employee data one `git add .` away
from GitHub. `data/` and `uploads/` are now ignored. The application's behaviour is untouched.
