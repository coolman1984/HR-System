# HISTORY

Every change of phase, every bug and every discovery, **newest first**. An entry is never deleted or rewritten: a
correction is a new entry. Each discovery has the shape **Symptom / Cause / Fix / Lesson** and describes what was
observed, not what was intended (`TEST_DOCS_CURRENT.py` checks the shape and that the newest entry belongs to the
session that last updated `STATUS.md`). Durable lessons are also collected in `docs/LESSONS.md`.

Older, finer-grained records stay where they were written: `project_memory/PROJECT_LOG.md` (decision table, Arabic),
`MIGRATION.md`, `docs/HR_SECURITY.md`, `.workflow/` (the 2026-09-05 foundation run).

## 2026-09-27 — Phase 2.5: HR-System becomes one installable product
- **What:** one server and one sign-in for everything (`hr_main.py`, `hr_core/app.py`, `hr_core/web.py`), screens in
  English and Arabic (`hr_core/web/`), the locked attendance engine behind the same sign-in (`hr_core/attendance.py`,
  three new rights), the installation home outside the program and the company identity rules (`hr_core/home.py`,
  ADR-HR-006), data versions with a verified pre-update backup, put-back on failure and resume after a power cut, and
  the recovery installer (`hr_core/upgrade.py`, ADR-HR-007), a Windows installer built with Nuitka and Inno Setup and
  accepted in CI with Python hidden and the network blocked (`tools/`, `installer/`, ADR-HR-004). `TEST_HR_DELIVERY.py`
  (69 checks), 14 planted bugs (55 in total). Decisions: `docs/HR_DELIVERY.md`.
- **Why:** stage 3.0 found that customers could install none of phases 1-2; the owner put delivery before shifts.

### A backup failed with "the request could not be read"
- **Symptom:** the first backup through the new server answered 400.
- **Cause:** the manifest recorded the attendance file's modification time in nanoseconds, larger than the integers
  canonical JSON carries exactly (2^53), so signing the manifest refused it. The audit's new file:line
  (`canonical.py:18`) named it at once.
- **Fix:** the time is stored as a string.
- **Lesson:** every value that goes into a signed, canonical document must fit its number rules; record where an error
  happened, not only its type.

### A test fixture that wrote tables directly could not be updated
- **Symptom:** the first version of the "phase-2 installation" fixture made the pre-update rehearsal fail
  (`accounts_rebuilt_identical failed`), so the update refused to run.
- **Cause:** the fixture changed `auth.db` rows without a journal line; the rehearsal rebuilds accounts from the
  journal and correctly found a difference.
- **Fix:** the fixture writes the old profiles as a journal line, as the phase-2 program did.
- **Lesson:** tables are folds of the journal; a fixture (or a repair) that skips the journal is corruption, and the
  rehearsal is right to refuse it.

### Buttons in tables were invisible, and the header hid itself too well
- **Symptom:** screenshots of the first screens showed empty action columns ("Edit", "Check", "Restore") and, before
  sign-in, a "Sign out" link on the setup page; another page showed "[object HTMLButtonElement]".
- **Cause:** link-styled buttons inherited white text on a white table; `header { display: flex }` overrode the
  `hidden` attribute; nested arrays of children were flattened one level only.
- **Fix:** link buttons take the accent colour, `[hidden]` always hides, children are flattened fully, the header
  stays (the language can be chosen before sign-in) and only "Sign out" hides.
- **Lesson:** look at the screens in a real browser (screenshots) before calling them done; a passing API test says
  nothing about what a person sees.

### A new site could not be saved from the screen
- **Symptom:** creating a site answered 400.
- **Cause:** the registry requires a site's parent to be the company, and the form left "Belongs to" empty.
- **Fix:** a new site belongs to the company unless another parent is chosen.
- **Lesson:** a rule the registry enforces should be the screen's default, not a surprise.

## 2026-09-27 — Stage 3.0: continuity documents and the documentation guard
- **What:** `HISTORY.md` (this file), `STATUS.md`, `docs/LESSONS.md`, `AGENT_HANDOFF.md`, the agent skill
  `.claude/skills/hr-development/SKILL.md`, and `TEST_DOCS_CURRENT.py` (10 planted bugs added to
  `migration/mutations.py`); CI made green (below), 3 more planted bugs, 41 in total. `CLAUDE.md`, `README.md`, `START_HERE_AI.md`, root `SKILL.md` corrected; older
  documents keep their text under a historical banner. No product code changed.
- **Why:** the owner changes agent sessions every few hours. GMES, BAMS and 3D-Modeling can be resumed from their
  files in minutes; HR-System could not.

