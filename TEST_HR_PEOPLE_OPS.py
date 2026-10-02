"""People operations (plan 30-HR WP-H2 to WP-H5): recruitment and onboarding, overtime, training that qualifies, leave.

Proves the rules that matter: a requisition is approved by someone else, the headcount plan limits it, a candidate becomes an
employee only through Hire (employee + contract + onboarding in one line), a new hire is not schedulable on a line before the
medical check, protective equipment and ESD training, a training pass qualifies and completes the onboarding task, leave balances
and overlaps, overtime is approved by someone else and capped, and approved leave takes a person out of the plan.
Synthetic data only. Standard library only.
"""

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"

from hr_core import people_ops, scheduling  # noqa: E402
from hr_core.auth import AuthError  # noqa: E402
from hr_core.registry import RegistryError  # noqa: E402
from hr_core.service import HRService  # noqa: E402

results = {}
TMP = tempfile.mkdtemp(prefix="hr_people_ops_")


def check(name, ok, detail=None):
    results[name] = bool(ok)
    if not ok:
        print(json.dumps(results, indent=2))
        raise AssertionError(f"{name}: {detail}")


def refused(code, fn):
    try:
        fn()
    except (RegistryError, AuthError, scheduling.ScheduleError) as exc:
        return exc.code == code or print("got", exc.code, exc)
    return False


svc = HRService(os.path.join(TMP, "data"), COMPANY, "NILE", "Nile Home", backup_dir=os.path.join(TMP, "backups"))
reg = svc.registry
TODAY = "2026-10-12"                          # a Monday
reg.today = lambda: TODAY
svc.bootstrap_admin("admin", "Admin", "Admin-2026!x")


def sign_in(username):
    svc.auth.commit("admin", "clear first-login flag", [{"entity": "user", "code": username, "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", username)["ver"]}])
    return svc.login(username, "Admin-2026!x")[1]


_, admin = svc.login("admin", "Admin-2026!x")
admin = sign_in("admin")
svc.create_user(admin, "boss", "Boss", "Admin-2026!x", "administrator")
svc.create_user(admin, "officer", "Officer", "Admin-2026!x", "hr_officer")
boss, officer = sign_in("boss"), sign_in("officer")
save = lambda u, e, code, f, ver=None: svc.save(u, e, code, f, ver)["row"]  # noqa: E731

