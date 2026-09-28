"""Discipline (phase 6): the penalty schedule, violations proposed from attendance, decisions - acceptance tests.

Proves: the schedule's penalty follows the number of repeats inside its window; proposals come only from worked days
(never a leave day, a rest day or a holiday) and running them twice proposes nothing twice; proposing and deciding are
different rights and who decided and when come from the server; the month cap, the single-violation cap, the 30-day
limit and the written investigation are enforced; a decision is final (never changed or deleted); penalties are
written as days, never as money; the permanent history rebuilds the same records; a backup with them rehearses.
Synthetic data only. Standard library only.
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"

from hr_core import discipline  # noqa: E402
from hr_core.auth import PERMISSIONS, AuthError  # noqa: E402
from hr_core.registry import ENTITIES, RegistryError  # noqa: E402
from hr_core.service import HRService  # noqa: E402

results = {}
TMP = tempfile.mkdtemp(prefix="hr_discipline_")


def check(name, ok, detail=None):
    results[name] = bool(ok)
    if not ok:
        print(json.dumps(results, indent=2))
        raise AssertionError(f"{name}: {detail}")


def refused(code, fn):
    try:
        fn()
    except (RegistryError, AuthError) as exc:
        return exc.code == code or print("got", exc.code, exc)
    return False


svc = HRService(os.path.join(TMP, "data"), COMPANY, "NILE", "Nile Home", backup_dir=os.path.join(TMP, "backups"))
reg = svc.registry
TODAY = "2026-10-20"
reg.today = lambda: TODAY
svc.bootstrap_admin("admin", "Admin", "Admin-2026!x")
svc.auth.commit("admin", "clear first-login flag", [{"entity": "user", "code": "admin", "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", "admin")["ver"]}])
_, admin = svc.login("admin", "Admin-2026!x")
save = lambda e, code, f, ver=None, who=None: svc.save(who or admin, e, code, f, ver)["row"]  # noqa: E731

# people and a plan: E1 and E2 work the day shift, Friday rest
company = [u for u in reg.list("org_unit") if u["type"] == "company"][0]
e1 = save("employee", "E1", {"preferred_name": "Aya", "employment_status": "Active", "legacy_number": "501"})
e2 = save("employee", "E2", {"preferred_name": "Omar", "employment_status": "Active"})
day = save("shift", "D", {"name": "Day", "start_time": "07:00", "end_time": "15:00", "break_minutes": 30})
cal = save("work_calendar", "FAC", {"name": "Factory", "rest_days": "FRI", "holidays": "2026-10-06"})
for e in (e1, e2):
    save("shift_assignment", f"{e['code']}-2026-09-01-R", {"employee_id": e["id"], "shift_id": day["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-09-01"})

# ================================================================== 1. the penalty schedule
late = save("penalty_rule", "LATE", {"name": "Late arrival", "violation": "late", "threshold_minutes": 15, "window_days": 30,
                                     "steps": "warning,deduct:0.25,deduct:0.5,deduct:1", "active": 1})
absent = save("penalty_rule", "ABS", {"name": "Absence without leave", "violation": "absence", "window_days": 365, "steps": "deduct:1,deduct:2,deduct:3,investigation", "active": 1})
check("a_rule_needs_a_known_violation", refused("rule.violation", lambda: save("penalty_rule", "X", {"name": "X", "violation": "sleeping", "steps": "warning"})))
check("a_rule_needs_valid_penalties", refused("penalty.kind", lambda: save("penalty_rule", "X", {"name": "X", "violation": "late", "steps": "fine:100"})))
check("a_deduction_is_at_most_five_days_in_quarters", refused("penalty.deduction", lambda: save("penalty_rule", "X", {"name": "X", "violation": "late", "steps": "deduct:6"}))
      and refused("penalty.deduction", lambda: save("penalty_rule", "X", {"name": "X", "violation": "late", "steps": "deduct:0.3"})))
check("the_last_step_repeats", discipline.proposed_for(late, 1) == "warning" and discipline.proposed_for(late, 4) == "deduct:1" and discipline.proposed_for(late, 9) == "deduct:1")

# ================================================================== 2. proposals from attendance
att = [{"employee_id": "E1", "work_date": "2026-10-01", "attendance_status": "Present", "late_minutes": 22},
       {"employee_id": "501", "work_date": "2026-10-03", "attendance_status": "Present", "late_minutes": 40},       # E1 by old number
       {"employee_id": "E1", "work_date": "2026-10-04", "attendance_status": "Present", "late_minutes": 9},        # under the threshold
       {"employee_id": "E1", "work_date": "2026-10-05", "attendance_status": "Absent"},
       {"employee_id": "E1", "work_date": "2026-10-06", "attendance_status": "Absent"},                          # a holiday
       {"employee_id": "E1", "work_date": "2026-10-09", "attendance_status": "Absent"},                          # Friday: rest
       {"employee_id": "E2", "work_date": "2026-10-05", "attendance_status": "Annual Leave"},                     # on leave
       {"employee_id": "E2", "work_date": "2026-10-07", "attendance_status": "Present", "late_minutes": 31}]
out = svc.propose_violations(admin, "2026-10-01", "2026-10-09", att)
codes = set(out["proposed"])
check("late_and_absence_are_proposed", {"E1-2026-10-01-LATE", "E1-2026-10-03-LATE", "E1-2026-10-05-ABS", "E2-2026-10-07-LATE"} <= codes)
check("under_the_threshold_nothing_is_proposed", "E1-2026-10-04-LATE" not in codes)
check("a_holiday_a_rest_day_and_a_leave_day_are_never_violations", not codes & {"E1-2026-10-06-ABS", "E1-2026-10-09-ABS", "E2-2026-10-05-ABS"})
v1, v2 = reg.get("violation", "E1-2026-10-01-LATE"), reg.get("violation", "E1-2026-10-03-LATE")
check("the_second_time_gets_the_second_step", v1["proposed"] == "warning" and v2["proposed"] == "deduct:0.25" and v2["occurrence"] == 2)
check("proposing_again_proposes_nothing_twice", svc.propose_violations(admin, "2026-10-01", "2026-10-09", att)["proposed"] == [])
check("a_violation_is_coded_by_person_day_and_rule", refused("violation.code", lambda: save("violation", "ANY",
      {"employee_id": e2["id"], "rule_id": late["id"], "work_date": "2026-10-08", "status": "proposed"})))
check("a_violation_cannot_be_in_the_future", refused("violation.future", lambda: save("violation", "E2-2026-11-02-LATE",
      {"employee_id": e2["id"], "rule_id": late["id"], "work_date": "2026-11-02", "status": "proposed"})))

# ================================================================== 3. rights: proposing is not deciding
svc.save_profile(admin, "line_manager", "Line manager", ["hr.employees.read", "hr.shifts.read", "hr.attendance.read", "hr.discipline.read", "hr.discipline.approve"])
for u, p in (("officer", "hr_officer"), ("manager", "line_manager")):
    svc.create_user(admin, u, u.title(), "Pass-2026!xx", p)
    svc.auth.commit("admin", "clear flag", [{"entity": "user", "code": u, "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", u)["ver"]}])
_, officer = svc.login("officer", "Pass-2026!xx")
_, manager = svc.login("manager", "Pass-2026!xx")
check("the_hr_officer_proposes_but_cannot_decide", "hr.discipline.write" in svc.me(officer)["permissions"]
      and refused("perm.denied", lambda: save("violation", v1["code"], {"status": "approved", "decision": "warning"}, v1["ver"], officer)))
check("the_manager_decides_but_cannot_propose", refused("perm.denied", lambda: svc.propose_violations(manager, "2026-10-01", "2026-10-09", att)))
d1 = save("violation", v1["code"], {"status": "approved", "decision": "warning", "decided_by": "someone-else", "decided_on": "2020-01-01"}, v1["ver"], manager)
check("who_decided_and_when_come_from_the_server", d1["decided_by"] == "manager" and d1["decided_on"] == TODAY)
check("a_decision_is_final", refused("violation.decided", lambda: save("violation", d1["code"], {"status": "waived", "note": "changed my mind"}, d1["ver"], manager)))
check("a_decided_violation_is_never_deleted", refused("violation.decided", lambda: svc.delete(admin, "violation", d1["code"], d1["ver"])))
check("a_proposal_cannot_carry_a_decision", reg.get("violation", "E1-2026-10-05-ABS")["decision"] is None)

# ================================================================== 4. the law's limits
abs1 = reg.get("violation", "E1-2026-10-05-ABS")
check("more_than_one_day_needs_the_written_investigation", refused("penalty.investigation", lambda: save("violation", abs1["code"],
      {"status": "approved", "decision": "deduct:2"}, abs1["ver"], manager)))
a = save("violation", abs1["code"], {"status": "approved", "decision": "deduct:2", "note": "Investigation 2026-10-12: no excuse given"}, abs1["ver"], manager)
more = save("violation", "E1-2026-10-07-ABS", {"employee_id": e1["id"], "rule_id": absent["id"], "work_date": "2026-10-07", "status": "proposed", "source": "manual"}, None, officer)
check("the_month_cap_of_five_days_holds", refused("penalty.month_cap", lambda: save("violation", more["code"],
      {"status": "approved", "decision": "deduct:3.25", "note": "Investigation: second absence"}, more["ver"], manager)))
ok = save("violation", more["code"], {"status": "approved", "decision": "deduct:3", "note": "Investigation: second absence"}, more["ver"], manager)
check("up_to_the_cap_is_accepted", ok["status"] == "approved")
w = reg.get("violation", "E2-2026-10-07-LATE")
check("a_waiver_needs_its_reason", refused("penalty.reason", lambda: save("violation", w["code"], {"status": "waived"}, w["ver"], manager)))
reg.today = lambda: "2026-11-25"   # found on 2026-10-20: 36 days later
check("no_penalty_after_thirty_days", refused("penalty.too_late", lambda: save("violation", w["code"], {"status": "approved", "decision": "warning"}, w["ver"], manager)))
w = save("violation", w["code"], {"status": "waived", "note": "Bus breakdown, confirmed by transport"}, w["ver"], manager)
check("after_thirty_days_it_can_still_be_waived", w["status"] == "waived")
reg.today = lambda: TODAY
check("penalties_are_days_never_money", set(ENTITIES["violation"]).isdisjoint({"amount", "money", "wage", "salary"})
      and all(k in PERMISSIONS for k in ("hr.discipline.read", "hr.discipline.write", "hr.discipline.approve")))

# ================================================================== 5. history, rebuild, backups
fp = reg.fingerprint()
reg.rebuild()
check("the_records_rebuild_identically_from_the_permanent_history", reg.fingerprint() == fp and svc.journal.verify()["ok"])
made = svc.backups.create("admin", "manual")
check("a_backup_with_the_penalty_schedule_rehearses", svc.backups.rehearse(made["path"], "admin")["ok"])

svc.close()
shutil.rmtree(TMP, ignore_errors=True)
print(json.dumps(results, indent=2))
print(f"TEST_HR_DISCIPLINE: {len(results)} checks passed")