### The repository still described itself as "attendance only" after two built phases
- **Symptom:** `README.md` ("هذه النسخة هي أساس الحضور فقط"), `START_HERE_AI.md` ("V1.0 يغطي الحضور فقط", "do not claim
  employees, shifts or leave are linked"), `PROJECT_GUIDE.md`, `project_memory/PROGRAM_MAP.md`,
  `SONNET_5_HIGH_EXECUTION_BRIEF_AR.md` and `.workflow/` all described the 2026-09-05 foundation. Linking (INT-01..03),
  the registry (phase 1) and security (phase 2) had been built since. A new agent reading in the recommended order
  would have believed the opposite of the truth.
- **Cause:** each later stage added its own document (`MIGRATION.md`, `docs/HR_SYSTEM_DESIGN.md`,
  `docs/HR_SECURITY.md`) beside the old ones without retiring them, and no single file said "where we are now".
  Nothing failed when a document fell behind.
- **Fix:** one current status file and one handoff; old documents marked HISTORICAL with a pointer, their text kept;
  `TEST_DOCS_CURRENT.py` compares an inventory in `STATUS.md` with the code (kernel files, entrances, tests,
  contracts, entities, permissions, routes, commands, module statuses, planted-bug count, phase plan) and fails when
  they differ, when `STATUS.md` and `AGENT_HANDOFF.md` disagree, or when an old claim reappears as current.
- **Lesson:** a document nobody is forced to update will eventually say the opposite of the code. Make the critical
  ones checkable, and keep history instead of deleting it.

### CI had never been green, on any branch
- **Symptom:** opening the documentation pull request showed every CI run since the migration red: Windows jobs,
  the Windows signing cross-check, and intermittently Linux. Earlier sessions reported "CI on Linux and Windows"
  from local runs only.
- **Cause:** three separate faults. (1) Git on Windows converted LF to CRLF on checkout, so the hash-pinned BAMS
  signing file no longer matched its pin. (2) `SMOKE_TEST.py` and the five tests that start the engine could not delete their temporary folder because the locked
  engine keeps `history.db` open until the process ends, and Windows cannot delete an open file. (3) A real bug: the
  server's threads shared one SQLite connection per database, and reads ran outside the lock; under load a save
  answered 500 (`InterfaceError` at `registry.py:118`, named by the audit once it recorded the place) or 400 instead of
  409, and a reader could see another thread's uncommitted transaction.
- **Fix:** `.gitattributes` `* -text` (byte-identical checkouts everywhere); those tests ignore cleanup errors of their
  temporary folder (engine unchanged); `hr_core/journal.py` `SharedConnection` runs every statement under the
  owner's lock and reads its rows before releasing it, `logout` and `end_sessions` hold the lock across statement and
  commit; the audit records file and line of every server error and unreadable request. New checks
  `every_shared_database_is_serialised` and `a_reader_waits_for_an_open_transaction_and_never_sees_it`, two planted bugs.
- **Lesson:** "CI runs it" means nothing until someone reads a green run on the pull request. A test that fails
  sometimes is reporting a race, not a flake; make the failure name its place, then make the rule deterministic.

### The customer ZIP does not contain the modern HR system
- **Symptom:** `BUILD_PROJECT.py` passes and produces a ZIP, but its explicit file list holds only the attendance
  application; `hr_core/`, `hr_server.py` and `eco_publisher.py` are not in it.
- **Cause:** the list was written for the 2026-09-05 foundation; phases 1–2 were built and tested beside it but never
  packaged (`MIGRATION.md` §6 already said "packaging the publisher is a next step").
- **Fix:** recorded as **Partially built** in `STATUS.md`; not changed here (the installer shape — embedded Python
  runtime, see ADR-HR-002 — is an owner decision).
- **Lesson:** "built and tested" is not "delivered". A status file must say which of the two is true.

### The customer README linked to documents the ZIP does not carry
- **Symptom:** a review of this change (Codex) found that `README.md`, which `BUILD_PROJECT.py` ships to customers,
  linked to `STATUS.md` and `AGENT_HANDOFF.md`, which the ZIP does not contain.
- **Cause:** the README serves two readers — the customer (inside the ZIP) and the developer (in the repository).
- **Fix:** the README names the developer documents as living in the source repository, without links; check 10 of
  `TEST_DOCS_CURRENT.py` fails when a shipped document links to a file the ZIP does not ship (planted bug added).
- **Lesson:** a document that ships has a different audience from one that stays in the repository; check its links
  against the package, not against the repository.

### Mizan's roadmap still plans its own employees and payroll
- **Symptom:** `Accounting-sys/docs/ROADMAP.md` lists "Payroll (basic): employees, salary components, monthly posting".
- **Cause:** written before the ecosystem decision that HR calculates pay and Mizan only books the resulting entry.
- **Fix:** none from here (never touch another repository from this one); recorded in `AGENT_HANDOFF.md` as a proposal
  for Mizan: rename it "Payroll posting from HR".
- **Lesson:** a stale roadmap line in a neighbour can recreate a second source of truth; check neighbours' plans, not
  only their code.

## 2026-09-27 — Phase 2: users, permissions, signed journal, verified backups (`8dcfe4f`)
- **What:** `hr_core/auth.py`, `service.py`, `api.py`, `device.py`, `journal.py`, `signing.py`, `backup.py`,
  `hr_server.py`; exit gate `TEST_HR_SECURITY.py` (77 checks); 28 planted bugs. Decisions ADR-HR-001..003 in
  `docs/HR_SECURITY.md`. GMES re-pinned and its HR end-to-end test passed against this commit.

### A broken `cryptography` install crashed instead of raising ImportError
- **Symptom:** with a system `cryptography` 41 and a missing `cffi`, importing it raised a Rust `PanicException`.
- **Cause:** `PanicException` derives from `BaseException`, so `except ImportError` / `except Exception` do not catch it.
- **Fix:** `hr_core/signing.py` catches everything except interruption while loading and accepts a backend only after
  it reproduces the RFC 8032 vector; problems are shown by `/api/admin/health`.
- **Lesson:** an optional native dependency must be probed by what it does, not by whether it imports.

### Opening the registry without a company code created a second company
- **Symptom:** the publisher opening the registry without a company code produced a company named `COMPANY` next to the
  real one (a phase-1 bug found during phase 2).
- **Cause:** the registry created the company from its constructor arguments on every open.
- **Fix:** the company is created only when none exists; a test proves it.
- **Lesson:** "create if missing" must look at the data, not at the arguments of the caller.

### A backup waited forever
- **Symptom:** the backup never finished while the live journal connection had an open transaction.
- **Cause:** the online copy waited on the live connection's lock.
- **Fix:** backups copy from a fresh read-only connection.
- **Lesson:** never back up through the connection that writes.

### The number of the last line cannot tell a restored journal from a current one
- **Symptom:** a journal put back from an old backup, then extended by one new device line, had a sequence number that
  looked current to the tables.
- **Cause:** only the sequence number of the last applied line was stored.
- **Fix:** every store records the **hash** of the last line it applied and checks the journal follows it.
- **Lesson:** position is not identity; compare hashes.

### Two planted bugs survived the first run
- **Symptom:** an appended unsigned line and a disabled account's session from another writer both passed the suite.
- **Cause:** no test covered those two paths.
- **Fix:** `appended_unsigned_line_detected` and `session_rechecks_account_on_every_request`.
- **Lesson:** a green suite proves nothing until it has been made to fail.

## 2026-09-27 — Phase 1: independent employee registry and organisation (`89e4d96`)
- **What:** `hr_core/` beside the locked engine: organisation tree, jobs, positions, employees (no personal data),
  hash-chained journal (ecosystem format, GMES ADR-026), optimistic versions, soft delete, rebuild, import from the data
  dictionary workbooks; the publisher takes employees from the registry. `TEST_HR_REGISTRY.py` (13), 11 planted bugs.

### Every re-import looked like a change
- **Symptom:** importing the same workbook twice wrote new journal lines the second time.
- **Cause:** columns declared `TEXT` turned `1` into `'1'`, so the stored value never equalled the imported one.
- **Fix:** columns without a declared type (SQLite keeps the Python type); a planted bug re-adds `TEXT`.
- **Lesson:** "re-import writes nothing" must be a test, because the database can quietly change a value's type.

## 2026-09-27 — Migration from Department-automation (`0a9ac4a`)
- **What:** the HR attendance application moved here with its full history (`58a2298`); equivalence test (0
  differences), publisher, contract validator, CI on Linux and Windows. Record: `MIGRATION.md`.

### New employee/roster/leave files are ignored when the attendance bytes were already uploaded
- **Symptom:** uploading the same attendance file again with new auxiliary files says "already processed" and the new
  files do nothing.
- **Cause:** the duplicate check of the locked engine looks at the attendance file.
- **Fix:** none yet — pinned in `migration/golden_behaviour.json` (scenario 4) so it cannot change by accident; a fix
  needs a decision and a test that first reproduces it (CLAUDE.md).
- **Lesson:** during a migration, preserve and record behaviour; fixing it is a separate, decided change.

### Four original tests could not import openpyxl
- **Symptom:** `TEST_HR_FOUNDATION.py` and the three INT tests failed on a clean machine.
- **Cause:** they import `openpyxl` directly; the original author had it installed system-wide, while the application
  loads it from `vendor.zip`.
- **Fix:** CI and every instruction set `PYTHONPATH=vendor.zip`; the tests themselves are unchanged.
- **Lesson:** run a migrated suite on a clean machine before trusting "it passed at the source".

## 2026-09-05 — Attendance foundation, then INT-01..03 (in Department-automation)
- **What:** attendance import and history (V1.0), then attendance + employee + roster + leave uploaded together and
  linked, with an upload screen. Details: `project_memory/PROJECT_LOG.md`, `.workflow/HANDOFF_AR.md`.

### Linked field names came out doubled
- **Symptom:** joined roster fields were named like `roster_roster_status`.
- **Cause:** the join added its prefix to field names that already carried it.
- **Fix:** prefixes are applied once (INT-02).
- **Lesson:** check the produced column names in a test, not only the values.

### A test made a third-party library look like a runtime dependency
- **Symptom:** `CHECK_ENVIRONMENT.py` reported `requests` as required to run the program.
- **Cause:** the first draft of `TEST_INT03_HTTP_MULTI_UPLOAD.py` used `requests`, and the check scans every top-level
  file.
- **Fix:** the test uses `urllib` from the standard library.
- **Lesson:** top-level files are standard library only, tests included.
