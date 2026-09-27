"""Employee registry and organisation (phase 1) — acceptance tests.

Synthetic data only. Standard library only (openpyxl comes from vendor.zip like the application).
"""

import ast
import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"
CLEAN = "inputs/hr-factory-synthetic-dataset/01_CLEAN_BASELINE/"
DIRTY = "inputs/hr-factory-synthetic-dataset/02_STRESS_DIRTY/"

from hr_core import modules  # noqa: E402
from hr_core.canonical import GENESIS, canonical, line_hash  # noqa: E402
from hr_core.importer import import_workbooks  # noqa: E402
from hr_core.registry import Conflict, Registry, RegistryError  # noqa: E402
import eco_contract  # noqa: E402
import eco_publisher  # noqa: E402

results = {}


def fresh():
    return Registry(tempfile.mkdtemp(prefix="hr_registry_"), COMPANY, "NILE", "Nile Electronics")


def expect_error(code, fn):
    try:
        fn()
    except RegistryError as exc:
        assert exc.code == code, (exc.code, str(exc))
        return str(exc)
    raise AssertionError(f"expected {code}")


# 1. The ecosystem's canonical JSON and hash: the same bytes as TypeScript (GMES) and BAMS.
vectors = json.loads((ROOT / "eco_schemas" / "canonical-v1.json").read_text(encoding="utf-8"))
prev = GENESIS
for v in vectors["vectors"]:
    assert canonical(v["value"]) == v["canonical"], v["name"]
    h = line_hash(vectors["domain"], dict(v["value"], prev=prev))
    assert h == v["line_hash"], v["name"]
    prev = h
try:
    canonical({"qty": 1.5})
    raise AssertionError("floats must be refused")
except ValueError:
    pass
results["canonical_json_matches_typescript_vectors"] = True

# 2. A real, independent registry imported from the workbooks: structure and counts.
reg = fresh()
report = import_workbooks(reg, CLEAN + "01_Organization_Factory.xlsx", CLEAN + "02_Employee_Master.xlsx", "test")
counts = {t: sum(1 for u in reg.list("org_unit") if u["type"] == t) for t in ("company", "site", "business_unit", "department", "section")}
assert counts == {"company": 1, "site": 4, "business_unit": 8, "department": 24, "section": 48}, counts
assert len(reg.list("job")) == 80 and len(reg.list("position")) == 220 and len(reg.list("employee")) == 197
assert len(report["skipped"]) == 2 and all("TOTAL / CHECK" in s for s in report["skipped"]), report["skipped"]
assert len(report["rejected"]) == 3 and all("before hire" in r for r in report["rejected"]), report["rejected"]
e1 = reg.get("employee", "E000001")
assert e1["id"] == "ad793f13-3ba3-5304-92f6-7bc2f8c8d5c8"  # the same shared id GMES uses
site = reg.by_id("org_unit", e1["home_site_id"])
assert site["type"] == "site" and site["code"] == "PLT-04"
pos = reg.by_id("position", e1["position_id"])
unit = reg.by_id("org_unit", pos["org_unit_id"])
chain = []
while unit:
    chain.append(unit["type"])
    unit = reg.by_id("org_unit", unit["parent_id"]) if unit["parent_id"] else None
assert chain == ["section", "department", "business_unit", "site", "company"], chain
results["independent_registry_company_site_bu_department_section_position_employee"] = True

# 3. Importing the same files again changes nothing and writes nothing.
lines = reg.verify()["lines"]
again = import_workbooks(reg, CLEAN + "01_Organization_Factory.xlsx", CLEAN + "02_Employee_Master.xlsx", "test")
assert again["changed"] is False and again["created"] == 0 and again["updated"] == 0 and reg.verify()["lines"] == lines, again
results["reimport_is_idempotent"] = True

# 4. The dirty workbook: problems are listed, the import is one change or none, and nothing is guessed.
dirty = fresh()
d = import_workbooks(dirty, DIRTY + "01_Organization_Factory.xlsx", DIRTY + "02_Employee_Master.xlsx", "test")
assert d["rejected"] and d["warnings"] and d["changed"] is True
assert any("appears 2 times" in r for r in d["rejected"])
assert any("UNPLACED" in w for w in d["warnings"])
for u in dirty.list("org_unit"):
    if u["attrs"].get("unplaced"):
        assert dirty.by_id("org_unit", u["parent_id"])["type"] == "company"
