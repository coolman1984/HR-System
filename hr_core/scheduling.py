"""Shifts, working calendars, assignments and the planned schedule (phase 3). Standard library only.

The planned schedule exists BEFORE attendance and attendance is compared with it, never the other way round:

    shift            a named working time: start, end (an end at or before the start = overnight), break, grace
    work_calendar    weekly rest days and public holidays
    shift_assignment an employee works a shift under a calendar from a date (to a date); effective dated:
                     "regular" ones may not overlap each other, a "temporary" one covers a regular one for its dates
    roster_override  one employee, one day: another shift, or a day off (no shift); a swap is two of them

Resolving one employee's day, in order: an override for that day; else a temporary assignment covering it; else a
regular one; then that assignment's calendar makes the day a rest day or a holiday. An overnight shift has exactly ONE
work date, the day it starts (07 Oct 22:00 - 08 Oct 06:00 belongs to 07 Oct).

An assignment may be created with a start in the past only where the person had no plan of that kind (the first
set-up of a plant); it can never replace a plan that existed.

The rules that keep the past unchanged (checked in hr_core/registry.py through `check_*` below): an assignment that
has started keeps its employee, shift, calendar, kind and start and may only be ended (not before yesterday); an
override is for today or later; a shift or calendar already used by a started assignment keeps its times / rest days
/ past holidays (make a new one instead).
"""

from datetime import date, timedelta

DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
KINDS = ("regular", "temporary")
MAX_GRACE = 120


class ScheduleError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------- small parsers (strict: nothing is guessed)
def hhmm(value, what):
    text = str(value or "")
    if len(text) != 5 or text[2] != ":" or not (text[:2].isdigit() and text[3:].isdigit()) or int(text[:2]) > 23 or int(text[3:]) > 59:
        raise ScheduleError("shift.time", f"{what} must be HH:MM between 00:00 and 23:59, got {value!r}")
    return int(text[:2]) * 60 + int(text[3:])


def iso(value, what):
    try:
        if not (isinstance(value, str) and len(value) == 10):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        raise ScheduleError("date.format", f"{what} must be a date YYYY-MM-DD, got {value!r}") from None


