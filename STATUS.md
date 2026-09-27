# STATUS — where HR-System stands

Read this first after an interruption, then `AGENT_HANDOFF.md`. `TEST_DOCS_CURRENT.py` fails when this file falls
behind the code, so what it says is checked, not remembered.

Labels used everywhere in this repository:
**Built and tested** = in the code and proven by a test in CI · **Partially built** = some of it exists, the limit is
written next to it · **Planned** = designed, no code · **Design only** = architecture on paper, must not be built yet.

## Current stage

**Phase 3 has not started.** Stage 3.0 is the documentation gate: HR-System gets the same continuity memory as GMES,
BAMS and 3D-Modeling (`HISTORY.md`, this file, `docs/LESSONS.md`, `AGENT_HANDOFF.md`, the agent skill
`.claude/skills/hr-development/SKILL.md`) and a test that keeps them honest (`TEST_DOCS_CURRENT.py`).

**Finish line of stage 3.0:** the four documents exist and agree with the code; old "attendance only" documents are
marked historical, not deleted; `TEST_DOCS_CURRENT.py` runs in CI and its planted bugs are caught; every HR test,
every planted bug and GMES's real HR end-to-end test pass; pushed as its own change. Only then phase 3 begins.

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

## Partially built

| What | What exists | What is missing |
|---|---|---|
| Delivery to a customer | `BUILD_PROJECT.py` builds a ZIP of the attendance application (`START.bat`) | The ZIP does **not** contain `hr_core/`, `hr_server.py` or `eco_publisher.py`: the registry, accounts, backups and publisher are not installable by a customer yet (needs a decision first) |
| HR server | JSON API (`hr_core/api.py`) with every route below | No screens: registry and administration are used through the API and the command line only |
| Leave | Linked to attendance days at import | Leave requests, approval and balances as an HR module |
| Attendance ↔ official employee | Attendance is enriched from the **uploaded** employee file | Binding to the registry employee (phase 4) |
| LAN use | `hr_server.py serve --host` | No TLS yet (BAMS's pinned-certificate pattern is the plan, `docs/HR_SECURITY.md` §4) |
| Windows | CI runs every Python test on Windows (red on every run until 2026-09-27, see `HISTORY.md`) | `START.bat` and the protected-workbook Excel path never run on a real target PC |
| Signing library | `cryptography` when it works, BAMS's vendored file otherwise (ADR-HR-002) | Bundling `cryptography` needs an embedded Python runtime in the installer |

## Planned

| What | Phase |
|---|---|
| `shifts` — shift definitions, calendars, schedules, effective-dated assignments, rosters, swaps, planned overtime, conflicts; planned state separate from actual attendance; minimal read-only contract for GMES | 3 (next) |
| `overtime` — requests, approval and actuals, bound to shifts and attendance | 4 |
| Attendance and leave bound to the official employee and shift masters | 4 |
| `skills` — skills, certification, station and equipment qualification, contract for GMES | 5 |
| `training` — courses and completions that grant skills | 5 |
| Personal data (identity, contacts, dependants) behind encryption and permissions | after 5 |

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
python TEST_DOCS_CURRENT.py
python migration/mutations.py           every planted bug caught
python BUILD_PROJECT.py
```
Then, in a GMES checkout: `sh scripts/fetch-hr.sh`, `ECO_E2E_REQUIRED=1 npm test`, `node scripts/mutations.mjs`.

**Last full run (2026-09-27, this stage):** every test above passes; 41 of 41 planted bugs caught; GMES against this
repository: 15 + 29 + 10 tests pass, every GMES planted bug caught.

## Architecture inventory (checked by `TEST_DOCS_CURRENT.py`)

Change this block only after the documents above describe the change. `phase` is the next phase the design leaves
open; `stage` is the step inside it; `updated` is the date of the session that last changed this file.

```inventory
phase: 3
stage: 3.0 documentation gate
updated: 2026-09-27
done_phases: 1 2
hr_core: api auth backup canonical device importer journal modules registry service signing
root_python: BUILD_PROJECT CHECK_ENVIRONMENT CUSTOM_RULES SMOKE_TEST calculation_engine eco_contract eco_publisher engine hr_registry hr_server
root_python: TEST_DOCS_CURRENT TEST_ECO_PUBLISHER TEST_HR_FOUNDATION TEST_HR_REGISTRY TEST_HR_SECURITY TEST_INT01_MULTI_SOURCE TEST_INT02_ROSTER_LEAVE_LINK TEST_INT03_HTTP_MULTI_UPLOAD TEST_MIGRATION_EQUIVALENCE
contracts: canonical-v1 eco.attendance_day.v1 eco.employee.v1 eco.envelope.v1
entities: org_unit job position employee
permissions: hr.org.read hr.org.write hr.employees.read hr.employees.write hr.employees.delete hr.recycle.restore hr.import.run
permissions: admin.users.manage admin.audit.read admin.backup.manage admin.backup.restore admin.system.read
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
mutations: 41
```
