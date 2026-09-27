"""HR-System -> ecosystem publisher: contract, identity, retry and no-duplicate guarantees.

Runs the real HR engine on the synthetic dataset, then publishes to a FAKE manufacturing inbox
(standard-library HTTP server) that behaves like GMES's /eco/v1/inbox: it remembers event ids
and answers 'duplicate' for a repeat. The real GMES is exercised by GMES's own end-to-end test.
Standard library only.
"""

import json
import os
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"
CLEAN = "inputs/hr-factory-synthetic-dataset/01_CLEAN_BASELINE/"
KEY = "gk_test"


class FakeInbox(BaseHTTPRequestHandler):
    seen, received, refuse = set(), [], set()

    def log_message(self, *args):
        pass

    def do_POST(self):
        assert self.path == "/eco/v1/inbox" and self.headers["x-eco-key"] == KEY
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        results = []
        for ev in body["events"]:
            FakeInbox.received.append(ev)
            if ev["data"]["code"] in FakeInbox.refuse:
                results.append({"id": ev["id"], "result": "rejected", "code": "mdm.test", "message": "refused on purpose"})
            elif ev["id"] in FakeInbox.seen:
                results.append({"id": ev["id"], "result": "duplicate"})
            else:
                FakeInbox.seen.add(ev["id"])
                results.append({"id": ev["id"], "result": "applied"})
        data = json.dumps({"results": results}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def start_inbox(port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), FakeInbox)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


results = {}
with tempfile.TemporaryDirectory(prefix="hr_eco_", ignore_cleanup_errors=True) as folder:
    os.environ["EXCEL_APP_DATA_DIR"] = str(Path(folder) / "data")
    os.chdir(ROOT)
    import eco_contract
    import eco_publisher
    import engine

    # 1. HR alone: without ECO_GMES_URL the publisher does nothing and creates nothing.
    os.environ.pop("ECO_GMES_URL", None)
    assert eco_publisher.main(["--once"]) == 0
    assert not (Path(folder) / "data" / "eco_outbox.db").exists()
    results["standalone_publisher_disabled"] = True

    engine.process_file(CLEAN + "05_Time_Attendance_Leave.xlsx", auxiliary_paths={
        "employee": CLEAN + "02_Employee_Master.xlsx", "roster": CLEAN + "06_Shifts_Overtime.xlsx", "leave": CLEAN + "05_Time_Attendance_Leave.xlsx"})
    rows = engine.current_rows(force=True)

    # 2. Snapshots: shared ids, contract-valid, no personal data.
    snaps, problems = eco_publisher.build_snapshots(rows, COMPANY)
    employees = [b for (k, _), b in snaps.items() if k == "eco.employee.v1"]
    days = [b for (k, _), b in snaps.items() if k == "eco.attendance_day.v1"]
    assert len(days) == 200 and len(employees) == 200, (len(days), len(employees))
    e1 = next(e for e in employees if e["code"] == "E000001")
    assert e1["id"] == "ad793f13-3ba3-5304-92f6-7bc2f8c8d5c8"  # the same value GMES's TypeScript hrId() gives
    for body in employees + days:
        assert not eco_contract.validate(("eco.employee.v1" if body["origin"]["type"] == "employee" else "eco.attendance_day.v1"), dict(body, version=1))
    forbidden = {"date_of_birth", "national_id", "gender", "base_pay", "mobile", "legal_name"}
    assert not any(forbidden & set(e) for e in employees)
    assert problems == []
    results["snapshots_valid_shared_ids_no_personal_data"] = True

    # 3. GMES down: everything waits in the outbox; nothing is lost.
    publisher = eco_publisher.Publisher(COMPANY, "http://127.0.0.1:9", KEY, timeout=2)
    down = publisher.run_once(rows)
    assert down["staged"] == 400 and "stopped_by" in down and down["outbox"] == {"pending": 400}, down
    results["gmes_down_everything_waits"] = True

    # 4. GMES up: delivered once; a second cycle with no change sends nothing.
    inbox = start_inbox()
    publisher.url = f"http://127.0.0.1:{inbox.server_address[1]}"
    up = publisher.run_once(rows)
    assert up["delivered"] == 400 and up["outbox"] == {"delivered": 400}, up
    again = publisher.run_once(rows)
    assert again["staged"] == 0 and again["sent"] == 0, again
    for ev in FakeInbox.received:
        assert not eco_contract.validate_event(ev), eco_contract.validate_event(ev)
    results["delivered_once_nothing_resent"] = True

    # 5. A crash after GMES applied but before HR recorded it: the resend carries the SAME ids.
    publisher.outbox.db.execute("UPDATE entity SET state = 'pending'")
    publisher.outbox.db.commit()
    before = len(FakeInbox.seen)
    replay = publisher.run_once(rows)
    assert replay["delivered"] == 400 and len(FakeInbox.seen) == before, "resend must be recognised as duplicates"
    results["resend_after_crash_is_duplicate_not_new"] = True

    # 6. HR changes an employee: a higher version for that entity only.
    changed = [dict(r) for r in rows]
    for r in changed:
        if r.get("employee_id") == "E000001":
            r["employee_employment_status"] = "Terminated"
    FakeInbox.received.clear()
    upd = publisher.run_once(changed)
    assert upd["staged"] == 1 and len(FakeInbox.received) == 1, upd
    ev = FakeInbox.received[0]
    assert ev["data"]["active"] is False and ev["data"]["version"] > 1
    results["change_publishes_only_that_entity_with_higher_version"] = True

    # 7. The consumer refuses something: visible in the outbox, not retried until it changes.
    FakeInbox.refuse.add("E000002")
    for r in changed:
        if r.get("employee_id") == "E000002":
            r["employee_employment_status"] = "Suspended"
    ref = publisher.run_once(changed)
    assert ref["rejected"] == 1 and ref["outbox"].get("rejected") == 1, ref
    assert publisher.run_once(changed)["sent"] == 0
    results["refusal_visible_not_retried_blindly"] = True

    # 8. An employee seen in attendance but never confirmed by the employee master is NOT published.
    lone = [{"attendance_id": "X1", "employee_id": "E424242", "work_date": "2026-09-01", "attendance_status": "Present"}]
    snaps2, _ = eco_publisher.build_snapshots(lone, COMPANY)
    assert [k for k, _ in snaps2] == ["eco.attendance_day.v1"]
    results["unconfirmed_employee_not_invented"] = True

    # 9. Fractional minutes are refused, never rounded.
    frac = [{"attendance_id": "X2", "employee_id": "E1", "work_date": "2026-09-01", "attendance_status": "Present", "worked_minutes": 12.5}]
    snaps3, problems3 = eco_publisher.build_snapshots(frac, COMPANY)
    assert "worked_minutes" not in next(iter(snaps3.values())) and problems3
    results["no_silent_rounding"] = True
    inbox.shutdown()

print(json.dumps(results, indent=2))
