# STATUS — where HR-System stands

Read this first after an interruption, then `AGENT_HANDOFF.md`. `TEST_DOCS_CURRENT.py` fails when this file falls
behind the code, so what it says is checked, not remembered.

Labels used everywhere in this repository:
**Built and tested** = in the code and proven by a test in CI · **Partially built** = some of it exists, the limit is
written next to it · **Planned** = designed, no code · **Design only** = architecture on paper, must not be built yet.

## Current stage

**Phase 2.5 — HR-System as one installable product** (`docs/HR_DELIVERY.md`), and beside it **phase 2.6 — the
product shell (UX)**: the owner stopped business features (shifts, skills, payroll, new MES modules) until the screens
look and feel like a commercial HR product and he approves them. Phase 3 (shifts) waits for both gates. Stage 3.0 (the
continuity documents and their guard) is done and merged.

**Phase 2.6 (UX) — where it stands:** the screens were rebuilt as one application shell on the ecosystem's interface
kit (`hr_core/web/eco-ui/`, copied unchanged from GMES `packages/eco-ui/src` and pinned in `hr_core/eco_ui_pin.json`):
sign-in and first-run pages, dashboard, employees (search/filter conditions, dense grid, detail panel, bulk actions,
editor dialog), organisation structure tree, jobs, positions, attendance, users, profiles and rights, audit, backups,
system health, settings; English/Arabic, light/dark, compact/comfortable. Screenshots and the visual acceptance
checklist: `docs/ux/`. **Exit gate:** the owner approves the visual shell (compared with his redacted G-MES screenshots).
On the owner's order (2026-09-28) the shell took Mizan's look and ideas through the kit (GMES `4d27f55`, ADR-033): the
modern look by default, column filters / grouping / presets, the Advisor, the Mizan-style dashboard, the rights matrix.
Seen in a real browser on 2026-09-28 (Chrome over CDP, the demo installation): every main screen opens without a script error; a syntax error, a white box in primary buttons, too narrow columns and an empty half of the dashboard in Arabic were found there and fixed.

**Ecosystem plan, Phase A (2026-09-28, approved by the owner):** the installed product publishes HR's workforce truth to
GMES by itself, configured on Settings → Integration (GMES), instead of only through `python eco_publisher.py` with
environment variables (`hr_core/eco_link.py`, `docs/HR_DELIVERY.md` ADR-HR-008). Off until an address is set.

**Exit gate of phase 2.5:** installed from scratch on a clean Windows without Python and without internet; first
administrator and sign-in; employee register; permissions; attendance with the same numbers; backup, rehearsal and
restore; a restart loses nothing; an update over an installed version keeps data, accounts and journal; a failure
and a power cut in the middle of an update are survived; every HR test and planted bug; GMES's real HR end-to-end
test against the new commit.

