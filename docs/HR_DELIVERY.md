# HR-System — one installable product (phase 2.5)

Date: 2026-09-27. Status: **built and tested on Linux; the installed program is accepted on Windows by the CI job
`windows-installer`** (`tools/installed_acceptance.py`). A test on a truly clean PC (no Python ever installed) is
still owed: `installer/clean-pc-test.wsb` runs it in Windows Sandbox (see §5).

Why this phase exists: phases 1 and 2 were built and tested but never delivered. The customer ZIP carried only the
attendance application, so a customer who installed HR got none of the registry, accounts, signed journal or
backups (HISTORY.md, 2026-09-27).

## 1. What a customer gets

| | |
|---|---|
| One file | `HR-System-Setup-<version>.exe`: installs on a new PC, updates an installed one (same file) |
| Program | `C:\Program Files\HR-System\HR-System.exe`: compiled (Nuitka), its own Python runtime, openpyxl and `cryptography` inside; no readable program source (the one exception is `CUSTOM_RULES.py`, the attendance engine's documented customisation hook) |
| Data | `%ProgramData%\HR-System\`: `config.json`, `data\` (journal, tables, accounts, attendance history, device identity, the protected GMES key, the outbox to GMES), `backups\`, `recovery\`, `logs\`. Kept on update and on removal. Readable only by SYSTEM, the Administrators and the account that installed and runs the server (not by other users of the PC) |
| Start | Start menu and optional desktop icon; "start with Windows" (for the installing person, who runs the server) is offered and ticked by default, and can be switched off in Settings |
| Entry | One address, one sign-in: `http://127.0.0.1:8766/` — employees and organisation, attendance, users and permissions, backups, system health, settings (including the link to GMES, off until an address is set) |
| Old attendance program | On a first install the installer offers to COPY the old program's `data\history.db` (the old folder stays as it was) |
| Microsoft Excel | Not assumed: the installer and the health screen say whether it is there; only protected, damaged or old-format (.xls/.xlsb) workbooks need it, and without Excel such a file is refused at once with a plain message instead of waiting for Excel |
| Languages | English and Arabic screens (right-to-left); the attendance dashboard itself stays English (locked engine) |

## 2. Decisions

### ADR-HR-004 — Delivery: one compiled Windows installer, program and data apart (the BAMS way)
- **Decision.** Nuitka compiles `hr_main.py` and everything it imports into `HR-System.exe` with its own runtime
  (`tools/build_windows.py`); Inno Setup wraps it (`installer/hr-system.iss`). Program in Program Files, data in
  `%ProgramData%\HR-System`. The screens are packed inside the program at build time (`tools/make_assets.py`).
  CI builds the installer on every pull request and accepts the installed program on Windows.
  The data folder does not inherit ProgramData's "every user may change" rights: SYSTEM, Administrators and the
  installing account only (it holds the journal, password hashes and the device key). A Windows service under its
  own account is the next step if several people must run the server on one PC.
- **Why.** The customer installs nothing (ADR-HR-002's condition for bundling `cryptography` is met: one runtime,
  one build), the data survives updates and removal, and nobody edits the program by editing files.
- **Rejected.** (a) The old ZIP + "use the customer's Python": `cryptography`/`cffi` would need a build per Python
  version, and every PC is different. (b) An embedded CPython folder with readable `.py` files (BAMS's portable
  version): simpler, but the program could be edited in place. (c) MSI: more tooling, no gain for one server PC.
- **Kept.** `BUILD_PROJECT.py` still builds the old attendance ZIP: it is the rollback line for the engine, not the
  product.

### ADR-HR-005 — One server, one sign-in; the attendance engine stays locked behind it
- **Decision.** The HR-System server is the only entrance. The locked engine answers its own addresses through its
  own request handler, called by the HR server after the session and the right (`hr.attendance.read` /
  `hr.attendance.upload`) were checked; its page is served at `/attendance`. No engine file changed.
- **Evidence.** None of the engine's nine addresses collides with the HR API (`TEST_HR_DELIVERY.py`
  `no_attendance_address_collides_with_the_hr_api`), and an upload through the one server gives the golden numbers
  (`attendance_through_the_one_server_gives_the_golden_numbers`, `attendance_rows_are_the_golden_rows`).
- **Rejected.** Two servers on two ports (two sign-ins, two things to start and secure); rewriting the engine's
  screens now (the equivalence test is the rollback line).
- **Consequences.** The engine keeps `history.db` open while it runs (seen in CI on Windows), so backups copy it
  with the SQLite backup API while the attendance lock is held; a lost `history.db` comes back from the newest
  verified backup. Uploads and roll-backs are audited with the person's name.

### ADR-HR-006 — The company identity has one owner and never changes silently
- **Decision.** The company id is the namespace of every shared id (GMES identity map E4.2), so:
  * if the company already uses Mizan, HR takes Mizan's company id at setup (`source: owner`);
  * a standalone HR creates a local UUIDv7, marked **provisional** (`source: local`);
  * it is written once; a registry built for one company refuses to open under another
    (`company.mismatch`), so editing `config.json` stops the program with a message instead of giving every
    employee a new identity in every other application;
  * adopting an owner's identity later is an explicit, planned step (an adoption and matching wizard), never an edit.
- **Rejected.** HR always inventing its own id (two truths for "which company"); letting the id be edited.

