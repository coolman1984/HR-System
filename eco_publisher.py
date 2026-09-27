"""Publishes HR-System's workforce truth to the rest of the ecosystem (manufacturing first).

HR-System OWNS employees and their attendance (see MIGRATION.md and GMES
docs/ecosystem/02-truth-ownership.md). This additive component reads HR's own current state
through `engine.current_rows()` — it changes nothing in the locked core and nothing in the
application's behaviour — and turns it into versioned snapshots:

  eco.employee.v1        one per employee confirmed by an uploaded employee master
  eco.attendance_day.v1  one per attendance record (the merge key Attendance_ID)

Guarantees:
  * HR works alone. Without ECO_GMES_URL the publisher is disabled and does nothing.
  * The other side may be down. Snapshots wait in data/eco_outbox.db and are retried; nothing
    is lost and nothing is skipped.
  * No duplicates. Each staged envelope is STORED in the outbox and a resend (after a crash or an
    outage) sends those exact bytes, so GMES's inbox recognises the id as a duplicate. Versions only
    ever go up, so even a rebuilt outbox can only publish newer, never older, truth.
  * No personal data leaves HR: only the fields of the contracts (no birth date, national id,
    pay or contact details).

Usage:
  python eco_publisher.py --once          one cycle, prints a JSON report
  python eco_publisher.py --loop 30       every 30 seconds

Environment: ECO_COMPANY_ID (the company's ecosystem id, a lower-case UUID), ECO_GMES_URL
(e.g. http://127.0.0.1:4700), ECO_GMES_KEY (a GMES key with scope eco.inbox.write),
ECO_NODE (default hr-main), EXCEL_APP_DATA_DIR (HR's data folder, as for the application).
Standard library only.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

import eco_contract

BATCH = 200


def hr_id(company, kind, code):
    """Same identity as GMES's hrId(): UUIDv5(company, "hr:<kind>:<code>")."""
    return str(uuid.uuid5(uuid.UUID(company), f"hr:{kind}:{code}"))


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _date(value):
    text = _text(value)
    return text[:10] if text and len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


def build_snapshots(rows, company):
    """HR's current rows -> {(type, id): body without version}. Pure; no I/O.

    Employees come ONLY from rows enriched by an uploaded employee master (employee_employment_status);
    an employee seen in attendance but never confirmed by the master is not published, so other apps
    treat them as unknown rather than guessing. When rows disagree (enrichments from different uploads),
    the row with the latest work date wins, deterministically.
    """
    out, problems = {}, []
    best = {}
    for row in rows:
        emp = _text(row.get("employee_id"))
        status = _text(row.get("employee_employment_status"))
        if emp and status:
            rank = (_text(row.get("work_date")) or "", _text(row.get("attendance_id")) or "")
            if emp not in best or rank > best[emp][0]:
                best[emp] = (rank, row)
    for emp, (_, row) in sorted(best.items()):
        status = _text(row.get("employee_employment_status"))
        body = {"id": hr_id(company, "employee", emp), "code": emp, "employment_status": status, "active": status.lower() == "active",
                "origin": {"app": "hr", "type": "employee", "key": emp}}
        hire = _date(row.get("employee_hire_date"))
        if hire:
            body["hire_date"] = hire
        out[("eco.employee.v1", body["id"])] = body
    for row in rows:
        code, emp, day, status = (_text(row.get(k)) for k in ("attendance_id", "employee_id", "work_date", "attendance_status"))
        if not (code and emp and _date(day) and status):
            problems.append(f"attendance {code or '?'}: incomplete, not published")
            continue
        body = {"id": hr_id(company, "attendance", code), "code": code, "employee": {"id": hr_id(company, "employee", emp), "code": emp},
                "work_date": _date(day), "status": status, "origin": {"app": "hr", "type": "attendance", "key": code}}
        shift = _text(row.get("scheduled_shift_id"))
        if shift:
            body["scheduled_shift_code"] = shift
        roster = {k: v for k, v in (("shift_code", _text(row.get("roster_shift_id"))), ("status", _text(row.get("roster_status")))) if v}
        if roster:
            body["roster"] = roster
        leave = {k: v for k, v in (("request_code", _text(row.get("leave_request_id"))), ("type", _text(row.get("leave_type")))) if v}
        if leave:
            body["leave"] = leave
        minutes = row.get("worked_minutes")
        if isinstance(minutes, (int, float)) and not isinstance(minutes, bool):
            if float(minutes).is_integer() and minutes >= 0:
                body["worked_minutes"] = int(minutes)
            else:
                # never round silently (ADR-018 in GMES): leave it out and say so
                problems.append(f"attendance {code}: worked_minutes {minutes} is not a whole number, not published")
        out[("eco.attendance_day.v1", body["id"])] = body
    return out, problems


