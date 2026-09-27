"""Documentation guard — the continuity documents must describe the code as it is.

A new agent session starts from AGENT_HANDOFF.md and STATUS.md, not from the chat. If those files fall behind the
code, the next session builds on a false picture. This test fails when the architecture changes (a kernel file, an
entrance, a test, a contract, an entity, a permission, a route, a command, a module's status, the planted-bug count,
the phase plan) and the inventory in STATUS.md was not updated with it, when STATUS.md and AGENT_HANDOFF.md disagree,
when the newest HISTORY.md entry is not from the session that last updated them, or when an old "attendance only"
claim reappears in a current document.

    python TEST_DOCS_CURRENT.py

Fixing a failure means reading what changed and correcting the document, not copying the expected value.
Standard library only.
"""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
results = {}


def read(rel):
    path = ROOT / rel
    assert path.is_file(), f"{rel} is missing (see CLAUDE.md, 'Continuity documents')"
    return path.read_text(encoding="utf-8")


def block(rel, name):
    """The ```<name> block of a document as {key: [values]} (a key may repeat: one value per line)."""
    found = re.search(r"```" + name + r"\n(.*?)```", read(rel), re.S)
    assert found, f"{rel} has no ```{name} block"
    out = {}
    for line in found.group(1).splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            out.setdefault(key.strip(), []).append(value.strip())
    return out


def one(values, key, rel):
    assert key in values and len(values[key]) == 1, f"{rel}: the block needs exactly one '{key}:' line"
    return values[key][0]


def words(values, key, rel):
    return sorted(" ".join(values.get(key, [])).split()) if key in values else fail(f"{rel}: no '{key}:' line")


def fail(message):
    raise AssertionError(message)


def same(what, documented, actual, rel="STATUS.md"):
    documented, actual = sorted(documented), sorted(actual)
    if documented != actual:
        missing = [x for x in actual if x not in documented]
        extra = [x for x in documented if x not in actual]
        fail(f"{rel} is behind the code ({what}). In the code but not documented: {missing}. "
             f"Documented but not in the code: {extra}. Update STATUS.md, AGENT_HANDOFF.md, HISTORY.md "
             f"(and the design documents) to describe the change, then the inventory.")


def literal_keys(rel, name):
    for node in ast.walk(ast.parse(read(rel))):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return [k.value for k in node.value.keys]
    fail(f"{rel}: {name} not found")


def before_historical(text):
    """The current part of a document: everything before a heading marked Historical / تاريخي."""
    cut = re.search(r"^#+ .*(Historical|تاريخي)", text, re.M)
    return text[:cut.start()] if cut else text


STATUS = block("STATUS.md", "inventory")
HANDOFF = block("AGENT_HANDOFF.md", "handoff")

# 1. The continuity documents exist.
for rel in ("HISTORY.md", "STATUS.md", "docs/LESSONS.md", "AGENT_HANDOFF.md", "CLAUDE.md",
            ".claude/skills/hr-development/SKILL.md"):
    read(rel)
results["continuity_documents_exist"] = True

# 2. STATUS.md and AGENT_HANDOFF.md tell the same story.
for key in ("phase", "stage", "updated"):
    assert one(STATUS, key, "STATUS.md") == one(HANDOFF, key, "AGENT_HANDOFF.md"), \
        f"STATUS.md and AGENT_HANDOFF.md disagree on '{key}': {STATUS[key]} vs {HANDOFF[key]}"
results["status_and_handoff_agree"] = True

# 3. The newest HISTORY.md entry belongs to the session that last updated them, and every discovery is complete.
history = read("HISTORY.md")
entries = re.findall(r"^## (\d{4}-\d{2}-\d{2}) ", history, re.M)
assert entries, "HISTORY.md has no '## YYYY-MM-DD — title' entry"
assert entries[0] == one(STATUS, "updated", "STATUS.md"), \
    f"the newest HISTORY.md entry is from {entries[0]} but STATUS.md was updated {STATUS['updated'][0]}: " \
    "a session that updates the status also records what it did and learned"
assert entries == sorted(entries, reverse=True), "HISTORY.md entries must be newest first"
for title, body in re.findall(r"^### ([^\n]+)\n(.*?)(?=^##)", history + "\n##", re.M | re.S):
    missing = [label for label in ("Symptom", "Cause", "Fix", "Lesson") if f"**{label}:**" not in body]
    assert not missing, f"HISTORY.md discovery '{title}' lacks {missing} (the shape is Symptom / Cause / Fix / Lesson)"
results["history_is_current_and_complete"] = True

# 4. The phase plan: the phases marked done in the design are the ones STATUS.md calls done; the next one is current.
design = read("docs/HR_SYSTEM_DESIGN.md")
assert "\n## 7. " in design, "docs/HR_SYSTEM_DESIGN.md lost its §7 phase plan"
design = design[design.index("\n## 7. "):]
done_in_design = re.findall(r"^\| \*\*(\d+) \(منفذة\)\*\* \|", design, re.M)
same("phases done in docs/HR_SYSTEM_DESIGN.md §7", words(STATUS, "done_phases", "STATUS.md"), done_in_design)
planned = re.findall(r"^\| (\d+) \|", design, re.M)
assert planned and one(STATUS, "phase", "STATUS.md") == planned[0], \
    f"STATUS.md phase {STATUS['phase']} is not the first phase the design leaves open ({planned[:1]})"
results["phase_matches_the_plan"] = True

# 5. The architecture inventory matches the code.
same("hr_core kernel files", words(STATUS, "hr_core", "STATUS.md"),
     [p.stem for p in (ROOT / "hr_core").glob("*.py") if p.stem != "__init__"])
same("top-level Python files (entrances, tools, tests)", words(STATUS, "root_python", "STATUS.md"),
     [p.stem for p in ROOT.glob("*.py")])
