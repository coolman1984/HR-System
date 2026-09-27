---
name: hr-development
description: Working knowledge for HR-System, the ecosystem's owner of people - the file map, how the locked attendance engine and the hr_core kernel fit together, invariants, how to test and prove a change, how to add a module or a contract, and the pitfalls learned so far. Load it before changing anything in this repository, and update it whenever something new is learned.
---

# HR-System — how it works and how to change it safely

`CLAUDE.md` is the rules. `AGENT_HANDOFF.md` and `STATUS.md` say where the work stands. This skill is the map.
The root `SKILL.md` describes only the migrated Excel attendance engine (it ships inside the customer ZIP).

## Two layers, side by side
```
 Excel uploads ─► engine.py + calculation_engine.py + dashboard.html   (LOCKED: LOCKED_CORE.json, PROJECT.json)
                  data/history.db        START.bat, port chosen at start ─ the customer ZIP (BUILD_PROJECT.py)
                          │ engine.current_rows()  (read only)
                          ▼
 hr_core/ (kernel)  registry ── journal (signed, append-only) ── auth ── service.require() ── api ── hr_server.py
                    data/hr.db  data/hr_journal.db  data/auth.db  data/node/ (device key, never backed up)
                          │
                    eco_publisher.py ─► data/eco_outbox.db ─► GMES /eco/v1/inbox   (off without ECO_GMES_URL)
```
The layers never write into each other. Phase 4 binds attendance to the registry; until then attendance is enriched
from the uploaded employee file.

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
| `hr_core/vendor/` | BAMS Ed25519, byte-for-byte, hash-pinned | Never edited here |
| `eco_publisher.py`, `eco_contract.py`, `eco_schemas/` | Contracts to GMES; schemas generated in GMES | Schemas copied unchanged |
| `migration/` | Golden behaviour and planted bugs (`migration/mutations.py`) | A new rule = a new planted bug |
| `TEST_*.py` | Suites (list in `STATUS.md`); `TEST_DOCS_CURRENT.py` guards the documents | Every test runs in CI |

## Recipes
- **New HR module (e.g. shifts):** design section in `docs/HR_SYSTEM_DESIGN.md` → entities in `hr_core/` beside the
  registry, written through the journal → permissions in `hr_core/auth.py` → service methods with `require()` → API
  routes → tests + planted bugs → status `built` in `hr_core/modules.py` → `STATUS.md` (labels and inventory),
  `AGENT_HANDOFF.md`, `HISTORY.md`, `docs/LESSONS.md`.
- **New or changed contract:** in `GMES/packages/eco-contracts` first (additive = same version, breaking = new `vN`),
  regenerate there, copy into `eco_schemas/`, extend `eco_publisher.py`, re-pin GMES and pass its HR end-to-end test.
- **A document check fails:** read the message, find what changed, describe it in the documents, then update the
  inventory block. Never paste the expected value without the description.

## Pitfalls
- `TEST_HR_FOUNDATION.py` rewrites a tracked sample: `git checkout -- sample/` afterwards.
- The original tests need `PYTHONPATH=vendor.zip` for `openpyxl`.
- A broken `cryptography` can panic with a `BaseException`; `hr_core/signing.py` handles it — keep that.
- The customer ZIP has an explicit file list; new files are not delivered until listed (and the owner decides the
  installer shape).
- The HR server has no screens yet; the attendance dashboard is a different program on a different port.
- More: `docs/LESSONS.md`.
