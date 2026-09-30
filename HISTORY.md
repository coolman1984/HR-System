# HISTORY

Every change of phase, every bug and every discovery, **newest first**. An entry is never deleted or rewritten: a
correction is a new entry. Each discovery has the shape **Symptom / Cause / Fix / Lesson** and describes what was
observed, not what was intended (`TEST_DOCS_CURRENT.py` checks the shape and that the newest entry belongs to the
session that last updated `STATUS.md`). Durable lessons are also collected in `docs/LESSONS.md`.

Older, finer-grained records stay where they were written: `project_memory/PROJECT_LOG.md` (decision table, Arabic),
`MIGRATION.md`, `docs/HR_SECURITY.md`, `.workflow/` (the 2026-09-05 foundation run).

## 2026-09-30 - A simulated clock, impossible in an installed program
- **Symptom:** the scenario engine has to live ninety days in minutes; every rule of HR (past is history, overtime at most 3 days back, leave, contracts) reads "today", so nothing could be played on another date.
- **Cause:** `today()` was the computer's date, read in several places.
- **Fix:** one helper `hr_core/clock.py`; with `HR_SIMULATION=1` an administrator may move the date (`PUT /api/sim/today`, audited); without the switch the route is not even registered. `TEST_HR_SIMULATION.py` and two planted bugs (date movable without the switch; moved without the settings right).
- **Lesson:** a test hook that can exist in production is a back-dating hole; make it absent, not just refused.

## 2026-09-30 — Ecosystem plan, WP-H1 to WP-H5: what manufacturing tells HR, recruitment, overtime, training, leave
- **What:** the machine-key inbox (`POST /eco/v1/inbox`, `hr_core/eco_inbox.py`: crew requirements and labour facts from
  GMES, applied once, newest version wins) with the staffing gap per day and shift (`GET /api/staffing/gap`) and the
  labour evidence beside the plan (`GET /api/labour/evidence`); eleven new registers in the signed registry
  (headcount plan, agency, hiring request, candidate, onboarding task, contract, overtime request, course, training
  session, leave type, leave request) with their rules in `hr_core/people_ops.py` and `hr_core/people_service.py`; hire,
  complete-a-session, propose-headcount, expire-contracts, leave balance, overtime figures and policy as commands;
  eleven new rights (`hr.recruitment|overtime|training|leave.*`, data version 4 gives them to the built-in profiles);
  fourteen screens in English and Arabic (`STF2010`, `REC1010`–`REC1060`, `OVT1010`, `OVT1020`, `TRN1010`, `TRN2010`,
  `LEV1010`, `LEV2010`, `LEV3010`); `TEST_HR_PEOPLE_OPS.py` (60 checks); 19 new planted bugs. Modules `recruitment`,
  `overtime` and `training` are now built. Payroll (WP-H6) stays design only.
- **Why:** the ecosystem plan (`complete-company/plan/`) needs HR to hear what production needs, to hire and qualify
  people for it, and to keep the overtime and leave figures payroll will need later, without any pay or personal data
  leaving HR. Seen in a real browser (Chrome, synthetic company): all fourteen screens open with no script error, a
  requisition is approved by a second user, a candidate goes applied → offered → hired (employee, contract and
  onboarding created), an overtime request is approved.

### Six planted bugs survived the first version of the tests
- **Symptom:** running only the new planted bugs left six alive: a machine key without the scope, an older crew
  requirement replacing a newer one, overtime and leave approved by the person who entered them, a course lowering a
  higher qualification, and (as a planted bug that changed nothing) a shift filter that cannot differ.
- **Cause:** the tests only tried the refusals that the missing right already produced (`perm.denied` comes first), never a
  person who has the approve right and is also the author; there was one accepted scope; versions were tested as equal but
  never as older; no test held a qualification above the course level.
- **Fix:** checks added for each (`even_an_approver_cannot_approve_*`, `a_key_without_the_scope_is_refused`,
  `an_older_version_never_replaces_a_newer_one`, `a_course_never_lowers_a_higher_qualification`); the planted bug that
  could not change behaviour (`shift_code` is set only on working days) was replaced by one that can (a person of
  another shift counted for shift A) and a second employee on the night shift joined the test.
- **Lesson:** a planted bug that survives is a missing test or a mutant that changes nothing; decide which before adding
  the check. A four-eyes rule needs a test where the author holds the right.