same("contracts in eco_schemas/", words(STATUS, "contracts", "STATUS.md"),
     [p.name.removesuffix(".schema.json").removesuffix(".json") for p in (ROOT / "eco_schemas").glob("*.json")])
same("registry entities (hr_core/registry.py ENTITIES)", words(STATUS, "entities", "STATUS.md"),
     literal_keys("hr_core/registry.py", "ENTITIES"))
same("permissions (hr_core/auth.py PERMISSIONS)", words(STATUS, "permissions", "STATUS.md"),
     literal_keys("hr_core/auth.py", "PERMISSIONS"))
same("HTTP routes (hr_core/api.py)", STATUS.get("route", []),
     [f"{m} {p}" for m, p in re.findall(r'@route\("(\w+)", "([^"]+)"\)', read("hr_core/api.py"))])
same("commands", STATUS.get("command", []),
     [f"{f[:-3]} {c}" for f in ("hr_server.py", "hr_registry.py") for c in re.findall(r'cmd == "([\w-]+)"', read(f))])
from hr_core.modules import MODULES  # noqa: E402
same("module statuses (hr_core/modules.py)", STATUS.get("module", []), [f"{m} {s['status']}" for m, s in MODULES.items()])
mutations = [n for n in ast.walk(ast.parse(read("migration/mutations.py")))
             if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "MUTATIONS" for t in n.targets)]
same("planted bugs in migration/mutations.py", [one(STATUS, "mutations", "STATUS.md")], [str(len(mutations[0].value.elts))])
results["inventory_matches_the_code"] = True

# 6. Every module appears under the status heading that matches hr_core/modules.py.
status_text = read("STATUS.md")
sections = {}
for heading, body in re.findall(r"^## ([^\n]+)\n(.*?)(?=^## |\Z)", status_text, re.M | re.S):
    sections[heading.strip()] = body
for heading in ("Built and tested", "Partially built", "Planned", "Design only"):
    assert heading in sections, f"STATUS.md needs the section '## {heading}'"
where = {"built": "Built and tested", "planned": "Planned", "design_only": "Design only"}
for name, spec in MODULES.items():
    assert f"`{name}`" in sections[where[spec["status"]]], \
        f"STATUS.md: module `{name}` is {spec['status']} in hr_core/modules.py but not listed under '{where[spec['status']]}'"
results["modules_listed_under_their_real_status"] = True

# 7. Every test runs in CI and is listed where people look for it.
ci, claude = read(".github/workflows/ci.yml"), read("CLAUDE.md")
for test in sorted(p.name for p in ROOT.glob("TEST_*.py")) + ["migration/mutations.py"]:
    assert f"python {test}" in ci, f"{test} does not run in .github/workflows/ci.yml"
    assert f"python {test}" in claude, f"{test} is not in the CLAUDE.md test list"
    assert test in status_text, f"{test} is not in STATUS.md"
results["every_test_runs_in_ci_and_is_listed"] = True

# 8. Files named in the current documents exist (another repository is written as `GMES/...`, `Mizan/...`).
OTHER = ("GMES/", "Mizan/", "BAMS/", "3D-Modeling/", "Accounting-sys/", "Mr.Ayman-HR/", "opening-nerp-tcode/", "data/")
for rel in ("STATUS.md", "AGENT_HANDOFF.md", "CLAUDE.md", "README.md", "START_HERE_AI.md", "docs/LESSONS.md",
            ".claude/skills/hr-development/SKILL.md"):
    for token in re.findall(r"`([A-Za-z0-9_./-]+\.(?:md|py|json|yml|bat|ps1))`", read(rel)):
        if not token.startswith(OTHER):
            assert (ROOT / token).is_file(), f"{rel} names `{token}`, which does not exist"
results["named_files_exist"] = True

# 9. The old "attendance only" picture stays history, never a current claim.
STALE = ("هذه النسخة هي أساس الحضور فقط", "الإصدار V1.0 يغطي الحضور فقط",
         "لا تدّع أن الموظفين أو الورديات أو الإجازات مترابطة", "Foundation only")
for rel in ("README.md", "START_HERE_AI.md", "CLAUDE.md", "STATUS.md", "AGENT_HANDOFF.md",
            ".claude/skills/hr-development/SKILL.md"):
    current = before_historical(read(rel))
    for phrase in STALE:
        assert phrase not in current, f"{rel} states '{phrase}' as current; move it under a 'Historical' heading"
for rel in ("PROJECT_GUIDE.md", "project_memory/PROGRAM_MAP.md", "SONNET_5_HIGH_EXECUTION_BRIEF_AR.md",
            ".workflow/HANDOFF_AR.md", "SKILL.md"):
    head = "\n".join(read(rel).splitlines()[:6])
    assert "STATUS.md" in head and ("HISTORICAL" in head or "SCOPE" in head), \
        f"{rel} describes an older stage: its first lines must say so (HISTORICAL or SCOPE) and point to STATUS.md"
results["old_claims_marked_historical"] = True

# 10. A document shipped in the customer ZIP links only to documents the ZIP also carries.
shipped = next(n for n in ast.walk(ast.parse(read("BUILD_PROJECT.py")))
               if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "runtime_files" for t in n.targets))
shipped = {e.value for e in shipped.value.elts}
for rel in sorted(r for r in shipped if r.endswith(".md")):
    for target in re.findall(r"\]\(([^)#\s]+)\)", read(rel)):
        if "://" not in target:
            target = (Path(rel).parent / target).as_posix()
            assert target in shipped, f"{rel} is in the customer ZIP and links to {target}, which BUILD_PROJECT.py does not ship"
results["shipped_documents_link_only_to_shipped_documents"] = True

print(json.dumps(results, indent=2))
