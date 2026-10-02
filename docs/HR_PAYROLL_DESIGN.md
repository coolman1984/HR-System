# Payroll — detailed design (first version BUILT on 2026-10-02, see the box below)

> **Built 2026-10-02 (owner's order: sample data, the trial runs on this laptop, "change the rules").** The gate in §2 was lifted for
> the trial; what was built is a deliberately smaller first version of this design, in `hr_core/payroll_calc.py` and
> `hr_core/payroll.py`, tested by `TEST_HR_PAYROLL.py`:
> * **Data:** not four registry entities but one separate database `data/payroll.db` (profiles with effective dates, monthly
>   adjustments, runs, one result per employee, an outbox), a backup attachment; the registry stays free of money.
> * **Rights:** `hr.payroll.read|write|run|approve` instead of `payroll.read|run|approve|admin`.
> * **Calculation:** basic and allowances prorated by days in post, unpaid leave and adjustments, overtime from approved requests
>   at basic / 240 with the company's premiums, night allowance from the shift plan, insurance, salary tax, martyrs' fund.
>   Attendance reaches pay only as adjustments, because the locked engine takes spreadsheets (§2.1 is still open).
> * **Screens:** `PAY2010` runs, `PAY1010` salary profiles, `PAY1020` adjustments (payslip printing is not built).
> * **Still owed before real salaries:** the five points of §2 (above all 5: a trial month calculated by hand by the owner's
>   accountant), the rules and rates confirmed by a payroll accountant, an attendance source other than a spreadsheet.
>
> The rest of this document is the original design, kept as the plan for what is owed.

Status of the original plan: **Design only** (owner's decision 2026-09-28: shifts and skills now, payroll designed now and built only after
attendance, leave and overtime are bound to the registry employee and stable — `CLAUDE.md` "Never", design §6-7).
This document turns `docs/HR_SYSTEM_DESIGN.md` §6 into a buildable plan, so the build can start the day the gate opens.

## 1. One truth for pay
| Who | Does | Never does |
|---|---|---|
| HR-System | Holds pay elements per employee, calculates a period, keeps every result (confidential), publishes ONE accounting summary per period | Posts journal entries, keeps accounts |
| Mizan | Receives the summary and books ONE balanced entry per period and cost centre | Stores employees, calculates pay, sees a person's pay |
| GMES | Nothing (it never sees pay) | — |

## 2. Gate before building (all must be green)
1. Attendance days bound to the registry employee (phase 4): no attendance row matched by an uploaded file only.
2. Leave requests, approval and balances as an HR module (today leave lives inside the locked engine).
3. Overtime: requests, approval and actuals derived from the planned schedule (phase 3, built) against attendance.
4. The planned-vs-attended comparison shows no unexplained "no record" days for a full trial month.
5. A trial month calculated by hand by the owner's accountant, to compare with.

## 3. Data (new registry entities, journal-signed like every other record)
| Entity | Fields | Rules |
|---|---|---|
| `pay_element` | code, name, kind (`earning` / `deduction` / `employer_contribution`), taxable, insurable, account_key | catalogue; codes never reused |
| `employee_pay` | employee, element, amount_minor (integer piastres) or rate_bp (basis points), valid_from, valid_to | effective dated exactly like shift assignments: a started line keeps its amount, a change is a new line from a date |
| `pay_rule` | code, formula kind (`fixed`, `per_day`, `per_hour`, `overtime_multiplier`, `absence_deduction`, `tax_table`, `insurance`), parameters | versioned by date; the rule used by a period is frozen into the period |
| `pay_period` | code (`2026-10`), from, to, state (`open` → `calculated` → `approved` → `sent` → `closed`), run number | a sent period never changes; a correction is a NEW adjustment period |
| `pay_result` | period, employee, element, basis (days / minutes / amount), amount_minor, explanation | written only by a calculation run; never edited by hand |

**Money is integer minor units** (piastres), rates in basis points, quantities as integers — the ecosystem rule; nothing
is rounded silently: every rounding step is a named rule with its own result line ("rounding", amount).

## 4. Calculation (deterministic and repeatable)
Inputs frozen at the start of a run: the period's approved attendance days, approved leave, approved overtime, the
planned schedule (`hr_core/scheduling.py`), `employee_pay` lines valid in the period, and the `pay_rule` versions.
Same inputs → same results, byte for byte (a test recalculates a closed period and compares the fingerprint).
Order: earnings (fixed, per day, per hour) → overtime (planned vs attended minutes × multiplier) → absence and lateness
deductions (from the comparison verdicts, never guessed) → social insurance (Egyptian table, versioned) → income tax
(versioned table) → net. Each line carries its explanation (which days, which minutes, which rule version).

## 5. What leaves HR
`hr.payroll_period.v1` (to be added in GMES `packages/eco-contracts` first, then copied to `eco_schemas/`):
period code, company, run number, currency, and totals **per cost centre × account key** (gross earnings, employer
contributions, deductions payable, net payable). **No names, no per-person amounts.** Identity:
UUIDv5(company, "hr:payroll_period:<period>:<run>") — a resend books nothing twice (Mizan's link checks the id, as the
GMES link does with `eco:<event-id>`). Cost centres come from HR's org units (department `cost_center_code`); the
mapping to Mizan accounts lives in the link, not in HR.

## 6. Security
New rights: `payroll.read` (see results), `payroll.run` (calculate), `payroll.approve` (approve and send; must not be
the person who ran it — four eyes), `payroll.admin` (elements, rules). Pay data is in its own database file
(`payroll.db`), backed up and rehearsed like the others, and never in logs, the audit detail or GMES.

## 7. Screens (built from the same kit)
PAY1010 Pay elements · PAY1020 Employee pay (effective dated, like SHF2010) · PAY2010 Period run (conditions → Calculate →
grid of employees × totals → detail with every explained line) · PAY2020 Approve and send · PAY3010 Payslips (print).

## 8. Tests that must exist before the first real period
Hand-calculated reference employees (monthly, daily, hourly, night overtime, absence, mid-month hire and leave);
determinism (recalculate = same fingerprint); a sent period cannot change; adjustment period; four-eyes approval;
no per-person amount in the published summary; the Mizan entry balances (end to end against a real Mizan, like GMES's
link); planted bugs for every rule.

## 9. Design input from Mizan (2026-09-28, owner's order: take Mizan's good ideas) — still design only
Mizan (`coolman1984/Accounting-sys`) already holds a working Egyptian payroll engine that HR should reuse **as rules and
test vectors, not as code** (it is TypeScript; HR is standard-library Python) when the gate in §2 is green:
- **Salary tax, Law 7/2024:** the brackets, the high-income rule above EGP 600,000 a year, rounding down to EGP 10
  (`Accounting-sys/apps/server/src/modules/payroll/engine.ts`, `egyptSalaryTax()`), and the law's worked examples that
  Mizan's tests use: copy them into HR's reference employees (§8) so both products give the same tax to the piaster.
- **Social insurance:** employee 11 %, employer 18.75 % of the insurable wage, between the yearly floor and ceiling
  (`Accounting-sys/apps/server/src/contracts/egypt.ts`; Mizan's own note: the 2026 limits must be confirmed against the
  NOSI circular before use).
- **Pay elements** as Mizan models them: country-neutral components with `floor`, `insurable` and a tax rule
  (`Accounting-sys/docs/DECISIONS.md` ADR-017); money kept to the piaster (Mizan's lesson: rounding to whole pounds by
  hand disagrees with the law's examples).
- **Advisor checks** for payroll (insurable wage outside the limits, tax or insurance due): add them to HR's Advisor
  (`ADV1010`) when payroll exists.
- **Consequence for Mizan:** once HR calculates pay, Mizan's own `payroll` module (employees + calculation) becomes
  "payroll posting from HR" (ADR-022 in GMES); until then the two must not both be used for the same company.