**Where it stands:** everything above is built and passes on Linux and Windows (`TEST_HR_DELIVERY.py`, 96 checks) and,
for the installed program, in the CI job `windows-installer` (`tools/installed_acceptance.py`, 31 of 31: Python hidden
from the program, outbound network blocked). Still owed before the gate closes: the owner's clean-PC run in Windows Sandbox
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
| The link to GMES inside the installed product (ecosystem plan, Phase A, 2026-09-28): set on Settings → Integration (GMES) (address, node, interval, write-only key); off while the address is empty (HR works on its own); a background thread started on open, stopped on close, restarted on a change; "Send now"; last delivery and pending / delivered / refused on the screen; the registry read through its own read-only connection; the GMES key in `data/node/gmes.key` (Windows DPAPI, machine scope; owner-only file elsewhere), never in config.json, the API, a backup, a log line or the audit (`docs/HR_DELIVERY.md` ADR-HR-008) | `hr_core/eco_link.py`, `hr_core/app.py`, `hr_core/home.py`, `hr_core/api.py`, `hr_core/web/app.js` | `TEST_HR_DELIVERY.py` (fake GMES inbox on 127.0.0.1), `TEST_HR_WORKFORCE.py` (read-only view); the installed program: not yet run in the CI job `windows-installer` with a GMES address |
| Module and edition map (`kernel`, `attendance`, `leave` built) | `hr_core/modules.py` | `TEST_HR_REGISTRY.py` |
| Documentation guard | `TEST_DOCS_CURRENT.py` | itself, and its planted bugs in `migration/mutations.py` |
| One product (phase 2.5): one server, one port, one sign-in; screens for employees and organisation, attendance, users and permissions, backups, system health, settings; English and Arabic dictionaries with the same keys | `hr_main.py`, `hr_core/app.py`, `hr_core/web.py`, `hr_core/web/`, `hr_core/api.py` | `TEST_HR_DELIVERY.py` |
| `shifts` (phase 3, 2026-09-28, owner's order) — shifts (overnight = one work date), working calendars (rest days, holidays), effective-dated assignments (regular never overlap; temporary covers regular; a started one only ends, not before yesterday; past days never re-planned), day changes and swaps in one save, the planned schedule, planned vs attended comparison, published as `eco.schedule_day.v1` (14 days ahead); screens Roster, Assignments, Shifts, Calendars, Planned vs attended; data version 2 | `hr_core/scheduling.py`, `hr_core/registry.py`, `hr_core/service.py`, `hr_core/api.py`, `eco_publisher.py`, `hr_core/web/app.js` | `TEST_HR_WORKFORCE.py` (53), GMES `hr-e2e` (the plan mirrored, with its age) |
| `skills` (phase 5, 2026-09-28) — skills catalogue with validity, qualifications per person (level 1-4, certified, expiry from the skill's validity), published as `eco.qualification.v1` (a withdrawn one as inactive); GMES refuses a person at a station whose required skill they do not hold validly at the level; screens Skills matrix, Qualifications, Skills catalogue | `hr_core/skills.py`, `hr_core/registry.py`, `eco_publisher.py`, `hr_core/web/app.js` | `TEST_HR_WORKFORCE.py`, GMES `hr-boundary` and `hr-e2e` |
| The product shell (phase 2.6, UX): one application shell built from the ecosystem's interface kit (menu tree, screen search with actions, tabs, standard screen with subtitle and help, grid with column filters, grouping and presets, dialogs); the kit is the unchanged, hash-pinned copy from GMES (fonts included); Mizan's modern look by default; server values written as text only | `hr_core/web/app.js`, `hr_core/web/hr.css`, `hr_core/web/eco-ui/`, `hr_core/eco_ui_pin.json` | `TEST_HR_DELIVERY.py` (96), screenshots `docs/ux/` (taken before the modern look) |
| `discipline` (phase 6, 2026-09-28, owner's order) — the company's penalty schedule (violation, threshold, repeat window, the penalty for each repeat), violations proposed from the planned days against attendance (late, early leave, absence; never a leave day, a rest day or a holiday; nothing proposed twice), decisions by a separate right (`hr.discipline.approve`; who and when from the server), the law's limits (5 days per violation and per month, 30 days to decide, a written investigation over one day), decisions final, penalties in days never money; data version 3; screens Violations and penalties (`DSC2010`), Penalty schedule (`DSC1010`), the Discipline tab of an employee, Advisor warnings before the 30-day limit | `hr_core/discipline.py`, `hr_core/registry.py`, `hr_core/service.py`, `hr_core/api.py`, `hr_core/upgrade.py`, `hr_core/web/app.js` | `TEST_HR_DISCIPLINE.py` (26) |
| Employee journey (`EMP2010`): one person's facts from every module on one timeline (joining, team, account, shifts, day changes, qualifications, attended days, lateness, absences, leave, violations, decisions, two weeks ahead), a week-by-week time-lapse with running figures, and the person's activity from the audit | `hr_core/web/app.js` | seen in Chrome on the demo; `TEST_HR_DELIVERY.py` (its texts) |
| Guide system (Mizan's design): guide mode off/basic/full, F1 help panel (the screen's help, "how do I" search, keys), 8 guided tours across screens, help center (`HLP1010`), the Advisor's warnings on the record itself, tips inside the forms | `hr_core/web/app.js`, kit `drawer()` and `tour()` | seen in Chrome; `TEST_HR_DELIVERY.py` (every text in both languages) |
| Demo installation: `Start-HR-Demo.bat` builds and starts a separate installation (never a real one) with the synthetic factory dataset through the importer, shifts, assignments, qualifications, users, three weeks of attendance through the engine, the penalty schedule and decisions, deliberate problems for every Advisor check, and the story of a new production manager (hired 2026-06-15) | `tools/make_demo.py`, `tools/start_demo.ps1`, `Start-HR-Demo.bat` | built twice, screens checked in Chrome |
| Advisor (`ADV1010`): 23 daily checks (people, organisation, planning, skills, security, system) with the reason, what to do and the records concerned; computed in the browser from what the person may read; rights matrix with templates and separated duties (Mizan's ideas) | `hr_core/web/app.js` | `TEST_HR_DELIVERY.py` (every finding has its words in both languages; templates and duty pairs name real rights) |
| The locked attendance engine behind the same sign-in (`hr.attendance.read` / `hr.attendance.upload`), same golden numbers, uploads audited | `hr_core/attendance.py` | `TEST_HR_DELIVERY.py` |
| Installation home outside the program, company identity from its owner (Mizan) or local and provisional, never changed silently | `hr_core/home.py`, `hr_core/registry.py` | `TEST_HR_DELIVERY.py` |
| Data versions: verified pre-update backup kept forever, step-by-step update, put back on failure, resume after a power cut, newer data refused; one known-good recovery installer with its SHA-256 | `hr_core/upgrade.py`, `hr_core/version.py` | `TEST_HR_DELIVERY.py` |
| Backups carry the attendance history (copied while no upload runs); a lost history comes back from a backup | `hr_core/backup.py` | `TEST_HR_DELIVERY.py` |
| Windows installer: compiled program with its own runtime and `cryptography`, data in `%ProgramData%\HR-System`, start with Windows by default, old attendance data copied on first install, Excel detected | `tools/build_windows.py`, `installer/hr-system.iss` | CI `windows-installer` (`tools/installed_acceptance.py`) |

## Partially built

| What | What exists | What is missing |
|---|---|---|
| Delivery to a customer | The Windows installer (phase 2.5) installs the whole product; `BUILD_PROJECT.py` still builds the old attendance ZIP as the engine's rollback line | A run on a truly clean PC (Windows Sandbox, `docs/HR_DELIVERY.md` §5); a code-signing certificate before selling (Windows shows "unknown publisher") |
| Screens | Every phase-1/2 capability has a screen in the new shell, in English and Arabic | The owner's approval of the look (phase 2.6 gate); the attendance dashboard is the locked engine's own page (English only, its own look); importing workbooks is still a command (`hr_registry.py import`) |
| Company identity | From Mizan at setup, or local and provisional | The adoption step (a local id later matched to Mizan's) is planned, not built |
| Eco link in the installed program | Built and tested in the product logic (`hr_core/eco_link.py`, see Built and tested) | Not yet exercised by `tools/installed_acceptance.py` (the compiled program with a GMES address and DPAPI); GMES's end-to-end test still drives `eco_publisher.py` with environment variables, not the product's screen path |
| Leave | Linked to attendance days at import | Leave requests, approval and balances as an HR module |
| Phase 3 gate | Everything in the `shifts` row above | Excel import of shifts and rosters (re-import writes nothing the second time), planned overtime, leave shown on the plan; the phase is not marked done until these exist |
| Phase 5 gate | Qualifications and GMES's station check, end to end | `training`; a GMES screen to configure station requirements (today an API: `PUT /api/stations/<code>/requirements`) |
| Attendance ↔ official employee | Attendance is enriched from the **uploaded** employee file | Binding to the registry employee (phase 4) |
| LAN use | `hr_server.py serve --host` | No TLS yet (BAMS's pinned-certificate pattern is the plan, `docs/HR_SECURITY.md` §4) |
| Windows | CI runs every Python test on Windows and accepts the installed program | The protected-workbook Excel path never ran on a PC with Excel |
| Signing library | `cryptography` bundled in the installed program; BAMS's vendored file remains the fallback for source checkouts (ADR-HR-002) | — |

## Planned

| What | Phase |
|---|---|
| `overtime` — requests, approval and actuals, bound to shifts and attendance | 4 |
| Attendance and leave bound to the official employee and shift masters | 4 |
| `training` — courses and completions that grant skills | 5 |
| Personal data (identity, contacts, dependants) behind encryption and permissions | after 5 |
| Company identity adoption: a provisional local id matched to Mizan's, explicitly | when a customer needs it |

## Design only

| What | Why not built |
|---|---|
| `payroll` — HR calculates pay; Mizan books one summarized entry per period (`hr.payroll_period.v1`); detailed design: `docs/HR_PAYROLL_DESIGN.md` (data, calculation order, contract, four-eyes rights, tests) | Needs stable employees, attendance, leave and overtime first (`docs/HR_SYSTEM_DESIGN.md` §6; owner's decision 2026-09-28: design now, build after the gate). Mizan never stores employees or computes pay. |

## Next phase — 3: shifts, calendars, schedules and assignments

**Built on 2026-09-28** (see `shifts` under Built and tested); still owed for the gate: Excel import of shifts and
rosters, planned overtime and leave on the plan (Partially built). The original plan, kept for the gate:
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
python TEST_HR_WORKFORCE.py
python TEST_HR_DISCIPLINE.py
python TEST_DOCS_CURRENT.py
python migration/mutations.py           every planted bug caught
python BUILD_PROJECT.py
```
On Windows (CI job `windows-installer`): `python tools/build_windows.py`, then `python tools/installed_acceptance.py`.
Then, in a GMES checkout: `sh scripts/fetch-hr.sh`, `ECO_E2E_REQUIRED=1 npm test`, `node scripts/mutations.mjs`.

**Last full run (2026-09-27, phase 2.5, commit b3d106d):** every test above passes on Linux and Windows; 59 of 59
planted bugs caught; the CI job `windows-installer` built `HR-System-Setup-1.0.0.exe` and accepted the installed program
with Python hidden and the network blocked — 31 of 31 checks (install, rights, setup, register, permissions, attendance,
bundled `cryptography`, Excel detection, recovery installer, backup/rehearsal/restore, restart, update, failed update,
power cut, removal keeps the data); GMES against this commit: 15 + 29 + 10 tests pass, every GMES planted bug caught.

## Architecture inventory (checked by `TEST_DOCS_CURRENT.py`)

Change this block only after the documents above describe the change. `phase` is the next phase the design leaves
open; `stage` is the step inside it; `updated` is the date of the session that last changed this file.

```inventory
phase: 2.5
stage: 2.5 one installable product + 2.6 product shell
updated: 2026-09-28
done_phases: 1 2
hr_core: api app attendance auth backup canonical device discipline eco_link home importer journal modules registry scheduling service signing skills upgrade version web
root_python: BUILD_PROJECT CHECK_ENVIRONMENT CUSTOM_RULES SMOKE_TEST calculation_engine eco_contract eco_publisher engine hr_main hr_registry hr_server
root_python: TEST_DOCS_CURRENT TEST_ECO_PUBLISHER TEST_HR_DELIVERY TEST_HR_DISCIPLINE TEST_HR_FOUNDATION TEST_HR_REGISTRY TEST_HR_SECURITY TEST_HR_WORKFORCE TEST_INT01_MULTI_SOURCE TEST_INT02_ROSTER_LEAVE_LINK TEST_INT03_HTTP_MULTI_UPLOAD TEST_MIGRATION_EQUIVALENCE
contracts: canonical-v1 eco.attendance_day.v1 eco.employee.v1 eco.envelope.v1 eco.qualification.v1 eco.schedule_day.v1
entities: org_unit job position employee shift work_calendar shift_assignment roster_override skill employee_skill penalty_rule violation
permissions: hr.org.read hr.org.write hr.employees.read hr.employees.write hr.employees.delete hr.recycle.restore hr.import.run
permissions: admin.users.manage admin.audit.read admin.backup.manage admin.backup.restore admin.system.read
permissions: hr.attendance.read hr.attendance.upload admin.settings.manage
permissions: hr.shifts.read hr.shifts.write hr.skills.read hr.skills.write
permissions: hr.discipline.read hr.discipline.write hr.discipline.approve
module: kernel built
module: attendance built
module: leave built
module: shifts built
module: overtime planned
module: skills built
module: training planned
module: discipline built
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
route: GET /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation)
route: PUT /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation)/([^/]+)
route: DELETE /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation)/([^/]+)
route: POST /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation)/([^/]+)/restore
route: GET /api/schedule
route: GET /api/schedule/compare
route: POST /api/discipline/propose
route: POST /api/schedule/swap
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
route: GET /api/admin/integration
route: PUT /api/admin/integration
route: POST /api/admin/integration/run
mutations: 79
```
