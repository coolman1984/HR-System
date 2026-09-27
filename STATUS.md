# STATUS — where HR-System stands

Read this first after an interruption, then `AGENT_HANDOFF.md`. `TEST_DOCS_CURRENT.py` fails when this file falls
behind the code, so what it says is checked, not remembered.

Labels used everywhere in this repository:
**Built and tested** = in the code and proven by a test in CI · **Partially built** = some of it exists, the limit is
written next to it · **Planned** = designed, no code · **Design only** = architecture on paper, must not be built yet.

## Current stage

**Phase 2.5 — HR-System as one installable product** (`docs/HR_DELIVERY.md`). Phase 3 (shifts) waits until this
gate is closed. Stage 3.0 (the continuity documents and their guard) is done and merged.

**Exit gate of phase 2.5:** installed from scratch on a clean Windows without Python and without internet; first
administrator and sign-in; employee register; permissions; attendance with the same numbers; backup, rehearsal and
restore; a restart loses nothing; an update over an installed version keeps data, accounts and journal; a failure
and a power cut in the middle of an update are survived; every HR test and planted bug; GMES's real HR end-to-end
test against the new commit.

**Where it stands:** everything above is built and passes on Linux (`TEST_HR_DELIVERY.py`, 72 checks) and, for the
installed program, in the CI job `windows-installer` (`tools/installed_acceptance.py`: Python hidden from the
program, outbound network blocked). Still owed before the gate closes: the owner's clean-PC run in Windows Sandbox
(`installer/clean-pc-test.wsb`, `docs/HR_DELIVERY.md` §5), because the CI machine has Python installed.

## Built and tested

| What | Where | Proof |
|---|---|---|
| `attendance` — the migrated attendance application: daily Excel import, merge by `Attendance_ID`, duplicate-file refusal, last good result kept on a bad file, history and restore, dashboard | `engine.py`, `calculation_engine.py`, `dashboard.html`, `PROJECT.json` (locked core, `LOCKED_CORE.json`) | `TEST_HR_FOUNDATION.py`, `SMOKE_TEST.py` |
| Four files uploaded together: attendance + employee + roster + leave, employee joined 1:1, roster by employee + date, leave by date range (approved, not cancelled) | same engine, `/api/upload_multi` | `TEST_INT01_MULTI_SOURCE.py`, `TEST_INT02_ROSTER_LEAVE_LINK.py`, `TEST_INT03_HTTP_MULTI_UPLOAD.py` |
| `leave` — leave linked to attendance days (inside the migrated engine; see Partially built for the rest) | same engine | `TEST_INT02_ROSTER_LEAVE_LINK.py` |
| Behaviour of the migrated application frozen against the original repository (0 differences, 5 scenarios) | `migration/golden_behaviour.json` | `TEST_MIGRATION_EQUIVALENCE.py` |
| `kernel` — company → site → business unit → department → section, jobs, positions, employee registry (employment data only, no personal data), safe Excel import, optimistic versions, soft delete and Recycle Bin, rebuild from the journal | `hr_core/registry.py`, `hr_core/importer.py`, `hr_registry.py` | `TEST_HR_REGISTRY.py` (13) |
| Users, profiles, 12 server-side permissions checked on every request, sessions, lockout, device identity with clone detection, signed append-only journal and audit, verified backups, automatic restore rehearsal, compensating restore, recovery of a lost `hr.db` / `auth.db` / journal | `hr_core/auth.py`, `hr_core/service.py`, `hr_core/api.py`, `hr_core/device.py`, `hr_core/journal.py`, `hr_core/signing.py`, `hr_core/backup.py`, `hr_server.py` | `TEST_HR_SECURITY.py` (79), `docs/HR_SECURITY.md` |
| Ecosystem publisher: `eco.employee.v1` (from the registry) and `eco.attendance_day.v1`, outbox, retry with the same stored bytes, no duplicates; disabled without `ECO_GMES_URL` | `eco_publisher.py`, `eco_contract.py`, `eco_schemas/` | `TEST_ECO_PUBLISHER.py` (9), GMES `hr-e2e` against this repository |
| Module and edition map (`kernel`, `attendance`, `leave` built) | `hr_core/modules.py` | `TEST_HR_REGISTRY.py` |
| Documentation guard | `TEST_DOCS_CURRENT.py` | itself, and its planted bugs in `migration/mutations.py` |
| One product (phase 2.5): one server, one port, one sign-in; screens for employees and organisation, attendance, users and permissions, backups, system health, settings; English and Arabic dictionaries with the same keys | `hr_main.py`, `hr_core/app.py`, `hr_core/web.py`, `hr_core/web/`, `hr_core/api.py` | `TEST_HR_DELIVERY.py` |
| The locked attendance engine behind the same sign-in (`hr.attendance.read` / `hr.attendance.upload`), same golden numbers, uploads audited | `hr_core/attendance.py` | `TEST_HR_DELIVERY.py` |
| Installation home outside the program, company identity from its owner (Mizan) or local and provisional, never changed silently | `hr_core/home.py`, `hr_core/registry.py` | `TEST_HR_DELIVERY.py` |
| Data versions: verified pre-update backup kept forever, step-by-step update, put back on failure, resume after a power cut, newer data refused; one known-good recovery installer with its SHA-256 | `hr_core/upgrade.py`, `hr_core/version.py` | `TEST_HR_DELIVERY.py` |
| Backups carry the attendance history (copied while no upload runs); a lost history comes back from a backup | `hr_core/backup.py` | `TEST_HR_DELIVERY.py` |
| Windows installer: compiled program with its own runtime and `cryptography`, data in `%ProgramData%\HR-System`, start with Windows by default, old attendance data copied on first install, Excel detected | `tools/build_windows.py`, `installer/hr-system.iss` | CI `windows-installer` (`tools/installed_acceptance.py`) |

