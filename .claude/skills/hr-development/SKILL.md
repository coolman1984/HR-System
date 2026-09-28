---
name: hr-development
description: Working knowledge for HR-System, the ecosystem's owner of people - the file map, how the locked attendance engine and the hr_core kernel fit together, invariants, how to test and prove a change, how to add a module or a contract, and the pitfalls learned so far. Load it before changing anything in this repository, and update it whenever something new is learned.
---

# HR-System — how it works and how to change it safely

`CLAUDE.md` is the rules. `AGENT_HANDOFF.md` and `STATUS.md` say where the work stands. This skill is the map.
The root `SKILL.md` describes only the migrated Excel attendance engine (it ships inside the customer ZIP).

## One product, two layers inside it
```
 Browser ─► HR-System.exe (hr_main.py) ─► one ThreadingHTTPServer (hr_core/app.py Product)
             │ screens hr_core/web/ (EN/AR)        │ /api/...  HR API (hr_core/api.py → service.require → audit)
             │ /attendance + the engine's 9 addresses ─► locked engine.py / calculation_engine.py (its own handler)
             ▼
 %ProgramData%\HR-System (HR_HOME in tests):  config.json · data\ (hr_journal.db, hr.db, auth.db, history.db, node\)
                                              backups\ (keep-* kept forever) · recovery\known-good · logs\
```
Startup order (hr_core/app.py): recover a lost history.db → `upgrade.prepare` (pre-update backup, steps, put back on
failure, resume after power cut) → bind the engine → verify journal and audit → promote the recovery installer →
automatic backups. Until the company is set, the server runs in setup mode (hr_core/web.py).
The eco publisher is compiled in but not started by the product yet; phase 4 binds attendance to the registry.

## File map
| Path | Role | Change rule |
|---|---|---|
| `engine.py`, `calculation_engine.py`, `dashboard.html`, `PROJECT.json` | Migrated attendance application | Locked; behaviour pinned by `TEST_MIGRATION_EQUIVALENCE.py`. Changing it needs a PROJECT_LOG decision and `core_change` |
| `hr_core/registry.py` | Organisation, jobs, positions, employees; versions, soft delete, rebuild | Every write is a journal line |
| `hr_core/importer.py` | Data-dictionary workbooks → registry; re-import writes nothing | Absence is never deletion |
| `hr_core/journal.py`, `hr_core/canonical.py`, `hr_core/signing.py` | Hash-chained signed journal and audit; ecosystem canonical hashing | Append-only (triggers refuse UPDATE/DELETE) |
| `hr_core/auth.py` | Accounts, profiles, the 12 permissions, sessions, lockout | Folded from the journal; last administrator protected |
| `hr_core/service.py` | The only entrance: `require()` + audit + versions; startup recovery | New entrances go through it |
| `hr_core/api.py`, `hr_server.py` | JSON HTTP API and admin commands | Same-origin JSON mutations only |
| `hr_core/device.py`, `hr_core/backup.py` | Device identity, verified backups, rehearsal, restore | Restore = compensating line |
| `hr_core/modules.py` | Modules and editions (`built` / `planned` / `design_only`) | Change a status only with the code and `STATUS.md` |
| `hr_main.py`, `hr_core/app.py` | The product's one entry point and startup order | One server only; `tool <command>` for maintenance |
| `hr_core/home.py`, `hr_core/version.py` | Installation home, settings, company identity; product and data versions | The company id is set once (ADR-HR-006) |
| `hr_core/upgrade.py` | Data-version steps, pre-update backup, put back, resume; recovery installer | A new data shape = a new step + a planted bug |
| `hr_core/attendance.py` | The engine behind the sign-in, its rights, Excel detection | Never edit the engine to change this |
| `hr_core/web.py`, `hr_core/web/` | Screens: one application shell (`app.js`, `hr.css`) built from the ecosystem kit `hr_core/web/eco-ui/` (unchanged copy of GMES `packages/eco-ui/src`, pinned in `hr_core/eco_ui_pin.json`), `hr_core/web/i18n/en.json` + `hr_core/web/i18n/ar.json`, setup mode | Every text through `t()`; both dictionaries, same keys; never edit `eco-ui/` here |
| `tools/build_windows.py`, `tools/make_assets.py`, `tools/make_icon.py`, `installer/hr-system.iss` | The Windows installer | CI job `windows-installer` must stay green |
| `tools/installed_acceptance.py` | Acceptance of the installed program (Windows) | Python hidden, network blocked |
| `hr_core/vendor/` | BAMS Ed25519, byte-for-byte, hash-pinned | Never edited here |
| `eco_publisher.py`, `eco_contract.py`, `eco_schemas/` | Contracts to GMES; schemas generated in GMES | Schemas copied unchanged |
| `migration/` | Golden behaviour and planted bugs (`migration/mutations.py`) | A new rule = a new planted bug |
| `TEST_*.py` | Suites (list in `STATUS.md`); `TEST_DOCS_CURRENT.py` guards the documents | Every test runs in CI |

## Recipes
- **New HR module (e.g. shifts):** design section in `docs/HR_SYSTEM_DESIGN.md` → entities in `hr_core/` beside the
  registry, written through the journal → permissions in `hr_core/auth.py` → service methods with `require()` → API
  routes → tests + planted bugs → status `built` in `hr_core/modules.py` → `STATUS.md` (labels and inventory),
  `AGENT_HANDOFF.md`, `HISTORY.md`, `docs/LESSONS.md`.
- **A new screen or text:** add the key to `hr_core/web/i18n/en.json` AND `hr_core/web/i18n/ar.json` (TEST_HR_DELIVERY checks both);
  write server values with `textContent` only; look at it in a real browser (screenshots) in both languages.
- **The data changes shape:** raise `DATA_VERSION` in `hr_core/version.py`, add the step to `MIGRATIONS` in
  `hr_core/upgrade.py` (check what is already done first; write journal lines as actor `upgrade`), test failure and
  power cut, add a planted bug.
- **New or changed contract:** in `GMES/packages/eco-contracts` first (additive = same version, breaking = new `vN`),
  regenerate there, copy into `eco_schemas/`, extend `eco_publisher.py`, re-pin GMES and pass its HR end-to-end test.
- **A document check fails:** read the message, find what changed, describe it in the documents, then update the
  inventory block. Never paste the expected value without the description.

## Pitfalls
- `TEST_HR_FOUNDATION.py` rewrites a tracked sample: `git checkout -- sample/` afterwards.
- The original tests need `PYTHONPATH=vendor.zip` for `openpyxl`.
- A broken `cryptography` can panic with a `BaseException`; `hr_core/signing.py` handles it — keep that.
- The product is the Windows installer; the old ZIP (`BUILD_PROJECT.py`) is only the engine's rollback line.
- The engine binds to one data folder per process (on first import): tests that need two folders use subprocesses.
- The engine keeps `history.db` open: copy it with the SQLite backup API under the attendance lock, never as a file.
- More: `docs/LESSONS.md`.
