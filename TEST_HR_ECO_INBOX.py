"""What manufacturing tells HR (WP-H1): machine keys, the inbox for crew requirements, and the staffing gap.

Through the real HTTP handler. Synthetic data only. Standard library only.
"""

import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"

from hr_core.api import make_handler  # noqa: E402
from hr_core.service import HRService  # noqa: E402

results = {}


def check(name, ok, detail=None):
    results[name] = bool(ok)
    if not ok:
        print(json.dumps(results, indent=2))
        raise AssertionError(f"{name}: {detail}")


TMP = tempfile.mkdtemp(prefix="hr_eco_inbox_")
svc = HRService(os.path.join(TMP, "data"), COMPANY, "NILE", "Nile Home", backup_dir=os.path.join(TMP, "backups"))
reg = svc.registry
reg.today = lambda: "2026-10-01"
svc.bootstrap_admin("admin", "Admin", "Admin-2026!x")
svc.auth.commit("admin", "clear first-login flag", [{"entity": "user", "code": "admin", "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", "admin")["ver"]}])
_, admin = svc.login("admin", "Admin-2026!x")
save = lambda e, code, f: svc.save(admin, e, code, f)["row"]  # noqa: E731

# two people on the day shift; only one holds a valid soldering qualification (the other's has expired)
e1 = save("employee", "E1", {"preferred_name": "Aya", "employment_status": "Active"})
e2 = save("employee", "E2", {"preferred_name": "Omar", "employment_status": "Active"})
day = save("shift", "A", {"name": "Day", "start_time": "07:00", "end_time": "15:00", "break_minutes": 30, "grace_minutes": 10})
cal = save("work_calendar", "EG", {"name": "Egypt", "rest_days": "FRI", "holidays": ""})
for e in (e1, e2):
    save("shift_assignment", f"{e['code']}-R", {"employee_id": e["id"], "shift_id": day["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-01"})
night = save("shift", "B", {"name": "Night", "start_time": "23:00", "end_time": "07:00", "break_minutes": 30, "grace_minutes": 10})
e3 = save("employee", "E3", {"preferred_name": "Nour", "employment_status": "Active"})           # works the other shift: never counted for shift A
save("shift_assignment", "E3-R", {"employee_id": e3["id"], "shift_id": night["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-01"})
solder = save("skill", "SOLDER", {"name": "Soldering", "category": "technical", "validity_months": 12})
save("employee_skill", "E1-SOLDER", {"employee_id": e1["id"], "skill_id": solder["id"], "level": 3, "certified_on": "2026-01-01", "expires_on": "2026-12-31"})
save("employee_skill", "E2-SOLDER", {"employee_id": e2["id"], "skill_id": solder["id"], "level": 3, "certified_on": "2025-01-01", "expires_on": "2025-12-31"})

server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(svc))
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{server.server_address[1]}"
token = svc.login("admin", "Admin-2026!x")[0]


def call(method, path, body=None, key=None, session=True):
    req = urllib.request.Request(BASE + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **({"x-eco-key": key} if key else {}), **({"Cookie": f"hr_sid={token}"} if session else {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


status, made = call("POST", "/api/admin/eco-keys", {"name": "gmes", "scopes": ["eco.inbox.write"]})
check("an_admin_makes_a_machine_key_shown_once", status == 201 and made["key"].startswith("hk_"), made)
KEY = made["key"]
check("the_list_never_shows_the_key", KEY not in json.dumps(call("GET", "/api/admin/eco-keys")[1]))


def crew(line, headcount, version=1, date="2026-10-05", company=COMPANY):
    eid = str(uuid.uuid4())
    return {"specversion": "1.0", "id": eid, "source": f"eco://{company}/gmes/plant-1", "type": "mes.crew_requirement.v1", "subject": "crew/x",
            "time": "2026-10-01T02:00:00Z", "datacontenttype": "application/json", "ecoseq": 1, "ecocorrelation": "mrp_run/x",
            "data": {"id": str(uuid.uuid5(uuid.UUID(COMPANY), f"gmes:crew:{line}:A:{date}")), "line": line, "shift": "A", "work_date": date, "headcount": headcount,
                     "skills": [{"skill_code": "SOLDER", "level": 2, "count": 2}], "mrp_run": {"id": str(uuid.uuid4()), "code": "MRP-1"},
                     "version": version, "origin": {"app": "gmes", "type": "crew_requirement", "key": f"{line}:A:{date}"}}}


check("no_key_is_refused", call("POST", "/eco/v1/inbox", {"events": [crew("FA-1", 3)]}, session=False)[0] == 401)
check("a_wrong_key_is_refused", call("POST", "/eco/v1/inbox", {"events": [crew("FA-1", 3)]}, key="hk_nope", session=False)[0] == 401)
ev = crew("FA-1", 3)
status, out = call("POST", "/eco/v1/inbox", {"events": [ev, crew("FA-2", 1), crew("FA-9", 1, company=str(uuid.uuid4()))]}, key=KEY, session=False)
check("crew_requirements_are_applied", status == 200 and [r["result"] for r in out["results"]] == ["applied", "applied", "rejected"], out)
check("another_company_is_refused", out["results"][2]["code"] == "eco.foreign_company", out)
check("a_redelivery_is_a_duplicate", call("POST", "/eco/v1/inbox", {"events": [ev]}, key=KEY, session=False)[1]["results"][0]["result"] == "duplicate")
older = crew("FA-1", 9, version=1)
check("an_older_version_is_stale_or_unchanged", call("POST", "/eco/v1/inbox", {"events": [older]}, key=KEY, session=False)[1]["results"][0]["result"] == "unchanged")

check("a_key_without_the_scope_is_refused", svc.eco_inbox().caller(KEY, "eco.other")[1] == (403, "eco.scope_missing"))
first = call("POST", "/eco/v1/inbox", {"events": [crew("FA-3", 5, version=2, date="2026-10-06")]}, key=KEY, session=False)[1]["results"][0]["result"]
stale = call("POST", "/eco/v1/inbox", {"events": [crew("FA-3", 9, version=1, date="2026-10-06")]}, key=KEY, session=False)[1]["results"][0]["result"]
check("an_older_version_never_replaces_a_newer_one", first == "applied" and stale == "stale" and call("GET", "/api/staffing/gap?from=2026-10-06&to=2026-10-06")[1][0]["required"] == 5, (first, stale))

status, gap = call("GET", "/api/staffing/gap?from=2026-10-05&to=2026-10-05")
check("the_gap_is_computed", status == 200 and len(gap) == 1, gap)
g = gap[0]
check("required_is_the_sum_of_the_lines", g["required"] == 4 and g["scheduled"] == 2 and g["gap"] == 2, g)
check("an_expired_qualification_does_not_count", g["skills"] == [{"skill": "SOLDER", "level": 2, "required": 4, "covered": 1, "gap": 3}], g)

# ---- labour facts: what manufacturing says people did, beside what HR planned
def labour(minutes, version=1):
    eid = str(uuid.uuid4())
    return {"specversion": "1.0", "id": eid, "source": f"eco://{COMPANY}/gmes/plant-1", "type": "mes.labor_day.v1", "subject": "labor/x",
            "time": "2026-10-06T08:00:00Z", "datacontenttype": "application/json", "ecoseq": 5, "ecocorrelation": "labor/x",
            "data": {"id": str(uuid.uuid5(uuid.UUID(COMPANY), "gmes:labor:E1:2026-10-05")), "version": version, "origin": {"app": "gmes", "type": "labor_day", "key": "E1:2026-10-05"},
                     "employee": {"id": e1["id"], "code": "E1"}, "production_date": "2026-10-05", "shift": "A", "total_minutes": minutes,
                     "entries": [{"line": "FA-1", "station": "FA-1-PL", "minutes": minutes - 100}, {"line": "FA-2", "minutes": 100}]}}


check("labour_facts_are_applied", call("POST", "/eco/v1/inbox", {"events": [labour(500)]}, key=KEY, session=False)[1]["results"][0]["result"] == "applied")
check("an_older_labour_version_is_not_applied", call("POST", "/eco/v1/inbox", {"events": [labour(999, version=1)]}, key=KEY, session=False)[1]["results"][0]["result"] == "unchanged")
status, ev = call("GET", "/api/labour/evidence?from=2026-10-05&to=2026-10-05&employee=E1")
check("evidence_sets_worked_against_planned", status == 200 and len(ev) == 1 and ev[0]["worked_in_production"] == 500 and ev[0]["planned_paid"] == 450 and ev[0]["beyond_plan"] == 50, ev)
call("POST", "/eco/v1/inbox", {"events": [labour(430, version=2)]}, key=KEY, session=False)
check("a_newer_version_replaces_it", call("GET", "/api/labour/evidence?from=2026-10-05&to=2026-10-05")[1][0]["beyond_plan"] == 0)

# ---- request signatures (WP-X2): the same algorithm and the same vector as Mizan and GMES
import eco_signing  # noqa: E402

check("the_signature_vector_is_the_same_in_all_three_applications",
      eco_signing.sha256hex("mk_example_key") == "2e0337bdb84b83290ffebce13b546d7a2e9946911b81a9775b069bbb1afc7013"
      and eco_signing.sign_request(eco_signing.sha256hex("mk_example_key"), "POST", "/eco/v1/inbox?x=1", '{"events":[]}', 1_800_000_000_000)
      == "d67f9a620fd70b7d0f6ffeee7f3f4cbc256e1ef3a573dedb2cb33507e0868197")


def signed(body_obj, key=KEY, path="/eco/v1/inbox", ts=None, tamper=None):
    raw = json.dumps(body_obj).encode()
    headers = {"Content-Type": "application/json", "x-eco-key": key, **eco_signing.signature_headers(key, "POST", path, raw.decode(), ts)}
    req = urllib.request.Request(BASE + "/eco/v1/inbox", method="POST", data=tamper if tamper is not None else raw, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


check("a_signed_call_is_accepted", signed({"events": [crew("FA-7", 2, date="2026-10-07")]})[0] == 200)
status, out = signed({"events": [crew("FA-7", 2, date="2026-10-07")]}, tamper=json.dumps({"events": []}).encode())
check("a_body_changed_after_signing_is_refused", status == 401 and out["error"] == "auth.signature_invalid", out)
status, out = signed({"events": []}, path="/eco/v1/feed")
check("a_signature_for_another_path_is_refused", status == 401 and out["error"] == "auth.signature_invalid", out)
import time  # noqa: E402
status, out = signed({"events": []}, ts=int(time.time() * 1000) - 6 * 60_000)
check("a_stale_signature_is_refused", status == 401 and out["error"] == "auth.signature_expired", out)
check("unsigned_is_accepted_until_signatures_are_required", call("POST", "/eco/v1/inbox", {"events": [crew("FA-8", 2, date="2026-10-08")]}, key=KEY, session=False)[0] == 200)
os.environ["ECO_REQUIRE_SIGNATURE"] = "1"
try:
    status, out = call("POST", "/eco/v1/inbox", {"events": [crew("FA-8", 3, date="2026-10-09")]}, key=KEY, session=False)
    check("unsigned_is_refused_when_required", status == 401 and out["error"] == "auth.signature_required", out)
    check("signed_is_accepted_when_required", signed({"events": [crew("FA-8", 3, date="2026-10-10")]})[0] == 200)
finally:
    del os.environ["ECO_REQUIRE_SIGNATURE"]

server.shutdown()
print(json.dumps(results, indent=2))
print("TEST_HR_ECO_INBOX: all", len(results), "checks passed")