def _fingerprint(body):
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class Outbox:
    """HR's own small outbox database, next to (never inside) the application's history.db."""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS entity (
              type TEXT NOT NULL, id TEXT NOT NULL, hash TEXT NOT NULL, version INTEGER NOT NULL,
              envelope TEXT NOT NULL, state TEXT NOT NULL,          -- pending | delivered | rejected
              detail TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (type, id));
        """)

    def stage(self, kind, entity_id, body, envelope_for):
        row = self.db.execute("SELECT hash, version FROM entity WHERE type = ? AND id = ?", (kind, entity_id)).fetchone()
        digest = _fingerprint(body)
        if row and row[0] == digest:
            return False
        version = max((row[1] if row else 0) + 1, int(time.time() * 1000))
        envelope = envelope_for(kind, dict(body, version=version))
        self.db.execute(
            "INSERT INTO entity (type, id, hash, version, envelope, state, detail, updated_at) VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?) "
            "ON CONFLICT(type, id) DO UPDATE SET hash = excluded.hash, version = excluded.version, envelope = excluded.envelope, "
            "state = 'pending', detail = NULL, updated_at = excluded.updated_at",
            (kind, entity_id, digest, version, json.dumps(envelope, ensure_ascii=False), _now()))
        return True

    def pending(self, limit):
        return self.db.execute("SELECT type, id, envelope FROM entity WHERE state = 'pending' ORDER BY type DESC, id LIMIT ?", (limit,)).fetchall()

    def mark(self, kind, entity_id, state, detail=None):
        self.db.execute("UPDATE entity SET state = ?, detail = ?, updated_at = ? WHERE type = ? AND id = ?", (state, detail, _now(), kind, entity_id))

    def counts(self):
        return dict(self.db.execute("SELECT state, COUNT(*) FROM entity GROUP BY state").fetchall())


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Publisher:
    def __init__(self, company, gmes_url, gmes_key, node="hr-main", data_dir=None, timeout=10):
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", company or ""):
            raise ValueError("ECO_COMPANY_ID must be the company's ecosystem id (a lower-case UUID)")
        self.company, self.url, self.key, self.timeout = company, gmes_url.rstrip("/"), gmes_key, timeout
        self.source = f"eco://{company}/hr/{node}"
        data_dir = data_dir or os.environ.get("EXCEL_APP_DATA_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        self.outbox = Outbox(os.path.join(data_dir, "eco_outbox.db"))

    def envelope(self, kind, data):
        subject = f"{kind.split('.')[1]}/{data['id']}"
        return {
            "specversion": "1.0",
            # Reproducible from (type, entity, version); the duplicate guarantee itself comes from resending the STORED envelope.
            "id": str(uuid.uuid5(uuid.UUID(self.company), f"{kind}:{data['id']}:{data['version']}")),
            "source": self.source, "type": kind, "subject": subject, "time": _now(), "datacontenttype": "application/json",
            "ecoseq": data["version"], "ecocorrelation": subject, "data": data,
        }

    def stage_from(self, rows):
        snapshots, problems = build_snapshots(rows, self.company)
        staged = 0
        with self.outbox.db:
            for (kind, entity_id), body in sorted(snapshots.items()):
                if self.outbox.stage(kind, entity_id, body, self.envelope):
                    staged += 1
        return staged, problems

    def deliver(self):
        sent = delivered = rejected = 0
        while True:
            batch = self.outbox.pending(BATCH)
            if not batch:
                return {"sent": sent, "delivered": delivered, "rejected": rejected}
            events = [json.loads(e) for _, _, e in batch]
            for ev in events:  # never send what the contract would refuse
                problems = eco_contract.validate_event(ev)
                if problems:
                    raise RuntimeError(f"refusing to publish an invalid {ev.get('type')}: {problems[:3]}")
            body = json.dumps({"events": events}, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(self.url + "/eco/v1/inbox", data=body, method="POST",
                                             headers={"content-type": "application/json", "x-eco-key": self.key})
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    answer = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                if exc.code >= 500 or exc.code == 429:
                    raise ConnectionError(f"GMES answered {exc.code}")
                raise PermissionError(f"GMES refused the batch: HTTP {exc.code} {exc.read()[:300]!r}")
            except (urllib.error.URLError, OSError) as exc:
                raise ConnectionError(f"GMES unreachable: {exc}")
            sent += len(events)
            by_id = {r.get("id"): r for r in answer.get("results", [])}
            with self.outbox.db:
                for (kind, entity_id, _), ev in zip(batch, events):
                    r = by_id.get(ev["id"], {})
                    if r.get("result") in ("applied", "unchanged", "stale", "duplicate"):
                        self.outbox.mark(kind, entity_id, "delivered", r.get("result"))
                        delivered += 1
                    else:
                        # Visible, not retried until the content changes (a new version is then staged).
                        self.outbox.mark(kind, entity_id, "rejected", f"{r.get('code')}: {r.get('message')}")
                        rejected += 1

    def run_once(self, rows):
        staged, problems = self.stage_from(rows)
        report = {"staged": staged, "problems": problems[:20], "problem_count": len(problems)}
        try:
            report.update(self.deliver())
        except ConnectionError as exc:
            report["stopped_by"] = str(exc)
        report["outbox"] = self.outbox.counts()
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", type=int, default=0, help="seconds between cycles")
    args = parser.parse_args(argv)
    url = os.environ.get("ECO_GMES_URL", "").strip()
    if not url:
        print(json.dumps({"eco": "disabled", "reason": "ECO_GMES_URL is not set; HR-System runs on its own"}))
        return 0
    import engine  # imported only when publishing, so a disabled publisher touches nothing
    publisher = Publisher(os.environ.get("ECO_COMPANY_ID", ""), url, os.environ.get("ECO_GMES_KEY", ""), os.environ.get("ECO_NODE", "hr-main"))
    while True:
        print(json.dumps(publisher.run_once(engine.current_rows(force=True)), ensure_ascii=False))
        sys.stdout.flush()
        if args.once or not args.loop:
            return 0
        time.sleep(args.loop)


if __name__ == "__main__":
    sys.exit(main())
