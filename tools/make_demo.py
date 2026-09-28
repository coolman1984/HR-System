"""Builds a complete DEMO installation of HR-System with realistic, synthetic data, so every screen, rule and
warning can be tried (Nile Precision Industries, an Egyptian electronics factory).

    python tools/make_demo.py [folder] [--reset]        default folder: <repo>/../HR-Demo

Everything goes through the product's own code: the installation (Product.install), the workbook importer, the
service with its permission checks and rules, the attendance engine over HTTP, and the backups. Nothing is written
into the tables directly, so what the screens show is what the product itself produced.

Data: the organisation and the employees come from the synthetic dataset in inputs/hr-factory-synthetic-dataset
(clean baseline). Shifts, calendars, assignments, day changes, skills, qualifications, users and three weeks of
attendance are generated here with a fixed random seed (the same data every time). A few records are made wrong
ON PURPOSE so that every check of the Advisor has something to show (listed in DELIBERATE_PROBLEMS).

The demo is a separate installation (its own folder, HR_HOME) and never touches a real one. --reset deletes the
folder first, and only a folder this tool created (it carries the marker file .hr-demo).
"""
import http.cookiejar
import io
import json
import os
import random
import shutil
import sys
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta

ROOT = os.environ.get("HR_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
if os.path.join(ROOT, "vendor.zip") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "vendor.zip"))  # openpyxl for the attendance workbooks
DATASET = os.path.join(ROOT, "inputs", "hr-factory-synthetic-dataset", "01_CLEAN_BASELINE")
MARKER = ".hr-demo"
ADMIN = ("admin", "Mariam Fouad", "123")  # demo sign-in; shorter than the product allows, so written directly after install
INSTALL_PASSWORD = "Demo-2026!admin"
PASSWORD = "Demo-2026!pass"
TODAY = date.today()
HISTORY_FROM = date(2026, 6, 1) if TODAY > date(2026, 7, 1) else TODAY - timedelta(days=60)
R = random.Random(2026)

DELIBERATE_PROBLEMS = [
    "two people share one position (position_shared)", "four people without a position (unplaced)",
    "three people without a hire date (no_hire_date)", "two people past their termination date still Active (left_not_closed)",
    "two terminated people without a termination date (terminated_no_date)", "three people report to a manager who left (manager_gone)",
    "a planned section with no positions (empty_units)", "two terminated people still on the plan (terminated_planned)",
    "six active people without a regular shift (not_planned)", "expired and expiring qualifications (qual_expired, qual_expiring)",
    "a profile that holds two rights that should be separated (sod)", "two users who still have their first password (must_change)",
]


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ------------------------------------------------------------------ the folder
def prepare(folder, reset):
    folder = os.path.abspath(folder)
    if os.path.exists(folder) and os.listdir(folder):
        if not reset:
            sys.exit(f"{folder} already exists. Run with --reset to rebuild the demo (only a demo folder is deleted).")
        if not os.path.isfile(os.path.join(folder, MARKER)):
            sys.exit(f"{folder} is not a demo folder made by this tool (no {MARKER} file): refusing to delete it.")
        shutil.rmtree(folder)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, MARKER), "w", encoding="utf-8") as fh:
        fh.write(f"HR-System demo installation, made by tools/make_demo.py on {datetime.now().isoformat(timespec='seconds')}\n")
    return folder


# ------------------------------------------------------------------ reference data
SHIFTS = [  # code, name, start, end, break, grace
    ("A", "Morning shift", "07:00", "15:00", 30, 10), ("B", "Evening shift", "15:00", "23:00", 30, 10),
    ("C", "Night shift", "23:00", "07:00", 30, 10), ("ADM", "Office hours", "08:30", "16:30", 45, 15),
    ("LD", "Long day (12 h)", "07:00", "19:00", 60, 10), ("RMD", "Ramadan office hours", "09:00", "15:00", 0, 15),
]
# Egyptian public holidays 2026 (lunar dates approximate - confirm with the official decree each year)
HOLIDAYS_2026 = ["2026-01-07", "2026-01-25", "2026-03-20", "2026-03-21", "2026-03-22", "2026-04-12", "2026-04-13", "2026-04-25",
                 "2026-05-01", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-06-16", "2026-06-30", "2026-07-23",
                 "2026-08-25", "2026-10-06"]
CALENDARS = [("FAC", "Factory - Friday rest", "FRI", HOLIDAYS_2026), ("OFC", "Offices - Friday and Saturday rest", "FRI,SAT", HOLIDAYS_2026),
             ("SEC", "Security - no fixed rest day", "", [])]
