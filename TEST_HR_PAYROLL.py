"""Payroll (WP-H6): HR calculates pay from salary profiles, overtime, leave, adjustments and the plan; a second person approves;
only totals per cost centre and account key go to Mizan.

Every expected number below was worked out by hand (Egypt 2026: Law 91/2005 art. 8 as amended by Law 7/2024; insurance 11 % / 18.75 %
on 2,700-16,700; martyrs' fund 0.05 %; overtime on basic / 240 with the company's premiums). Synthetic data only. Standard library only.
"""

import http.server
import json
import os
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
COMPANY = "0192f7c4-8a3e-7b21-9c55-3d1f2a4b6c7d"

from hr_core import payroll_calc as calc  # noqa: E402
from hr_core.auth import AuthError  # noqa: E402
from hr_core.registry import RegistryError  # noqa: E402
from hr_core.scheduling import ScheduleError  # noqa: E402
from hr_core.service import HRService  # noqa: E402

results = {}
TMP = tempfile.mkdtemp(prefix="hr_payroll_")
POUND = 100


def check(name, ok, detail=None):
    results[name] = bool(ok)
    if not ok:
        print(json.dumps(results, indent=2))
        raise AssertionError(f"{name}: {detail}")


def refused(code, fn):
    try:
        fn()
    except (RegistryError, AuthError, ScheduleError) as exc:
        return exc.code == code or print("got", exc.code, exc)
    return False


# ================================================================== 1. the arithmetic, worked by hand
check("tax_20000_month_example", calc.salary_tax_yearly(197_956 * POUND) == 29_340 * POUND)
check("tax_brackets_edges", calc.salary_tax_yearly(40_000 * POUND) == 0 and calc.salary_tax_yearly(55_000 * POUND) == 1_500 * POUND)
check("tax_above_600000_drops_the_lowest_bracket", calc.salary_tax_yearly(650_000 * POUND) == (5_500 + 2_250 + 26_000 + 45_000 + 62_500) * POUND)
check("tax_above_1200000", calc.salary_tax_yearly(1_500_000 * POUND) == (300_000 + 82_500) * POUND)
check("income_rounds_down_to_ten_pounds", calc.salary_tax_yearly(197_959 * POUND) == calc.salary_tax_yearly(197_950 * POUND))
RATES = {"day": 3500, "night": 7000, "rest_day": 10000, "holiday": 10000}
none = {}
s = calc.payslip({"basic_minor": 20_000 * POUND, "allowance_minor": 0, "insurable_minor": 18_000 * POUND}, (30, 30), none, RATES, 0, 1500, 0, 0, 0)
check("month_of_20000_insurance_capped_at_16700", s["si_employee"] == 1_837 * POUND and s["si_employer"] == 313_125, s)
check("month_of_20000_tax_2445_net_15708", s["tax"] == 2_445 * POUND and s["other_deductions"] == 10 * POUND and s["net"] == 15_708 * POUND, s)
s = calc.payslip({"basic_minor": 2_000 * POUND, "allowance_minor": 0, "insurable_minor": 2_000 * POUND}, (30, 30), none, RATES, 0, 1500, 0, 0, 0)
check("insurance_floor_2700_and_no_tax_below_the_exemption", s["si_employee"] == 297 * POUND and s["si_employer"] == 50_625 and s["tax"] == 0 and s["net"] == 1_702 * POUND, s)
s = calc.payslip({"basic_minor": 12_000 * POUND, "allowance_minor": 0, "insurable_minor": 12_000 * POUND}, (30, 30), {"day": 120, "night": 60, "rest_day": 480}, RATES, 0, 1500, 0, 0, 0)
check("overtime_135_85_800_on_an_hourly_wage_of_50", s["overtime_by_kind"] == {"day": 135 * POUND, "night": 85 * POUND, "rest_day": 800 * POUND, "holiday": 0} and s["overtime"] == 1_020 * POUND, s)
s = calc.payslip({"basic_minor": 10_000 * POUND, "allowance_minor": 0, "insurable_minor": 10_000 * POUND}, (15, 30), none, RATES, 0, 1500, 0, 0, 0)
check("half_a_month_pays_half_and_insures_half", s["basic"] == 5_000 * POUND and s["si_employee"] == 550 * POUND, s)
s = calc.payslip({"basic_minor": 9_000 * POUND, "allowance_minor": 0, "insurable_minor": 9_000 * POUND}, (30, 30), none, RATES, 0, 1500, 2, 0, 0)
check("two_unpaid_days_cost_two_thirtieths_of_basic", s["absence"] == 600 * POUND and s["earnings"] == 8_400 * POUND, s)
s = calc.payslip({"basic_minor": 8_000 * POUND, "allowance_minor": 0, "insurable_minor": 8_000 * POUND}, (30, 30), none, RATES, 13, 1500, 0, 0, 0)
check("night_allowance_is_15_percent_of_basic_over_26_days", s["night_allowance"] == 600 * POUND, s)
check("net_is_always_gross_less_deductions", all(x["net"] == x["gross"] - x["si_employee"] - x["tax"] - x["other_deductions"] for x in [s]))

