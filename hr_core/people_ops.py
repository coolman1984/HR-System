"""People operations (plan 30-HR WP-H2 to WP-H5): recruitment and onboarding, overtime, training that grants
qualifications, and leave. New work beside the locked attendance engine.

* Every rule here is a check on a record (`validate`) or a command that changes SEVERAL records in ONE journal line
  (hire, complete a training session, end a contract): all or nothing.
* Who may do what is decided in service.py: proposing and approving are different rights (separation of duties), and the
  person who decides is taken from the session, never from the form.
* Nothing here publishes personal data. A hire publishes the employee exactly as before (`eco.employee.v1`, no personal data).
* Money is not touched: overtime is minutes and premiums in basis points; payroll (WP-H6) is gated and comes later.
Standard library only.
"""

import json
import re
from datetime import date, timedelta

from . import skills
from .scheduling import ScheduleError, Schedule

PERIOD = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

EMPLOYMENT_TYPES = ("regular", "fixed_term", "agency", "intern")
REQ_REASONS = ("crew_gap", "replacement", "growth", "seasonal")
REQ_STATUS = ("draft", "approved", "open", "filled", "cancelled")
REQ_NEXT = {"draft": ("approved", "cancelled"), "approved": ("open", "filled", "cancelled"), "open": ("filled", "cancelled"), "filled": (), "cancelled": ()}
CAND_SOURCES = ("agency", "referral", "walk_in", "online")
CAND_STAGES = ("applied", "screened", "interviewed", "offered", "hired", "rejected", "withdrawn")
ONBOARDING_KINDS = ("medical", "badge", "ppe", "esd_training", "station_training", "contract_signed")
REQUIRED_FOR_LINE = ("medical", "ppe", "esd_training")          # a new hire is not schedulable on a production line before these
OT_KINDS = ("day", "night", "rest_day", "holiday")
OT_STATUS = ("requested", "approved", "rejected")
LEAVE_STATUS = ("requested", "approved", "rejected", "cancelled")

# Overtime policy defaults (research/TV_INDUSTRY_REFERENCE.md section 6). Figures marked "verify" must be confirmed against the
# text of Labour Law 14/2025 and the company's contracts before they are relied upon; they are settings, not code.
DEFAULT_POLICY = {
    "premium_day_bp": 3500, "premium_night_bp": 7000, "rest_day_premium_bp": 10000, "holiday_premium_bp": 10000,
    "night_from": "19:00", "night_to": "07:00", "max_daily_minutes_incl_ot": 600, "max_weekly_ot_minutes": 0, "max_monthly_ot_minutes": 0,
    "night_allowance_bp": 1500, "substitute_day_for_rest_day": True,
    "source_note": "Defaults from the industry reference; verify each figure against Labour Law 14/2025 and the contracts.",
}


def _d(value, what):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ScheduleError("date.format", f"{what} must be a date YYYY-MM-DD") from None


def _int(value, what, low, high):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ScheduleError("number.format", f"{what} must be a whole number") from None
    if not low <= n <= high:
        raise ScheduleError("number.range", f"{what} must be between {low} and {high}")
    return n


def policy(stored):
    out = dict(DEFAULT_POLICY)
    out.update({k: v for k, v in (stored or {}).items() if k in DEFAULT_POLICY})
    return out


def check_policy(p):
    for k in ("premium_day_bp", "premium_night_bp", "rest_day_premium_bp", "holiday_premium_bp", "night_allowance_bp"):
        _int(p[k], k, 0, 100000)
    for k in ("max_daily_minutes_incl_ot",):
        _int(p[k], k, 60, 1440)
    for k in ("max_weekly_ot_minutes", "max_monthly_ot_minutes"):
        _int(p[k], k, 0, 100000)
    for k in ("night_from", "night_to"):
        if not HHMM.match(str(p[k])):
            raise ScheduleError("time.format", f"{k} must be HH:MM")