### The documents check could not read the routes it was guarding
- **Symptom:** `TEST_DOCS_CURRENT.py` failed on commit `412beea` (the crew-requirement inbox) at the first inventory line,
  and after that would still have ignored every route written as a raw string or as `"/api/" + ENTITY_ROUTE`.
- **Cause:** the route list was read with a regular expression for `@route("M", "pattern")`; routes with `r"..."`, and the
  four register routes built from `ENTITY_ROUTE`, did not match, so they were neither required nor checked in `STATUS.md`.
  The inbox commit also did not update the documents.
- **Fix:** the test reads the decorators with `ast` and writes `ENTITY_ROUTE` out from `ENTITIES`; `STATUS.md`'s inventory
  lists every route again (raw ones included).
- **Lesson:** a guard that parses code with a regular expression stops guarding when the code style changes; parse it.

## 2026-09-28 — Ecosystem plan, Phase A: the installed product publishes to GMES by itself
- **What:** Settings → Integration (GMES) (address, node, interval, write-only key, "Send now", last delivery, pending /
  delivered / refused, both languages) and `hr_core/eco_link.py`: a background thread inside the product, started by
  `Product.open()` when an address is set, stopped by `close()`, restarted on a change; routes
  `GET|PUT /api/admin/integration` and `POST /api/admin/integration/run` (right `admin.settings.manage`, audited without
  the key); `config.json` section `eco` validated in `hr_core/home.py`; the GMES key in `data/node/gmes.key` (Windows
  DPAPI, machine scope; owner-only file elsewhere). `eco_schemas/README.md` now lists all five schemas. 17 new checks in
  `TEST_HR_DELIVERY.py` (a fake GMES inbox on 127.0.0.1), one in `TEST_HR_WORKFORCE.py`, 5 new planted bugs.
- **Why:** until now only `python eco_publisher.py` with `ECO_*` environment variables published, so no installed
  customer could feed GMES (`STATUS.md` listed it as Partially built). `docs/HR_DELIVERY.md` ADR-HR-008.

### A planted bug was committed: the last administrator could be disabled
- **Symptom:** on commit `06fcf5e` `TEST_HR_SECURITY.py` failed at `last_administrator_cannot_be_disabled` (the server
  answered 200 and disabled the only administrator), and `migration/mutations.py` stopped with "anchor not found" for
  the planted bug "the last administrator can be disabled".
- **Cause:** `hr_core/auth.py` still held that planted bug (`self._check_admin_remains()` replaced by `pass`), committed
  with `0ba58a3`. A mutation run that is stopped before its `finally` block leaves the planted bug in the file.
- **Fix:** the line is back; `TEST_HR_SECURITY.py` passes again and the planted bug is caught again.
- **Lesson:** after an interrupted `python migration/mutations.py`, run `git diff` before committing: a planted bug looks
  like an ordinary one-line change.

### The planted-bug run stopped half way: the dictionaries had Windows line endings
- **Symptom:** `python migration/mutations.py` stopped with "anchor not found in hr_core/web/i18n/en.json" (the planted
  bug "a menu name is missing from the dictionary"), so every planted bug listed after it never ran.
- **Cause:** commit `0ba58a3` rewrote `en.json` and `ar.json` with CRLF line endings (they had LF before); the anchor ends
  in `\n`. With `* -text` in `.gitattributes`, git keeps whatever bytes a tool writes.
- **Fix:** both dictionaries are LF again (same keys and texts; the diff is line endings plus the new `eco.*` texts).
- **Lesson:** a tool that rewrites a JSON file on Windows must write `newline=""` bytes as they were; check
  `git ls-files --eol` when a whole file shows as changed.

### Opening the registry to publish could write to it
- **Symptom:** the plan said the link opens "its own read-only Registry"; `hr_core.registry.Registry` has no read-only mode.
- **Cause:** `Registry()` opens the journal as well, creates missing tables and runs `recover()`, which folds (writes)
  journal lines the tables have not seen; a second opener beside the live service could race it and fold a line twice.
- **Fix:** the link reads through `ReadOnlyRegistry` (`hr.db` opened with `mode=ro`, only `list` and `by_id`, the two
  calls `eco_publisher` needs), opened and closed in the thread that runs each cycle. `TEST_HR_WORKFORCE.py` proves it
  gives the same snapshots as the registry and cannot write; a planted bug opens it writable.