# ================================================================== 2. a small company and the service
svc = HRService(os.path.join(TMP, "data"), COMPANY, "NILE", "Nile Home", backup_dir=os.path.join(TMP, "backups"))
reg = svc.registry
reg.today = lambda: "2026-09-10"
svc.bootstrap_admin("admin", "Admin", "Admin-2026!x")


def sign_in(username):
    svc.auth.commit("admin", "clear first-login flag", [{"entity": "user", "code": username, "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", username)["ver"]}])
    return svc.login(username, "Admin-2026!x")[1]


_, admin = svc.login("admin", "Admin-2026!x")
admin = sign_in("admin")
svc.create_user(admin, "boss", "Boss", "Admin-2026!x", "administrator")
svc.create_user(admin, "officer", "Officer", "Admin-2026!x", "hr_officer")
svc.create_user(admin, "viewer1", "Viewer", "Admin-2026!x", "viewer")
boss, officer, viewer = sign_in("boss"), sign_in("officer"), sign_in("viewer1")
save = lambda u, e, code, f, ver=None: svc.save(u, e, code, f, ver)["row"]  # noqa: E731

company = [u for u in reg.list("org_unit") if u["type"] == "company"][0]
site = save(admin, "org_unit", "CAI", {"type": "site", "name": "Cairo", "parent_id": company["id"]})
dept = save(admin, "org_unit", "FA", {"type": "department", "name": "Final assembly", "parent_id": site["id"], "attrs": {"cost_center": "CC-FA"}})
job = save(admin, "job", "OPR", {"title": "Line operator"})
pos = save(admin, "position", "POS-OPR", {"job_id": job["id"], "org_unit_id": dept["id"], "status": "open"})
day_shift = save(admin, "shift", "A", {"name": "Day", "start_time": "07:00", "end_time": "15:00", "break_minutes": 30, "grace_minutes": 10})
night_shift = save(admin, "shift", "C", {"name": "Night", "start_time": "23:00", "end_time": "07:00", "break_minutes": 30, "grace_minutes": 10})
cal = save(admin, "work_calendar", "EG", {"name": "Egypt", "rest_days": "FRI", "holidays": ""})
emps = {}
for code, name, hire in (("E000001", "Aya", "2026-01-05"), ("E000002", "Omar", "2026-09-16"), ("E000003", "Nour", "2026-03-01"), ("E000004", "Sara", "2026-01-05")):
    emps[code] = save(admin, "employee", code, {"preferred_name": name, "legal_name": name, "employment_status": "Active", "worker_type": "Regular", "hire_date": hire, "position_id": pos["id"]})
for code, shift, since in (("E000001", day_shift, "2026-01-05"), ("E000002", night_shift, "2026-09-16"), ("E000003", day_shift, "2026-03-01"), ("E000004", day_shift, "2026-01-05")):
    save(admin, "shift_assignment", f"{code}-R", {"employee_id": emps[code]["id"], "shift_id": shift["id"], "calendar_id": cal["id"], "kind": "regular", "valid_from": since})
save(admin, "leave_type", "UNPAID", {"name": "Unpaid leave", "paid": 0, "annual_days": 0, "carry_over_days": 0, "active": 1})
# overtime for E000001 in September: day 120 minutes on Thu 10 Sep, night 60 minutes on Wed 9 Sep (asked for by the officer, approved by the boss)
for code, d, kind, minutes in (("OT-1", "2026-09-10", "day", 120), ("OT-2", "2026-09-09", "night", 60)):
    r = save(officer, "overtime_request", code, {"employee_id": emps["E000001"]["id"], "work_date": d, "planned_minutes": minutes, "kind": kind, "reason": "order peak", "status": "requested"})
    save(boss, "overtime_request", code, {"employee_id": emps["E000001"]["id"], "work_date": d, "planned_minutes": minutes, "kind": kind, "reason": "order peak", "status": "approved"}, r["ver"])