SKILLS = [  # code, name, category, validity months (None = does not expire)
    ("SMT-PRN", "SMT stencil printing", "SMT line", 24), ("SPI", "Solder paste inspection (SPI)", "Inspection", 24),
    ("PNP", "Pick & place machine operation", "SMT line", 24), ("REFLOW", "Reflow oven operation", "SMT line", 24),
    ("AOI", "Automated optical inspection (AOI)", "Inspection", 24), ("ASSY", "Manual assembly", "Assembly", None),
    ("TORQUE", "Torque control", "Assembly", 12), ("ESD", "ESD handling", "Safety", 12), ("FCT", "Functional test", "Test", 24),
    ("VIS", "Visual inspection (IPC-A-610)", "Inspection", 24), ("PACK", "Packing", "Logistics", None),
    ("FORK", "Forklift licence", "Logistics", 24), ("SOLDER", "Hand soldering (IPC J-STD-001)", "Assembly", 24),
    ("REPAIR", "Rework and repair", "Assembly", 36), ("SAMPLING", "Quality sampling (AQL)", "Quality", 36),
    ("CHANGEOVER", "Line changeover", "SMT line", None), ("SETUP", "Machine setup", "Maintenance", None),
    ("5S", "5S workplace organisation", "Quality", None), ("LOTO", "Lock-out / tag-out", "Safety", 12),
    ("FIRSTAID", "First aid", "Safety", 24),
]
USERS = [  # user, name, profile, keeps first password
    ("mona.hassan", "Mona Hassan", "hr_officer", False), ("karim.adel", "Karim Adel", "shift_planner", False),
    ("salma.nabil", "Salma Nabil", "skills_coordinator", False), ("omar.farouk", "Omar Farouk", "auditor", False),
    ("nour.samir", "Nour Samir", "viewer", False), ("ahmed.it", "Ahmed Tarek", "it_admin", False),
    ("hany.supervisor", "Hany Mahmoud", "hr_supervisor", False), ("yara.new", "Yara Mostafa", "viewer", True),
    ("tamer.new", "Tamer Ali", "shift_planner", True),
    ("hesham.kamal", "Hesham Kamal", "line_manager", False),          # the plant director: decides the new manager's violations
    ("karim.abdelaziz", "Karim Abdelaziz", "production_manager", False),  # the new manager of the story
]
READS = ["hr.org.read", "hr.employees.read", "hr.attendance.read", "hr.shifts.read", "hr.skills.read"]
PROFILES = {  # created as the Profiles screen would (templates), plus one that breaks the separation of duties on purpose
    "shift_planner": ("Shift planner", READS + ["hr.shifts.write"]),
    "skills_coordinator": ("Training and skills coordinator", READS + ["hr.skills.write"]),
    "it_admin": ("IT administrator", ["hr.org.read", "admin.users.manage", "admin.audit.read", "admin.system.read", "admin.settings.manage", "admin.backup.manage"]),
    "hr_supervisor": ("HR supervisor (all in one)", READS + ["hr.employees.write", "hr.org.write", "admin.users.manage"]),
    "line_manager": ("Line manager", READS + ["hr.discipline.read", "hr.discipline.approve"]),
    "production_manager": ("Production manager", READS + ["hr.shifts.write", "hr.discipline.read", "hr.discipline.approve"]),
}
OFFICE_WORDS = ("hr", "human", "finance", "account", "admin", "it ", "information", "purchas", "procure", "sales", "legal", "planning", "engineering office", "management")


def iso(d):
    return d.isoformat()


