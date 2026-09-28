"""Discipline (phase 6): the company's penalty schedule, violations and decisions.

    penalty_rule  one line of the company's penalty schedule (لائحة الجزاءات): which violation, from how many minutes it
                  counts, over how many days repeats are counted, and the penalty for the 1st, 2nd, 3rd ... time.
                  steps: comma list of penalties, e.g. "warning,deduct:0.25,deduct:0.5,deduct:1,investigation".
    violation     one violation of one person on one day (code <employee>-<date>-<rule>): proposed from attendance or
                  entered by hand, then decided once by someone with the right to decide (approved or waived).

A penalty is written, never computed into money: "deduct:0.5" means half a day's wage, recorded as days. Turning
days into an amount is payroll's job (design only, docs/HR_PAYROLL_DESIGN.md); Mizan books the entry.

Rules (Egyptian labour law defaults; the schedule itself is the company's, approved as the law requires - confirm
the figures with your legal adviser):
  * one penalty per violation; a deduction for one violation is at most 5 days' wage;
  * the deductions decided for one person in one calendar month are at most 5 days in all;
  * no penalty more than 30 days after the violation was found (the day it was proposed or entered);
  * a deduction of more than one day, or a referral to investigation, needs the written investigation or reason;
  * a decision is final: a decided violation never changes (history); a mistake is corrected by a new decision
    on appeal, recorded as its own violation line with the reason.
Standard library only.
"""

from datetime import date, timedelta

from .scheduling import ScheduleError, iso

VIOLATIONS = ("late", "early_leave", "absence", "no_record", "misconduct")
STATUSES = ("proposed", "approved", "waived")
MAX_SINGLE_DEDUCTION = 5
MAX_MONTH_DEDUCTION = 5
DECIDE_WITHIN_DAYS = 30


def parse_penalty(text):
    """'warning' | 'final_warning' | 'investigation' | 'deduct:<days>' -> (kind, days). Raises on anything else."""
    t = str(text or "").strip()
    if t in ("warning", "final_warning", "investigation"):
        return t, 0.0
    if t.startswith("deduct:"):
        try:
            days = float(t.split(":", 1)[1])
        except ValueError:
            days = -1
        if 0 < days <= MAX_SINGLE_DEDUCTION and abs(days * 4 - round(days * 4)) < 1e-9:
            return "deduct", days
        raise ScheduleError("penalty.deduction", f"a deduction is 0.25 to {MAX_SINGLE_DEDUCTION} days in quarter days, got {t!r}")
    raise ScheduleError("penalty.kind", f"a penalty is warning, final_warning, investigation or deduct:<days>, got {t!r}")


def steps_of(rule):
    return [s.strip() for s in str(rule.get("steps") or "").split(",") if s.strip()]


def check_rule(row):
    if not (row.get("name") or "").strip():
        raise ScheduleError("rule.name", "a rule of the penalty schedule needs a name")
    if row.get("violation") not in VIOLATIONS:
        raise ScheduleError("rule.violation", f"the violation is one of {', '.join(VIOLATIONS)}")
    for key, low, high in (("threshold_minutes", 0, 480), ("window_days", 1, 366)):
        v = row.get(key)
        if v is not None and not (isinstance(v, int) and low <= v <= high):
            raise ScheduleError("rule.number", f"{key} is a whole number from {low} to {high}")
    steps = steps_of(row)
    if not steps:
        raise ScheduleError("rule.steps", "give the penalty for the first time at least (e.g. warning)")
    for s in steps:
        parse_penalty(s)


def proposed_for(rule, occurrence):
    """The schedule's penalty for the n-th time within the window (the last step repeats)."""
    steps = steps_of(rule)
    return steps[min(max(occurrence, 1), len(steps)) - 1]


