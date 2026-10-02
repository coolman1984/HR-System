"""The HR modules and the editions a customer can buy (mechano, as in Mizan).

status: built = shipped and tested; planned = designed, not built; design_only = architecture only,
never part of a sellable edition until built (payroll).
"""

MODULES = {
    "kernel": {"depends_on": [], "status": "built", "what": "company, organisation, jobs, positions, employee registry, journal, audit, eco publisher"},
    "attendance": {"depends_on": ["kernel"], "status": "built", "what": "the migrated attendance application (locked engine), daily import, dashboard, history"},
    "leave": {"depends_on": ["attendance"], "status": "built", "what": "leave requests linked to attendance days (inside the migrated engine); leave types, balances and approvals in the registry"},
    "recruitment": {"depends_on": ["shifts"], "status": "built", "what": "headcount plan, requisitions approved by someone else, candidates, hiring with contract and onboarding, contract end"},
    "shifts": {"depends_on": ["kernel"], "status": "built", "what": "shifts, working calendars, effective-dated assignments, day changes and swaps, the planned schedule compared with attendance"},
    "overtime": {"depends_on": ["shifts", "attendance"], "status": "built", "what": "overtime requests, approval by someone else, caps, actuals against approvals, the figures payroll will need"},
    "skills": {"depends_on": ["kernel"], "status": "built", "what": "skills catalogue, qualifications with levels and expiry, published for manufacturing's station check"},
    "training": {"depends_on": ["skills"], "status": "built", "what": "courses and sessions whose passes grant or renew qualifications"},
    "discipline": {"depends_on": ["shifts", "attendance"], "status": "built", "what": "the company's penalty schedule, violations proposed from attendance, decisions by the right person (days, never money)"},
    "payroll": {"depends_on": ["attendance", "leave", "overtime", "shifts"], "status": "built", "what": "salary profiles, monthly pay runs (earnings, overtime, insurance, salary tax, net) approved by a second person, totals sent to Mizan"},
}

EDITIONS = {
    "attendance": ["kernel", "attendance"],
    "attendance_leave": ["kernel", "attendance", "leave"],
    "full": ["kernel", "attendance", "leave", "shifts", "recruitment", "overtime", "skills", "training", "payroll"],
}


def resolve(edition):
    """Modules of an edition with every dependency, refusing what is not built or cannot be sold."""
    wanted, out = list(EDITIONS[edition]), []

    def visit(name, path):
        if name in out:
            return
        if name in path:
            raise ValueError(f"module cycle: {' -> '.join(path + [name])}")
        spec = MODULES[name]
        if spec["status"] == "design_only":
            raise ValueError(f"module {name} is design-only and cannot be part of an edition")
        for dep in spec["depends_on"]:
            if dep not in wanted and dep not in out:
                raise ValueError(f"edition {edition}: module {name} needs {dep}, which the edition does not include")
            visit(dep, path + [name])
        out.append(name)

    for name in wanted:
        visit(name, [])
    return out


def available(edition):
    """Modules of the edition that are actually built today (planned ones are listed, not pretended)."""
    return [m for m in resolve(edition) if MODULES[m]["status"] == "built"]