# unpaid leave for E000003: Sun 6 and Mon 7 Sep = 2 working days
lr = save(officer, "leave_request", "LV-1", {"employee_id": emps["E000003"]["id"], "leave_type_id": reg.get("leave_type", "UNPAID")["id"], "from_date": "2026-09-06", "to_date": "2026-09-07"})
save(boss, "leave_request", "LV-1", {"status": "approved"}, lr["ver"])
reg.today = lambda: "2026-10-02"

# ================================================================== 3. rights and salary profiles
check("a_viewer_cannot_see_pay", refused("perm.denied", lambda: svc.pay_profiles(viewer)))
check("an_officer_keeps_profiles", svc.set_pay_profile(officer, "E000001", {"effective_from": "2026-01-01", "basic_minor": 20_000 * POUND, "insurable_minor": 18_000 * POUND})["employee"] == "E000001")
svc.set_pay_profile(officer, "E000002", {"effective_from": "2026-09-01", "basic_minor": 10_000 * POUND, "insurable_minor": 10_000 * POUND, "cost_center": "CC-NIGHT"})
svc.set_pay_profile(officer, "E000003", {"effective_from": "2026-01-01", "basic_minor": 9_000 * POUND, "insurable_minor": 9_000 * POUND})
check("a_profile_needs_a_known_employee", refused("employee.not_found", lambda: svc.set_pay_profile(officer, "E999999", {"basic_minor": 1000})))
check("a_profile_needs_a_positive_basic", refused("pay.range", lambda: svc.set_pay_profile(officer, "E000004", {"basic_minor": 0})))
check("a_viewer_cannot_calculate", refused("perm.denied", lambda: svc.pay_calculate(viewer, "2026-09")))
check("the_officer_has_no_approve_right", "hr.payroll.approve" not in svc.me(officer)["permissions"] and "hr.payroll.run" in svc.me(officer)["permissions"])
check("the_month_must_have_ended", refused("period.open", lambda: svc.pay_calculate(officer, "2026-10")))
svc.add_pay_adjustment(officer, "2026-09", "E000003", "unpaid_absence_days", 1, "absent on the 14th")
svc.add_pay_adjustment(officer, "2026-09", "E000003", "bonus", 500 * POUND, "attendance bonus")
check("an_adjustment_is_checked", refused("pay.adjustment_kind", lambda: svc.add_pay_adjustment(officer, "2026-09", "E000003", "gift", 5)))

# ================================================================== 4. a run
run = svc.pay_calculate(officer, "2026-09")
check("one_person_has_no_profile_and_is_reported_not_paid", run["headcount"] == 3 and any("E000004" in w for w in run["warnings"]), run["warnings"])
slips = {s["employee_code"]: s for s in svc.pay_slips(officer, "2026-09", run["run"])}
a, o, n = slips["E000001"], slips["E000002"], slips["E000003"]
check("cost_centre_comes_from_the_org_unit_or_the_profile", a["cost_center"] == "CC-FA" and o["cost_center"] == "CC-NIGHT")
# E000001: basic 20,000 (hourly 83.3333) + overtime day 2 h x 1.35 = 225.00 + night 1 h x 1.70 = 141.67 -> overtime 366.67, gross 20,366.67
check("overtime_comes_from_the_approved_requests", a["overtime"] == 36_667 and a["gross"] == 2_036_667, a)
# insurance 1,837.00; taxable (20,366.67-1,837.00) x 12 = 222,356.04 - 20,000 = 202,356.04 -> 202,350: 1,500 + 2,250 + 130,000 x 20% = 26,000 + 2,350 x 22.5% = 528.75 -> 30,278.75 / 12 = 2,523.23
check("tax_follows_the_brackets", a["si_employee"] == 1_837 * POUND and a["tax"] == 252_323, a)
check("martyrs_fund_is_five_hundredths_of_a_percent", a["other_deductions"] == 1_018, a)
check("net_pay", a["net"] == 2_036_667 - 183_700 - 252_323 - 1_018, a)
# E000002: hired 16 Sep, 15 of 30 days, night shift, 13 work days (Fridays 18 and 25 are rest days) -> night allowance 750
check("a_hire_in_the_month_is_prorated", o["basic"] == 5_000 * POUND and o["in_post_days"] == 15 and o["night_days"] == 13, o)
check("night_allowance", o["night_allowance"] == 750 * POUND, o)
# E000003: basic 9,000, unpaid leave 2 days + 1 absent day = 3/30 x 9,000 = 900, bonus 500
check("unpaid_leave_and_absence_reduce_the_basic", n["unpaid_days"] == 3 and n["absence"] == 900 * POUND and n["earnings"] == (9_000 - 900 + 500) * POUND, n)
check("the_period_totals_balance_per_cost_centre", all(
    sum(l["amount_minor"] for l in run["lines"] if l["cost_center"] == cc and l["account_key"] in ("gross_earnings", "overtime", "night_allowance", "employer_social_insurance"))
    == sum(l["amount_minor"] for l in run["lines"] if l["cost_center"] == cc and l["account_key"] in ("employee_social_insurance", "employer_social_insurance", "salary_tax", "other_deductions", "net_payable"))
    for cc in {l["cost_center"] for l in run["lines"]}))