## Partially built

| What | What exists | What is missing |
|---|---|---|
| Delivery to a customer | The Windows installer (phase 2.5) installs the whole product; `BUILD_PROJECT.py` still builds the old attendance ZIP as the engine's rollback line | A run on a truly clean PC (Windows Sandbox, `docs/HR_DELIVERY.md` §5); a code-signing certificate before selling (Windows shows "unknown publisher") |
| Screens | Every phase-1/2 capability has a screen, in English and Arabic | The attendance dashboard is the locked engine's own page (English only); importing workbooks is still a command (`hr_registry.py import`) |
| Company identity | From Mizan at setup, or local and provisional | The adoption step (a local id later matched to Mizan's) is planned, not built |
| Eco publisher in the product | Built and tested (`eco_publisher.py`) and compiled into the program | Not started by the installed program yet (no screen to configure `ECO_GMES_URL`) |
| Leave | Linked to attendance days at import | Leave requests, approval and balances as an HR module |
| Attendance ↔ official employee | Attendance is enriched from the **uploaded** employee file | Binding to the registry employee (phase 4) |
| LAN use | `hr_server.py serve --host` | No TLS yet (BAMS's pinned-certificate pattern is the plan, `docs/HR_SECURITY.md` §4) |
| Windows | CI runs every Python test on Windows and accepts the installed program | The protected-workbook Excel path never ran on a PC with Excel |
| Signing library | `cryptography` bundled in the installed program; BAMS's vendored file remains the fallback for source checkouts (ADR-HR-002) | — |

## Planned

| What | Phase |
|---|---|
| `shifts` — shift definitions, calendars, schedules, effective-dated assignments, rosters, swaps, planned overtime, conflicts; planned state separate from actual attendance; minimal read-only contract for GMES | 3 (next) |
| `overtime` — requests, approval and actuals, bound to shifts and attendance | 4 |
| Attendance and leave bound to the official employee and shift masters | 4 |
| `skills` — skills, certification, station and equipment qualification, contract for GMES | 5 |
| `training` — courses and completions that grant skills | 5 |
| Personal data (identity, contacts, dependants) behind encryption and permissions | after 5 |
| Company identity adoption: a provisional local id matched to Mizan's, explicitly | when a customer needs it |

## Design only

| What | Why not built |
|---|---|
| `payroll` — HR calculates pay; Mizan books one summarized entry per period (`hr.payroll_period.v1`) | Needs stable employees, attendance, leave and overtime first (`docs/HR_SYSTEM_DESIGN.md` §6). Mizan never stores employees or computes pay. |

## Next phase — 3: shifts, calendars, schedules and assignments

Model separately: shift definitions (start/end, overnight, breaks, working duration, grace rules), working calendars
(weekly rest days, holidays), effective-dated employee shift assignments, temporary assignments, daily roster
overrides, shift swaps, rest days, leave interactions, planned overtime and schedule conflicts. Everything goes through
the existing permissions, signed journal, optimistic versions, backups, audit and soft delete, in `hr_core/` beside the
locked engine.

**Exit gate:** a schedule exists before attendance and attendance is compared with it; an overnight shift has exactly
one work date; an employee cannot silently hold overlapping assignments; changing next month never rewrites last
month (effective dating); Excel re-import writes nothing the second time; a minimal read-only contract (employee,
effective assignment, shift, availability) is published and GMES keeps a last-known-good mirror that shows its age
instead of stopping the factory; new tests and planted bugs are caught; GMES's real HR end-to-end test passes. No
skills and no payroll in this phase.

## How to prove the work is right

```
python CHECK_ENVIRONMENT.py
python SMOKE_TEST.py
export PYTHONPATH=vendor.zip            (Windows: set PYTHONPATH=vendor.zip)
python TEST_HR_FOUNDATION.py            then: git checkout -- sample/
python TEST_INT01_MULTI_SOURCE.py
python TEST_INT02_ROSTER_LEAVE_LINK.py
python TEST_INT03_HTTP_MULTI_UPLOAD.py
python TEST_MIGRATION_EQUIVALENCE.py    0 differences
python TEST_ECO_PUBLISHER.py
python TEST_HR_REGISTRY.py
python TEST_HR_SECURITY.py
python TEST_HR_DELIVERY.py
python TEST_DOCS_CURRENT.py
python migration/mutations.py           every planted bug caught
python BUILD_PROJECT.py
```
On Windows (CI job `windows-installer`): `python tools/build_windows.py`, then `python tools/installed_acceptance.py`.
Then, in a GMES checkout: `sh scripts/fetch-hr.sh`, `ECO_E2E_REQUIRED=1 npm test`, `node scripts/mutations.mjs`.

**Last full run (2026-09-27, phase 2.5):** every test above passes on Linux; 58 of 58 planted bugs caught; GMES against
this repository: 15 + 29 + 10 tests pass, every GMES planted bug caught. The Windows installer job: see the pull request.

## Architecture inventory (checked by `TEST_DOCS_CURRENT.py`)

Change this block only after the documents above describe the change. `phase` is the next phase the design leaves
open; `stage` is the step inside it; `updated` is the date of the session that last changed this file.

```inventory
phase: 2.5
stage: 2.5 one installable product
updated: 2026-09-27
done_phases: 1 2
hr_core: api app attendance auth backup canonical device home importer journal modules registry service signing upgrade version web
root_python: BUILD_PROJECT CHECK_ENVIRONMENT CUSTOM_RULES SMOKE_TEST calculation_engine eco_contract eco_publisher engine hr_main hr_registry hr_server
root_python: TEST_DOCS_CURRENT TEST_ECO_PUBLISHER TEST_HR_DELIVERY TEST_HR_FOUNDATION TEST_HR_REGISTRY TEST_HR_SECURITY TEST_INT01_MULTI_SOURCE TEST_INT02_ROSTER_LEAVE_LINK TEST_INT03_HTTP_MULTI_UPLOAD TEST_MIGRATION_EQUIVALENCE
contracts: canonical-v1 eco.attendance_day.v1 eco.employee.v1 eco.envelope.v1
entities: org_unit job position employee
permissions: hr.org.read hr.org.write hr.employees.read hr.employees.write hr.employees.delete hr.recycle.restore hr.import.run
permissions: admin.users.manage admin.audit.read admin.backup.manage admin.backup.restore admin.system.read
permissions: hr.attendance.read hr.attendance.upload admin.settings.manage
module: kernel built
module: attendance built
module: leave built
module: shifts planned
module: overtime planned
module: skills planned
module: training planned
module: payroll design_only
command: hr_server serve
command: hr_server create-admin
command: hr_server backup
command: hr_server backups
command: hr_server rehearse
command: hr_server health
command: hr_registry import
command: hr_registry list
command: hr_registry verify
command: hr_registry rebuild
command: hr_main data-version
command: hr_main recovery
command: hr_main backup
command: hr_main backups
command: hr_main rehearse
route: POST /api/setup
route: POST /api/login
route: POST /api/logout
route: GET /api/me
route: POST /api/password
route: GET /api/recycle
route: GET /api/(org_unit|job|position|employee)
route: PUT /api/(org_unit|job|position|employee)/([^/]+)
route: DELETE /api/(org_unit|job|position|employee)/([^/]+)
route: POST /api/(org_unit|job|position|employee)/([^/]+)/restore
route: GET /api/admin/users
route: POST /api/admin/users
route: PATCH /api/admin/users/([^/]+)
route: POST /api/admin/users/([^/]+)/password
route: GET /api/admin/profiles
route: PUT /api/admin/profiles/([^/]+)
route: GET /api/admin/audit
route: GET /api/admin/health
route: GET /api/admin/backups
route: POST /api/admin/backups
route: POST /api/admin/backups/([^/]+)/(verify|rehearse|restore)
route: GET /api/info
route: GET /api/admin/settings
route: PUT /api/admin/settings
mutations: 58
```
