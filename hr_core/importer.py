"""Import the organisation and the employee master from the HR workbooks (data dictionary V1).

Rules carried over from the migrated application: the absence of a row NEVER deletes anything; an unknown
reference is imported with a visible warning (never guessed, never a silent drop); the whole import is ONE
saved change or nothing (a rejected row is listed and skipped before anything is written).
Personal data (EMP_02 and later sheets) is deliberately NOT imported in phase 1.
"""

import calculation_engine  # noqa: F401  (puts the bundled openpyxl from vendor.zip on the path)
from openpyxl import load_workbook

import re

from .registry import EMPLOYMENT_STATUSES, RegistryError

# A real key looks like "DEP-004" or "E000001". Anything else in the key column (e.g. a "TOTAL / CHECK"
# row under the table) is a summary row, not data: skipped and reported, never imported as an entity.
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

ORG_SHEETS = {
    "site": ("ORG_01_Plants", "Plant_ID"),
    "business_unit": ("ORG_02_BusinessUnits", "Business_Unit_ID"),
    "department": ("ORG_03_Departments", "Department_ID"),
    "section": ("ORG_04_Sections", "Section_ID"),
    "job": ("ORG_06_Jobs", "Job_ID"),
    "position": ("ORG_07_Positions", "Position_ID"),
}


def _sheet(path, name, key):
    """Rows of a sheet as dicts; the header row is found by its key column (header rows differ: 1, 2 or 3)."""
    workbook = load_workbook(path, read_only=True, data_only=True)
    if name not in workbook.sheetnames:
        raise RegistryError("import.sheet", f"{path}: sheet {name} is missing")
    rows = list(workbook[name].iter_rows(values_only=True))
    workbook.close()
    for i, row in enumerate(rows):
        if row and key in [str(c).strip() if c is not None else None for c in row]:
            header = [str(c).strip() if c is not None else None for c in row]
            return [dict(zip(header, r)) for r in rows[i + 1:] if r and any(v is not None for v in r)]
    raise RegistryError("import.header", f"{path}: sheet {name} has no column {key}")


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value):
    if value is None or value == "":
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


