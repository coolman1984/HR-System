"""Behaviour-equivalence guard for the migration into coolman1984/HR-System.

The golden file migration/golden_behaviour.json was produced by running THIS script against
the ORIGINAL source, coolman1984/Department-automation @58a2298 (see MIGRATION.md):

    python TEST_MIGRATION_EQUIVALENCE.py --root <original checkout> --write migration/golden_behaviour.json

Run without arguments it replays the same five scenarios against this repository and fails
on ANY difference: every KPI, chart value, warning, reconciliation figure, auxiliary-source
report and a fingerprint of every stored row. It uses only the synthetic dataset.
Standard library only (CHECK_ENVIRONMENT.py treats any other import as a runtime dependency).
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "migration" / "golden_behaviour.json"

SCENARIO = r'''
import hashlib, json, sys
import engine
clean = "inputs/hr-factory-synthetic-dataset/01_CLEAN_BASELINE/"
dirty = "inputs/hr-factory-synthetic-dataset/02_STRESS_DIRTY/"
def aux(d):
    return {"employee": d + "02_Employee_Master.xlsx", "roster": d + "06_Shifts_Overtime.xlsx", "leave": d + "05_Time_Attendance_Leave.xlsx"}
VOLATILE = {"run_id", "updated_at"}
def shape(result):
    out = {k: v for k, v in result.items() if k not in VOLATILE}
    rows = sorted(engine.current_rows(), key=lambda r: json.dumps(r, sort_keys=True, default=str))
    out["_current_rows"] = len(rows)
    out["_current_rows_sha256"] = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    return out
steps = {}
steps["1_clean_attendance_only"] = shape(engine.process_file(clean + "05_Time_Attendance_Leave.xlsx"))
steps["2_same_bytes_again"] = shape(engine.process_file(clean + "05_Time_Attendance_Leave.xlsx", source_name="renamed.xlsx"))
steps["3_delta_correction"] = shape(engine.process_file("sample/HR_Attendance_Delta_Demo.xlsx"))
steps["4_clean_with_employee_roster_leave"] = shape(engine.process_file(clean + "05_Time_Attendance_Leave.xlsx", source_name="with-aux.xlsx", auxiliary_paths=aux(clean)))
try:
    steps["5_stress_dirty_with_aux"] = shape(engine.process_file(dirty + "05_Time_Attendance_Leave.xlsx", auxiliary_paths=aux(dirty)))
except Exception as exc:
    steps["5_stress_dirty_with_aux"] = {"error_type": type(exc).__name__, "error": str(exc)}
print(json.dumps(steps, sort_keys=True, default=str, ensure_ascii=False))
'''


def run(root):
    root = Path(root).resolve()
    with tempfile.TemporaryDirectory(prefix="hr_equivalence_") as folder:
        env = dict(os.environ, EXCEL_APP_DATA_DIR=str(Path(folder) / "data"))
        # The original tests import openpyxl directly; the application itself loads it from vendor.zip.
        env["PYTHONPATH"] = str(root / "vendor.zip") + os.pathsep + env.get("PYTHONPATH", "")
        done = subprocess.run([sys.executable, "-c", SCENARIO], cwd=root, env=env, capture_output=True, text=True, encoding="utf-8")
        if done.returncode != 0:
            raise SystemExit(done.stderr)
        return json.loads(done.stdout.strip().splitlines()[-1])


def diff(a, b, path=""):
    if type(a) is not type(b):
        return [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'golden' if k in a else 'current'}")
            else:
                out += diff(a[k], b[k], f"{path}.{k}")
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in diff(x, y, f"{path}[{i}]")]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(HERE))
    parser.add_argument("--write")
    args = parser.parse_args()
    observed = run(args.root)
    if args.write:
        Path(args.write).write_text(json.dumps(observed, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"golden written from {args.root}")
        sys.exit(0)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    differences = diff(golden, observed)
    summary = {name: {"current_rows": step.get("_current_rows"), "error": step.get("error")} for name, step in observed.items()}
    print(json.dumps({"scenarios": summary, "differences": len(differences)}, indent=2, ensure_ascii=False))
    if differences:
        print("\n".join(differences[:40]))
        raise SystemExit("Behaviour differs from the original Department-automation @58a2298")