assert dirty.verify()["ok"] and dirty.verify()["lines"] == 3  # device registration + the company + ONE import
results["dirty_data_reported_not_guessed"] = True

# 5. Rules: optimistic versions, soft delete, restore, no reuse, structure.
e = reg.get("employee", "E000002")
reg.commit("hr-officer", "Status change", [reg.op_put("employee", "E000002", {"employment_status": "Suspended"}, expected_ver=e["ver"])])
expect_error("ver.conflict", lambda: reg.commit("other-officer", "Late edit", [reg.op_put("employee", "E000002", {"employment_status": "Active"}, expected_ver=e["ver"])]))
assert reg.get("employee", "E000002")["employment_status"] == "Suspended"
expect_error("employee.status", lambda: reg.commit("x", "bad", [reg.op_put("employee", "E000002", {"employment_status": "Fired"})]))
expect_error("employee.dates", lambda: reg.commit("x", "bad", [reg.op_put("employee", "E000002", {"hire_date": "2020-01-01", "termination_date": "2019-01-01"})]))
dept = next(u for u in reg.list("org_unit") if u["type"] == "department")
expect_error("org_unit.in_use", lambda: reg.commit("x", "delete", [reg.op_delete("org_unit", dept["code"], dept["ver"], "department")]))
sect = next(u for u in reg.list("org_unit") if u["type"] == "section")
expect_error("org.parent", lambda: reg.commit("x", "bad", [reg.op_put("org_unit", "SEC-NEW", {"type": "section", "name": "x", "parent_id": sect["id"]})]))
expect_error("org.parent", lambda: reg.commit("x", "bad", [reg.op_put("org_unit", "SITE-X", {"type": "site", "name": "x", "parent_id": dept["id"]})]))
expect_error("position.unit", lambda: reg.commit("x", "bad", [reg.op_put("position", "POS-X", {"job_id": reg.list("job")[0]["id"], "org_unit_id": reg.list("org_unit")[1]["id"] if reg.list("org_unit")[1]["type"] == "site" else next(u["id"] for u in reg.list("org_unit") if u["type"] == "site")})]))
# an employee nobody manages and who holds nothing can be removed to the Recycle Bin and restored; the code is never reused
leaf = next(x for x in reg.list("employee") if not reg.db.execute("SELECT 1 FROM employee WHERE manager_id = ? AND deleted = 0", (x["id"],)).fetchone())
reg.commit("hr-officer", "Remove", [reg.op_delete("employee", leaf["code"], leaf["ver"])])
assert reg.get("employee", leaf["code"]) is None and reg.get("employee", leaf["code"], include_deleted=True)["deleted"] == 1
expect_error("employee.deleted", lambda: reg.commit("x", "re-create", [reg.op_put("employee", leaf["code"], {"employment_status": "Active"})]))
reg.commit("hr-officer", "Restore", [reg.op_restore("employee", leaf["code"])])
assert reg.get("employee", leaf["code"])["deleted"] == 0
expect_error("audit.required", lambda: reg.commit("", "", []))
results["versions_soft_delete_restore_no_reuse_structure_rules"] = True

# 6. Absence from a later import is NOT a deletion (the migrated application's rule).
count = len(reg.list("employee"))
tmp = tempfile.mkdtemp()
from openpyxl import load_workbook  # noqa: E402  (bundled, put on the path by the importer)
wb = load_workbook(CLEAN + "02_Employee_Master.xlsx")
ws = wb["EMP_01_EmployeeMaster"]
ws.delete_rows(3, 50)  # remove 50 employees from the file
wb.save(Path(tmp) / "fewer.xlsx")
import_workbooks(reg, CLEAN + "01_Organization_Factory.xlsx", str(Path(tmp) / "fewer.xlsx"), "test")
assert len(reg.list("employee")) == count
results["absence_is_not_deletion"] = True