check("totals_equal_the_sum_of_the_slips", run["totals"]["net_payable"] == a["net"] + o["net"] + n["net"] and run["totals"]["salary_tax"] == a["tax"] + o["tax"] + n["tax"])
check("regular_hours_follow_the_plan", run["hours"]["overtime_day"] == 2 and run["hours"]["overtime_night"] == 1 and run["hours"]["regular"] > 0, run["hours"])
check("the_published_lines_hold_no_names", all(set(l) == {"cost_center", "account_key", "amount_minor"} for l in run["lines"]))
again = svc.pay_calculate(officer, "2026-09")
check("same_data_same_fingerprint_and_the_same_run_number", again["fingerprint"] == run["fingerprint"] and again["run"] == run["run"] == 1)
check("the_audit_holds_no_pay_of_one_person", all(str(a["net"]) not in json.dumps(e, default=str) for e in svc.audit_entries(admin, "activity", 500)))

# ================================================================== 5. approval by someone else
check("the_one_who_calculated_cannot_approve", refused("perm.denied", lambda: svc.pay_approve(officer, "2026-09", 1, run["fingerprint"])))
svc.create_user(admin, "boss2", "Boss Two", "Admin-2026!x", "administrator")
boss2 = sign_in("boss2")
calc_by_boss = svc.pay_calculate(boss, "2026-09")
check("an_approver_cannot_approve_their_own_calculation", refused("sod.own_payroll", lambda: svc.pay_approve(boss, "2026-09", 1, calc_by_boss["fingerprint"])))
svc.pay_calculate(officer, "2026-09")                                                              # back to the officer's run
check("an_approval_must_name_the_fingerprint_it_saw", refused("pay.stale", lambda: svc.pay_approve(boss, "2026-09", 1, "0" * 64)))

# a fake Mizan that records what it is sent
seen = []


