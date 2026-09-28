"""Skills and qualifications (phase 5). Standard library only.

    skill           a catalogue entry: what a person can be qualified for (e.g. WELD-MIG), how long a qualification
                    stays valid (months; empty = does not expire)
    employee_skill  one person holds one skill at a level (1 learner, 2 works with help, 3 independent, 4 can train
                    others), certified on a date, valid until a date. Coded <employee>-<skill>: re-certifying changes
                    the same record, and the permanent history keeps every earlier state.

Which skill a station needs is MANUFACTURING's configuration (GMES owns stations); HR owns who is qualified and
publishes it (eco.qualification.v1). A qualification is valid on a day when the day is between certified_on and
expires_on (inclusive) and the employee and the record are not in the Recycle Bin.
"""

from datetime import date

from .scheduling import ScheduleError, iso, whole

LEVELS = {1: "learner", 2: "with help", 3: "independent", 4: "trainer"}


def add_months(day, months):
    y, m = divmod(day.month - 1 + months, 12)
    y, m = day.year + y, m + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(day.day, last))


def check_skill(row):
    if not (row.get("name") or "").strip():
        raise ScheduleError("skill.name", "a skill needs a name")
    if row.get("validity_months") is not None:
        whole(row["validity_months"], "validity (months)", 1, 120)


def check_employee_skill(row, employee_code, skill_code):
    if row.get("code") != f"{employee_code}-{skill_code}":
        raise ScheduleError("qualification.code", f"a qualification is coded <employee>-<skill> ({employee_code}-{skill_code}): one per person and skill")
    whole(row.get("level"), "the level", 1, 4)
    start = iso(row.get("certified_on"), "the certification date")
    if row.get("expires_on") and iso(row["expires_on"], "the expiry date") < start:
        raise ScheduleError("qualification.dates", "a qualification cannot expire before it was certified")


def default_expiry(certified_on, validity_months):
    """The expiry a skill's validity gives, when the person did not type one (None when the skill never expires)."""
    if not validity_months or not certified_on:
        return None
    return add_months(date.fromisoformat(certified_on), int(validity_months)).isoformat()


def state(q, on):
    """valid | expiring (within 30 days) | expired | not_yet — for the day `on` (YYYY-MM-DD)."""
    if q["certified_on"] > on:
        return "not_yet"
    if q.get("expires_on") and q["expires_on"] < on:
        return "expired"
    if q.get("expires_on") and (date.fromisoformat(q["expires_on"]) - date.fromisoformat(on)).days <= 30:
        return "expiring"
    return "valid"
