# HR-System — rules for anyone (human or AI) changing this repository

HR-System is the ecosystem's **authoritative source of workforce truth**: employees and their ids,
departments, positions, organisation, employment status, shifts, attendance, absence, leave, overtime,
skills/training, assignments, and payroll CALCULATION data. Other applications (GMES manufacturing, Mizan
accounting, Space Planner 3D) keep read-only mirrors and reference employees by the shared id
`UUIDv5(company, "hr:employee:<Employee_ID>")`. BAMS (`Mr.Ayman-HR`) is a different product and stays separate.

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
- Edit `eco_schemas/`: they are generated in `coolman1984/GMES/packages/eco-contracts` and copied here unchanged.

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
python migration/mutations.py      every planted bug must be caught
python BUILD_PROJECT.py
```
`TEST_HR_FOUNDATION.py` rewrites `sample/HR_Attendance_Delta_Demo.xlsx`; restore it with `git checkout -- sample/`.