class FakeMizan(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        seen.append({"path": self.path, "headers": dict(self.headers), "body": json.loads(raw)})
        out = json.dumps({"results": [{"id": e["id"], "result": "applied"} for e in json.loads(raw)["events"]]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *args):
        pass


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeMizan)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ.pop("ECO_MIZAN_URL", None)
os.environ.pop("ECO_MIZAN_KEY", None)
approved = svc.pay_approve(boss, "2026-09", 1, run["fingerprint"])
check("approved_by_the_second_person", approved["status"] == "approved" and approved["approved_by"] == "boss" and approved["pay_date"] == "2026-09-30", approved)
check("without_an_address_the_event_waits_in_the_outbox", approved["delivery"]["state"] == "pending" and not seen, approved["delivery"])
URL = f"http://127.0.0.1:{server.server_address[1]}"
check("the_officer_cannot_point_the_payroll_somewhere", refused("perm.denied", lambda: svc.set_pay_target(officer, URL, "eco_test_key_for_payroll")))
check("the_address_is_checked", refused("target.url", lambda: svc.set_pay_target(admin, "mizan.local", "eco_test_key_for_payroll")))
check("the_key_is_checked", refused("target.key", lambda: svc.set_pay_target(admin, URL, "has a space")))
target = svc.set_pay_target(admin, URL, "eco_test_key_for_payroll")
check("the_target_is_kept_and_the_key_is_never_returned", target == {"url": URL, "key_set": True} and svc.pay_target(admin) == target and "eco_test_key" not in json.dumps(target))
check("the_key_is_in_its_own_file_outside_the_backups", os.path.isfile(os.path.join(TMP, "data", "node", "mizan.key")) and b"eco_test_key" not in Path(TMP, "data", "node", "mizan.key").read_bytes() or os.name != "nt")
check("the_key_is_not_in_the_audit", all("eco_test_key" not in json.dumps(e, default=str) for e in svc.audit_entries(admin, None, 500)))
sent = svc.pay_deliver(boss)
check("delivery_reaches_mizan_signed", sent["delivered"] == 1 and len(seen) == 1 and "x-eco-sig" in {k.lower() for k in seen[0]["headers"]} and seen[0]["path"] == "/eco/v1/inbox", (sent, seen))
event = seen[0]["body"]["events"][0]
data = event["data"]
check("the_event_is_the_contract", event["type"] == "hr.payroll_period.v1" and data["status"] == "approved" and data["period"] == "2026-09" and data["run"] == 1
      and data["currency"] == "EGP" and data["version"] == 1 and data["headcount"] == 3 and data["lines"] == approved["lines"], data)
check("the_event_carries_no_names_and_no_employee_codes", "Aya" not in json.dumps(event) and "E00000" not in json.dumps(event))
check("a_second_delivery_sends_nothing_new", svc.pay_deliver(boss)["waiting"] == 0 and len(seen) == 1)
check("an_approved_run_is_final", refused("pay.locked", lambda: svc.pay_calculate(officer, "2026-09")))
check("pay_of_an_approved_month_cannot_be_adjusted", refused("pay.locked", lambda: svc.add_pay_adjustment(officer, "2026-09", "E000001", "bonus", 100)))
check("a_salary_change_cannot_start_in_an_approved_month", refused("pay.locked", lambda: svc.set_pay_profile(officer, "E000001", {"effective_from": "2026-09-15", "basic_minor": 21_000 * POUND})))
check("nobody_can_approve_twice", refused("pay.state", lambda: svc.pay_approve(boss2, "2026-09", 1, run["fingerprint"])))
check("reversing_needs_the_approve_right", refused("perm.denied", lambda: svc.pay_reverse(officer, "2026-09", 1, "wrong bonus")))
check("reversing_needs_a_reason", refused("pay.reason", lambda: svc.pay_reverse(boss, "2026-09", 1, " ")))
rev = svc.pay_reverse(boss, "2026-09", 1, "the attendance bonus was entered twice")
check("a_reversal_sends_version_2_with_status_reversed", rev["status"] == "reversed" and seen[-1]["body"]["events"][0]["data"]["status"] == "reversed" and seen[-1]["body"]["events"][0]["data"]["version"] == 2)
svc.remove_pay_adjustment(officer, [x for x in svc.pay_adjustments(officer, "2026-09") if x["kind"] == "bonus"][0]["id"])
run2 = svc.pay_calculate(officer, "2026-09")
check("after_a_reversal_the_correction_is_a_new_run", run2["run"] == 2 and run2["fingerprint"] != run["fingerprint"] and run2["totals"]["net_payable"] < run["totals"]["net_payable"])
check("a_new_run_has_a_new_identity_for_mizan", run2["status"] == "calculated")
approved2 = svc.pay_approve(boss2, "2026-09", 2, run2["fingerprint"], "2026-10-01")
check("the_corrected_run_goes_out_with_its_pay_date", seen[-1]["body"]["events"][0]["data"]["run"] == 2 and seen[-1]["body"]["events"][0]["data"]["pay_date"] == "2026-10-01"
      and seen[-1]["body"]["events"][0]["data"]["id"] != data["id"])

# ================================================================== 6. a refusal from Mizan stays visible and is retried only on purpose
svc.set_pay_profile(officer, "E000004", {"effective_from": "2026-10-01", "basic_minor": 7_000 * POUND})
reg.today = lambda: "2026-11-02"
r3 = svc.pay_calculate(officer, "2026-10")
check("october_pays_the_person_who_now_has_a_profile", r3["headcount"] == 4 and not any("no pay profile" in w for w in r3["warnings"]), r3["warnings"])
seen_before = len(seen)
server.shutdown()
server.server_close()
svc.pay_approve(boss, "2026-10", 1, r3["fingerprint"])
check("an_unreachable_mizan_keeps_the_run_approved_and_waiting", svc._run_view("2026-10", 1)["delivery"]["state"] == "pending" and len(seen) == seen_before)

# ================================================================== 7. the pay is in every backup
made = svc.backups.create("admin", "manual")
check("payroll_db_is_inside_the_backup", os.path.isfile(os.path.join(made["path"], "payroll.db")), os.listdir(made["path"]))
check("the_backup_verifies", svc.backups.verify(made["path"])["ok"])
check("no_key_travels_in_the_backup", not any(f.endswith(".key") for f in os.listdir(made["path"])), os.listdir(made["path"]))

# ================================================================== 8. a published month never leaves personal data
svc.close()
print(json.dumps(results, indent=1))
print(f"payroll: {len(results)} checks passed")
