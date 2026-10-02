"""Payroll (WP-H6): HR calculates pay, Mizan books the entries; neither does the other's job.

What is kept here, in its own database `data/payroll.db` (never in the registry, never in the journal's folds, but inside every
backup as an attachment): salary profiles (effective-dated), monthly adjustments, pay runs with one result per employee, and an
outbox of what was sent to Mizan. The registry stays free of money; the audit holds counts and totals, never one person's pay.

A pay run goes calculated -> approved (by someone other than the person who calculated it, bound to the fingerprint they saw)
-> sent to Mizan as `hr.payroll_period.v1` (totals per cost centre and account key, no names) -> optionally reversed. A run that is
approved or reversed never changes; correcting a month means reversing it and calculating a new run.

Rights: hr.payroll.read (see runs and slips), hr.payroll.write (salary profiles and adjustments), hr.payroll.run (calculate),
hr.payroll.approve (approve, send, reverse).
Standard library only.
"""

import hashlib
import json
import os
import threading
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime, timedelta, timezone

import eco_contract
import eco_signing

from . import payroll_calc as calc
from . import people_ops as ops
from .canonical import canonical
from .eco_link import KEY_TEXT, KeyStore
from .journal import SharedConnection
from .registry import RegistryError
from .scheduling import Schedule

FILE = "payroll.db"
KIND = "hr.payroll_period.v1"
PERIOD = ops.PERIOD
ADJUSTMENT_KINDS = ("unpaid_absence_days", "bonus", "deduction")
STATES = ("calculated", "approved", "reversed")
TARGET_FILE, MIZAN_KEY_FILE, MIZAN_ENTROPY = "payroll_target.json", "mizan.key", b"HR-System eco.mizan_key"
ACCOUNT_KEYS = ("gross_earnings", "overtime", "night_allowance", "employer_social_insurance", "employee_social_insurance", "salary_tax", "other_deductions", "net_payable")


class PayrollError(RegistryError):
    pass


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def month_bounds(period):
    if not PERIOD.match(str(period or "")):
        raise PayrollError("period.format", "the period is a month YYYY-MM")
    first = date(int(period[:4]), int(period[5:7]), 1)
    nxt = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


