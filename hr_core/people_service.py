"""The service side of people operations (plan 30-HR WP-H2 to WP-H5): who may do what, and the commands that change
several records at once. Mixed into HRService; every entrance goes through `require()` and the audit like the rest.

Separation of duties, enforced here on the server (the screens only hide what a person may not do):
  * a requisition, an overtime request and a leave request are decided (approved or rejected) by someone with the
    approve right who is NOT the person who raised it, and who decided and when comes from the session, not the form;
  * a candidate becomes an employee only through the hire command, a training session becomes done only through the
    complete command, a requisition becomes filled only by hiring.
Standard library only.
"""

import json
import os
import sqlite3
import threading
from contextlib import closing
from datetime import date, timedelta

from . import people_ops as ops
from .registry import RegistryError
from .scheduling import Schedule, ScheduleError

READ = {"headcount_plan": "hr.recruitment.read", "agency": "hr.recruitment.read", "hire_requisition": "hr.recruitment.read", "candidate": "hr.recruitment.read",
        "onboarding_task": "hr.recruitment.read", "contract": "hr.recruitment.read", "overtime_request": "hr.overtime.read",
        "course": "hr.training.read", "training_session": "hr.training.read", "leave_type": "hr.leave.read", "leave_request": "hr.leave.read"}
WRITE = {"headcount_plan": "hr.recruitment.write", "agency": "hr.recruitment.write", "hire_requisition": "hr.recruitment.write", "candidate": "hr.recruitment.write",
         "onboarding_task": "hr.recruitment.write", "contract": "hr.recruitment.write", "overtime_request": "hr.overtime.write",
         "course": "hr.training.write", "training_session": "hr.training.write", "leave_type": "hr.leave.write", "leave_request": "hr.leave.write"}
APPROVE = {"hire_requisition": "hr.recruitment.approve", "overtime_request": "hr.overtime.approve", "leave_request": "hr.leave.approve"}
POLICY_FILE = "overtime_policy.json"          # the old place of the policy: read once and moved into settings.db
SETTINGS_FILE = "settings.db"