- **Lesson:** "read-only" is a property of the connection, not of the caller's intentions: open it `mode=ro`.

### An attendance upload was sometimes not yet in the audit when the test looked
- **Symptom:** `TEST_HR_DELIVERY.py` failed twice in a row at `an_upload_is_audited_with_its_person` on a Windows
  checkout, then passed on the next runs; the same commit passed in a clean copy.
- **Cause:** the server writes the attendance audit line just after the locked engine has sent its answer; a fast client
  can read the audit in between. The product is right (the upload is audited); the test raced it.
- **Fix:** the test waits (at most 15 s) until the expected number of attendance audit lines is there
  (`attendance_events()`), then checks them as before; the planted bug on that check is still caught.
- **Lesson:** when the server acts after it answered, a test must wait for the effect, never assume it is already there.

### The schema README listed three of the five contracts
- **Symptom:** `eco_schemas/README.md` named the envelope, employee and attendance day only.
- **Cause:** `eco.schedule_day.v1` and `eco.qualification.v1` were copied in with phases 3 and 5 without the README line.
- **Fix:** both rows added (README only; the schema files are unchanged copies from GMES).
- **Lesson:** a copied folder's index is part of the copy: check it when a file is added.

## 2026-09-28 — Discipline module, employee journey, guide system and the client demo
- **What:** on the owner's order ("a full demo for clients: a new manager hired, his days, activities and penalties, time
  lapse", "a real penalties module", "Mizan's guide and warning system", "auto-fit the columns"): the **discipline** module
  (`hr_core/discipline.py`, phase 6: penalty schedule, violations proposed from attendance, decisions under a separate right,
  the law's limits, days never money, data version 3, `TEST_HR_DISCIPLINE.py`); the **employee journey** screen (`EMP2010`,
  one person's facts from every module on one timeline with a week-by-week time-lapse); the **guide system** from Mizan's
  design (guide mode, F1 help panel, 8 guided tours, help center `HLP1010`, warnings on the record, tips in the forms); the
  kit (GMES `e14ff0d`, `6c70662`) gained auto-fitting columns, colour tones, `drawer()` and `tour()`; a **demo installation**
  (`Start-HR-Demo.bat`, `tools/make_demo.py`) built from the synthetic factory dataset through the product's own code, with
  the story of Karim Abdelaziz, production manager hired 2026-06-15.
- **Why:** the owner shows the product to clients; every figure must come from the real engine, so the demo is made by
  the product's own operations, each by the person who would do it, on its own date. Payroll stays design only: a penalty
  is recorded in days; payroll turns days into money later (`docs/HR_PAYROLL_DESIGN.md`).

### The whole screen application did not load: one parenthesis too many
- **Symptom:** in Chrome the page stayed on the sign-in screen with `SyntaxError: Unexpected token ')'` in `app.js`; every
  automated check was green.
- **Cause:** `node --check app.js` treats a `.js` file outside a package as a script and did not flag the error in that
  run; no Python test executes the screens.
- **Fix:** the extra parenthesis was removed; every change to the screens is now checked as a module
  (`node --check` on a copy named `.mjs`) and opened in a real browser over CDP before it is called done.
- **Lesson:** a green suite that never runs the screens proves nothing about them: open them.

### Auto-fitted columns came out narrower than their text
- **Symptom:** after the first auto-fit, names showed as "Moh…" and positions as "POS-00…".
- **Cause:** the width measured the text only: not the 24 px of cell padding, the avatar drawn beside a name, or the
  monospace font of code columns.
- **Fix:** the kit measures with the column's own font (mono for codes), adds the look's padding and the avatar, and a
  width the person dragged is kept (only those are saved in the layout).
- **Lesson:** measure what is drawn, not the value.

### The one who proposes a violation could not be kept from deciding it
- **Symptom:** the first test run refused the line manager ("no right hr.discipline.write") when he decided a violation.
- **Cause:** `save()` checked the entity's write right before looking at what the change was, so deciding needed both
  rights and the two duties could not be separated.
- **Fix:** a decision (status other than proposed) needs only `hr.discipline.approve`; a proposal only
  `hr.discipline.write`; who decided and when come from the server. A planted bug proves it.
- **Lesson:** separate duties are separate checks, decided by what the request does, not by the table it touches.

## 2026-09-28 — Mizan's look and ideas in HR-System (phase 2.6, through the shared kit)
- **What:** on the owner's order ("take Mizan's design, look, features and ideas"): the kit is re-copied from GMES
  `4d27f55` (ADR-033 there) with its new opt-in modern look (Mizan's tokens, Inter + IBM Plex Sans Arabic carried in
  `eco-ui/fonts/`), column filters, grouping and presets in every grid, filter chips, actions in the screen search. HR uses
  the modern look by default (a person may switch back). New in HR: the **Advisor** (`ADV1010`, 23 daily checks with the
  reason, what to do and the records concerned, computed from what the person may already read), a Mizan-style
  **dashboard** (KPIs, quick actions, status donut, advisor card, latest hires), the **rights matrix** (object × action pills,
  templates, "rights that should be separated" warnings, new profiles from a template), a subtitle and a help text on every
  screen, grid presets, print, and Mizan's sign-in look. 187 new texts in each language. No new route, right or data shape.
- **Why:** the owner judged Mizan the more advanced product. Its React code cannot enter a standard-library program with
  no build step, and a copy in HR alone would split the ecosystem's look, so the ideas went into the kit once (GMES) and
  HR took the kit unchanged. Mizan's Egyptian payroll rules are recorded as design input only (`docs/HR_PAYROLL_DESIGN.md`).

### The planted-bug run changed the line endings of 14 files on Windows
- **Symptom:** after `python migration/mutations.py` on Windows, 14 files (among them `PROJECT.json`, the locked
  core, `hr_core/vendor/ed25519_bams.py`) showed as modified with no visible change; `git diff --ignore-cr-at-eol` was empty.
- **Cause:** the run read each file with `Path.read_text` and put it back with `Path.write_text`, which on Windows writes
  every LF as CRLF. The repository stores files byte for byte (`* -text`) and pins some of them by hash.
- **Fix:** the files were converted back (CRLF to LF only, content untouched); `mutations.py` now reads and writes bytes.
- **Lesson:** a tool that "puts a file back" must put back the same bytes; text mode is a change on Windows.

### The kit's pin could not hold a folder
- **Symptom:** the new kit carries its typefaces in `eco-ui/fonts/`; the pin check hashed `iterdir()` entries and would
  have tried to read the folder as a file.
- **Cause:** the check was written when the kit was three flat files.
- **Fix:** the check hashes every file below the kit by its relative path; `web.py` serves `.woff2` (and the licence `.txt`).
- **Lesson:** a pin describes a tree, not a directory listing.

## 2026-09-28 — Shifts (phase 3) and skills (phase 5) built; payroll designed, not built
- **What:** on the owner's order: shifts, working calendars, effective-dated assignments, day changes and swaps, the
  planned schedule and its comparison with attendance (`hr_core/scheduling.py`); skills and qualifications with levels
  and expiry (`hr_core/skills.py`); six new registry entities, four rights, data version 2 (built-in profiles gain the
  rights; a verified `keep-` backup first); eight new screens; `eco.schedule_day.v1` and `eco.qualification.v1`
  (generated in GMES, copied to `eco_schemas/`); GMES mirrors both with their age and refuses an unqualified person at a
  station. `TEST_HR_WORKFORCE.py` (50 checks), 8 new planted bugs (70). Payroll: `docs/HR_PAYROLL_DESIGN.md` only.
- **Why:** the owner asked for shifts, skills and payroll; payroll was kept as design by his choice (asked 2026-09-28),
  because calculating money on attendance not yet bound to the registry employee would give wrong pay.

### A planted bug pointed at a module that had moved on
- **Symptom:** the planted-bug run stopped: "anchor not found in hr_core/modules.py" for "a module is marked built without the documents".
- **Cause:** that planted bug flipped `shifts` from planned to built; `shifts` is now really built, so its text changed.
- **Fix:** the planted bug now flips `overtime`, still planned.
- **Lesson:** a planted bug that can no longer be planted fails loudly by design; move it to something still true.

### A validator that refuses unknown keywords did its job
- **Symptom:** the first publication of a planned day failed: `schema keyword(s) not supported by eco_contract.py: ['enum']`.
- **Cause:** the new contract is the first with an enumerated field; HR's standard-library validator supports a fixed
  subset of JSON Schema and refuses anything else loudly, by design.
- **Fix:** `enum` added to the validator (value must be one of the list), with the new contracts validated in the test.
- **Lesson:** a validator that fails loudly on what it does not know turns a silent half-check into a one-line fix.

### New tables would have broken the rehearsal of every older backup
- **Symptom:** (found by reasoning before it happened) the backup rehearsal compares the restored tables' fingerprint
  with the one in the backup's manifest, written by the program that made the backup.
- **Cause:** the fingerprint covered every entity; six new, empty entities would change it for every backup made before.
- **Fix:** entities added later are left out of the fingerprint while empty; a test proves an empty installation gives
  exactly the fingerprint phase 2 computed.
- **Lesson:** anything stored with a backup must be computed the same way by every later program; extend it only additively.

### The past schedule must not move
- **Symptom:** (design) changing a shift's times, a calendar's rest days or a started assignment would silently change
  the plan of days already worked, and with it every comparison with attendance.
- **Cause:** a plan resolved from current records is only history-safe if those records cannot change backwards.
- **Fix:** a started assignment only ends (not before yesterday); a day before today is not re-planned; a shift or
  calendar that people already worked keeps its times and rest days (make a new one); planted bugs for each.
- **Lesson:** effective dating is a rule on writes, not a filter on reads.

## 2026-09-28 — Phase 2.6 (UX): the product shell before any new business feature
- **What:** the owner stopped shifts, skills and payroll until HR-System looks and feels like a commercial HR product.
  The screens (`hr_core/web/app.js`, `hr_core/web/hr.css`) were rebuilt as one application shell on the ecosystem's
  interface kit, built in GMES (`packages/eco-ui/src`, GMES ADR-029) and copied here unchanged into `hr_core/web/eco-ui/`
  with a SHA-256 pin (`hr_core/eco_ui_pin.json`): sign-in and first-run pages, dashboard, employees (conditions, dense
  grid, detail panel, bulk actions, grouped editor), organisation tree, jobs, positions, attendance, users, profiles and
  rights, audit, backups, health, settings; English/Arabic, light/dark. `TEST_HR_DELIVERY.py` 76 checks; 3 new planted
  bugs (62). Screenshots and the visual acceptance checklist: `docs/ux/`.
- **Why:** a strong backend that looks primitive does not sell; the owner wants one design system, not styled pages.

### The kit is shared, so a local fix would be a fork
- **Symptom:** while polishing HR screens, small kit fixes (a quick filter, a reset icon, chart scaling) were needed.
- **Cause:** the kit lives in GMES; editing the HR copy would make two kits that drift, exactly like two copies of a
  security algorithm (L14).
- **Fix:** every kit change was made in GMES and copied back; a test compares the copy with the pinned hashes and a
  planted bug (a changed token) must be caught.
- **Lesson:** a shared file has one home; the others hold a pinned copy and a test that refuses any other.

### Screenshots hide what only a person's hands find
- **Symptom:** every screenshot looked right, yet a browser run found the quick filter returning nothing for a name in
  a hidden column, and the org tree opening with the selected department collapsed out of sight.
- **Cause:** screenshots show states, not interactions; the filter searched visible columns only, the tree opened roots only.
- **Fix:** the filter searches every column; the tree opens every unit that has children; interactions are driven in a
  real browser (sort, hide + reload, quick filter, saved filter, required-condition refusal, screen search, tab close, export).
- **Lesson:** review a screen by using it, not only by looking at it.

### The dashboard chart scaled its text with its bars
- **Symptom:** on a wide card the department chart's labels became huge and stretched.
- **Cause:** the SVG was drawn narrow and stretched without keeping its proportions.
- **Fix:** uniform scaling and a drawing width close to the card's (kit `barChart({ width })`).
- **Lesson:** never stretch a drawing that carries text.

## 2026-09-27 — Phase 2.5: HR-System becomes one installable product
- **What:** one server and one sign-in for everything (`hr_main.py`, `hr_core/app.py`, `hr_core/web.py`), screens in
  English and Arabic (`hr_core/web/`), the locked attendance engine behind the same sign-in (`hr_core/attendance.py`,
  three new rights), the installation home outside the program and the company identity rules (`hr_core/home.py`,
  ADR-HR-006), data versions with a verified pre-update backup, put-back on failure and resume after a power cut, and
  the recovery installer (`hr_core/upgrade.py`, ADR-HR-007), a Windows installer built with Nuitka and Inno Setup and
  accepted in CI with Python hidden and the network blocked (`tools/`, `installer/`, ADR-HR-004). `TEST_HR_DELIVERY.py`
  (74 checks), 18 planted bugs (59 in total). Decisions: `docs/HR_DELIVERY.md`.
- **Why:** stage 3.0 found that customers could install none of phases 1-2; the owner put delivery before shifts.

### Four review findings on the first phase-2.5 pull request (Codex)
- **Symptom:** (1) the installer gave the built-in Users group modify rights on `%ProgramData%\HR-System`, so any other
  account on the PC could read HR data, password hashes and the device key, or write "valid" signed history; (2) setup
  wrote the company identity before the administrator's user name was checked, so a refusal left an identity that can
  never change; (3) once a `keep-` backup existed it always sorted first, so "latest backup" and the automatic
  backup's "nothing changed" check used the old one; (4) a refused or duplicate attendance upload was audited as
  `attendance.uploaded`.
- **Cause:** (1) the BAMS installer pattern was copied for a folder that holds secrets BAMS keeps elsewhere; (2) only
  the password was checked before the write; (3) sorting by name, and `k` > `h`; (4) the audit looked at the address,
  not at what the engine answered.
- **Fix:** (1) the installer removes inherited rights and grants SYSTEM, Administrators and the installing account
  only (`icacls`), the start-up shortcut is that person's; the installed-program test checks the rights; (2) every
  administrator field is checked before `set_company`, which itself validates before writing; (3) backups are
  ordered by their time stamp; (4) the engine's reply is captured and a refusal is audited as `attendance.refused`.
  Three new checks and three planted bugs (58).
- **Lesson:** a reused pattern carries its assumptions: check what the folder holds before copying its rights. And
  "written once" data must be the last thing written, after every other check.

### The installed program's first run in CI: 23 steps passed, then "a failed update puts the data back" failed
- **Symptom:** on Windows, with Python hidden and the network blocked, the installed program passed install, setup,
  register, permissions, attendance, signing with the bundled `cryptography`, backup/rehearsal/restore, restart and an
  update over the installed version; after a planted failure mid-update the data version file was gone, not 0.
  Earlier runs of the same job showed the data folder's rights shutting out the installing account (`icacls /T` with
  inheritance flags on existing files).
