# STATUS — where HR-System stands

Review repairs (2026-10-02): F01 freezes approved leave material fields, including when cancelling; cancel and submit a new request for revised dates. F13 charges cross-year working days to each year and includes the proposed prior-year charge when checking carryover. F14 stores overtime policy in backed-up `data/settings.db`, importing legacy JSON once; data version 6 provides the resumable upgrade. Validation: people operations 72, payroll 66, security 78, delivery 96, workforce 53 and inbox 25 checks passed; docs/environment checks passed, locked-engine equivalence had zero differences, and all four focused leave/settings/payroll backup planted faults were caught. The full 119-mutation run and fresh compiled installer acceptance were not rerun. Backups contain settings/payroll attachments for fresh-folder recovery; the compensating registry restore command still restores registry rows only. No real salary data or statutory validation was performed.

| `clock` (simulation, 2026-09-30) - one helper gives every "today" in `hr_core`; with `HR_SIMULATION=1` an administrator can move it (`GET/PUT /api/sim/today`, audited); without the switch the route does not exist, so an installed program can never be back-dated | `hr_core/clock.py`, `hr_core/registry.py`, `hr_core/api.py` | `TEST_HR_SIMULATION.py` (9), two planted bugs in `migration/mutations.py` |
| `eco_signing` (WP-X2, 2026-09-30) - a machine call may be signed (HMAC-SHA256 over method, path, body and time, five-minute window, keyed with the SHA-256 of the machine key); HR's publisher signs, the inbox checks, `ECO_REQUIRE_SIGNATURE=1` makes it mandatory; the same algorithm and test vector as Mizan and GMES | `eco_signing.py`, `hr_core/eco_inbox.py`, `hr_core/api.py`, `eco_publisher.py` | `TEST_HR_ECO_INBOX.py`, `TEST_ECO_PUBLISHER.py`, three planted bugs |
python TEST_HR_SIMULATION.py         the simulated date: movable only with HR_SIMULATION=1, every rule follows it

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
checklist: `docs/ux/`. **Exit gate:** the owner approves the visual shell (compared with his redacted reference screenshots).
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
| Users, profiles, server-side permissions (12 in phase 2, 27 now) checked on every request, sessions, lockout, device identity with clone detection, signed append-only journal and audit, verified backups, automatic restore rehearsal, compensating restore, recovery of a lost `hr.db` / `auth.db` / journal | `hr_core/auth.py`, `hr_core/service.py`, `hr_core/api.py`, `hr_core/device.py`, `hr_core/journal.py`, `hr_core/signing.py`, `hr_core/backup.py`, `hr_server.py` | `TEST_HR_SECURITY.py` (79), `docs/HR_SECURITY.md` |
| Ecosystem publisher: `eco.employee.v1` (from the registry) and `eco.attendance_day.v1`, outbox, retry with the same stored bytes, no duplicates; disabled without `ECO_GMES_URL` | `eco_publisher.py`, `eco_contract.py`, `eco_schemas/` | `TEST_ECO_PUBLISHER.py` (9), GMES `hr-e2e` against this repository |
| The link to GMES inside the installed product (ecosystem plan, Phase A, 2026-09-28): set on Settings → Integration (GMES) (address, node, interval, write-only key); off while the address is empty (HR works on its own); a background thread started on open, stopped on close, restarted on a change; "Send now"; last delivery and pending / delivered / refused on the screen; the registry read through its own read-only connection; the GMES key in `data/node/gmes.key` (Windows DPAPI, machine scope; owner-only file elsewhere), never in config.json, the API, a backup, a log line or the audit (`docs/HR_DELIVERY.md` ADR-HR-008) | `hr_core/eco_link.py`, `hr_core/app.py`, `hr_core/home.py`, `hr_core/api.py`, `hr_core/web/app.js` | `TEST_HR_DELIVERY.py` (fake GMES inbox on 127.0.0.1), `TEST_HR_WORKFORCE.py` (read-only view); the installed program: not yet run in the CI job `windows-installer` with a GMES address |
| Module and edition map (`kernel`, `attendance`, `leave` built) | `hr_core/modules.py` | `TEST_HR_REGISTRY.py` |
| Documentation guard | `TEST_DOCS_CURRENT.py` | itself, and its planted bugs in `migration/mutations.py` |
| One product (phase 2.5): one server, one port, one sign-in; screens for employees and organisation, attendance, users and permissions, backups, system health, settings; English and Arabic dictionaries with the same keys | `hr_main.py`, `hr_core/app.py`, `hr_core/web.py`, `hr_core/web/`, `hr_core/api.py` | `TEST_HR_DELIVERY.py` |
| `shifts` (phase 3, 2026-09-28, owner's order) — shifts (overnight = one work date), working calendars (rest days, holidays), effective-dated assignments (regular never overlap; temporary covers regular; a started one only ends, not before yesterday; past days never re-planned), day changes and swaps in one save, the planned schedule, planned vs attended comparison, published as `eco.schedule_day.v1` (14 days ahead); screens Roster, Assignments, Shifts, Calendars, Planned vs attended; data version 2 | `hr_core/scheduling.py`, `hr_core/registry.py`, `hr_core/service.py`, `hr_core/api.py`, `eco_publisher.py`, `hr_core/web/app.js` | `TEST_HR_WORKFORCE.py` (53), GMES `hr-e2e` (the plan mirrored, with its age) |
| `skills` (phase 5, 2026-09-28) — skills catalogue with validity, qualifications per person (level 1-4, certified, expiry from the skill's validity), published as `eco.qualification.v1` (a withdrawn one as inactive); GMES refuses a person at a station whose required skill they do not hold validly at the level; screens Skills matrix, Qualifications, Skills catalogue | `hr_core/skills.py`, `hr_core/registry.py`, `eco_publisher.py`, `hr_core/web/app.js` | `TEST_HR_WORKFORCE.py`, GMES `hr-boundary` and `hr-e2e` |
| The product shell (phase 2.6, UX): one application shell built from the ecosystem's interface kit (menu tree, screen search with actions, tabs, standard screen with subtitle and help, grid with column filters, grouping and presets, dialogs); the kit is the unchanged, hash-pinned copy from GMES (fonts included); Mizan's modern look by default; server values written as text only | `hr_core/web/app.js`, `hr_core/web/hr.css`, `hr_core/web/eco-ui/`, `hr_core/eco_ui_pin.json` | `TEST_HR_DELIVERY.py` (96), screenshots `docs/ux/` (taken before the modern look) |
| `discipline` (phase 6, 2026-09-28, owner's order) — the company's penalty schedule (violation, threshold, repeat window, the penalty for each repeat), violations proposed from the planned days against attendance (late, early leave, absence; never a leave day, a rest day or a holiday; nothing proposed twice), decisions by a separate right (`hr.discipline.approve`; who and when from the server), the law's limits (5 days per violation and per month, 30 days to decide, a written investigation over one day), decisions final, penalties in days never money; data version 3; screens Violations and penalties (`DSC2010`), Penalty schedule (`DSC1010`), the Discipline tab of an employee, Advisor warnings before the 30-day limit | `hr_core/discipline.py`, `hr_core/registry.py`, `hr_core/service.py`, `hr_core/api.py`, `hr_core/upgrade.py`, `hr_core/web/app.js` | `TEST_HR_DISCIPLINE.py` (26) |
| `recruitment` support: what manufacturing tells HR (WP-H1, 2026-09-30) — machine keys (`hk_...`, shown once, only the hash kept, scope `eco.inbox.write`, revocable), `POST /eco/v1/inbox` for `mes.crew_requirement.v1` and `mes.labor_day.v1` (contract-checked, own company only, each event once, an older version never replaces a newer one, refusals kept), the staffing gap per day and shift (heads and required skills, expired qualifications do not count, `STF2010`), labour facts beside the plan (`GET /api/labour/evidence`: worked in production vs planned paid); the labour minutes never leave as pay and no personal data enters | `hr_core/eco_inbox.py`, `hr_core/api.py`, `hr_core/web/app.js` | `TEST_HR_ECO_INBOX.py` (17) |
| `payroll` (WP-H6, 2026-10-02, owner's order: sample data, trial on this laptop; see `docs/HR_PAYROLL_DESIGN.md`) — salary profiles (effective-dated, integer piastres, in their own `data/payroll.db`, copied into every backup), the month's adjustments (unpaid absence days, bonus, deduction), and a pay run per month: everyone with a profile is calculated from the plan, approved overtime (basic / 240 with the company's premiums), night allowance, unpaid leave, absence, social insurance (11 % / 18.75 % on the insurable wage kept between 2,700 and 16,700), salary tax (Law 7/2024 brackets, personal exemption 20,000, rounded down to 10 pounds) and the martyrs' fund; the same data gives the same fingerprint; a run is calculated, approved by someone else who names the fingerprint they saw, then sent signed to Mizan as `hr.payroll_period.v1` (totals per cost centre and account key, no names; each cost centre balances); an approved run never changes (reverse it, calculate a new run); an administrator sets Mizan's address and key (PUT /api/payroll/target, the key kept like the GMES key, never in a backup or the audit); a refusal from Mizan stays visible; four rights (`hr.payroll.read|write|run|approve`, data version 5); screens `PAY2010`, `PAY1010`, `PAY1020` in English and Arabic | `hr_core/payroll_calc.py`, `hr_core/payroll.py`, `TEST_HR_PAYROLL.py` (66 checks, hand-computed), 13 planted bugs |
| `recruitment`, `overtime`, `training`, `leave` (WP-H2 to WP-H5, 2026-09-30) — eleven registers in the signed registry: headcount plan (proposed from GMES crew needs plus a relief allowance, never overwriting a person's own plan), agency, hiring request (starts as a draft, approved by someone else, frozen after approval, the plan limits it unless a reason is written), candidate (stages only move forward, hired only through Hire), onboarding task, contract (fixed-term ends its employee on the last day); **Hire** creates the employee, the contract and the onboarding checklist and fills the request in one journal line; a new hire is not schedulable on a line before the medical check, protective equipment and ESD training; courses and sessions where a pass grants or renews the qualification (never lowering a higher one) and completes the matching onboarding task; overtime requests approved by someone else with the daily/weekly/monthly caps of a settable policy (the defaults name their source and say verify) and the monthly figures payroll will need (minutes by kind, premiums in basis points, substitute days, exceptions); leave types, requests (days counted on the person's calendar, no overlaps), approval by someone else, balances with carry-over, approved leave takes the person out of the plan; eleven new rights (`hr.recruitment\|overtime\|training\|leave.*`), data version 4; screens `REC1010`-`REC1060`, `OVT1010`, `OVT1020`, `TRN1010`, `TRN2010`, `LEV1010`, `LEV2010`, `LEV3010`, English and Arabic | `hr_core/people_ops.py`, `hr_core/people_service.py`, `hr_core/registry.py`, `hr_core/service.py`, `hr_core/api.py`, `hr_core/auth.py`, `hr_core/upgrade.py`, `hr_core/web/app.js` | `TEST_HR_PEOPLE_OPS.py` (60), `TEST_HR_DELIVERY.py` (texts); seen in Chrome on a synthetic company (approve, candidate to hire, overtime approval) |
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
| Leave | Leave types, requests, approval by someone else, balances and the plan are built (see Built and tested); the attendance engine still reads its own uploaded leave file | The two are not one yet: attendance does not read the registry's approved leave (phase 4) |
| Phase 3 gate | Everything in the `shifts` row above | Excel import of shifts and rosters (re-import writes nothing the second time); planned overtime and leave on the plan are built; the phase is not marked done until the import exists |
| Phase 5 gate | Qualifications and GMES's station check, end to end; `training` | A GMES screen to configure station requirements (today an API: `PUT /api/stations/<code>/requirements`) |
| Attendance ↔ official employee | Attendance is enriched from the **uploaded** employee file | Binding to the registry employee (phase 4) |
| LAN use | `hr_server.py serve --host` | No TLS yet (BAMS's pinned-certificate pattern is the plan, `docs/HR_SECURITY.md` §4) |
| Windows | CI runs every Python test on Windows and accepts the installed program | The protected-workbook Excel path never ran on a PC with Excel |
| Signing library | `cryptography` bundled in the installed program; BAMS's vendored file remains the fallback for source checkouts (ADR-HR-002) | — |

## Planned

| What | Phase |
|---|---|
| Attendance and leave bound to the official employee and shift masters | 4 |
| Personal data (identity, contacts, dependants) behind encryption and permissions | after 5 |
| Company identity adoption: a provisional local id matched to Mizan's, explicitly | when a customer needs it |

## Design only

| What | Why not built |
|---|---|
| _(nothing: payroll was built on 2026-10-02, see Built and tested)_ | |

## Next phase — 3: shifts, calendars, schedules and assignments

**Built on 2026-09-28** (see `shifts` under Built and tested); still owed for the gate: Excel import of shifts and
rosters (Partially built; planned overtime and leave on the plan are built). The original plan, kept for the gate:
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
python TEST_HR_ECO_INBOX.py         what manufacturing tells HR: keys, crew requirements, labour facts, staffing gap
python TEST_HR_PEOPLE_OPS.py         recruitment, onboarding, overtime, training that qualifies, leave
python TEST_HR_PAYROLL.py            payroll: hand-computed pay, four-eyes approval, what Mizan receives
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
updated: 2026-10-02
done_phases: 1 2
hr_core: api app attendance auth backup canonical clock device discipline eco_inbox eco_link home importer journal modules payroll payroll_calc people_ops people_service registry scheduling service signing skills upgrade version web
root_python: BUILD_PROJECT CHECK_ENVIRONMENT CUSTOM_RULES SMOKE_TEST calculation_engine eco_contract eco_publisher eco_signing engine hr_main hr_registry hr_server
root_python: TEST_DOCS_CURRENT TEST_ECO_PUBLISHER TEST_HR_DELIVERY TEST_HR_DISCIPLINE TEST_HR_ECO_INBOX TEST_HR_FOUNDATION TEST_HR_PAYROLL TEST_HR_PEOPLE_OPS TEST_HR_REGISTRY TEST_HR_SECURITY TEST_HR_SIMULATION TEST_HR_WORKFORCE TEST_INT01_MULTI_SOURCE TEST_INT02_ROSTER_LEAVE_LINK TEST_INT03_HTTP_MULTI_UPLOAD TEST_MIGRATION_EQUIVALENCE
contracts: canonical-v1 eco.attendance_day.v1 eco.employee.v1 eco.envelope.v1 eco.qualification.v1 eco.schedule_day.v1 hr.payroll_period.v1 mes.crew_requirement.v1 mes.labor_day.v1
entities: org_unit job position employee shift work_calendar shift_assignment roster_override skill employee_skill penalty_rule violation headcount_plan agency hire_requisition candidate onboarding_task contract overtime_request course training_session leave_type leave_request
permissions: hr.org.read hr.org.write hr.employees.read hr.employees.write hr.employees.delete hr.recycle.restore
permissions: hr.import.run admin.users.manage admin.audit.read admin.backup.manage admin.backup.restore admin.system.read
permissions: hr.attendance.read hr.attendance.upload admin.settings.manage hr.shifts.read hr.shifts.write hr.skills.read
permissions: hr.skills.write hr.discipline.read hr.discipline.write hr.discipline.approve hr.recruitment.read hr.recruitment.write
permissions: hr.recruitment.approve hr.overtime.read hr.overtime.write hr.overtime.approve hr.training.read hr.training.write
permissions: hr.leave.read hr.leave.write hr.leave.approve hr.payroll.read hr.payroll.write hr.payroll.run hr.payroll.approve
module: kernel built
module: attendance built
module: leave built
module: recruitment built
module: shifts built
module: overtime built
module: skills built
module: training built
module: discipline built
module: payroll built
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
route: GET /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation|headcount_plan|agency|hire_requisition|candidate|onboarding_task|contract|overtime_request|course|training_session|leave_type|leave_request)
route: PUT /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation|headcount_plan|agency|hire_requisition|candidate|onboarding_task|contract|overtime_request|course|training_session|leave_type|leave_request)/([^/]+)
route: DELETE /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation|headcount_plan|agency|hire_requisition|candidate|onboarding_task|contract|overtime_request|course|training_session|leave_type|leave_request)/([^/]+)
route: POST /api/(org_unit|job|position|employee|shift|work_calendar|shift_assignment|roster_override|skill|employee_skill|penalty_rule|violation|headcount_plan|agency|hire_requisition|candidate|onboarding_task|contract|overtime_request|course|training_session|leave_type|leave_request)/([^/]+)/restore
route: GET /api/schedule
route: GET /api/schedule/compare
route: POST /api/discipline/propose
route: POST /api/schedule/swap
route: POST /eco/v1/inbox
route: GET /api/admin/eco-keys
route: POST /api/admin/eco-keys
route: POST /api/admin/eco-keys/(\d+)/revoke
route: GET /api/labour/evidence
route: POST /api/recruitment/candidates/([^/]+)/hire
route: GET /api/recruitment/onboarding
route: POST /api/recruitment/propose-headcount
route: POST /api/recruitment/expire-contracts
route: POST /api/training/sessions/([^/]+)/complete
route: GET /api/leave/balance
route: GET /api/overtime/figures
route: GET /api/overtime/policy
route: PUT /api/overtime/policy
route: GET /api/payroll/target
route: PUT /api/payroll/target
route: GET /api/payroll/profiles
route: PUT /api/payroll/profiles/([^/]+)
route: GET /api/payroll/adjustments
route: POST /api/payroll/adjustments
route: DELETE /api/payroll/adjustments/(\d+)
route: GET /api/payroll/runs
route: POST /api/payroll/calculate
route: GET /api/payroll/runs/(\d{4}-\d{2})/(\d+)
route: GET /api/payroll/runs/(\d{4}-\d{2})/(\d+)/slips
route: POST /api/payroll/runs/(\d{4}-\d{2})/(\d+)/approve
route: POST /api/payroll/runs/(\d{4}-\d{2})/(\d+)/reverse
route: POST /api/payroll/runs/(\d{4}-\d{2})/(\d+)/retry
route: POST /api/payroll/deliver
route: GET /api/staffing/gap
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
route: GET /api/sim/today
route: PUT /api/sim/today
route: GET /api/info
route: GET /api/admin/settings
route: PUT /api/admin/settings
route: GET /api/admin/integration
route: PUT /api/admin/integration
route: POST /api/admin/integration/run
mutations: 119
```

Integration recovery (2026-10-02): inbox status retains historical `rejected` source/id records and adds `unresolved_rejections`, excluding source/id pairs already accepted into the inbox. Successful retry no longer erases rejection evidence. GET /api/payroll/target already reports the effective URL and whether its key is set (never the key); an empty target remains supported for standalone HR.

Chrome startup (2026-10-02, built and tested): `hr_main.py` calls only the mandatory interactive-desktop Chrome helper, or prints the URL when unavailable. Source/frozen interpreter selection and missing-helper handling are checked with mocks; no GUI execution in those checks. `Start-HR-Demo.bat -NoBrowser` or `--background` forwards `--no-browser`, independently of the autostart preference.
