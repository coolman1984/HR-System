"""Phase 2.5 — HR-System as one installable product: acceptance tests that run on any machine (Linux and Windows CI).

The installed program itself (compiled, installed, no Python, no network) is tested by the Windows installer job in
CI (tools/installed_acceptance.py); this file proves the product logic it is built from:
  one server and one sign-in for everything, the attendance engine unchanged behind it (same numbers as the golden
  file), the company identity rules, the data-version update with its verified pre-update backup, a failure in the
  middle, a power cut in the middle, the recovery installer, start-with-Windows, and the screens' two languages.
Synthetic data only. Standard library only (openpyxl comes from vendor.zip, like the application).
"""

import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from hr_core import upgrade  # noqa: E402
from hr_core.app import Product  # noqa: E402
from hr_core.attendance import ROUTES as ATT_ROUTES, excel_installed  # noqa: E402
from hr_core.home import Home, HomeError  # noqa: E402
from hr_core.registry import Registry, RegistryError  # noqa: E402
from hr_core.service import HRService  # noqa: E402

results = {}
TMP = tempfile.mkdtemp(prefix="hr_delivery_")
MIZAN_COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"
PASSWORD = "Admin-pass-1a"


def check(name, cond, detail=None):
    if not cond:
        raise AssertionError(f"{name}: {detail!r}")
    results[name] = True


def refused(code, fn):
    try:
        fn()
    except (HomeError, RegistryError, upgrade.UpgradeError) as exc:
        return exc.code == code
    return False


def home(name):
    return Home(os.path.join(TMP, name))


# ================================================================== 1. company identity
h = home("identity")
check("local_identity_is_a_provisional_uuid7", (lambda c: c["source"] == "local" and c["provisional"] and c["id"][14] == "7")(
    h.set_company("local", "nile", "Nile Electronics")))
check("identity_is_set_once", refused("company.set", lambda: h.set_company("local", "NILE", "Nile")))
h2 = home("identity-owner")
check("owner_identity_needs_the_owners_id", refused("company.id", lambda: h2.set_company("owner", "NILE", "Nile", "not-an-id", "mizan")))
check("owner_identity_names_its_owner", refused("company.owner", lambda: h2.set_company("owner", "NILE", "Nile", MIZAN_COMPANY, "excel")))
c2 = h2.set_company("owner", "NILE", "Nile", MIZAN_COMPANY.upper(), "mizan")
check("owner_identity_is_the_owners_id_not_provisional", c2["id"] == MIZAN_COMPANY and not c2["provisional"] and c2["owner_app"] == "mizan")
reg = Registry(os.path.join(TMP, "identity-reg"), MIZAN_COMPANY, "NILE", "Nile")
reg.close()
check("records_refuse_to_open_under_another_company",
      refused("company.mismatch", lambda: Registry(os.path.join(TMP, "identity-reg"), "11111111-2222-4333-8444-555555555555", "NILE", "Nile")))
check("settings_are_checked", refused("config.language", lambda: h.set(language="fr")) and refused("config.backup_hours", lambda: h.set(backup_hours=0))
      and refused("config.field", lambda: h.set(company="x")))

# ================================================================== 2. one server, one sign-in
H = home("product")
P = Product(H)
SERVER = P.serve("127.0.0.1", 0)
PORT = SERVER.server_address[1]
threading.Thread(target=SERVER.serve_forever, daemon=True).start()