class SettingsStore:
    """The company's settings that are not records of the registry (today: the overtime policy), in `data/settings.db`. It is a backup attachment,
    so a recovery on a fresh data folder brings the company's caps and premiums back (a missing file used to mean silent defaults)."""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, SETTINGS_FILE)
        self.lock = threading.RLock()
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.commit()

    def get(self, key):
        with self.lock:
            db = sqlite3.connect(self.path)
            try:
                row = db.execute("SELECT value FROM setting WHERE key = ?", (key,)).fetchone()
            finally:
                db.close()
        return json.loads(row[0]) if row else None

    def put(self, key, value):
        with self.lock, closing(sqlite3.connect(self.path)) as db:
            db.execute("INSERT INTO setting (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value, sort_keys=True)))
            db.commit()


class PeopleOpsMixin:
    # ------------------------------------------------------------------ settings
    def _load_policy(self):
        stored = self._settings.get("overtime_policy")
        if stored is None:                                      # an installation from before settings.db: move its file in
            try:
                with open(os.path.join(self.data_dir, POLICY_FILE), encoding="utf-8") as fh:
                    stored = json.load(fh)
                self._settings.put("overtime_policy", stored)
            except (FileNotFoundError, ValueError):
                stored = {}
        self.registry.overtime_policy = stored

    def overtime_policy(self, user, ip=None):
        self.require(user, "hr.overtime.read", ip, "overtime.policy")
        return ops.policy(self.registry.overtime_policy)

    def set_overtime_policy(self, user, changes, ip=None):
        """The company's overtime settings. Changing them is audited; the defaults say where they come from and what to verify."""
        self.require(user, "hr.overtime.approve", ip, "overtime.policy:change")
        unknown = set(changes) - set(ops.DEFAULT_POLICY)
        if unknown:
            raise RegistryError("policy.field", f"not an overtime setting: {sorted(unknown)[0]}")
        new = ops.policy({**self.registry.overtime_policy, **changes})
        try:
            ops.check_policy(new)
        except ScheduleError as exc:
            raise RegistryError(exc.code, str(exc)) from None
        self._settings.put("overtime_policy", {k: new[k] for k in sorted(new)})
        self.registry.overtime_policy = new
        self.journal.audit("security", "overtime.policy.changed", user["code"], {k: changes[k] for k in sorted(changes)}, ip)
        return new

    # ------------------------------------------------------------------ the rules around saving one record
    def people_fields(self, user, entity, cur, fields, ip=None):
        """The permission needed and the fields to save for a record of this module. Raises when the person may not do it."""
        fields = dict(fields)
        me = user["code"]
        perm = WRITE[entity]
        decided = lambda new, *states: new in states and (cur is None or cur.get("status") != new)  # noqa: E731
        if entity == "hire_requisition":
            if cur is None:
                fields.update(status="draft", filled=0, approved_by=None)
            else:
                fields["filled"] = cur.get("filled") or 0                       # only hiring fills a requisition
                new = fields.get("status", cur["status"])
                if new == "filled" and cur["status"] != "filled":
                    raise RegistryError("req.filled_by_hiring", "a requisition is filled by hiring, one person at a time")
                if decided(new, "approved", "open"):
                    perm = APPROVE[entity]
                    self.require(user, perm, ip, f"{entity}:decide")     # the right first, then the rule about one's own request
                    if new == "approved":
                        if cur.get("created_by") == me:
                            raise RegistryError("sod.own_requisition", "a requisition is approved by someone else than the person who raised it")
                        fields["approved_by"] = me
                    else:
                        fields["approved_by"] = cur.get("approved_by")
                elif new in ("draft", "cancelled") or new == cur["status"]:
                    fields["approved_by"] = cur.get("approved_by")
        elif entity == "candidate":
            new = fields.get("stage")
            if new == "hired" and (cur is None or cur["stage"] != "hired"):
                raise RegistryError("candidate.hire_command", "a candidate becomes an employee through Hire, which creates the employee, the contract and the onboarding")
            if cur is None or new != cur["stage"]:
                fields["stage_date"] = self.registry.today()
            else:
                fields["stage_date"] = cur.get("stage_date")
        elif entity == "overtime_request":
            if cur is None:
                fields.update(status="requested", requested_by=me, approved_by=None, decided_on=None)
            else:
                new = fields.get("status", cur["status"])
                fields["requested_by"] = cur.get("requested_by")
                if decided(new, "approved", "rejected"):
                    perm = APPROVE[entity]
                    self.require(user, perm, ip, f"{entity}:decide")     # the right first, then the rule about one's own request
                    if cur.get("requested_by") == me:
                        raise RegistryError("sod.own_overtime", "overtime is approved or rejected by someone else than the person who asked for it")
                    fields.update(approved_by=me, decided_on=self.registry.today())
                else:
                    fields.update(approved_by=cur.get("approved_by"), decided_on=cur.get("decided_on"))
        elif entity == "leave_request":
            emp = self.registry.by_id("employee", fields.get("employee_id") or (cur or {}).get("employee_id"))
            first, last = fields.get("from_date") or (cur or {}).get("from_date"), fields.get("to_date") or (cur or {}).get("to_date")
            if cur and cur["status"] == "approved":
                if any(k in fields and str(fields[k]) != str(cur.get(k)) for k in ("employee_id", "leave_type_id", "from_date", "to_date", "days")):
                    raise RegistryError("leave.frozen", "approved leave does not change: cancel it and submit a new request")
                fields["days"] = cur["days"]
            elif emp and first and last:
                fields["days"] = self.leave_days(emp["id"], first, last)
            if cur is None:
                fields.update(status="requested", approver=None, decided_on=None)
            else:
                new = fields.get("status", cur["status"])
                if decided(new, "approved", "rejected"):
                    perm = APPROVE[entity]
                    self.require(user, perm, ip, f"{entity}:decide")     # the right first, then the rule about one's own request
                    if cur.get("created_by") == me:
                        raise RegistryError("sod.own_leave", "leave is approved or rejected by someone else than the person who entered it")
                    fields.update(approver=me, decided_on=self.registry.today())
                else:
                    fields.update(approver=cur.get("approver"), decided_on=cur.get("decided_on"))
        elif entity == "training_session":
            if (cur is None and fields.get("status") == "done") or (cur is not None and fields.get("status") == "done" and cur["status"] != "done"):
                raise RegistryError("session.complete_command", "a session is completed with Complete, which records the results and qualifies the people who passed")
            fields.setdefault("status", "planned")
            att = fields.get("attendees")
            if isinstance(att, str) and att.strip() and not att.strip().startswith("["):      # typed as E000001, E000002
                att = [{"employee_code": c.strip()} for c in att.replace(";", ",").split(",") if c.strip()]
            if isinstance(att, list):
                fields["attendees"] = json.dumps(att, ensure_ascii=False)
        return perm, fields

    def leave_days(self, employee_id, first, last):
        """Working days in a leave: the calendar days minus the person's rest days and holidays (an unscheduled day counts)."""
        plan = Schedule(self.registry)
        a, b = date.fromisoformat(first), date.fromisoformat(last)
        if b < a:
            return 1
        n = 0
        for i in range((b - a).days + 1):
            d = plan.day(employee_id, (a + timedelta(days=i)).isoformat())
            if d["status"] not in ("rest", "holiday"):
                n += 1
        return max(1, n)

    # ------------------------------------------------------------------ recruitment
    def hire(self, user, candidate_code, hire, ip=None):
        """A candidate at the offer stage becomes an employee: the employee, the contract, the onboarding checklist, the candidate's
        stage and the requisition's count change in ONE journal line (all or nothing)."""
        self.require(user, "hr.recruitment.write", ip, f"hire:{candidate_code}")
        reg = self.registry
        cand = reg.get("candidate", candidate_code)
        if not cand or cand["deleted"]:
            raise RegistryError("candidate.not_found", f"candidate {candidate_code} does not exist")
        if cand["stage"] != "offered":
            raise RegistryError("hire.stage", f"only a candidate who has been offered the job can be hired (this one is {cand['stage']})")
        req = reg.by_id("hire_requisition", cand["requisition_id"])
        if not req or req["deleted"] or req["status"] not in ("approved", "open"):
            raise RegistryError("hire.requisition", "the requisition is not approved or open")
        if int(req.get("filled") or 0) >= int(req["count"]):
            raise RegistryError("hire.full", "the requisition is already filled")
        hire_date = hire.get("hire_date") or reg.today()
        try:
            ops._d(hire_date, "the hire date")
        except ScheduleError as exc:
            raise RegistryError(exc.code, str(exc)) from None
        etype = hire.get("employment_type") or req["employment_type"]
        code = ops.next_employee_code(reg)
        contract_end = hire.get("contract_end")
        if not contract_end and etype == "fixed_term" and req.get("contract_months"):
            contract_end = _add_months(hire_date, int(req["contract_months"]))
        position_id = hire.get("position_id") or req.get("position_id")
        worker = {"regular": "Regular", "fixed_term": "Fixed-term", "agency": "Agency", "intern": "Intern"}[etype]
        todo = [reg.op_put("employee", code, {"preferred_name": cand["display_name"], "legal_name": cand["display_name"], "employment_status": "Active",
                                              "worker_type": worker, "hire_date": hire_date, "position_id": position_id})]
        contract_code = f"C-{code}-1"
        todo.append(reg.op_put("contract", contract_code, {"employee_id": reg.gid("employee", code), "employment_type": etype, "start_date": hire_date, "end_date": contract_end,
                                                            "agency_id": hire.get("agency_id") or req.get("agency_id"), "requisition_id": req["id"], "reason": req["reason"]}))
        due = (date.fromisoformat(hire_date) + timedelta(days=7)).isoformat()
        for kind in ops.ONBOARDING_KINDS:
            todo.append(reg.op_put("onboarding_task", f"ONB-{code}-{kind}", {"employee_id": reg.gid("employee", code), "kind": kind, "due": due, "done_on": None}))
        todo.append(reg.op_put("candidate", candidate_code, {"stage": "hired", "stage_date": reg.today(), "note": f"{(cand.get('note') or '').strip()} hired as {code}".strip()}, cand["ver"]))
        filled = int(req.get("filled") or 0) + 1
        todo.append(reg.op_put("hire_requisition", req["code"], {"filled": filled, "status": "filled" if filled >= int(req["count"]) else "open"}, req["ver"]))
        seq = self._commit(user, ip, f"Hired {candidate_code} as {code}", todo, "recruitment.hired", "employee", code)
        return {"seq": seq, "employee": code, "contract": contract_code, "requisition": {"code": req["code"], "filled": filled, "of": int(req["count"])}}

    def onboarding_status(self, user, employee_code, ip=None):
        self.require(user, "hr.recruitment.read", ip, "onboarding")
        emp = self.registry.get("employee", employee_code)
        if not emp:
            raise RegistryError("employee.not_found", f"employee {employee_code} does not exist")
        tasks = [t for t in self.registry.list("onboarding_task") if t["employee_id"] == emp["id"]]
        pending = [t["kind"] for t in tasks if not t.get("done_on") and t["kind"] in ops.REQUIRED_FOR_LINE]
        return {"employee": employee_code, "tasks": [{"kind": t["kind"], "due": t["due"], "done_on": t["done_on"], "code": t["code"], "ver": t["ver"]} for t in tasks],
                "schedulable_on_a_line": not pending, "blocking": pending}

    def propose_headcount(self, user, apply=False, relief_bp=None, ip=None):
        """From GMES's crew requirements: the average heads needed per line and month plus a relief allowance. With apply, the proposals
        are saved as headcount plans (source crew_requirement); a person's own plan for the same line and month is never overwritten."""
        self.require(user, "hr.recruitment.write", ip, "headcount.propose")
        rows = self.eco_inbox().requirements("0000-01-01", "9999-12-31")
        proposals = ops.headcount_from_crew(rows, 800 if relief_bp is None else int(relief_bp))
        made = []
        if apply and proposals:
            todo = []
            for p in proposals:
                code = f"HP-{p['work_center_code']}-{p['period']}"
                cur = self.registry.get("headcount_plan", code)
                if cur and cur["source"] == "manual":
                    continue
                todo.append(self.registry.op_put("headcount_plan", code, {"work_center_code": p["work_center_code"], "period": p["period"], "planned_fte": p["planned_fte"],
                                                                        "source": "crew_requirement", "note": f"average {p['average_required']} over {p['days']} day(s), relief allowance included"},
                                                 cur["ver"] if cur else None))
                made.append(code)
            if todo:
                self._commit(user, ip, f"Headcount proposed from crew requirements: {len(made)}", todo, "recruitment.plan_proposed", "headcount_plan", "crew")
        return {"proposals": proposals, "saved": made}

    def expire_contracts(self, user=None, ip=None):
        """Fixed-term contracts that ended: the employee becomes Terminated on the contract's last day (one journal line)."""
        actor = user["code"] if user else "system"
        todo = ops.contract_ends(self.registry, self.registry.today())
        if not todo:
            return {"ended": []}
        self.registry.commit(actor, f"Contract end: {len(todo)} employee(s) terminated", todo)
        self.journal.audit("activity", "recruitment.contract_ended", actor, {"employees": [o["code"] for o in todo]}, ip)
        return {"ended": [o["code"] for o in todo]}

    # ------------------------------------------------------------------ training
    def complete_training(self, user, session_code, results, ip=None):
        """Records the results of a planned session. A pass grants or renews the course's qualification (level, certified on the session
        date, expiry from the validity, evidence = the session) and completes the onboarding task the course stands for; a fail changes nothing
        but the record. One journal line: the session and every qualification, or nothing."""
        self.require(user, "hr.training.write", ip, f"training:{session_code}")
        reg = self.registry
        sess = reg.get("training_session", session_code)
        if not sess or sess["deleted"]:
            raise RegistryError("session.not_found", f"session {session_code} does not exist")
        if sess["status"] != "planned":
            raise RegistryError("session.not_planned", f"session {session_code} is {sess['status']}")
        if sess["session_date"] > reg.today():
            raise RegistryError("session.future", f"session {session_code} is on {sess['session_date']}: record the results when it has taken place")
        course = reg.by_id("course", sess["course_id"])
        try:
            expected = json.loads(sess["attendees"]) if sess.get("attendees") else []
        except ValueError:
            expected = []
        codes = [a["employee_code"] if isinstance(a, dict) else a for a in expected]
        by = {r["employee_code"]: r["result"] for r in results or []}
        stray = sorted(set(by) - set(codes))
        if stray:
            raise RegistryError("session.stranger", f"{stray[0]} did not attend this session")
        if any(r not in ("pass", "fail") for r in by.values()):
            raise RegistryError("session.result", "a result is pass or fail")
        if set(codes) - set(by):
            raise RegistryError("session.missing", f"a result is needed for {sorted(set(codes) - set(by))[0]}")
        todo, qualified = [], []
        skill = reg.by_id("skill", course["skill_id"]) if course.get("skill_id") else None
        for emp_code in codes:
            if by[emp_code] != "pass":
                continue
            emp = reg.get("employee", emp_code)
            if skill:
                q_code = f"{emp_code}-{skill['code']}"
                cur = reg.get("employee_skill", q_code, include_deleted=True)
                months = course.get("validity_months") or skill.get("validity_months")
                level = int(course["grants_level"])
                if cur and not cur["deleted"]:
                    level = max(level, int(cur["level"]))                 # a course never lowers what a person holds
                todo.append(reg.op_put("employee_skill", q_code, {"employee_id": emp["id"], "skill_id": skill["id"], "level": level, "certified_on": sess["session_date"],
                                                                 "expires_on": ops.default_expiry(sess["session_date"], months), "evidence": session_code}, cur["ver"] if cur else None))
                qualified.append(q_code)
            if course.get("onboarding_kind"):
                task = reg.get("onboarding_task", f"ONB-{emp_code}-{course['onboarding_kind']}")
                if task and not task["deleted"] and not task.get("done_on"):
                    todo.append(reg.op_put("onboarding_task", task["code"], {"done_on": sess["session_date"]}, task["ver"]))
        results_json = json.dumps([{"employee_code": c, "result": by[c]} for c in codes], ensure_ascii=False)
        todo.append(reg.op_put("training_session", session_code, {"attendees": results_json, "status": "done"}, sess["ver"]))
        seq = self._commit(user, ip, f"Training session {session_code} completed", todo, "training.completed", "training_session", session_code)
        return {"seq": seq, "qualified": qualified, "failed": sorted(c for c in codes if by[c] == "fail")}

    # ------------------------------------------------------------------ leave and overtime figures
    def leave_balance_of(self, user, employee_code, year, ip=None):
        self.require(user, "hr.leave.read", ip, "leave.balance")
        emp = self.registry.get("employee", employee_code)
        if not emp:
            raise RegistryError("employee.not_found", f"employee {employee_code} does not exist")
        out = []
        for lt in self.registry.list("leave_type"):
            if not lt.get("active", 1):
                continue
            capped = lt.get("annual_days") not in (None, "", 0, "0")
            used = sum(ops.days_in_year(self.registry, emp["id"], date.fromisoformat(r["from_date"]), date.fromisoformat(r["to_date"]), int(r["days"]), int(year))
                       for r in self.registry.list("leave_request") if r["employee_id"] == emp["id"] and r["leave_type_id"] == lt["id"]
                       and r["status"] == "approved" and str(r["from_date"])[:4] <= str(year) <= str(r["to_date"])[:4])
            out.append({"leave_type": lt["code"], "name": lt["name"], "entitlement": int(lt["annual_days"]) if capped else None, "used": used,
                        "left": ops.leave_balance(self.registry, emp["id"], lt, int(year)) if capped else None})
        return {"employee": employee_code, "year": int(year), "balances": out}

    def overtime_figures(self, user, period, ip=None):
        self.require(user, "hr.overtime.read", ip, "overtime.figures")
        worked = []
        try:
            for r in self.eco_inbox().labour(period + "-01", period + "-31"):
                planned = Schedule(self.registry).day(self.registry.gid("employee", r["employee_code"]), r["production_date"])
                worked.append({"employee": r["employee_code"], "date": r["production_date"], "beyond_plan": max(0, r["total_minutes"] - planned["paid_minutes"])})
        except Exception:                                                      # the evidence is optional: without manufacturing there is none
            worked = []
        try:
            return ops.overtime_for_period(self.registry, period, worked)
        except ScheduleError as exc:
            raise RegistryError(exc.code, str(exc)) from None


def _add_months(iso_day, months):
    y, m, d = int(iso_day[:4]), int(iso_day[5:7]), int(iso_day[8:10])
    m0 = m - 1 + months
    y, m = y + m0 // 12, m0 % 12 + 1
    last = (date(y + (m // 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d, last)).isoformat()