def check_violation(row, cur, employee_code, rule_code, today, deducted_in_month):
    """`deducted_in_month`: days already deducted by OTHER approved violations of this person in the month of
    this violation's day."""
    day = iso(row.get("work_date"), "the day of the violation")
    if row.get("code") != f"{employee_code}-{day.isoformat()}-{rule_code}":
        raise ScheduleError("violation.code", f"a violation is coded <employee>-<date>-<rule> ({employee_code}-{day.isoformat()}-{rule_code})")
    if day.isoformat() > today:
        raise ScheduleError("violation.future", "a violation happens on a day that has passed (or today)")
    status = row.get("status") or "proposed"
    if status not in STATUSES:
        raise ScheduleError("violation.status", f"the status is one of {', '.join(STATUSES)}")
    if row.get("proposed"):
        parse_penalty(row["proposed"])
    if cur and not cur.get("deleted") and cur.get("status") in ("approved", "waived"):
        raise ScheduleError("violation.decided", f"violation {row['code']} was decided on {cur.get('decided_on')}: a decision is final; "
                            "record an appeal as a new decision instead")
    if status == "proposed":
        if row.get("decision") or row.get("decided_on") or row.get("decided_by"):
            raise ScheduleError("violation.undecided", "a proposed violation has no decision yet")
        return
    decided_on = iso(row.get("decided_on"), "the day of the decision")
    if not row.get("decided_by"):
        raise ScheduleError("violation.decided_by", "a decision records who decided")
    if status == "waived":  # waiving is always possible, also after the 30 days
        if not (row.get("note") or "").strip():
            raise ScheduleError("penalty.reason", "say why the violation is waived")
        return
    found = date.fromisoformat((cur or {}).get("created_at", today)[:10]) if cur else date.fromisoformat(today)
    if decided_on > found + timedelta(days=DECIDE_WITHIN_DAYS):
        raise ScheduleError("penalty.too_late", f"a penalty must be decided within {DECIDE_WITHIN_DAYS} days of finding the violation "
                            f"(found on {found.isoformat()}); after that it can only be waived")
    kind, days = parse_penalty(row.get("decision"))
    if (kind == "investigation" or days > 1) and not (row.get("note") or "").strip():
        raise ScheduleError("penalty.investigation", "a deduction of more than one day, or a referral, needs the written investigation (note)")
    if days and deducted_in_month + days > MAX_MONTH_DEDUCTION:
        raise ScheduleError("penalty.month_cap", f"this would deduct {deducted_in_month + days:g} days in {day.strftime('%Y-%m')}: "
                            f"the deductions of one month are at most {MAX_MONTH_DEDUCTION} days")


def check_violation_delete(cur):
    if cur.get("status") in ("approved", "waived"):
        raise ScheduleError("violation.decided", f"violation {cur['code']} was decided: a decision is history and is not deleted")


def findings(compared_days, attendance_rows, rules, employees_by_id):
    """What the attendance says, per person and day: [(employee, day, violation, minutes)]. Nothing is guessed: a
    day on approved leave, a rest day or a holiday is never a violation."""
    by_key = {}
    for r in attendance_rows:
        by_key[(str(r.get("employee_id") or "").strip(), str(r.get("work_date") or "")[:10])] = r
    wanted = {r["violation"] for r in rules}
    out = []
    for d in compared_days:
        emp = employees_by_id.get(d["employee_id"])
        if not emp or d["status"] != "work":
            continue
        r = by_key.get((emp["code"], d["work_date"])) or by_key.get((emp.get("legacy_number") or "", d["work_date"]))
        if d["verdict"] == "absent" and "absence" in wanted:
            out.append((emp, d["work_date"], "absence", 0))
        elif d["verdict"] == "no_record" and "no_record" in wanted:
            out.append((emp, d["work_date"], "no_record", 0))
        elif d["verdict"] == "as_planned" and r:
            late, early = int(float(r.get("late_minutes") or 0)), int(float(r.get("early_leave_minutes") or 0))
            if late and "late" in wanted:
                out.append((emp, d["work_date"], "late", late))
            if early and "early_leave" in wanted:
                out.append((emp, d["work_date"], "early_leave", early))
    return out