class Client:
    def __init__(self, port=None):
        self.cookie, self.port = None, port or PORT

    def call(self, method, path, body=None, raw=None, ctype=None, origin=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        headers = {}
        if raw is not None:
            data, headers["Content-Type"] = raw, ctype or "application/octet-stream"
        elif method != "GET":
            data, headers["Content-Type"] = json.dumps(body or {}).encode(), "application/json"
        else:
            data = None
        if self.cookie:
            headers["Cookie"] = self.cookie
        if origin:
            headers["Origin"] = origin
        c.request(method, path, data, headers)
        r = c.getresponse()
        payload = r.read()
        if r.getheader("Set-Cookie", "").startswith("hr_sid="):
            self.cookie = r.getheader("Set-Cookie").split(";")[0]
        try:
            out = json.loads(payload)
        except ValueError:
            out = payload
        return r.status, out, r


anon = Client()
s, info, _ = anon.call("GET", "/api/info")
check("setup_mode_before_the_company_exists", s == 200 and info["setup_needed"] and info["company"] is None)
s, _, _ = anon.call("GET", "/api/employee")
check("setup_mode_serves_no_data", s == 503)


class FarServer(ThreadingHTTPServer):
    def get_request(self):  # every request looks like it came from another computer on the network
        sock, _ = super().get_request()
        return sock, ("10.1.2.3", 40000)


far = FarServer(("127.0.0.1", 0), SERVER.RequestHandlerClass)
threading.Thread(target=far.serve_forever, daemon=True).start()
s, out, _ = Client(far.server_address[1]).call("POST", "/api/setup/install", {"company": {"source": "local", "code": "NILE", "name": "Nile"},
                                                                            "admin": {"username": "admin1", "password": PASSWORD}})
check("setup_only_from_the_server_machine", s == 403 and out["error"] == "setup.local_only" and not H.company(), out)
far.shutdown()
s, out, _ = anon.call("POST", "/api/setup/install", {"company": {"source": "local", "code": "NILE", "name": "Nile"}, "admin": {"username": "admin1", "password": "short"}})
check("a_refused_setup_writes_nothing", s == 400 and not H.company(), out)
s, out, _ = anon.call("POST", "/api/setup/install", {"company": {"source": "local", "code": "NILE", "name": "Nile"}, "admin": {"username": "x", "password": PASSWORD}})
check("a_wrong_administrator_name_writes_no_company_identity", s == 400 and not H.company(), out)  # Codex review, PR 4
s, out, _ = anon.call("POST", "/api/setup/install", {"company": {"source": "owner", "owner_app": "mizan", "id": MIZAN_COMPANY, "code": "NILE", "name": "Nile Electronics"},
                                                     "admin": {"username": "admin1", "display_name": "Admin", "password": PASSWORD}})
check("setup_with_the_owners_identity", s == 201 and H.company()["id"] == MIZAN_COMPANY, out)
check("fresh_installation_is_at_the_current_data_version", upgrade.read_version(H.data) == upgrade.DATA_VERSION)
s, out, _ = anon.call("POST", "/api/setup/install", {"company": {"source": "local", "code": "OTHER", "name": "Other"}, "admin": {"username": "admin2", "password": PASSWORD}})
check("setup_happens_once", s in (400, 404, 503) and H.company()["code"] == "NILE", (s, out))

admin = Client()
s, me, _ = admin.call("POST", "/api/login", {"username": "admin1", "password": PASSWORD})
check("administrator_has_every_right", s == 200 and {"hr.attendance.read", "hr.attendance.upload", "admin.settings.manage"} <= set(me["permissions"]), me)
s, page, r = anon.call("GET", "/")
check("screens_are_served_with_a_strict_policy", s == 200 and b"/ui/app.js" in page and "script-src 'self';" in r.getheader("Content-Security-Policy", ""))
check("no_inline_script_in_the_screens", not re.search(rb"<script(?![^>]*\bsrc=)", page))
s, _, _ = anon.call("GET", "/ui/../hr_core/app.py")
check("only_screen_files_are_served", s == 404)

# the attendance application answers from the same server, only after sign-in and only with its right
for (method, path), right in sorted(ATT_ROUTES.items()):
    s, _, _ = anon.call(method, path, {} if method == "POST" else None)
    check(f"attendance_{method}_{path}_needs_sign_in", s == 401, s)
s, _, r = anon.call("GET", "/attendance")
check("attendance_page_sends_strangers_to_sign_in", s == 302 and r.getheader("Location", "").startswith("/#/login"))
engine_routes = set(re.findall(r'route (?:==|in \() ?"(/api/[a-z_.]+)"', (ROOT / "engine.py").read_text(encoding="utf-8")))
api_patterns = re.findall(r'@route\("\w+", "([^"]+)"\)', (ROOT / "hr_core" / "api.py").read_text(encoding="utf-8"))
check("no_attendance_address_collides_with_the_hr_api", engine_routes and not [p for p in engine_routes for a in api_patterns if re.fullmatch(a, p)]
      and engine_routes <= {p for _, p in ATT_ROUTES}, engine_routes)

assert admin.call("POST", "/api/admin/users", {"username": "viewer1", "display_name": "V", "password": "Viewer-pass-1a", "profile": "viewer"})[0] == 201
assert admin.call("POST", "/api/admin/users", {"username": "officer1", "display_name": "O", "password": "Officer-pass-1a", "profile": "hr_officer"})[0] == 201
viewer, officer = Client(), Client()
viewer.call("POST", "/api/login", {"username": "viewer1", "password": "Viewer-pass-1a"})
viewer.call("POST", "/api/password", {"old": "Viewer-pass-1a", "new": "Viewer-pass-2b"})
officer.call("POST", "/api/login", {"username": "officer1", "password": "Officer-pass-1a"})
officer.call("POST", "/api/password", {"old": "Officer-pass-1a", "new": "Officer-pass-2b"})
CLEAN = ROOT / "inputs/hr-factory-synthetic-dataset/01_CLEAN_BASELINE/05_Time_Attendance_Leave.xlsx"
s, out, _ = viewer.call("POST", "/api/upload?filename=05_Time_Attendance_Leave.xlsx", raw=CLEAN.read_bytes())
check("a_viewer_cannot_upload_attendance", s == 403 and out["error"] == "perm.denied", (s, out))
s, _, _ = viewer.call("GET", "/api/state")
check("a_viewer_can_see_attendance", s == 200)
s, out, _ = officer.call("POST", "/api/upload?filename=05_Time_Attendance_Leave.xlsx", raw=CLEAN.read_bytes(), origin="http://evil.example")
check("a_cross_site_upload_is_refused", s == 403 and out["error"] == "origin.refused")
s, out, _ = officer.call("POST", "/api/upload?filename=05_Time_Attendance_Leave.xlsx", raw=CLEAN.read_bytes())
golden = json.load(open(ROOT / "migration" / "golden_behaviour.json", encoding="utf-8"))["1_clean_attendance_only"]
same = {k: (out.get(k) == golden.get(k)) for k in ("kpis", "charts", "current_count", "accepted_count", "rejected_count", "reconciliation", "insights", "warnings")}
check("attendance_through_the_one_server_gives_the_golden_numbers", s == 200 and all(same.values()), same)
rows = sorted(P.attendance.engine.current_rows(), key=lambda r: json.dumps(r, sort_keys=True, default=str))
check("attendance_rows_are_the_golden_rows", hashlib.sha256(json.dumps(rows, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
      == golden["_current_rows_sha256"])
def attendance_events(at_least):
    """The attendance lines of the audit. The server writes them just AFTER the engine's answer went out, so a fast
    client can look before they exist (seen on Windows, 2026-09-28): wait until `at_least` are there (15 s at most)."""
    deadline = time.time() + 15
    while True:
        found = [a for a in P.service.journal.audit_entries("activity", 50) if a["event"].startswith("attendance.")]
        if len(found) >= at_least or time.time() > deadline:
            return found
        time.sleep(0.05)


check("an_upload_is_audited_with_its_person", any(a["event"] == "attendance.uploaded" and a["actor"] == "officer1" for a in attendance_events(1)))
s, out, _ = officer.call("POST", "/api/upload?filename=05_Time_Attendance_Leave.xlsx", raw=CLEAN.read_bytes())
s2, out2, _ = officer.call("POST", "/api/upload?filename=broken.csv", raw=b"\xff\xfe not a table")
events = attendance_events(3)
check("a_refused_or_duplicate_upload_is_not_recorded_as_a_change", out.get("duplicate_upload") and s2 == 400
      and sum(1 for a in events if a["event"] == "attendance.uploaded") == 1 and sum(1 for a in events if a["event"] == "attendance.refused") == 2,
      [(a["event"], a["detail"]) for a in events])  # Codex review, PR 4

s, _, _ = viewer.call("GET", "/api/admin/settings")
check("settings_need_their_right", s == 403)
s, out, _ = admin.call("PUT", "/api/admin/settings", {"autostart": False, "language": "ar"})
check("settings_are_saved_outside_the_program", s == 200 and not out["autostart"] and H.config()["language"] == "ar")
s, out, _ = admin.call("PUT", "/api/admin/settings", {"backup_hours": 0})
check("a_wrong_setting_is_refused_plainly", s == 400 and out["error"] == "config.backup_hours", out)
s, health, _ = admin.call("GET", "/api/admin/health")
check("health_shows_version_company_attendance_and_excel", s == 200 and health["product"]["data_version"] == upgrade.DATA_VERSION
      and health["company"]["source"] == "owner" and health["attendance"]["history_file"] and "excel_desktop" in health["attendance"], health.get("product"))
check("excel_is_detected_not_assumed", excel_installed() is None if os.name != "nt" else isinstance(excel_installed(), bool))

# a PC without Microsoft Excel: a file only Excel could open is refused at once (the engine would wait minutes for
# Excel, holding the attendance lock - seen in Windows CI); ordinary workbooks still go to the engine unchanged
import hr_core.attendance as attendance_module  # noqa: E402
real_excel = attendance_module.excel_installed
attendance_module.excel_installed = lambda: False
try:
    t0 = time.time()
    s, out, _ = officer.call("POST", "/api/upload?filename=protected.xlsx", raw=b"\xd0\xcf\x11\xe0 an OLE file, not a zip package")
    s3, out3, _ = officer.call("POST", "/api/upload?filename=old.xls", raw=b"\xd0\xcf\x11\xe0")
    fast = time.time() - t0 < 30
    s4, out4, _ = officer.call("POST", "/api/upload?filename=05_Time_Attendance_Leave.xlsx", raw=CLEAN.read_bytes())
finally:
    attendance_module.excel_installed = real_excel
check("without_excel_a_file_only_excel_opens_is_refused_at_once", s == 400 and out["error"] == "attendance.needs_excel" and s3 == 400 and fast, (s, out))
check("without_excel_an_ordinary_workbook_still_reaches_the_engine", s4 == 200 and out4.get("duplicate_upload"), (s4, out4))

# backups carry the attendance history, never half an upload
s, made, _ = admin.call("POST", "/api/admin/backups")
check("a_backup_holds_the_attendance_history", s == 201 and "history.db" in made["manifest"]["files"] and made["rehearsal"]["ok"], made.get("manifest", {}).get("files"))
# Deterministic, not timed (a timed version passed a planted bug on a slow Windows disk): watch the copies. While an
# upload holds the attendance lock, the backup copies the journal files but must not copy history.db.
from hr_core import backup as backup_module  # noqa: E402
copies, real_copy = [], backup_module._copy_db
backup_module._copy_db = lambda src, dst: (real_copy(src, dst), copies.append(os.path.basename(dst)))
finished = []
try:
    with P.attendance.lock:  # an upload is running
        t = threading.Thread(target=lambda: finished.append(P.service.backups.create("test", "manual")))
        t.start()
        deadline = time.time() + 60
        while time.time() < deadline and "hr_journal.db" not in copies:
            time.sleep(0.05)
        time.sleep(1.0)  # time enough to copy history.db too, if the lock did not stop it
        copied_during_upload = "history.db" in copies
    t.join()
finally:
    backup_module._copy_db = real_copy
check("a_backup_waits_for_a_running_upload", "hr_journal.db" in copies and not copied_during_upload
      and finished and "history.db" in finished[0]["manifest"]["files"], copies)

# ------------------------------------------------------------------ the link to manufacturing (GMES), set on a screen
# Ecosystem plan, Phase A: the installed product publishes by itself (hr_core/eco_link.py). A fake GMES inbox stands in
# for GMES (the real one is exercised by GMES's own end-to-end test); the product's own path is used throughout.
import socket  # noqa: E402
from http.server import BaseHTTPRequestHandler  # noqa: E402

GMES_KEY = "gk_Phase-A-integration-7f3c91e2"  # distinctive: searched for in every place it must never be


class GmesInbox(BaseHTTPRequestHandler):
    seen, keys, sources = set(), [], set()

    def log_message(self, *args):
        pass

    def do_POST(self):
        GmesInbox.keys.append(self.headers.get("x-eco-key"))
        events = json.loads(self.rfile.read(int(self.headers["content-length"])))["events"]
        results = []
        for ev in events:
            GmesInbox.sources.add(ev["source"])
            results.append({"id": ev["id"], "result": "duplicate" if ev["id"] in GmesInbox.seen else "applied"})
            GmesInbox.seen.add(ev["id"])
        data = json.dumps({"results": results}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def closed_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


s, st, _ = admin.call("GET", "/api/admin/integration")
check("integration_is_off_by_default_hr_works_alone", s == 200 and st["gmes_url"] == "" and not st["enabled"] and not st["running"]
      and not st["key_set"] and P.link is not None and not P.link.running and not os.path.exists(os.path.join(H.data, "eco_outbox.db")), st)
s, out, _ = admin.call("POST", "/api/admin/integration/run")
check("send_now_without_an_address_is_refused", s == 400 and out["error"] == "integration.disabled", out)
answers = [viewer.call(m, p, b)[0] for m, p, b in (("GET", "/api/admin/integration", None), ("PUT", "/api/admin/integration", {"gmes_url": "http://127.0.0.1:1", "key": GMES_KEY}),
                                                   ("POST", "/api/admin/integration/run", {}))] + [anon.call("GET", "/api/admin/integration")[0]]
check("integration_needs_the_settings_right", answers == [403, 403, 403, 401] and H.config()["eco"]["gmes_url"] == "" and not P.link.keys.exists(), answers)
wrong = [({"gmes_url": "ftp://gmes.local"}, "config.eco_url"), ({"gmes_url": "http://user:secret@gmes.local"}, "config.eco_url"),
         ({"gmes_url": "gmes.local:4700"}, "config.eco_url"), ({"gmes_url": "http://gmes.local:99999"}, "config.eco_url"),
         ({"interval_seconds": 9}, "config.eco_interval"), ({"interval_seconds": 3601}, "config.eco_interval"), ({"interval_seconds": "often"}, "config.eco_interval"),
         ({"node": "hr main"}, "config.eco_node"), ({"key": "has a space"}, "integration.key"), ({"surprise": 1}, "config.field"),
         ({"gmes_url": "http://127.0.0.1:4700", "key": "bad key"}, "integration.key")]
got = [(admin.call("PUT", "/api/admin/integration", body)[1] or {}).get("error") for body, _ in wrong]
check("integration_settings_are_validated_and_a_refusal_writes_nothing", got == [code for _, code in wrong]
      and H.config()["eco"] == {"gmes_url": "", "node": "hr-main", "interval_seconds": 60} and not P.link.keys.exists() and not P.link.running, got)

# GMES down: the address is saved, the link starts, everything waits in the outbox (the 200 attendance days uploaded above;
# no employee file was uploaded and the registry is empty, so no employee is invented)
down_url = f"http://127.0.0.1:{closed_port()}"
s, st, _ = admin.call("PUT", "/api/admin/integration", {"gmes_url": down_url + "/", "node": "hr-test", "interval_seconds": 3600, "key": GMES_KEY})
check("an_address_from_the_screen_starts_the_link", s == 200 and st["running"] and st["enabled"] and st["key_set"] and st["gmes_url"] == down_url
      and st["node"] == "hr-test" and H.config()["eco"]["interval_seconds"] == 3600, st)
check("the_api_never_returns_the_gmes_key", "key" not in st and GMES_KEY not in json.dumps(st), sorted(st))
s, rep, _ = admin.call("POST", "/api/admin/integration/run")
check("gmes_down_everything_waits_in_the_outbox", s == 200 and "stopped_by" in rep and rep["outbox"].get("pending", 0) >= 200
      and not rep["outbox"].get("delivered"), rep)

# GMES comes back: the product delivers by itself (the thread's first cycle runs when it starts), with the stored key
inbox = ThreadingHTTPServer(("127.0.0.1", 0), GmesInbox)
threading.Thread(target=inbox.serve_forever, daemon=True).start()
s, st, _ = admin.call("PUT", "/api/admin/integration", {"gmes_url": f"http://127.0.0.1:{inbox.server_address[1]}", "key": ""})
check("an_empty_key_field_keeps_the_stored_key", s == 200 and st["key_set"] and st["running"], st)
deadline = time.time() + 120
while time.time() < deadline and not (P.link.last and P.link.last.get("sent") and not P.link.last.get("outbox", {}).get("pending")):
    time.sleep(0.2)
s, st, _ = admin.call("GET", "/api/admin/integration")
check("the_product_delivers_by_itself_when_gmes_is_back", s == 200 and st["outbox"].get("pending", 0) == 0 and st["outbox"].get("delivered", 0) >= 200
      and st["last_delivered_at"] and st["last"]["origin"] == "automatic" and len(GmesInbox.seen) >= 200, st)
check("gmes_receives_the_stored_key_and_this_node", set(GmesInbox.keys) == {GMES_KEY}
      and GmesInbox.sources == {f"eco://{MIZAN_COMPANY}/hr/hr-test"}, (len(GmesInbox.keys), GmesInbox.sources))
s, rep, _ = admin.call("POST", "/api/admin/integration/run")
check("send_now_sends_nothing_twice", s == 200 and rep["sent"] == 0 and rep["staged"] == 0 and "stopped_by" not in rep and "error" not in rep, rep)
audited = [a for a in P.service.journal.audit_entries(None, 500) if a["event"] in ("integration.changed", "integration.sent")]
check("integration_changes_and_sends_are_audited_without_the_key",
      any(a["event"] == "integration.changed" and a["actor"] == "admin1" and a["detail"]["key"] == "changed" for a in audited)
      and any(a["event"] == "integration.sent" for a in audited) and GMES_KEY not in json.dumps(audited), audited[:2])
s, made, _ = admin.call("POST", "/api/admin/backups")
key_file = os.path.realpath(P.link.keys.path)
leaks = []
for folder, _, names in os.walk(H.path):
    for name in names:
        path = os.path.join(folder, name)
        if os.path.realpath(path) != key_file:
            try:
                if GMES_KEY.encode() in open(path, "rb").read():
                    leaks.append(os.path.relpath(path, H.path))
            except OSError:
                pass
check("the_gmes_key_is_never_in_config_logs_audit_or_a_backup", s == 201 and not leaks and os.path.isfile(key_file)
      and os.path.relpath(key_file, os.path.realpath(H.data)) == os.path.join("node", "gmes.key")
      and not [n for n in os.listdir(os.path.join(H.backups, made["name"])) if "gmes" in n or n == "node"] and GMES_KEY not in open(H.config_path, encoding="utf-8").read()
      and os.path.isfile(os.path.join(H.logs, "eco-link.log")), leaks)
check("the_gmes_key_is_protected_on_windows", os.name != "nt" or GMES_KEY.encode() not in open(key_file, "rb").read())

# a lost attendance history comes back from the newest verified backup, and it is audited. Tried on a copy of the
# installation in a new process: this process's engine is bound to the original folder and keeps its file open
# (Windows cannot delete an open file), exactly like the real program, which is stopped before such a repair.
SERVER.shutdown()
SERVER.server_close()
link_before = P.link
P.close()
check("closing_the_product_stops_the_link", not link_before.running and P.link is None)
P2 = Product(H)
P2.open()
check("an_installation_with_an_address_starts_the_link_when_it_opens", P2.link.running and P2.report["eco_link"] is True)
P2.close()
H.set(eco={"gmes_url": ""})  # HR on its own again: the copies below must not publish
P2 = Product(H)
P2.open()
check("an_empty_address_starts_nothing_when_it_opens", not P2.link.running and P2.report["eco_link"] is False and P2.link.keys.exists())
P2.close()
inbox.shutdown()
lost = os.path.join(TMP, "product-lost-history")
shutil.copytree(H.path, lost)
os.remove(os.path.join(lost, "data", "history.db"))
probe = ("import json, sys; sys.path.insert(0, %r)\nfrom hr_core.app import Product\nfrom hr_core.home import Home\n"
         "p = Product(Home(%r)); p.open()\nimport os\nprint(json.dumps({'file': os.path.isfile(p.attendance.path), "
         "'from': p.report['attendance_recovered_from'], 'audited': any(a['event'] == 'attendance.recovered' for a in "
         "p.service.journal.audit_entries('system', 50))}))\np.close()\n") % (str(ROOT), lost)
r = subprocess.run([sys.executable, "-c", probe], env=dict(os.environ, PYTHONPATH=str(ROOT / "vendor.zip")), capture_output=True, timeout=300)
out = json.loads(r.stdout.decode().strip().splitlines()[-1]) if r.returncode == 0 else {"error": r.stderr.decode()[-500:]}
check("a_lost_attendance_history_is_recovered_from_a_backup", out.get("file") and out.get("from") and out.get("audited"), out)

# a config.json edited to another company id: the program explains, the data is untouched
before = hashlib.sha256(open(os.path.join(H.data, "hr_journal.db"), "rb").read()).hexdigest()
cfg = json.load(open(H.config_path, encoding="utf-8"))
cfg["company"]["id"] = "11111111-2222-4333-8444-555555555555"
json.dump(cfg, open(H.config_path, "w", encoding="utf-8"))
P3 = Product(H)
srv3 = P3.serve("127.0.0.1", 0)
check("an_edited_company_id_stops_the_program_with_a_message", P3.error and P3.error["code"] == "company.mismatch" and P3.service is None
      and hashlib.sha256(open(os.path.join(H.data, "hr_journal.db"), "rb").read()).hexdigest() == before, P3.error)
srv3.server_close()

# ================================================================== 3. updating the data
def opener(hm):
    c = hm.company()
    return lambda: HRService(hm.data, c["id"], c["code"], c["name"], backup_dir=hm.backups)


def perms(hm, code):
    svc = opener(hm)()
    try:
        return set(svc.auth._get("profile", code)["perms"])
    finally:
        svc.close()


def v0_by_journal(name):
    """An installation as phase 2 left it: no data version file, and built-in profiles journaled WITHOUT the rights
    phase 2.5 added (written as the phase-2 program wrote them: one journal line carrying the rows)."""
    hm = home(name)
    hm.set_company("local", "NILE", "Nile")
    svc = HRService(hm.data, hm.company()["id"], "NILE", "Nile", backup_dir=hm.backups)
    svc.bootstrap_admin("admin1", "Admin", PASSWORD)
    from hr_core.auth import ADDED_IN_DATA_VERSION_1
    ops = []
    for code, added in sorted(ADDED_IN_DATA_VERSION_1.items()):
        cur = svc.auth._get("profile", code)
        ops.append({"entity": "profile", "row": {**cur, "perms": sorted(set(cur["perms"]) - set(added)), "ver": cur["ver"] + 1}})
    seq = svc.journal.append("system", "Built-in profiles (as phase 2 wrote them)", ops)
    svc.auth._fold(seq, ops)
    svc.close()
    os.remove(os.path.join(hm.data, upgrade.VERSION_FILE)) if os.path.exists(os.path.join(hm.data, upgrade.VERSION_FILE)) else None
    return hm


hm = v0_by_journal("v0")
svc, rep = upgrade.prepare(hm, opener(hm))
kept = [b for b in svc.backups.list() if b["kept_forever"]]
check("an_update_starts_with_a_verified_rehearsed_backup_kept_forever", rep["from"] == 0 and rep["to"] == upgrade.DATA_VERSION and kept
      and kept[0]["reason"] == "pre-update" and kept[0]["rehearsal"]["ok"], rep)
check("the_update_gives_older_profiles_the_new_rights", {"hr.attendance.read", "hr.attendance.upload", "admin.settings.manage"} <= set(svc.auth._get("profile", "administrator")["perms"])
      and "hr.attendance.read" in svc.auth._get("profile", "viewer")["perms"])
check("the_update_is_journaled_and_audited", any(a["event"] == "upgrade.done" for a in svc.journal.audit_entries("system", 50))
      and upgrade.read_version(hm.data) == upgrade.DATA_VERSION and not os.path.exists(os.path.join(hm.data, upgrade.MARKER)))
for _ in range(16):
    svc.backups.create("test", "manual")
check("retention_never_removes_a_pre_update_backup", len(svc.backups.list()) == 15 and any(b["kept_forever"] for b in svc.backups.list()))
check("the_latest_backup_is_the_newest_whatever_its_kind", not svc.backups.latest()["kept_forever"]
      and svc.backups.list()[0]["created_at"] >= svc.backups.list()[-1]["created_at"])  # Codex review, PR 4
svc.close()
svc, rep = upgrade.prepare(hm, opener(hm))
check("an_up_to_date_installation_starts_without_a_new_backup", "backup" not in rep and len([b for b in svc.backups.list() if b["kept_forever"]]) == 1)
svc.close()

upgrade.write_version(hm.data, 99)
check("data_from_a_newer_program_is_refused", refused("data.newer", lambda: upgrade.prepare(hm, opener(hm))) and upgrade.read_version(hm.data) == 99)
upgrade.write_version(hm.data, upgrade.DATA_VERSION)

# a failure in the middle puts everything back exactly as the pre-update backup holds it
hm = v0_by_journal("failure")
before_perms = perms(hm, "administrator")
os.environ.update({"HR_TEST_HOOKS": "1", "HR_UPGRADE_FAULT": "fail:1"})
try:
    failed = refused("upgrade.failed", lambda: upgrade.prepare(hm, opener(hm)))
finally:
    os.environ.pop("HR_UPGRADE_FAULT")
svc = opener(hm)()
check("a_failed_update_puts_the_data_back", failed and set(svc.auth._get("profile", "administrator")["perms"]) == before_perms
      and upgrade.read_version(hm.data) == 0 and json.load(open(os.path.join(hm.data, upgrade.VERSION_FILE)))["data_version"] == 0
      and not os.path.exists(os.path.join(hm.data, upgrade.MARKER)) and svc.journal.verify()["ok"])
check("a_failed_update_keeps_its_backup", any(b["kept_forever"] for b in svc.backups.list()))
svc.close()
svc, rep = upgrade.prepare(hm, opener(hm))
check("after_a_failure_the_next_start_updates_cleanly", upgrade.read_version(hm.data) == upgrade.DATA_VERSION and "admin.settings.manage" in svc.auth._get("profile", "administrator")["perms"])
svc.close()

# a power cut after a step wrote its line but before the version was written: the next start finishes, once
hm = v0_by_journal("powercut")
script = ("import sys; sys.path.insert(0, %r)\nfrom hr_core import upgrade\nfrom hr_core.home import Home\nfrom hr_core.service import HRService\n"
          "hm = Home(%r); c = hm.company()\nupgrade.prepare(hm, lambda: HRService(hm.data, c['id'], c['code'], c['name'], backup_dir=hm.backups))\n") % (str(ROOT), hm.path)
env = dict(os.environ, HR_TEST_HOOKS="1", HR_UPGRADE_FAULT="stall:1", PYTHONPATH=str(ROOT / "vendor.zip"))
proc = subprocess.Popen([sys.executable, "-c", script], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def line_count():
    import sqlite3
    try:
        db = sqlite3.connect(Path(os.path.join(hm.data, "hr_journal.db")).as_uri() + "?mode=ro", uri=True)
        try:
            return db.execute("SELECT COUNT(*) FROM journal WHERE label LIKE 'Data version 1: profile administrator%'").fetchone()[0]
        finally:
            db.close()
    except Exception:
        return 0


deadline = time.time() + 120
while time.time() < deadline and line_count() == 0:
    time.sleep(0.2)
proc.kill()  # the power goes off
proc.wait()
check("the_power_cut_happened_mid_update", line_count() == 1 and os.path.exists(os.path.join(hm.data, upgrade.MARKER)) and upgrade.read_version(hm.data) == 0)
svc, rep = upgrade.prepare(hm, opener(hm))
check("after_a_power_cut_the_update_finishes_once", line_count() == 1 and upgrade.read_version(hm.data) == upgrade.DATA_VERSION
      and not os.path.exists(os.path.join(hm.data, upgrade.MARKER)) and svc.journal.verify()["ok"]
      and any(a["event"] == "upgrade.resumed" for a in svc.journal.audit_entries("system", 50)))
svc.close()

# putting files back is refused when anyone but the update wrote after the backup
hm = v0_by_journal("diverged")
svc = opener(hm)()
made = svc.backups.create("upgrade", "pre-update")
svc.save(svc.auth._get("user", "admin1"), "job", "J1", {"title": "Welder"})
svc.close()
marker = {"from": 0, "to": 1, "backup": made["name"], "journal_hash": made["manifest"]["journal"]["last_hash"]}
json.dump(marker, open(os.path.join(hm.data, upgrade.MARKER), "w"))
journal_before = hashlib.sha256(open(os.path.join(hm.data, "hr_journal.db"), "rb").read()).hexdigest()
check("files_are_never_put_back_over_other_peoples_work", refused("upgrade.diverged", lambda: upgrade._put_back(hm, marker))
      and hashlib.sha256(open(os.path.join(hm.data, "hr_journal.db"), "rb").read()).hexdigest() == journal_before)

# ================================================================== 4. the recovery installer
hm = home("recovery")


def pending(version, content=b"setup program", sha=None):
    d = os.path.join(hm.recovery, "pending")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "HR-System-Setup.exe"), "wb").write(content)
    json.dump({"file": "HR-System-Setup.exe", "version": version, "sha256": sha or hashlib.sha256(content).hexdigest()}, open(os.path.join(d, "installer.json"), "w"))


pending("0.9.0")
check("an_installer_of_another_version_is_not_kept", upgrade.promote_installer(hm)["promoted"] is False and upgrade.known_good(hm) is None)
pending(upgrade.VERSION, sha="0" * 64)
check("an_installer_that_does_not_match_its_hash_is_not_kept", upgrade.promote_installer(hm)["promoted"] is False and upgrade.known_good(hm) is None)
pending(upgrade.VERSION, b"good setup")
first = upgrade.promote_installer(hm)
pending(upgrade.VERSION, b"good setup, second build")
upgrade.promote_installer(hm)
kg = upgrade.known_good(hm)
check("only_one_known_good_installer_with_version_and_hash", first["promoted"] and kg["intact"] and kg["version"] == upgrade.VERSION
      and os.listdir(hm.recovery) == ["known-good"] and kg["sha256"] == hashlib.sha256(b"good setup, second build").hexdigest())
open(os.path.join(hm.recovery, "known-good", "HR-System-Setup.exe"), "ab").write(b"x")
check("a_damaged_recovery_installer_is_reported", upgrade.known_good(hm)["intact"] is False)

# ================================================================== 5. start with Windows, one entry point
hm = home("autostart")
hm.set(autostart=False)
t0 = time.time()
r = subprocess.run([sys.executable, str(ROOT / "hr_main.py"), "--background", "--port", "0"], env=dict(os.environ, HR_HOME=hm.path,
                   PYTHONPATH=str(ROOT / "vendor.zip")), capture_output=True, timeout=60)
check("start_with_windows_switched_off_starts_nothing", r.returncode == 0 and time.time() - t0 < 30 and not r.stdout, r.stdout)
r = subprocess.run([sys.executable, str(ROOT / "hr_main.py"), "tool", "data-version"], env=dict(os.environ, HR_HOME=H.path, PYTHONPATH=str(ROOT / "vendor.zip")),
                   capture_output=True, timeout=120)
check("the_entry_point_has_maintenance_tools", r.returncode == 0 and json.loads(r.stdout)["data_version"] == upgrade.DATA_VERSION, r.stderr[-300:])

# Browser startup is verified without executing the GUI helper.
import hr_main
from unittest.mock import patch
from types import SimpleNamespace

with patch.object(hr_main.os.path, "isfile", return_value=True), patch.object(hr_main.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as launch:
    check("source_startup_uses_only_the_mandatory_chrome_helper", hr_main._open_chrome("http://127.0.0.1:8790/")
          and launch.call_args.args[0][0] == sys.executable
          and launch.call_args.args[0][1].endswith("windows-chrome-launcher\\scripts\\open_chrome.py"))
with patch.object(hr_main.os.path, "isfile", return_value=True), patch.object(hr_main.sys, "frozen", True, create=True), \
        patch.object(hr_main.shutil, "which", side_effect=lambda name: "C:/Python/python.exe" if name == "python" else None), \
        patch.object(hr_main.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as launch:
    check("frozen_startup_uses_a_child_python_not_the_product_exe", hr_main._open_chrome("http://127.0.0.1:8790/")
          and launch.call_args.args[0][0] == "C:/Python/python.exe")
with patch.object(hr_main.os.path, "isfile", return_value=False), patch.object(hr_main.subprocess, "run") as launch, patch("builtins.print") as printed:
    check("missing_chrome_helper_reports_the_url_without_opening_a_handler", hr_main._open_chrome("http://127.0.0.1:8790/") is False
          and not launch.called and "http://127.0.0.1:8790/" in printed.call_args.args[0])
with patch.object(hr_main, "_running", return_value=True), patch.object(hr_main, "_open_chrome") as launch, patch("hr_core.home.Home", return_value=hm):
    check("no_browser_on_a_second_start_never_opens_chrome", hr_main.main(["--no-browser"]) == 0 and not launch.called)
fake_server = SimpleNamespace(serve_forever=lambda: None, server_close=lambda: None)
fake_product = SimpleNamespace(error=None, serve=lambda **kw: fake_server, close=lambda: None)
with patch.object(hr_main, "_running", return_value=False), patch.object(hr_main, "_open_chrome") as launch, \
        patch("hr_core.home.Home", return_value=hm), patch("hr_core.app.Product", return_value=fake_product):
    check("no_browser_starts_the_server_even_when_windows_autostart_is_off", hr_main.main(["--no-browser"]) == 0 and not launch.called)

# ================================================================== 6. the screens and their two languages
en = json.load(open(ROOT / "hr_core/web/i18n/en.json", encoding="utf-8"))
ar = json.load(open(ROOT / "hr_core/web/i18n/ar.json", encoding="utf-8"))
check("english_and_arabic_have_the_same_keys", set(en) == set(ar), sorted(set(en) ^ set(ar)))
check("no_empty_translation", all(str(v).strip() for v in list(en.values()) + list(ar.values())))
check("the_arabic_screens_are_in_arabic", all(re.search("[؀-ۿ]", v) for k, v in ar.items() if not k.startswith("product.") or k == "product.name"))
js = (ROOT / "hr_core/web/app.js").read_text(encoding="utf-8")
used = set(re.findall(r'\bt\("([a-z_]+(?:\.[a-z_]+)+)"', js))
check("every_text_on_the_screens_is_translated", used and used <= set(en), sorted(used - set(en)))
from hr_core.auth import PERMISSIONS  # noqa: E402
check("every_permission_has_a_translated_name", all(f"perm.{p}" in en for p in PERMISSIONS), [p for p in PERMISSIONS if f"perm.{p}" not in en])
web_js = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in (ROOT / "hr_core/web").rglob("*.js")}
check("the_screens_write_server_values_as_text_only", all(not re.search(r"\.innerHTML|outerHTML\s*=|insertAdjacentHTML|document\.write|\beval\(|new Function\(", src)
                                                       for src in web_js.values()), [n for n, src in web_js.items() if "insertAdjacentHTML" in src or "innerHTML" in src])
rights_block = js[js.index("const SOD = "):js.index("const PERM_ACTIONS")]
named_rights = set(re.findall(r'"((?:hr|admin)\.[a-z_]+\.[a-z_]+)"', rights_block))
check("templates_and_separated_duties_name_real_rights", named_rights and named_rights <= set(PERMISSIONS), sorted(named_rights - set(PERMISSIONS)))
codes = set(re.findall(r'^  ([A-Z]{3}\d{4}): \[', js, re.M))
check("every_screen_has_a_subtitle_and_help_in_both_languages", "ADV1010" in codes and all(f"{p}.{c}" in en and f"{p}.{c}" in ar for c in codes for p in ("sub", "about")),
      sorted(c for c in codes if f"about.{c}" not in en))
adv_ids = set(re.findall(r'\badd\("([a-z_]+)"', js))
check("every_advisor_finding_has_its_words", adv_ids and all(f"adv.{i}.{p}" in en for i in adv_ids for p in ("title", "body", "fix")), sorted(i for i in adv_ids if f"adv.{i}.title" not in en))
named = set(re.findall(r'"((?:nav|g|sec|perm_group|door)\.[a-z_]+)"', js))
check("every_menu_and_section_name_is_translated", named and named <= set(en), sorted(named - set(en)))
import hashlib  # noqa: E402
pin = json.load(open(ROOT / "hr_core/eco_ui_pin.json", encoding="utf-8"))
KIT = ROOT / "hr_core/web/eco-ui"
kit = {p.relative_to(KIT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in KIT.rglob("*") if p.is_file()}  # the typefaces sit in fonts/
check("the_interface_kit_is_the_unchanged_copy_from_gmes", kit == pin["files"] and len(pin["commit"]) == 40,
      sorted(k for k in set(kit) | set(pin["files"]) if kit.get(k) != pin["files"].get(k)))
import importlib.util  # noqa: E402  (tools/ is not a package; loaded by path so CHECK_ENVIRONMENT sees no import)
_spec = importlib.util.spec_from_file_location("make_assets", ROOT / "tools" / "make_assets.py")
make_assets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_assets)
packed = os.path.join(TMP, "_assets_check.py")
make_assets.write(packed)
ns = {}
exec(compile(open(packed, encoding="utf-8").read(), packed, "exec"), ns)
from hr_core import web  # noqa: E402
check("packed_screens_are_identical_to_the_files", ns["FILES"] == {n: web.asset(n) for n in web.asset_names()} and "index.html" in ns["FILES"])

shutil.rmtree(TMP, ignore_errors=True)
print(json.dumps(results, indent=2))
print(f"TEST_HR_DELIVERY: {len(results)} checks passed")
