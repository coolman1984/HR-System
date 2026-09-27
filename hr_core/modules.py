"""The HR modules and the editions a customer can buy (mechano, as in Mizan).

status: built = shipped and tested; planned = designed, not built; design_only = architecture only,
never part of a sellable edition until built (payroll).
"""

MODULES = {
    "kernel": {"depends_on": [], "status": "built", "what": "company, organisation, jobs, positions, employee registry, journal, audit, eco publisher"},
    "attendance": {"depends_on": ["kernel"], "status": "built", "what": "the migrated attendance application (locked engine), daily import, dashboard, history"},
    "leave": {"depends_on": ["attendance"], "status": "built", "what": "leave requests linked to attendance days (inside the migrated engine)"},
    "shifts": {"depends_on": ["kernel"], "status": "planned", "what": "shift definitions, rosters and assignments independent of attendance"},
    "overtime": {"depends_on": ["shifts", "attendance"], "status": "planned", "what": "overtime requests, approval and actuals"},
    "skills": {"depends_on": ["kernel"], "status": "planned", "what": "skills, certifications, station qualification for manufacturing"},
    "training": {"depends_on": ["skills"], "status": "planned", "what": "courses and completions that grant skills"},
    "payroll": {"depends_on": ["attendance", "leave", "overtime"], "status": "design_only", "what": "pay calculation; accounting entries go to Mizan"},
}

EDITIONS = {
    "attendance": ["kernel", "attendance"],
    "attendance_leave": ["kernel", "attendance", "leave"],
    "full": ["kernel", "attendance", "leave", "shifts", "overtime", "skills", "training"],
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
