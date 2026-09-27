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
     'done = self.applied_seq()', 'return\n        done = self.applied_seq()', "TEST_HR_REGISTRY.py"),
    ("summary rows are imported as entities", "hr_core/importer.py",
     "elif not KEY.match(code):", "elif False:", "TEST_HR_REGISTRY.py"),
    ("the publisher ignores the registry", "eco_publisher.py",
     'if registry is not None and registry.list("employee"):', 'if False:', "TEST_HR_REGISTRY.py"),
]

survived = 0
for name, rel, old, new, test in MUTATIONS:
    path = ROOT / rel
    original = path.read_text(encoding="utf-8")
    if old not in original:
        sys.exit(f"mutation '{name}': anchor not found in {rel}")
    path.write_text(original.replace(old, new, 1), encoding="utf-8")
    try:
        env = dict(os.environ, PYTHONPATH=str(ROOT / "vendor.zip"))
        failed = subprocess.run([sys.executable, test], cwd=ROOT, env=env, capture_output=True).returncode != 0
    finally:
        path.write_text(original, encoding="utf-8")
    print(("caught    " if failed else "SURVIVED  ") + name)
    survived += 0 if failed else 1
subprocess.run(["git", "checkout", "--", "sample/"], cwd=ROOT, capture_output=True)
if survived:
    sys.exit(f"{survived} mutation(s) survived: a test is missing")
print("every planted bug was caught")
