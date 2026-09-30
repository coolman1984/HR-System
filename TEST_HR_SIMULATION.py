"""The simulated date (plan 30-HR WP-H7): "today" can be moved only when the server runs in simulation, and every rule follows it.

Through the real HTTP handler. Synthetic data only. Standard library only.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"

results = {}


def check(name, ok, detail=None):
    results[name] = bool(ok)
    if not ok:
        print(json.dumps(results, indent=2))
        raise AssertionError(f"{name}: {detail}")


# ---- 1. without the switch there is no way to move the date, in code or over HTTP
os.environ.pop("HR_SIMULATION", None)
from hr_core import clock  # noqa: E402

try:
    clock.set_today("2026-08-01")
    refused = False
except clock.ClockError as exc:
    refused = exc.code == "clock.not_simulation"
check("an_installed_program_cannot_move_its_date", refused)
check("without_the_switch_today_is_the_computers_date", clock.today() == __import__("datetime").date.today().isoformat())

from hr_core.api import make_handler  # noqa: E402
from hr_core.service import HRService  # noqa: E402


def start(tmp):
    svc = HRService(os.path.join(tmp, "data"), COMPANY, "NILE", "Nile Home", backup_dir=os.path.join(tmp, "backups"))
    svc.bootstrap_admin("admin", "Admin", "Admin-2026!x")
    svc.auth.commit("admin", "clear first-login flag", [{"entity": "user", "code": "admin", "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", "admin")["ver"]}])
    token = svc.login("admin", "Admin-2026!x")[0]
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "Cookie": f"hr_sid={token}"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")
    return svc, server, call


tmp = tempfile.mkdtemp(prefix="hr_sim_off_")
svc, server, call = start(tmp)
check("the_address_does_not_exist_without_the_switch", call("PUT", "/api/sim/today", {"today": "2026-08-01"})[0] == 404)
check("and_the_date_is_unchanged", clock.today() == __import__("datetime").date.today().isoformat())
server.shutdown()

# ---- 2. with the switch, in a fresh interpreter (the switch is read when the handler is made)
child = r'''
import json, os, sys, tempfile, threading, urllib.request, urllib.error
sys.path.insert(0, os.getcwd())
os.environ["HR_SIMULATION"] = "1"
from http.server import ThreadingHTTPServer
from hr_core.api import make_handler
from hr_core.service import HRService
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"
tmp = tempfile.mkdtemp(prefix="hr_sim_on_")
svc = HRService(os.path.join(tmp, "data"), COMPANY, "NILE", "Nile Home", backup_dir=os.path.join(tmp, "backups"))
svc.bootstrap_admin("admin", "Admin", "Admin-2026!x")
svc.auth.commit("admin", "x", [{"entity": "user", "code": "admin", "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", "admin")["ver"]}])
svc.create_user(svc.login("admin", "Admin-2026!x")[1], "viewer", "Viewer", "Admin-2026!x", "viewer")
svc.auth.commit("admin", "x", [{"entity": "user", "code": "viewer", "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", "viewer")["ver"]}])
tok = svc.login("admin", "Admin-2026!x")[0]
vtok = svc.login("viewer", "Admin-2026!x")[0]
server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % server.server_address[1]
def call(method, path, body=None, token=tok):
    req = urllib.request.Request(base + path, method=method, data=None if body is None else json.dumps(body).encode(), headers={"Content-Type": "application/json", "Cookie": "hr_sid=" + token})
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
out = {}
out["viewer_refused"] = call("PUT", "/api/sim/today", {"today": "2026-08-01"}, vtok)[0]
out["bad_date"] = call("PUT", "/api/sim/today", {"today": "31/07/2026"})[0]
out["set"] = call("PUT", "/api/sim/today", {"today": "2026-08-01"})
out["get"] = call("GET", "/api/sim/today")[1]["today"]
out["registry_today"] = svc.registry.today()
print(json.dumps(out))
'''
r = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True, cwd=ROOT, env=dict(os.environ, PYTHONPATH=str(ROOT / "vendor.zip")))
check("the_simulation_child_ran", r.returncode == 0, r.stderr[-800:])
out = json.loads(r.stdout.strip().splitlines()[-1])
check("only_the_right_to_change_settings_moves_the_date", out["viewer_refused"] == 403, out)
check("a_date_that_is_not_a_date_is_refused", out["bad_date"] == 400, out)
check("in_simulation_the_date_moves", out["set"][0] == 200 and out["set"][1]["today"] == "2026-08-01" and out["get"] == "2026-08-01", out)
check("the_registry_follows_it", out["registry_today"] == "2026-08-01", out)

print(json.dumps(results, indent=2))
print("TEST_HR_SIMULATION: all", len(results), "checks passed")