# ---------------------------------------------------------------------- validation of records
def validate(reg, entity, row, cur):
    """Called by the registry for the entities of this module; raises ScheduleError (turned into RegistryError there)."""
    today = reg.today()
    if entity == "headcount_plan":
        if not PERIOD.match(str(row.get("period") or "")):
            raise ScheduleError("plan.period", "the period is a month YYYY-MM")
        _int(row.get("planned_fte"), "planned headcount", 0, 100000)
        if row.get("source") not in ("manual", "crew_requirement"):
            raise ScheduleError("plan.source", "the source is manual or crew_requirement")
        if not row.get("job_id") and not row.get("work_center_code") and not row.get("org_unit_id"):
            raise ScheduleError("plan.scope", "say where the headcount is planned: a job, a work centre or an org unit")
        if row.get("job_id"):
            reg._live("job", row["job_id"], "the job")
        if row.get("org_unit_id"):
            reg._live("org_unit", row["org_unit_id"], "the org unit")
    elif entity == "agency":
        if not row.get("name"):
            raise ScheduleError("agency.name", "an agency needs a name")
        fee = row.get("fee_percent")
        if fee not in (None, ""):
            try:
                if not 0 <= float(fee) <= 100:
                    raise ValueError
            except (TypeError, ValueError):
                raise ScheduleError("agency.fee", "the fee is a percentage between 0 and 100") from None
    elif entity == "hire_requisition":
        _check_requisition(reg, row, cur, today)
    elif entity == "candidate":
        _check_candidate(reg, row, cur)
    elif entity == "onboarding_task":
        reg._live("employee", row.get("employee_id"), "the employee")
        if row.get("kind") not in ONBOARDING_KINDS:
            raise ScheduleError("onboarding.kind", f"the task is one of {', '.join(ONBOARDING_KINDS)}")
        if row.get("due"):
            _d(row["due"], "the due date")
        if row.get("done_on"):
            if _d(row["done_on"], "the completion date") > _d(today, "today"):
                raise ScheduleError("onboarding.future", "a task cannot be done in the future")
    elif entity == "contract":
        _check_contract(reg, row)
    elif entity == "overtime_request":
        _check_overtime(reg, row, cur, today)
    elif entity == "course":
        if not row.get("name"):
            raise ScheduleError("course.name", "a course needs a name")
        if row.get("skill_id"):
            reg._live("skill", row["skill_id"], "the skill")
            _int(row.get("grants_level"), "the level the course grants", 1, 4)
        if row.get("validity_months") not in (None, ""):
            _int(row["validity_months"], "validity in months", 0, 600)
        if row.get("duration_hours") not in (None, ""):
            _int(row["duration_hours"], "duration in hours", 0, 1000)
        if row.get("mandatory_for") not in (None, "", "all_production"):
            raise ScheduleError("course.mandatory", "mandatory for: everyone in production, or nobody")
        if row.get("onboarding_kind") not in (None, "") + ONBOARDING_KINDS:
            raise ScheduleError("course.onboarding", "the onboarding task a pass completes is one of the standard tasks")
    elif entity == "training_session":
        _check_session(reg, row, cur)
    elif entity == "leave_type":
        if not row.get("name"):
            raise ScheduleError("leave.name", "a leave type needs a name")
        if row.get("paid") not in (0, 1, "0", "1", None):
            raise ScheduleError("leave.paid", "paid is yes or no")
        for k in ("annual_days", "carry_over_days"):
            if row.get(k) not in (None, ""):
                _int(row[k], k, 0, 366)
    elif entity == "leave_request":
        _check_leave(reg, row, cur, today)


