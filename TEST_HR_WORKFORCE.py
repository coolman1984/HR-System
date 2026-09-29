"""Shifts and schedules (phase 3) and skills (phase 5) — acceptance tests.

Proves the exit gates that can be proven inside HR: a schedule exists before attendance and attendance is compared
with it; an overnight shift has exactly one work date; an employee cannot hold overlapping assignments; changing next
month never rewrites last month; a swap is both day changes or neither; a skill's validity gives a qualification its
expiry; rights are checked; the permanent history and a rebuild give the same records; old backups still rehearse.
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

from hr_core import scheduling, skills  # noqa: E402
from hr_core.auth import AuthError  # noqa: E402
from hr_core.registry import RegistryError  # noqa: E402
from hr_core.service import HRService  # noqa: E402

results = {}
TMP = tempfile.mkdtemp(prefix="hr_workforce_")


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
TODAY = "2026-10-10"
reg.today = lambda: TODAY
svc.bootstrap_admin("admin", "Admin", "Admin-2026!x")
_, admin = svc.login("admin", "Admin-2026!x")
svc.auth.commit("admin", "clear first-login flag", [{"entity": "user", "code": "admin", "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", "admin")["ver"]}])
_, admin = svc.login("admin", "Admin-2026!x")

# organisation and people
company = [u for u in reg.list("org_unit") if u["type"] == "company"][0]
save = lambda e, code, f, ver=None: svc.save(admin, e, code, f, ver)["row"]  # noqa: E731
site = save("org_unit", "CAI", {"type": "site", "name": "Cairo", "parent_id": company["id"]})
e1 = save("employee", "E1", {"preferred_name": "Aya", "employment_status": "Active", "legacy_number": "501"})
e2 = save("employee", "E2", {"preferred_name": "Omar", "employment_status": "Active"})
e3 = save("employee", "E3", {"preferred_name": "Nour", "employment_status": "Active"})

# ================================================================== 1. shifts and calendars
day = save("shift", "DAY", {"name": "Day", "start_time": "07:00", "end_time": "15:00", "break_minutes": 30, "grace_minutes": 10})
night = save("shift", "NIGHT", {"name": "Night", "start_time": "22:00", "end_time": "06:00", "break_minutes": 30, "grace_minutes": 10})
check("a_shift_needs_valid_times", refused("shift.time", lambda: save("shift", "BAD", {"name": "Bad", "start_time": "7:00", "end_time": "15:00"})))
check("a_break_longer_than_the_shift_is_refused", refused("number.range", lambda: save("shift", "BAD", {"name": "Bad", "start_time": "07:00", "end_time": "08:00", "break_minutes": 90})))
cal = save("work_calendar", "EG", {"name": "Egypt", "rest_days": "FRI", "holidays": "2026-10-06,2026-10-20"})
check("rest_days_are_checked", refused("calendar.rest_days", lambda: save("work_calendar", "X", {"name": "X", "rest_days": "FRIDAY"})))
check("holidays_are_checked", refused("calendar.holidays", lambda: save("work_calendar", "X", {"name": "X", "rest_days": "", "holidays": "2026-10-20,2026-10-06"})))

# ================================================================== 2. assignments: effective dated, no overlap
a1 = save("shift_assignment", "E1-2026-10-01-R", {"employee_id": e1["id"], "shift_id": day["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-01"})
check("overlapping_regular_assignments_are_refused", refused("assignment.overlap", lambda: save("shift_assignment", "E1-2026-11-01-R",
      {"employee_id": e1["id"], "shift_id": night["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-11-01"})))
check("a_temporary_assignment_needs_an_end", refused("assignment.temporary_end", lambda: save("shift_assignment", "E1-T",
      {"employee_id": e1["id"], "shift_id": night["id"], "calendar_id": cal["id"], "kind": "temporary", "valid_from": "2026-10-12"})))
check("a_started_assignment_keeps_its_shift", refused("assignment.started", lambda: save("shift_assignment", a1["code"], {"shift_id": night["id"]}, a1["ver"])))
check("a_started_assignment_cannot_end_in_the_past", refused("assignment.past", lambda: save("shift_assignment", a1["code"], {"valid_to": "2026-10-05"}, a1["ver"])))
check("a_started_assignment_cannot_be_deleted", refused("assignment.started", lambda: svc.delete(admin, "shift_assignment", a1["code"], a1["ver"])))
before = json.dumps(svc.schedule(admin, "2026-10-01", "2026-10-09", "E1"), sort_keys=True)
a1 = save("shift_assignment", a1["code"], {"valid_to": "2026-10-31"}, a1["ver"])  # next month: nights
save("shift_assignment", "E1-2026-11-01-R", {"employee_id": e1["id"], "shift_id": night["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-11-01"})
after = json.dumps(svc.schedule(admin, "2026-10-01", "2026-10-09", "E1"), sort_keys=True)
check("changing_next_month_never_rewrites_last_month", before == after)
check("the_shift_of_a_started_assignment_keeps_its_times", refused("shift.in_use", lambda: save("shift", "DAY", {"start_time": "08:00"}, day["ver"])))
check("a_calendar_in_use_keeps_its_rest_days", refused("calendar.in_use", lambda: save("work_calendar", "EG", {"rest_days": "FRI,SAT"}, cal["ver"])))
check("a_calendar_in_use_keeps_its_past_holidays", refused("calendar.past_holidays", lambda: save("work_calendar", "EG", {"holidays": "2026-10-20"}, cal["ver"])))
cal = save("work_calendar", "EG", {"holidays": "2026-10-06,2026-10-20,2026-12-25"}, cal["ver"])
check("future_holidays_can_be_added", "2026-12-25" in cal["holidays"])

# ================================================================== 3. resolving days
plan = svc.schedule(admin, "2026-10-01", "2026-11-02", "E1")
by = {d["work_date"]: d for d in plan}
check("a_working_day_follows_the_shift", by["2026-10-01"]["status"] == "work" and by["2026-10-01"]["shift_code"] == "DAY" and by["2026-10-01"]["paid_minutes"] == 450)
check("a_rest_day_follows_the_calendar", by["2026-10-02"]["status"] == "rest")  # a Friday
check("a_holiday_follows_the_calendar", by["2026-10-06"]["status"] == "holiday")
night_day = by["2026-11-01"]
check("an_overnight_shift_has_exactly_one_work_date", night_day["status"] == "work" and night_day["overnight"] and night_day["start"] == "2026-11-01T22:00"
      and night_day["end"] == "2026-11-02T06:00" and sum(1 for d in plan if d["start"] == "2026-11-01T22:00") == 1)
check("nobody_is_scheduled_without_an_assignment", svc.schedule(admin, "2026-10-12", "2026-10-12", "E3")[0]["status"] == "unscheduled")
save("shift_assignment", "E1-2026-10-12-T", {"employee_id": e1["id"], "shift_id": night["id"], "calendar_id": cal["id"], "kind": "temporary",
                                              "valid_from": "2026-10-12", "valid_to": "2026-10-13", "note": "cover"})
t = {d["work_date"]: d for d in svc.schedule(admin, "2026-10-11", "2026-10-14", "E1")}
check("a_temporary_assignment_covers_the_regular_one_for_its_dates", t["2026-10-12"]["shift_code"] == "NIGHT" and t["2026-10-12"]["source"] == "temporary"
      and t["2026-10-14"]["shift_code"] == "DAY")

# ================================================================== 4. day changes and swaps
check("a_day_change_needs_its_code", refused("override.code", lambda: save("roster_override", "X", {"employee_id": e1["id"], "work_date": "2026-10-15", "shift_id": None, "reason": "x"})))
check("a_day_change_in_the_past_is_refused", refused("override.past", lambda: save("roster_override", "E1-2026-10-05", {"employee_id": e1["id"], "work_date": "2026-10-05", "shift_id": None, "reason": "sick"})))
check("a_day_change_needs_a_reason", refused("override.reason", lambda: save("roster_override", "E1-2026-10-15", {"employee_id": e1["id"], "work_date": "2026-10-15", "shift_id": None, "reason": " "})))
save("roster_override", "E1-2026-10-15", {"employee_id": e1["id"], "work_date": "2026-10-15", "shift_id": None, "reason": "family day"})
check("a_day_change_makes_a_day_off", svc.schedule(admin, "2026-10-15", "2026-10-15", "E1")[0]["status"] == "rest")
save("shift_assignment", "E2-2026-10-01-R", {"employee_id": e2["id"], "shift_id": night["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": "2026-10-01"})
lines = svc.journal.last_seq()
svc.swap(admin, "2026-10-14", "E1", "E2", "doctor visit")
d1, d2 = (svc.schedule(admin, "2026-10-14", "2026-10-14", c)[0] for c in ("E1", "E2"))
check("a_swap_exchanges_the_two_shifts", d1["shift_code"] == "NIGHT" and d2["shift_code"] == "DAY" and d1["source"] == "override")
check("a_swap_is_one_saved_change", svc.journal.last_seq() == lines + 1)
check("a_swap_between_two_free_people_is_refused", refused("swap.nothing", lambda: svc.swap(admin, "2026-10-16", "E2", "E3", "x")))  # E2 rests (Friday), E3 unplanned
check("a_swap_with_oneself_is_refused", refused("swap.people", lambda: svc.swap(admin, "2026-10-16", "E3", "E3", "x")))

# ================================================================== 5. planned against attended
attendance = [{"employee_id": "501", "work_date": "2026-10-01", "attendance_status": "Present", "worked_minutes": 455},   # E1 by old number
              {"employee_id": "E1", "work_date": "2026-10-03", "attendance_status": "Absent"},
              {"employee_id": "E1", "work_date": "2026-10-02", "attendance_status": "Present"},                        # Friday: a rest day
              {"employee_id": "Z9", "work_date": "2026-10-01", "attendance_status": "Present"}]
cmp = svc.compare(admin, "2026-10-01", "2026-10-04", attendance)
v = {(d["employee_code"], d["work_date"]): d["verdict"] for d in cmp["days"]}
check("attendance_is_compared_with_the_plan", v[("E1", "2026-10-01")] == "as_planned" and v[("E1", "2026-10-03")] == "absent"
      and v[("E1", "2026-10-02")] == "worked_off_day" and v[("E1", "2026-10-04")] == "no_record" and v[("E3", "2026-10-01")] == "none")
check("an_unknown_attendance_person_is_reported_not_matched", cmp["unknown_attendance_people"] == ["Z9"])

# ================================================================== 6. skills and qualifications
weld = save("skill", "WELD", {"name": "MIG welding", "category": "Production", "validity_months": 12})
check("a_skill_validity_is_checked", refused("number.range", lambda: save("skill", "BAD", {"name": "Bad", "validity_months": 0})))
q = save("employee_skill", "E1-WELD", {"employee_id": e1["id"], "skill_id": weld["id"], "level": 3, "certified_on": "2026-01-31"})
check("a_qualification_expires_after_the_skill_validity", q["expires_on"] == "2027-01-31")
check("a_qualification_is_coded_by_person_and_skill", refused("qualification.code", lambda: save("employee_skill", "WHATEVER",
      {"employee_id": e2["id"], "skill_id": weld["id"], "level": 2, "certified_on": "2026-01-01"})))
check("a_level_is_one_to_four", refused("number.range", lambda: save("employee_skill", "E2-WELD", {"employee_id": e2["id"], "skill_id": weld["id"], "level": 5, "certified_on": "2026-01-01"})))
check("qualification_states", skills.state(q, "2026-10-10") == "valid" and skills.state(q, "2027-01-10") == "expiring"
      and skills.state(q, "2027-02-01") == "expired" and skills.state(q, "2025-12-01") == "not_yet")
check("a_skill_held_by_people_cannot_be_binned", refused("skill.in_use", lambda: svc.delete(admin, "skill", "WELD", weld["ver"])))
q = save("employee_skill", "E1-WELD", {**{k: q[k] for k in ("employee_id", "skill_id", "level", "expires_on")}, "certified_on": "2026-09-30"}, q["ver"])
check("recertifying_moves_an_expiry_that_came_from_the_skill", q["expires_on"] == "2027-09-30")
q = save("employee_skill", "E1-WELD", {"expires_on": "2027-03-31"}, q["ver"])
q = save("employee_skill", "E1-WELD", {"certified_on": "2026-10-01", "expires_on": "2027-03-31"}, q["ver"])
check("a_typed_expiry_is_kept_on_recertification", q["expires_on"] == "2027-03-31")
check("february_ends_where_it_ends", skills.add_months(__import__("datetime").date(2026, 1, 31), 1).isoformat() == "2026-02-28")

# ================================================================== 7. rights, history, rebuild, backups
svc.create_user(admin, "viewer1", "Viewer One", "Viewer-2026!x", "viewer")
svc.auth.commit("admin", "clear flag", [{"entity": "user", "code": "viewer1", "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", "viewer1")["ver"]}])
_, viewer = svc.login("viewer1", "Viewer-2026!x")
check("a_viewer_sees_the_schedule", len(svc.schedule(viewer, "2026-10-01", "2026-10-01")) == 3)
check("a_viewer_cannot_plan", refused("perm.denied", lambda: svc.save(viewer, "shift", "EVE", {"name": "Eve", "start_time": "15:00", "end_time": "23:00"})))
check("a_viewer_cannot_swap", refused("perm.denied", lambda: svc.swap(viewer, "2026-10-20", "E1", "E2", "x")))
check("a_long_range_is_refused", refused("schedule.range", lambda: svc.schedule(admin, "2026-01-01", "2026-12-31")))
fp = reg.fingerprint()
reg.rebuild()
check("the_records_rebuild_identically_from_the_permanent_history", reg.fingerprint() == fp and svc.journal.verify()["ok"])
made = svc.backups.create("admin", "manual")
check("a_backup_with_shifts_and_skills_rehearses", svc.backups.rehearse(made["path"], "admin")["ok"])
empty = HRService(os.path.join(TMP, "empty"), COMPANY, "NILE", "Nile Home", backup_dir=os.path.join(TMP, "b2"))
import hashlib  # noqa: E402
from hr_core.canonical import canonical  # noqa: E402
old = {e: empty.registry.list(e, include_deleted=True) for e in ("org_unit", "job", "position", "employee")}  # what phase 2 fingerprinted
check("empty_new_tables_leave_the_fingerprint_of_older_programs", empty.registry.fingerprint() == hashlib.sha256(canonical(old).encode("utf-8")).hexdigest())
empty.close()

# ================================================================== 8. what leaves HR for manufacturing
import eco_contract  # noqa: E402
import eco_publisher  # noqa: E402
snaps = eco_publisher.registry_plan_and_skills(reg, COMPANY, today=TODAY)
kinds = {k for k, _ in snaps}
check("the_plan_and_qualifications_are_published", kinds == {"eco.schedule_day.v1", "eco.qualification.v1"})
check("every_published_fact_fits_its_contract", all(not eco_contract.validate(k, dict(b, version=1)) for (k, _), b in snaps.items()))
days = [b for (k, _), b in snaps.items() if k == "eco.schedule_day.v1" and b["employee"]["code"] == "E1"]
check("fourteen_days_ahead_are_published", len(days) == eco_publisher.WINDOW_DAYS and min(d["work_date"] for d in days) == TODAY)
check("an_unplanned_employee_is_not_published", not any(b["employee"]["code"] == "E3" for (k, _), b in snaps.items() if k == "eco.schedule_day.v1"))
q = reg.get("employee_skill", "E1-WELD")
svc.delete(admin, "employee_skill", "E1-WELD", q["ver"])
withdrawn = [b for (k, _), b in eco_publisher.registry_plan_and_skills(reg, COMPANY, today=TODAY).items() if k == "eco.qualification.v1"]
check("a_withdrawn_qualification_is_published_as_inactive", withdrawn and withdrawn[0]["active"] is False)
check("no_personal_data_in_the_plan", not any(set(b) - {"id", "employee", "work_date", "status", "shift_code", "start", "end", "paid_minutes", "source", "origin"}
                                                  for (k, _), b in snaps.items() if k == "eco.schedule_day.v1"))
# the installed product's link (hr_core/eco_link.py) reads the registry through its own read-only connection: the same
# facts as the registry itself, and it cannot write
import sqlite3  # noqa: E402
from hr_core.eco_link import ReadOnlyRegistry  # noqa: E402
view = ReadOnlyRegistry(os.path.join(TMP, "data"), COMPANY)
same_facts = eco_publisher.build_snapshots([], COMPANY, view)[0] == eco_publisher.build_snapshots([], COMPANY, reg)[0]
try:
    view.db.execute("CREATE TABLE written_by_the_link (x)")
    writable = True
except sqlite3.OperationalError:
    writable = False
view.close()
check("the_product_link_reads_the_same_facts_and_cannot_write", same_facts and not writable, (same_facts, writable))

svc.close()
shutil.rmtree(TMP, ignore_errors=True)
print(json.dumps(results, indent=2))
print(f"TEST_HR_WORKFORCE: {len(results)} checks passed")
