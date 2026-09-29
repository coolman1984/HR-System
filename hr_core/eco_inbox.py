"""What manufacturing tells HR (plan 30-HR WP-H1, flow F8): the inbox for ecosystem events, and the staffing gap.

* Machine keys: other applications call `POST /eco/v1/inbox` with header `x-eco-key`; a key is shown once when it is made
  and only its SHA-256 is kept (`data/eco_inbox.db`, never in a backup of the registry, never in the audit).
* Inbox: the same answers as GMES and Mizan (applied / unchanged / stale / duplicate / rejected), dedupe on (source, id),
  another company's events and types HR does not consume are refused. Accepted: `mes.crew_requirement.v1`.
* Staffing gap: for each production day and shift, the people the lines need (from the crew requirements) against the
  people HR scheduled on that shift who hold a VALID qualification (expired / not yet certified do not count) —
  the whole plant per shift, because the schedule does not say the line yet (work centres come later).
Standard library only.
"""

import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import eco_contract

from . import skills

ACCEPTED = ("mes.crew_requirement.v1",)
SCOPES = ("eco.inbox.write",)

SCHEMA = """
CREATE TABLE IF NOT EXISTS machine_key (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, hash TEXT NOT NULL UNIQUE, scopes TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, created_by TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inbox (
  source TEXT NOT NULL, event_id TEXT NOT NULL, type TEXT NOT NULL, result TEXT NOT NULL, received_at TEXT NOT NULL,
  PRIMARY KEY (source, event_id)
);
CREATE TABLE IF NOT EXISTS inbox_reject (
  source TEXT NOT NULL, event_id TEXT NOT NULL, type TEXT, code TEXT NOT NULL, message TEXT NOT NULL, at TEXT NOT NULL,
  PRIMARY KEY (source, event_id)
);
CREATE TABLE IF NOT EXISTS crew_requirement (
  id TEXT PRIMARY KEY, line_code TEXT NOT NULL, shift_code TEXT NOT NULL, work_date TEXT NOT NULL, headcount INTEGER NOT NULL,
  skills TEXT NOT NULL, version INTEGER NOT NULL, mrp_run TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE (line_code, shift_code, work_date)
);
"""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _hash(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class EcoInbox:
    def __init__(self, data_dir, company_id):
        self.company_id = (company_id or "").lower()
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(Path(data_dir) / "eco_inbox.db"), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    # ------------------------------------------------------------------ keys
    def create_key(self, name, scopes, by):
        name = str(name or "").strip()
        if not name or len(name) > 60:
            raise ValueError("key name: 1 to 60 characters")
        bad = [s for s in scopes if s not in SCOPES]
        if not scopes or bad:
            raise ValueError(f"scopes must be among {', '.join(SCOPES)}")
        key = "hk_" + secrets.token_urlsafe(32)
        with self.lock:
            self.db.execute("INSERT INTO machine_key (name, hash, scopes, created_at, created_by) VALUES (?, ?, ?, ?, ?)",
                            (name, _hash(key), " ".join(scopes), _now(), by))
        return key

    def keys(self):
        return [dict(r) for r in self.db.execute("SELECT id, name, scopes, active, created_at, created_by FROM machine_key ORDER BY name")]

    def revoke(self, key_id):
        with self.lock:
            self.db.execute("UPDATE machine_key SET active = 0 WHERE id = ?", (int(key_id),))

    def caller(self, key, scope):
        """The key's name, or (status, code) when refused."""
        if not key:
            return None, (401, "eco.key_required")
        row = self.db.execute("SELECT name, scopes, active FROM machine_key WHERE hash = ?", (_hash(key),)).fetchone()
        if row is None or not row["active"]:
            return None, (401, "eco.key_unknown")
        if scope not in row["scopes"].split():
            return None, (403, "eco.scope_missing")
        return row["name"], None

    # ------------------------------------------------------------------ inbox
    def receive(self, raw):
        env = raw if isinstance(raw, dict) else {}
        eid = env.get("id") if isinstance(env.get("id"), str) else None
        src = env.get("source") if isinstance(env.get("source"), str) else "?"

        def refuse(code, message):
            with self.lock:
                self.db.execute("INSERT INTO inbox_reject (source, event_id, type, code, message, at) VALUES (?, ?, ?, ?, ?, ?) "
                                "ON CONFLICT (source, event_id) DO UPDATE SET code = excluded.code, message = excluded.message, at = excluded.at",
                                (src[:200], (eid or "?")[:100], str(env.get("type"))[:100], code, message[:1000], _now()))
            return {"id": eid, "result": "rejected", "code": code, "message": message}

        problems = eco_contract.validate("eco.envelope.v1", env)
        if problems:
            return refuse("eco.contract_violation", "; ".join(problems[:5]))
        parts = src.split("/")
        if len(parts) < 3 or parts[2].lower() != self.company_id:
            return refuse("eco.foreign_company", f"event from another company: {src}")
        if env["type"] not in ACCEPTED:
            return refuse("eco.not_accepted", f"HR does not consume {env['type']}")
        problems = eco_contract.validate(env["type"], env.get("data"))
        if problems:
            return refuse("eco.contract_violation", "; ".join(problems[:5]))
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if self.db.execute("SELECT 1 FROM inbox WHERE source = ? AND event_id = ?", (src, eid)).fetchone():
                    self.db.execute("COMMIT")
                    return {"id": eid, "result": "duplicate"}
                result = self._crew(env["data"])
                self.db.execute("INSERT INTO inbox (source, event_id, type, result, received_at) VALUES (?, ?, ?, ?, ?)", (src, eid, env["type"], result, _now()))
                self.db.execute("DELETE FROM inbox_reject WHERE source = ? AND event_id = ?", (src, eid))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return {"id": eid, "result": result}

    def _crew(self, d):
        cur = self.db.execute("SELECT version FROM crew_requirement WHERE id = ?", (d["id"],)).fetchone()
        if cur and d["version"] < cur["version"]:
            return "stale"
        if cur and d["version"] == cur["version"]:
            return "unchanged"
        self.db.execute(
            "INSERT INTO crew_requirement (id, line_code, shift_code, work_date, headcount, skills, version, mrp_run, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET headcount = excluded.headcount, skills = excluded.skills, version = excluded.version, mrp_run = excluded.mrp_run, updated_at = excluded.updated_at",
            (d["id"], d["line"], d["shift"], d["work_date"], d["headcount"], json.dumps(d["skills"]), d["version"], d["mrp_run"]["code"], _now()))
        return "applied"

    def status(self):
        q = lambda sql: self.db.execute(sql).fetchone()[0]  # noqa: E731
        return {"received": q("SELECT COUNT(*) FROM inbox"), "rejected": q("SELECT COUNT(*) FROM inbox_reject"),
                "crew_rows": q("SELECT COUNT(*) FROM crew_requirement WHERE headcount > 0"),
                "last": q("SELECT MAX(received_at) FROM inbox")}

    def requirements(self, first, last, line=None):
        sql = "SELECT * FROM crew_requirement WHERE work_date BETWEEN ? AND ? AND headcount > 0" + (" AND line_code = ?" if line else "") + " ORDER BY work_date, shift_code, line_code"
        return [dict(r, skills=json.loads(r["skills"])) for r in self.db.execute(sql, (first, last, line) if line else (first, last))]


def staffing_gap(requirements, days, qualifications):
    """requirements: crew rows; days: resolved schedule days (scheduling.Schedule.days); qualifications: employee_id ->
    list of {"skill": code, "level": n, "certified_on", "expires_on"}. One row per production day and shift."""
    by_slot = {}
    for r in requirements:
        s = by_slot.setdefault((r["work_date"], r["shift_code"]), {"date": r["work_date"], "shift": r["shift_code"], "lines": [], "required": 0, "skills": {}})
        s["lines"].append({"line": r["line_code"], "headcount": r["headcount"]})
        s["required"] += r["headcount"]
        for k in r["skills"]:
            key = (k["skill_code"], k["level"])
            s["skills"][key] = s["skills"].get(key, 0) + k["count"]
    people = {}
    for d in days:
        if d["status"] == "work" and d.get("shift_code"):
            people.setdefault((d["work_date"], d["shift_code"]), []).append(d["employee_id"])
    out = []
    for (day, shift), s in sorted(by_slot.items()):
        here = people.get((day, shift), [])
        skill_rows = []
        for (code, level), need in sorted(s["skills"].items()):
            have = sum(1 for e in here if any(q["skill"] == code and q["level"] >= level and skills.state(q, day) in ("valid", "expiring") for q in qualifications.get(e, [])))
            skill_rows.append({"skill": code, "level": level, "required": need, "covered": min(have, need), "gap": max(0, need - have)})
        out.append({"date": day, "shift": shift, "lines": s["lines"], "required": s["required"], "scheduled": len(here),
                    "gap": max(0, s["required"] - len(here)), "skills": skill_rows})
    return out