class PayrollStore:
    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, FILE)
        self.lock = threading.RLock()
        self.db = SharedConnection(self.path, self.lock)
        self.db.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS pay_profile (
              employee_code TEXT NOT NULL, effective_from TEXT NOT NULL, basic_minor INTEGER NOT NULL, allowance_minor INTEGER NOT NULL,
              insurable_minor INTEGER NOT NULL, cost_center TEXT, note TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL,
              PRIMARY KEY (employee_code, effective_from));
            CREATE TABLE IF NOT EXISTS pay_adjustment (
              id INTEGER PRIMARY KEY AUTOINCREMENT, period TEXT NOT NULL, employee_code TEXT NOT NULL, kind TEXT NOT NULL, value INTEGER NOT NULL,
              note TEXT, created_by TEXT NOT NULL, created_at TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS pay_period (
              period TEXT NOT NULL, run INTEGER NOT NULL, status TEXT NOT NULL, fingerprint TEXT NOT NULL, pay_date TEXT NOT NULL,
              headcount INTEGER NOT NULL, hours TEXT NOT NULL, lines TEXT NOT NULL, totals TEXT NOT NULL, warnings TEXT NOT NULL,
              calculated_by TEXT NOT NULL, calculated_at TEXT NOT NULL, approved_by TEXT, approved_at TEXT, reversed_by TEXT, reversed_at TEXT,
              reverse_reason TEXT, PRIMARY KEY (period, run));
            CREATE TABLE IF NOT EXISTS pay_result (
              period TEXT NOT NULL, run INTEGER NOT NULL, employee_code TEXT NOT NULL, cost_center TEXT NOT NULL, data TEXT NOT NULL,
              PRIMARY KEY (period, run, employee_code));
            CREATE TABLE IF NOT EXISTS pay_outbox (
              period TEXT NOT NULL, run INTEGER NOT NULL, version INTEGER NOT NULL, envelope TEXT NOT NULL, state TEXT NOT NULL,
              detail TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (period, run, version));
        """)

    def close(self):
        self.db.close()


# ---------------------------------------------------------------------------------------------------- the calculation
def cost_center_of(reg, employee, profile):
    """The profile's own cost centre, else the one written on the employee's org unit or the nearest unit above it."""
    if profile.get("cost_center"):
        return profile["cost_center"]
    position = reg.by_id("position", employee["position_id"]) if employee.get("position_id") else None
    unit = reg.by_id("org_unit", position["org_unit_id"]) if position else None
    seen = 0
    while unit and seen < 8:
        cc = (unit.get("attrs") or {}).get("cost_center")
        if cc:
            return cc
        unit = reg.by_id("org_unit", unit["parent_id"]) if unit.get("parent_id") else None
        seen += 1
    return None


def _is_night(start_time, pol):
    t = str(start_time or "")[11:16] if "T" in str(start_time or "") else str(start_time or "")[:5]
    lo, hi = pol["night_from"], pol["night_to"]
    return bool(t) and (t >= lo or t < hi) if lo > hi else bool(t) and lo <= t < hi


def calculate(reg, store, period, leave_days, rules=None):
    """The whole month for everyone who has a pay profile. Pure given the registry, the store and the rules: the same data always
    gives the same results and the same fingerprint. Returns (results, warnings, summary)."""
    first, last = month_bounds(period)
    first_s, last_s, days_in_month = first.isoformat(), last.isoformat(), (last - first).days + 1
    pol = ops.policy(reg.overtime_policy)
    premium = {"day": pol["premium_day_bp"], "night": pol["premium_night_bp"], "rest_day": pol["rest_day_premium_bp"], "holiday": pol["holiday_premium_bp"]}
    plan = Schedule(reg)
    overtime = {p["employee"]: p["minutes"] for p in ops.overtime_for_period(reg, period)["employees"]}
    adjustments = {}
    for a in store.db.execute("SELECT employee_code, kind, value FROM pay_adjustment WHERE period = ? AND removed = 0", (period,)):
        adjustments.setdefault(a["employee_code"], {}).setdefault(a["kind"], 0)
        adjustments[a["employee_code"]][a["kind"]] += int(a["value"])
    leave_types = {t["id"]: t for t in reg.list("leave_type")}
    leaves = {}
    for r in reg.list("leave_request"):
        if r["status"] == "approved" and str(r["from_date"]) <= last_s and str(r["to_date"]) >= first_s:
            leaves.setdefault(r["employee_id"], []).append(r)
    profiles = {}
    for p in store.db.execute("SELECT * FROM pay_profile WHERE effective_from <= ? ORDER BY employee_code, effective_from", (last_s,)):
        profiles[p["employee_code"]] = dict(p)                       # the latest effective one wins
    results, warnings, missing = [], [], []
    for emp in reg.list("employee"):
        hire, end = emp.get("hire_date") or "0000-01-01", emp.get("termination_date") or "9999-12-31"
        if hire > last_s or end < first_s or emp["worker_type"] == "Agency":
            continue
        prof = profiles.get(emp["code"])
        if not prof:
            if emp["employment_status"] != "Terminated":
                missing.append(emp["code"])
            continue
        start, stop = max(hire, first_s), min(end, last_s)
        in_post = (date.fromisoformat(stop) - date.fromisoformat(start)).days + 1
        cc = cost_center_of(reg, emp, prof)
        if not cc:
            raise PayrollError("pay.cost_center", f"{emp['code']} has no cost centre: write it on the pay profile or on the employee's org unit")
        unpaid, work_days, night_days, paid_minutes = 0, 0, 0, 0
        for r in leaves.get(emp["id"], []):
            lt = leave_types.get(r["leave_type_id"])
            if lt is not None and str(lt.get("paid", 1)) == "0":
                unpaid += leave_days(emp["id"], max(r["from_date"], start), min(r["to_date"], stop))
        d = date.fromisoformat(start)
        while d.isoformat() <= stop:
            sched = plan.day(emp["id"], d.isoformat())
            if sched["status"] == "work":
                work_days += 1
                paid_minutes += sched["paid_minutes"]
                if _is_night(sched.get("start"), pol):
                    night_days += 1
            d += timedelta(days=1)
        adj = adjustments.get(emp["code"], {})
        unpaid += adj.get("unpaid_absence_days", 0)
        slip = calc.payslip(prof, (in_post, days_in_month), overtime.get(emp["code"], {}), premium, max(0, night_days - adj.get("unpaid_absence_days", 0)),
                            pol["night_allowance_bp"], unpaid, adj.get("bonus", 0), adj.get("deduction", 0), rules)
        if slip["net"] < 0:
            raise PayrollError("pay.negative_net", f"{emp['code']}: the deductions are more than the pay for {period}; correct the adjustments first")
        if emp["employment_status"] in ("Suspended",):
            warnings.append(f"{emp['code']} is suspended and is paid in full: decide before approving")
        results.append({"employee_code": emp["code"], "cost_center": cc, "in_post_days": in_post, "days_in_month": days_in_month, "scheduled_days": work_days,
                        "scheduled_minutes": paid_minutes, "night_days": night_days, "unpaid_days": unpaid,
                        "overtime_minutes": {k: int(overtime.get(emp["code"], {}).get(k, 0)) for k in ops.OT_KINDS}, **slip})
    if missing:
        warnings.append(f"{len(missing)} employee(s) in post have no pay profile and are not paid: {', '.join(missing[:8])}{' ...' if len(missing) > 8 else ''}")
    results.sort(key=lambda r: r["employee_code"])
    # the plain scheduled days, minutes of overtime, and the totals per cost centre and account key
    by_cc, hours = {}, {"regular": 0, "overtime_day": 0, "overtime_night": 0}
    minutes = {"regular": 0, "overtime_day": 0, "overtime_night": 0}
    for r in results:
        b = by_cc.setdefault(r["cost_center"], {k: 0 for k in ACCOUNT_KEYS})
        b["gross_earnings"] += r["earnings"]
        b["overtime"] += r["overtime"]
        b["night_allowance"] += r["night_allowance"]
        b["employer_social_insurance"] += r["si_employer"]
        b["employee_social_insurance"] += r["si_employee"]
        b["salary_tax"] += r["tax"]
        b["other_deductions"] += r["other_deductions"]
        b["net_payable"] += r["net"]
        minutes["regular"] += r["scheduled_minutes"]
        m = r["overtime_minutes"]
        minutes["overtime_night"] += m["night"]
        minutes["overtime_day"] += m["day"] + m["rest_day"] + m["holiday"]
    hours = {k: v // 60 for k, v in minutes.items()}
    lines = [{"cost_center": cc, "account_key": k, "amount_minor": v} for cc in sorted(by_cc) for k, v in by_cc[cc].items() if v > 0]
    for cc, b in by_cc.items():              # the entry Mizan will book must balance: costs = deductions + net pay (proved here, again there)
        debit = b["gross_earnings"] + b["overtime"] + b["night_allowance"] + b["employer_social_insurance"]
        credit = b["employee_social_insurance"] + b["employer_social_insurance"] + b["salary_tax"] + b["other_deductions"] + b["net_payable"]
        if debit != credit:
            raise PayrollError("pay.unbalanced", f"cost centre {cc}: costs {debit} against liabilities {credit}")
    totals = {k: sum(b[k] for b in by_cc.values()) for k in ACCOUNT_KEYS}
    summary = {"period": period, "headcount": len(results), "hours": hours, "lines": lines, "totals": totals,
               "fingerprint": hashlib.sha256(canonical({"period": period, "rules": dict(calc.DEFAULT_RULES, **(rules or {})), "premium": premium,
                                                         "results": results}).encode("utf-8")).hexdigest()}
    return results, warnings, summary


# ---------------------------------------------------------------------------------------------------- the service side
class PayrollMixin:
    def _payroll(self):
        if getattr(self, "_payroll_store", None) is None:
            self._payroll_store = PayrollStore(self.data_dir)
        return self._payroll_store

    def _employee_or_refuse(self, code):
        emp = self.registry.get("employee", code)
        if not emp:
            raise PayrollError("employee.not_found", f"employee {code} does not exist")
        return emp

    def _locked_months(self):
        """Months that have an approved run: their pay is final (a profile change must start later)."""
        return {r["period"] for r in self._payroll().db.execute("SELECT period FROM pay_period WHERE status = 'approved'")}

    # ---- salary profiles
    def pay_profiles(self, user, ip=None):
        self.require(user, "hr.payroll.read", ip, "payroll.profiles")
        rows = self._payroll().db.execute("SELECT * FROM pay_profile ORDER BY employee_code, effective_from")
        return [dict(r) for r in rows]

    def set_pay_profile(self, user, employee_code, fields, ip=None):
        self.require(user, "hr.payroll.write", ip, "payroll.profile")
        self._employee_or_refuse(employee_code)
        store = self._payroll()
        try:
            eff = str(fields.get("effective_from") or self.registry.today())
            date.fromisoformat(eff)
            money = {k: int(fields.get(k, 0)) for k in ("basic_minor", "allowance_minor")}
            insurable = int(fields.get("insurable_minor", money["basic_minor"]))
        except (TypeError, ValueError):
            raise PayrollError("pay.number", "amounts are whole piastres and the date is YYYY-MM-DD") from None
        if min(money.values()) < 0 or insurable < 0 or money["basic_minor"] <= 0 or max(money.values()) > 10**11:
            raise PayrollError("pay.range", "the basic wage must be above zero and no amount negative")
        cc = (fields.get("cost_center") or "").strip() or None
        if cc and len(cc) > 64:
            raise PayrollError("pay.cost_center", "the cost centre code is too long")
        if eff[:7] in self._locked_months():
            raise PayrollError("pay.locked", f"{eff[:7]} has an approved pay run: a salary change must start in a later month")
        with store.lock:
            store.db.execute("INSERT INTO pay_profile (employee_code, effective_from, basic_minor, allowance_minor, insurable_minor, cost_center, note, created_by, created_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(employee_code, effective_from) DO UPDATE SET basic_minor = excluded.basic_minor, "
                             "allowance_minor = excluded.allowance_minor, insurable_minor = excluded.insurable_minor, cost_center = excluded.cost_center, "
                             "note = excluded.note, created_by = excluded.created_by, created_at = excluded.created_at",
                             (employee_code, eff, money["basic_minor"], money["allowance_minor"], insurable, cc, fields.get("note"), user["code"], _now()))
            store.db.commit()
        self.journal.audit("activity", "payroll.profile.saved", user["code"], {"employee": employee_code, "effective_from": eff}, ip)   # no amounts
        return {"employee": employee_code, "effective_from": eff}

    # ---- monthly adjustments (what attendance and HR decisions add to the month)
    def pay_adjustments(self, user, period, ip=None):
        self.require(user, "hr.payroll.read", ip, "payroll.adjustments")
        month_bounds(period)
        return [dict(r) for r in self._payroll().db.execute("SELECT * FROM pay_adjustment WHERE period = ? AND removed = 0 ORDER BY id", (period,))]

    def add_pay_adjustment(self, user, period, employee_code, kind, value, note=None, ip=None):
        self.require(user, "hr.payroll.write", ip, "payroll.adjustment")
        month_bounds(period)
        self._employee_or_refuse(employee_code)
        if kind not in ADJUSTMENT_KINDS:
            raise PayrollError("pay.adjustment_kind", f"an adjustment is one of {', '.join(ADJUSTMENT_KINDS)}")
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise PayrollError("pay.number", "the value is a whole number (days, or piastres)") from None
        if value <= 0 or value > (31 if kind == "unpaid_absence_days" else 10**10):
            raise PayrollError("pay.range", "the value must be above zero" + (" and at most 31 days" if kind == "unpaid_absence_days" else ""))
        if period in self._locked_months():
            raise PayrollError("pay.locked", f"{period} has an approved pay run: reverse it before adjusting")
        store = self._payroll()
        with store.lock:
            cur = store.db.execute("INSERT INTO pay_adjustment (period, employee_code, kind, value, note, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                                   (period, employee_code, kind, value, note, user["code"], _now()))
            store.db.commit()
            new_id = store.db.execute("SELECT MAX(id) AS id FROM pay_adjustment").fetchone()["id"]
        self.journal.audit("activity", "payroll.adjustment.added", user["code"], {"period": period, "employee": employee_code, "kind": kind}, ip)
        return {"id": new_id}

    def remove_pay_adjustment(self, user, adjustment_id, ip=None):
        self.require(user, "hr.payroll.write", ip, "payroll.adjustment:remove")
        store = self._payroll()
        row = store.db.execute("SELECT period FROM pay_adjustment WHERE id = ? AND removed = 0", (int(adjustment_id),)).fetchone()
        if not row:
            raise PayrollError("adjustment.not_found", f"adjustment {adjustment_id} does not exist")
        if row["period"] in self._locked_months():
            raise PayrollError("pay.locked", f"{row['period']} has an approved pay run: reverse it before adjusting")
        with store.lock:
            store.db.execute("UPDATE pay_adjustment SET removed = 1 WHERE id = ?", (int(adjustment_id),))
            store.db.commit()
        self.journal.audit("activity", "payroll.adjustment.removed", user["code"], {"id": int(adjustment_id)}, ip)
        return {"id": int(adjustment_id)}

    # ---- runs
    def pay_calculate(self, user, period, ip=None):
        """Calculate (or recalculate) the month. A run that is still only calculated is replaced; an approved one is final."""
        self.require(user, "hr.payroll.run", ip, "payroll.calculate")
        first, last = month_bounds(period)
        if last.isoformat() > self.registry.today():
            raise PayrollError("period.open", f"{period} has not ended yet: pay is calculated after the last day of the month")
        store = self._payroll()
        results, warnings, summary = calculate(self.registry, store, period, self.leave_days)
        if not results:
            raise PayrollError("pay.empty", f"nobody has a pay profile in {period}: enter the salary profiles first")
        with store.lock:
            latest = store.db.execute("SELECT run, status FROM pay_period WHERE period = ? ORDER BY run DESC LIMIT 1", (period,)).fetchone()
            if latest and latest["status"] == "approved":
                raise PayrollError("pay.locked", f"{period} run {latest['run']} is approved: reverse it first, then calculate again")
            run = latest["run"] if latest and latest["status"] == "calculated" else (latest["run"] + 1 if latest else 1)
            store.db.execute("DELETE FROM pay_result WHERE period = ? AND run = ?", (period, run))
            store.db.execute("DELETE FROM pay_period WHERE period = ? AND run = ? AND status = 'calculated'", (period, run))
            store.db.execute("INSERT INTO pay_period (period, run, status, fingerprint, pay_date, headcount, hours, lines, totals, warnings, calculated_by, calculated_at) "
                             "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                             (period, run, "calculated", summary["fingerprint"], last.isoformat(), summary["headcount"], json.dumps(summary["hours"]), json.dumps(summary["lines"]),
                              json.dumps(summary["totals"]), json.dumps(warnings), user["code"], _now()))
            for r in results:
                store.db.execute("INSERT INTO pay_result (period, run, employee_code, cost_center, data) VALUES (?,?,?,?,?)",
                                 (period, run, r["employee_code"], r["cost_center"], json.dumps(r, sort_keys=True)))
            store.db.commit()
        self.journal.audit("activity", "payroll.calculated", user["code"], {"period": period, "run": run, "headcount": summary["headcount"],
                                                                            "fingerprint": summary["fingerprint"]}, ip)
        return self._run_view(period, run)

    def _run_view(self, period, run):
        row = self._payroll().db.execute("SELECT * FROM pay_period WHERE period = ? AND run = ?", (period, run)).fetchone()
        if not row:
            raise PayrollError("run.not_found", f"there is no pay run {period} #{run}")
        out = dict(row)
        for k in ("hours", "lines", "totals", "warnings"):
            out[k] = json.loads(out[k])
        sent = self._payroll().db.execute("SELECT version, state, detail FROM pay_outbox WHERE period = ? AND run = ? ORDER BY version DESC LIMIT 1", (period, run)).fetchone()
        out["delivery"] = dict(sent) if sent else None
        return out

    def pay_runs(self, user, ip=None):
        """Every run with its totals (no names, no per-person amounts)."""
        self.require(user, "hr.payroll.read", ip, "payroll.runs")
        rows = self._payroll().db.execute("SELECT period, run FROM pay_period ORDER BY period DESC, run DESC")
        return [{k: v for k, v in self._run_view(r["period"], r["run"]).items() if k != "lines"} for r in rows]

    def pay_run(self, user, period, run, ip=None):
        self.require(user, "hr.payroll.read", ip, "payroll.run")
        return self._run_view(period, int(run))

    def pay_slips(self, user, period, run, employee_code=None, ip=None):
        """One person's slip, or every slip of the run, for the people who may see pay."""
        self.require(user, "hr.payroll.read", ip, "payroll.slips")
        self._run_view(period, int(run))
        sql, args = "SELECT data FROM pay_result WHERE period = ? AND run = ?", [period, int(run)]
        if employee_code:
            sql, args = sql + " AND employee_code = ?", args + [employee_code]
        slips = [json.loads(r["data"]) for r in self._payroll().db.execute(sql + " ORDER BY employee_code", tuple(args))]
        self.journal.audit("activity", "payroll.slips.viewed", user["code"], {"period": period, "run": int(run), "employee": employee_code}, ip)
        return slips

    def pay_approve(self, user, period, run, fingerprint, pay_date=None, ip=None):
        """Approve exactly the figures the approver looked at (the fingerprint), by someone other than the person who calculated them."""
        self.require(user, "hr.payroll.approve", ip, "payroll.approve")
        store = self._payroll()
        view = self._run_view(period, int(run))
        if view["status"] != "calculated":
            raise PayrollError("pay.state", f"{period} run {run} is {view['status']}, not waiting for approval")
        if view["calculated_by"] == user["code"]:
            raise PayrollError("sod.own_payroll", "a pay run is approved by someone else than the person who calculated it")
        if fingerprint != view["fingerprint"]:
            raise PayrollError("pay.stale", "the run changed since you looked at it: open it again and approve what you see")
        if view["warnings"] and any("suspended" in w for w in view["warnings"]):
            raise PayrollError("pay.warnings", "the run has warnings that need a decision first: " + view["warnings"][0])
        _, last = month_bounds(period)
        pay_day = str(pay_date or last.isoformat())
        try:
            date.fromisoformat(pay_day)
        except ValueError:
            raise PayrollError("date.format", "the pay date is YYYY-MM-DD") from None
        with store.lock:
            store.db.execute("UPDATE pay_period SET status = 'approved', approved_by = ?, approved_at = ?, pay_date = ? WHERE period = ? AND run = ? AND status = 'calculated'",
                             (user["code"], _now(), pay_day, period, int(run)))
            self._stage(period, int(run), 1, "approved")
            store.db.commit()
        self.journal.audit("activity", "payroll.approved", user["code"], {"period": period, "run": int(run), "fingerprint": fingerprint}, ip)
        self.pay_deliver(user=None)
        return self._run_view(period, int(run))

    def pay_reverse(self, user, period, run, reason, ip=None):
        self.require(user, "hr.payroll.approve", ip, "payroll.reverse")
        if not str(reason or "").strip():
            raise PayrollError("pay.reason", "say why the run is reversed")
        view = self._run_view(period, int(run))
        if view["status"] != "approved":
            raise PayrollError("pay.state", f"{period} run {run} is {view['status']}: only an approved run can be reversed")
        store = self._payroll()
        with store.lock:
            store.db.execute("UPDATE pay_period SET status = 'reversed', reversed_by = ?, reversed_at = ?, reverse_reason = ? WHERE period = ? AND run = ?",
                             (user["code"], _now(), str(reason).strip()[:300], period, int(run)))
            self._stage(period, int(run), 2, "reversed")
            store.db.commit()
        self.journal.audit("activity", "payroll.reversed", user["code"], {"period": period, "run": int(run)}, ip)
        self.pay_deliver(user=None)
        return self._run_view(period, int(run))

    # ---- Mizan
    def _target(self):
        """Where the approved totals go: the address in data/payroll_target.json and the key in data/node/mizan.key (set by an administrator),
        else ECO_MIZAN_URL and ECO_MIZAN_KEY from the environment (tests, scripts). Empty when neither is set."""
        url, key = "", ""
        try:
            with open(os.path.join(self.data_dir, TARGET_FILE), encoding="utf-8") as fh:
                url = str(json.load(fh).get("url") or "")
        except (FileNotFoundError, ValueError):
            pass
        key = KeyStore(self.data_dir, MIZAN_KEY_FILE, MIZAN_ENTROPY).load() or ""
        return (url or os.environ.get("ECO_MIZAN_URL", "")).strip().rstrip("/"), (key or os.environ.get("ECO_MIZAN_KEY", "")).strip()

    def pay_target(self, user, ip=None):
        self.require(user, "admin.settings.manage", ip, "payroll.target")
        url, key = self._target()
        return {"url": url, "key_set": bool(key)}

    def set_pay_target(self, user, url, key, ip=None):
        """The address of Mizan and the key it made for HR (write-only: never returned, logged, audited or put in a backup)."""
        self.require(user, "admin.settings.manage", ip, "payroll.target:set")
        url = str(url or "").strip().rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")) or len(url) > 300 or " " in url:
            raise PayrollError("target.url", "the address of Mizan starts with http:// or https://")
        if key not in (None, ""):
            if not isinstance(key, str) or not KEY_TEXT.match(key):
                raise PayrollError("target.key", "the key is 1-512 printable characters without spaces (made by Mizan, shown once)")
            KeyStore(self.data_dir, MIZAN_KEY_FILE, MIZAN_ENTROPY).save(key)
        path = os.path.join(self.data_dir, TARGET_FILE)
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump({"url": url}, fh)
        os.replace(path + ".tmp", path)
        self.journal.audit("security", "payroll.target.set", user["code"], {"url": url, "key_changed": key not in (None, "")}, ip)
        return {"url": url, "key_set": bool(self._target()[1])}

    def _stage(self, period, run, version, status):
        """Put the event in the outbox with its exact bytes (a resend sends the same event, so Mizan sees a duplicate, never a second booking)."""
        view = self._run_view(period, run)
        company = self.registry.company_id
        gid = str(uuid.uuid5(uuid.UUID(company), f"hr:payroll_period:{period}:{run}"))
        code = f"PAY-{period}-R{run}"
        body = {"id": gid, "code": code, "version": version, "origin": {"app": "hr", "type": "payroll_period", "key": code}, "period": period, "run": run,
                "currency": "EGP", "pay_date": view["pay_date"], "status": status, "lines": view["lines"], "headcount": view["headcount"], "hours": view["hours"]}
        subject = f"payroll_period/{gid}"
        envelope = {"specversion": "1.0", "id": str(uuid.uuid5(uuid.UUID(company), f"{KIND}:{gid}:{version}")), "source": f"eco://{company}/hr/{os.environ.get('ECO_NODE', 'hr-main')}",
                    "type": KIND, "subject": subject, "time": _now(), "datacontenttype": "application/json", "ecoseq": version, "ecocorrelation": subject, "data": body}
        problems = eco_contract.validate_event(envelope)
        if problems:
            raise PayrollError("pay.contract", f"the event would not pass the contract: {problems[:2]}")
        self._payroll().db.execute("INSERT OR REPLACE INTO pay_outbox (period, run, version, envelope, state, detail, updated_at) VALUES (?,?,?,?,?,?,?)",
                                   (period, run, version, json.dumps(envelope, ensure_ascii=False), "pending", None, _now()))

    def pay_deliver(self, user=None, ip=None):
        """Send what is waiting to Mizan (ECO_MIZAN_URL, ECO_MIZAN_KEY), signed. Nothing waiting or no address: nothing happens, and the
        runs stay approved here either way. A refusal is kept with its reason and is not retried until a person looks."""
        if user is not None:
            self.require(user, "hr.payroll.approve", ip, "payroll.deliver")
        url, key = self._target()
        store = self._payroll()
        waiting = store.db.execute("SELECT period, run, version, envelope FROM pay_outbox WHERE state = 'pending' ORDER BY period, run, version").fetchall()
        report = {"waiting": len(waiting), "delivered": 0, "rejected": 0, "stopped_by": None}
        if not waiting:
            return report
        if not url or not key:
            report["stopped_by"] = "the address and key of Mizan are not set (Settings, or ECO_MIZAN_URL and ECO_MIZAN_KEY): the runs wait here"
            return report
        for row in waiting:
            body = json.dumps({"events": [json.loads(row["envelope"])]}, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(url + "/eco/v1/inbox", data=body, method="POST", headers={
                "content-type": "application/json", "x-eco-key": key, **eco_signing.signature_headers(key, "POST", "/eco/v1/inbox", body)})
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    answer = json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                report["stopped_by"] = f"Mizan answered {exc.code}"
                if exc.code < 500 and exc.code != 429:
                    self._mark(row, "rejected", f"HTTP {exc.code}: {exc.read()[:200]!r}")
                    report["rejected"] += 1
                    continue
                break
            except (urllib.error.URLError, OSError) as exc:
                report["stopped_by"] = f"Mizan unreachable: {exc}"
                break
            result = (answer.get("results") or [{}])[0]
            if result.get("result") in ("applied", "unchanged", "stale", "duplicate"):
                self._mark(row, "delivered", result.get("result"))
                report["delivered"] += 1
            else:
                self._mark(row, "rejected", f"{result.get('code')}: {result.get('message')}")
                report["rejected"] += 1
        return report

    def _mark(self, row, state, detail):
        store = self._payroll()
        with store.lock:
            store.db.execute("UPDATE pay_outbox SET state = ?, detail = ?, updated_at = ? WHERE period = ? AND run = ? AND version = ?",
                             (state, detail, _now(), row["period"], row["run"], row["version"]))
            store.db.commit()

    def pay_retry(self, user, period, run, ip=None):
        """After a person has looked at a refusal (for example an unknown cost centre in Mizan): send the same event again."""
        self.require(user, "hr.payroll.approve", ip, "payroll.retry")
        store = self._payroll()
        with store.lock:
            store.db.execute("UPDATE pay_outbox SET state = 'pending', detail = NULL WHERE period = ? AND run = ? AND state = 'rejected'", (period, int(run)))
            store.db.commit()
        return self.pay_deliver(user=None)