def _check_requisition(reg, row, cur, today):
    reg._live("job", row.get("job_id"), "the job")
    if row.get("position_id"):
        reg._live("position", row["position_id"], "the position")
    _int(row.get("count"), "the number of people", 1, 1000)
    if row.get("employment_type") not in EMPLOYMENT_TYPES:
        raise ScheduleError("req.type", f"the employment type is one of {', '.join(EMPLOYMENT_TYPES)}")
    if row.get("reason") not in REQ_REASONS:
        raise ScheduleError("req.reason", f"the reason is one of {', '.join(REQ_REASONS)}")
    if row.get("status") not in REQ_STATUS:
        raise ScheduleError("req.status", f"the status is one of {', '.join(REQ_STATUS)}")
    _d(row.get("needed_by"), "the needed-by date")
    if row["employment_type"] == "fixed_term":
        _int(row.get("contract_months"), "the contract length in months", 1, 120)
    if row["employment_type"] == "agency":
        reg._live("agency", row.get("agency_id"), "the agency")
    filled = _int(row.get("filled") if row.get("filled") not in (None, "") else 0, "filled", 0, 1000)
    if filled > int(row["count"]):
        raise ScheduleError("req.filled", "more people were hired than the requisition asked for")
    if cur is None and row["status"] != "draft":
        raise ScheduleError("req.new_status", "a requisition starts as a draft; it is approved by someone else")
    if cur and cur["status"] != row["status"] and row["status"] not in REQ_NEXT[cur["status"]]:
        raise ScheduleError("req.transition", f"a requisition {cur['status']} cannot become {row['status']}")
    if cur and cur["status"] not in ("draft",) and any(str(cur.get(k)) != str(row.get(k)) for k in ("count", "job_id", "employment_type")):
        raise ScheduleError("req.frozen", "after approval the number, job and type of a requisition no longer change: cancel it and raise a new one")
    # the headcount plan limits the number, unless a reason is written down
    if cur is None or cur.get("count") != row.get("count"):
        month = str(row["needed_by"])[:7]
        plans = reg.db.execute("SELECT planned_fte FROM headcount_plan WHERE job_id = ? AND period = ? AND deleted = 0", (row["job_id"], month)).fetchall()
        if plans:
            planned = sum(int(p[0]) for p in plans)
            asked = sum(int(r[0]) for r in reg.db.execute(
                "SELECT count FROM hire_requisition WHERE job_id = ? AND substr(needed_by, 1, 7) = ? AND deleted = 0 AND status <> 'cancelled' AND id != ?",
                (row["job_id"], month, cur["id"] if cur else "")))
            if asked + int(row["count"]) > planned and len(str(row.get("note") or "").strip()) < 10:
                raise ScheduleError("req.over_plan", f"the headcount plan for {month} allows {planned} and {asked} are already asked for: write the reason (in the note) to go beyond it")


def _check_candidate(reg, row, cur):
    if not row.get("display_name"):
        raise ScheduleError("candidate.name", "a candidate needs a name")
    if row.get("source") not in CAND_SOURCES:
        raise ScheduleError("candidate.source", f"the source is one of {', '.join(CAND_SOURCES)}")
    if row.get("stage") not in CAND_STAGES:
        raise ScheduleError("candidate.stage", f"the stage is one of {', '.join(CAND_STAGES)}")
    req = reg._live("hire_requisition", row.get("requisition_id"), "the requisition")
    if cur is None and req["status"] not in ("approved", "open"):
        raise ScheduleError("candidate.requisition", "candidates are taken for an approved or open requisition")
    if cur and CAND_STAGES.index(row["stage"]) < CAND_STAGES.index(cur["stage"]) and row["stage"] not in ("rejected", "withdrawn"):
        raise ScheduleError("candidate.backwards", "a candidate moves forward through the stages (or is rejected or withdraws)")
    if cur and cur["stage"] in ("hired", "rejected", "withdrawn") and cur["stage"] != row["stage"]:
        raise ScheduleError("candidate.final", f"a candidate who is {cur['stage']} does not change stage")


def _check_contract(reg, row):
    reg._live("employee", row.get("employee_id"), "the employee")
    if row.get("employment_type") not in EMPLOYMENT_TYPES:
        raise ScheduleError("contract.type", f"the employment type is one of {', '.join(EMPLOYMENT_TYPES)}")
    start = _d(row.get("start_date"), "the start date")
    if row.get("end_date"):
        if _d(row["end_date"], "the end date") < start:
            raise ScheduleError("contract.dates", "the contract ends before it starts")
    elif row["employment_type"] in ("fixed_term", "intern"):
        raise ScheduleError("contract.end", "a fixed-term or intern contract has an end date")
    if row.get("agency_id"):
        reg._live("agency", row["agency_id"], "the agency")


