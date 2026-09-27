"""Acceptance of the INSTALLED product on Windows (CI job `windows-installer`; also usable on a test PC).

    python tools/installed_acceptance.py dist\\HR-System-Setup-<version>.exe

This script is the tester, not the product: it uses the machine's Python to drive the installed HR-System.exe, which
runs with Python hidden from it (no PATH entry, a bogus PYTHONHOME) and with outbound network blocked by a firewall
rule, so the program proves it carries its own runtime and needs no internet. It walks the phase-2.5 exit gate:
fresh install (with the old attendance program's history brought over), first administrator, sign-in, employee
register, permissions, attendance with the golden numbers, backup + rehearsal + restore, a restart that loses
nothing, an update over the installed version (data, accounts and journal kept; a pre-update backup when the data
version moves), a failure in the middle of an update, a power cut in the middle of an update, and removal of the
program keeping the data. Synthetic data only. Standard library only.
"""

import glob
import hashlib
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "HR-System")
EXE = os.path.join(PROGRAM, "HR-System.exe")
HOME = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "HR-System")
DATA = os.path.join(HOME, "data")
PORT = 18766
PASSWORD = "Admin-pass-1a"
results = {}


def check(name, cond, detail=None):
    print(("ok    " if cond else "FAIL  ") + name, flush=True)
    if not cond:
        raise SystemExit(f"{name}: {detail!r}")
    results[name] = True


def run(cmd, **kw):
    print(">", " ".join(cmd), flush=True)
    return subprocess.run(cmd, **kw)


def clean_env(**extra):
    """The environment of a PC without Python: no Python on PATH, a PYTHONHOME that points nowhere."""
    path = [p for p in os.environ.get("PATH", "").split(os.pathsep)
            if p and not glob.glob(os.path.join(p, "python*.exe")) and "python" not in p.lower()]
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    env.update({"PATH": os.pathsep.join(path), "PYTHONHOME": r"C:\no-python-here", "PYTHONPATH": ""})
    env.update(extra)
    return env


