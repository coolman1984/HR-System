"""HR-System's secured server and administration commands (phase 2).

  python hr_server.py serve [--host 127.0.0.1] [--port 8766] [--backup-hours 6]
  python hr_server.py create-admin <username> "<display name>"      (asks for the password; server machine only)
  python hr_server.py backup                                         create + verify + rehearse now
  python hr_server.py backups                                        list backups and their rehearsal results
  python hr_server.py rehearse <backup name>                         restore into a temporary folder and compare
  python hr_server.py health                                         journal, audit, signing, device, last backup

Environment: EXCEL_APP_DATA_DIR (data folder), ECO_COMPANY_ID (the company's ecosystem id), HR_COMPANY_CODE,
HR_COMPANY_NAME, HR_BACKUP_DIR (default <data>/backups), HR_BACKUP_EXTRA (more local folders, separated by ';').
Passwords are asked interactively and never taken from arguments or the environment. Standard library only.
"""

import getpass
import json
import os
import sys

from hr_core.service import HRService


def open_service():
    data_dir = os.environ.get("EXCEL_APP_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    company = os.environ.get("ECO_COMPANY_ID", "")
    if not company:
        raise SystemExit("ECO_COMPANY_ID is required (the company's ecosystem id, a lower-case UUID)")
    extra = [d for d in (os.environ.get("HR_BACKUP_EXTRA") or "").split(";") if d.strip()]
    return HRService(data_dir, company, os.environ.get("HR_COMPANY_CODE", "COMPANY"), os.environ.get("HR_COMPANY_NAME", "Company"),
                     os.environ.get("HR_BACKUP_DIR") or None, extra)


def _arg(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, svc = argv[0], open_service()
    try:
        if cmd == "serve":
            from hr_core.api import serve
            host, port = _arg(argv, "--host", "127.0.0.1"), int(_arg(argv, "--port", "8766"))
            svc.backups.start(float(_arg(argv, "--backup-hours", "6")))
            server = serve(svc, host, port)
            print(f"HR-System server on http://{host}:{port}  (signing: {svc.health()['signing']['backend']})")
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            server.server_close()
        elif cmd == "create-admin" and len(argv) >= 3:
            password = getpass.getpass("Password for the first administrator: ")
            if password != getpass.getpass("Again: "):
                raise SystemExit("the two passwords differ")
            svc.bootstrap_admin(argv[1], argv[2], password, "local-cli")
            print(f"administrator {argv[1]} created")
        elif cmd == "backup":
            made = svc.backups.create("local-cli", "manual")
            made["rehearsal"] = svc.backups.rehearse(made["path"], "local-cli")
            print(json.dumps({"name": made["name"], "copies": made["copies"], "rehearsal": made["rehearsal"]}, indent=1))
            return 0 if made["rehearsal"]["ok"] else 1
        elif cmd == "backups":
            print(json.dumps(svc.backups.list(), indent=1))
        elif cmd == "rehearse" and len(argv) >= 2:
            result = svc.backups.rehearse(svc.backups.path_of(argv[1]), "local-cli")
            print(json.dumps(result, indent=1))
            return 0 if result["ok"] else 1
        elif cmd == "health":
            h = svc.health()
            print(json.dumps(h, indent=1, default=str))
            return 0 if h["journal"]["ok"] and h["audit"]["ok"] else 1
        else:
            print(__doc__)
            return 2
    finally:
        svc.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
