"""The employee registry and organisation — HR-System's master data (phase 1).

Design taken from BAMS (the ecosystem's infrastructure reference), re-implemented, not copied:

* Separate databases: data/hr.db (business tables, rebuildable) and data/hr_journal.db (permanent,
  append-only, hash-chained, never restored backwards). The attendance history.db is untouched.
* A save = ONE journal line holding the full resulting rows. The journal append is the commit point:
  the business tables are a deterministic fold of the journal, so a crash between the two is repaired
  on the next start, and `rebuild()` recreates hr.db from the journal with an identical fingerprint.
* Optimistic versions (`ver`): saving over a newer version is refused, never silently overwritten.
* Soft delete + restore: nothing is erased; codes are never reused.
* Hash chain in the ecosystem's unified format (ADR-026): SHA-256("HR-JOURNAL1\\n" + canonical(line)),
  every line carries `prev`, and (phase 2) the Ed25519 signature of this installation's device (hr_core/journal.py).

Standard library only.
"""

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone  # noqa: F401

from . import clock
from . import discipline, people_ops, scheduling, skills
from .canonical import canonical
from .journal import SharedConnection, open_journal
from .scheduling import ScheduleError


ORG_TYPES = ("company", "site", "business_unit", "department", "section")
# Allowed parent type per org unit type. A department directly under the company is accepted only as
# "unplaced" (its business unit is unknown); the importer reports it so a person decides.
PARENTS = {"company": (), "site": ("company",), "business_unit": ("site",), "department": ("business_unit", "site", "company"), "section": ("department",)}
EMPLOYMENT_STATUSES = ("Active", "Leave", "Suspended", "Terminated")

ENTITIES = {
    "org_unit": ["type", "code", "name", "parent_id", "attrs"],
    "job": ["code", "title", "family", "level", "critical", "attrs"],
    "position": ["code", "job_id", "org_unit_id", "reports_to_id", "status", "attrs"],
    "employee": ["code", "legacy_number", "preferred_name", "legal_name", "employment_status", "worker_type", "hire_date",
                 "termination_date", "home_site_id", "position_id", "manager_id"],
    # phase 3 (hr_core/scheduling.py) and phase 5 (hr_core/skills.py); order = dependency order
    "shift": ["code", "name", "start_time", "end_time", "break_minutes", "grace_minutes"],
    "work_calendar": ["code", "name", "rest_days", "holidays"],
    "shift_assignment": ["code", "employee_id", "shift_id", "calendar_id", "kind", "valid_from", "valid_to", "note"],
    "roster_override": ["code", "employee_id", "work_date", "shift_id", "reason"],
    "skill": ["code", "name", "category", "validity_months"],
    "employee_skill": ["code", "employee_id", "skill_id", "level", "certified_on", "expires_on", "evidence"],
    # phase 6 (hr_core/discipline.py): the penalty schedule and the violations decided under it
    "penalty_rule": ["code", "name", "violation", "threshold_minutes", "window_days", "steps", "active"],
    "violation": ["code", "employee_id", "rule_id", "work_date", "minutes", "occurrence", "proposed", "status", "decision", "decided_by",
                  "decided_on", "note", "source"],
    # WP-H2 to WP-H5 (hr_core/people_ops.py): recruitment and onboarding, overtime, training, leave
    "headcount_plan": ["code", "org_unit_id", "work_center_code", "job_id", "period", "planned_fte", "source", "note"],
    "agency": ["code", "name", "contact", "fee_percent", "active"],
    "hire_requisition": ["code", "job_id", "position_id", "work_center_code", "count", "filled", "employment_type", "reason", "needed_by", "contract_months", "agency_id",
                         "status", "approved_by", "note"],
    "candidate": ["code", "requisition_id", "display_name", "source", "stage", "stage_date", "note"],
    "onboarding_task": ["code", "employee_id", "kind", "due", "done_on"],
    "contract": ["code", "employee_id", "employment_type", "start_date", "end_date", "agency_id", "requisition_id", "reason"],
    "overtime_request": ["code", "employee_id", "work_date", "planned_minutes", "kind", "reason", "requested_by", "status", "approved_by", "decided_on"],
    "course": ["code", "name", "skill_id", "grants_level", "validity_months", "duration_hours", "mandatory_for", "onboarding_kind"],
    "training_session": ["code", "course_id", "session_date", "trainer", "attendees", "status"],
    "leave_type": ["code", "name", "paid", "annual_days", "carry_over_days", "active"],
    "leave_request": ["code", "employee_id", "leave_type_id", "from_date", "to_date", "days", "status", "approver", "decided_on", "note"],
}
# Entities added after phase 2: left out of the fingerprint while empty, so backups made before they existed still
# rehearse to the same fingerprint (an older program's manifest does not know them).
LATER_ENTITIES = ("shift", "work_calendar", "shift_assignment", "roster_override", "skill", "employee_skill", "penalty_rule", "violation",
                  "headcount_plan", "agency", "hire_requisition", "candidate", "onboarding_task", "contract", "overtime_request", "course", "training_session", "leave_type", "leave_request")