class Program:
    def __init__(self, **env):
        self.proc = subprocess.Popen([EXE, "--background", "--port", str(PORT)], env=clean_env(**env),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def wait_ready(self, timeout=180):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise SystemExit("HR-System.exe stopped: " + self.proc.stdout.read().decode(errors="replace")[-2000:])
            try:
                s, info = call("GET", "/api/info")
                if s == 200:
                    return info
            except OSError:
                pass
            time.sleep(1)
        raise SystemExit("HR-System.exe did not answer")

    def stop(self):
        self.proc.kill()  # what a power cut or taskkill does
        self.proc.wait()


COOKIE = {}


def call(method, path, body=None, raw=None, who=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=300)
    headers = {}
    if raw is not None:
        data, headers["Content-Type"] = raw, "application/octet-stream"
    elif method != "GET":
        data, headers["Content-Type"] = json.dumps(body or {}).encode(), "application/json"
    else:
        data = None
    if who and COOKIE.get(who):
        headers["Cookie"] = COOKIE[who]
    c.request(method, path, data, headers)
    r = c.getresponse()
    payload = r.read()
    if who and (r.getheader("Set-Cookie") or "").startswith("hr_sid="):
        COOKIE[who] = r.getheader("Set-Cookie").split(";")[0]
    try:
        return r.status, json.loads(payload)
    except ValueError:
        return r.status, payload


def login(who, password):
    s, out = call("POST", "/api/login", {"username": who, "password": password}, who=who)
    return s == 200


def install(setup, *extra):
    r = run([setup, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/TASKS=autostart", *extra])
    return r.returncode == 0


def journal_state():
    import sqlite3
    db = sqlite3.connect("file:" + os.path.join(DATA, "hr_journal.db").replace("\\", "/") + "?mode=ro", uri=True)
    try:
        return db.execute("SELECT COUNT(*), MAX(seq) FROM journal").fetchone()
    finally:
        db.close()


def data_version():
    try:
        return json.load(open(os.path.join(DATA, "data_version.json")))["data_version"]
    except FileNotFoundError:
        return None


def main(setup):
    setup = os.path.abspath(setup)
    sys.path.insert(0, ROOT)
    from hr_core.version import VERSION

    # an old portable attendance installation, as the ZIP left it (built with the original engine, synthetic data)
    old = tempfile.mkdtemp(prefix="old_attendance_")
    subprocess.check_call([sys.executable, "-c", "import engine; engine.process_file('sample/HR_Time_Attendance_Demo.xlsx')"], cwd=ROOT,
                          env=dict(os.environ, EXCEL_APP_DATA_DIR=os.path.join(old, "data"), PYTHONPATH=os.path.join(ROOT, "vendor.zip")))
    open(os.path.join(old, "START.bat"), "w").write("@echo off\n")
    old_hash = hashlib.sha256(open(os.path.join(old, "data", "history.db"), "rb").read()).hexdigest()

    # ---------------------------------------------------------------- 1. install from scratch
    shutil.rmtree(HOME, ignore_errors=True)
    check("installs_silently", install(setup, f"/OLDDATA={old}"))
    check("program_is_in_program_files", os.path.isfile(EXE))
    leaks = [p for p in glob.glob(os.path.join(PROGRAM, "**", "*.py"), recursive=True) if os.path.basename(p) != "CUSTOM_RULES.py"]
    check("no_program_source_in_the_program_folder", not leaks, leaks[:5])
    check("data_folder_is_outside_the_program", os.path.isdir(DATA) and not os.path.exists(os.path.join(PROGRAM, "data")))
    check("old_attendance_history_was_copied_not_moved", os.path.isfile(os.path.join(DATA, "history.db"))
          and hashlib.sha256(open(os.path.join(old, "data", "history.db"), "rb").read()).hexdigest() == old_hash)
    pending = os.path.join(HOME, "recovery", "pending", "installer.json")
    check("installer_left_a_copy_for_recovery", os.path.isfile(pending) and json.load(open(pending))["version"] == VERSION)
    startup = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup", "HR-System.lnk")
    check("starts_with_windows_by_default_for_the_installing_person", os.path.isfile(startup), startup)
    acl = subprocess.run(["icacls", HOME], capture_output=True, text=True).stdout
    check("data_is_not_open_to_every_user_of_the_pc", all(g not in acl for g in ("BUILTIN\\Users", "Everyone", "Authenticated Users"))
          and os.environ["USERNAME"].lower() in acl.lower(), acl)

    rule = "HR-System acceptance: no internet"
    run(["netsh", "advfirewall", "firewall", "add", "rule", f"name={rule}", "dir=out", "action=block", f"program={EXE}", "enable=yes"], check=True)
    try:
        prog = Program()
        info = prog.wait_ready()
        check("runs_without_python_and_without_internet", info["product"] == "HR-System" and info["version"] == VERSION and info["setup_needed"])

        # ------------------------------------------------------------ 2. first administrator, sign-in, register, permissions
        s, out = call("POST", "/api/setup/install", {"company": {"source": "local", "code": "NILE", "name": "Nile Electronics"},
                                                     "admin": {"username": "admin1", "display_name": "Admin", "password": PASSWORD}})
        check("first_administrator_created", s == 201, out)
        check("administrator_signs_in", login("admin1", PASSWORD))
        s, site = call("PUT", "/api/org_unit/CAI", {"fields": {"type": "site", "name": "Cairo", "parent_id": None}}, who="admin1")
        s, out = call("GET", "/api/org_unit", who="admin1")
        company = next(u for u in out if u["type"] == "company")
        s, _ = call("PUT", "/api/org_unit/CAI", {"fields": {"type": "site", "name": "Cairo", "parent_id": company["id"]}}, who="admin1")
        s, emp = call("PUT", "/api/employee/E001", {"fields": {"preferred_name": "Mona", "employment_status": "Active", "hire_date": "2024-01-01"}}, who="admin1")
        check("employee_register_works", s == 200 and emp["row"]["code"] == "E001", emp)
        call("POST", "/api/admin/users", {"username": "viewer1", "display_name": "V", "password": "Viewer-pass-1a", "profile": "viewer"}, who="admin1")
        login("viewer1", "Viewer-pass-1a")
        call("POST", "/api/password", {"old": "Viewer-pass-1a", "new": "Viewer-pass-2b"}, who="viewer1")
        s, out = call("PUT", "/api/employee/E002", {"fields": {"preferred_name": "X"}}, who="viewer1")
        check("permissions_are_enforced", s == 403 and out["error"] == "perm.denied", out)

        # ------------------------------------------------------------ 3. attendance, unchanged numbers
        s, state = call("GET", "/api/state", who="admin1")
        check("old_attendance_history_is_visible", s == 200 and state.get("current_count") == 200, state.get("current_count") if isinstance(state, dict) else state)
        clean = open(os.path.join(ROOT, "inputs", "hr-factory-synthetic-dataset", "01_CLEAN_BASELINE", "05_Time_Attendance_Leave.xlsx"), "rb").read()
        shutil.rmtree(os.path.join(DATA, "uploads"), ignore_errors=True)
        s, out = call("POST", "/api/upload?filename=05_Time_Attendance_Leave.xlsx", raw=clean, who="admin1")
        golden = json.load(open(os.path.join(ROOT, "migration", "golden_behaviour.json"), encoding="utf-8"))["1_clean_attendance_only"]
        check("attendance_upload_works_in_the_installed_program", s == 200 and out.get("accepted_count") == golden["accepted_count"]
              and out.get("kpis") is not None, out if s != 200 else None)
        s, health = call("GET", "/api/admin/health", who="admin1")
        check("signing_uses_the_bundled_standard_library", health["signing"]["backend"] == "cryptography", health["signing"])
        check("excel_is_detected_not_assumed", isinstance(health["attendance"]["excel_desktop"], bool), health["attendance"])
        check("recovery_installer_promoted_after_a_clean_start", health["recovery"] and health["recovery"]["intact"] and health["recovery"]["version"] == VERSION, health["recovery"])

        # ------------------------------------------------------------ 4. backup, rehearsal, restore
        s, made = call("POST", "/api/admin/backups", who="admin1")
        check("backup_and_rehearsal_pass", s == 201 and made["rehearsal"]["ok"] and "history.db" in made["manifest"]["files"], made)
        call("PUT", "/api/employee/E001", {"fields": {"preferred_name": "Changed after backup"}, "expected_ver": emp["row"]["ver"]}, who="admin1")
        s, out = call("POST", f"/api/admin/backups/{made['name']}/restore", who="admin1")
        s, rows = call("GET", "/api/employee", who="admin1")
        check("restore_brings_back_the_backup_as_a_new_line", next(r for r in rows if r["code"] == "E001")["preferred_name"] == "Mona")

        # ------------------------------------------------------------ 5. restart (as after switching the PC off)
        before = journal_state()
        prog.stop()
        prog = Program()
        prog.wait_ready()
        check("a_restart_loses_nothing", login("admin1", PASSWORD) and journal_state()[0] >= before[0]
              and call("GET", "/api/state", who="admin1")[1].get("current_count") == golden["current_count"])
        prog.stop()

        # ------------------------------------------------------------ 6. update over the installed version
        users_before = journal_state()
        upgrade_from = 0
        json.dump({"data_version": upgrade_from}, open(os.path.join(DATA, "data_version.json"), "w"))  # as an older version left it
        check("update_installs_silently", install(setup))
        prog = Program()
        prog.wait_ready()
        s, backups = (login("admin1", PASSWORD), call("GET", "/api/admin/backups", who="admin1")[1])
        check("update_keeps_accounts_data_and_history", s and journal_state()[0] >= users_before[0]
              and any(r["code"] == "E001" for r in call("GET", "/api/employee", who="admin1")[1]))
        check("update_took_a_verified_backup_kept_forever", any(b["kept_forever"] and b["rehearsal"] and b["rehearsal"]["ok"] for b in backups))
        check("update_reached_the_current_data_version", data_version() == call("GET", "/api/admin/health", who="admin1")[1]["product"]["program_data_version"])
        prog.stop()

        # ------------------------------------------------------------ 7. failure in the middle of an update
        json.dump({"data_version": 0}, open(os.path.join(DATA, "data_version.json"), "w"))
        before = journal_state()
        prog = Program(HR_TEST_HOOKS="1", HR_UPGRADE_FAULT="fail:1")
        info = prog.wait_ready()
        check("a_failed_update_stops_with_a_message", info.get("error") and info["error"]["code"] == "upgrade.failed", info)
        check("a_failed_update_puts_the_data_back", data_version() == 0 and journal_state()[0] <= before[0] + 0
              and not os.path.exists(os.path.join(DATA, "upgrade-in-progress.json")))
        prog.stop()
        prog = Program()
        prog.wait_ready()
        check("after_a_failure_the_next_start_updates", data_version() >= 1 and login("admin1", PASSWORD))
        prog.stop()

        # ------------------------------------------------------------ 8. power cut in the middle of an update
        json.dump({"data_version": 0}, open(os.path.join(DATA, "data_version.json"), "w"))
        prog = Program(HR_TEST_HOOKS="1", HR_UPGRADE_FAULT="stall:1")
        deadline = time.time() + 180
        while time.time() < deadline and not os.path.exists(os.path.join(DATA, "upgrade-in-progress.json")):
            time.sleep(0.5)
        time.sleep(2)
        prog.stop()  # the power goes off
        check("the_power_cut_happened_mid_update", os.path.exists(os.path.join(DATA, "upgrade-in-progress.json")) and data_version() == 0)
        prog = Program()
        prog.wait_ready()
        check("after_a_power_cut_the_update_finishes", data_version() >= 1 and not os.path.exists(os.path.join(DATA, "upgrade-in-progress.json"))
              and login("admin1", PASSWORD) and call("GET", "/api/admin/health", who="admin1")[1]["journal"]["ok"])
        prog.stop()
    finally:
        run(["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"])

    # ---------------------------------------------------------------- 9. removing the program keeps the data
    uninstaller = os.path.join(PROGRAM, "unins000.exe")
    run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], check=True)
    deadline = time.time() + 60
    while time.time() < deadline and os.path.exists(EXE):
        time.sleep(1)
    check("removal_keeps_the_data", not os.path.exists(EXE) and os.path.isfile(os.path.join(DATA, "hr_journal.db"))
          and os.path.isfile(os.path.join(HOME, "config.json")))
    print(json.dumps(results, indent=1))
    print(f"installed acceptance: {len(results)} checks passed")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else glob.glob(os.path.join(ROOT, "dist", "HR-System-Setup-*.exe"))[0])
