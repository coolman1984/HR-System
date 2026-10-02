"""Pay arithmetic of WP-H6: one employee's month, in whole piastres (integers only, never floats).

Pure functions, no I/O. The Egyptian rules are the same ones Mizan's tests check against worked examples
(Law 91/2005 art. 8 as amended by Law 7/2024; social insurance Law 148/2019; overtime Labour Law 14/2025):

* social insurance is taken on the insurable wage kept between a minimum and a maximum (2026: 2,700 and 16,700 pounds),
  employee 11 %, employer 18.75 %, prorated for a part month;
* salary tax is taken on the month's gross less the employee's insurance, multiplied by 12, less the personal exemption
  (20,000 pounds), rounded down to 10 pounds, run through the yearly brackets, divided by 12;
* overtime is the hourly wage (basic / 240) times the minutes times (1 + premium), the premiums come from the company's
  overtime policy (day 35 %, night 70 %, rest day and holiday 100 % by default).

Every rounding is half up to the piastre and happens once per amount, so the same input always gives the same pay.
Standard library only.
"""

POUND = 100                       # piastres
HOUR_DIVISOR = 240                # 30 days x 8 hours
DEFAULT_RULES = {
    "si_employee_bp": 1100, "si_employer_bp": 1875,
    "si_min_minor": 2_700 * POUND, "si_max_minor": 16_700 * POUND,
    "exemption_minor": 20_000 * POUND,
    "martyrs_fund_bp": 5,         # 0.05 % of gross (a deduction in Egypt's payroll)
    "hour_divisor": HOUR_DIVISOR,
    "absence_divisor": 30,        # one absent day costs basic / 30
}
# the yearly brackets: (upper bound in pounds or None, rate in basis points)
BRACKETS = [(40_000, 0), (55_000, 1000), (70_000, 1500), (200_000, 2000), (400_000, 2250), (1_200_000, 2500), (None, 2750)]


def div_half_up(numerator, denominator):
    """Integer division rounding half up (for the positive amounts of payroll)."""
    return (2 * numerator + denominator) // (2 * denominator)


def pct(amount, bp):
    return div_half_up(amount * bp, 10_000)


def bracket_tax(income, brackets):
    """Tax on `income` (piastres) where each bracket's lower bound is the previous one's upper bound (the first starts at 0)."""
    tax, low = 0, 0
    for upper, bp in brackets:
        top = income if upper is None else min(income, upper * POUND)
        if top > low:
            tax += (top - low) * bp
        if upper is None or income <= upper * POUND:
            break
        low = upper * POUND
    return div_half_up(tax, 10_000)             # rounded once, at the end, like Mizan's own tax engine


def salary_tax_yearly(annual_minor):
    """Egypt's salary tax on the yearly taxable income: rounded down to 10 pounds; above 600,000 the lowest brackets fall away."""
    income = annual_minor // (10 * POUND) * (10 * POUND)
    if income <= 0:
        return 0
    dropped = 5 if income > 1_200_000 * POUND else 4 if income > 900_000 * POUND else 3 if income > 800_000 * POUND else 2 if income > 700_000 * POUND else 1 if income > 600_000 * POUND else 0
    return bracket_tax(income, BRACKETS[dropped:])


def clamp(value, low, high):
    return max(min(value, high), low)


def overtime_pay(basic_minor, minutes, premium_bp, divisor=HOUR_DIVISOR):
    """Pay for `minutes` of overtime at the hourly wage with a premium: basic x minutes x (10000 + premium) / (divisor x 60 x 10000)."""
    if minutes <= 0:
        return 0
    return div_half_up(basic_minor * minutes * (10_000 + premium_bp), divisor * 60 * 10_000)


def payslip(profile, share, ot_minutes, premium_bp, night_days, night_bp, unpaid_days, bonus_minor, deduction_minor, rules=None):
    """One employee's month. `share` is (numerator, denominator): the part of the month employed (days in post / days in the month).
    `profile` has basic_minor, allowance_minor, insurable_minor. `ot_minutes` / `premium_bp` are dicts by kind (day, night, rest_day, holiday).
    Returns every line in piastres; gross = earnings, net = gross - insurance - tax - other deductions."""
    r = dict(DEFAULT_RULES, **(rules or {}))
    num, den = share
    basic = div_half_up(profile["basic_minor"] * num, den)
    allowance = div_half_up(profile["allowance_minor"] * num, den)
    absence = div_half_up(profile["basic_minor"] * unpaid_days, r["absence_divisor"]) if unpaid_days else 0
    absence = min(absence, basic + allowance)                  # an absence never costs more than the month's pay
    overtime = {k: overtime_pay(profile["basic_minor"], int(ot_minutes.get(k, 0)), int(premium_bp[k]), r["hour_divisor"]) for k in ("day", "night", "rest_day", "holiday")}
    night_allowance = div_half_up(profile["basic_minor"] * night_bp * night_days, 10_000 * 26) if night_days else 0
    earnings = basic + allowance - absence + int(bonus_minor)
    overtime_total = sum(overtime.values())
    gross = earnings + overtime_total + night_allowance
    base = div_half_up(clamp(int(profile["insurable_minor"]), r["si_min_minor"], r["si_max_minor"]) * num, den)
    si_employee, si_employer = pct(base, r["si_employee_bp"]), pct(base, r["si_employer_bp"])
    taxable_year = max(0, (gross - si_employee) * 12 - r["exemption_minor"])
    tax = div_half_up(salary_tax_yearly(taxable_year), 12)
    other = pct(gross, r["martyrs_fund_bp"]) + int(deduction_minor)
    net = gross - si_employee - tax - other
    return {"basic": basic, "allowance": allowance, "absence": absence, "bonus": int(bonus_minor), "earnings": earnings,
            "overtime": overtime_total, "overtime_by_kind": overtime, "night_allowance": night_allowance, "gross": gross,
            "si_employee": si_employee, "si_employer": si_employer, "tax": tax, "other_deductions": other, "net": net}
