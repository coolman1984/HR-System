# AGENT HANDOFF — start here if you are a new session

You have no chat history. These files are the memory. Ten minutes, in this order:

1. `CLAUDE.md` — the rules (governing file).
2. This file — where we are, why, what not to break, what is next.
3. `STATUS.md` — built / partially built / planned / design only, the next exit gate, the test commands.
4. `HISTORY.md` (top entries) and `docs/LESSONS.md` — what went wrong before and why.
5. For the area you touch: `docs/HR_SYSTEM_DESIGN.md` (plan, data model, phases), `docs/HR_SECURITY.md` (phase 2),
   `MIGRATION.md` (where the code came from). The skill `.claude/skills/hr-development/SKILL.md` maps the files.

```handoff
phase: 3
stage: 3.0 documentation gate
updated: 2026-09-27
```

## Where we are
HR-System is the ecosystem's only source of truth for people. Built and tested: the migrated attendance application
(locked engine, four-file upload with employee/roster/leave linking), the employee registry and organisation
(phase 1), users/permissions/signed journal/verified backups/recovery (phase 2), and the publisher that feeds GMES.
This session (stage 3.0) added the continuity documents and `TEST_DOCS_CURRENT.py`; no product code changed.
**Phase 3 (shifts) has not started.**

## Why we are here
- The product began as an Excel attendance tool (Department-automation, 2026-09-05) and was migrated with its history
  on 2026-09-27 when the ecosystem needed one owner for people (`MIGRATION.md`).
- The registry came first because every other HR fact hangs on an employee; security came second (owner's order:
  no new business module before permissions, signing and recovery exist).
- Shifts come next because attendance, overtime and GMES's "is this person scheduled" all need a planned schedule
  that exists before attendance does.

## Never break (the short list; `CLAUDE.md` is complete)
- The locked engine (`engine.py`, `calculation_engine.py`, `dashboard.html`, `PROJECT.json`) and 0 differences in
  `TEST_MIGRATION_EQUIVALENCE.py`. New work goes in `hr_core/`.
- The journal is append-only and signed; restores and recoveries are new lines; tables are rebuildable folds.
- Every change goes through `hr_core/service.py` (`require()` + audit) with the version the person edited.
- No personal data leaves HR; no other application's database is touched; `eco_schemas/` and `hr_core/vendor/` are
  never edited here.
- One truth for pay: HR calculates (later), Mizan books. Payroll stays design only.
- Standard library only in top-level files; synthetic data only; no `data/` in git.

## Next step
Phase 3 — shifts, calendars, schedules and assignments. The model and the exit gate are in `STATUS.md` ("Next phase").
Start by writing the phase-3 design section (entities, effective dating, overnight work date, conflict rules, the
minimal read-only contract for GMES) in `docs/HR_SYSTEM_DESIGN.md`, then build the smallest slice with its tests and
planted bugs. A new contract is added in `GMES/packages/eco-contracts` first (additive = same version), then copied
into `eco_schemas/`; GMES's HR end-to-end test must pass against the new commit.

## How to prove your work
Run everything under "How to prove the work is right" in `STATUS.md`, including `python migration/mutations.py`
(every planted bug caught) and, in GMES, `ECO_E2E_REQUIRED=1 npm test` after `sh scripts/fetch-hr.sh` pinned to your
commit. A new rule gets a new planted bug. A failing `TEST_DOCS_CURRENT.py` means a document is behind: fix the
document, never the expectation.

## Open decisions for the owner
- Installer shape: embedded Python runtime (bundles `cryptography`, lets the ZIP carry `hr_core/` and the server) or
  keep "use the customer's Python". Until decided, the customer ZIP ships attendance only.
- The re-upload quirk (same attendance bytes + new auxiliary files are ignored): fix or keep.
- Real (non-synthetic) daily file samples and a Windows run of `START.bat` are still missing.

## Ecosystem observations (not changed from here)
- Mizan's `Accounting-sys/docs/ROADMAP.md` still lists "Payroll (basic): employees" — proposal: "Payroll posting from HR".
- GMES's end-to-end test pins Mizan one merge behind Mizan's `main` (the budgets app); harmless today, refresh the pin
  before the next GMES integration change.
- GMES's pin of HR-System (`8dcfe4f`) has the same content as HR's `main` before this stage.

## End-of-session checklist (every long session, before pushing)
1. `STATUS.md`: stage, labels, last full run, inventory block.
2. This file: the `handoff` block (same phase, stage and date as `STATUS.md`), where we are, next step, open decisions.
3. `HISTORY.md`: a new entry at the top with Symptom / Cause / Fix / Lesson for every bug or discovery.
4. `docs/LESSONS.md`: anything learned the hard way.
5. The design documents when behaviour, contracts or phases change; `project_memory/PROJECT_LOG.md` for decisions.
6. All tests, all planted bugs, GMES's HR end-to-end test. Then commit and push.
