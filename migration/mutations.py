"""Plant realistic bugs and require a test to FAIL for each (a green test proves nothing until it
has been made to fail). Restores every file in a finally block. Standard library only.

    python migration/mutations.py
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTATIONS = [
    ("a resend rebuilds the envelope with a fresh id", "eco_publisher.py",
     "events = [json.loads(e) for _, _, e in batch]", "events = [dict(json.loads(e), id=str(uuid.uuid4())) for _, _, e in batch]", "TEST_ECO_PUBLISHER.py"),
    ("employees invented from attendance alone", "eco_publisher.py",
     "if emp and status:", "if emp:\n            status = status or 'Active'\n        if emp and status:", "TEST_ECO_PUBLISHER.py"),
    ("versions may go down", "eco_publisher.py",
     "version = max((row[1] if row else 0) + 1, int(time.time() * 1000))", "version = 1", "TEST_ECO_PUBLISHER.py"),
    ("minutes rounded silently", "eco_publisher.py",
     "if float(minutes).is_integer() and minutes >= 0:", "if minutes >= 0:", "TEST_ECO_PUBLISHER.py"),
    ("a KPI of the original application changes", "PROJECT.json",
     '"Employees observed"', '"Employees seen"', "TEST_MIGRATION_EQUIVALENCE.py"),
    ("absence is no longer explicit-only", "PROJECT.json",
     '"Absent"', '"Leave"', "TEST_MIGRATION_EQUIVALENCE.py"),
    ("registry columns get TEXT affinity (1 becomes '1')", "hr_core/registry.py",
     'cols = ", ".join(f for f in fields if f not in ("code",))', 'cols = ", ".join(f"{f} TEXT" for f in fields if f not in ("code",))', "TEST_HR_REGISTRY.py"),
    ("a stale version overwrites a newer one", "hr_core/registry.py",
     'if op.get("expected_ver") is not None and (not cur or cur["ver"] != op["expected_ver"]):', 'if False:', "TEST_HR_REGISTRY.py"),
    ("a crash after the commit point is not repaired", "hr_core/registry.py",
     'done, last = self.applied_seq(), self.journal.last_seq()', 'return\n            done, last = self.applied_seq(), self.journal.last_seq()', "TEST_HR_REGISTRY.py"),
    ("summary rows are imported as entities", "hr_core/importer.py",
     "elif not KEY.match(code):", "elif False:", "TEST_HR_REGISTRY.py"),
    ("the publisher ignores the registry", "eco_publisher.py",
     'if registry is not None and registry.list("employee"):', 'if False:', "TEST_HR_REGISTRY.py"),
    # phase 2: security and recovery (TEST_HR_SECURITY.py)
    ("journal signatures are not checked", "hr_core/journal.py",
     'if not r["sig"] or not signing.verify(pub, bytes.fromhex(r["hash"]), bytes.fromhex(r["sig"])):', 'if not r["sig"]:', "TEST_HR_SECURITY.py"),
    ("an unsigned line after signing began is accepted", "hr_core/journal.py",
     'elif signed_from is not None:', 'elif False:', "TEST_HR_SECURITY.py"),
    ("the server-side permission check is skipped", "hr_core/service.py",
     'if perm != "self" and perm not in self.auth.permissions(user):', 'if False:', "TEST_HR_SECURITY.py"),
    ("a disabled account keeps its open session", "hr_core/auth.py",
     'if s["last_seen"] < idle or s["created_at"] < oldest or not user or user["deleted"] or not user["active"]:', 'if s["last_seen"] < idle or s["created_at"] < oldest:', "TEST_HR_SECURITY.py"),
    ("a change without a version overwrites blindly", "hr_core/service.py",
     'if cur and expected_ver is None:', 'if False:', "TEST_HR_SECURITY.py"),
    ("account versions are not checked", "hr_core/auth.py",
     'if op.get("expected_ver") is not None and (not cur or cur["ver"] != op["expected_ver"]):', 'if False:', "TEST_HR_SECURITY.py"),
    ("wrong passwords never lock the account", "hr_core/auth.py",
     'if count >= MAX_FAILED else None', 'if False else None', "TEST_HR_SECURITY.py"),
    ("the last administrator can be disabled", "hr_core/auth.py",
     '                self._check_admin_remains()', '                pass', "TEST_HR_SECURITY.py"),
    ("cross-site requests are accepted", "hr_core/api.py",
     'if origin and urlparse(origin).netloc != self.headers.get("Host"):', 'if False:', "TEST_HR_SECURITY.py"),
    ("backup file hashes are not compared", "hr_core/backup.py",
     'elif _sha256(fp) != meta["sha256"] or os.path.getsize(fp) != meta["size"]:', 'elif False:', "TEST_HR_SECURITY.py"),
    ("the backup manifest signature is not checked", "hr_core/backup.py",
     'if pub is None or not sig or not signing.verify(pub, _manifest_digest(manifest), bytes.fromhex(sig)):', 'if False:', "TEST_HR_SECURITY.py"),
    ("the rehearsal does not compare the rebuild", "hr_core/backup.py",
     'checks["rebuilt_from_journal_identical"] = reg.fingerprint() == stored', 'checks["rebuilt_from_journal_identical"] = True', "TEST_HR_SECURITY.py"),
    ("a restore rolls history back instead of compensating", "hr_core/registry.py",
     'seq = self._append(actor, label, out, kind="restore")', 'self._wipe()\n            seq = self.journal.last_seq()', "TEST_HR_SECURITY.py"),
    ("a journal restored from a backup silently drops newer data", "hr_core/registry.py",
     'if not self.journal.follows(done, self.applied_hash()):', 'if False:', "TEST_HR_SECURITY.py"),
    ("a lost journal is replaced by an empty one", "hr_core/service.py",
     'restored_from = recover_lost_journal(data_dir, [backup_dir, *extra_backup_dirs])', 'restored_from, allow_new_journal = None, True', "TEST_HR_SECURITY.py"),
    ("the vendored BAMS signing file is edited", "hr_core/vendor/ed25519_bams.py",
     'def verify(pub, msg, sig):', 'def verify(pub, msg, sig):  # tidied', "TEST_HR_SECURITY.py"),
    ("the private device key is put into backups", "hr_core/backup.py",
     'files = {f: {"sha256"', 'shutil.copytree(os.path.join(self.data_dir, "node"), os.path.join(work, "node"))\n                files = {f: {"sha256"', "TEST_HR_SECURITY.py"),
    # stage 3.0: the continuity documents stay tied to the code (TEST_DOCS_CURRENT.py)
    ("a module is marked built without the documents", "hr_core/modules.py",
     '"shifts": {"depends_on": ["kernel"], "status": "planned"', '"shifts": {"depends_on": ["kernel"], "status": "built"', "TEST_DOCS_CURRENT.py"),
    ("a new kernel file appears without the documents", "hr_core/shifts.py",
     None, '"""Shift definitions (not documented yet)."""\n', "TEST_DOCS_CURRENT.py"),
    ("an HTTP route changes without the documents", "hr_core/api.py",
     '@route("GET", "/api/me")', '@route("GET", "/api/whoami")', "TEST_DOCS_CURRENT.py"),
    ("a test no longer runs in CI", ".github/workflows/ci.yml",
     "      - run: python TEST_HR_REGISTRY.py\n", "", "TEST_DOCS_CURRENT.py"),
    ("the handoff names another phase than the status", "AGENT_HANDOFF.md",
     "```handoff\nphase: 3", "```handoff\nphase: 4", "TEST_DOCS_CURRENT.py"),
    ("the design marks phase 3 done while the status does not", "docs/HR_SYSTEM_DESIGN.md",
     "| 3 | الورديات والجداول والتكليفات مستقلة", "| **3 (منفذة)** | الورديات والجداول والتكليفات مستقلة", "TEST_DOCS_CURRENT.py"),
    ("a history discovery loses its lesson", "HISTORY.md",
     "- **Lesson:** a document nobody", "- **Note:** a document nobody", "TEST_DOCS_CURRENT.py"),
    ("the status moves on without a history entry", "HISTORY.md",
     "## 2026-09-27 — Stage 3.0", "## 2026-09-26 — Stage 3.0", "TEST_DOCS_CURRENT.py"),
    ("the old attendance-only claim returns to the README", "README.md",
     "## ما يصل للعميل اليوم\n", "## ما يصل للعميل اليوم\n\nهذه النسخة هي أساس الحضور فقط.\n", "TEST_DOCS_CURRENT.py"),
    ("an outdated guide loses its historical banner", "PROJECT_GUIDE.md",
     "> **HISTORICAL (2026-09-05", "> **Note (2026-09-05", "TEST_DOCS_CURRENT.py"),
]

survived = 0
for name, rel, old, new, test in MUTATIONS:
    path = ROOT / rel
    if old is None:  # the planted bug is a new file
        if path.exists():
            sys.exit(f"mutation '{name}': {rel} already exists")
        original = None
        path.write_text(new, encoding="utf-8")
    else:
        original = path.read_text(encoding="utf-8")
        if old not in original:
            sys.exit(f"mutation '{name}': anchor not found in {rel}")
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
    try:
        env = dict(os.environ, PYTHONPATH=str(ROOT / "vendor.zip"))
        failed = subprocess.run([sys.executable, test], cwd=ROOT, env=env, capture_output=True).returncode != 0
    finally:
        if original is None:
            path.unlink()
        else:
            path.write_text(original, encoding="utf-8")
    print(("caught    " if failed else "SURVIVED  ") + name)
    survived += 0 if failed else 1
subprocess.run(["git", "checkout", "--", "sample/"], cwd=ROOT, capture_output=True)
if survived:
    sys.exit(f"{survived} mutation(s) survived: a test is missing")
print("every planted bug was caught")
