# AGENT HANDOFF — start here if you are a new session

You have no chat history. These files are the memory. Ten minutes, in this order:

1. `CLAUDE.md` — the rules (governing file).
2. This file — where we are, why, what not to break, what is next.
3. `STATUS.md` — built / partially built / planned / design only, the next exit gate, the test commands.
4. `HISTORY.md` (top entries) and `docs/LESSONS.md` — what went wrong before and why.
5. For the area you touch: `docs/HR_SYSTEM_DESIGN.md` (plan, data model, phases), `docs/HR_SECURITY.md` (phase 2),
   `MIGRATION.md` (where the code came from). The skill `.claude/skills/hr-development/SKILL.md` maps the files.

```handoff
phase: 2.5
stage: 2.5 one installable product + 2.6 product shell
updated: 2026-09-28
```

## Where we are
HR-System is the ecosystem's only source of truth for people. Built and tested: the migrated attendance application
(locked engine), the employee registry and organisation (phase 1), users/permissions/signed journal/verified
backups/recovery (phase 2), the publisher that feeds GMES, and now (phase 2.5) **one installable product**: one
server and one sign-in for everything, screens in English and Arabic, the attendance engine behind the same sign-in,
data outside the program, company identity rules, data-version updates with a verified pre-update backup, a Windows
installer built and accepted in CI. **Phase 3 (shifts) has not started.** Phase 2.5 still owes the owner's
clean-PC run (Windows Sandbox, `docs/HR_DELIVERY.md` §5).

**Phase 2.6 (UX, 2026-09-28):** the owner stopped all business features until the products look commercial. The screens
are now one application shell built from the ecosystem's interface kit (`hr_core/web/eco-ui/`, the unchanged copy of
GMES `packages/eco-ui/src`, pinned by SHA-256 in `hr_core/eco_ui_pin.json`). Waiting for: the owner's approval of the
look, after comparing with his redacted G-MES screenshots (`docs/ux/visual-acceptance.md`).

**Mizan's look and ideas (2026-09-28, owner's order):** the kit (GMES `4d27f55`, ADR-033 there) now has an opt-in
*modern* look taken from Mizan, and HR uses it by default; the grid filters every column, groups and has presets. HR added
the Advisor (`ADV1010`), a Mizan-style dashboard, the rights matrix with templates and separated duties, and a subtitle and
help on every screen. They were checked in Chrome over CDP on 2026-09-28 (demo installation) and the bugs found were fixed.

**Discipline, journey, guide, demo (2026-09-28, owner's order):** the `discipline` module is built (penalty schedule,
violations proposed from attendance, a separate right to decide, the law's limits, days never money; data version 3;
`TEST_HR_DISCIPLINE.py`). New screens: Violations and penalties (`DSC2010`), Penalty schedule (`DSC1010`), Employee journey
(`EMP2010`, time-lapse), Help center (`HLP1010`); F1 help panel, guided tours, guide mode. `Start-HR-Demo.bat` builds a
separate demo installation (never a real one) at `..\HR-Demo` and starts it on port 8790 (admin / 123; other
users Demo-2026!pass); the client story is Karim Abdelaziz (`E000900`), production manager hired 2026-06-15.

**Ecosystem plan, Phase A (2026-09-28, approved by the owner):** the installed product now publishes to GMES by itself.
Settings → Integration (GMES) sets the address, the node, the interval and a write-only key; with an empty address HR
works on its own. `hr_core/eco_link.py` runs the publisher in a background thread started by `Product.open()`, stopped
by `close()`, restarted on a change, reading the registry through its own read-only connection. The GMES key is kept in
`data/node/gmes.key` (Windows DPAPI, machine scope), never in config.json, the API, a backup, a log or the audit
(`docs/HR_DELIVERY.md` ADR-HR-008). Routes: `GET|PUT /api/admin/integration`, `POST /api/admin/integration/run`.
`python eco_publisher.py` with `ECO_*` keeps working unchanged.

## Why we are here
- The product began as an Excel attendance tool (Department-automation, 2026-09-05) and was migrated with its history
  on 2026-09-27 when the ecosystem needed one owner for people (`MIGRATION.md`).
