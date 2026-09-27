# HR-System — rules for anyone (human or AI) changing this repository

HR-System is the ecosystem's **only source of truth for people**. Built today: the employee registry and the
organisation (company → site → business unit → department → section, jobs, positions — `hr_core/`), and the
migrated attendance application with roster and leave linking (locked engine), and (phase 2) users, profiles and
server-side permissions, device identity, a signed append-only journal and audit, verified automatic backups with a
restore rehearsal (`docs/HR_SECURITY.md`). **Planned, not built:** independent
shifts/rosters/assignments, overtime, skills/training/station qualification. **Design only:** payroll calculation
(Mizan books the entries; it never stores employees or computes pay). Other applications (GMES, Mizan, Space Planner)
keep read-only mirrors and reference employees by the shared id `UUIDv5(company, "hr:employee:<Employee_ID>")`.
BAMS (`Mr.Ayman-HR`) is a different product; it is the ecosystem's infrastructure REFERENCE, never modified from here.
Design and plan: `docs/HR_SYSTEM_DESIGN.md`.

Read first: `START_HERE_AI.md` (the original working rules, still valid), `MIGRATION.md`, then
`project_memory/PROJECT_LOG.md`.

## Never
- Change behaviour during migration or "clean-up". Behaviour changes need a decision in PROJECT_LOG.md and a test
  that first reproduces the old behaviour. `TEST_MIGRATION_EQUIVALENCE.py` must stay at 0 differences unless the
  golden file is deliberately regenerated in the same commit, with the reason.
- Commit `data/`, uploads, databases or any real employee information. Synthetic data only.
- Add a non-standard-library import to a top-level `.py` file (CHECK_ENVIRONMENT.py reports it as a runtime dependency).
- Publish personal data (birth date, national id, gender, pay, contacts) to another application.
- Write into another application's database, or accept employee records from another application.
- Let payroll have two truths: HR calculates pay; Mizan books the entries; neither does the other's job.
- Build payroll before employees, attendance, leave and overtime are stable (docs/HR_SYSTEM_DESIGN.md §6-7).
- Touch `engine.py` / `calculation_engine.py` / `dashboard.html` / `PROJECT.json` for new modules: new work goes in `hr_core/` beside them.
- Edit `eco_schemas/`: they are generated in `coolman1984/GMES/packages/eco-contracts` and copied here unchanged.
- Edit `hr_core/vendor/` (BAMS's signing code, byte-for-byte, hash-pinned) or keep a second, modified copy of any
  security algorithm. Fixes go to BAMS first, then are copied here unchanged (ADR-HR-002).
- Reach the registry or the accounts from a new entrance without `hr_core/service.py` (`require()` + audit), or
  accept a change to an existing record without the version the person edited.
- Rewrite, UPDATE or DELETE a journal or audit line; copy a backup over live data (restore = a new compensating line);
  put `data/node/device.key`, a password, a session token or a key in a backup, a log line or the audit.
- Build shifts, skills or payroll before `TEST_HR_SECURITY.py` (phase 2 exit gate) passes.

## Tests (all must pass; CI runs them on Linux and Windows)
```
python CHECK_ENVIRONMENT.py
python SMOKE_TEST.py
set PYTHONPATH=vendor.zip   (Linux: export PYTHONPATH=vendor.zip)
python TEST_HR_FOUNDATION.py
python TEST_INT01_MULTI_SOURCE.py
python TEST_INT02_ROSTER_LEAVE_LINK.py
python TEST_INT03_HTTP_MULTI_UPLOAD.py
python TEST_MIGRATION_EQUIVALENCE.py
python TEST_ECO_PUBLISHER.py
python TEST_HR_REGISTRY.py
python TEST_HR_SECURITY.py         phase-2 exit gate (HR_REQUIRE_CROSSCHECK=1 with `cryptography` installed: CI does)
python migration/mutations.py      every planted bug must be caught
python BUILD_PROJECT.py
```
Run the server: `python hr_server.py create-admin <user> "<name>"`, then `python hr_server.py serve`.
`TEST_HR_FOUNDATION.py` rewrites `sample/HR_Attendance_Delta_Demo.xlsx`; restore it with `git checkout -- sample/`.