### ADR-HR-007 — Data versions: backup first, step by step, put back on failure, resume after a power cut
- **Decision.** `hr_core/upgrade.py` runs before the server accepts a request:
  * data from a newer program is refused;
  * older data gets a verified and rehearsed pre-update backup (`keep-…`, never removed by retention), then each
    step runs as journal lines by the actor `upgrade`, and `data_version.json` is written after each step;
  * a failing step puts the data files back from that backup and the program shows the message — the one place
    files are copied back, allowed only after checking that every journal line since the backup was written by
    the update itself;
  * a power cut leaves `upgrade-in-progress.json`; the next start continues from the last finished step (steps
    check what is done first, so nothing is applied twice).
- **Recovery installer.** The installer leaves a copy of itself in `recovery\pending` with its version and SHA-256;
  the program promotes it to `recovery\known-good` only after this version started and verified its journal and
  audit. Only one is kept; a pending copy of another version or with a wrong hash is discarded.
- **Rejected.** Migrating on install (the installer cannot verify the journal); keeping every old installer.

### ADR-HR-008 — The installed product publishes to GMES by itself, set on a screen (ecosystem plan, Phase A)
- **Decision.** Settings → *Integration (GMES)* (`SYS9060`, administrators with `admin.settings.manage`) sets the section
  `eco` of `config.json`:

  | Setting | Default | Rule |
  |---|---|---|
  | `gmes_url` | empty | empty = the link is off and HR works on its own; otherwise `http://` or `https://` with a host, no user or password, no query |
  | `node` | `hr-main` | 1-40 letters, digits, dot, dash, underscore; the sender `eco://<company>/hr/<node>` |
  | `interval_seconds` | 60 | 10 to 3600 |

  `hr_core/eco_link.py` runs `eco_publisher.py`'s outbox and delivery in a background thread: started by
  `Product.open()` when an address is set, stopped by `Product.close()`, restarted when the settings change; "Send now"
  runs one cycle at once. Each cycle opens its own connections in its own thread: the outbox, and the registry
  **read-only** (`hr.db` with `mode=ro`; opening `Registry` would open the journal and may repair on open). The screen
  shows the last delivery, the last attempt and what is pending, delivered and refused; a cycle that did or failed
  something is one line in `logs\eco-link.log`. Maintenance commands (`HR-System.exe tool ...`) never publish.
- **The GMES key is a secret, not a setting.** It is kept in `data\node\gmes.key` beside `device.key`: protected with the
  Windows Data Protection API (DPAPI, machine scope, so a copy of the folder on another PC cannot read it; the key is
  then shown as "cannot be read on this computer, enter it again"), and as a plain owner-only file (mode 0600) on other
  systems. Backups copy named databases and the public `device.json` only, so the key never lands in a backup; the API
  answers `key_set` (true/false), never the key; the audit records `key: changed | removed | unchanged`. The key field on
  the screen is write-only: leaving it empty keeps the stored key.
- **Routes.** `GET /api/admin/integration` (settings, `key_set`, `running`, last report, outbox counts),
  `PUT /api/admin/integration` (`gmes_url`, `node`, `interval_seconds`, optional `key`, optional `clear_key`; everything is
  checked before anything is written; audited as `integration.changed`), `POST /api/admin/integration/run` (one cycle
  now, returns its report; audited as `integration.sent`). All need `admin.settings.manage`.
- **Kept.** `python eco_publisher.py --once | --loop N` with `ECO_COMPANY_ID`, `ECO_GMES_URL`, `ECO_GMES_KEY`,
  `ECO_NODE`, `EXCEL_APP_DATA_DIR` works unchanged (a manual second way; do not run both against one outbox at once).
- **Rejected.** The key in `config.json` (it would travel with every copy of the settings); returning a masked key
  (nothing to gain, one more thing to leak); a second process or a Windows service for publishing (one program to
  start and to secure).

## 3. Tests
| What | Where |
|---|---|
| Product logic (any OS): setup, identity, one server, attendance equivalence, permissions, backups with the attendance history, lost history, update, failure, power cut, recovery installer, start with Windows, languages, the link to GMES (off by default, started on open, delivery into a fake GMES inbox, GMES down then back, the key never in the API, `config.json`, a backup, a log or the audit, validation, rights) | `TEST_HR_DELIVERY.py` (96 checks) and its planted bugs in `migration/mutations.py` |
| The installed program on Windows: no Python visible, outbound network blocked, install with the old attendance history, first administrator, register, permissions, attendance, backup/rehearsal/restore, restart, update over the installed version, failure and power cut in the middle of an update, removal keeps the data | `tools/installed_acceptance.py` in the CI job `windows-installer` |

## 4. Limits, said plainly
- The CI Windows machine has Python installed; the program is started with Python hidden from it, which proves it
  does not use it, but it is not a machine that never had Python. §5 is the clean-PC test.
- "Restart" in CI is the program killed and started again, which is what a power cut does to it; a real reboot of
  the PC is part of §5.
- The unknown-publisher warning of Windows remains until the installer is signed with a code-signing certificate
  (acceptable for trials only; needed before selling).
- Adopting Mizan's company id after a standalone start is planned, not built.
- LAN use (other PCs opening the server) still needs TLS (docs/HR_SECURITY.md §4); the server listens on this PC only.

## 5. Clean-PC test (owner, once per release)
Windows Sandbox is a fresh Windows with no Python and, with `installer/clean-pc-test.wsb`, no network. Put the
installer in `dist\`, double-click the `.wsb` file, then in the sandbox: install, set up, sign in, add an employee,
upload `sample\HR_Time_Attendance_Demo.xlsx`, make a backup, restart the sandbox's program, and check that nothing was lost.