- The registry came first because every other HR fact hangs on an employee; security came second (owner's order:
  no new business module before permissions, signing and recovery exist).
- Phase 2.5 came before shifts because the continuity work found that customers could not install any of it: the
  delivery ZIP held the attendance tool only. From now on every feature lands in the program a customer installs.
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
000. Phase A (the link to GMES): run the Windows installer job and look at Settings → Integration (GMES) in the
   installed program, in English and Arabic, light and dark (not yet seen in a browser); extend
   `tools/installed_acceptance.py` with an address and a key (DPAPI in the compiled program was not run); in GMES, let
   the HR end-to-end test configure HR through `PUT /api/admin/integration` instead of `ECO_*` variables.
00. The owner reviews the demo (`Start-HR-Demo.bat`): the journey of `E000900`, violations and decisions, the Advisor, the
   guided tours. Arabic and dark mode of the new screens (journey, violations, help panel) were not yet looked at in a
   browser: do that, and retake `docs/ux/` screenshots. Fix the look in GMES
   `packages/eco-ui/src` (kit) or `hr_core/web/hr.css` (HR's own parts), never in `hr_core/web/eco-ui/`.
0. Phase 2.6 (UX): wait for the owner's approval of the shell; apply his G-MES screenshot comparison to the TOKENS in
   GMES `packages/eco-ui/src/tokens.css` (never here), copy the kit back with a new pin, retake `docs/ux/` screenshots.
   Never edit `hr_core/web/eco-ui/` in this repository.
0b. Shifts (phase 3) and skills (phase 5) were built on the owner's order (2026-09-28); still owed for their gates:
   Excel import of shifts/rosters, planned overtime, leave on the plan, training, a GMES screen for station requirements.
   **Payroll is design only** (`docs/HR_PAYROLL_DESIGN.md`): do not build it before its gate (§2 there).
1. Close phase 2.5: the CI job `windows-installer` is green (31/31 on b3d106d); still owed: the owner's clean-PC run in
   Windows Sandbox; mark phase 2.5 done in `docs/HR_SYSTEM_DESIGN.md` §7 and move the `phase` line here and in
   `STATUS.md` to 3.
2. Phase 3 — shifts, calendars, schedules and assignments (model and exit gate in `STATUS.md`). Start with the
   phase-3 design section in `docs/HR_SYSTEM_DESIGN.md`, then the smallest slice, with screens (both languages),
   tests and planted bugs. A new data shape means a new `DATA_VERSION` step in `hr_core/upgrade.py`.
   A new contract is added in `GMES/packages/eco-contracts` first, then copied into `eco_schemas/`.

## How to prove your work
Run everything under "How to prove the work is right" in `STATUS.md` (on Windows also the installer job), including `python migration/mutations.py`
(every planted bug caught) and, in GMES, `ECO_E2E_REQUIRED=1 npm test` after `sh scripts/fetch-hr.sh` pinned to your
commit. A new rule gets a new planted bug. A failing `TEST_DOCS_CURRENT.py` means a document is behind: fix the
document, never the expectation.

## Open decisions for the owner
- Should GMES also use the modern look? (Today: GMES classic, HR modern; both from the same kit.)
- The penalty schedule's defaults (5 days per violation and per month, 30 days to decide, investigation over one day)
  follow the Egyptian labour law as understood here: have them confirmed by the company's legal adviser before selling.
- Mizan's Egyptian payroll rules (Law 7/2024 salary tax, social insurance): recorded as design input; code only after
  the payroll gate (`docs/HR_PAYROLL_DESIGN.md` §2).
- A code-signing certificate before selling (the "unknown publisher" warning is accepted for trials only).
- When a standalone customer later adopts Mizan: build the adoption and matching step (planned, ADR-HR-006).
- The re-upload quirk (same attendance bytes + new auxiliary files are ignored): fix or keep.
- Real (non-synthetic) daily file samples, and one run on a PC with Microsoft Excel for protected workbooks.

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