def _check_overtime(reg, row, cur, today):
    emp = reg._live("employee", row.get("employee_id"), "the employee")
    p = policy(reg.overtime_policy)
    day = _d(row.get("work_date"), "the work date")
    minutes = _int(row.get("planned_minutes"), "the planned minutes", 1, 600)
    if row.get("kind") not in OT_KINDS:
        raise ScheduleError("ot.kind", f"the kind is one of {', '.join(OT_KINDS)}")
    if row.get("status") not in OT_STATUS:
        raise ScheduleError("ot.status", f"the status is one of {', '.join(OT_STATUS)}")
    if not str(row.get("reason") or "").strip():
        raise ScheduleError("ot.reason", "overtime needs a reason")
    if cur is None and day < _d(today, "today") - timedelta(days=3):
        raise ScheduleError("ot.past", "overtime is asked for before it is worked (at most 3 days back, to record what already happened)")
    if cur and cur["status"] != "requested" and (cur["status"] != row["status"] or any(cur.get(k) != row.get(k) for k in ("work_date", "planned_minutes", "kind", "employee_id"))):
        raise ScheduleError("ot.decided", "a decided overtime request does not change")
    planned = Schedule(reg).day(emp["id"], day.isoformat())
    if planned["status"] == "leave":
        raise ScheduleError("ot.on_leave", f"{emp['code']} is on approved leave on {day}: no overtime is asked for a day of leave")
    if planned["status"] in ("rest", "holiday") and row["kind"] not in ("rest_day", "holiday"):
        raise ScheduleError("ot.kind_mismatch", f"{day} is a {planned['status'].replace('_', ' ')} for this person: the overtime is {'holiday' if planned['status'] == 'holiday' else 'rest day'} work")
    if planned["status"] == "work" and row["kind"] in ("rest_day", "holiday"):
        raise ScheduleError("ot.kind_mismatch", f"{day} is a normal working day for this person")
    if planned["status"] == "work" and minutes + planned["paid_minutes"] > p["max_daily_minutes_incl_ot"]:
        raise ScheduleError("ot.daily_cap", f"{planned['paid_minutes']} planned + {minutes} overtime is over the daily limit of {p['max_daily_minutes_incl_ot']} minutes")
    for label, key, start in (("weekly", "max_weekly_ot_minutes", day - timedelta(days=(day.weekday() + 2) % 7)), ("monthly", "max_monthly_ot_minutes", day.replace(day=1))):
        cap = p[key]
        if not cap:
            continue
        end = start + timedelta(days=6) if label == "weekly" else (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        used = reg.db.execute("SELECT COALESCE(SUM(planned_minutes), 0) FROM overtime_request WHERE employee_id = ? AND deleted = 0 AND status <> 'rejected' AND work_date BETWEEN ? AND ? AND id != ?",
                              (row["employee_id"], start.isoformat(), end.isoformat(), cur["id"] if cur else "")).fetchone()[0]
        if used + minutes > cap:
            raise ScheduleError("ot.period_cap", f"{used} minutes are already asked for this {label[:-2] if label == 'weekly' else 'month'} and the limit is {cap}")


def _check_session(reg, row, cur):
    reg._live("course", row.get("course_id"), "the course")
    _d(row.get("session_date"), "the session date")
    if row.get("status") not in ("planned", "done", "cancelled"):
        raise ScheduleError("session.status", "the status is planned, done or cancelled")
    attendees = row.get("attendees")
    try:
        people = json.loads(attendees) if isinstance(attendees, str) and attendees else (attendees or [])
        assert isinstance(people, list)
    except (ValueError, AssertionError):
        raise ScheduleError("session.attendees", "attendees are a list of employee codes") from None
    for a in people:
        code = a.get("employee_code") if isinstance(a, dict) else a
        emp = reg.get("employee", str(code))
        if not emp or emp["deleted"]:
            raise ScheduleError("session.attendee", f"attendee {code} is not an employee")
        if isinstance(a, dict) and a.get("result") not in (None, "", "pass", "fail"):
            raise ScheduleError("session.result", "a result is pass or fail")
    if cur and cur["status"] == "done" and (cur["status"] != row["status"] or cur.get("attendees") != row.get("attendees")):
        raise ScheduleError("session.done", "a completed session does not change: its results are what qualified people")


def _check_leave(reg, row, cur, today):
    emp = reg._live("employee", row.get("employee_id"), "the employee")
    ltype = reg._live("leave_type", row.get("leave_type_id"), "the leave type")
    first, last = _d(row.get("from_date"), "the first day"), _d(row.get("to_date"), "the last day")
    if last < first:
        raise ScheduleError("leave.dates", "the leave ends before it starts")
    if (last - first).days > 365:
        raise ScheduleError("leave.long", "a leave request covers at most a year")
    if row.get("status") not in LEAVE_STATUS:
        raise ScheduleError("leave.status", f"the status is one of {', '.join(LEAVE_STATUS)}")
    days = _int(row.get("days"), "the days", 1, 366)
    if days > (last - first).days + 1:
        raise ScheduleError("leave.days", "more leave days than days between the dates")
    if cur is None and row["status"] != "requested":
        raise ScheduleError("leave.new_status", "a leave request starts as requested; someone else approves it")
    if cur and cur["status"] == "approved" and any(str(cur.get(k)) != str(row.get(k)) for k in ("employee_id", "leave_type_id", "from_date", "to_date", "days")):
        raise ScheduleError("leave.frozen", "approved leave does not change (person, type, dates, days): cancel it and enter a new request, which someone else approves")
    if cur and cur["status"] in ("approved", "rejected", "cancelled") and cur["status"] != row["status"] and not (cur["status"] == "approved" and row["status"] == "cancelled"):
        raise ScheduleError("leave.decided", f"a {cur['status']} leave request cannot become {row['status']}")
    clash = reg.db.execute("SELECT code FROM leave_request WHERE employee_id = ? AND deleted = 0 AND status IN ('requested', 'approved') AND from_date <= ? AND to_date >= ? AND id != ?",
                           (row["employee_id"], last.isoformat(), first.isoformat(), cur["id"] if cur else "")).fetchone()
    if clash and row["status"] in ("requested", "approved"):
        raise ScheduleError("leave.overlap", f"{emp['code']} already has leave {clash[0]} on those days")
    if row["status"] == "approved" and (cur is None or cur["status"] != "approved") and ltype.get("annual_days") not in (None, "", 0, "0"):
        for year in range(first.year, last.year + 1):          # a request over New Year is charged to each year for the days that fall in it
            asked = days_in_year(reg, emp["id"], first, last, days, year)
            left = leave_balance(reg, emp["id"], ltype, year, exclude=cur["id"] if cur else None)
            # The proposed request also reduces the previous year's unused entitlement.
            if year > first.year and int(ltype.get("carry_over_days") or 0) and emp.get("hire_date") and str(emp["hire_date"]) < f"{year}-01-01":
                entitlement = int(ltype["annual_days"])
                previous_left = leave_balance(reg, emp["id"], dict(ltype, carry_over_days=0), year - 1, exclude=cur["id"] if cur else None)
                cap = int(ltype["carry_over_days"])
                previous_asked = days_in_year(reg, emp["id"], first, last, days, year - 1)
                left -= min(max(0, previous_left), cap) - min(max(0, previous_left - previous_asked), cap)
            if asked > left:
                raise ScheduleError("leave.insufficient", f"{emp['code']} has {left} day(s) of {ltype['code']} left in {year} and asks for {asked}")


# ---------------------------------------------------------------------- figures
def days_in_year(reg, employee_id, first, last, days, year):
    """The working days of a leave (first..last, `days` in all) that fall in `year`: the person's own rest days and holidays do not count, and an
    unscheduled day does (as in `leave_days`). Whole-year requests answer `days`; the parts of a request over New Year add up to `days`."""
    if first.year == last.year:
        return int(days) if first.year == year else 0
    plan = Schedule(reg)
    plan.leaves = {}                                            # the leave itself must not hide its own days
    counts = {}
    d = first
    while d <= last:
        if plan.day(employee_id, d.isoformat())["status"] not in ("rest", "holiday"):
            counts[d.year] = counts.get(d.year, 0) + 1
        d += timedelta(days=1)
    total = sum(counts.values())
    if total == int(days):
        return counts.get(year, 0)
    if not total:  # Legacy/manual requests on only rest days still have a recorded day charge.
        d = first
        while d <= last:
            counts[d.year] = counts.get(d.year, 0) + 1
            d += timedelta(days=1)
        total = sum(counts.values())
    ys = sorted(counts)                                         # days typed by hand: shared in proportion, the remainder to the last year
    shares = {y: int(days) * counts[y] // max(1, total) for y in ys}
    shares[ys[-1]] += int(days) - sum(shares.values())
    return shares.get(year, 0)


def leave_balance(reg, employee_id, ltype, year, exclude=None):
    """Days of a capped leave type left in `year`: the yearly entitlement, plus the unused days of the year before up to
    the carry-over limit, minus the approved days of the year (a request over New Year counts in each year for its own days).
    A type without an entitlement has no balance (uncapped)."""
    entitlement = int(ltype.get("annual_days") or 0)
    carry_cap = int(ltype.get("carry_over_days") or 0)

    def used(y):
        total = 0
        for r in reg.db.execute(
                "SELECT from_date, to_date, days, id FROM leave_request WHERE employee_id = ? AND leave_type_id = ? AND deleted = 0 AND status = 'approved' "
                "AND substr(from_date, 1, 4) <= ? AND substr(to_date, 1, 4) >= ?", (employee_id, ltype["id"], str(y), str(y))):
            if exclude is not None and r[3] == exclude:
                continue
            total += days_in_year(reg, employee_id, _d(r[0], "the first day"), _d(r[1], "the last day"), int(r[2]), y)
        return total
    emp = reg.by_id("employee", employee_id)
    # unused days carry over only for someone already employed the year before (no hire date on record: no carry-over)
    employed_before = bool(emp and emp.get("hire_date") and str(emp["hire_date"]) < f"{year}-01-01")
    carried = min(max(0, entitlement - used(year - 1)), carry_cap) if carry_cap and employed_before else 0
    return entitlement + carried - used(year)


def next_code(reg, entity, prefix, width=4):
    n = 0
    for r in reg.list(entity, include_deleted=True):
        m = re.fullmatch(re.escape(prefix) + r"(\d+)", r["code"])
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1:0{width}d}"


def next_employee_code(reg):
    n = 0
    for r in reg.list("employee", include_deleted=True):
        m = re.fullmatch(r"E(\d{6})", r["code"])
        if m:
            n = max(n, int(m.group(1)))
    return f"E{n + 1:06d}"


def classify_day(reg, employee_id, day, pol):
    """rest_day | holiday | day | night for the overtime of `employee_id` on `day` (from the plan; night when most of the shift
    falls in the night window)."""
    planned = Schedule(reg).day(employee_id, day)
    if planned["status"] == "holiday":
        return "holiday"
    if planned["status"] == "rest":
        return "rest_day"
    if planned["status"] == "work" and planned.get("start") and planned.get("end"):
        def minutes(t):
            return int(t[11:13]) * 60 + int(t[14:16])
        start, end = minutes(planned["start"]), minutes(planned["end"]) + (1440 if planned["end"][:10] > planned["start"][:10] else 0)
        n_from, n_to = int(pol["night_from"][:2]) * 60 + int(pol["night_from"][3:]), int(pol["night_to"][:2]) * 60 + int(pol["night_to"][3:])
        night = sum(1 for m in range(start, end) if m % 1440 >= n_from or m % 1440 < n_to)      # the window runs through midnight
        return "night" if night * 2 > (end - start) else "day"
    return "day"


def overtime_for_period(reg, period, worked=None):
    """The payroll input of WP-H6: per employee, the approved overtime of the month by kind with the premium in basis points and
    the substitute days owed for rest-day work; plus the exceptions (overtime that was worked but never approved)."""
    if not PERIOD.match(period):
        raise ScheduleError("period.format", "the period is a month YYYY-MM")
    pol = policy(reg.overtime_policy)
    premium = {"day": pol["premium_day_bp"], "night": pol["premium_night_bp"], "rest_day": pol["rest_day_premium_bp"], "holiday": pol["holiday_premium_bp"]}
    emp_code = {e["id"]: e["code"] for e in reg.list("employee")}
    people, approved_days = {}, set()
    for r in reg.list("overtime_request"):
        if r["status"] != "approved" or not str(r["work_date"]).startswith(period):
            continue
        p = people.setdefault(emp_code.get(r["employee_id"], "?"), {"employee": emp_code.get(r["employee_id"], "?"), "minutes": {k: 0 for k in OT_KINDS}, "premium_bp": premium, "substitute_days": 0, "_days": set()})
        p["minutes"][r["kind"]] += int(r["planned_minutes"])
        approved_days.add((p["employee"], r["work_date"]))
        if r["kind"] == "rest_day":
            p["_days"].add(r["work_date"])
    for p in people.values():
        p["substitute_days"] = len(p.pop("_days")) if pol["substitute_day_for_rest_day"] else 0
        p["total_minutes"] = sum(p["minutes"].values())
    exceptions = []
    for w in worked or []:                       # {employee, date, beyond_plan}: what manufacturing/attendance say was worked beyond the plan
        if str(w["date"]).startswith(period) and w["beyond_plan"] > 0 and (w["employee"], w["date"]) not in approved_days:
            exceptions.append({"employee": w["employee"], "date": w["date"], "minutes": w["beyond_plan"], "reason": "worked beyond the plan without an approved overtime request"})
    return {"period": period, "policy": pol, "employees": sorted(people.values(), key=lambda x: x["employee"]), "exceptions": sorted(exceptions, key=lambda x: (x["employee"], x["date"]))}


def headcount_from_crew(rows, relief_bp=800):
    """Average required headcount per line and month from GMES crew requirements, plus the relief allowance (absence, leave):
    a proposal for `headcount_plan` (never applied by itself)."""
    by = {}
    for r in rows:
        if r["headcount"] <= 0:
            continue
        key = (r["line_code"], r["work_date"][:7])
        day = by.setdefault(key, {})
        day[r["work_date"]] = day.get(r["work_date"], 0) + r["headcount"]         # all shifts of a day together
    out = []
    for (line, month), days in sorted(by.items()):
        avg = sum(days.values()) / len(days)
        out.append({"work_center_code": line, "period": month, "planned_fte": int(-(-avg * (10000 + relief_bp) // 10000)), "average_required": round(avg, 2), "days": len(days)})
    return out


def contract_ends(reg, today):
    """The employees whose fixed-term contract ended before `today` and who are still Active: they become Terminated on the
    contract's last day (reason: contract end). One journal line per call."""
    emp = {e["id"]: e for e in reg.list("employee")}
    ops = []
    for c in reg.list("contract"):
        e = emp.get(c["employee_id"])
        if not e or e["employment_status"] != "Active" or not c.get("end_date") or c["end_date"] >= today:
            continue
        later = [x for x in reg.list("contract") if x["employee_id"] == c["employee_id"] and (x.get("end_date") or "9999") > c["end_date"]]
        if later:
            continue                                                     # a newer contract continues the employment
        ops.append(reg.op_put("employee", e["code"], {"employment_status": "Terminated", "termination_date": c["end_date"]}, e["ver"]))
    return ops


def default_expiry(certified_on, months):
    return skills.default_expiry(certified_on, months)