# ------------------------------------------------------------------ build
def build(folder):
    os.environ["HR_HOME"] = folder
    from hr_core import importer
    from hr_core.app import Product
    from hr_core.home import Home

    product = Product(Home(folder))
    product.home.set(language="en", backup_hours=6, autostart=False)
    product.install({"source": "local", "code": "NILE", "name": "Nile Precision Industries"}, {"username": ADMIN[0], "display_name": ADMIN[1], "password": INSTALL_PASSWORD})
    svc = product.service
    from hr_core.auth import hash_password
    svc.auth.commit(ADMIN[0], "demo: admin sign-in set to the demo password", [{"entity": "user", "code": ADMIN[0], "fields": {"pw": hash_password(ADMIN[2]), "must_change": 0}, "expected_ver": svc.auth._get("user", ADMIN[0])["ver"]}])
    _, admin = svc.login(ADMIN[0], ADMIN[2])
    reg = svc.registry
    log("installation made")

    # 1. organisation and employees: the importer, exactly as a customer would load their workbooks
    report = importer.import_workbooks(reg, os.path.join(DATASET, "01_Organization_Factory.xlsx"), os.path.join(DATASET, "02_Employee_Master.xlsx"), ADMIN[0])
    log(f"imported: {report['created']} records, {len(report['rejected'])} rejected by the rules (kept out, as the importer does)")
    live = lambda e: [r for r in reg.list(e) if not r["deleted"]]  # noqa: E731
    save = lambda e, code, f, ver=None: svc.save(admin, e, code, f, ver)["row"]  # noqa: E731
    units, positions, jobs = {u["id"]: u for u in live("org_unit")}, {p["id"]: p for p in live("position")}, {j["id"]: j for j in live("job")}
    emps = sorted(live("employee"), key=lambda e: e["code"])
    unit_of = lambda e: units.get((positions.get(e["position_id"]) or {}).get("org_unit_id"))  # noqa: E731

    def is_office(e):
        u, names = unit_of(e), []
        while u:
            names.append((u.get("name") or "").lower())
            u = units.get(u.get("parent_id"))
        job = (jobs.get((positions.get(e["position_id"]) or {}).get("job_id")) or {}).get("title", "").lower()
        return any(w in " ".join(names + [job]) for w in OFFICE_WORDS)

    # managers: the holder of the position a person's position reports to
    holder = {e["position_id"]: e for e in emps if e["position_id"] and e["employment_status"] != "Terminated"}
    n = 0
    for e in emps:
        boss = holder.get((positions.get(e["position_id"]) or {}).get("reports_to_id"))
        if boss and boss["id"] != e["id"] and not e["manager_id"]:
            save("employee", e["code"], {"manager_id": boss["id"]}, e["ver"]); n += 1
    # the rest: in each unit the longest-serving person leads the others; a unit's lead reports to the parent unit's lead
    people = [e for e in sorted(live("employee"), key=lambda e: (e["hire_date"] or "9999", e["code"])) if e["employment_status"] != "Terminated"]
    lead = {}
    for e in people:
        u = unit_of(e)
        if u and u["id"] not in lead:
            lead[u["id"]] = e

    def lead_above(u):
        u = units.get(u.get("parent_id"))
        while u and u["id"] not in lead:
            u = units.get(u.get("parent_id"))
        return lead.get(u["id"]) if u else None
    for e in sorted(live("employee"), key=lambda e: e["code"]):
        u = unit_of(e)
        if e["manager_id"] or not u:
            continue
        boss = lead[u["id"]] if lead.get(u["id"]) and lead[u["id"]]["id"] != e["id"] else lead_above(u)
        if boss and boss["id"] != e["id"]:
            save("employee", e["code"], {"manager_id": boss["id"]}, e["ver"]); n += 1
    log(f"managers linked: {sum(1 for e in live('employee') if e['manager_id'])} of {len(live('employee'))} people have one")

    # 2. shifts and calendars
    for code, name, start, end, brk, grace in SHIFTS:
        save("shift", code, {"name": name, "start_time": start, "end_time": end, "break_minutes": brk, "grace_minutes": grace})
    for code, name, rest, hol in CALENDARS:
        save("work_calendar", code, {"name": name, "rest_days": rest, "holidays": ",".join(hol)})
    shift_id = {s["code"]: s["id"] for s in live("shift")}
    cal_id = {c["code"]: c["id"] for c in live("work_calendar")}

    # 3. deliberate problems in the register (each one is a check of the Advisor)
    emps = sorted(live("employee"), key=lambda e: e["code"])
    active = [e for e in emps if e["employment_status"] == "Active"]
    terminated = [e for e in emps if e["employment_status"] == "Terminated"]
    R.shuffle(active)
    pick = iter(active)
    a, b = next(pick), next(pick)
    save("employee", a["code"], {"position_id": b["position_id"]}, a["ver"])                                   # position_shared
    unplaced = [next(pick) for _ in range(4)]
    for e in unplaced:
        save("employee", e["code"], {"position_id": None, "hire_date": iso(TODAY - timedelta(days=R.randint(3, 20)))}, e["ver"])   # new hires, unplaced
    for e in [next(pick) for _ in range(3)]:
        save("employee", e["code"], {"hire_date": None}, e["ver"])                                              # no_hire_date
    left = [next(pick) for _ in range(2)]
    for e in left:
        save("employee", e["code"], {"termination_date": iso(TODAY - timedelta(days=R.randint(5, 25)))}, e["ver"])  # left_not_closed
    for e in terminated[:2]:
        save("employee", e["code"], {"termination_date": None}, e["ver"])                                       # terminated_no_date
    gone = terminated[2] if len(terminated) > 2 else None
    if gone:
        for e in [next(pick) for _ in range(3)]:
            now = next(r for r in reg.list("employee") if r["code"] == e["code"])
            save("employee", e["code"], {"manager_id": gone["id"]}, now["ver"])                                  # manager_gone
    dept = next(u for u in units.values() if u["type"] == "department")
    save("org_unit", "SEC-ROBOT", {"type": "section", "name": "Robotics cell (planned for 2027)", "parent_id": dept["id"]})   # empty_units
    log("deliberate problems placed")

    # 4. regular assignments (history from HISTORY_FROM), temporary cover, day changes, swaps
    emps = sorted(live("employee"), key=lambda e: e["code"])
    staff = [e for e in emps if e["employment_status"] != "Terminated" or (e["termination_date"] or "") >= iso(HISTORY_FROM)]
    skip = {e["id"] for e in [x for x in emps if x["employment_status"] == "Active" and x["position_id"]][-6:]}   # not_planned
    still_planned = {e["id"] for e in terminated[3:5]}                                                          # terminated_planned
    rot = 0
    regular = {}
    for e in staff:
        if e["id"] in skip or e["id"] in {u["id"] for u in unplaced}:
            continue
        start = max(HISTORY_FROM, date.fromisoformat(e["hire_date"]) if e["hire_date"] else HISTORY_FROM)
        if start > TODAY + timedelta(days=30):
            continue
        office = is_office(e)
        sh, cal = ("ADM", "OFC") if office else (("A", "B", "C")[rot % 3], "FAC")
        if not office:
            rot += 1
        if not office and rot % 23 == 0:
            sh, cal = "LD", "SEC"
        end = None
        if e["employment_status"] == "Terminated" and e["id"] not in still_planned and e["termination_date"]:
            end = e["termination_date"]
            if end < iso(start):
                continue
        code = f"{e['code']}-{iso(start)}-R"
        save("shift_assignment", code, {"employee_id": e["id"], "shift_id": shift_id[sh], "calendar_id": cal_id[cal], "kind": "regular", "valid_from": iso(start), "valid_to": end,
                                        "note": "Moved to the night rotation" if sh == "C" and rot % 11 == 0 else None})
        regular[e["id"]] = (sh, cal)
    for e in terminated[3:5]:  # still planned although they left: the Advisor flags it
        if e["id"] not in regular:
            save("shift_assignment", f"{e['code']}-{iso(HISTORY_FROM)}-R", {"employee_id": e["id"], "shift_id": shift_id["A"], "calendar_id": cal_id["FAC"], "kind": "regular", "valid_from": iso(HISTORY_FROM)})
    factory = [e for e in emps if regular.get(e["id"], ("ADM",))[0] in ("A", "B", "C") and e["employment_status"] == "Active"]
    R.shuffle(factory)
    notes = ["Covering the AOI station during the audit", "Training on line 3", "Night cover while a colleague is on leave", "Ramp-up of the new model", "Inventory count week"]
    for i, e in enumerate(factory[:10]):
        other = {"A": "B", "B": "C", "C": "A"}[regular[e["id"]][0]]
        s = TODAY - timedelta(days=R.randint(2, 10)) if i < 6 else TODAY + timedelta(days=R.randint(3, 9))
        f = max(s, TODAY) + (timedelta(days=R.randint(3, 12)) if i % 3 else timedelta(days=25))
        save("shift_assignment", f"{e['code']}-{iso(s)}-T", {"employee_id": e["id"], "shift_id": shift_id[other], "calendar_id": cal_id["FAC"], "kind": "temporary",
                                                           "valid_from": iso(s), "valid_to": iso(f), "note": notes[i % len(notes)]})
    reasons = ["Doctor appointment", "Machine maintenance - moved to the night shift", "Covering an absent colleague", "Family event", "Training day at the supplier", "Exam day"]
    for i, e in enumerate(factory[10:24]):
        d = TODAY + timedelta(days=1 + i % 9)
        save("roster_override", f"{e['code']}-{iso(d)}", {"employee_id": e["id"], "work_date": iso(d), "shift_id": None if i % 3 == 0 else shift_id[R.choice(["A", "B", "C"])],
                                                        "reason": reasons[i % len(reasons)]})
    swaps = 0
    for x, y in zip(factory[24:32:2], factory[25:33:2]):
        d = TODAY + timedelta(days=2 + swaps)
        while d.strftime("%a").upper()[:3] == "FRI":
            d += timedelta(days=1)
        try:
            svc.swap(admin, iso(d), x["code"], y["code"], "Swap agreed with the line supervisor"); swaps += 1
        except Exception as exc:  # noqa: BLE001 - a swap the rules refuse is simply not made
            log(f"swap skipped: {exc}")
    log(f"assignments: {len(regular)} regular, 10 temporary, 14 day changes, {swaps} swaps")

    # 5. skills and qualifications (a natural mix of valid, expiring, expired and planned certifications)
    for code, name, cat, months in SKILLS:
        save("skill", code, {"name": name, "category": cat, "validity_months": months})
    skill = {s["code"]: s for s in live("skill")}
    by_cat = {}
    for code, _, cat, _ in SKILLS:
        by_cat.setdefault(cat, []).append(code)
    q = 0
    for i, e in enumerate(factory + [x for x in emps if regular.get(x["id"], ("",))[0] == "LD"]):
        cats = R.sample(["SMT line", "Inspection", "Assembly", "Test", "Logistics", "Quality"], k=R.randint(1, 3)) + ["Safety"]
        for cat in cats:
            for code in R.sample(by_cat[cat], k=min(len(by_cat[cat]), R.randint(1, 2))):
                months = skill[code]["validity_months"]
                roll = R.random()
                if months and roll < 0.07:
                    cert = TODAY - timedelta(days=months * 30 + R.randint(5, 90))           # expired
                elif months and roll < 0.16:
                    cert = TODAY - timedelta(days=months * 30 - R.randint(3, 28))           # expires within 30 days
                elif roll > 0.985:
                    cert = TODAY + timedelta(days=R.randint(2, 20))                          # certification planned
                else:
                    cert = TODAY - timedelta(days=R.randint(20, 600))
                level = R.choices([1, 2, 3, 4], weights=[2, 4, 5, 2])[0]
                ev = R.choice(["Practical test on line 2", "Supplier training certificate", "Internal assessment", "IPC certificate", "Supervisor sign-off"])
                try:
                    save("employee_skill", f"{e['code']}-{code}", {"employee_id": e["id"], "skill_id": skill[code]["id"], "level": level, "certified_on": iso(cert), "evidence": ev}); q += 1
                except Exception:  # noqa: BLE001 - same person and skill twice
                    pass
    log(f"skills: {len(SKILLS)}, qualifications: {q}")

    # 6. profiles and users
    for code, (name, perms) in PROFILES.items():
        svc.save_profile(admin, code, name, perms)
    for user, name, prof, first in USERS:
        svc.create_user(admin, user, name, PASSWORD, prof)
        if not first:
            svc.auth.commit(ADMIN[0], "demo: password already changed", [{"entity": "user", "code": user, "fields": {"must_change": 0}, "expected_ver": svc.auth._get("user", user)["ver"]}])
    log(f"users: {len(USERS) + 1}, profiles added: {len(PROFILES)}")
    # a mistaken record in the Recycle Bin, to show delete and restore
    dup = save("employee", "E900001", {"preferred_name": "Ahmed (duplicate entry)", "employment_status": "Active", "hire_date": iso(TODAY - timedelta(days=2))})
    svc.delete(admin, "employee", "E900001", dup["ver"])
    story = new_manager(svc, admin, factory)
    return product, svc, admin, regular, story