- **Cause:** putting the data back removed `data_version.json` when the old version was 0 (a falsy test on the
  number); the rights were applied file by file instead of on the folder.
- **Fix:** the old version is always written back (0 included), the Linux check requires the file; rights are set on
  the folder and its contents reset to inherit them.
- **Lesson:** "put back exactly" includes the small files; test 0 as a value, not as "nothing".

### A broken upload held the attendance screen for minutes on a PC without Excel
- **Symptom:** in Windows CI an upload of a file that is not a workbook timed out after 120 s; everything else waited
  behind the attendance lock (uploads, backups).
- **Cause:** the locked engine hands a workbook it cannot read (protected, damaged, or .xls/.xlsb) to Microsoft Excel
  through PowerShell and waits up to minutes for Excel; the CI machine, like many customer PCs, has no Excel.
- **Fix:** before the engine, when Excel is not installed, a file only Excel could open is refused at once with a
  plain message (`attendance.needs_excel`) and audited; ordinary workbooks and CSV reach the engine with the same bytes.
  The engine is unchanged. Two checks and a planted bug.
- **Lesson:** "do not assume Excel" (the owner's rule) is not only a notice: every path that would call it must know
  it is missing.

### A timed check let a planted bug through on Windows
- **Symptom:** in Windows CI the planted bug "the attendance history is copied during an upload" SURVIVED; on Linux it
  was caught.
- **Cause:** the check held the attendance lock and asserted the backup was still running after 0.5 s; on a slow disk
  the backup was still busy anyway, with or without the lock.
- **Fix:** the check watches which files the backup copies: after the journal files are copied, history.db must not be
  copied while the upload holds the lock, and must be in the finished backup.
- **Lesson:** a check that depends on timing measures the machine, not the rule; observe the order of events instead.

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