# a small company: a job, people on a day shift, a skill
company = [u for u in reg.list("org_unit") if u["type"] == "company"][0]
site = save(admin, "org_unit", "CAI", {"type": "site", "name": "Cairo", "parent_id": company["id"]})
dept = save(admin, "org_unit", "FA", {"type": "department", "name": "Final assembly", "parent_id": site["id"]})
job = save(admin, "job", "OPR", {"title": "Line operator"})
pos = save(admin, "position", "POS-OPR", {"job_id": job["id"], "org_unit_id": dept["id"], "status": "open"})
e1 = save(admin, "employee", "E000001", {"preferred_name": "Aya", "employment_status": "Active"})
e2 = save(admin, "employee", "E000002", {"preferred_name": "Omar", "employment_status": "Active"})
day = save(admin, "shift", "A", {"name": "Day", "start_time": "07:00", "end_time": "15:00", "break_minutes": 30, "grace_minutes": 10})
night = save(admin, "shift", "C", {"name": "Night", "start_time": "23:00", "end_time": "07:00", "break_minutes": 30, "grace_minutes": 10})
cal = save(admin, "work_calendar", "EG", {"name": "Egypt", "rest_days": "FRI", "holidays": ""})
save(admin, "shift_assignment", "E000001-2026-10-01-R", {"employee_id": e1["id"], "shift_id": day["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-01"})
save(admin, "shift_assignment", "E000002-2026-10-01-R", {"employee_id": e2["id"], "shift_id": night["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-01"})
esd = save(admin, "skill", "ESD", {"name": "ESD handling", "category": "safety", "validity_months": 12})

# ================================================================== 1. headcount plan and requisitions
save(officer, "headcount_plan", "HP-OPR-2026-11", {"job_id": job["id"], "period": "2026-11", "planned_fte": 2, "source": "manual"})
agency = save(officer, "agency", "AG1", {"name": "Temp Staff Co", "fee_percent": 12, "active": 1})
req_fields = {"job_id": job["id"], "position_id": pos["id"], "count": 2, "employment_type": "regular", "reason": "growth", "needed_by": "2026-11-15"}
r1 = save(officer, "hire_requisition", "REQ-0001", {**req_fields, "status": "approved"})          # asking for "approved" at creation
check("a_requisition_always_starts_as_a_draft", r1["status"] == "draft" and r1["filled"] == 0, r1)
check("the_person_who_raised_it_cannot_approve_it", refused("perm.denied", lambda: save(officer, "hire_requisition", "REQ-0001", {"status": "approved"}, r1["ver"])))
r1b = save(admin, "hire_requisition", "REQ-0009", {**req_fields, "count": 1, "needed_by": "2026-12-15"})    # a month with no plan
check("an_approver_cannot_approve_their_own_requisition", refused("sod.own_requisition", lambda: save(admin, "hire_requisition", "REQ-0009", {"status": "approved"}, r1b["ver"])))
r1 = save(boss, "hire_requisition", "REQ-0001", {"status": "approved"}, r1["ver"])
check("someone_else_approves_and_is_recorded", r1["status"] == "approved" and r1["approved_by"] == "boss", r1)
check("after_approval_the_number_is_frozen", refused("req.frozen", lambda: save(officer, "hire_requisition", "REQ-0001", {"count": 5}, r1["ver"])))
check("beyond_the_plan_needs_a_written_reason", refused("req.over_plan", lambda: save(officer, "hire_requisition", "REQ-0002", {**req_fields, "count": 1})))
over = save(officer, "hire_requisition", "REQ-0002", {**req_fields, "count": 1, "note": "the customer order grew by a third"})
check("a_written_reason_allows_it", over["count"] == 1)
check("a_fixed_term_requisition_needs_its_length", refused("number.format", lambda: save(officer, "hire_requisition", "REQ-0003", {**req_fields, "employment_type": "fixed_term", "note": "seasonal peak of the season"})))

# ================================================================== 2. candidates and hiring
c1 = save(officer, "candidate", "CAN-0001", {"requisition_id": r1["id"], "display_name": "Nour Adel", "source": "referral", "stage": "applied"})
check("a_candidate_is_taken_for_an_approved_requisition_only", refused("candidate.requisition", lambda: save(officer, "candidate", "CAN-0009", {"requisition_id": r1b["id"], "display_name": "X", "source": "walk_in", "stage": "applied"})))
check("a_candidate_cannot_be_marked_hired_by_hand", refused("candidate.hire_command", lambda: save(officer, "candidate", "CAN-0001", {"stage": "hired"}, c1["ver"])))
check("hire_needs_the_offer_first", refused("hire.stage", lambda: svc.hire(officer, "CAN-0001", {})))
for stage in ("screened", "interviewed", "offered"):
    c1 = save(officer, "candidate", "CAN-0001", {"stage": stage}, c1["ver"])
check("stages_only_move_forward", refused("candidate.backwards", lambda: save(officer, "candidate", "CAN-0001", {"stage": "screened"}, c1["ver"])))
hired = svc.hire(officer, "CAN-0001", {"hire_date": "2026-10-12"})
new = hired["employee"]
check("hire_creates_the_employee", new == "E000003" and reg.get("employee", new)["employment_status"] == "Active", hired)
check("hire_fills_the_requisition_one_at_a_time", hired["requisition"] == {"code": "REQ-0001", "filled": 1, "of": 2} and reg.get("hire_requisition", "REQ-0001")["status"] == "open")
check("hire_creates_a_contract_and_the_onboarding_checklist", reg.get("contract", "C-E000003-1")["employment_type"] == "regular"
      and len([t for t in reg.list("onboarding_task") if t["code"].startswith("ONB-E000003-")]) == len(people_ops.ONBOARDING_KINDS))
check("the_candidate_is_hired", reg.get("candidate", "CAN-0001")["stage"] == "hired")
status = svc.onboarding_status(officer, new)
check("onboarding_blocks_the_line_until_the_three_checks_are_done", not status["schedulable_on_a_line"] and status["blocking"] == ["esd_training", "medical", "ppe"], status)
E3 = reg.get("employee", new)
check("a_new_hire_cannot_be_scheduled_before_onboarding", refused("hr.onboarding.incomplete", lambda: save(officer, "shift_assignment", "E000003-2026-10-12-R",
      {"employee_id": E3["id"], "shift_id": day["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-12"})))
for kind in ("medical", "ppe"):
    t = reg.get("onboarding_task", f"ONB-E000003-{kind}")
    save(officer, "onboarding_task", t["code"], {"done_on": TODAY}, t["ver"])

# ================================================================== 3. training that qualifies
course = save(officer, "course", "ESD-101", {"name": "ESD basics", "skill_id": esd["id"], "grants_level": 2, "validity_months": 12, "duration_hours": 4, "onboarding_kind": "esd_training"})
sess = save(officer, "training_session", "TS-0001", {"course_id": course["id"], "session_date": "2026-10-13", "trainer": "Safety officer",
                                                     "attendees": [{"employee_code": "E000003"}, {"employee_code": "E000001"}], "status": "planned"})
check("a_session_cannot_be_marked_done_by_hand", refused("session.complete_command", lambda: save(officer, "training_session", "TS-0001", {"status": "done"}, sess["ver"])))
check("results_wait_for_the_session_to_take_place", refused("session.future", lambda: svc.complete_training(officer, "TS-0001", [])))
reg.today = lambda: "2026-10-13"
check("a_stranger_cannot_have_a_result", refused("session.stranger", lambda: svc.complete_training(officer, "TS-0001", [{"employee_code": "E000002", "result": "pass"}])))
done = svc.complete_training(officer, "TS-0001", [{"employee_code": "E000003", "result": "pass"}, {"employee_code": "E000001", "result": "fail"}])
q = reg.get("employee_skill", "E000003-ESD")
check("a_pass_qualifies_at_the_course_level_with_expiry_and_evidence", q and q["level"] == 2 and q["certified_on"] == "2026-10-13" and q["expires_on"] == "2027-10-13" and q["evidence"] == "TS-0001", q)
check("a_fail_qualifies_nobody", reg.get("employee_skill", "E000001-ESD") is None and done["failed"] == ["E000001"])
check("the_pass_completes_the_esd_onboarding_task", reg.get("onboarding_task", "ONB-E000003-esd_training")["done_on"] == "2026-10-13")
check("a_completed_session_does_not_change", refused("session.done", lambda: save(officer, "training_session", "TS-0001", {"trainer": "Someone else"}, reg.get("training_session", "TS-0001")["ver"])))
check("a_session_completes_only_once", refused("session.not_planned", lambda: svc.complete_training(officer, "TS-0001", [])))
reg.today = lambda: "2026-10-14"
check("after_onboarding_the_new_hire_can_be_scheduled", svc.onboarding_status(officer, new)["schedulable_on_a_line"]
      and save(officer, "shift_assignment", "E000003-2026-10-14-R", {"employee_id": E3["id"], "shift_id": day["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-14"})["code"])
s2 = save(officer, "training_session", "TS-0002", {"course_id": course["id"], "session_date": "2027-03-01", "trainer": "Safety officer", "attendees": [{"employee_code": "E000003"}], "status": "planned"})
reg.today = lambda: "2027-03-01"
svc.complete_training(officer, "TS-0002", [{"employee_code": "E000003", "result": "pass"}])
q2 = reg.get("employee_skill", "E000003-ESD")
check("recertification_extends_the_expiry", q2["certified_on"] == "2027-03-01" and q2["expires_on"] == "2028-03-01", q2)
save(admin, "employee_skill", "E000003-ESD", {"level": 3}, reg.get("employee_skill", "E000003-ESD")["ver"])
save(officer, "training_session", "TS-0003", {"course_id": course["id"], "session_date": "2027-03-01", "trainer": "Safety officer", "attendees": [{"employee_code": "E000003"}], "status": "planned"})
svc.complete_training(officer, "TS-0003", [{"employee_code": "E000003", "result": "pass"}])
check("a_course_never_lowers_a_higher_qualification", reg.get("employee_skill", "E000003-ESD")["level"] == 3)
reg.today = lambda: TODAY

# ================================================================== 4. a fixed-term hire and the end of the contract
r3 = save(officer, "hire_requisition", "REQ-0004", {**req_fields, "count": 1, "employment_type": "fixed_term", "contract_months": 2, "reason": "seasonal", "needed_by": "2026-10-20", "note": "seasonal peak of the season"})
r3 = save(boss, "hire_requisition", "REQ-0004", {"status": "approved"}, r3["ver"])
c4 = save(officer, "candidate", "CAN-0004", {"requisition_id": r3["id"], "display_name": "Salma Ali", "source": "agency", "stage": "offered"})
h4 = svc.hire(officer, "CAN-0004", {"hire_date": "2026-10-12"})
check("a_fixed_term_hire_gets_an_end_date_from_the_requisition", reg.get("contract", f"C-{h4['employee']}-1")["end_date"] == "2026-12-12")
check("a_full_requisition_becomes_filled", reg.get("hire_requisition", "REQ-0004")["status"] == "filled")
reg.today = lambda: "2026-12-20"
ended = svc.expire_contracts(boss)
emp4 = reg.get("employee", h4["employee"])
check("when_the_contract_ends_the_employee_is_terminated_on_its_last_day", ended["ended"] == [h4["employee"]] and emp4["employment_status"] == "Terminated" and emp4["termination_date"] == "2026-12-12", emp4)
check("ending_contracts_twice_changes_nothing", svc.expire_contracts(boss)["ended"] == [])
reg.today = lambda: TODAY

# ================================================================== 5. leave
annual = save(officer, "leave_type", "ANNUAL", {"name": "Annual leave", "paid": 1, "annual_days": 21, "carry_over_days": 5, "active": 1})
unpaid = save(officer, "leave_type", "UNPAID", {"name": "Unpaid leave", "paid": 0, "active": 1})
lv = save(officer, "leave_request", "LV-1", {"employee_id": e1["id"], "leave_type_id": annual["id"], "from_date": "2026-10-19", "to_date": "2026-10-23", "days": 99, "status": "approved"})
check("a_leave_request_starts_as_requested_and_days_are_computed", lv["status"] == "requested" and lv["days"] == 4, lv)          # Friday is a rest day
check("the_person_who_entered_it_cannot_approve_it", refused("perm.denied", lambda: save(officer, "leave_request", "LV-1", {"status": "approved"}, lv["ver"])))
lv = save(boss, "leave_request", "LV-1", {"status": "approved"}, lv["ver"])
check("someone_else_approves_leave", lv["status"] == "approved" and lv["approver"] == "boss")
own = save(admin, "leave_request", "LV-5", {"employee_id": e2["id"], "leave_type_id": unpaid["id"], "from_date": "2027-02-01", "to_date": "2027-02-02"})
check("even_an_approver_cannot_approve_leave_they_entered", refused("sod.own_leave", lambda: save(admin, "leave_request", "LV-5", {"status": "approved"}, own["ver"])))
check("leave_that_overlaps_is_refused", refused("leave.overlap", lambda: save(officer, "leave_request", "LV-2", {"employee_id": e1["id"], "leave_type_id": unpaid["id"], "from_date": "2026-10-22", "to_date": "2026-10-25"})))
plan = scheduling.Schedule(reg)
check("approved_leave_takes_the_person_out_of_the_plan", plan.day(e1["id"], "2026-10-20")["status"] == "leave" and plan.day(e1["id"], "2026-10-26")["status"] == "work")
bal = svc.leave_balance_of(officer, "E000001", 2026)["balances"]
check("the_balance_is_the_entitlement_minus_the_approved_days", [b for b in bal if b["leave_type"] == "ANNUAL"][0] == {"leave_type": "ANNUAL", "name": "Annual leave", "entitlement": 21, "used": 4, "left": 17})
save(admin, "employee", "E000002", {"hire_date": "2020-01-01"}, reg.get("employee", "E000002")["ver"])
check("unused_days_carry_over_up_to_the_limit_for_someone_employed_the_year_before",
      [b for b in svc.leave_balance_of(officer, "E000002", 2026)["balances"] if b["leave_type"] == "ANNUAL"][0]["left"] == 26)
big = save(officer, "leave_request", "LV-3", {"employee_id": e1["id"], "leave_type_id": annual["id"], "from_date": "2026-11-01", "to_date": "2026-12-30"})
check("leave_beyond_the_balance_cannot_be_approved", refused("leave.insufficient", lambda: save(boss, "leave_request", "LV-3", {"status": "approved"}, big["ver"])))
check("unpaid_leave_has_no_cap", save(officer, "leave_request", "LV-4", {"employee_id": e2["id"], "leave_type_id": unpaid["id"], "from_date": "2026-11-01", "to_date": "2026-12-30"})["days"] >= 50)
check("approved_leave_cannot_be_edited_by_the_officer_who_only_may_write", refused("leave.frozen", lambda: save(officer, "leave_request", "LV-1", {"from_date": "2027-04-01", "to_date": "2027-05-01"}, lv["ver"])))
check("approved_leave_cannot_change_person_type_or_days_either", refused("leave.frozen", lambda: save(officer, "leave_request", "LV-1", {"days": 1}, lv["ver"])))
check("cancelling_cannot_rewrite_the_approved_dates", refused("leave.frozen", lambda: save(officer, "leave_request", "LV-1", {"status": "cancelled", "from_date": "2027-04-01", "to_date": "2027-05-01"}, lv["ver"])))
check("approved_leave_can_still_be_cancelled", save(officer, "leave_request", "LV-1", {"status": "cancelled"}, lv["ver"])["status"] == "cancelled")
lv = save(officer, "leave_request", "LV-1B", {"employee_id": e1["id"], "leave_type_id": annual["id"], "from_date": "2026-10-19", "to_date": "2026-10-23"})
lv = save(boss, "leave_request", "LV-1B", {"status": "approved"}, lv["ver"])      # the same days again, for what follows
ny = save(officer, "leave_request", "LV-NY", {"employee_id": e2["id"], "leave_type_id": annual["id"], "from_date": "2026-12-31", "to_date": "2027-01-04"})
check("leave_over_new_year_counts_its_working_days", ny["days"] == 4, ny)                                          # Thu 31 Dec, then Sat, Sun, Mon: Friday 1 January is a rest day
save(boss, "leave_request", "LV-NY", {"status": "approved"}, ny["version"] if "version" in ny else ny["ver"])
left = lambda y: [b for b in svc.leave_balance_of(officer, "E000002", y)["balances"] if b["leave_type"] == "ANNUAL"][0]
check("each_year_is_charged_for_its_own_days", left(2026)["used"] == 1 and left(2027)["used"] == 3 and left(2026)["left"] == 25 and left(2027)["left"] == 23, [left(2026), left(2027)])

tiny = save(officer, "leave_type", "TINY", {"name": "Synthetic capped leave", "paid": 1, "annual_days": 1, "carry_over_days": 1})
carry = save(officer, "leave_request", "LV-CARRY", {"employee_id": e1["id"], "leave_type_id": tiny["id"], "from_date": "2026-12-31", "to_date": "2027-01-03"})
check("approval_reduces_next_year_carryover_by_the_proposed_prior_year_days", refused("leave.insufficient", lambda: save(boss, "leave_request", "LV-CARRY", {"status": "approved"}, carry["ver"])))
from datetime import date  # noqa: E402
from unittest.mock import patch  # noqa: E402
with patch.object(people_ops.Schedule, "day", return_value={"status": "rest"}):
    shares = [people_ops.days_in_year(reg, e1["id"], date(2026, 12, 31), date(2027, 1, 1), 1, y) for y in (2026, 2027)]
check("manual_cross_year_leave_on_rest_days_does_not_crash", sum(shares) == 1, shares)

# ================================================================== 6. overtime
check("overtime_is_asked_before_it_is_worked", refused("ot.past", lambda: save(officer, "overtime_request", "OT-0", {"employee_id": e1["id"], "work_date": "2026-09-01", "planned_minutes": 60, "kind": "day", "reason": "late order"})))
ot = save(officer, "overtime_request", "OT-1", {"employee_id": e1["id"], "work_date": "2026-10-13", "planned_minutes": 90, "kind": "day", "reason": "customer order", "status": "approved"})
check("an_overtime_request_starts_as_requested", ot["status"] == "requested" and ot["requested_by"] == "officer", ot)
check("the_daily_limit_including_overtime_holds", refused("ot.daily_cap", lambda: save(officer, "overtime_request", "OT-2", {"employee_id": e1["id"], "work_date": "2026-10-14", "planned_minutes": 200, "kind": "day", "reason": "customer order"})))
check("a_rest_day_needs_the_rest_day_kind", refused("ot.kind_mismatch", lambda: save(officer, "overtime_request", "OT-3", {"employee_id": e1["id"], "work_date": "2026-10-16", "planned_minutes": 120, "kind": "day", "reason": "customer order"})))
check("overtime_is_not_asked_on_leave", refused("ot.on_leave", lambda: save(officer, "overtime_request", "OT-4", {"employee_id": e1["id"], "work_date": "2026-10-20", "planned_minutes": 60, "kind": "day", "reason": "customer order"})))
save(officer, "overtime_request", "OT-5", {"employee_id": e1["id"], "work_date": "2026-10-16", "planned_minutes": 120, "kind": "rest_day", "reason": "customer order"})
save(officer, "overtime_request", "OT-6", {"employee_id": e2["id"], "work_date": "2026-10-13", "planned_minutes": 60, "kind": "night", "reason": "end of month shipment"})
own_ot = save(admin, "overtime_request", "OT-8", {"employee_id": e2["id"], "work_date": "2026-10-14", "planned_minutes": 60, "kind": "night", "reason": "end of month shipment"})
check("even_an_approver_cannot_approve_overtime_they_asked_for", refused("sod.own_overtime", lambda: save(admin, "overtime_request", "OT-8", {"status": "approved"}, own_ot["ver"])))
check("the_person_who_asked_cannot_approve", refused("perm.denied", lambda: save(officer, "overtime_request", "OT-1", {"status": "approved"}, ot["ver"])))
for code in ("OT-1", "OT-5", "OT-6"):
    save(boss, "overtime_request", code, {"status": "approved"}, reg.get("overtime_request", code)["ver"])
check("a_decided_request_does_not_change", refused("ot.decided", lambda: save(boss, "overtime_request", "OT-1", {"planned_minutes": 30}, reg.get("overtime_request", "OT-1")["ver"])))
pol = people_ops.policy(reg.overtime_policy)
check("classification_follows_the_plan", people_ops.classify_day(reg, e1["id"], "2026-10-13", pol) == "day" and people_ops.classify_day(reg, e2["id"], "2026-10-13", pol) == "night"
      and people_ops.classify_day(reg, e1["id"], "2026-10-16", pol) == "rest_day")
figs = svc.overtime_figures(boss, "2026-10")
by = {p["employee"]: p for p in figs["employees"]}
check("the_figures_give_minutes_by_kind_and_premium", by["E000001"]["minutes"]["day"] == 90 and by["E000001"]["minutes"]["rest_day"] == 120 and by["E000002"]["minutes"]["night"] == 60
      and by["E000001"]["premium_bp"]["night"] == 7000, by)
check("rest_day_work_earns_a_substitute_day", by["E000001"]["substitute_days"] == 1 and by["E000002"]["substitute_days"] == 0)
unapproved = people_ops.overtime_for_period(reg, "2026-10", [{"employee": "E000001", "date": "2026-10-13", "beyond_plan": 30}, {"employee": "E000001", "date": "2026-10-14", "beyond_plan": 45}])
check("overtime_worked_without_approval_is_an_exception", [(x["employee"], x["date"]) for x in unapproved["exceptions"]] == [("E000001", "2026-10-14")])
check("the_policy_is_a_setting_with_its_source", refused("number.range", lambda: svc.set_overtime_policy(boss, {"max_daily_minutes_incl_ot": 5})) and "verify" in svc.overtime_policy(boss)["source_note"])
svc.set_overtime_policy(boss, {"max_weekly_ot_minutes": 200})
check("a_weekly_limit_holds_once_set", refused("ot.period_cap", lambda: save(officer, "overtime_request", "OT-7", {"employee_id": e1["id"], "work_date": "2026-10-15", "planned_minutes": 100, "kind": "day", "reason": "customer order"})))

# ================================================================== 7. headcount from crew requirements, and rights
rows = [{"line_code": "FA-1", "shift_code": s, "work_date": f"2026-11-{d:02d}", "headcount": 10} for d in (2, 3) for s in ("A", "B")]
prop = people_ops.headcount_from_crew(rows, 800)
check("headcount_is_proposed_with_a_relief_allowance", prop == [{"work_center_code": "FA-1", "period": "2026-11", "planned_fte": 22, "average_required": 20.0, "days": 2}], prop)
svc.create_user(admin, "watcher", "Watcher", "Admin-2026!x", "viewer")
watcher = sign_in("watcher")
check("a_viewer_sees_recruitment_but_changes_nothing", svc.onboarding_status(watcher, "E000003")["employee"] == "E000003" and refused("perm.denied", lambda: svc.hire(watcher, "CAN-0001", {})) and refused("perm.denied", lambda: save(watcher, "candidate", "CAN-0100", {"display_name": "X"})))
check("the_hr_officer_cannot_approve_requisitions_overtime_or_leave", not any(p in svc.auth.permissions(officer) for p in ("hr.recruitment.approve", "hr.overtime.approve", "hr.leave.approve")))

# the company's overtime policy is in every backup, and comes back from one on a fresh data folder
import sqlite3  # noqa: E402
made = svc.backups.create("admin", "manual")
with sqlite3.connect(os.path.join(made["path"], "settings.db")) as policy_db:
    saved = policy_db.execute("SELECT value FROM setting WHERE key = 'overtime_policy'").fetchone()
check("the_overtime_policy_is_in_the_backup", saved is not None and json.loads(saved[0])["max_weekly_ot_minutes"] == 200, saved)
fresh = os.path.join(TMP, "fresh")
os.makedirs(fresh)
import shutil  # noqa: E402
shutil.copy(os.path.join(made["path"], "settings.db"), os.path.join(fresh, "settings.db"))
from hr_core.people_service import SettingsStore  # noqa: E402
check("a_fresh_folder_gets_the_policy_back_not_the_defaults", SettingsStore(fresh).get("overtime_policy")["max_weekly_ot_minutes"] == 200)

# Legacy JSON is imported once; reopening preserves the backed-up database policy.
legacy = os.path.join(TMP, "legacy")
os.makedirs(legacy)
Path(legacy, "overtime_policy.json").write_text(json.dumps({"max_weekly_ot_minutes": 123}), encoding="utf-8")
oldsvc = HRService(legacy, COMPANY)
check("legacy_policy_is_migrated_to_the_settings_attachment", oldsvc._settings.get("overtime_policy")["max_weekly_ot_minutes"] == 123)
oldsvc._settings.put("overtime_policy", {"max_weekly_ot_minutes": 456})
oldsvc._load_policy()
check("legacy_json_does_not_overwrite_a_restored_policy", oldsvc.registry.overtime_policy["max_weekly_ot_minutes"] == 456)
oldsvc.close()

print(json.dumps(results, indent=2))
print("TEST_HR_PEOPLE_OPS: all", len(results), "checks passed")