people_ops_ENTITIES = ("headcount_plan", "agency", "hire_requisition", "candidate", "onboarding_task", "contract", "overtime_request", "course", "training_session", "leave_type", "leave_request")
META_COLUMNS = ["id", "ver", "deleted", "deleted_at", "deleted_by", "created_at", "created_by", "updated_at", "updated_by"]


class RegistryError(Exception):
    """A rule of the registry refused the change (message for people, code for programs)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class Conflict(RegistryError):
    pass


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    """Today's date on this computer, the boundary between history and the plan (phase 3 rules). HR_TEST_TODAY
    moves it for the delivery tests only (with HR_TEST_HOOKS=1)."""
    if os.environ.get("HR_TEST_HOOKS") == "1" and os.environ.get("HR_TEST_TODAY"):
        return os.environ["HR_TEST_TODAY"]
    return clock.today()  # the computer's date, or the simulated one (hr_core/clock.py; only with HR_SIMULATION=1)


class Registry:
    def __init__(self, data_dir, company_id, company_code="COMPANY", company_name="Company", journal=None):
        uuid.UUID(company_id)
        self.today = _today  # replaced by tests to put "today" where a rule needs it
        self.overtime_policy = {}  # the company's overtime settings (set by the service; defaults in people_ops)
        self.company_id = company_id
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "hr.db")
        self.journal = journal or open_journal(data_dir)
        self.journal_path = self.journal.path
        self.jdb = self.journal.db
        self.lock = threading.RLock()
        self.db = SharedConnection(self.path, self.lock)
        self._schema()
        self.recover()
        # Only when there is no company yet: a second opener that does not know the code (the publisher) must not
        # create a second "COMPANY" (found in phase 2; see PROJECT_LOG.md).
        company = self.db.execute("SELECT id, code FROM org_unit WHERE type = 'company' ORDER BY created_at LIMIT 1").fetchone()
        if company and company["id"] != self.gid("org_unit", company["code"], "company"):
            # every shared id is derived from the company id: opening these records under another company would give
            # every employee a new identity in every other application (ADR-HR-006)
            raise RegistryError("company.mismatch", "these HR records belong to another company id; the company identity "
                                "never changes silently (adopting an owner's identity is an explicit step)")
        if not company:
            self.commit("system", "Company created", [self.op_put("org_unit", company_code, {"type": "company", "name": company_name, "parent_id": None, "attrs": {}})])

    # ------------------------------------------------------------------ schema
    def _schema(self):
        parts = ["PRAGMA journal_mode = WAL;", "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"]
        for entity, fields in ENTITIES.items():
            # No declared type: SQLite keeps each value exactly as written (a TEXT column turned 1 into '1'
            # and made every re-import look like a change — caught by the idempotency test).
            cols = ", ".join(f for f in fields if f not in ("code",))
            parts.append(f"""CREATE TABLE IF NOT EXISTS {entity} (id TEXT PRIMARY KEY, code TEXT NOT NULL, {cols},
                ver INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT, deleted_by TEXT,
                created_at TEXT NOT NULL, created_by TEXT NOT NULL, updated_at TEXT NOT NULL, updated_by TEXT NOT NULL);""")
        parts.append("CREATE UNIQUE INDEX IF NOT EXISTS org_unit_code ON org_unit(type, code);")
        for entity in ("job", "position", "employee") + LATER_ENTITIES:
            parts.append(f"CREATE UNIQUE INDEX IF NOT EXISTS {entity}_code ON {entity}(code);")
        self.db.executescript("\n".join(parts))

    # ------------------------------------------------------------------ identity
    def gid(self, entity, code, org_type=None):
        """Global id shared with every ecosystem app: UUIDv5(company, "hr:<kind>:<code>")."""
        kind = f"org_unit:{org_type}" if entity == "org_unit" else entity
        return str(uuid.uuid5(uuid.UUID(self.company_id), f"hr:{kind}:{code}"))

    # ------------------------------------------------------------------ reads
    def _row(self, entity, row):
        if row is None:
            return None
        out = dict(row)
        if "attrs" in out:
            out["attrs"] = json.loads(out["attrs"]) if out["attrs"] else {}
        return out

    def get(self, entity, code, org_type=None, include_deleted=False):
        if entity == "org_unit" and org_type is None:
            rows = self.db.execute("SELECT * FROM org_unit WHERE code = ?", (code,)).fetchall()
            row = rows[0] if len(rows) == 1 else None
        elif entity == "org_unit":
            row = self.db.execute("SELECT * FROM org_unit WHERE type = ? AND code = ?", (org_type, code)).fetchone()
        else:
            row = self.db.execute(f"SELECT * FROM {entity} WHERE code = ?", (code,)).fetchone()
        row = self._row(entity, row)
        if row and row["deleted"] and not include_deleted:
            return None
        return row

    def by_id(self, entity, gid):
        return self._row(entity, self.db.execute(f"SELECT * FROM {entity} WHERE id = ?", (gid,)).fetchone())

    def list(self, entity, include_deleted=False):
        where = "" if include_deleted else "WHERE deleted = 0"
        return [self._row(entity, r) for r in self.db.execute(f"SELECT * FROM {entity} {where} ORDER BY code")]

    # ------------------------------------------------------------------ operations
    def op_put(self, entity, code, fields, expected_ver=None):
        return {"op": "put", "entity": entity, "code": code, "fields": fields, "expected_ver": expected_ver}

    def op_delete(self, entity, code, expected_ver, org_type=None):
        return {"op": "delete", "entity": entity, "code": code, "expected_ver": expected_ver, "org_type": org_type}

    def op_restore(self, entity, code, org_type=None):
        return {"op": "restore", "entity": entity, "code": code, "org_type": org_type}

    def commit(self, actor, label, ops):
        """Validate every op against the current state (earlier ops of the same save included), write ONE
        journal line with the resulting rows (the commit point), then fold it into hr.db.
        Returns the journal seq, or None when nothing changed (nothing is written then)."""
        if not actor or not label:
            raise RegistryError("audit.required", "every change needs who (actor) and why (label)")
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                results = [self._plan(op, actor) for op in ops]
                results = [r for r in results if r is not None]
            finally:
                self.db.execute("ROLLBACK")  # planning only; the fold below writes
            if not results:
                return None
            seq = self._append(actor, label, results)
            self._fold(seq, results)
            return seq

    def _plan(self, op, actor):
        """Validate one op and return the full resulting row (or None if it changes nothing).
        Applies it to the open planning transaction so later ops of the same save see it."""
        entity, code = op["entity"], op["code"]
        if entity not in ENTITIES:
            raise RegistryError("entity.unknown", f"unknown entity {entity}")
        now = _now()
        if op["op"] == "put":
            fields = dict(op["fields"])
            org_type = fields.get("type") if entity == "org_unit" else None
            cur = self.get(entity, code, org_type=org_type, include_deleted=True)
            if cur and cur["deleted"]:
                raise RegistryError(f"{entity}.deleted", f"{entity} {code} is in the Recycle Bin: restore it instead of creating it again (codes are never reused)")
            if op.get("expected_ver") is not None and (not cur or cur["ver"] != op["expected_ver"]):
                raise Conflict("ver.conflict", f"{entity} {code} was changed by someone else meanwhile (version {cur['ver'] if cur else 'none'}); reload and try again")
            row = {f: _plain(fields[f]) if f in fields else (cur.get(f) if cur else None) for f in ENTITIES[entity] if f != "code"}
            row["code"] = code
            if "attrs" in row and row["attrs"] is None:
                row["attrs"] = {}
            self._validate(entity, row, cur)
            if cur and all(_same(row[f], cur.get(f)) for f in ENTITIES[entity]):
                return None
            full = {**row, "id": cur["id"] if cur else self.gid(entity, code, org_type), "ver": (cur["ver"] + 1) if cur else 1, "deleted": 0,
                    "deleted_at": None, "deleted_by": None, "created_at": cur["created_at"] if cur else now, "created_by": cur["created_by"] if cur else actor,
                    "updated_at": now, "updated_by": actor}
        elif op["op"] in ("delete", "restore"):
            cur = self.get(entity, code, org_type=op.get("org_type"), include_deleted=True)
            if not cur:
                raise RegistryError(f"{entity}.not_found", f"{entity} {code} does not exist")
            if op["op"] == "delete":
                if cur["deleted"]:
                    return None
                if op.get("expected_ver") != cur["ver"]:
                    raise Conflict("ver.conflict", f"{entity} {code} was changed meanwhile (version {cur['ver']}); reload before deleting")
                self._check_delete(entity, cur)
                full = {**cur, "ver": cur["ver"] + 1, "deleted": 1, "deleted_at": now, "deleted_by": actor, "updated_at": now, "updated_by": actor}
            else:
                if not cur["deleted"]:
                    return None
                self._validate(entity, cur, cur)
                full = {**cur, "ver": cur["ver"] + 1, "deleted": 0, "deleted_at": None, "deleted_by": None, "updated_at": now, "updated_by": actor}
        else:
            raise RegistryError("op.unknown", f"unknown op {op['op']}")
        self._write(entity, full)
        return {"entity": entity, "row": full}

    # ------------------------------------------------------------------ rules
    def _validate(self, entity, row, cur):
        if not row.get("code") or len(str(row["code"])) > 64:
            raise RegistryError(f"{entity}.code", "a code (1-64 characters) is required")
        if entity == "org_unit":
            t = row.get("type")
            if t not in ORG_TYPES:
                raise RegistryError("org.type", f"org unit type must be one of {', '.join(ORG_TYPES)}")
            if cur and cur.get("type") != t:
                raise RegistryError("org.type_fixed", "the type of an org unit cannot change; create a new unit instead")
            if not row.get("name"):
                raise RegistryError("org.name", "an org unit needs a name")
            parent = self.by_id("org_unit", row["parent_id"]) if row.get("parent_id") else None
            if t == "company":
                if row.get("parent_id"):
                    raise RegistryError("org.parent", "the company has no parent")
            else:
                if not parent or parent["deleted"]:
                    raise RegistryError("org.parent", f"{t} {row['code']} needs an existing parent")
                if parent["type"] not in PARENTS[t]:
                    raise RegistryError("org.parent", f"a {t} cannot be placed under a {parent['type']} (allowed: {', '.join(PARENTS[t])})")
                seen, node = set(), parent
                while node:  # a cycle is impossible by types, but checked anyway (types may evolve)
                    if cur and node["id"] == cur["id"] or node["id"] in seen:
                        raise RegistryError("org.cycle", "an org unit cannot be under itself")
                    seen.add(node["id"])
                    node = self.by_id("org_unit", node["parent_id"]) if node["parent_id"] else None
        elif entity == "job":
            if not row.get("title"):
                raise RegistryError("job.title", "a job needs a title")
        elif entity == "position":
            job = self.by_id("job", row.get("job_id")) if row.get("job_id") else None
            if not job or job["deleted"]:
                raise RegistryError("position.job", f"position {row['code']} needs an existing job")
            unit = self.by_id("org_unit", row.get("org_unit_id")) if row.get("org_unit_id") else None
            if not unit or unit["deleted"] or unit["type"] not in ("department", "section"):
                raise RegistryError("position.unit", f"position {row['code']} must belong to an existing department or section")
            if row.get("reports_to_id") and not self.by_id("position", row["reports_to_id"]):
                raise RegistryError("position.reports_to", f"position {row['code']} reports to a position that does not exist")
        elif entity == "employee":
            if row.get("employment_status") not in EMPLOYMENT_STATUSES:
                raise RegistryError("employee.status", f"employment status must be one of {', '.join(EMPLOYMENT_STATUSES)}")
            hire, term = row.get("hire_date"), row.get("termination_date")
            for d in (hire, term):
                if d is not None and not (isinstance(d, str) and len(d) == 10 and d[4] == "-" and d[7] == "-"):
                    raise RegistryError("employee.date", f"dates are YYYY-MM-DD, got {d!r}")
            if hire and term and term < hire:
                raise RegistryError("employee.dates", f"employee {row['code']}: termination {term} is before hire {hire}")
            for field, entity2, what in (("home_site_id", "org_unit", "home site"), ("position_id", "position", "position"), ("manager_id", "employee", "manager")):
                if row.get(field):
                    ref = self.by_id(entity2, row[field])
                    if not ref or ref["deleted"]:
                        raise RegistryError(f"employee.{field}", f"employee {row['code']}: {what} does not exist")
                    if field == "home_site_id" and ref["type"] != "site":
                        raise RegistryError("employee.home_site_id", f"employee {row['code']}: home site must be a site")
            if cur and row.get("manager_id") == cur["id"]:
                raise RegistryError("employee.manager", "an employee cannot be their own manager")
        elif entity in LATER_ENTITIES:
            try:
                self._validate_later(entity, row, cur)
            except ScheduleError as exc:
                raise RegistryError(exc.code, str(exc)) from None

    def _live(self, entity, gid, what):
        ref = self.by_id(entity, gid) if gid else None
        if not ref or ref["deleted"]:
            raise RegistryError(f"{entity}.missing", f"{what} does not exist (or is in the Recycle Bin)")
        return ref

    def _validate_later(self, entity, row, cur):
        today = self.today()
        started = lambda col, gid: self.db.execute(  # noqa: E731
            f"SELECT 1 FROM shift_assignment WHERE {col} = ? AND deleted = 0 AND valid_from < ? LIMIT 1", (gid, today)).fetchone() is not None
        if entity == "shift":
            used = cur is not None and (started("shift_id", cur["id"]) or self.db.execute(
                "SELECT 1 FROM roster_override WHERE shift_id = ? AND deleted = 0 AND work_date < ? LIMIT 1", (cur["id"], today)).fetchone() is not None)
            scheduling.check_shift(row, cur, used)
        elif entity == "work_calendar":
            scheduling.check_calendar(row, cur, cur is not None and started("calendar_id", cur["id"]), today)
        elif entity == "shift_assignment":
            self._live("employee", row.get("employee_id"), "the employee")
            self._live("shift", row.get("shift_id"), "the shift")
            self._live("work_calendar", row.get("calendar_id"), "the working calendar")
            if cur is None:   # a new hire is not put on a production line before the medical check, the protective equipment and the ESD training are done
                todo = [r[0] for r in self.db.execute("SELECT kind FROM onboarding_task WHERE employee_id = ? AND deleted = 0 AND (done_on IS NULL OR done_on = '') AND kind IN ('medical', 'ppe', 'esd_training') ORDER BY kind", (row["employee_id"],))]
                if todo:
                    raise RegistryError("hr.onboarding.incomplete", f"the employee cannot be scheduled on a line yet: {', '.join(todo)} not done")
            others = [dict(r) for r in self.db.execute("SELECT * FROM shift_assignment WHERE employee_id = ? AND deleted = 0 AND id != ?",
                                                        (row["employee_id"], cur["id"] if cur else ""))]
            scheduling.check_assignment(row, cur, others, today)
        elif entity == "roster_override":
            emp = self._live("employee", row.get("employee_id"), "the employee")
            if row.get("shift_id"):
                self._live("shift", row["shift_id"], "the shift")
            scheduling.check_override(row, cur, emp["code"], today)
        elif entity == "skill":
            skills.check_skill(row)
        elif entity == "employee_skill":
            emp = self._live("employee", row.get("employee_id"), "the employee")
            skill = self._live("skill", row.get("skill_id"), "the skill")
            skills.check_employee_skill(row, emp["code"], skill["code"])
        elif entity in people_ops_ENTITIES:
            people_ops.validate(self, entity, row, cur)
        elif entity == "penalty_rule":
            discipline.check_rule(row)
        elif entity == "violation":
            emp = self._live("employee", row.get("employee_id"), "the employee")
            rule = self._live("penalty_rule", row.get("rule_id"), "the rule of the penalty schedule")
            month = str(row.get("work_date") or "")[:7]
            others = self.db.execute("SELECT decision FROM violation WHERE employee_id = ? AND deleted = 0 AND status = 'approved' AND substr(work_date, 1, 7) = ? AND id != ?",
                                     (row["employee_id"], month, cur["id"] if cur else "")).fetchall()
            deducted = sum(discipline.parse_penalty(r[0])[1] for r in others if r[0])
            discipline.check_violation(row, cur, emp["code"], rule["code"], today, deducted)

    def _check_delete(self, entity, cur):
        checks = {
            "org_unit": [("org_unit", "parent_id", "units under it"), ("position", "org_unit_id", "positions in it"), ("employee", "home_site_id", "employees based there")],
            "job": [("position", "job_id", "positions of this job")],
            "position": [("employee", "position_id", "employees holding it"), ("position", "reports_to_id", "positions reporting to it")],
            "employee": [("employee", "manager_id", "employees managed by them")],
            "shift": [("shift_assignment", "shift_id", "assignments of this shift"), ("roster_override", "shift_id", "day changes to this shift")],
            "work_calendar": [("shift_assignment", "calendar_id", "assignments using this calendar")],
            "shift_assignment": [], "roster_override": [],
            "headcount_plan": [], "agency": [("hire_requisition", "agency_id", "requisitions for it"), ("contract", "agency_id", "contracts through it")],
            "hire_requisition": [("candidate", "requisition_id", "candidates for it")], "candidate": [], "onboarding_task": [], "contract": [],
            "overtime_request": [], "course": [("training_session", "course_id", "sessions of it")], "training_session": [],
            "leave_type": [("leave_request", "leave_type_id", "leave requests of this type")], "leave_request": [],
            "skill": [("employee_skill", "skill_id", "people qualified for it"), ("course", "skill_id", "courses that grant it")],
            "employee_skill": [],
            "penalty_rule": [("violation", "rule_id", "violations decided under it")], "violation": [],
        }[entity]
        try:
            if entity == "shift_assignment":
                scheduling.check_assignment_delete(cur, self.today())
            elif entity == "violation":
                discipline.check_violation_delete(cur)
            elif entity == "roster_override":
                emp = self.by_id("employee", cur["employee_id"])
                scheduling.check_override(cur, cur, emp["code"] if emp else "", self.today(), deleting=True)
        except ScheduleError as exc:
            raise RegistryError(exc.code, str(exc)) from None
        for table, col, what in checks:
            n = self.db.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ? AND deleted = 0", (cur["id"],)).fetchone()[0]
            if n:
                raise RegistryError(f"{entity}.in_use", f"{entity} {cur['code']} still has {n} {what}; move or remove them first")

    # ------------------------------------------------------------------ journal and fold
    def _append(self, actor, label, results, kind="data"):
        return self.journal.append(actor, label, results, kind)

    def _write(self, entity, row):
        cols = ["id", "code"] + [f for f in ENTITIES[entity] if f != "code"] + [c for c in META_COLUMNS if c != "id"]
        values = [json.dumps(row[c], sort_keys=True, ensure_ascii=False) if c == "attrs" else row.get(c) for c in cols]
        self.db.execute(f"INSERT OR REPLACE INTO {entity} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", values)

    def _fold(self, seq, results):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                for r in results:
                    self._write(r["entity"], r["row"])
                self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('applied_seq', ?)", (str(seq),))
                self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('applied_hash', ?)", (self.journal.hash_at(seq),))  # also for lines with no business ops
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def applied_seq(self):
        row = self.db.execute("SELECT value FROM meta WHERE key = 'applied_seq'").fetchone()
        return int(row[0]) if row else 0

    def applied_hash(self):
        row = self.db.execute("SELECT value FROM meta WHERE key = 'applied_hash'").fetchone()
        return row[0] if row else None

    def recover(self):
        """Bring hr.db level with the journal.
        * Lines hr.db has not seen (a crash after the commit point) are folded.
        * If hr.db is AHEAD of or DIFFERENT from the journal (the journal file was lost and restored from an older backup), the
          journal is never rewritten: the difference between the journal's state and hr.db is recorded as ONE new
          `recovery` line, so nothing in hr.db is lost and the permanent history stays continuous (BAMS rule)."""
        with self.lock:
            done, last = self.applied_seq(), self.journal.last_seq()
            if not self.journal.follows(done, self.applied_hash()):
                target = self._all_rows()
                self._wipe()
                self._fold_lines(0)
                missing = self._diff_to(target)
                if missing:
                    seq = self._append("system", f"Recovery: {len(missing)} record(s) re-recorded after the journal was restored from a backup", missing, kind="recovery")
                    self._fold(seq, missing)
                    self.journal.audit("system", "journal.recovered", "system", {"records": len(missing), "tables_were_at": done, "journal_was_at": last})
                return
            self._fold_lines(done)

    def _fold_lines(self, after):
        for seq, kind, ops in self.journal.lines_after(after):
            self._fold(seq, [o for o in ops if o.get("entity") in ENTITIES])

    def _all_rows(self):
        return {e: {r["id"]: r for r in self.list(e, include_deleted=True)} for e in ENTITIES}

    def _wipe(self):
        self.db.executescript("BEGIN; " + " ".join(f"DELETE FROM {e};" for e in ENTITIES) + " DELETE FROM meta; COMMIT;")

    def _diff_to(self, target):
        """Full rows that make the current tables equal to `target` (rows only in the tables are soft-deleted)."""
        out = []
        for entity in ENTITIES:  # dependency order: org units, jobs, positions, employees
            current = {r["id"]: r for r in self.list(entity, include_deleted=True)}
            for gid, row in target[entity].items():
                if gid not in current or canonical(current[gid]) != canonical(row):
                    out.append({"entity": entity, "row": row})
        return out

    def rebuild(self):
        """Recreate every business table from the journal (disaster recovery)."""
        with self.lock:
            self._wipe()
            self._fold_lines(0)

    def restore_state(self, target, actor, label):
        """Compensating restore (BAMS): make the current data equal to `target` (rows of a backup) with ONE new
        journal line. History is never rolled back; the restore itself can be undone by restoring again."""
        with self.lock:
            now, out = _now(), []
            for entity in ENTITIES:
                current = {r["id"]: r for r in self.list(entity, include_deleted=True)}
                for gid, row in target[entity].items():
                    cur = current.get(gid)
                    wanted = {k: row[k] for k in row if k not in ("ver", "updated_at", "updated_by")}
                    if cur is None or any(canonical(cur.get(k)) != canonical(v) for k, v in wanted.items()):
                        out.append({"entity": entity, "row": {**row, "ver": (cur["ver"] if cur else row["ver"]) + 1, "updated_at": now, "updated_by": actor}})
                for gid, cur in current.items():
                    if gid not in target[entity] and not cur["deleted"]:
                        out.append({"entity": entity, "row": {**cur, "ver": cur["ver"] + 1, "deleted": 1, "deleted_at": now, "deleted_by": actor,
                                                              "updated_at": now, "updated_by": actor}})
            if not out:
                return None
            seq = self._append(actor, label, out, kind="restore")
            self._fold(seq, out)
            return seq

    def verify(self):
        return self.journal.verify()

    def fingerprint(self):
        dump = {e: [dict(r, attrs=r["attrs"]) if "attrs" in r else r for r in self.list(e, include_deleted=True)] for e in ENTITIES}
        dump = {e: rows for e, rows in dump.items() if rows or e not in LATER_ENTITIES}
        return hashlib.sha256(canonical(dump).encode("utf-8")).hexdigest()

    def close(self):
        self.db.close()
        self.journal.close()


def _plain(value):
    """Booleans are stored as 0/1 so what is read back is exactly what was written."""
    return int(value) if isinstance(value, bool) else value


def _same(a, b):
    return canonical(a) == canonical(b)