def import_workbooks(registry, org_path, employee_path, actor):
    """Returns a report: {changed, seq, created, updated, unchanged, warnings[], rejected[]}."""
    reg, warnings, rejected, ops, skipped = registry, [], [], [], []
    company = [u for u in reg.list("org_unit") if u["type"] == "company"][0]
    known = {}  # (entity-or-type, code) -> global id, for everything that will exist after this import

    def note_existing():
        for u in reg.list("org_unit"):
            known[(u["type"], u["code"])] = u["id"]
        for e in ("job", "position", "employee"):
            for r in reg.list(e):
                known[(e, r["code"])] = r["id"]

    note_existing()
    data = {kind: _sheet(org_path, *ORG_SHEETS[kind]) for kind in ORG_SHEETS}
    employees = _sheet(employee_path, "EMP_01_EmployeeMaster", "Employee_ID")

    def seen_once(kind, key, rows):
        out, counts, told = [], {}, set()
        for r in rows:
            code = _text(r.get(key))
            counts[code] = counts.get(code, 0) + 1
        for i, r in enumerate(rows):
            code = _text(r.get(key))
            if not code:
                rejected.append(f"{kind} row {i + 1}: no {key}")
            elif not KEY.match(code):
                skipped.append(f"{kind}: row {code!r} is not a {key} (summary/total row), skipped")
            elif counts[code] > 1:
                if code not in told:
                    rejected.append(f"{kind} {code}: appears {counts[code]} times in the file; none of them imported")
                    told.add(code)
            else:
                out.append((code, r))
        return out

    def put(entity, code, fields, org_type=None):
        ops.append(reg.op_put(entity, code, fields))
        known[(org_type or entity, code)] = reg.gid(entity, code, org_type)

    for code, r in seen_once("site", "Plant_ID", data["site"]):
        put("org_unit", code, {"type": "site", "name": _text(r.get("Plant_Name")) or code, "parent_id": company["id"],
                               "attrs": {k: v for k, v in (("time_zone", _text(r.get("Time_Zone"))), ("currency", _text(r.get("Default_Currency"))),
                                                           ("source_active_flag", bool(r.get("Active_Flag")))) if v is not None}}, "site")
    for code, r in seen_once("business_unit", "Business_Unit_ID", data["business_unit"]):
        parent = known.get(("site", _text(r.get("Plant_ID"))))
        if not parent:
            rejected.append(f"business unit {code}: site {r.get('Plant_ID')} does not exist")
            continue
        put("org_unit", code, {"type": "business_unit", "name": _text(r.get("Business_Unit_Name")) or code, "parent_id": parent,
                               "attrs": {"source_active_flag": bool(r.get("Active_Flag"))}}, "business_unit")
    for code, r in seen_once("department", "Department_ID", data["department"]):
        parent = known.get(("business_unit", _text(r.get("Business_Unit_ID"))))
        attrs = {"department_type": _text(r.get("Department_Type")), "default_cost_center": _text(r.get("Default_Cost_Center_ID")),
                 "source_active_flag": bool(r.get("Active_Flag"))}
        if not parent:
            warnings.append(f"department {code}: business unit {r.get('Business_Unit_ID')} does not exist; placed directly under the company as UNPLACED — decide where it belongs")
            parent, attrs["unplaced"] = company["id"], True
        put("org_unit", code, {"type": "department", "name": _text(r.get("Department_Name")) or code, "parent_id": parent,
                               "attrs": {k: v for k, v in attrs.items() if v is not None}}, "department")
    for code, r in seen_once("section", "Section_ID", data["section"]):
        parent = known.get(("department", _text(r.get("Department_ID"))))
        if not parent:
            rejected.append(f"section {code}: department {r.get('Department_ID')} does not exist")
            continue
        put("org_unit", code, {"type": "section", "name": _text(r.get("Section_Name")) or code, "parent_id": parent,
                               "attrs": {"shift_based": bool(r.get("Shift_Based_Flag")), "source_active_flag": bool(r.get("Active_Flag"))}}, "section")
    for code, r in seen_once("job", "Job_ID", data["job"]):
        if not _text(r.get("Job_Title")):
            rejected.append(f"job {code}: no title")
            continue
        put("job", code, {"title": _text(r.get("Job_Title")), "family": _text(r.get("Job_Family")), "level": _text(r.get("Job_Level")),
                          "critical": bool(r.get("Critical_Job_Flag")), "attrs": {"source_active_flag": bool(r.get("Active_Flag"))}})
    positions = seen_once("position", "Position_ID", data["position"])
    for code, r in positions:
        job = known.get(("job", _text(r.get("Job_ID"))))
        unit = known.get(("section", _text(r.get("Section_ID")))) or known.get(("department", _text(r.get("Department_ID"))))
        if not job or not unit:
            rejected.append(f"position {code}: job {r.get('Job_ID')} or unit {r.get('Section_ID')}/{r.get('Department_ID')} does not exist")
            continue
        put("position", code, {"job_id": job, "org_unit_id": unit, "status": _text(r.get("Position_Status")),
                               "attrs": {"cost_center": _text(r.get("Cost_Center_ID"))}})
    # Reporting lines in a second pass (row order never matters), and ONLY here, so a re-import that
    # changes nothing writes nothing.
    for code, r in positions:
        if ("position", code) not in known:
            continue
        target, value = _text(r.get("Reports_To_Position_ID")), None
        if target and target != code:
            if ("position", target) in known:
                value = known[("position", target)]
            else:
                warnings.append(f"position {code}: reports to {target}, which does not exist; left empty")
        ops.append(reg.op_put("position", code, {"reports_to_id": value}))

    staff = seen_once("employee", "Employee_ID", employees)
    for code, r in staff:
        status = _text(r.get("Employment_Status"))
        if status not in EMPLOYMENT_STATUSES:
            rejected.append(f"employee {code}: employment status {status!r} is not one of {', '.join(EMPLOYMENT_STATUSES)}")
            continue
        hire, term = _date(r.get("Hire_Date")), _date(r.get("Termination_Date"))
        if hire and term and term < hire:
            rejected.append(f"employee {code}: termination {term} is before hire {hire}")
            continue
        if status == "Terminated" and not term:
            warnings.append(f"employee {code}: Terminated without a termination date")
        site = known.get(("site", _text(r.get("Home_Plant_ID"))))
        if r.get("Home_Plant_ID") and not site:
            warnings.append(f"employee {code}: home site {r.get('Home_Plant_ID')} does not exist; left empty")
        position = known.get(("position", _text(r.get("Current_Position_ID"))))
        if r.get("Current_Position_ID") and not position:
            warnings.append(f"employee {code}: position {r.get('Current_Position_ID')} does not exist; left empty")
        put("employee", code, {"legacy_number": _text(r.get("Employee_Number_Legacy")), "preferred_name": _text(r.get("Preferred_Name")),
                               "legal_name": _text(r.get("Legal_Name")), "employment_status": status, "worker_type": _text(r.get("Worker_Type")),
                               "hire_date": hire, "termination_date": term, "home_site_id": site, "position_id": position})
    for code, r in staff:
        if ("employee", code) not in known:
            continue
        manager, value = _text(r.get("Manager_Employee_ID")), None
        if manager and manager != code:
            if ("employee", manager) in known:
                value = known[("employee", manager)]
            else:
                warnings.append(f"employee {code}: manager {manager} does not exist; left empty")
        ops.append(reg.op_put("employee", code, {"manager_id": value}))

    before = {e: {r["code"]: r["ver"] for r in reg.list(e, include_deleted=True)} for e in ("org_unit", "job", "position", "employee")}
    seq = reg.commit(actor, f"Import {org_path.split('/')[-1]} + {employee_path.split('/')[-1]}", ops) if ops else None
    created = updated = unchanged = 0
    for e in before:
        after = {r["code"]: r["ver"] for r in reg.list(e, include_deleted=True)}
        created += sum(1 for c in after if c not in before[e])
        updated += sum(1 for c, v in after.items() if c in before[e] and v != before[e][c])
        unchanged += sum(1 for c, v in after.items() if c in before[e] and v == before[e][c])
    return {"changed": seq is not None, "seq": seq, "created": created, "updated": updated, "unchanged": unchanged,
            "warnings": warnings, "rejected": rejected, "skipped": skipped}
