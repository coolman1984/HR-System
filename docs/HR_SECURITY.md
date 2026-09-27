# HR-System — security and recovery (phase 2)

Date: 2026-09-27. Status: **built and passing its exit gate** (`TEST_HR_SECURITY.py`, 77 checks; 28 planted bugs
caught by `migration/mutations.py`). No new HR business module (shifts, skills, payroll) was started.

## 1. What exists now

| Capability | Where | What it does |
|---|---|---|
| Users and roles | `hr_core/auth.py` | Accounts and **profiles** (administrator, hr_officer, viewer, auditor + custom). PBKDF2-SHA256 600 000 rounds. 5 wrong passwords → 15 min lock. New users must change their password. Sessions end after 30 min idle / 12 h. The last administrator can never be disabled or reduced. |
| Fine-grained server-side permissions | `hr_core/service.py` `require()` | 12 `module.object.action` rights (`hr.employees.write`, `admin.backup.restore`, …). Checked on the **server** for every request and **recomputed every time** from the durable accounts, so a disabled account or a reduced profile takes effect on the next click. Every refusal is audited. |
| HTTP API | `hr_core/api.py`, `hr_server.py serve` | Cookie `hr_sid` (HttpOnly, SameSite=Strict, only a SHA-256 of the token is stored). Every mutation must be JSON (even with no body) and same-origin. 401 = sign in, 403 = no right, 409 = stale version. First administrator only from the server machine, only once. |
| Device identity | `hr_core/device.py` | Each installation has its own id and Ed25519 key (`data/node/device.key`, mode 0600, never in a backup). A data folder copied to another machine gets a **new** identity (clone detection), so two machines never sign as one. |
| Append-only, tamper-evident journal | `hr_core/journal.py` | One journal for every durable change (business data, accounts, devices): database triggers refuse UPDATE/DELETE; SHA-256 chain in the ecosystem format (ADR-026). The audit log is a second chain in the same file. |
| Signed journal entries | `hr_core/journal.py`, `hr_core/signing.py` | Every line carries the device's Ed25519 signature over its hash. After the first signed line, an unsigned line is a failure (a stripped or appended-without-key line is found). Phase-1 lines keep their original hashes. |
| Verified automatic backups | `hr_core/backup.py` | Online copies of `hr.db`, `auth.db` (sessions stripped), `hr_journal.db`, the public `device.json`, and a **signed manifest** (hash + size of each file, journal length and last hash, registry fingerprint). Verified after writing: hashes, `PRAGMA integrity_check`, manifest signature, full journal verification. Optional second local disk; network (UNC) paths refused; retention. Automatic on start and every N hours when something changed. |
| Automatic restore rehearsal | `Backups.rehearse` | After every automatic backup: copy to a temporary folder, open it as a real installation, check no new line was needed, compare the tables with the manifest, **rebuild the tables and the accounts from the journal and compare fingerprints**, verify journal and audit, delete the folder. Result audited and stored beside the backup (`rehearsal.json`). |
| Recycle Bin / compensating corrections | registry + service | Delete = soft delete (Recycle Bin, needs the version you saw); restore from the bin; codes never reused. A backup restore is **one new `restore` line** (history kept; the restore can itself be undone). Accounts are not restored (as in BAMS). |
| Security and activity audit | `journal.audit()` | Sign-in ok/failed/locked, logout, password change/reset, user and profile changes, every refusal of a right, every saved/deleted/restored/refused record, backups created/failed/rehearsed/restored, service start (with device, signing backend, clone and journal recovery). Hash-chained, append-only, never holds passwords or tokens. |

### Recovery rules (what happens when a file is lost)

