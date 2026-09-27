"""Employee registry and organisation — command line (phase 1, no screen yet).

  python hr_registry.py import <organisation.xlsx> <employee_master.xlsx> [--actor NAME]
  python hr_registry.py list org_unit|job|position|employee
  python hr_registry.py verify            journal chain check
  python hr_registry.py rebuild           recreate hr.db from the journal

Environment: EXCEL_APP_DATA_DIR (data folder, as the application), ECO_COMPANY_ID (the company's ecosystem
id, a lower-case UUID), HR_COMPANY_CODE and HR_COMPANY_NAME (used once, when the registry is created).
Standard library only.
"""

import json
import os
import sys

from hr_core.registry import Registry


def open_registry():
    data_dir = os.environ.get("EXCEL_APP_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    company = os.environ.get("ECO_COMPANY_ID", "")
    if not company:
        raise SystemExit("ECO_COMPANY_ID is required (the company's ecosystem id, a lower-case UUID)")
    return Registry(data_dir, company, os.environ.get("HR_COMPANY_CODE", "COMPANY"), os.environ.get("HR_COMPANY_NAME", "Company"))


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    reg, cmd = open_registry(), argv[0]
    if cmd == "import" and len(argv) >= 3:
        from hr_core.importer import import_workbooks
        actor = argv[argv.index("--actor") + 1] if "--actor" in argv else os.environ.get("USERNAME") or os.environ.get("USER") or "import"
        print(json.dumps(import_workbooks(reg, argv[1], argv[2], actor), ensure_ascii=False, indent=1))
    elif cmd == "list" and len(argv) == 2:
        for row in reg.list(argv[1]):
            print(json.dumps(row, ensure_ascii=False))
    elif cmd == "verify":
        result = reg.verify()
        print(json.dumps(result))
        return 0 if result["ok"] else 1
    elif cmd == "rebuild":
        before = reg.fingerprint()
        reg.rebuild()
        print(json.dumps({"rebuilt": True, "same_as_before": before == reg.fingerprint()}))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
