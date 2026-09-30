# LESSONS — what HR-System learned the hard way

Short, durable rules. Each one comes from a real event in `HISTORY.md`, from the ecosystem (GMES, BAMS, 3D-Modeling)
or from the owner. Add a line when something surprises you; never delete one, strike it through with the reason.

## Truth and ownership
- **L1** One fact, one owner. HR owns people, organisation, employment, shifts, attendance, leave, overtime, skills and
  (later) pay calculation. Other applications keep read-only mirrors; a mirror never becomes a master.
- **L2** Mizan books payroll entries and never stores employees or computes pay. A neighbour's stale plan can recreate
  a second truth (Mizan's roadmap line, `HISTORY.md` 2026-09-27).
- **L3** Never write into another application's database and never accept employee records from one. Contracts only,
  generated in `GMES/packages/eco-contracts`, copied into `eco_schemas/` unchanged.

## History and recovery
- **L4** The journal is the truth; tables and accounts are folds of it and can always be rebuilt.
- **L5** Recovery never rewrites history: a restore is a new line, a lost journal comes back from a verified backup
  plus one `recovery` line. Starting over with an empty journal is refused.
- **L6** Position is not identity: compare the hash of the last applied line, not its number.
- **L7** Never back up through the connection that writes (it hung).

## Tests
- **L8** A green suite proves nothing until it has been made to fail: every rule gets a planted bug in
  `migration/mutations.py` (two survived the first phase-2 run).
- **L9** "Re-import writes nothing" is a test, not a belief: SQLite `TEXT` columns turned `1` into `'1'`.
- **L10** Run a migrated suite on a clean machine: the original tests needed `PYTHONPATH=vendor.zip`.
- **L11** `TEST_HR_FOUNDATION.py` rewrites `sample/HR_Attendance_Delta_Demo.xlsx`: run `git checkout -- sample/` after it.
- **L12** Top-level `.py` files are standard library only, tests included (`CHECK_ENVIRONMENT.py` scans them all).
- **L24** A green CI badge is read on the pull request, not assumed: HR's CI was red on every run for a whole day.
- **L25** One SQLite connection shared by server threads: every statement under the lock, rows read before release
  (`SharedConnection`); an intermittent 500 was a race, found by recording the file and line in the audit.
- **L26** Hash-pinned files need byte-identical checkouts: `.gitattributes` `* -text` (Windows CRLF broke the pin).

- **L27** Look at the screens in a real browser before calling them done (white-on-white buttons passed every API test).
- **L34** A check that depends on timing measures the machine, not the rule: observe the order of events (a planted
  bug survived only on a slow Windows disk).
- **L28** A fixture or repair that writes tables without a journal line is corruption; the rehearsal refuses it, rightly.

## Delivery (phase 2.5)
- **L29** Built and tested is not delivered: every feature must land in the program a customer installs, and CI
  must accept the INSTALLED program, with Python hidden and the network blocked.
- **L30** Program and data apart: updating or removing the program never touches `%ProgramData%\HR-System`.
- **L31** Before data changes shape: a verified, rehearsed backup kept forever; steps that check what is done; put
  back only when nobody but the update wrote since the backup.
- **L32** The company id is everyone's namespace: it comes from its owner, and a registry refuses another one.
- **L33** Values in signed canonical documents must fit their rules (integers up to 2^53: nanoseconds do not).
- **L35** Review screens by using them in a real browser, not only by looking at screenshots.
- **L36** Build screens from one kit (shell, standard screen, grid, dialog); a screen styled on its own is a bug.
- **L37** A shared file has one home: the interface kit is changed in GMES and copied here with a pinned hash.
- **L38** Effective dating is a rule on writes: what has started only ends; the past is never re-planned.
- **L39** Anything stored with a backup (a fingerprint) is extended only additively, or older backups stop rehearsing.
- **L40** Money waits for its inputs: payroll is built only when attendance, leave and overtime are bound to the employee.

## Dependencies
- **L13** Probe an optional native library by what it does, not by whether it imports: a broken `cryptography`
  panicked with a `BaseException`.
- **L14** Two modified copies of a security algorithm are never allowed; BAMS's signing file is vendored byte-for-byte
  and hash-pinned.

## Migration and behaviour
- **L15** During a migration, preserve and record odd behaviour; fix it later by decision, behind a test that first
  reproduces it (the re-upload quirk is still pinned).
- **L16** The engine is locked (`LOCKED_CORE.json`); new work goes beside it in `hr_core/`, never inside it.

## Documentation and handoff
- **L17** A document nobody is forced to update will say the opposite of the code: `TEST_DOCS_CURRENT.py` keeps
  `STATUS.md` and `AGENT_HANDOFF.md` tied to the code.
- **L18** "Built and tested" is not "delivered": the customer ZIP still ships only the attendance application.
- **L19** Keep history, mark it: an outdated document gets a HISTORICAL banner, not a deletion.
- **L20** End every long session by updating `STATUS.md`, `AGENT_HANDOFF.md`, `HISTORY.md` and this file before
  pushing; the next session has no chat, only files.

## Look and shared kit
- **L41** A good idea from a neighbour enters the shared kit (GMES `packages/eco-ui`) once, then every product copies
  it; never restyle one product alone (HISTORY 2026-09-28, Mizan's look). A new look is opt-in per product.
- **L42** A tool that restores a file must restore the same bytes: on Windows `Path.write_text` turns LF into CRLF and
  silently "changes" hash-pinned files (HISTORY 2026-09-28, planted-bug run).
- **L43** A pin describes a tree of files (relative paths), not a flat directory listing.

## From the ecosystem (apply when the time comes)
- **L21** Production quantities are never merged from several writers (GMES ADR-015). BAMS's multi-master merge is a
  reference for editable master data only.
- **L22** A consumer that loses HR keeps working on its last-known-good mirror and shows its age; it does not stop the
  factory (phase 3 contract).
- **L23** Extract a shared library only when two real applications use it.

## 2026-09-28 — screens, demo data, separate duties
- A test suite that never runs the screens says nothing about them: open every changed screen in a real browser (CDP,
  headless or visible) and read its console before calling it done; check `app.js` as a module (`.mjs` copy).
- Demo data is made by the product's own operations (importer, service, engine over HTTP, backups), each by the person
  who would do it, with the rules' clock moved only where history must be written on its own date. Then every figure a
  client sees is one the product really produces.
- Separate duties are separate checks chosen by what a request does (propose vs decide), not by the table it writes.
- Measure what is drawn (padding, icons, the column's font) when sizing columns; keep what the person chose.

## 2026-09-28 — Phase A: the product publishes to GMES
- **L44** A secret is never a setting: settings are copied, shown, audited and backed up. Keep it beside `device.key`
  (outside every backup), protected by the operating system (DPAPI on Windows), and let the API say only whether one is set.
- **L45** "Read-only" is a property of the connection (`mode=ro`), not of the code that promises not to write; a second
  opener of the registry would open the journal and may repair on open.
- **L46** When the server acts after it has answered (the attendance audit line), a test waits for the effect.
- **L47** After an interrupted `migration/mutations.py` run, `git diff` before committing: a planted bug left in a file
  looks like an ordinary change (one was committed in `0ba58a3`).
- **L48** A four-eyes rule (the author never approves) is tested with a person who holds the approve right and is the author; a plain viewer is refused by the right first and proves nothing (six planted bugs survived until then, `HISTORY.md` 2026-09-30).
- **L49** A planted bug that survives is either a missing test or a change that alters nothing; find out which before adding a check.
- **L50** Guards that read code with a regular expression stop guarding when the code style changes; read it with `ast` (the route inventory missed raw strings and `ENTITY_ROUTE`).