| Lost or damaged | What happens | Proven by |
|---|---|---|
| `hr.db` (business tables) | Rebuilt from the journal on the next start, identical fingerprint | `lost_hr_db_rebuilt_identical` |
| Tables damaged in place | `registry.rebuild()` (`hr_registry.py rebuild`); the rehearsal of a backup taken from damaged tables fails | `damaged_tables_rebuilt_from_journal`, `rehearsal_detects_tables_that_differ_from_the_journal` |
| `auth.db` (accounts) | Rebuilt from the journal; passwords still work | `lost_auth_db_rebuilt_accounts_and_passwords` |
| `hr_journal.db` (permanent history) | On start, the newest backup whose journal verifies is put back; what the tables hold beyond it is recorded as ONE `recovery` line. History up to the backup is intact, nothing current is lost. Without any verified backup the server **refuses to start** instead of inventing a new history. | `lost_journal_restored_from_backup_with_recovery_line`, `missing_journal_without_backup_refuses_to_start` |

A store knows it is ahead of (or diverged from) a journal restored from a backup because it records the **hash** of
the last line it folded, not only its number.

## 2. Exit gate — result

| Gate (owner's wording) | Checks in `TEST_HR_SECURITY.py` |
|---|---|
| unauthorized operations are rejected server-side | `no_session_is_401`, `viewer_write_is_403`, `viewer_admin_areas_are_403`, `profile_change_applies_immediately`, `disabled_account_is_out_immediately`, `session_rechecks_account_on_every_request`, `cross_site_request_refused`, `non_json_mutation_refused`, `restore_needs_its_own_right`, `five_wrong_passwords_lock_the_account` |
| concurrent edits cannot silently overwrite | `stale_version_is_409`, `change_without_version_is_409`, `twelve_simultaneous_saves_exactly_one_wins`, `account_edits_are_versioned_too` |
| journal modification is detected | `edited_content_detected`, `stripped_signature_detected`, `stripped_signer_detected`, `deleted_line_detected`, `rehashed_history_detected_by_signature`, `signature_by_another_key_detected`, `appended_unsigned_line_detected`, `audit_modification_detected` |
| damaged materialized HR data can be rebuilt | `damaged_tables_rebuilt_from_journal`, `lost_hr_db_rebuilt_identical`, `lost_auth_db_rebuilt_accounts_and_passwords` |
| backup → restore → integrity comparison succeeds automatically | `automatic_backup_and_rehearsal_pass`, `damaged_backup_fails_verification_and_rehearsal`, `edited_manifest_fails_signature`, `backup_with_edited_journal_rejected`, `restore_is_one_compensating_line`, `restore_brings_back_the_backup_state` |
| loss of one database file does not destroy permanent history | `lost_journal_restored_from_backup_with_recovery_line`, `history_up_to_the_backup_survives_journal_loss`, `rehearsal_passes_after_recovery` |
| all previous HR and GMES integration tests remain green | the 4 original tests, equivalence (0 differences), publisher, registry; GMES `hr-e2e` against this commit |

## 3. Decisions

### ADR-HR-001 — The BAMS security model, re-implemented once for HR (not copied)
- **Decision.** HR takes BAMS's proven model: durable accounts and profiles folded from the signed journal; local-only
  sessions, counters and locks; rights checked on the server and recomputed per request; soft delete and
  compensating restore; verified backups with a restore test; device identity with clone detection. The code is
  written for HR (BAMS's `store.py` and `server.py` are shaped around its own tables), except the signing
  algorithm (ADR-HR-002).
- **Rejected.** (a) Copying BAMS's `server.py`/`store.py` and adapting them — two diverging copies of the same
  security logic. (b) A shared library now — the second consumer (GMES) has not been built yet; extracting from one
  user fixes the wrong seams. The capability matrix in GMES `docs/ecosystem/08-infrastructure-foundation.md` keeps
  the extraction plan (F-steps). (c) Multi-master merge — HR has one server per company for now; BAMS's merge
  stays out (and never for manufacturing facts).
- **Consequence.** Signing, canonical hashing, backup verification and device identity are written behind small
  interfaces (`signing.py`, `canonical.py`, `Backups.verify`, `Device`) so they can move to one ecosystem
  foundation later without changing callers.

### ADR-HR-002 — Signing: the standard library first, BAMS's reviewed implementation as the only fallback
- **Question.** Can a well-established standard cryptography library be bundled completely inside the offline
  Windows installer with no setup burden for the customer?
- **Evidence (2026-09-27).** PyCA `cryptography` 50.0.1 ships one `abi3` wheel per Windows architecture
  (`win_amd64` 3.8 MB, `win32`, `win_arm64`) — version-independent. But it imports `_cffi_backend`, which is **not**
  abi3: one compiled `cffi` build per Python minor version × architecture. HR today runs on the customer's own
  Python (whatever `RUN_PROJECT.ps1` finds, 3.10+ including Anaconda), so bundling means ~15 builds and a runtime
  choice among them. In this sandbox a system `cryptography` 41 with a missing `cffi` did not raise `ImportError`:
  it crashed with a Rust `PanicException` (a `BaseException`) — a broken install must be survivable.
- **Answer.** **Yes with an embedded Python runtime** (as BAMS ships): one `cryptography` + one `cffi` per
  architecture, no customer setup. **No with the current "use the customer's Python"** delivery.
- **Decision.** `hr_core/signing.py` uses `cryptography` whenever it imports **and** reproduces the RFC 8032 test
  vector; otherwise BAMS's `ed25519.py`, vendored **byte-for-byte** (`hr_core/vendor/`, SHA-256 pinned by a test).
  Any failure while loading, including a panic, is recorded in `signing.PROBLEMS` and shown by `/api/admin/health`.
  When the installer moves to an embedded runtime, it bundles `cryptography` and the fallback simply stops being
  used. Ed25519 is deterministic, so both produce identical signatures and a journal written by one verifies under
  the other.
- **Conditions the owner set for reusing BAMS's code — all met.** Reviewed (vendor README: RFC 8032 §5.1,
  cofactorless verify, rejects `s ≥ q` and non-canonical points, not constant-time — outside the LAN threat model);
  RFC 8032 vectors preserved (tests 1–3, the same ones BAMS's suite holds); cross-checked with **two independent
  implementations**: `cryptography` (40 key/message pairs byte-identical, both directions, and journals written by
  one verify under the other) and the **OpenSSL command line**; mutation tests (a one-byte edit to the file, a
  skipped signature check, an unsigned line accepted — all caught); this ADR.
- **Never.** Two independently modified copies of a security algorithm. A fix goes to BAMS (its owner), then is
  copied here unchanged with the pinned hash updated; long term the file moves to the shared ecosystem foundation.
- **CI.** Every job runs whatever backend is present (normally the fallback); a separate job installs
  `cryptography`, requires the cross-check (`HR_REQUIRE_CROSSCHECK=1`) and runs the suite once more forced to the
  fallback (`HR_SIGNING_BACKEND=bams`).

### ADR-HR-003 — Recovery never rewrites history
- **Decision.** Tables and accounts are folds of the journal and can always be thrown away and rebuilt. The journal
  is never restored backwards over newer history: a restore from a backup is a new `restore` line; a lost journal
  is replaced by the newest *verified* backup's journal and the difference is recorded as a new `recovery` line.
  Starting with no journal while tables exist is refused unless a person explicitly allows it
  (`allow_new_journal=True`).
- **Rejected.** Copying the backup over the live data (BAMS forbids it too: it silently erases work done after the
  backup and makes the journal disagree with the tables); starting a fresh empty journal (the history would end
  silently).

## 4. Threat model and limits (said plainly)
- The server listens on `127.0.0.1` by default. On a LAN it must be started with `--host` on a trusted network:
  there is **no TLS yet** (BAMS pins its own certificate; HR will take the same pattern when HR has LAN clients).
- Someone with the device key and write access to the data folder can write validly signed lines: signatures prove
  *which installation* wrote a line and detect edits by anyone else, not a fully compromised server. Backups on a
  second disk keep an independent copy of history.
- The pure-Python fallback is not constant-time; acceptable for a local server signing its own journal, and it
  disappears once the installer bundles `cryptography`.