def whole(value, what, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ScheduleError("number.range", f"{what} must be a whole number from {low} to {high}, got {value!r}")
    return value


def duration(shift):
    """Minutes from start to end; an end at or before the start is the next day (overnight)."""
    start, end = hhmm(shift["start_time"], "start"), hhmm(shift["end_time"], "end")
    return (end - start) % 1440 or 1440, end <= start


def rest_days(text):
    days = [d for d in str(text or "").split(",") if d]
    if any(d not in DAYS for d in days) or len(set(days)) != len(days):
        raise ScheduleError("calendar.rest_days", f"rest days are a comma list of {', '.join(DAYS)} without repeats, got {text!r}")
    return days


def holidays(text):
    days = [d for d in str(text or "").split(",") if d]
    for d in days:
        iso(d, "a holiday")
    if days != sorted(set(days)):
        raise ScheduleError("calendar.holidays", "holidays are written once each, in date order")
    return days


# ---------------------------------------------------------------------- rules used by the registry
def check_shift(row, cur, in_use):
    if not row.get("name"):
        raise ScheduleError("shift.name", "a shift needs a name")
    minutes, _ = duration(row)
    whole(row.get("break_minutes") or 0, "the break", 0, minutes - 1)
    whole(row.get("grace_minutes") or 0, "the grace time", 0, MAX_GRACE)
    if cur and in_use and any(row.get(k) != cur.get(k) for k in ("start_time", "end_time", "break_minutes")):
        raise ScheduleError("shift.in_use", f"shift {row['code']} is already worked by started assignments: its times would rewrite "
                            "past schedules. Create a new shift and assign it from a date instead")


def check_calendar(row, cur, in_use, today):
    if not row.get("name"):
        raise ScheduleError("calendar.name", "a calendar needs a name")
    rest_days(row.get("rest_days"))
    new = holidays(row.get("holidays"))
    if cur and in_use:
        if row.get("rest_days") != cur.get("rest_days"):
            raise ScheduleError("calendar.in_use", f"calendar {row['code']} is used by started assignments: changing its rest days would "
                                "rewrite past schedules. Create a new calendar and assign it from a date instead")
        past = lambda days: [d for d in days if d < today]  # noqa: E731
        if past(new) != past(holidays(cur.get("holidays"))):
            raise ScheduleError("calendar.past_holidays", "holidays before today are part of past schedules and cannot change")


def check_assignment(row, cur, others, today):
    """`others`: this employee's other (not deleted) assignments."""
    if row.get("kind") not in KINDS:
        raise ScheduleError("assignment.kind", f"an assignment is {' or '.join(KINDS)}")
    start = iso(row.get("valid_from"), "the start date")
    end = iso(row["valid_to"], "the end date") if row.get("valid_to") else None
    if end and end < start:
        raise ScheduleError("assignment.dates", "an assignment cannot end before it starts")
    if row["kind"] == "temporary" and not end:
        raise ScheduleError("assignment.temporary_end", "a temporary assignment needs an end date")
    t = date.fromisoformat(today)
    if cur and not cur.get("deleted") and cur.get("valid_from") and cur["valid_from"] < today:
        fixed = ("employee_id", "shift_id", "calendar_id", "kind", "valid_from")
        if any(row.get(k) != cur.get(k) for k in fixed):
            raise ScheduleError("assignment.started", f"assignment {row['code']} has started: only its end date can change "
                                "(end it and start a new one, so past schedules stay as they were)")
        if row.get("valid_to") != cur.get("valid_to"):
            if cur.get("valid_to") and cur["valid_to"] < today:
                raise ScheduleError("assignment.ended", f"assignment {row['code']} has already ended; the past is not rewritten")
            if end and end < t - timedelta(days=1):
                raise ScheduleError("assignment.past", "an assignment can be ended yesterday at the earliest; days before are history")
    for o in others:
        if o["kind"] != row["kind"]:
            continue
        o_start, o_end = date.fromisoformat(o["valid_from"]), date.fromisoformat(o["valid_to"]) if o.get("valid_to") else None
        if start <= (o_end or date.max) and o_start <= (end or date.max):
            raise ScheduleError("assignment.overlap", f"the employee already has the {row['kind']} assignment {o['code']} "
                                f"({o['valid_from']} to {o.get('valid_to') or 'open'}) on these dates")


def check_override(row, cur, employee_code, today, deleting=False):
    day = iso(row.get("work_date"), "the day")
    if row.get("code") != f"{employee_code}-{day.isoformat()}":
        raise ScheduleError("override.code", f"a day's change is coded <employee>-<date> ({employee_code}-{day.isoformat()}): one per person and day")
    if not deleting and not (row.get("reason") or "").strip():
        raise ScheduleError("override.reason", "say why the day changes")
    for d in filter(None, (row.get("work_date"), cur and not cur.get("deleted") and cur.get("work_date"))):
        if d < today:
            raise ScheduleError("override.past", "a day before today is history: its schedule cannot change")


def check_assignment_delete(cur, today):
    if cur.get("valid_from") and cur["valid_from"] < today:
        raise ScheduleError("assignment.started", f"assignment {cur['code']} has started: end it instead of deleting it")


# ---------------------------------------------------------------------- the planned schedule
class Schedule:
    """Everything needed to resolve days, read once from the registry (current, not deleted records)."""

    def __init__(self, registry):
        live = lambda e: [r for r in registry.list(e) if not r["deleted"]]  # noqa: E731
        self.employees = {r["id"]: r for r in live("employee")}
        self.shifts = {r["id"]: r for r in registry.list("shift", include_deleted=True)}      # history needs deleted ones too
        self.calendars = {r["id"]: r for r in registry.list("work_calendar", include_deleted=True)}
        self.assignments, self.overrides = {}, {}
        for a in live("shift_assignment"):
            self.assignments.setdefault(a["employee_id"], []).append(a)
        for o in live("roster_override"):
            self.overrides[(o["employee_id"], o["work_date"])] = o
        # approved leave (hr_core/people_ops.py): the person is not expected on those days
        self.leaves = {}
        for lv in live("leave_request"):
            if lv["status"] == "approved":
                self.leaves.setdefault(lv["employee_id"], []).append((lv["from_date"], lv["to_date"]))

    def day(self, employee_id, work_date):
        d = work_date if isinstance(work_date, str) else work_date.isoformat()
        emp = self.employees.get(employee_id)
        out = {"employee_id": employee_id, "employee_code": emp["code"] if emp else None, "work_date": d,
               "status": "unscheduled", "shift_code": None, "start": None, "end": None, "overnight": False, "paid_minutes": 0, "source": None}
        if any(f <= d <= l for f, l in self.leaves.get(employee_id, ())):
            out.update(status="leave", source="leave")
            return out
        covering = [a for a in self.assignments.get(employee_id, []) if a["valid_from"] <= d and (not a.get("valid_to") or d <= a["valid_to"])]
        chosen = next((a for a in covering if a["kind"] == "temporary"), None) or next((a for a in covering if a["kind"] == "regular"), None)
        override = self.overrides.get((employee_id, d))
        if override:
            out["source"] = "override"
            if not override.get("shift_id"):
                out["status"] = "rest"
                return out
            return self._work(out, self.shifts[override["shift_id"]], d)
        if not chosen:
            return out
        out["source"] = chosen["kind"]
        cal = self.calendars.get(chosen.get("calendar_id")) or {}
        if d in holidays(cal.get("holidays")):
            out["status"] = "holiday"
            return out
        if DAYS[date.fromisoformat(d).weekday()] in rest_days(cal.get("rest_days")):
            out["status"] = "rest"
            return out
        return self._work(out, self.shifts[chosen["shift_id"]], d)

    @staticmethod
    def _work(out, shift, d):
        minutes, overnight = duration(shift)
        start = date.fromisoformat(d)
        end_day = start + timedelta(days=1) if overnight else start
        out.update(status="work", shift_code=shift["code"], overnight=overnight, paid_minutes=minutes - int(shift.get("break_minutes") or 0),
                   start=f"{d}T{shift['start_time']}", end=f"{end_day.isoformat()}T{shift['end_time']}")
        return out

    def days(self, first, last, employee_ids=None):
        a, b = iso(first, "the first day"), iso(last, "the last day")
        if b < a or (b - a).days > 92:
            raise ScheduleError("schedule.range", "ask for 1 to 93 days, first day before last")
        ids = employee_ids or sorted(self.employees, key=lambda i: self.employees[i]["code"])
        return [self.day(e, (a + timedelta(days=n)).isoformat()) for e in ids for n in range((b - a).days + 1)]


# ---------------------------------------------------------------------- planned vs attended
PRESENT = {"present", "late", "early leave", "early_leave", "overtime"}


def compare(days, attendance_rows, employees):
    """Planned days against attendance records. An attendance record is matched to the registry employee by code,
    else by the old number (the attendance files still carry the old numbers until phase 4 binds them).
    Returns rows with a verdict; nothing is guessed: an unknown attendance person is reported, not matched."""
    by_code = {e["code"]: e for e in employees.values()}
    by_legacy = {e["legacy_number"]: e for e in employees.values() if e.get("legacy_number")}
    seen, unknown = {}, set()
    for r in attendance_rows:
        key = str(r.get("employee_id") or "").strip()
        emp = by_code.get(key) or by_legacy.get(key)
        day = str(r.get("work_date") or "")[:10]
        if not emp:
            if key:
                unknown.add(key)
            continue
        seen[(emp["id"], day)] = r
    out = []
    for d in days:
        r = seen.get((d["employee_id"], d["work_date"]))
        status = str(r.get("attendance_status") or "").strip() if r else None
        present = bool(status) and status.lower() in PRESENT
        if d["status"] == "work":
            verdict = "no_record" if r is None else "as_planned" if present else "leave" if status and "leave" in status.lower() else "absent"
        elif d["status"] == "leave":
            verdict = "worked_on_leave" if present else "on_leave"
        elif d["status"] in ("rest", "holiday"):
            verdict = "worked_off_day" if present else "off"
        else:
            verdict = "no_schedule" if present else "none"
        out.append({**d, "attendance_status": status, "worked_minutes": r.get("worked_minutes") if r else None, "verdict": verdict,
                    "late_minutes": r.get("late_minutes") if r else None, "early_leave_minutes": r.get("early_leave_minutes") if r else None})
    return {"days": out, "unknown_attendance_people": sorted(unknown)}