# 7. The journal: chain verified, tampering located, crash repaired, rebuild identical.
v = reg.verify()
assert v["ok"]
fp = reg.fingerprint()
reg.rebuild()
assert reg.fingerprint() == fp
results["rebuild_from_journal_identical"] = True
# crash after the commit point: the journal has the line, hr.db does not
reg.commit("hr-officer", "Before crash", [reg.op_put("employee", "E000003", {"worker_type": "Contractor"})])
before = reg.applied_seq() - 1  # hr.db as it was before the line (the fold writes seq and hash together)
reg.db.execute("UPDATE meta SET value = ? WHERE key = 'applied_seq'", (str(before),))
reg.db.execute("UPDATE meta SET value = ? WHERE key = 'applied_hash'", (reg.journal.hash_at(before),))
reg.db.execute("UPDATE employee SET worker_type = 'Regular', ver = ver - 1 WHERE code = 'E000003'")
reg.db.commit()
data_dir = str(Path(reg.path).parent)
reg.close()
reopened = Registry(data_dir, COMPANY)
assert reopened.get("employee", "E000003")["worker_type"] == "Contractor"
assert reopened.applied_seq() == reopened.verify()["lines"] and reopened.verify()["ok"]
results["crash_after_commit_point_repaired_on_start"] = True
raw = sqlite3.connect(reopened.journal_path)
for stmt in ("UPDATE journal SET label = 'x' WHERE seq = 2", "DELETE FROM journal WHERE seq = 2"):
    try:
        raw.execute(stmt)
        raise AssertionError("journal must refuse " + stmt)
    except sqlite3.DatabaseError as exc:
        assert "append-only" in str(exc)
raw.execute("DROP TRIGGER journal_no_update")
raw.execute("UPDATE journal SET label = 'forged' WHERE seq = 2")
raw.commit()
raw.close()
bad = reopened.verify()
assert bad["ok"] is False and bad["first_bad_seq"] == 2, bad
reopened.close()
results["journal_append_only_and_tamper_located"] = True

# 8. No personal data in the registry (phase 1 imports employment facts only).
cols = {r[1] for r in sqlite3.connect(reg.path).execute("PRAGMA table_info(employee)")}
assert not cols & {"date_of_birth", "gender", "national_id", "national_id_hash", "mobile", "blood_group", "base_pay"}, cols
results["no_personal_data_stored"] = True

# 9. The publisher now takes employees from the registry, with department, position and site.
reg2 = fresh()
import_workbooks(reg2, CLEAN + "01_Organization_Factory.xlsx", CLEAN + "02_Employee_Master.xlsx", "test")
snaps, problems = eco_publisher.build_snapshots([], COMPANY, reg2)
employees = [b for (k, _), b in snaps.items() if k == "eco.employee.v1"]
assert len(employees) == 197
e = next(x for x in employees if x["code"] == "E000001")
assert e["plant_code"] == "PLT-04" and e["position_code"] == "POS-0001" and e["department_code"].startswith("DEP-") and e["display_name"] == "Ahmed"
assert not {"legal_name", "legacy_number"} & set(e)
assert all(not eco_contract.validate("eco.employee.v1", dict(b, version=1)) for b in employees)
assert all(b["active"] is (b["employment_status"] == "Active") for b in employees)
# without a registry, the pre-registry behaviour is unchanged (rollback line)
old, _ = eco_publisher.build_snapshots([{"attendance_id": "A1", "employee_id": "E1", "work_date": "2026-09-01", "attendance_status": "Present", "employee_employment_status": "Active"}], COMPANY, None)
assert [k for k, _ in old] == ["eco.employee.v1", "eco.attendance_day.v1"]
results["publisher_uses_registry_with_org_codes"] = True

# 10. Editions (mechano): what can be sold is resolved, payroll is design-only.
assert modules.available("attendance") == ["kernel", "attendance"]
assert modules.available("attendance_leave") == ["kernel", "attendance", "leave"]
assert "payroll" not in modules.resolve("full")
try:
    modules.EDITIONS["bad"] = ["payroll"]
    modules.resolve("bad")
    raise AssertionError("payroll must not be sellable")
except ValueError:
    pass
finally:
    modules.EDITIONS.pop("bad", None)
results["editions_resolve_and_payroll_is_design_only"] = True

# 11. The kernel package is standard library only (CHECK_ENVIRONMENT.py only scans top-level files).
import sys  # noqa: E402
std = set(sys.stdlib_module_names) | {"hr_core", "calculation_engine", "engine", "openpyxl"}  # engine: the locked attendance application (phase 2.5 serves it)
for path in (ROOT / "hr_core").rglob("*.py"):
    # The ONE exception: signing.py prefers the standard `cryptography` package when present (optional, guarded).
    allowed = std | ({"cryptography"} if path.name == "signing.py" else set())
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module else [])
        for name in names:
            assert name.split(".")[0] in allowed, f"{path.name} imports {name}"
results["kernel_is_standard_library_only"] = True

uuid.UUID(COMPANY)
print(json.dumps(results, indent=2))