# ------------------------------------------------------------------ the story: a new production manager, from hiring to today
HIRED = date(2026, 6, 15)
MANAGER_CODE = "E000900"
# his own attendance story (dates before today only): late arrivals, one absence, one leave, one excused late arrival
STORY_LATE = {"2026-06-29": 22, "2026-07-08": 35, "2026-07-21": 18, "2026-08-25": 41, "2026-09-15": 25}
STORY_ABSENT = {"2026-08-10"}
STORY_LEAVE = ("2026-08-17", "2026-08-20")
STORY_DECISIONS = {  # violation day -> (day of the decision, decision or "waive", note)
    "2026-06-29": ("2026-07-01", "warning", "First late arrival; discussed with him"),
    "2026-07-08": ("2026-07-12", "deduct:0.25", ""),
    "2026-07-21": ("2026-07-24", "deduct:0.5", "Third late arrival within 30 days"),
    "2026-08-10": ("2026-08-13", "deduct:1", "Investigation 2026-08-12: no excuse given for the absence"),
    "2026-08-25": ("2026-08-27", "warning", ""),
    "2026-09-15": ("2026-09-17", "waive", "Traffic accident on the ring road, confirmed by the police report"),
}


def new_manager(svc, admin, factory):
    """Hires Karim Abdelaziz as production manager on HIRED and lives his first months through the product's own
    operations, each by the person who would do it in real life."""
    reg = svc.registry
    save = lambda e, code, f, ver=None, who=None: svc.save(who or admin, e, code, f, ver)["row"]  # noqa: E731
    live = lambda e: [r for r in reg.list(e) if not r["deleted"]]  # noqa: E731
    units = live("org_unit")
    dept = next((u for u in units if u["type"] == "department" and "production" in (u["name"] or "").lower()), None) or next(u for u in units if u["type"] == "department")
    site = next(u for u in units if u["type"] == "site")
    job = save("job", "JOB-PM", {"title": "Production Manager", "family": "Operations", "level": "M2", "critical": 1})
    pos = save("position", "POS-PM-01", {"job_id": job["id"], "org_unit_id": dept["id"], "status": "Filled"})
    seniors = sorted([e for e in live("employee") if e["employment_status"] == "Active" and e["hire_date"]], key=lambda e: e["hire_date"])
    director = seniors[0]
    karim = save("employee", MANAGER_CODE, {"preferred_name": "Karim Abdelaziz", "legal_name": "كريم عبد العزيز محمود", "legacy_number": "EMP-2026-0415",
                                            "employment_status": "Active", "worker_type": "Regular", "hire_date": iso(HIRED), "home_site_id": site["id"],
                                            "position_id": pos["id"], "manager_id": director["id"]})
    team = [e for e in factory if e["employment_status"] == "Active"][:12]
    for e in team:
        now = next(r for r in reg.list("employee") if r["code"] == e["code"])
        save("employee", e["code"], {"manager_id": karim["id"]}, now["ver"])
    shifts = {s["code"]: s["id"] for s in live("shift")}
    cals = {c["code"]: c["id"] for c in live("work_calendar")}
    save("shift_assignment", f"{MANAGER_CODE}-{iso(HIRED)}-R", {"employee_id": karim["id"], "shift_id": shifts["ADM"], "calendar_id": cals["OFC"], "kind": "regular", "valid_from": iso(HIRED),
                                                              "note": "Office hours; visits the lines at shift change"})
    save("shift_assignment", f"{MANAGER_CODE}-2026-08-03-T", {"employee_id": karim["id"], "shift_id": shifts["C"], "calendar_id": cals["FAC"], "kind": "temporary", "valid_from": "2026-08-03",
                                                            "valid_to": "2026-08-14", "note": "Night cover during the ramp-up of the new SMT line"})
    _, salma = svc.login("salma.nabil", PASSWORD)  # the training coordinator certifies him
    skills = {s["code"]: s["id"] for s in live("skill")}
    for code, day, level, evidence in (("ESD", "2026-06-18", 3, "Induction training"), ("LOTO", "2026-06-20", 3, "Safety induction, practical test"),
                                       ("FIRSTAID", "2026-06-25", 2, "Red Crescent course"), ("5S", "2026-07-05", 4, "Leads the 5S audit of line 2"),
                                       ("SAMPLING", "2026-07-20", 3, "AQL workshop")):
        save("employee_skill", f"{MANAGER_CODE}-{code}", {"employee_id": karim["id"], "skill_id": skills[code], "level": level, "certified_on": day, "evidence": evidence}, None, salma)
    # his attendance from the day he joined (the planned days, in slices of 90 days)
    rows, first = [], HIRED
    while first < TODAY:
        last = min(first + timedelta(days=89), TODAY - timedelta(days=1))
        for d in svc.schedule(admin, iso(first), iso(last), MANAGER_CODE):
            day = d["work_date"]
            if d["status"] != "work":
                continue
            if day in STORY_ABSENT:
                rows.append([f"TIM02-K{len(rows):05d}", MANAGER_CODE, date.fromisoformat(day), d["shift_code"], None, None, 0, "Absent", 0, 0, 0]); continue
            if STORY_LEAVE[0] <= day <= STORY_LEAVE[1]:
                rows.append([f"TIM02-K{len(rows):05d}", MANAGER_CODE, date.fromisoformat(day), d["shift_code"], None, None, 0, "Leave", 0, 0, 0]); continue
            late = STORY_LATE.get(day, 0)
            start, end = datetime.fromisoformat(d["start"]), datetime.fromisoformat(d["end"])
            t_in = start + (timedelta(minutes=late) if late else -timedelta(minutes=R.randint(5, 20)))
            t_out = end + timedelta(minutes=R.randint(0, 45))  # a manager often stays late
            worked = max(0, int((t_out - t_in).total_seconds() // 60) - 45)
            rows.append([f"TIM02-K{len(rows):05d}", MANAGER_CODE, date.fromisoformat(day), d["shift_code"], t_in.strftime("%H:%M"), t_out.strftime("%H:%M"), worked, "Present", late, 0, 0])
        first = last + timedelta(days=1)
    leave = [["TIM07-K0001", MANAGER_CODE, "Annual", date.fromisoformat(STORY_LEAVE[0]), date.fromisoformat(STORY_LEAVE[1]), "Approved", False]]
    log(f"story: {MANAGER_CODE} Karim Abdelaziz hired {iso(HIRED)} as production manager, team of {len(team)}, {len(rows)} attendance days")
    return {"id": karim["id"], "team": [e["id"] for e in team], "attendance": rows, "leave": leave}


def discipline(product, svc, story):
    """The penalty schedule, the violations proposed from attendance by the HR officer, and the decisions: the plant
    director decides the new manager's own violations on their dates; the new manager decides some of his team's."""
    reg = svc.registry
    _, admin = svc.login(ADMIN[0], ADMIN[2])
    _, mona = svc.login("mona.hassan", PASSWORD)
    _, hesham = svc.login("hesham.kamal", PASSWORD)
    _, karim = svc.login("karim.abdelaziz", PASSWORD)
    for code, f in (("LATE", {"name": "Late arrival", "violation": "late", "threshold_minutes": 15, "window_days": 30, "steps": "warning,deduct:0.25,deduct:0.5,deduct:1", "active": 1}),
                    ("EARLY", {"name": "Leaving before the end of the shift", "violation": "early_leave", "threshold_minutes": 15, "window_days": 30, "steps": "warning,deduct:0.5,deduct:1", "active": 1}),
                    ("ABS", {"name": "Absence without leave", "violation": "absence", "window_days": 365, "steps": "deduct:1,deduct:2,deduct:3,investigation", "active": 1}),
                    ("NOREC", {"name": "No attendance record", "violation": "no_record", "window_days": 30, "steps": "warning,deduct:0.25", "active": 0}),
                    ("MISC", {"name": "Breaking the clean-room rules", "violation": "misconduct", "window_days": 365, "steps": "warning,deduct:1,deduct:2,investigation", "active": 1})):
        svc.save(admin, "penalty_rule", code, f)
    rows = product.attendance.engine.current_rows(force=True)
    made = 0
    first = HIRED
    while first < TODAY:
        last = min(first + timedelta(days=89), TODAY - timedelta(days=1))
        made += len(svc.propose_violations(mona, iso(first), iso(last), rows)["proposed"])
        first = last + timedelta(days=1)
    # the director decides Karim's violations, each a few days after it happened
    real_today = reg.today
    decided = 0
    for v in sorted([v for v in reg.list("violation") if v["employee_id"] == story["id"]], key=lambda v: v["work_date"]):
        plan = STORY_DECISIONS.get(v["work_date"])
        if not plan or plan[0] >= iso(TODAY):
            continue
        reg.today = lambda d=plan[0]: d
        fields = {"status": "waived", "note": plan[2]} if plan[1] == "waive" else {"status": "approved", "decision": plan[1], "note": plan[2]}
        svc.save(hesham, "violation", v["code"], fields, v["ver"]); decided += 1
    reg.today = real_today
    # Karim decides part of his team's violations; the rest waits for him (the Advisor shows them)
    team = [v for v in reg.list("violation") if v["employee_id"] in story["team"] and v["status"] == "proposed"]
    for i, v in enumerate(sorted(team, key=lambda v: v["work_date"])[:6]):
        fields = {"status": "waived", "note": "Bus of the company was late that morning"} if i == 2 else {"status": "approved", "decision": v["proposed"],
                  "note": "Investigation: agreed with the worker" if (v["proposed"] or "").startswith("deduct:") and float(v["proposed"][7:]) > 1 else ""}
        try:
            svc.save(karim, "violation", v["code"], fields, v["ver"]); decided += 1
        except Exception as exc:  # noqa: BLE001 - a rule of the law refused it: leave it proposed
            log(f"decision left open ({v['code']}): {exc}")
    # a misconduct seen on the line, entered by hand by the HR officer, waiting for Karim
    m = next(e for e in reg.list("employee") if e["id"] == story["team"][0])
    d = TODAY - timedelta(days=2)
    svc.save(mona, "violation", f"{m['code']}-{iso(d)}-MISC", {"employee_id": m["id"], "rule_id": reg.get("penalty_rule", "MISC")["id"], "work_date": iso(d), "status": "proposed",
                                                                "occurrence": 1, "proposed": "warning", "source": "manual", "note": "Entered the SMT clean room without the ESD smock"})
    # his planning work: a day change and a swap for his team
    by_id = {e["id"]: e for e in reg.list("employee")}
    team_codes = [by_id[i]["code"] for i in story["team"]]  # same order as story["team"]
    for k in range(1, 6):
        day = TODAY + timedelta(days=k)
        try:
            svc.save(karim, "roster_override", f"{team_codes[1]}-{iso(day)}", {"employee_id": story["team"][1], "work_date": iso(day), "shift_id": reg.get("shift", "C")["id"],
                                                                             "reason": "Line 3 changeover: moved to the night shift"})
            break
        except Exception:  # noqa: BLE001 - try the next day
            continue
    for k in range(2, 9):
        try:
            svc.swap(karim, iso(TODAY + timedelta(days=k)), team_codes[2], team_codes[3], "Agreed between them, approved by Karim"); break
        except Exception:  # noqa: BLE001 - a day where the swap is possible
            continue
    log(f"discipline: 5 rules, {made} violations proposed from attendance, {decided} decided")


# ------------------------------------------------------------------ attendance: three weeks through the locked engine, over HTTP
def attendance(product, svc, admin, regular, story):
    from openpyxl import Workbook
    first, last = TODAY - timedelta(days=21), TODAY - timedelta(days=1)
    plan = [d for d in svc.schedule(admin, iso(first), iso(last)) if d["employee_id"] in regular]
    emps = {e["id"]: e for e in svc.registry.list("employee")}
    leave_people = R.sample(sorted({d["employee_id"] for d in plan if d["status"] == "work"}), k=12)
    leaves, on_leave = [], set()
    for i, pid in enumerate(leave_people):
        s = first + timedelta(days=R.randint(0, 15))
        f = s + timedelta(days=R.randint(0, 4))
        kind = R.choice(["Annual", "Annual", "Sick", "Casual", "Mission"])
        status = "Approved" if i < 10 else "Rejected"
        leaves.append([f"TIM07-{i + 1:05d}", emps[pid]["code"], kind, s, f, status, False])
        if status == "Approved":
            on_leave |= {(pid, iso(s + timedelta(days=k))) for k in range((f - s).days + 1)}
    att, roster = [], []
    n = 0
    for d in plan:
        e = emps[d["employee_id"]]
        day = d["work_date"]
        if d["status"] == "work":
            roster.append([f"SCH02-{len(roster) + 1:06d}", e["code"], date.fromisoformat(day), d["shift_code"], "Published"])
        n += 1
        aid = f"TIM02-{n:06d}"
        if d["status"] != "work":
            if R.random() < 0.02:  # came in on a rest day (overtime)
                att.append([aid, e["code"], date.fromisoformat(day), None, "08:00", "14:00", 360, "Present", 0, 0, 360])
            continue
        start = datetime.fromisoformat(d["start"])
        paid = d.get("paid_minutes") or 450
        if (d["employee_id"], day) in on_leave:
            att.append([aid, e["code"], date.fromisoformat(day), d["shift_code"], None, None, 0, "Leave", 0, 0, 0]); continue
        r = R.random()
        if r < 0.025:
            att.append([aid, e["code"], date.fromisoformat(day), d["shift_code"], None, None, 0, "Absent", 0, 0, 0]); continue
        if r < 0.04:
            continue  # no punch at all: "no record"
        late = R.randint(16, 45) if r < 0.065 else R.randint(0, 6)   # about 2.5 % of the days late, 1.5 % leaving early
        early = R.randint(16, 60) if 0.065 <= r < 0.08 else 0
        ot = R.choice([60, 90, 120]) if r > 0.93 else 0
        t_in = start - timedelta(minutes=R.randint(3, 15)) + timedelta(minutes=late)
        t_out = datetime.fromisoformat(d["end"]) - timedelta(minutes=early) + timedelta(minutes=ot + R.randint(0, 8))
        worked = max(0, int((t_out - t_in).total_seconds() // 60) - 30)
        att.append([aid, e["code"], date.fromisoformat(day), d["shift_code"], t_in.strftime("%H:%M"), t_out.strftime("%H:%M"), worked, "Present", late if late > 10 else 0, early, ot])
    att += story["attendance"]
    leaves += story["leave"]
    for k in range(3):  # badges the register does not know (a visitor card, a contractor): "unknown attendance people"
        att.append([f"TIM02-9{k:05d}", f"E9{k:05d}", last, "A", "07:05", "15:02", 447, "Present", 0, 0, 0])

    def book(sheet, blanks, headers, rows):
        wb = Workbook()
        ws = wb.active
        ws.title = sheet
        for _ in range(blanks):
            ws.append(["Nile Precision Industries - time and attendance export"])
        ws.append(headers)
        for row in rows:
            ws.append(row)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    files = {"attendance": ("attendance.xlsx", book("TIM_02_DailyAttendance", 2, ["Attendance_ID", "Employee_ID", "Work_Date", "Scheduled_Shift_ID", "First_In", "Last_Out",
                                                                                   "Worked_Minutes", "Attendance_Status", "Late_Minutes", "Early_Leave_Minutes", "Overtime_Eligible_Minutes"], att)),
             "employee": ("employee.xlsx", book("EMP_01_EmployeeMaster", 1, ["Employee_ID", "Employment_Status", "Hire_Date"],
                                                [[e["code"], e["employment_status"], date.fromisoformat(e["hire_date"]) if e["hire_date"] else None] for e in emps.values() if not e["deleted"]])),
             "roster": ("roster.xlsx", book("SCH_02_EmployeeRosters", 2, ["Roster_ID", "Employee_ID", "Work_Date", "Shift_ID", "Roster_Status"], roster)),
             "leave": ("leave.xlsx", book("TIM_07_LeaveRequests", 1, ["Leave_Request_ID", "Employee_ID", "Leave_Type", "Start_Date", "End_Date", "Approval_Status", "Cancellation_Flag"], leaves))}

    server = product.serve(host="127.0.0.1", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = json.dumps({"username": ADMIN[0], "password": ADMIN[2]}).encode()
    opener.open(urllib.request.Request(base + "/api/login", data=body, method="POST", headers={"Content-Type": "application/json"}), timeout=60).read()
    boundary = "NileDemoBoundary2026"
    parts = []
    for field, (name, content) in files.items():
        parts += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n'.encode(),
                  b"Content-Type: application/octet-stream\r\n\r\n", content, b"\r\n"]
    parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(parts)
    res = opener.open(urllib.request.Request(base + "/api/upload_multi", data=data, method="POST",
                                             headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(data))}), timeout=300).read()
    server.shutdown()
    server.server_close()
    out = json.loads(res.decode() or "{}")
    log(f"attendance: {len(att)} rows, {len(roster)} roster days, {len(leaves)} leave requests uploaded ({', '.join(f'{k}={v}' for k, v in list(out.items())[:4])})")


def main(argv):
    folder = next((a for a in argv if not a.startswith("--")), os.path.join(os.path.dirname(ROOT), "HR-Demo"))
    folder = prepare(folder, "--reset" in argv)
    log(f"building the demo in {folder}")
    product, svc, admin, regular, story = build(folder)
    try:
        attendance(product, svc, admin, regular, story)
        discipline(product, svc, story)
    finally:
        made = svc.backups.create(ADMIN[0], "manual")
        log(f"backup made: {made['name']}")
        product.close()
    print(json.dumps({"folder": folder, "sign_in": {"user": ADMIN[0], "password": ADMIN[2]}, "other_users_password": PASSWORD,
                      "users": [u[0] for u in USERS], "deliberate_problems": DELIBERATE_PROBLEMS}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
