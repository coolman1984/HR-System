// HR-System screens (UX phase): one application shell built from the ecosystem's interface kit (eco-ui/, copied
// unchanged from GMES packages/eco-ui). No screen styles itself: they are built from the kit's parts.
// Every text goes through t(key): the dictionaries are /ui/i18n/en.json and /ui/i18n/ar.json (same keys, checked by
// TEST_HR_DELIVERY.py). Every value from the server is written as text, never as HTML.
import * as ui from "/ui/eco-ui/eco-ui.js";

const { h } = ui;
const S = { info: null, me: null, dict: {}, fallback: {}, lang: "en", shell: null, refs: null };

// ------------------------------------------------------------------ language, server calls
function t(key, vars) {
  let s = S.dict[key] ?? S.fallback[key] ?? key;
  for (const [k, v] of Object.entries(vars || {})) s = s.replace("{" + k + "}", String(v));
  return s;
}
const has = (key) => key in S.fallback;
async function loadLang(lang) {
  S.fallback = await (await fetch("/ui/i18n/en.json")).json();
  S.dict = lang === "ar" ? await (await fetch("/ui/i18n/ar.json")).json() : S.fallback;
  S.lang = lang === "ar" ? "ar" : "en";
}
class ApiError extends Error { constructor(message, code, status) { super(message); this.code = code; this.status = status; } }
async function api(method, path, body) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body || {}); }
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch (_) { data = null; }
  if (r.status === 401 && path !== "/api/login" && path !== "/api/me") { S.me = null; showLogin(); throw new ApiError(t("err.signin"), "auth.required", 401); }
  if (!r.ok) {
    const code = data && data.error;
    throw new ApiError(code && has("code." + code) ? t("code." + code) : (data && data.message) || String(r.status), code, r.status);
  }
  return data;
}
const can = (perm) => !!(S.me && S.me.permissions.includes(perm));
/** Every screen: the kit's standard screen with the one-line subtitle and the help text of its code (sub.CODE, about.CODE). */
const screen = (o) => ui.screen({ subtitle: o.code && has("sub." + o.code) ? t("sub." + o.code) : null, help: o.code && has("about." + o.code) ? t("about." + o.code) : null, ...o });
const value = (v) => (v && has("value." + v) ? t("value." + v) : v);
const profileName = (code, fallback) => (has("profile." + code) ? t("profile." + code) : fallback || code);
function fail(e) { ui.toast({ kind: "bad", title: t("failed_title"), text: e.message, timeout: 7000 }); }

// ------------------------------------------------------------------ start
async function boot() {
  ui.configure({ prefix: "hr", product: "hr" });
  S.info = await (await fetch("/api/info")).json();
  await loadLang(ui.prefs.get("lang", S.info.language || "en"));
  // the modern look (Mizan's visual language, in the shared kit) is HR's default; a person may switch to the classic one
  ui.configure({ lang: S.lang, theme: ui.prefs.get("theme", "light"), density: ui.prefs.get("density", "compact"), look: ui.prefs.get("look", "modern") });
  document.title = t("product.name");
  if (S.info.error) return showError();
  if (S.info.setup_needed) return showSetup();
  try { S.me = await api("GET", "/api/me"); } catch (_) { return showLogin(); }
  if (S.me.must_change) return showPassword(true);
  showShell();
}
function setLanguage(lang) { ui.prefs.set("lang", lang); location.reload(); }
function setTheme(theme) { ui.prefs.set("theme", theme); ui.configure({ theme }); }

// ------------------------------------------------------------------ sign-in, first run, errors (the "front door")
function door(content, { wide } = {}) {
  const c = S.info && S.info.company;
  const brand = h("aside", { class: "hr-door-brand" },
    h("div", { class: "hr-door-logo" }, h("span", { class: "eco-brand-mark", text: "HR" }), h("strong", { text: t("product.name") })),
    h("div", { class: "hr-door-pitch" }, h("h1", { text: t("door.title") }), h("p", { text: t("door.text") }),
      h("ul", {}, [["shield", "door.point_history"], ["archive", "door.point_backups"], ["globe", "door.point_languages"]].map(([ic, k]) => h("li", {}, ui.icon(ic, 18), h("span", { text: t(k) }))))),
    h("div", { class: "hr-door-foot" }, c ? h("span", {}, ui.icon("building", 14), " ", c.name, " · ", ui.ltr(c.code)) : null, h("span", {}, t("product.name") + " ", ui.ltr(S.info ? S.info.version : ""))));
  const tools = h("div", { class: "hr-door-tools" },
    ui.segmented({ value: S.lang, options: [["en", "English"], ["ar", "العربية"]], onChange: setLanguage }),
    ui.button({ icon: document.documentElement.dataset.theme === "dark" ? "sun" : "moon", kind: "ghost", title: ui.kitText("theme"),
      onClick: () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark") }));
  document.body.replaceChildren(h("div", { class: "hr-door" }, brand, h("main", { class: "hr-door-main" }, decorLines(), tools, h("div", { class: ["hr-door-card", wide && "is-wide"] }, content))));
}
/** Coloured rails with rounded corners and node dots around the sign-in card (Mizan's front door; shown in the modern look). */
function decorLines() {
  const NS = "http://www.w3.org/2000/svg", el = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
  const svg = el("svg", { class: "hr-decor", viewBox: "0 0 900 800", preserveAspectRatio: "xMidYMid slice", "aria-hidden": "true" });
  [["#a78bfa", "M -20 70 H 120 Q 140 70 140 90 V 250", [140, 250]], ["#2dd4bf", "M -20 360 H 60 Q 80 360 80 380 V 470 Q 80 490 100 490 H 210", [210, 490]],
    ["#f59e0b", "M 920 120 H 800 Q 780 120 780 140 V 300", [780, 300]], ["#ec4899", "M 920 520 H 860 Q 840 520 840 540 V 660 Q 840 680 820 680 H 700", [700, 680]],
    ["#3b82f6", "M 690 -20 V 40 Q 690 60 710 60 H 920", [690, 40]]].forEach(([c, d, [x, y]]) => { svg.append(el("path", { d, stroke: c }), el("circle", { cx: x, cy: y, r: "4.5", fill: c })); });
  return svg;
}
function showError() {
  door(h("div", {}, h("div", { class: "hr-door-icon is-bad" }, ui.icon("x-octagon", 26)), h("h2", { text: t("error.title") }),
    ui.banner("bad", S.info.error.message), h("p", { class: "eco-muted", text: t("error.help") })));
}
function showLogin(message) {
  const user = ui.input({ autocomplete: "username", dir: "ltr" }), pw = ui.input({ type: "password", autocomplete: "current-password" });
  const out = h("div");
  const submit = ui.button({ label: t("login.submit"), kind: "primary", size: "lg", type: "submit", cls: "hr-wide" });
  const form = h("form", { class: "hr-door-form" }, h("h2", { text: t("login.title") }), h("p", { class: "eco-muted", text: t("login.help") }),
    ui.field(t("user.username"), user), ui.field(t("user.password"), pw), out, submit);
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    submit.disabled = true;
    try {
      S.me = await api("POST", "/api/login", { username: user.value, password: pw.value });
      if (S.me.must_change) showPassword(true); else showShell();
    } catch (e) { ui.clear(out, ui.banner("bad", e.message)); pw.select(); }
    finally { submit.disabled = false; }
  });
  door(h("div", {}, message ? ui.banner("info", message) : null, form));
  user.focus();
}
function showSetup() {
  const local = S.info.local;
  const source = ui.segmented({ value: "local", options: [["local", t("setup.source.local_short"), "building"], ["owner", t("setup.source.owner_short"), "link"]],
    onChange: (v) => { idRow.hidden = v !== "owner"; source.value_ = v; } });
  source.value_ = "local";
  const cid = ui.input({ placeholder: "xxxxxxxx-xxxx-7xxx-xxxx-xxxxxxxxxxxx", dir: "ltr" });
  const idRow = ui.field(t("setup.company_id"), cid, { required: true, hint: t("code.company.id") });
  idRow.hidden = true;
  const code = ui.input({ dir: "ltr" }), name = ui.input(), user = ui.input({ dir: "ltr" }), dname = ui.input(), pw = ui.input({ type: "password" });
  const out = h("div");
  const submit = ui.button({ label: t("setup.install"), icon: "check", kind: "primary", size: "lg", type: "submit", cls: "hr-wide" });
  const step = (n, title, help, ...kids) => h("section", { class: "hr-step" }, h("div", { class: "hr-step-num", text: String(n) }),
    h("div", { class: "hr-step-body" }, h("h3", { text: title }), help ? h("p", { class: "eco-muted", text: help }) : null, h("div", { class: "eco-form" }, kids)));
  const form = h("form", { class: "hr-door-form" }, h("h2", { text: t("setup.title") }), h("p", { class: "eco-muted", text: t("setup.intro") }),
    step(1, t("setup.company"), t("setup.company_help"), h("div", { class: "eco-span-2" }, ui.field(t("setup.source"), source)), h("div", { class: "eco-span-2" }, idRow),
      ui.field(t("setup.company_code"), code, { required: true, hint: t("setup.code_hint") }), ui.field(t("setup.company_name"), name, { required: true })),
    step(2, t("setup.admin"), t("setup.admin_help"), ui.field(t("user.username"), user, { required: true }), ui.field(t("user.display_name"), dname),
      h("div", { class: "eco-span-2" }, ui.field(t("user.password"), pw, { required: true, hint: t("user.password_rule") }))),
    out, submit);
  if (S.info.demo_skip) {   // a presentation start only (HR_DEMO_SKIP=1 on an empty installation): straight into the demo company, sign in admin / 123
    const skip = ui.button({ label: t("setup.skip"), icon: "arrow-right", size: "lg", type: "button", cls: "hr-wide" });
    skip.addEventListener("click", async () => {
      skip.disabled = submit.disabled = true;
      ui.clear(out, ui.banner("info", t("setup.skip_busy")));
      try {
        await api("POST", "/api/setup/skip", {});
        S.info = await (await fetch("/api/info")).json();
        showLogin("");
      } catch (e) { ui.clear(out, ui.banner("bad", e.message)); skip.disabled = submit.disabled = false; }
    });
    form.append(skip);
  }
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    submit.disabled = true;
    try {
      const src = source.value_;
      await api("POST", "/api/setup/install", { company: { source: src, owner_app: src === "owner" ? "mizan" : null, id: cid.value.trim(), code: code.value, name: name.value },
        admin: { username: user.value, display_name: dname.value, password: pw.value } });
      S.info = await (await fetch("/api/info")).json();
      showLogin(t("setup.done"));
    } catch (e) { ui.clear(out, ui.banner("bad", e.message)); }
    finally { submit.disabled = false; }
  });
  door(local ? form : h("div", {}, h("div", { class: "hr-door-icon" }, ui.icon("monitor", 26)), h("h2", { text: t("setup.title") }), ui.banner("warn", t("setup.local_only"))), { wide: true });
}
function passwordForm(onDone) {
  const old = ui.input({ type: "password", autocomplete: "current-password" }), neu = ui.input({ type: "password", autocomplete: "new-password" }), again = ui.input({ type: "password", autocomplete: "new-password" });
  const out = h("div");
  const save = async () => {
    if (neu.value !== again.value) { ui.clear(out, ui.banner("bad", t("password.differ"))); return false; }
    try { await api("POST", "/api/password", { old: old.value, new: neu.value }); S.me = await api("GET", "/api/me"); onDone(); return true; }
    catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
  };
  return { body: h("div", { class: "eco-form" }, h("div", { class: "eco-span-2" }, ui.field(t("password.old"), old, { required: true })), ui.field(t("password.new"), neu, { required: true, hint: t("user.password_rule") }),
    ui.field(t("password.again"), again, { required: true }), h("div", { class: "eco-span-2" }, out)), save };
}
function showPassword(forced) {
  if (!forced) {
    const f = passwordForm(() => ui.toast({ kind: "ok", text: t("password.changed") }));
    ui.dialog({ title: t("password.title"), icon: "key", width: 520, body: f.body, actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("password.save"), kind: "primary", onClick: f.save }] });
    return;
  }
  const f = passwordForm(() => showShell());
  const btn = ui.button({ label: t("password.save"), kind: "primary", size: "lg", cls: "hr-wide", onClick: () => f.save() });
  door(h("div", { class: "hr-door-form" }, h("h2", { text: t("password.title") }), ui.banner("warn", t("password.must")), f.body, btn));
}

// ------------------------------------------------------------------ reference data (names instead of ids)
async function refs(force) {
  if (S.refs && !force) return S.refs;
  const get = (e, perm) => (can(perm) ? api("GET", "/api/" + e).catch(() => []) : Promise.resolve([]));
  const [units, jobs, positions, employees, shifts, calendars, skillList, rules, agencies, reqs, leaveTypes, courses] = await Promise.all([get("org_unit", "hr.org.read"), get("job", "hr.org.read"), get("position", "hr.org.read"),
    get("employee", "hr.employees.read"), get("shift", "hr.shifts.read"), get("work_calendar", "hr.shifts.read"), get("skill", "hr.skills.read"), get("penalty_rule", "hr.discipline.read"),
    get("agency", "hr.recruitment.read"), get("hire_requisition", "hr.recruitment.read"), get("leave_type", "hr.leave.read"), get("course", "hr.training.read")]);
  const byId = new Map([...units, ...jobs, ...positions, ...employees, ...shifts, ...calendars, ...skillList, ...rules, ...agencies, ...reqs, ...leaveTypes, ...courses].map((r) => [r.id, r]));
  const name = (r) => (r ? r.name || r.title || r.preferred_name || r.display_name || (r.job_id && byId.get(r.job_id) ? byId.get(r.job_id).title : "") || r.code : "");
  const label = (r) => (r ? r.code + " · " + name(r) : "");
  const unitOf = (emp) => { const p = emp && byId.get(emp.position_id); return p ? byId.get(p.org_unit_id) : null; };
  const jobOf = (emp) => { const p = emp && byId.get(emp.position_id); return p ? byId.get(p.job_id) : null; };
  S.refs = { units, jobs, positions, employees, shifts, calendars, skills: skillList, rules, agencies, reqs, leaveTypes, courses, byId, name, label, unitOf, jobOf, company: units.find((u) => u.type === "company") };
  return S.refs;
}
const changed = () => { S.refs = null; S.findings = null; };

// ------------------------------------------------------------------ record editor: one dialog for every register
const FORM = {
  employee: [["sec.identity", [["code", { req: true, ltr: true, fixed: true }], ["preferred_name", { req: true }], ["legal_name", {}], ["legacy_number", { ltr: true }]]],
    ["sec.employment", [["employment_status", { req: true, choices: ["Active", "Leave", "Suspended", "Terminated"] }], ["worker_type", {}], ["hire_date", { date: true }], ["termination_date", { date: true }]]],
    ["sec.placement", [["home_site_id", { ref: (R) => R.units.filter((u) => u.type === "site") }], ["position_id", { ref: (R) => R.positions }], ["manager_id", { ref: (R, row) => R.employees.filter((e) => !row || e.id !== row.id) }]]]],
  org_unit: [["sec.unit", [["type", { req: true, choices: ["site", "business_unit", "department", "section"], fixed: true }], ["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }],
    ["parent_id", { ref: (R) => R.units }]]]],
  job: [["sec.job", [["code", { req: true, ltr: true, fixed: true }], ["title", { req: true }], ["family", {}], ["level", {}], ["critical", { yesno: true }]]]],
  position: [["sec.position", [["code", { req: true, ltr: true, fixed: true }], ["job_id", { req: true, ref: (R) => R.jobs }], ["org_unit_id", { req: true, ref: (R) => R.units.filter((u) => u.type === "department" || u.type === "section") }],
    ["reports_to_id", { ref: (R, row) => R.positions.filter((p) => !row || p.id !== row.id) }], ["status", {}]]]],
  shift: [["sec.shift", [["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }], ["start_time", { req: true, time: true }], ["end_time", { req: true, time: true, hint: "hint.overnight" }],
    ["break_minutes", { num: true }], ["grace_minutes", { num: true }]]]],
  work_calendar: [["sec.calendar", [["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }], ["rest_days", { days: true, span: 2 }], ["holidays", { ltr: true, span: 2, hint: "hint.holidays" }]]]],
  shift_assignment: [["sec.assignment", [["employee_id", { req: true, ref: (R) => R.employees, started: true }], ["kind", { req: true, choices: ["regular", "temporary"], started: true }],
    ["shift_id", { req: true, ref: (R) => R.shifts, started: true }], ["calendar_id", { req: true, ref: (R) => R.calendars, started: true }],
    ["valid_from", { req: true, date: true, started: true }], ["valid_to", { date: true, hint: "hint.valid_to" }], ["note", { span: 2 }]]]],
  skill: [["sec.skill", [["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }], ["category", {}], ["validity_months", { num: true, hint: "hint.validity" }]]]],
  employee_skill: [["sec.qualification", [["employee_id", { req: true, ref: (R) => R.employees, fixed: true }], ["skill_id", { req: true, ref: (R) => R.skills, fixed: true }],
    ["level", { req: true, choices: ["1", "2", "3", "4"], num: true, prefix: "level." }], ["certified_on", { req: true, date: true }], ["expires_on", { date: true, hint: "hint.expiry" }], ["evidence", { span: 2 }]]]],
  penalty_rule: [["sec.penalty_rule", [["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }], ["violation", { req: true, choices: ["late", "early_leave", "absence", "no_record", "misconduct"], prefix: "violation." }],
    ["threshold_minutes", { num: true, hint: "hint.threshold" }], ["window_days", { num: true, hint: "hint.window" }], ["active", { yesno: true }], ["steps", { req: true, ltr: true, span: 2, hint: "hint.steps" }]]]],
  violation: [["sec.violation", [["employee_id", { req: true, ref: (R) => R.employees, fixed: true }], ["rule_id", { req: true, ref: (R) => R.rules, fixed: true }],
    ["work_date", { req: true, date: true, fixed: true }], ["minutes", { num: true }], ["note", { span: 2, hint: "hint.violation_note" }]]]],
  // people operations (WP-H2 to WP-H5)
  headcount_plan: [["sec.headcount_plan", [["code", { req: true, ltr: true, fixed: true }], ["period", { req: true, ltr: true, hint: "hint.period" }], ["job_id", { ref: (R) => R.jobs }], ["work_center_code", { ltr: true, hint: "hint.work_center" }],
    ["org_unit_id", { ref: (R) => R.units.filter((u) => u.type === "department" || u.type === "section") }], ["planned_fte", { req: true, num: true }],
    ["source", { req: true, choices: ["manual", "crew_requirement"], prefix: "value." }], ["note", { span: 2 }]]]],
  agency: [["sec.agency", [["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }], ["contact", {}], ["fee_percent", { num: true }], ["active", { yesno: true }]]]],
  hire_requisition: [["sec.hire_requisition", [["code", { req: true, ltr: true, fixed: true }], ["job_id", { req: true, ref: (R) => R.jobs }], ["position_id", { ref: (R) => R.positions }], ["work_center_code", { ltr: true, hint: "hint.work_center" }],
    ["count", { req: true, num: true }], ["employment_type", { req: true, choices: ["regular", "fixed_term", "agency", "intern"], prefix: "value." }], ["reason", { req: true, choices: ["crew_gap", "replacement", "growth", "seasonal"], prefix: "value." }],
    ["needed_by", { req: true, date: true }], ["contract_months", { num: true, hint: "hint.contract_months" }], ["agency_id", { ref: (R) => R.agencies }], ["note", { span: 2, hint: "hint.over_plan" }]]]],
  candidate: [["sec.candidate", [["code", { req: true, ltr: true, fixed: true }], ["requisition_id", { req: true, ref: (R) => R.reqs.filter((r) => r.status === "approved" || r.status === "open"), fixed: true }], ["display_name", { req: true }],
    ["source", { req: true, choices: ["agency", "referral", "walk_in", "online"], prefix: "value." }], ["stage", { req: true, choices: ["applied", "screened", "interviewed", "offered", "rejected", "withdrawn"], prefix: "stage." }], ["note", { span: 2 }]]]],
  onboarding_task: [["sec.onboarding_task", [["code", { req: true, ltr: true, fixed: true }], ["employee_id", { req: true, ref: (R) => R.employees, fixed: true }],
    ["kind", { req: true, choices: ["medical", "badge", "ppe", "esd_training", "station_training", "contract_signed"], prefix: "onb." }], ["due", { date: true }], ["done_on", { date: true }]]]],
  contract: [["sec.contract", [["code", { req: true, ltr: true, fixed: true }], ["employee_id", { req: true, ref: (R) => R.employees, fixed: true }], ["employment_type", { req: true, choices: ["regular", "fixed_term", "agency", "intern"], prefix: "value." }],
    ["start_date", { req: true, date: true }], ["end_date", { date: true }], ["agency_id", { ref: (R) => R.agencies }], ["reason", { span: 2 }]]]],
  overtime_request: [["sec.overtime_request", [["code", { req: true, ltr: true, fixed: true }], ["employee_id", { req: true, ref: (R) => R.employees, fixed: true }], ["work_date", { req: true, date: true, fixed: true }],
    ["planned_minutes", { req: true, num: true }], ["kind", { req: true, choices: ["day", "night", "rest_day", "holiday"], prefix: "ot." }], ["reason", { req: true, span: 2 }]]]],
  course: [["sec.course", [["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }], ["skill_id", { ref: (R) => R.skills }], ["grants_level", { num: true, choices: ["1", "2", "3", "4"], prefix: "level." }],
    ["validity_months", { num: true, hint: "hint.validity" }], ["duration_hours", { num: true }], ["mandatory_for", { choices: ["all_production"], prefix: "value." }],
    ["onboarding_kind", { choices: ["esd_training", "station_training", "ppe", "medical"], prefix: "onb.", hint: "hint.onboarding_kind" }]]]],
  training_session: [["sec.training_session", [["code", { req: true, ltr: true, fixed: true }], ["course_id", { req: true, ref: (R) => R.courses, fixed: true }], ["session_date", { req: true, date: true }], ["trainer", {}],
    ["attendees", { req: true, ltr: true, span: 2, hint: "hint.attendees" }]]]],
  leave_type: [["sec.leave_type", [["code", { req: true, ltr: true, fixed: true }], ["name", { req: true }], ["paid", { yesno: true }], ["annual_days", { num: true, hint: "hint.annual_days" }], ["carry_over_days", { num: true }], ["active", { yesno: true }]]]],
  leave_request: [["sec.leave_request", [["code", { req: true, ltr: true, fixed: true }], ["employee_id", { req: true, ref: (R) => R.employees, fixed: true }], ["leave_type_id", { req: true, ref: (R) => R.leaveTypes, fixed: true }],
    ["from_date", { req: true, date: true }], ["to_date", { req: true, date: true }], ["note", { span: 2 }]]]],
};
// records whose code is made from their content (one per person and day, per person and skill ...)
const AUTO_CODE = {
  shift_assignment: (v, R) => { const e = R.byId.get(v.employee_id); return e && v.valid_from ? e.code + "-" + v.valid_from + "-" + (v.kind === "temporary" ? "T" : "R") : ""; },
  employee_skill: (v, R) => { const e = R.byId.get(v.employee_id), k = R.byId.get(v.skill_id); return e && k ? e.code + "-" + k.code : ""; },
  violation: (v, R) => { const e = R.byId.get(v.employee_id), k = R.byId.get(v.rule_id); return e && k && v.work_date ? e.code + "-" + v.work_date + "-" + k.code : ""; },
};
const localToday = () => ui.isoDate(new Date());
/** The month payroll works on: the last month that is over (the current one has only just begun, so it shows nothing yet). */
const lastMonth = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return ui.isoDate(d).slice(0, 7); };
async function editRecord(entity, row, preset = {}) {
  const R = await refs();
  const inputs = {};
  const started = entity === "shift_assignment" && row && row.valid_from < localToday();
  const sections = FORM[entity].map(([title, fields]) => h("fieldset", { class: "hr-fieldset" }, h("legend", { text: t(title) }), h("div", { class: "eco-form" }, fields.map(([f, o]) => {
    let c;
    if (o.days) {
      const chosen = new Set(String((row ? row[f] : preset[f]) || "").split(",").filter(Boolean));
      const boxes = DAYS.map((d) => { const b = h("input", { type: "checkbox", class: "eco-check", checked: chosen.has(d), value: d, disabled: !!(row && started) }); return h("label", { class: "eco-check-label" }, b, h("span", { text: t("day." + d.toLowerCase()) })); });
      c = h("div", { class: "hr-days" }, boxes);
      c.getValue = () => boxes.map((l) => l.firstChild).filter((b) => b.checked).map((b) => b.value).join(",");
      inputs[f] = c;
      return ui.field(t("field." + f), c, { span: o.span });
    }
    if (o.choices) c = ui.select({ options: o.choices.map((v) => [v, o.prefix ? t(o.prefix + v) : value(v)]), placeholder: o.req ? undefined : "—" });
    else if (o.ref) c = ui.select({ options: o.ref(R, row).map((r) => [r.id, R.label(r)]), placeholder: "—" });
    else if (o.yesno) c = ui.select({ options: [["0", t("no")], ["1", t("yes")]] });
    else c = ui.input({ type: o.date ? "date" : o.time ? "time" : o.num ? "number" : "text", dir: o.ltr || o.time || o.num ? "ltr" : null });
    const v = row ? row[f] : preset[f];
    if (v !== null && v !== undefined) c.value = String(v);
    if ((row && o.fixed) || (started && o.started)) c.disabled = true;
    inputs[f] = c;
    return ui.field(t("field." + f), c, { required: o.req, span: o.span, hint: o.hint ? t(o.hint) : o.fixed && !row ? t("hint.fixed") : started && o.started ? t("hint.started") : null });
  }))));
  const out = h("div");
  return new Promise((resolve) => {
    ui.dialog({ title: row ? t("edit_title", { code: row.code }) : t("new." + entity), subtitle: row ? t("hint.version", { ver: row.ver }) : null,
      icon: { employee: "user", org_unit: "sitemap", job: "briefcase", position: "id-card", shift: "clock", work_calendar: "calendar", shift_assignment: "calendar-check", skill: "tag", employee_skill: "shield", penalty_rule: "scale", violation: "flag",
        headcount_plan: "chart", agency: "building", hire_requisition: "clipboard", candidate: "user-plus", onboarding_task: "clipboard-check", contract: "id-card", overtime_request: "clock", course: "bookmark", training_session: "calendar-check",
        leave_type: "tag", leave_request: "calendar" }[entity],
      width: entity === "employee" ? 680 : 560,
      body: h("div", { class: "hr-editor" }, guideAtLeast("full") && has("tip." + entity) ? ui.banner("info", t("tip." + entity), { title: t("guide.tip") }) : null, sections, out), onClose: (r) => resolve(r === true),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("save"), kind: "primary", icon: "save", onClick: async () => {
        const values = {};
        const nums = new Set(FORM[entity].flatMap(([, fs]) => fs.filter(([, o]) => o.num).map(([f]) => f)));
        for (const [f, c] of Object.entries(inputs)) {
          if (f === "code") continue;
          const raw = c.getValue ? c.getValue() : c.value;
          values[f] = raw === "" && !c.getValue ? null : f === "critical" || f === "active" || nums.has(f) ? Number(raw) : raw;
        }
        if (entity === "violation" && !row) Object.assign(values, { status: "proposed", source: "manual" });
        if (entity === "org_unit" && row) values.type = row.type;
        if (entity === "org_unit" && values.type === "site" && !values.parent_id && R.company) values.parent_id = R.company.id;  // a site belongs to the company
        const code = inputs.code ? inputs.code.value.trim() : row ? row.code : AUTO_CODE[entity](values, R);
        if (!code) { ui.clear(out, ui.banner("bad", t("err.code_required"))); return false; }
        try {
          await api("PUT", "/api/" + entity + "/" + encodeURIComponent(code), { fields: values, expected_ver: row ? row.ver : null });
          changed();
          ui.toast({ kind: "ok", title: t("saved"), text: code });
          return true;
        } catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
      } }] });
  });
}
async function binRecords(entity, rows) {
  if (!rows.length) return false;
  const ok = await ui.confirm({ title: t("bin.title"), text: rows.length === 1 ? t("confirm.delete", { code: rows[0].code }) : t("bin.many", { n: rows.length }), okLabel: t("delete"), danger: true });
  if (!ok) return false;
  let done = 0;
  for (const r of rows) {
    try { await api("DELETE", "/api/" + entity + "/" + encodeURIComponent(r.code) + "?ver=" + r.ver + (r.type ? "&type=" + r.type : "")); done++; }
    catch (e) { fail(e); }
  }
  changed();
  if (done) ui.toast({ kind: "ok", title: t("moved_to_bin"), text: t("bin.done", { n: done }), keep: true });
  return done > 0;
}
async function restoreRecord(entity, r) {
  try { await api("POST", "/api/" + entity + "/" + encodeURIComponent(r.code) + "/restore", { type: r.type || null }); changed(); ui.toast({ kind: "ok", title: t("restored"), text: r.code }); return true; }
  catch (e) { fail(e); return false; }
}
function recordFacts(r) {
  return ui.props([[t("rec.version"), ui.ltr(String(r.ver))], [t("rec.created"), r.created_at ? h("span", {}, ui.ltr(r.created_at.slice(0, 16).replace("T", " ")), " · ", ui.ltr(r.created_by || "")) : null],
    [t("rec.updated"), r.updated_at ? h("span", {}, ui.ltr(r.updated_at.slice(0, 16).replace("T", " ")), " · ", ui.ltr(r.updated_by || "")) : null], [t("rec.id"), h("small", {}, ui.ltr(r.id))]]);
}
const DAYS = ["SAT", "SUN", "MON", "TUE", "WED", "THU", "FRI"];  // the Egyptian working week starts on Saturday
const STATUS_ST = { Active: "ok", Leave: "idle", Suspended: "hold", Terminated: "neutral" };

// ------------------------------------------------------------------ Employees (the template of every register)
function employeesScreen({ shell }) {
  const conds = ui.conditionPanel([
    { key: "text", label: t("find.person"), placeholder: t("find.person_ph") },
    { key: "status", label: t("field.employment_status"), type: "select", options: ["Active", "Leave", "Suspended", "Terminated"].map((v) => [v, value(v)]), placeholder: t("all") },
    { key: "unit", label: t("field.org_unit_id"), type: "select", options: [], placeholder: t("all") },
    { key: "site", label: t("field.home_site_id"), type: "select", options: [], placeholder: t("all") },
    { key: "view", label: t("find.show"), type: "toggle", options: [["current", t("find.current")], ["bin", t("recycle.title")]], default: "current" },
  ], { key: "EMP1010", onSubmit: () => load() });
  const detail = h("div", { class: "hr-detail" });
  let R = null;
  const g = ui.grid([
    { key: "employment_status", label: t("field.employment_status"), type: "status", width: 130, frozen: true, status: (r) => (r.deleted ? "neutral" : STATUS_ST[r.employment_status] || "neutral"), label_of: (s, r) => (r.deleted ? t("recycle.title") : value(r.employment_status)) },
    { key: "code", label: t("field.code"), type: "code", width: 96, frozen: true, total: "count" },
    { key: "preferred_name", label: t("field.preferred_name"), width: 200, render: (r) => h("span", { class: "hr-person" }, ui.avatar(r.preferred_name || r.code, 22), h("span", { text: r.preferred_name || "" })) },
    { key: "position", label: t("field.position_id"), width: 150, value: (r) => (R && R.byId.get(r.position_id) ? R.byId.get(r.position_id).code : "") },
    { key: "job", label: t("field.job_id"), width: 170, value: (r) => (R ? R.name(R.jobOf(r)) : "") },
    { key: "unit", label: t("field.org_unit_id"), width: 170, value: (r) => (R ? R.name(R.unitOf(r)) : "") },
    { key: "site", label: t("field.home_site_id"), width: 130, value: (r) => (R ? R.name(R.byId.get(r.home_site_id)) : "") },
    { key: "manager", label: t("field.manager_id"), width: 150, value: (r) => (R ? R.name(R.byId.get(r.manager_id)) : "") },
    { key: "hire_date", label: t("field.hire_date"), type: "date", width: 100 },
    { key: "worker_type", label: t("field.worker_type"), width: 110 },
    { key: "legacy_number", label: t("field.legacy_number"), type: "code", width: 100 },
    { key: "legal_name", label: t("field.legal_name"), width: 180, hidden: true },
    { key: "termination_date", label: t("field.termination_date"), type: "date", width: 100, hidden: true },
    { key: "updated_at", label: t("rec.updated"), type: "date", width: 140, value: (r) => (r.updated_at || "").slice(0, 16).replace("T", " ") },
  ], { rowKey: "id", selection: "multi", totals: true, layoutKey: "EMP1010", emptyText: t("emp.empty"), onSelect: (sel) => { draw(sel); buttons(sel); }, onOpen: (r) => !r.deleted && can("hr.employees.write") && edit(r),
    presets: [{ id: "active", label: value("Active"), test: (r) => r.employment_status === "Active" }, { id: "leave", label: value("Leave"), test: (r) => r.employment_status === "Leave" },
      { id: "unplaced", label: t("preset.no_position"), test: (r) => !r.position_id && r.employment_status !== "Terminated" },
      { id: "new", label: t("preset.hired_this_year"), test: (r) => (r.hire_date || "").slice(0, 4) === localToday().slice(0, 4) }] });

  const act = {
    add: ui.button({ label: t("new.employee"), icon: "user-plus", kind: "primary", disabled: !can("hr.employees.write"), onClick: () => editRecord("employee", null).then((ok) => ok && load()) }),
    edit: ui.button({ label: t("edit"), icon: "edit", disabled: true, onClick: () => edit(g.selected()[0]) }),
    bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: () => binRecords("employee", g.selected()).then((ok) => ok && load()) }),
    restore: ui.button({ label: t("restore"), icon: "rotate", disabled: true, onClick: async () => { for (const r of g.selected()) await restoreRecord("employee", r); load(); } }),
  };
  function buttons(sel) {
    const bin = conds.values().view === "bin";
    act.edit.disabled = bin || sel.length !== 1 || !can("hr.employees.write");
    act.bin.disabled = bin || !sel.length || !can("hr.employees.delete");
    act.restore.hidden = !bin; act.restore.disabled = !sel.length || !can("hr.recycle.restore");
    act.bin.hidden = bin;
  }
  const edit = (r) => editRecord("employee", r).then((ok) => ok && load());
  const sc = screen({ code: "EMP1010", title: t("nav.employees"), path: [t("g.people")], shell, toolbar: [act.add, act.edit, act.bin, act.restore],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("employees"), exportLabel: t("export"), columns: () => g.columnsDialog(),
      print: () => print(), printLabel: t("print") },
    conditions: conds, grid: g, detail, detailKey: "EMP1010:detail" });
  function draw(sel) {
    if (!sel.length) { ui.clear(detail, ui.empty({ icon: "user", title: t("emp.none"), text: t("emp.none_help") })); return; }
    if (sel.length > 1) {
      const by = {};
      sel.forEach((e) => { by[e.employment_status] = (by[e.employment_status] || 0) + 1; });
      ui.clear(detail, h("div", { class: "hr-card-head" }, h("h2", { text: ui.kitText("selected", { n: sel.length }) }), h("span", { class: "eco-muted", text: t("bulk.hint") })),
        ui.section(t("field.employment_status"), ui.props(Object.entries(by).map(([k, n]) => [value(k), ui.ltr(String(n))]))));
      return;
    }
    const e = sel[0], pos = R.byId.get(e.position_id), unit = R.unitOf(e), job = R.jobOf(e), mgr = R.byId.get(e.manager_id), site = R.byId.get(e.home_site_id);
    recordWarnings(e.code).then((n) => { if (n && detail.firstChild && g.selected()[0] === e) detail.insertBefore(n, detail.children[1] || null); });
    const reports = R.employees.filter((x) => x.manager_id === e.id);
    ui.clear(detail,
      h("div", { class: "hr-profile" }, ui.avatar(e.preferred_name || e.code, 56),
        h("div", { class: "hr-profile-text" }, h("h2", { text: e.preferred_name || e.code }), h("div", { class: "eco-muted" }, job ? R.name(job) : t("emp.no_job"), unit ? " · " + R.name(unit) : ""),
          h("div", { class: "hr-row" }, ui.statusChip(e.deleted ? "neutral" : STATUS_ST[e.employment_status] || "neutral", e.deleted ? t("recycle.title") : value(e.employment_status)), h("span", { class: "eco-code" }, ui.ltr(e.code))))),
      ui.tabs([
        { id: "p", label: t("tab.profile"), icon: "id-card", render: () => h("div", {}, ui.section(t("sec.identity"), ui.props([[t("field.preferred_name"), e.preferred_name], [t("field.legal_name"), e.legal_name], [t("field.legacy_number"), e.legacy_number ? ui.ltr(e.legacy_number) : null]])),
          ui.section(t("sec.employment"), ui.props([[t("field.employment_status"), value(e.employment_status)], [t("field.worker_type"), e.worker_type], [t("field.hire_date"), e.hire_date ? ui.ltr(e.hire_date) : null], [t("field.termination_date"), e.termination_date ? ui.ltr(e.termination_date) : null]]))) },
        { id: "j", label: t("tab.work"), icon: "briefcase", render: () => h("div", {}, ui.section(t("sec.placement"), ui.props([[t("field.position_id"), pos ? R.label(pos) : null], [t("field.job_id"), job ? R.label(job) : null],
          [t("field.org_unit_id"), unit ? R.label(unit) : null], [t("field.home_site_id"), site ? R.label(site) : null], [t("field.manager_id"), mgr ? R.label(mgr) : null]])),
          ui.section(t("emp.reports", { n: reports.length }), reports.length ? h("div", { class: "hr-people" }, reports.map((x) => h("span", { class: "hr-person" }, ui.avatar(x.preferred_name || x.code, 20), h("span", { text: x.preferred_name || x.code })))) : h("span", { class: "eco-muted", text: t("none") }))) },
        { id: "r", label: t("tab.record"), icon: "history", render: () => h("div", {}, ui.section(t("tab.record"), recordFacts(e)), h("div", { class: "hr-pad" }, ui.banner("info", t("emp.history_note")))) },
        can("hr.discipline.read") ? { id: "d", label: t("tab.discipline"), icon: "scale", render: () => {
          const box = h("div", { class: "hr-pad" }, h("span", { class: "eco-spinner" }));
          api("GET", "/api/violation").then((all) => {
            const mine = all.filter((v) => v.employee_id === e.id).sort((a, b) => b.work_date.localeCompare(a.work_date));
            const days = mine.filter((v) => v.status === "approved" && (v.decision || "").startsWith("deduct:")).reduce((s, v) => s + Number(v.decision.slice(7)), 0);
            ui.clear(box, mine.length ? h("div", { class: "hr-stack" }, ui.kpiStrip([{ label: t("disc.total"), value: mine.length }, { label: t("vstatus.proposed"), value: mine.filter((v) => v.status === "proposed").length, status: "warn" },
              { label: t("field.deducted_days"), value: days, status: days ? "bad" : "ok" }]),
            h("ul", { class: "hr-list hr-list-tight" }, mine.slice(0, 20).map((v) => h("li", {}, ui.statusChip(VSTATE[v.status], t("vstatus." + v.status)),
              h("div", {}, h("b", { text: (R.byId.get(v.rule_id) || {}).name || "" }), h("small", { class: "eco-muted", text: v.work_date + (v.minutes ? " · " + t("disc.minutes_n", { n: v.minutes }) : "") })),
              h("span", { class: "eco-grow" }), h("span", { text: penaltyText(v.decision || v.proposed) }))))) : ui.empty({ icon: "check-circle", title: t("disc.none_for_person") }));
          }).catch((err) => ui.clear(box, ui.banner("bad", err.message)));
          return box;
        } } : null,
      ].filter(Boolean)),
      h("div", { class: "hr-pad hr-row" }, !e.deleted && can("hr.employees.write") ? ui.button({ label: t("edit"), icon: "edit", onClick: () => edit(e) }) : null,
        shell.screens.EMP2010 ? ui.button({ label: t("nav.journey"), icon: "trending-up", kind: "subtle", onClick: () => shell.open("EMP2010", { employee: e.id }) }) : null));
  }
  async function load() {
    const t0 = performance.now();
    g.setLoading();
    try {
      R = await refs(true);
      const v = conds.values();
      fillOptions(conds.control("unit"), R.units.filter((u) => u.type === "department" || u.type === "section"), v.unit);
      fillOptions(conds.control("site"), R.units.filter((u) => u.type === "site"), v.site);
      const rows = v.view === "bin" ? await api("GET", "/api/employee?deleted=1").then((all) => all.filter((r) => r.deleted)) : R.employees;
      const q = (v.text || "").trim().toLowerCase();
      g.setRows(rows.filter((e) => (!q || [e.code, e.preferred_name, e.legal_name, e.legacy_number].some((x) => (x || "").toLowerCase().includes(q))) &&
        (!v.status || e.employment_status === v.status) && (!v.unit || (R.unitOf(e) || {}).id === v.unit) && (!v.site || e.home_site_id === v.site)));
      sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
      buttons([]);
      const first = g.view()[0];
      if (first) g.select(first.id);
    } catch (e) { g.setError(e.message); }
  }
  load();
  return { el: sc.el };
}
// ------------------------------------------------------------------ Employee journey: one person's whole story, with a time-lapse
// Everything the modules know about one person, on one timeline: joining, placement, shifts and day changes, qualifications,
// every attended day, lateness, absences, leave, violations and decisions, and what is planned ahead. The player walks
// through it week by week and the figures add up as it goes (for a review, an appeal, or to show a client the product).
function journeyScreen({ shell, params }) {
  let R = null, E = null, events = [], weeks = [], pos = 0, timer = null, activity = [];
  const pickEmp = ui.select({ options: [], width: "320px" });
  const top = h("div", { class: "hr-journey-top" });
  const player = h("div", { class: "hr-journey-player" });
  const figures = h("div", { class: "hr-journey-figures" });
  const story = h("div", { class: "hr-journey-story" });
  const chart = h("div", { class: "hr-journey-chart" });
  const line = h("ol", { class: "hr-timeline" });
  const acts = h("div");
  const body = h("div", { class: "hr-page hr-journey" }, top, player, figures, h("div", { class: "hr-journey-grid" },
    ui.card({ title: t("jr.timeline"), icon: "history", tone: 2, cls: "hr-flush", body: h("div", { class: "hr-timeline-box" }, line) }),
    h("div", { class: "hr-dash-col" }, ui.card({ title: t("jr.week"), icon: "sparkles", tone: 1, body: story }), ui.card({ title: t("jr.hours"), icon: "chart", tone: 5, body: chart }),
      ui.card({ title: t("jr.activities"), subtitle: t("jr.activities_sub"), icon: "activity", tone: 3, cls: "hr-flush", body: acts }))));
  const sc = screen({ code: "EMP2010", title: t("nav.journey"), path: [t("g.people")], shell, headExtra: pickEmp,
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", print: () => print(), printLabel: t("print") }, body });
  pickEmp.addEventListener("change", () => { stop(); load(); });
  const fmtDate = (d) => new Date(d + "T12:00:00").toLocaleDateString(S.lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { day: "numeric", month: "short", year: "numeric" });
  const ev = (date, kind, icon, tone, title, detail, extra = {}) => events.push({ date, kind, icon, tone, title, detail, ...extra });

  async function load() {
    stop();
    ui.clear(line, h("li", {}, h("span", { class: "eco-spinner" })));
    try {
      R = R || await refs(true);
      if (!pickEmp.options.length) {
        pickEmp.replaceChildren(...R.employees.slice().sort((a, b) => (b.hire_date || "").localeCompare(a.hire_date || "")).map((e) => h("option", { value: e.id, text: e.code + " · " + (e.preferred_name || "") })));
        pickEmp.value = (params && params.employee) || (R.employees.find((e) => e.code === "E000900") || {}).id || pickEmp.options[0].value;
      }
      E = R.byId.get(pickEmp.value);
      events = [];
      const today = localToday(), start = E.hire_date && E.hire_date > addDays(today, -365) ? E.hire_date : addDays(today, -120);
      const get = (perm, path) => (can(perm) ? api("GET", path).catch(() => []) : Promise.resolve([]));
      const [asg, ovr, quals, viol, audit, users] = await Promise.all([get("hr.shifts.read", "/api/shift_assignment"), get("hr.shifts.read", "/api/roster_override"),
        get("hr.skills.read", "/api/employee_skill"), get("hr.discipline.read", "/api/violation"), get("admin.audit.read", "/api/admin/audit?limit=1000"), get("admin.users.manage", "/api/admin/users")]);
      // attended days: the comparison, in slices of 90 days (the planned schedule answers up to 93 days at a time)
      const days = [];
      if (can("hr.attendance.read") && can("hr.shifts.read")) {
        for (let a = start; a < today; a = addDays(a, 90)) {
          const b = addDays(a, 89) < addDays(today, -1) ? addDays(a, 89) : addDays(today, -1);
          const res = await api("GET", "/api/schedule/compare?from=" + a + "&to=" + b + "&employee=" + encodeURIComponent(E.code)).catch(() => ({ days: [] }));
          days.push(...res.days);
        }
      }
      const ahead = can("hr.shifts.read") ? await api("GET", "/api/schedule?from=" + today + "&to=" + addDays(today, 13) + "&employee=" + encodeURIComponent(E.code)).catch(() => []) : [];
      // the story, fact by fact
      const job = R.jobOf(E), unit = R.unitOf(E), mgr = R.byId.get(E.manager_id);
      if (E.hire_date) ev(E.hire_date, "joined", "user-plus", 2, t("jr.joined", { job: job ? R.name(job) : t("emp.no_job") }), [unit && R.name(unit), mgr && t("jr.reports_to", { name: mgr.preferred_name || mgr.code })].filter(Boolean).join(" · "));
      const team = R.employees.filter((x) => x.manager_id === E.id && x.employment_status !== "Terminated");
      if (team.length && E.hire_date) ev(E.hire_date, "team", "users", 1, t("jr.team", { n: team.length }), team.slice(0, 6).map((x) => x.preferred_name || x.code).join(", ") + (team.length > 6 ? " …" : ""));
      const account = users.find((u) => u.display_name && [E.preferred_name, E.legal_name].includes(u.display_name));
      if (account) ev(E.hire_date || start, "account", "key", 1, t("jr.account", { user: account.code }), profileName(account.profile));
      for (const a of asg.filter((x) => x.employee_id === E.id)) {
        const s = R.byId.get(a.shift_id), c = R.byId.get(a.calendar_id);
        ev(a.valid_from, "shift", "clock", 5, t(a.kind === "temporary" ? "jr.temp_shift" : "jr.shift", { shift: s ? s.name + " (" + s.start_time + "–" + s.end_time + ")" : "" }), [c && c.name, a.note].filter(Boolean).join(" · "), { future: a.valid_from > today });
        if (a.valid_to) ev(a.valid_to, "shift_end", "clock", 5, t("jr.shift_end", { shift: s ? s.name : "" }), "", { future: a.valid_to > today });
      }
      for (const o of ovr.filter((x) => x.employee_id === E.id)) ev(o.work_date, "change", "calendar", 4, o.shift_id ? t("jr.day_changed", { shift: (R.byId.get(o.shift_id) || {}).name || "" }) : t("jr.day_off"), o.reason, { future: o.work_date >= today });
      for (const q of quals.filter((x) => x.employee_id === E.id)) {
        const k = R.byId.get(q.skill_id) || {};
        ev(q.certified_on, "skill", "shield", 2, t("jr.certified", { skill: k.name || "", level: t("level." + q.level) }), q.evidence || "", { future: q.certified_on > today });
        if (q.expires_on) ev(q.expires_on, "skill_expiry", "alert", q.expires_on < today ? 3 : 4, t(q.expires_on < today ? "jr.expired" : "jr.expires", { skill: k.name || "" }), "", { future: q.expires_on > today });
      }
      let leaveRun = null;
      for (const d of days.sort((a, b) => a.work_date.localeCompare(b.work_date))) {
        if (d.verdict === "leave") { if (leaveRun && addDays(leaveRun.end, 1) >= d.work_date) { leaveRun.end = d.work_date; leaveRun.n++; } else { leaveRun = { start: d.work_date, end: d.work_date, n: 1 }; events.push(Object.assign({ date: d.work_date, kind: "leave", icon: "calendar", tone: 4, title: "", detail: "" }, { run: leaveRun })); } continue; }
        if (d.verdict === "absent") ev(d.work_date, "absent", "x-octagon", 3, t("jr.absent"), d.shift_code ? t("jr.planned", { shift: d.shift_code }) : "");
        else if (d.verdict === "no_record") ev(d.work_date, "no_record", "alert", 4, t("jr.no_record"), "");
        else if (d.verdict === "as_planned" || d.verdict === "worked_off_day") {
          events.push({ date: d.work_date, kind: "worked", minutes: Number(d.worked_minutes) || 0, silent: true });
          if (Number(d.late_minutes) > 0) ev(d.work_date, "late", "clock", 4, t("jr.late", { n: Math.round(d.late_minutes) }), d.start ? t("jr.shift_started", { time: d.start.slice(11) }) : "");
          if (d.verdict === "worked_off_day") ev(d.work_date, "extra", "zap", 1, t("jr.worked_off_day"), "");
        }
      }
      for (const e of events.filter((x) => x.kind === "leave")) { e.title = t("jr.leave", { n: e.run.n }); e.detail = e.run.start === e.run.end ? "" : t("jr.until", { date: fmtDate(e.run.end) }); }
      for (const v of viol.filter((x) => x.employee_id === E.id)) {
        const rule = R.byId.get(v.rule_id) || {};
        ev(v.work_date, "violation", "flag", 3, t("jr.violation", { what: t("violation." + rule.violation) }), t("jr.proposed", { penalty: penaltyText(v.proposed), n: v.occurrence || 1 }));
        if (v.status !== "proposed") ev(v.decided_on, v.status === "approved" ? "penalty" : "waived", "scale", v.status === "approved" ? 3 : 5,
          v.status === "approved" ? t("jr.penalty", { penalty: penaltyText(v.decision) }) : t("jr.waived"), [v.decided_by && t("jr.by", { who: v.decided_by }), v.note].filter(Boolean).join(" · "),
          { deducted: v.status === "approved" && (v.decision || "").startsWith("deduct:") ? Number(v.decision.slice(7)) : 0 });
      }
      for (const d of ahead.filter((x) => x.status === "work")) events.push({ date: d.work_date, kind: "planned", silent: true, future: true, minutes: d.paid_minutes || 0 });
      activity = account ? audit.filter((x) => x.actor === account.code && !["login.ok", "change.refused", "permission.denied"].includes(x.event)).slice(0, 40) : [];
      if (E.termination_date) ev(E.termination_date, "left", "logout", 3, t("jr.left"), "");
      events.sort((a, b) => a.date.localeCompare(b.date) || (a.silent ? 1 : 0) - (b.silent ? 1 : 0));
      // weeks of the time-lapse: from the first fact to two weeks ahead
      const first = weekStart(events.length ? events[0].date : start), last = addDays(today, 13);
      weeks = [];
      for (let w = first; w <= last; w = addDays(w, 7)) weeks.push(w);
      pos = weeks.findIndex((w) => addDays(w, 6) >= today);
      if (pos < 0) pos = weeks.length - 1;
      ui.clear(acts, activity.length ? h("ul", { class: "hr-activity" }, activity.map((a) => h("li", {}, h("span", { class: "hr-dot" }), h("div", {}, h("b", { text: eventText(a) }),
        h("small", { class: "eco-muted" }, ui.ltr((a.at || "").slice(0, 16).replace("T", " ")))))))
        : h("div", { class: "hr-pad2 eco-muted", text: account ? t("none") : t("jr.no_account") }));
      drawTop(account, team);
      drawPlayer();
      draw();
    } catch (e) { ui.clear(line, h("li", {}, ui.banner("bad", e.message))); }
  }
  function drawTop(account, team) {
    const job = R.jobOf(E), unit = R.unitOf(E);
    ui.clear(top, h("div", { class: "hr-profile hr-journey-head" }, ui.avatar(E.preferred_name || E.code, 64),
      h("div", { class: "hr-profile-text" }, h("h2", { text: E.preferred_name || E.code }), h("div", { class: "eco-muted", text: [E.legal_name, job && R.name(job), unit && R.name(unit)].filter(Boolean).join(" · ") }),
        h("div", { class: "hr-row" }, ui.statusChip(STATUS_ST[E.employment_status] || "neutral", value(E.employment_status)), h("span", { class: "eco-code" }, ui.ltr(E.code)),
          E.hire_date ? ui.badge(t("jr.since", { date: fmtDate(E.hire_date) }), "accent", "calendar") : null, account ? ui.badge(t("jr.user", { user: account.code }), "info", "key") : null,
          team.length ? ui.badge(t("jr.team_n", { n: team.length }), "neutral", "users") : null))));
  }
  function drawPlayer() {
    const range = h("input", { type: "range", min: "0", max: String(Math.max(0, weeks.length - 1)), value: String(pos), class: "hr-journey-range", "aria-label": t("jr.week") });
    range.addEventListener("input", () => { stop(); pos = Number(range.value); draw(); });
    const play = ui.button({ label: t("jr.play"), icon: "play", kind: "primary", onClick: () => (timer ? stop() : startPlay()) });
    play.classList.add("hr-play");
    ui.clear(player, h("div", { class: "hr-row" }, play, ui.button({ icon: ui.isRTL() ? "chev-right" : "chev-left", title: t("plan.prev"), onClick: () => { stop(); pos = Math.max(0, pos - 1); draw(); } }),
      ui.button({ icon: ui.isRTL() ? "chev-left" : "chev-right", title: t("plan.next"), onClick: () => { stop(); pos = Math.min(weeks.length - 1, pos + 1); draw(); } }),
      h("strong", { class: "hr-journey-date" }), h("span", { class: "eco-grow" }), ui.badge(t("jr.today_marker"), "accent", "flag")), range);
    player.range = range; player.play = play;
  }
  function startPlay() {
    if (pos >= weeks.length - 1) pos = 0;
    player.play.replaceChildren(ui.icon("pause", 15), h("span", { text: t("jr.pause") }));
    timer = setInterval(() => { if (pos >= weeks.length - 1) { stop(); return; } pos++; draw(); }, 1100);
  }
  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
    if (player.play) player.play.replaceChildren(ui.icon("play", 15), h("span", { text: t("jr.play") }));
  }
  function draw() {
    if (!weeks.length) return;
    const end = addDays(weeks[pos], 6), today = localToday();
    player.range.value = String(pos);
    player.querySelector(".hr-journey-date").textContent = t("jr.week_of", { from: fmtDate(weeks[pos]), to: fmtDate(end) }) + (weeks[pos] > today ? " · " + t("jr.ahead") : "");
    const upto = events.filter((e) => e.date <= end);
    const past = upto.filter((e) => !e.future || e.date <= today);
    const sum = (k) => past.filter((e) => e.kind === k).length;
    const worked = past.filter((e) => e.kind === "worked");
    const hoursTotal = Math.round(worked.reduce((s, e) => s + e.minutes, 0) / 60);
    const deducted = past.filter((e) => e.deducted).reduce((s, e) => s + e.deducted, 0);
    const skillsHeld = past.filter((e) => e.kind === "skill").length - past.filter((e) => e.kind === "skill_expiry" && e.date <= end && e.date < today).length;
    ui.clear(figures, ui.kpiStrip([{ label: t("jr.k.days"), value: worked.length, status: "ok" }, { label: t("jr.k.hours"), value: hoursTotal, unit: t("unit.h") },
      { label: t("jr.k.late"), value: sum("late"), status: sum("late") ? "warn" : null }, { label: t("jr.k.absent"), value: sum("absent"), status: sum("absent") ? "bad" : null },
      { label: t("jr.k.leave"), value: past.filter((e) => e.kind === "leave").reduce((s, e) => s + e.run.n, 0) },
      { label: t("jr.k.penalties"), value: sum("penalty"), status: sum("penalty") ? "bad" : null }, { label: t("field.deducted_days"), value: deducted, status: deducted ? "bad" : null },
      { label: t("jr.k.skills"), value: Math.max(0, skillsHeld), status: "info" }]));
    // this week, told in words
    const wk = events.filter((e) => e.date >= weeks[pos] && e.date <= end && !e.silent);
    const wkWorked = events.filter((e) => e.kind === "worked" && e.date >= weeks[pos] && e.date <= end);
    const planned = events.filter((e) => e.kind === "planned" && e.date >= weeks[pos] && e.date <= end);
    ui.clear(story, h("p", { class: "hr-journey-summary", text: weeks[pos] > today ? t("jr.story_ahead", { n: planned.length }) : t("jr.story", { n: wkWorked.length, h: Math.round(wkWorked.reduce((s, e) => s + e.minutes, 0) / 60) }) }),
      wk.length ? h("ul", { class: "hr-journey-list" }, wk.map((e) => h("li", { class: "eco-tone-" + e.tone }, h("span", { class: "hr-tl-ic" }, ui.icon(e.icon, 14)), h("div", {}, h("b", { text: e.title }), h("small", { class: "eco-muted", text: fmtDate(e.date) + (e.detail ? " · " + e.detail : "") })))))
        : h("p", { class: "eco-muted", text: t("jr.quiet") }));
    // hours per week up to this week
    const shown = weeks.slice(Math.max(0, pos - 11), pos + 1);
    ui.clear(chart, ui.barChart({ labels: shown.map((w) => w.slice(5).replace("-", "/")), series: [{ label: t("jr.hours"), values: shown.map((w) => Math.round(events.filter((e) => (e.kind === "worked" || (e.kind === "planned" && w > today)) && e.date >= w && e.date <= addDays(w, 6)).reduce((s, e) => s + e.minutes, 0) / 60)) }], height: 190, width: 620 }));
    // the timeline up to now (newest first), the current week highlighted, the future faint
    const shownEvents = events.filter((e) => !e.silent && e.date <= end).reverse().slice(0, 150);
    ui.clear(line, shownEvents.length ? shownEvents.map((e) => h("li", { class: ["eco-tone-" + e.tone, e.date >= weeks[pos] && "is-now", e.future && e.date > today && "is-future"] },
      h("span", { class: "hr-tl-dot" }, ui.icon(e.icon, 13)), h("div", { class: "hr-tl-body" }, h("div", { class: "hr-tl-date", text: fmtDate(e.date) }), h("b", { text: e.title }), e.detail ? h("small", { class: "eco-muted", text: e.detail }) : null)))
      : h("li", {}, ui.empty({ icon: "history", title: t("jr.empty") })));
  }
  load();
  return { el: sc.el, onActivate: (p) => { if (p && p.employee && E && p.employee !== E.id) { pickEmp.value = p.employee; load(); } }, onClose: stop };
}

function fillOptions(sel, rows, keep) {
  const first = sel.options[0];
  sel.replaceChildren(first, ...rows.map((r) => h("option", { value: r.id, text: r.code + " · " + (r.name || r.title || "") })));
  sel.value = keep || "";
}

// ------------------------------------------------------------------ Organisation: structure tree, jobs, positions
function structureScreen({ shell }) {
  const side = h("div", { class: "hr-side" }), record = h("div", { class: "hr-record" });
  let R = null, current = null, tr = null;
  const TYPE_ICON = { company: "building", site: "map-pin", business_unit: "layers", department: "sitemap", section: "users" };
  const CHILD = { company: "site", site: "business_unit", business_unit: "department", department: "section" };
  const staff = (u) => R.employees.filter((e) => { const x = R.unitOf(e); return x && (x.id === u.id); });
  const below = (u) => R.units.filter((x) => x.parent_id === u.id);
  function draw() {
    const node = (u) => ({ id: u.id, label: u.code + "  " + (u.name || ""), icon: TYPE_ICON[u.type], badge: staff(u).length || null, children: below(u).map(node) });
    const roots = R.units.filter((u) => !u.parent_id);
    tr = ui.tree(roots.map(node), { key: "ORG1010", expanded: R.units.filter((u) => below(u).length).map((u) => u.id), selected: current && current.id, onSelect: (n) => { current = R.byId.get(n.id); drawRecord(); } });
    ui.clear(side, h("div", { class: "hr-side-head" }, h("strong", { text: t("org.tree") }), h("span", { class: "eco-grow" }),
      ui.button({ icon: "expand", kind: "ghost", size: "sm", title: t("org.expand"), onClick: () => tr.expandAll() }), ui.button({ icon: "minus", kind: "ghost", size: "sm", title: t("org.collapse"), onClick: () => tr.collapseAll() })),
    h("div", { class: "hr-side-body" }, R.units.length ? tr : ui.empty({ icon: "sitemap", title: t("org.empty") })));
    drawRecord();
  }
  function drawRecord() {
    const u = current;
    act.add.disabled = !can("hr.org.write") || (u && !CHILD[u.type]);
    act.edit.disabled = !u || u.type === "company" || !can("hr.org.write");
    act.bin.disabled = !u || u.type === "company" || !can("hr.employees.delete");
    if (!u) { ui.clear(record, ui.empty({ icon: "sitemap", title: t("org.pick"), text: t("org.pick_help") })); return; }
    const parent = R.byId.get(u.parent_id), people = staff(u), positions = R.positions.filter((p) => p.org_unit_id === u.id), subs = below(u);
    const peopleGrid = ui.grid([{ key: "employment_status", label: t("field.employment_status"), type: "status", width: 124, status: (r) => STATUS_ST[r.employment_status] || "neutral", label_of: (s, r) => value(r.employment_status) },
      { key: "code", label: t("field.code"), type: "code", width: 90 }, { key: "preferred_name", label: t("field.preferred_name"), width: 200 },
      { key: "job", label: t("field.job_id"), width: 180, value: (r) => R.name(R.jobOf(r)) }], { rows: people, selection: "single", layoutKey: "ORG1010-people", emptyText: t("org.no_people") });
    const posGrid = ui.grid([{ key: "code", label: t("field.code"), type: "code", width: 110 }, { key: "job", label: t("field.job_id"), width: 190, value: (r) => R.name(R.byId.get(r.job_id)) },
      { key: "holder", label: t("org.holder"), width: 190, value: (r) => R.name(R.employees.find((e) => e.position_id === r.id)) || "—" }, { key: "status", label: t("field.status"), width: 100 }],
    { rows: positions, selection: "single", layoutKey: "ORG1010-positions", emptyText: t("org.no_positions") });
    const subGrid = ui.grid([{ key: "type", label: t("field.type"), width: 130, value: (r) => value(r.type) }, { key: "code", label: t("field.code"), type: "code", width: 110 }, { key: "name", label: t("field.name"), width: 220 },
      { key: "n", label: t("org.people"), type: "number", width: 90, value: (r) => staff(r).length }], { rows: subs, selection: "single", layoutKey: "ORG1010-subs", emptyText: t("org.no_units"),
      onOpen: (r) => { current = r; tr.select(r.id); drawRecord(); } });
    ui.clear(record,
      h("div", { class: "hr-record-head" }, h("span", { class: "hr-record-icon" }, ui.icon(TYPE_ICON[u.type], 20)),
        h("div", { class: "hr-record-titles" }, h("div", { class: "eco-muted" }, value(u.type), " · ", ui.ltr(u.code)), h("h2", { text: u.name || u.code })),
        h("div", { class: "hr-mini-kpis" }, [[t("org.people"), people.length], [t("tab.position"), positions.length], [t("org.units"), subs.length]].map(([k, n]) => h("div", {}, h("b", {}, ui.ltr(String(n))), h("span", { text: k }))))),
      ui.section(t("sec.unit"), ui.props([[t("field.code"), ui.ltr(u.code)], [t("field.type"), value(u.type)], [t("field.parent_id"), parent ? R.label(parent) : null]], { cols: 2 })),
      ui.tabs([{ id: "people", label: t("org.people"), icon: "users", count: people.length, render: () => h("div", { class: "hr-subgrid" }, peopleGrid.el) },
        { id: "pos", label: t("tab.position"), icon: "id-card", count: positions.length, render: () => h("div", { class: "hr-subgrid" }, posGrid.el) },
        { id: "units", label: t("org.units"), icon: "sitemap", count: subs.length, render: () => h("div", { class: "hr-subgrid" }, subGrid.el) },
        { id: "rec", label: t("tab.record"), icon: "history", render: () => ui.section(t("tab.record"), recordFacts(u)) }]));
  }
  const act = {
    add: ui.button({ label: t("org.add_below"), icon: "plus", kind: "primary", onClick: () => editRecord("org_unit", null, { type: current ? CHILD[current.type] : "site", parent_id: current ? current.id : null }).then((ok) => ok && load()) }),
    edit: ui.button({ label: t("edit"), icon: "edit", onClick: () => editRecord("org_unit", current).then((ok) => ok && load()) }),
    bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", onClick: () => binRecords("org_unit", [current]).then((ok) => { if (ok) { current = null; load(); } }) }),
  };
  const sc = screen({ code: "ORG1010", title: t("nav.structure"), path: [t("g.organisation")], shell, toolbar: [act.add, act.edit, act.bin],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", print: () => print(), printLabel: t("print") },
    body: ui.split(side, record, { key: "ORG1010:side", initial: 320, min: 220, second: false }) });
  async function load() {
    try {
      R = await refs(true);
      current = current ? R.byId.get(current.id) || null : R.units.find((u) => u.type === "department") || R.units[0] || null;
      draw();
    } catch (e) { ui.clear(record, ui.empty({ icon: "x-octagon", title: e.message })); }
  }
  load();
  return { el: sc.el };
}
function registerScreen(entity, code, titleKey, columns, opts = {}) {
  const o = { write: "hr.org.write", group: "g.organisation", rows: (R) => (entity === "job" ? R.jobs : R.positions), people: true, ...opts };
  return ({ shell }) => {
    let R = null;
    const detail = h("div", { class: "hr-detail" });
    const g = ui.grid(columns(() => R), { rowKey: "id", selection: "multi", totals: true, layoutKey: code, emptyText: t("empty"),
      onSelect: (sel) => {
        act.edit.disabled = sel.length !== 1 || !can(o.write); act.bin.disabled = !sel.length || !can("hr.employees.delete"); drawDetail(sel[0]);
        for (const { a, b } of custom) b.disabled = sel.length !== 1 || !can(a.perm || o.write) || !!(a.when && !a.when(sel[0], R));
      },
      onOpen: (r) => can(o.write) && editRecord(entity, r).then((ok) => ok && load()) });
    const act = {
      add: ui.button({ label: t("new." + entity), icon: "plus", kind: "primary", disabled: !can(o.write), onClick: async () => { const preset = o.preset ? await o.preset(R) : {}; if (await editRecord(entity, null, preset)) load(); } }),
      edit: ui.button({ label: t("edit"), icon: "edit", disabled: true, onClick: () => editRecord(entity, g.selected()[0]).then((ok) => ok && load()) }),
      bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: () => binRecords(entity, g.selected()).then((ok) => ok && load()) }),
    };
    // buttons that act on the selected record (approve, hire, complete ...): shown disabled until a record they apply to is selected
    const custom = (o.actions || []).map((a) => {
      const b = ui.button({ label: t(a.label), icon: a.icon, kind: a.kind || "default", disabled: true, onClick: () => a.run(g.selected()[0], { R, reload: () => load(), sc }) });
      return { a, b };
    });
    const tools = (o.tools || []).map((x) => ui.button({ label: t(x.label), icon: x.icon, disabled: !can(x.perm), onClick: () => x.run({ R, reload: () => load() }) }));
    const sc = screen({ code, title: t(titleKey), path: [t(o.group)], shell, toolbar: [act.add, act.edit, ...custom.map((c) => c.b), ...tools, act.bin],
      standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", export: () => g.exportCSV(entity), exportLabel: t("export"), columns: () => g.columnsDialog() }, grid: g, detail, detailKey: code + ":detail" });
    function drawDetail(r) {
      if (!r) { ui.clear(detail, ui.empty({ icon: o.icon || (entity === "job" ? "briefcase" : "id-card"), title: t("pick.one") })); return; }
      const holders = !o.people ? [] : entity === "position" ? R.employees.filter((e) => e.position_id === r.id) : R.employees.filter((e) => (R.jobOf(e) || {}).id === r.id);
      ui.clear(detail, h("div", { class: "hr-card-head" }, h("div", { class: "eco-muted" }, ui.ltr(r.code)), h("h2", { text: R.name(r) })),
        ui.section(t("sec." + entity), ui.props(columns(() => R).filter((c) => !c.hidden).map((c) => [c.label, c.value ? String(c.value(r) ?? "") : r[c.key] === null || r[c.key] === undefined ? null : String(r[c.key])]))),
        !o.people ? (o.extra ? o.extra(r, R) : null) : ui.section(t("org.people") + " (" + holders.length + ")", holders.length ? h("div", { class: "hr-people" }, holders.map((x) => h("span", { class: "hr-person" }, ui.avatar(x.preferred_name || x.code, 20), h("span", { text: x.preferred_name || x.code })))) : h("span", { class: "eco-muted", text: t("none") })),
        ui.section(t("tab.record"), recordFacts(r)));
    }
    async function load() {
      const t0 = performance.now();
      g.setLoading();
      try { R = await refs(true); g.setRows(o.fetch ? await api("GET", "/api/" + entity) : o.rows(R)); sc.result({ ms: Math.round(performance.now() - t0) }); drawDetail(null); }
      catch (e) { g.setError(e.message); }
    }
    load();
    return { el: sc.el };
  };
}
const jobsScreen = registerScreen("job", "ORG1020", "nav.jobs", (R) => [
  { key: "code", label: t("field.code"), type: "code", width: 110, frozen: true, total: "count" }, { key: "title", label: t("field.title"), width: 220 },
  { key: "family", label: t("field.family"), width: 150 }, { key: "level", label: t("field.level"), width: 90 },
  { key: "critical", label: t("field.critical"), width: 90, value: (r) => (r.critical ? t("yes") : t("no")) },
  { key: "positions", label: t("tab.position"), type: "number", width: 90, total: "sum", value: (r) => (R() ? R().positions.filter((p) => p.job_id === r.id).length : 0) },
]);
const positionsScreen = registerScreen("position", "ORG1030", "nav.positions", (R) => [
  { key: "code", label: t("field.code"), type: "code", width: 120, frozen: true, total: "count" },
  { key: "job", label: t("field.job_id"), width: 200, value: (r) => (R() ? R().name(R().byId.get(r.job_id)) : "") },
  { key: "unit", label: t("field.org_unit_id"), width: 200, value: (r) => (R() ? R().name(R().byId.get(r.org_unit_id)) : "") },
  { key: "reports", label: t("field.reports_to_id"), width: 130, value: (r) => (R() && R().byId.get(r.reports_to_id) ? R().byId.get(r.reports_to_id).code : "") },
  { key: "holder", label: t("org.holder"), width: 180, value: (r) => (R() ? R().name(R().employees.find((e) => e.position_id === r.id)) || "—" : "") },
  { key: "status", label: t("field.status"), width: 100 },
]);

// ------------------------------------------------------------------ Workforce planning (phase 3): shifts, calendars, assignments, roster
const minutesOf = (hhmm) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3));
const shiftFacts = (r) => { const d = ((minutesOf(r.end_time) - minutesOf(r.start_time)) % 1440 + 1440) % 1440 || 1440; return { overnight: minutesOf(r.end_time) <= minutesOf(r.start_time), paid: d - (r.break_minutes || 0) }; };
const hours = (m) => (m / 60).toFixed(m % 60 ? 2 : 0).replace(/\.?0+$/, "") + " " + t("unit.h");
const shiftsScreen = registerScreen("shift", "SHF1010", "nav.shifts", () => [
  { key: "code", label: t("field.code"), type: "code", width: 100, frozen: true, total: "count" }, { key: "name", label: t("field.name"), width: 180 },
  { key: "start_time", label: t("field.start_time"), type: "code", width: 90 }, { key: "end_time", label: t("field.end_time"), type: "code", width: 90 },
  { key: "overnight", label: t("shift.overnight"), width: 110, render: (r) => (shiftFacts(r).overnight ? ui.badge(t("shift.overnight"), "info", "moon") : h("span", { class: "eco-muted", text: "—" })) },
  { key: "paid", label: t("shift.paid"), width: 110, value: (r) => hours(shiftFacts(r).paid) },
  { key: "break_minutes", label: t("field.break_minutes"), type: "number", width: 100 }, { key: "grace_minutes", label: t("field.grace_minutes"), type: "number", width: 100 },
], { write: "hr.shifts.write", group: "g.planning", rows: (R) => R.shifts, people: false, icon: "clock",
  extra: (r) => ui.section(t("shift.rule"), h("p", { class: "eco-muted hr-small", text: t("shift.rule_text") })) });
const calendarsScreen = registerScreen("work_calendar", "SHF1020", "nav.calendars", () => [
  { key: "code", label: t("field.code"), type: "code", width: 100, frozen: true, total: "count" }, { key: "name", label: t("field.name"), width: 200 },
  { key: "rest_days", label: t("field.rest_days"), width: 200, value: (r) => (r.rest_days || "").split(",").filter(Boolean).map((d) => t("day." + d.toLowerCase())).join("، ") || "—" },
  { key: "holidays_n", label: t("cal.holidays_n"), type: "number", width: 110, value: (r) => (r.holidays || "").split(",").filter(Boolean).length },
  { key: "next_holiday", label: t("cal.next_holiday"), type: "date", width: 130, value: (r) => (r.holidays || "").split(",").find((d) => d >= localToday()) || "" },
], { write: "hr.shifts.write", group: "g.planning", rows: (R) => R.calendars, people: false, icon: "calendar",
  extra: (r) => ui.section(t("field.holidays"), (r.holidays || "") ? h("div", { class: "hr-people" }, r.holidays.split(",").map((d) => ui.badge(d, d < localToday() ? "neutral" : "warn", "calendar"))) : h("span", { class: "eco-muted", text: t("none") })) });

function assignmentsScreen({ shell }) {
  let R = null;
  const today = localToday();
  const stateOf = (a) => (a.valid_to && a.valid_to < today ? "ended" : a.valid_from > today ? "future" : "current");
  const conds = ui.conditionPanel([{ key: "text", label: t("find.person"), placeholder: t("find.person_ph") },
    { key: "state", label: t("asg.state"), type: "select", options: ["current", "future", "ended"].map((v) => [v, t("asg." + v)]), placeholder: t("all") },
    { key: "kind", label: t("field.kind"), type: "select", options: [["regular", value("regular")], ["temporary", value("temporary")]], placeholder: t("all") }], { key: "SHF2010", onSubmit: () => load() });
  const g = ui.grid([
    { key: "state", label: t("asg.state"), type: "status", width: 110, frozen: true, status: (r) => ({ current: "run", future: "setup", ended: "neutral" })[stateOf(r)], label_of: (s, r) => t("asg." + stateOf(r)) },
    { key: "employee", label: t("field.employee_id"), width: 200, value: (r) => R.label(R.byId.get(r.employee_id)) },
    { key: "kind", label: t("field.kind"), width: 100, value: (r) => value(r.kind) },
    { key: "shift", label: t("field.shift_id"), width: 150, value: (r) => R.label(R.byId.get(r.shift_id)) },
    { key: "calendar", label: t("field.calendar_id"), width: 150, value: (r) => R.label(R.byId.get(r.calendar_id)) },
    { key: "valid_from", label: t("field.valid_from"), type: "date", width: 110 }, { key: "valid_to", label: t("field.valid_to"), type: "date", width: 110 },
    { key: "note", label: t("field.note"), width: 200 }, { key: "code", label: t("field.code"), type: "code", width: 170, hidden: true },
  ], { rowKey: "id", selection: "single", layoutKey: "SHF2010", totals: false, emptyText: t("asg.empty"), rowStatus: (r) => (stateOf(r) === "current" ? "run" : null),
    presets: [{ id: "temp", label: value("temporary"), test: (r) => r.kind === "temporary" }, { id: "ending", label: t("preset.ending_soon"), test: (r) => !!r.valid_to && r.valid_to >= today && r.valid_to <= addDays(today, 14) }],
    onSelect: (sel) => { const a = sel[0]; act.edit.disabled = !a || !can("hr.shifts.write") || stateOf(a) === "ended"; act.bin.disabled = !a || a.valid_from < today || !can("hr.employees.delete"); },
    onOpen: (r) => can("hr.shifts.write") && editRecord("shift_assignment", r).then((ok) => ok && load()) });
  const act = {
    add: ui.button({ label: t("new.shift_assignment"), icon: "plus", kind: "primary", disabled: !can("hr.shifts.write"), onClick: () => editRecord("shift_assignment", null, { kind: "regular", valid_from: today }).then((ok) => ok && load()) }),
    edit: ui.button({ label: t("asg.edit_or_end"), icon: "edit", disabled: true, onClick: () => editRecord("shift_assignment", g.selected()[0]).then((ok) => ok && load()) }),
    bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: () => binRecords("shift_assignment", g.selected()).then((ok) => ok && load()) }),
  };
  const sc = screen({ code: "SHF2010", title: t("nav.assignments"), path: [t("g.planning")], shell, toolbar: [act.add, act.edit, act.bin],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("assignments"), exportLabel: t("export"), columns: () => g.columnsDialog() },
    conditions: conds, grid: g, note: h("div", { class: "hr-pad" }, ui.banner("info", t("asg.rule"))) });
  async function load() {
    const t0 = performance.now();
    g.setLoading();
    try {
      R = await refs(true);
      const v = conds.values(), q = (v.text || "").toLowerCase();
      const rows = await api("GET", "/api/shift_assignment");
      g.setRows(rows.filter((a) => { const e = R.byId.get(a.employee_id) || {}; return (!q || (e.code + " " + (e.preferred_name || "")).toLowerCase().includes(q)) && (!v.state || stateOf(a) === v.state) && (!v.kind || a.kind === v.kind); }));
      sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
    } catch (e) { g.setError(e.message); }
  }
  load();
  return { el: sc.el };
}

const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return ui.isoDate(d); };
const weekStart = (iso) => { const d = new Date(iso + "T12:00:00"); return addDays(iso, -((d.getDay() + 1) % 7)); };  // Saturday
function dayChip(d, onOpen) {
  const cls = d.status === "work" ? (d.overnight ? "is-night" : "is-work") : "is-" + d.status;
  const text = d.status === "work" ? d.shift_code : t("plan." + d.status);
  return h("button", { type: "button", class: ["hr-day", cls, d.source === "override" && "is-changed"], title: d.status === "work" ? d.start.slice(11) + "–" + d.end.slice(11) : text,
    onclick: (ev) => { ev.stopPropagation(); onOpen(d); } }, h("span", { text }), d.status === "work" ? h("small", {}, ui.ltr(d.start.slice(11) + "–" + d.end.slice(11))) : null);
}
function rosterScreen({ shell }) {
  let R = null, start = weekStart(localToday());
  const week = ui.input({ type: "date", value: start, width: "150px" });
  const label = h("strong", { class: "hr-week-label" });
  const nav = h("div", { class: "hr-row" }, ui.button({ icon: ui.isRTL() ? "chev-right" : "chev-left", title: t("plan.prev"), onClick: () => move(-7) }), week,
    ui.button({ icon: ui.isRTL() ? "chev-left" : "chev-right", title: t("plan.next"), onClick: () => move(7) }), ui.button({ label: t("pr.this_week"), kind: "ghost", onClick: () => { start = weekStart(localToday()); week.value = start; load(); } }), label);
  week.addEventListener("change", () => { if (week.value) { start = weekStart(week.value); week.value = start; load(); } });
  const conds = ui.conditionPanel([{ key: "text", label: t("find.person"), placeholder: t("find.person_ph") }, { key: "unit", label: t("field.org_unit_id"), type: "select", options: [], placeholder: t("all") }],
    { key: "SHF3010", onSubmit: () => load(), extra: nav });
  const cols = () => [
    { key: "code", label: t("field.code"), type: "code", width: 80, frozen: true, total: "count" },
    { key: "name", label: t("field.preferred_name"), width: 170, frozen: true },
    ...DAYS.map((_, i) => ({ key: "d" + i, label: t("day." + DAYS[i].toLowerCase()) + " " + addDays(start, i).slice(5).replace("-", "/"), width: 118, cls: "hr-day-cell",
      render: (r) => dayChip(r["d" + i], openDay), value: (r) => (r["d" + i].status === "work" ? r["d" + i].shift_code : t("plan." + r["d" + i].status)),
      total: (rows) => t("plan.working_n", { n: rows.filter((x) => x["d" + i].status === "work").length }) })),
    { key: "hours", label: t("plan.week_hours"), width: 100, type: "number", value: (r) => Math.round(DAYS.reduce((a, _, i) => a + (r["d" + i].paid_minutes || 0), 0) / 6) / 10 },
  ];
  let g = null;
  const host = h("div", { class: "hr-roster-host" });
  const legend = h("div", { class: "hr-legend" }, [["is-work", "plan.work"], ["is-night", "plan.night"], ["is-rest", "plan.rest"], ["is-holiday", "plan.holiday"], ["is-unscheduled", "plan.unscheduled"], ["is-changed", "plan.changed"]]
    .map(([c, k]) => h("span", {}, h("i", { class: "hr-day " + c }), t(k))));
  const sc = screen({ code: "SHF3010", title: t("nav.roster"), path: [t("g.planning")], shell,
    toolbar: [ui.button({ label: t("plan.swap"), icon: "rotate", disabled: !can("hr.shifts.write"), onClick: () => swapDialog() }), legend],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", export: () => g && g.exportCSV("roster-" + start), exportLabel: t("export"), print: () => print(), printLabel: t("print") },
    conditions: conds, body: host });
  function move(n) { start = addDays(start, n); week.value = start; load(); }
  function openDay(d) {
    const emp = R.byId.get(d.employee_id), past = d.work_date < localToday(), mode = { v: d.status === "work" ? "shift" : "off" };
    const shiftSel = ui.select({ options: R.shifts.map((s) => [s.id, s.code + " · " + s.name + " (" + s.start_time + "–" + s.end_time + ")"]) });
    const cur = R.shifts.find((s) => s.code === d.shift_code); if (cur) shiftSel.value = cur.id;
    const reason = ui.input({ placeholder: t("plan.reason_ph") });
    const pick = ui.segmented({ value: mode.v, options: [["shift", t("plan.work_shift"), "clock"], ["off", t("plan.day_off"), "calendar"]], onChange: (x) => { mode.v = x; shiftRow.hidden = x !== "shift"; } });
    const shiftRow = ui.field(t("field.shift_id"), shiftSel);
    shiftRow.hidden = mode.v !== "shift";
    const out = h("div");
    ui.dialog({ title: (emp ? emp.preferred_name || emp.code : "") + " · " + d.work_date, subtitle: t("plan.now") + ": " + (d.status === "work" ? d.shift_code + " " + d.start.slice(11) + "–" + d.end.slice(11) : t("plan." + d.status)),
      icon: "calendar-check", width: 520,
      body: past ? ui.banner("info", t("plan.past")) : !can("hr.shifts.write") ? ui.banner("info", t("code.perm.denied")) : h("div", { class: "hr-stack" }, pick, shiftRow, ui.field(t("field.reason"), reason, { required: true }), out),
      actions: past || !can("hr.shifts.write") ? [{ label: t("close"), kind: "primary" }] : [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("save"), kind: "primary", icon: "save", onClick: async () => {
        const code = emp.code + "-" + d.work_date;
        const existing = (await api("GET", "/api/roster_override")).find((o) => o.code === code);
        try {
          await api("PUT", "/api/roster_override/" + encodeURIComponent(code), { fields: { employee_id: emp.id, work_date: d.work_date, shift_id: mode.v === "shift" ? shiftSel.value : null, reason: reason.value }, expected_ver: existing ? existing.ver : null });
          ui.toast({ kind: "ok", title: t("saved"), text: code }); load(); return true;
        } catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
      } }] });
  }
  function swapDialog() {
    const people = R.employees.map((e) => [e.code, e.code + " · " + (e.preferred_name || "")]);
    const a = ui.select({ options: people }), b = ui.select({ options: people }), day = ui.input({ type: "date", value: localToday() }), reason = ui.input({ placeholder: t("plan.reason_ph") });
    if (people[1]) b.value = people[1][0];
    const out = h("div", { class: "eco-span-2" });
    ui.dialog({ title: t("plan.swap"), icon: "rotate", width: 560, body: h("div", { class: "eco-form" }, ui.field(t("plan.person_a"), a, { required: true }), ui.field(t("plan.person_b"), b, { required: true }),
      ui.field(t("plan.day"), day, { required: true }), ui.field(t("field.reason"), reason), h("div", { class: "eco-span-2" }, ui.banner("info", t("plan.swap_help"))), out),
    actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("plan.swap"), kind: "primary", icon: "rotate", onClick: async () => {
      try { await api("POST", "/api/schedule/swap", { date: day.value, a: a.value, b: b.value, reason: reason.value }); ui.toast({ kind: "ok", title: t("plan.swapped"), keep: true }); load(); return true; }
      catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
    } }] });
  }
  async function load() {
    const t0 = performance.now();
    try {
      R = await refs(true);
      const v = conds.values();
      fillOptions(conds.control("unit"), R.units.filter((u) => u.type === "department" || u.type === "section"), v.unit);
      label.textContent = start + " → " + addDays(start, 6);
      const days = await api("GET", "/api/schedule?from=" + start + "&to=" + addDays(start, 6));
      const rows = new Map();
      for (const d of days) {
        const e = R.byId.get(d.employee_id);
        if (!rows.has(d.employee_id)) rows.set(d.employee_id, { id: d.employee_id, code: e.code, name: e.preferred_name || "", emp: e });
        rows.get(d.employee_id)["d" + DAYS.findIndex((_, i) => addDays(start, i) === d.work_date)] = d;
      }
      const q = (v.text || "").toLowerCase();
      const list = [...rows.values()].filter((r) => r.emp.employment_status !== "Terminated" && (!q || (r.code + " " + r.name).toLowerCase().includes(q)) && (!v.unit || (R.unitOf(r.emp) || {}).id === v.unit || (R.unitOf(r.emp) || {}).parent_id === v.unit));
      g = ui.grid(cols(), { rows: list, rowKey: "id", selection: "single", totals: true, layoutKey: null, rowHeight: 36, autofit: false, emptyText: t("plan.empty") });
      g.el.classList.add("hr-roster");
      ui.clear(host, g.el);
      sc.result && sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
    } catch (e) { ui.clear(host, ui.empty({ icon: "x-octagon", title: e.message })); }
  }
  load();
  return { el: sc.el };
}

const VERDICT_ST = { as_planned: "ok", absent: "bad", no_record: "warn", leave: "idle", worked_off_day: "info", off: "neutral", no_schedule: "warn", none: "neutral" };
function compareScreen({ shell }) {
  let R = null;
  const today = localToday();
  const conds = ui.conditionPanel([{ key: "days", label: t("cmp.period"), type: "daterange", required: true, default: [weekStart(today), today], span: 2 },
    { key: "verdict", label: t("cmp.verdict"), type: "select", options: Object.keys(VERDICT_ST).map((k) => [k, t("verdict." + k)]), placeholder: t("all") },
    { key: "text", label: t("find.person"), placeholder: t("find.person_ph") }], { key: "SHF3020", onSubmit: () => load() });
  const counts = h("div", { class: "hr-pad hr-row" });
  const g = ui.grid([
    { key: "verdict", label: t("cmp.verdict"), type: "status", width: 200, frozen: true, status: (r) => VERDICT_ST[r.verdict], label_of: (s, r) => t("verdict." + r.verdict) },
    { key: "employee_code", label: t("field.code"), type: "code", width: 80 }, { key: "name", label: t("field.preferred_name"), width: 170, value: (r) => R.name(R.byId.get(r.employee_id)) },
    { key: "work_date", label: t("plan.day"), type: "date", width: 104 },
    { key: "planned", label: t("cmp.planned"), width: 170, value: (r) => (r.status === "work" ? r.shift_code + " " + r.start.slice(11) + "–" + r.end.slice(11) : t("plan." + r.status)) },
    { key: "attendance_status", label: t("cmp.attended"), width: 120 }, { key: "worked_minutes", label: t("cmp.worked"), type: "number", width: 110 },
    { key: "paid_minutes", label: t("cmp.planned_minutes"), type: "number", width: 120 },
  ], { rowKey: "key", selection: "single", totals: false, layoutKey: "SHF3020", emptyText: t("cmp.empty"), idleText: t("hint.inquiry"), rowStatus: (r) => (r.verdict === "absent" ? "down" : r.verdict === "as_planned" ? "run" : null) });
  const sc = screen({ code: "SHF3020", title: t("nav.compare"), path: [t("g.planning")], shell,
    standard: { inquiry: () => load(), inquiryLabel: t("inquiry"), reset: () => conds.reset(), resetLabel: t("reset"), export: () => g.exportCSV("planned-vs-attended"), exportLabel: t("export"), columns: () => g.columnsDialog() },
    conditions: conds, grid: g, note: counts });
  async function load() {
    const missing = conds.missing();
    if (missing.length) { ui.toast({ kind: "warn", text: ui.kitText("required_missing", { fields: missing.join(", ") }) }); return; }
    const t0 = performance.now();
    g.setLoading();
    try {
      R = await refs(true);
      const v = conds.values(), q = (v.text || "").toLowerCase();
      const res = await api("GET", "/api/schedule/compare?from=" + v.days[0] + "&to=" + v.days[1]);
      const rows = res.days.map((d) => ({ ...d, key: d.employee_id + d.work_date })).filter((d) => d.verdict !== "none" && (!v.verdict || d.verdict === v.verdict) && (!q || (d.employee_code + " " + R.name(R.byId.get(d.employee_id))).toLowerCase().includes(q)));
      g.setRows(rows);
      const by = {};
      res.days.forEach((d) => { by[d.verdict] = (by[d.verdict] || 0) + 1; });
      ui.clear(counts, Object.keys(VERDICT_ST).filter((k) => by[k] && k !== "none").map((k) => ui.statusChip(VERDICT_ST[k], t("verdict." + k) + " · " + by[k])),
        res.unknown_attendance_people.length ? ui.badge(t("cmp.unknown", { n: res.unknown_attendance_people.length }), "warn", "alert") : null);
      sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
    } catch (e) { g.setError(e.message); }
  }
  load();   // opens on this week's comparison: the period is already filled in
  return { el: sc.el };
}

// ------------------------------------------------------------------ Skills (phase 5)
const QSTATE = { valid: "ok", expiring: "warn", expired: "bad", not_yet: "neutral" };
const qState = (q, on) => (q.certified_on > on ? "not_yet" : q.expires_on && q.expires_on < on ? "expired" : q.expires_on && (new Date(q.expires_on) - new Date(on)) / 864e5 <= 30 ? "expiring" : "valid");
const skillsScreen = registerScreen("skill", "SKL1010", "nav.skills", (R) => [
  { key: "code", label: t("field.code"), type: "code", width: 110, frozen: true, total: "count" }, { key: "name", label: t("field.name"), width: 220 },
  { key: "category", label: t("field.category"), width: 150 }, { key: "validity_months", label: t("field.validity_months"), type: "number", width: 130 },
], { write: "hr.skills.write", group: "g.skills", rows: (R) => R.skills, people: false, icon: "tag" });
function qualificationsScreen({ shell }) {
  let R = null;
  const today = localToday();
  const conds = ui.conditionPanel([{ key: "text", label: t("find.person"), placeholder: t("find.person_ph") }, { key: "skill", label: t("field.skill_id"), type: "select", options: [], placeholder: t("all") },
    { key: "state", label: t("qual.state"), type: "select", options: Object.keys(QSTATE).map((k) => [k, t("qual." + k)]), placeholder: t("all") }], { key: "SKL2010", onSubmit: () => load() });
  const g = ui.grid([
    { key: "state", label: t("qual.state"), type: "status", width: 120, frozen: true, status: (r) => QSTATE[qState(r, today)], label_of: (s, r) => t("qual." + qState(r, today)) },
    { key: "employee", label: t("field.employee_id"), width: 200, value: (r) => R.label(R.byId.get(r.employee_id)) },
    { key: "skill", label: t("field.skill_id"), width: 200, value: (r) => R.label(R.byId.get(r.skill_id)) },
    { key: "level", label: t("field.level"), width: 150, render: (r) => h("span", { class: "hr-level" }, [1, 2, 3, 4].map((n) => h("i", { class: n <= r.level ? "is-on" : null })), h("span", { text: t("level." + r.level) })) },
    { key: "certified_on", label: t("field.certified_on"), type: "date", width: 110 }, { key: "expires_on", label: t("field.expires_on"), type: "date", width: 110 },
    { key: "evidence", label: t("field.evidence"), width: 200 },
  ], { rowKey: "id", selection: "single", layoutKey: "SKL2010", emptyText: t("qual.empty"), rowStatus: (r) => (qState(r, today) === "expired" ? "down" : null),
    presets: ["expiring", "expired"].map((k) => ({ id: k, label: t("qual." + k), test: (r) => qState(r, today) === k })),
    onSelect: (sel) => { act.edit.disabled = !sel.length || !can("hr.skills.write"); act.bin.disabled = !sel.length || !can("hr.employees.delete"); },
    onOpen: (r) => can("hr.skills.write") && editRecord("employee_skill", r).then((ok) => ok && load()) });
  const act = {
    add: ui.button({ label: t("new.employee_skill"), icon: "plus", kind: "primary", disabled: !can("hr.skills.write"), onClick: () => editRecord("employee_skill", null, { level: 3, certified_on: today }).then((ok) => ok && load()) }),
    edit: ui.button({ label: t("qual.recertify"), icon: "refresh", disabled: true, onClick: () => editRecord("employee_skill", g.selected()[0]).then((ok) => ok && load()) }),
    bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: () => binRecords("employee_skill", g.selected()).then((ok) => ok && load()) }),
  };
  const sc = screen({ code: "SKL2010", title: t("nav.qualifications"), path: [t("g.skills")], shell, toolbar: [act.add, act.edit, act.bin],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("qualifications"), exportLabel: t("export"), columns: () => g.columnsDialog() },
    conditions: conds, grid: g });
  async function load() {
    const t0 = performance.now();
    g.setLoading();
    try {
      R = await refs(true);
      const v = conds.values(), q = (v.text || "").toLowerCase();
      fillOptions(conds.control("skill"), R.skills, v.skill);
      const rows = await api("GET", "/api/employee_skill");
      g.setRows(rows.filter((r) => { const e = R.byId.get(r.employee_id) || {}; return (!q || (e.code + " " + (e.preferred_name || "")).toLowerCase().includes(q)) && (!v.skill || r.skill_id === v.skill) && (!v.state || qState(r, today) === v.state); }));
      sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
    } catch (e) { g.setError(e.message); }
  }
  load();
  return { el: sc.el };
}
function matrixScreen({ shell }) {
  let R = null;
  const today = localToday(), host = h("div", { class: "hr-roster-host" });
  const conds = ui.conditionPanel([{ key: "text", label: t("find.person"), placeholder: t("find.person_ph") }, { key: "unit", label: t("field.org_unit_id"), type: "select", options: [], placeholder: t("all") },
    { key: "category", label: t("field.category"), placeholder: t("all") }], { key: "SKL3010", onSubmit: () => load() });
  const legend = h("div", { class: "hr-legend" }, Object.keys(QSTATE).map((k) => h("span", {}, ui.statusChip(QSTATE[k], t("qual." + k)))));
  const sc = screen({ code: "SKL3010", title: t("nav.matrix"), path: [t("g.skills")], shell, toolbar: [legend],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", print: () => print(), printLabel: t("print") }, conditions: conds, body: host });
  async function load() {
    try {
      R = await refs(true);
      const v = conds.values();
      fillOptions(conds.control("unit"), R.units.filter((u) => u.type === "department" || u.type === "section"), v.unit);
      const quals = await api("GET", "/api/employee_skill");
      const held = new Map(quals.map((q) => [q.employee_id + "|" + q.skill_id, q]));
      const skillCols = R.skills.filter((k) => !v.category || (k.category || "").toLowerCase().includes(v.category.toLowerCase()));
      const cell = (e, k) => {
        const q = held.get(e.id + "|" + k.id);
        return h("button", { type: "button", class: ["hr-q", q ? "is-" + qState(q, today) : "is-none"], title: q ? t("level." + q.level) + (q.expires_on ? " · " + t("field.expires_on") + " " + q.expires_on : "") : t("qual.none"),
          onclick: (ev) => { ev.stopPropagation(); if (can("hr.skills.write")) editRecord("employee_skill", q || null, { employee_id: e.id, skill_id: k.id, level: 3, certified_on: today }).then((ok) => ok && load()); } },
        q ? [1, 2, 3, 4].map((n) => h("i", { class: n <= q.level ? "is-on" : null })) : h("span", { text: "+" }));
      };
      const q = (v.text || "").toLowerCase();
      const rows = R.employees.filter((e) => e.employment_status !== "Terminated" && (!q || (e.code + " " + (e.preferred_name || "")).toLowerCase().includes(q)) &&
        (!v.unit || (R.unitOf(e) || {}).id === v.unit || (R.unitOf(e) || {}).parent_id === v.unit));
      const g = ui.grid([{ key: "code", label: t("field.code"), type: "code", width: 80, frozen: true, total: "count" }, { key: "preferred_name", label: t("field.preferred_name"), width: 170, frozen: true },
        { key: "job", label: t("field.job_id"), width: 150, value: (e) => R.name(R.jobOf(e)) },
        ...skillCols.map((k) => ({ key: "s_" + k.code, label: k.code, title: k.name, width: 96, align: "center", render: (e) => cell(e, k), value: (e) => { const x = held.get(e.id + "|" + k.id); return x ? x.level : ""; },
          total: (vis) => t("qual.holders_n", { n: vis.filter((e) => { const x = held.get(e.id + "|" + k.id); return x && qState(x, today) !== "expired"; }).length }) }))],
      { rows, rowKey: "id", selection: "single", totals: true, rowHeight: 32, autofit: false, emptyText: skillCols.length ? t("empty") : t("qual.no_skills") });
      g.el.classList.add("hr-roster");
      ui.clear(host, g.el);
    } catch (e) { ui.clear(host, ui.empty({ icon: "x-octagon", title: e.message })); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Discipline (phase 6): the penalty schedule, violations, decisions
const penaltyText = (p) => {
  if (!p) return "";
  if (p.startsWith("deduct:")) { const d = Number(p.slice(7)); return t("penalty.deduct", { days: d % 1 ? d.toFixed(2).replace(/0$/, "") : d }); }
  return has("penalty." + p) ? t("penalty." + p) : p;
};
const VSTATE = { proposed: "idle", approved: "bad", waived: "neutral" };
const rulesScreen = registerScreen("penalty_rule", "DSC1010", "nav.penalty_rules", () => [
  { key: "code", label: t("field.code"), type: "code", width: 100, frozen: true, total: "count" }, { key: "name", label: t("field.name"), width: 220 },
  { key: "violation", label: t("field.violation"), width: 150, value: (r) => t("violation." + r.violation) },
  { key: "threshold_minutes", label: t("field.threshold_minutes"), type: "number", width: 110 }, { key: "window_days", label: t("field.window_days"), type: "number", width: 110 },
  { key: "steps", label: t("field.steps"), width: 380, value: (r) => (r.steps || "").split(",").map((s, i) => (i + 1) + ". " + penaltyText(s.trim())).join("   ") },
  { key: "active", label: t("field.active"), width: 90, value: (r) => (r.active ? t("yes") : t("no")) },
], { write: "hr.discipline.write", group: "g.discipline", rows: (R) => R.rules, people: false, icon: "scale",
  extra: (r) => ui.section(t("field.steps"), h("ol", { class: "hr-steps" }, (r.steps || "").split(",").map((s) => h("li", { text: penaltyText(s.trim()) })))) });

function violationsScreen({ shell }) {
  let R = null;
  const today = localToday();
  const conds = ui.conditionPanel([
    { key: "days", label: t("cmp.period"), type: "daterange", default: [addDays(today, -60), today], span: 2 },
    { key: "status", label: t("field.status"), type: "select", options: Object.keys(VSTATE).map((k) => [k, t("vstatus." + k)]), placeholder: t("all") },
    { key: "text", label: t("find.person"), placeholder: t("find.person_ph") }], { key: "DSC2010", onSubmit: () => load() });
  const g = ui.grid([
    { key: "status", label: t("field.status"), type: "status", width: 120, frozen: true, status: (r) => VSTATE[r.status], label_of: (s, r) => t("vstatus." + r.status) },
    { key: "employee", label: t("field.employee_id"), width: 200, value: (r) => R.label(R.byId.get(r.employee_id)) },
    { key: "work_date", label: t("plan.day"), type: "date", width: 104 },
    { key: "rule", label: t("field.rule_id"), width: 170, value: (r) => R.name(R.byId.get(r.rule_id)) },
    { key: "minutes", label: t("field.minutes"), type: "number", width: 90 },
    { key: "occurrence", label: t("field.occurrence"), type: "number", width: 90 },
    { key: "proposed", label: t("field.proposed"), width: 170, value: (r) => penaltyText(r.proposed) },
    { key: "decision", label: t("field.decision"), width: 170, value: (r) => penaltyText(r.decision) },
    { key: "days", label: t("field.deducted_days"), type: "number", digits: 2, width: 110, total: "sum", value: (r) => (r.status === "approved" && (r.decision || "").startsWith("deduct:") ? Number(r.decision.slice(7)) : 0) },
    { key: "decided_by", label: t("field.decided_by"), type: "code", width: 120 }, { key: "decided_on", label: t("field.decided_on"), type: "date", width: 110 },
    { key: "source", label: t("field.source"), width: 110, value: (r) => t("vsource." + (r.source || "manual")) },
    { key: "note", label: t("field.note"), width: 260 },
  ], { rowKey: "id", selection: "single", totals: true, layoutKey: "DSC2010", emptyText: t("disc.empty"), rowStatus: (r) => (r.status === "approved" ? "down" : null),
    presets: [{ id: "waiting", label: t("vstatus.proposed"), test: (r) => r.status === "proposed" }, { id: "deduct", label: t("disc.deductions"), test: (r) => r.status === "approved" && (r.decision || "").startsWith("deduct:") },
      { id: "late", label: t("violation.late"), test: (r) => (R.byId.get(r.rule_id) || {}).violation === "late" }, { id: "absence", label: t("violation.absence"), test: (r) => (R.byId.get(r.rule_id) || {}).violation === "absence" }],
    onSelect: (sel) => { const v = sel[0]; act.decide.disabled = !v || v.status !== "proposed" || !can("hr.discipline.approve"); },
    onOpen: (r) => r.status === "proposed" && can("hr.discipline.approve") && decide(r) });
  const act = {
    propose: ui.button({ label: t("disc.propose"), icon: "sparkles", kind: "primary", disabled: !can("hr.discipline.write"), onClick: () => propose() }),
    add: ui.button({ label: t("new.violation"), icon: "plus", disabled: !can("hr.discipline.write"), onClick: () => editRecord("violation", null, { work_date: today }).then((ok) => ok && load()) }),
    decide: ui.button({ label: t("disc.decide"), icon: "scale", disabled: true, onClick: () => decide(g.selected()[0]) }),
  };
  const sc = screen({ code: "DSC2010", title: t("nav.violations"), path: [t("g.discipline")], shell, toolbar: [act.propose, act.add, act.decide],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("violations"), exportLabel: t("export"), columns: () => g.columnsDialog() },
    conditions: conds, grid: g, note: h("div", { class: "hr-pad" }, ui.banner("info", t("disc.rule_note"))) });
  function propose() {
    const a = ui.input({ type: "date", value: addDays(today, -30) }), b = ui.input({ type: "date", value: addDays(today, -1) }), out = h("div");
    ui.dialog({ title: t("disc.propose"), icon: "sparkles", width: 520, body: h("div", { class: "hr-stack" }, h("p", { class: "eco-dialog-text", text: t("disc.propose_help") }),
      h("div", { class: "eco-form" }, ui.field(t("from"), a, { required: true }), ui.field(t("to"), b, { required: true })), out),
    actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("disc.propose"), kind: "primary", icon: "sparkles", onClick: async () => {
      try { const r = await api("POST", "/api/discipline/propose", { from: a.value, to: b.value }); ui.toast({ kind: "ok", title: t("disc.proposed_n", { n: r.proposed.length }), text: t("disc.checked_n", { n: r.checked_days }), keep: true }); load(); return true; }
      catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
    } }] });
  }
  function decide(v) {
    const emp = R.byId.get(v.employee_id), rule = R.byId.get(v.rule_id) || {};
    const steps = (rule.steps || "").split(",").map((s) => s.trim()).filter(Boolean);
    const options = [...new Set([v.proposed, ...steps, "warning", "final_warning", "investigation"].filter(Boolean))];
    const pick = ui.select({ options: options.map((p) => [p, penaltyText(p) + (p === v.proposed ? " · " + t("disc.schedule_says") : "")]), value: v.proposed });
    const note = h("textarea", { class: "eco-input", rows: 3, placeholder: t("disc.note_ph") });
    const mode = ui.segmented({ value: "approved", options: [["approved", t("disc.apply"), "scale"], ["waived", t("disc.waive"), "check"]], onChange: (x) => { mode.value_ = x; row.hidden = x !== "approved"; } });
    mode.value_ = "approved";
    const row = ui.field(t("field.decision"), pick);
    const out = h("div");
    ui.dialog({ title: t("disc.decide") + " · " + (emp ? emp.preferred_name || emp.code : ""), subtitle: v.work_date + " · " + (rule.name || "") + (v.minutes ? " · " + t("disc.minutes_n", { n: v.minutes }) : ""),
      icon: "scale", width: 560, body: h("div", { class: "hr-stack" },
        ui.props([[t("field.occurrence"), t("disc.nth", { n: v.occurrence || 1, days: rule.window_days || 30 })], [t("field.proposed"), penaltyText(v.proposed)]]),
        mode, row, ui.field(t("field.note"), note, { hint: t("disc.note_hint") }), ui.banner("info", t("disc.final")), out),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("disc.record"), kind: "primary", icon: "save", onClick: async () => {
        const fields = mode.value_ === "approved" ? { status: "approved", decision: pick.value, note: note.value } : { status: "waived", note: note.value };
        try { await api("PUT", "/api/violation/" + encodeURIComponent(v.code), { fields, expected_ver: v.ver }); ui.toast({ kind: "ok", title: t("saved"), text: v.code, keep: true }); load(); return true; }
        catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
      } }] });
  }
  async function load() {
    const t0 = performance.now();
    g.setLoading();
    try {
      R = await refs(true);
      const v = conds.values(), q = (v.text || "").toLowerCase();
      const rows = await api("GET", "/api/violation");
      g.setRows(rows.filter((r) => (!v.days[0] || r.work_date >= v.days[0]) && (!v.days[1] || r.work_date <= v.days[1]) && (!v.status || r.status === v.status)
        && (!q || R.label(R.byId.get(r.employee_id)).toLowerCase().includes(q))).sort((a, b) => b.work_date.localeCompare(a.work_date)));
      sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
    } catch (e) { g.setError(e.message); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Attendance (the migrated application, behind the same sign-in)
function attendanceScreen({ shell }) {
  const note = h("div");
  const sc = screen({ code: "ATT2010", title: t("nav.attendance"), path: [t("g.people")], shell,
    toolbar: [ui.button({ label: t("att.open_new"), icon: "expand", onClick: () => window.open("/attendance", "_blank", "noopener") })],
    standard: { inquiry: () => { frame.src = "/attendance"; }, inquiryLabel: t("refresh"), inquiryIcon: "refresh" },
    body: h("div", { class: "hr-attendance" }, note, h("iframe", { class: "hr-attendance-frame", src: "/attendance", title: t("nav.attendance") })) });
  const frame = sc.el.querySelector("iframe");
  if (can("admin.system.read")) api("GET", "/api/admin/health").then((hh) => { if (hh.attendance && hh.attendance.excel_desktop === false) ui.clear(note, h("div", { class: "hr-pad" }, ui.banner("warn", t("attendance.no_excel")))); }).catch(() => {});
  return { el: sc.el };
}

// ------------------------------------------------------------------ Users and profiles
function usersScreen({ shell }) {
  let profiles = [];
  const detail = h("div", { class: "hr-detail" });
  const conds = ui.conditionPanel([{ key: "text", label: t("find.user"), placeholder: t("find.user_ph") },
    { key: "profile", label: t("user.profile"), type: "select", options: [], placeholder: t("all") },
    { key: "active", label: t("user.active"), type: "select", options: [["1", t("yes")], ["0", t("no")]], placeholder: t("all") }], { key: "SEC9010", onSubmit: () => load() });
  const g = ui.grid([
    { key: "active", label: t("user.state"), type: "status", width: 100, frozen: true, status: (r) => (r.active ? "ok" : "neutral"), label_of: (s, r) => (r.active ? t("user.active") : t("user.inactive")) },
    { key: "code", label: t("user.username"), type: "code", width: 140, frozen: true, total: "count" },
    { key: "display_name", label: t("user.display_name"), width: 200, render: (r) => h("span", { class: "hr-person" }, ui.avatar(r.display_name || r.code, 22), h("span", { text: r.display_name || "" })) },
    { key: "profile", label: t("user.profile"), width: 150, value: (r) => profileName(r.profile) },
    { key: "must_change", label: t("user.must_change"), width: 150, value: (r) => (r.must_change ? t("yes") : t("no")) },
    { key: "updated_at", label: t("rec.updated"), type: "date", width: 140, value: (r) => (r.updated_at || "").slice(0, 16).replace("T", " ") },
  ], { rowKey: "code", selection: "single", layoutKey: "SEC9010", onSelect: (sel) => draw(sel[0]) });
  const sc = screen({ code: "SEC9010", title: t("nav.users"), path: [t("g.security")], shell,
    toolbar: [ui.button({ label: t("user.new"), icon: "user-plus", kind: "primary", onClick: () => create() })],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("users"), exportLabel: t("export") },
    conditions: conds, grid: g, detail, detailKey: "SEC9010:detail" });
  function draw(u) {
    if (!u) { ui.clear(detail, ui.empty({ icon: "user", title: t("user.none") })); return; }
    const prof = ui.select({ options: profiles.map((p) => [p.code, profileName(p.code, p.name)]), value: u.profile });
    const active = ui.toggle({ label: t("user.active"), checked: !!u.active, hint: t("user.active_hint") });
    const perms = (profiles.find((p) => p.code === u.profile) || { perms: [] }).perms;
    ui.clear(detail,
      h("div", { class: "hr-profile" }, ui.avatar(u.display_name || u.code, 52), h("div", { class: "hr-profile-text" }, h("h2", { text: u.display_name || u.code }),
        h("div", { class: "eco-muted" }, ui.ltr(u.code), " · ", profileName(u.profile)), h("div", { class: "hr-row" }, ui.statusChip(u.active ? "ok" : "neutral", u.active ? t("user.active") : t("user.inactive")),
          u.must_change ? ui.badge(t("user.must_change"), "warn", "key") : null))),
      ui.section(t("user.access"), h("div", { class: "hr-stack" }, ui.field(t("user.profile"), prof), active,
        h("div", { class: "hr-row" }, ui.button({ label: t("save"), icon: "save", kind: "primary", onClick: async () => {
          try { await api("PATCH", "/api/admin/users/" + encodeURIComponent(u.code), { fields: { profile: prof.value, active: active.querySelector("input").checked ? 1 : 0 }, expected_ver: u.ver }); ui.toast({ kind: "ok", title: t("saved"), text: u.code }); load(u.code); }
          catch (e) { fail(e); }
        } }), ui.button({ label: t("user.reset_password"), icon: "key", onClick: () => resetPw(u) })))),
      u.profile !== "administrator" && sodConflicts(perms).length ? h("div", { class: "hr-pad" }, ui.banner("warn", sodConflicts(perms).map(([a, b]) => t("perm." + a) + " + " + t("perm." + b)).join(" · "), { title: t("sod.title") })) : null,
      ui.section(t("user.rights", { n: perms.length }), h("div", { class: "hr-perm-list" }, perms.map((p) => h("span", { class: "hr-perm" }, ui.icon("check", 12), h("span", { text: t("perm." + p) }))))));
  }
  async function resetPw(u) {
    const pw = await ui.promptValue({ title: t("user.reset_password"), label: t("user.new_password_for", { user: u.code }), type: "password", hint: t("user.password_rule") });
    if (!pw) return;
    try { await api("POST", "/api/admin/users/" + encodeURIComponent(u.code) + "/password", { password: pw }); ui.toast({ kind: "ok", text: t("user.password_was_reset") }); }
    catch (e) { fail(e); }
  }
  function create() {
    const nu = ui.input({ dir: "ltr" }), nd = ui.input(), np = ui.input({ type: "password" }), prof = ui.select({ options: profiles.map((p) => [p.code, profileName(p.code, p.name)]), value: "viewer" });
    const out = h("div", { class: "eco-span-2" });
    ui.dialog({ title: t("user.new"), icon: "user-plus", width: 560, body: h("div", { class: "eco-form" }, ui.field(t("user.username"), nu, { required: true, hint: t("user.username_hint") }), ui.field(t("user.display_name"), nd, { required: true }),
      ui.field(t("user.first_password"), np, { required: true, hint: t("user.password_rule") }), ui.field(t("user.profile"), prof, { required: true }), out),
    actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("user.create"), kind: "primary", icon: "check", onClick: async () => {
      try { await api("POST", "/api/admin/users", { username: nu.value, display_name: nd.value, password: np.value, profile: prof.value }); ui.toast({ kind: "ok", title: t("user.created"), text: nu.value, keep: true }); load(nu.value.trim().toLowerCase()); return true; }
      catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
    } }] });
  }
  async function load(select) {
    const t0 = performance.now();
    g.setLoading();
    try {
      const [users, profs] = await Promise.all([api("GET", "/api/admin/users"), api("GET", "/api/admin/profiles")]);
      profiles = profs;
      const v = conds.values();
      fillOptions(conds.control("profile"), profiles.map((p) => ({ id: p.code, code: p.code, name: profileName(p.code, p.name) })), v.profile);
      const q = (v.text || "").toLowerCase();
      g.setRows(users.filter((u) => (!q || (u.code + " " + (u.display_name || "")).toLowerCase().includes(q)) && (!v.profile || u.profile === v.profile) && (v.active === "" || v.active === undefined || String(u.active ? 1 : 0) === v.active)));
      sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
      const pick = select && g.view().find((u) => u.code === select) ? select : (g.view()[0] || {}).code;
      if (pick) g.select(pick);
    } catch (e) { g.setError(e.message); }
  }
  load();
  return { el: sc.el };
}
// ------------------------------------------------------------------ rights: segregation of duties and role templates (ideas from Mizan)
// Two rights one person should not hold together (the administrator profile is exempt: it holds every right by rule).
const SOD = [["admin.users.manage", "hr.employees.write"], ["hr.employees.delete", "admin.backup.restore"], ["hr.discipline.write", "hr.discipline.approve"]];
const sodConflicts = (perms) => SOD.filter(([a, b]) => perms.includes(a) && perms.includes(b));
const READS = ["hr.org.read", "hr.employees.read", "hr.attendance.read", "hr.shifts.read", "hr.skills.read"];
// starting points for a new profile or for resetting one; the person still ticks and saves (no hidden rights)
const TEMPLATES = {
  viewer: READS,
  hr_clerk: [...READS, "hr.employees.write", "hr.attendance.upload", "hr.import.run", "hr.discipline.read", "hr.discipline.write"],
  planner: [...READS, "hr.shifts.write"],
  skills_coordinator: [...READS, "hr.skills.write"],
  auditor: [...READS, "admin.audit.read", "admin.system.read", "hr.discipline.read"],
  line_manager: [...READS, "hr.discipline.read", "hr.discipline.approve"],
  it_admin: ["hr.org.read", "admin.users.manage", "admin.audit.read", "admin.system.read", "admin.settings.manage", "admin.backup.manage"],
};
// the matrix: one row per object, one cell per action (Mizan's role editor)
const PERM_ACTIONS = ["read", "write", "approve", "delete", "upload", "restore", "run", "manage"];
const permSplit = (p) => { const i = p.lastIndexOf("."); return { object: p.slice(0, i), action: p.slice(i + 1) }; };

// ------------------------------------------------------------------ the Advisor: daily checks with the reason and what to do (Mizan's advisor, for people)
// Computed in the browser from what the person may already read: it never shows a record the person could not open.
async function advisorFindings() {
  const R = await refs(true), today = localToday(), out = [];
  const opt = (perm, path) => (can(perm) ? api("GET", path).catch(() => null) : Promise.resolve(null));
  const [asg, quals, hh, users, profs, st, viol] = await Promise.all([opt("hr.shifts.read", "/api/shift_assignment"), opt("hr.skills.read", "/api/employee_skill"), opt("admin.system.read", "/api/admin/health"),
    opt("admin.users.manage", "/api/admin/users"), opt("admin.users.manage", "/api/admin/profiles"), opt("admin.settings.manage", "/api/admin/settings"), opt("hr.discipline.read", "/api/violation")]);
  const who = (e) => (e ? e.code + " · " + (e.preferred_name || "") : "");
  const person = (e, sub) => ({ label: who(e), sub, screen: "EMP1010" });
  const add = (id, severity, area, items, vars = {}, screen) => { if (items === true || (items && items.length)) out.push({ id, severity, area, items: items === true ? [] : items, vars: { n: items === true ? 0 : items.length, ...vars }, screen }); };
  const staff = R.employees.filter((e) => e.employment_status !== "Terminated");
  // people
  const holders = new Map();
  staff.forEach((e) => { if (e.position_id) holders.set(e.position_id, (holders.get(e.position_id) || []).concat([e])); });
  add("position_shared", "error", "people", [...holders.entries()].filter(([, es]) => es.length > 1).flatMap(([p, es]) => es.map((e) => person(e, (R.byId.get(p) || {}).code))), {}, "EMP1010");
  add("unplaced", "warning", "people", staff.filter((e) => !e.position_id).map((e) => person(e, value(e.employment_status))), {}, "EMP1010");
  add("no_hire_date", "warning", "people", staff.filter((e) => !e.hire_date).map((e) => person(e)), {}, "EMP1010");
  add("left_not_closed", "error", "people", staff.filter((e) => e.termination_date && e.termination_date < today).map((e) => person(e, e.termination_date)), {}, "EMP1010");
  add("terminated_no_date", "warning", "people", R.employees.filter((e) => e.employment_status === "Terminated" && !e.termination_date).map((e) => person(e)), {}, "EMP1010");
  add("manager_gone", "warning", "people", staff.filter((e) => { const m = R.byId.get(e.manager_id); return e.manager_id && (!m || m.employment_status === "Terminated"); }).map((e) => person(e)), {}, "EMP1010");
  // organisation
  add("vacant_positions", "tip", "organisation", R.positions.filter((p) => !holders.has(p.id)).map((p) => ({ label: p.code + " · " + R.name(R.byId.get(p.job_id)), sub: R.name(R.byId.get(p.org_unit_id)), screen: "ORG1030" })), {}, "ORG1030");
  add("empty_units", "tip", "organisation", R.units.filter((u) => (u.type === "department" || u.type === "section") && !R.positions.some((p) => p.org_unit_id === u.id) && !R.units.some((x) => x.parent_id === u.id))
    .map((u) => ({ label: u.code + " · " + (u.name || ""), sub: value(u.type), screen: "ORG1010" })), {}, "ORG1010");
  // planning
  if (asg) {
    const live = asg.filter((a) => a.valid_from <= today && (!a.valid_to || a.valid_to >= today));
    add("terminated_planned", "error", "planning", live.filter((a) => (R.byId.get(a.employee_id) || {}).employment_status === "Terminated").map((a) => person(R.byId.get(a.employee_id), a.code)), {}, "SHF2010");
    if (asg.length) add("not_planned", "warning", "planning", staff.filter((e) => e.employment_status === "Active" && !live.some((a) => a.employee_id === e.id && a.kind === "regular")).map((e) => person(e)), {}, "SHF2010");
    add("ending_soon", "tip", "planning", asg.filter((a) => a.valid_to && a.valid_to >= today && a.valid_to <= addDays(today, 14)).map((a) => person(R.byId.get(a.employee_id), a.valid_to)), { days: 14 }, "SHF2010");
  }
  // skills
  if (quals) {
    const active = (q) => (R.byId.get(q.employee_id) || {}).employment_status === "Active";
    const qItem = (q) => ({ label: who(R.byId.get(q.employee_id)), sub: R.label(R.byId.get(q.skill_id)) + " · " + (q.expires_on || ""), screen: "SKL2010" });
    add("qual_expired", "error", "skills", quals.filter((q) => active(q) && qState(q, today) === "expired").map(qItem), {}, "SKL2010");
    add("qual_expiring", "warning", "skills", quals.filter((q) => active(q) && qState(q, today) === "expiring").map(qItem), { days: 30 }, "SKL2010");
  }
  // discipline: a decision is due within 30 days of finding the violation
  if (viol) {
    const waiting = viol.filter((v) => v.status === "proposed");
    const age = (v) => Math.floor((new Date(today) - new Date((v.created_at || today).slice(0, 10))) / 864e5);
    const vItem = (v) => ({ label: who(R.byId.get(v.employee_id)), sub: v.work_date + " · " + ((R.byId.get(v.rule_id) || {}).name || ""), screen: "DSC2010" });
    add("decision_due", "warning", "discipline", waiting.filter((v) => age(v) >= 20).map(vItem), { days: 30 }, "DSC2010");
    add("decision_waiting", "tip", "discipline", waiting.filter((v) => age(v) < 20).map(vItem), {}, "DSC2010");
  }
  // security
  if (users && profs) {
    const byProf = new Map(profs.map((p) => [p.code, p]));
    const risky = users.filter((u) => u.active && u.profile !== "administrator" && sodConflicts([...((byProf.get(u.profile) || {}).perms || []), ...(u.extra_perms || [])]).length);
    add("sod", "error", "security", risky.map((u) => ({ label: u.code + " · " + (u.display_name || ""), sub: profileName(u.profile), screen: "SEC9010" })), {}, "SEC9020");
    const admins = users.filter((u) => u.active && u.profile === "administrator");
    if (admins.length === 1) add("one_admin", "tip", "security", admins.map((u) => ({ label: u.code + " · " + (u.display_name || ""), screen: "SEC9010" })), {}, "SEC9010");
    add("must_change", "tip", "security", users.filter((u) => u.active && u.must_change).map((u) => ({ label: u.code + " · " + (u.display_name || ""), screen: "SEC9010" })), {}, "SEC9010");
  }
  // system
  if (hh) {
    if (!hh.journal.ok || !hh.audit.ok) add("chain_broken", "error", "system", true, {}, "SYS9100");
    const last = hh.last_backup, hours = st ? st.backup_hours : 24;
    if (!last) add("no_backup", "error", "system", true, {}, "SYS9070");
    else if (last.rehearsal && !last.rehearsal.ok) add("backup_failed", "error", "system", [{ label: last.name, sub: (last.created_at || "").slice(0, 16).replace("T", " "), screen: "SYS9070" }], {}, "SYS9070");
    else if ((Date.now() - new Date(last.created_at).getTime()) / 36e5 > Math.max(2 * hours, 26)) add("backup_old", "warning", "system", [{ label: last.name, sub: (last.created_at || "").slice(0, 16).replace("T", " "), screen: "SYS9070" }], { hours }, "SYS9070");
    if (hh.recovery && !hh.recovery.intact) add("recovery_damaged", "error", "system", true, {}, "SYS9100");
    else if (!hh.recovery) add("recovery_missing", "tip", "system", true, {}, "SYS9100");
  }
  if ((S.info.company || {}).provisional) add("company_provisional", "tip", "system", true, {}, "SYS9060");
  const rank = { error: 0, warning: 1, tip: 2 };
  return out.sort((a, b) => rank[a.severity] - rank[b.severity]);
}
const ADV_AREAS = ["people", "organisation", "planning", "skills", "discipline", "security", "system"];
function adviceCard(f, shell) {
  const words = (part) => (has("adv." + f.id + "." + part) ? t("adv." + f.id + "." + part, f.vars) : null);
  return ui.advice({ severity: f.severity, title: words("title"), tags: [t("adv.area." + f.area)], body: words("body"), fix: words("fix"), basis: words("basis"),
    items: f.items.map((it) => ({ label: it.label, sub: it.sub, onClick: it.screen && shell.screens[it.screen] ? () => shell.open(it.screen) : null })),
    action: f.screen && shell.screens[f.screen] ? { label: t("adv.open", { screen: shell.screens[f.screen].title }), onClick: () => shell.open(f.screen) } : null });
}
function advisorScreen({ shell }) {
  const body = h("div", { class: "hr-page hr-advisor" });
  let area = "all", found = [];
  const sc = screen({ code: "ADV1010", title: t("nav.advisor"), path: [t("g.people")], shell, standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", print: () => print(), printLabel: t("print") }, body });
  function draw() {
    const count = (s) => found.filter((f) => f.severity === s).length;
    const list = found.filter((f) => area === "all" || f.area === area);
    const areas = ui.segmented({ value: area, options: [["all", ui.kitText("all") + " · " + found.length]].concat(ADV_AREAS.filter((a) => found.some((f) => f.area === a)).map((a) => [a, t("adv.area." + a) + " · " + found.filter((f) => f.area === a).length])),
      onChange: (v) => { area = v; draw(); } });
    ui.clear(body,
      h("div", { class: "hr-kpis hr-kpis-3" }, [["error", "x-octagon", "bad"], ["warning", "alert", "warn"], ["tip", "lightbulb", "info"]].map(([s, ic, st]) =>
        ui.kpi({ label: t("adv.count." + s), value: String(count(s)), icon: ic, status: count(s) ? st : "ok" }))),
      found.length ? areas : null,
      list.length ? h("div", { class: "hr-stack" }, list.map((f) => adviceCard(f, shell)))
        : ui.card({ body: h("div", { class: "hr-row hr-allclear" }, ui.icon("shield", 28, "hr-ok"), h("div", {}, h("strong", { text: ui.kitText("all_clear") }), h("p", { class: "eco-muted", text: t("adv.all_clear_text") }))) }),
      h("p", { class: "eco-muted hr-small", text: t("adv.disclaimer") }));
  }
  async function load() {
    ui.clear(body, h("div", { class: "hr-loading" }, h("span", { class: "eco-spinner" })));
    try { found = await advisorFindings(); draw(); } catch (e) { ui.clear(body, ui.banner("bad", e.message)); }
  }
  load();
  return { el: sc.el, onActivate: () => { if (S.refs === null) load(); } };
}

const PERM_GROUPS = [["perm_group.people",["hr.employees.read", "hr.employees.write", "hr.employees.delete", "hr.recycle.restore", "hr.import.run"]],
  ["perm_group.organisation", ["hr.org.read", "hr.org.write"]], ["perm_group.attendance", ["hr.attendance.read", "hr.attendance.upload"]],
  ["perm_group.planning", ["hr.shifts.read", "hr.shifts.write"]], ["perm_group.recruitment", ["hr.recruitment.read", "hr.recruitment.write", "hr.recruitment.approve"]],
  ["perm_group.overtime", ["hr.overtime.read", "hr.overtime.write", "hr.overtime.approve"]], ["perm_group.payroll", ["hr.payroll.read", "hr.payroll.write", "hr.payroll.run", "hr.payroll.approve"]], ["perm_group.training", ["hr.training.read", "hr.training.write"]],
  ["perm_group.leave", ["hr.leave.read", "hr.leave.write", "hr.leave.approve"]], ["perm_group.skills", ["hr.skills.read", "hr.skills.write"]], ["perm_group.discipline", ["hr.discipline.read", "hr.discipline.write", "hr.discipline.approve"]],
    ["perm_group.administration", ["admin.users.manage", "admin.audit.read", "admin.system.read", "admin.settings.manage"]], ["perm_group.backups", ["admin.backup.manage", "admin.backup.restore"]]];
function profilesScreen({ shell }) {
  let profiles = [], users = [], current = null, work = null;
  const list = h("div", { class: "hr-plist" }), matrix = h("div", { class: "hr-matrix" });
  const sc = screen({ code: "SEC9020", title: t("nav.profiles"), path: [t("g.security")], shell,
    toolbar: [ui.button({ label: t("prof.new"), icon: "plus", kind: "primary", onClick: () => create() })],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh" },
    body: ui.split(h("div", { class: "hr-side" }, h("div", { class: "hr-side-head" }, h("strong", { text: t("profile.title") })), list), matrix, { key: "SEC9020:side", initial: 280, min: 220, second: false }) });
  const known = new Set(PERM_GROUPS.flatMap(([, ps]) => ps));
  const usersOf = (code) => users.filter((u) => u.profile === code && u.active);
  function draw() {
    ui.clear(list, profiles.map((p) => {
      const risk = p.code !== "administrator" && sodConflicts(p.perms).length;
      return h("button", { type: "button", class: ["hr-plist-item", current && current.code === p.code && "is-on"], onclick: () => { current = p; work = null; draw(); } },
        h("span", { class: "hr-plist-icon" }, ui.icon(p.code === "administrator" ? "shield" : "users", 16)),
        h("div", {}, h("b", { text: profileName(p.code, p.name) }), h("small", { class: "eco-muted", text: t("user.rights", { n: p.perms.length }) + " · " + t("prof.users_n", { n: usersOf(p.code).length }) })),
        risk ? ui.icon("alert", 15, "hr-warn") : null);
    }));
    if (!current) { ui.clear(matrix, ui.empty({ icon: "shield", title: t("pick.one") })); return; }
    const locked = current.code === "administrator";
    work = work || new Set(current.perms);
    const conflicts = locked ? [] : sodConflicts([...work]);
    const dirty = [...work].sort().join() !== [...current.perms].sort().join();
    const toggle = (p) => { if (locked) return; work.has(p) ? work.delete(p) : work.add(p); draw(); };
    // Mizan's role editor: one section per area, one row per object, one pill per action
    const sections = PERM_GROUPS.map(([gk, perms]) => {
      const objects = [...new Set(perms.map((p) => permSplit(p).object))];
      const on = perms.filter((p) => work.has(p)).length;
      return h("section", { class: ["hr-pm-section", !on && "is-off"] },
        h("header", {}, h("strong", { text: t(gk) }), h("span", { class: "eco-count", text: on + " / " + perms.length }), h("span", { class: "eco-grow" }),
          locked ? null : ui.button({ label: on === perms.length ? t("prof.none") : t("prof.all"), kind: "ghost", size: "sm", onClick: () => { perms.forEach((p) => (on === perms.length ? work.delete(p) : work.add(p))); draw(); } })),
        h("table", {}, h("tbody", {}, objects.map((obj) => h("tr", {}, h("th", {}, h("span", { text: t("perm_obj." + obj) }), h("small", { class: "eco-muted" }, ui.ltr(obj))),
          h("td", {}, h("div", { class: "hr-pm-cells" }, perms.filter((p) => permSplit(p).object === obj).sort((a, b) => PERM_ACTIONS.indexOf(permSplit(a).action) - PERM_ACTIONS.indexOf(permSplit(b).action)).map((p) =>
            h("button", { type: "button", class: ["hr-pm-cell", work.has(p) && "is-on"], role: "checkbox", "aria-checked": String(work.has(p)), disabled: locked, title: t("perm." + p), onclick: () => toggle(p) },
              ui.icon(work.has(p) ? "check" : "plus", 13), h("span", { text: t("perm_act." + permSplit(p).action) }))))))))));
    });
    const people = usersOf(current.code);
    ui.clear(matrix,
      h("div", { class: "hr-record-head" }, h("span", { class: "hr-record-icon" }, ui.icon("shield", 20)),
        h("div", { class: "hr-record-titles" }, h("div", { class: "eco-muted" }, ui.ltr(current.code), current.builtin ? " · " + t("prof.builtin") : ""), h("h2", { text: profileName(current.code, current.name) })),
        locked ? null : ui.button({ label: t("prof.template"), icon: "copy", onClick: (ev) => ui.menu(ev.currentTarget, [{ header: t("prof.template_hint") }].concat(Object.keys(TEMPLATES).map((k) => ({ label: t("template." + k), icon: "users",
          onSelect: () => { work = new Set(TEMPLATES[k]); draw(); } })))) }),
        locked ? null : ui.button({ label: t("reset"), icon: "x", disabled: !dirty, onClick: () => { work = null; draw(); } }),
        locked ? null : ui.button({ label: t("save"), icon: "save", kind: "primary", disabled: !dirty, onClick: async () => {
          try { await api("PUT", "/api/admin/profiles/" + current.code, { name: current.name, perms: [...work], expected_ver: current.ver }); ui.toast({ kind: "ok", title: t("saved"), text: profileName(current.code, current.name) }); work = null; load(current.code); }
          catch (e) { fail(e); }
        } })),
      locked ? h("div", { class: "hr-pad" }, ui.banner("info", t("profile.admin_locked"))) : null,
      conflicts.length ? h("div", { class: "hr-pad" }, ui.banner("warn", conflicts.map(([a, b]) => t("perm." + a) + " + " + t("perm." + b)).join(" · "), { title: t("sod.title") }),
        h("p", { class: "eco-muted hr-small", text: t("sod.why") })) : null,
      dirty ? h("div", { class: "hr-pad" }, ui.banner("info", t("prof.unsaved"))) : null,
      h("div", { class: "hr-pm" }, sections),
      ui.section(t("prof.people", { n: people.length }), people.length ? h("div", { class: "hr-people" }, people.map((u) => h("span", { class: "hr-person" }, ui.avatar(u.display_name || u.code, 20), h("span", { text: u.display_name || u.code }))))
        : h("span", { class: "eco-muted", text: t("none") })),
      [...work].some((p) => !known.has(p)) ? h("div", { class: "hr-pad" }, ui.banner("info", t("prof.other_rights"))) : null);
  }
  function create() {
    const code = ui.input({ dir: "ltr", placeholder: "planner_day" }), name = ui.input(), from = ui.select({ options: Object.keys(TEMPLATES).map((k) => [k, t("template." + k)]), value: "viewer" });
    const out = h("div", { class: "eco-span-2" });
    ui.dialog({ title: t("prof.new"), icon: "shield", width: 560, body: h("div", { class: "eco-form" }, ui.field(t("prof.code"), code, { required: true, hint: t("prof.code_hint") }), ui.field(t("prof.name"), name, { required: true }),
      h("div", { class: "eco-span-2" }, ui.field(t("prof.template"), from, { hint: t("prof.template_hint") })), out),
    actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("prof.create"), kind: "primary", icon: "check", onClick: async () => {
      const c = code.value.trim().toLowerCase();
      if (!/^[a-z][a-z0-9_]{2,30}$/.test(c)) { ui.clear(out, ui.banner("bad", t("prof.code_hint"))); return false; }
      if (profiles.some((p) => p.code === c)) { ui.clear(out, ui.banner("bad", t("prof.exists"))); return false; }
      if (!name.value.trim()) { ui.clear(out, ui.banner("bad", t("prof.name_required"))); return false; }
      try { await api("PUT", "/api/admin/profiles/" + c, { name: name.value.trim(), perms: TEMPLATES[from.value], expected_ver: null }); ui.toast({ kind: "ok", title: t("saved"), text: name.value, keep: true }); load(c); return true; }
      catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; }
    } }] });
  }
  async function load(keep) {
    try {
      [profiles, users] = await Promise.all([api("GET", "/api/admin/profiles"), api("GET", "/api/admin/users").catch(() => [])]);
      current = profiles.find((p) => p.code === (keep || (current && current.code))) || profiles.find((p) => p.code === "hr_officer") || profiles[0];
      work = null; draw();
    } catch (e) { ui.clear(matrix, ui.empty({ icon: "x-octagon", title: e.message })); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Audit and security
function auditScreen({ shell }) {
  const detail = h("div", { class: "hr-detail" }), integrity = h("div");
  const conds = ui.conditionPanel([
    { key: "category", label: t("audit.category"), type: "select", options: [["security", t("audit.cat.security")], ["system", t("audit.cat.system")], ["data", t("audit.cat.data")]], placeholder: t("all") },
    { key: "actor", label: t("audit.actor"), placeholder: t("audit.actor_ph") }, { key: "event", label: t("audit.event"), placeholder: t("audit.event_ph") },
    { key: "limit", label: t("audit.limit"), type: "select", options: [["200", "200"], ["500", "500"], ["1000", "1000"]], default: "200", required: true },
  ], { key: "SEC9030", onSubmit: () => load() });
  const g = ui.grid([
    { key: "seq", label: "#", type: "number", width: 70, frozen: true },
    { key: "at", label: t("audit.at"), type: "date", width: 150, value: (r) => (r.at || "").slice(0, 19).replace("T", " ") },
    { key: "category", label: t("audit.category"), width: 100, render: (r) => ui.badge(has("audit.cat." + r.category) ? t("audit.cat." + r.category) : r.category, r.category === "security" ? "warn" : "neutral") },
    { key: "event", label: t("audit.event"), type: "code", width: 190 },
    { key: "actor", label: t("audit.actor"), type: "code", width: 120 },
    { key: "ip", label: t("audit.ip"), type: "code", width: 110 },
    { key: "detail", label: t("audit.detail"), width: 360, value: (r) => Object.entries(r.detail || {}).map(([k, v]) => k + "=" + (typeof v === "object" ? JSON.stringify(v) : v)).join("  ") },
  ], { rowKey: "seq", selection: "single", layoutKey: "SEC9030", rowStatus: (r) => (/denied|failed|refused|locked/.test(r.event) ? "down" : null), onSelect: (sel) => draw(sel[0]) });
  const sc = screen({ code: "SEC9030", title: t("nav.audit"), path: [t("g.security")], shell,
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("audit"), exportLabel: t("export"), columns: () => g.columnsDialog() },
    conditions: conds, grid: g, detail, detailKey: "SEC9030:detail", note: integrity });
  function draw(r) {
    if (!r) { ui.clear(detail, ui.empty({ icon: "history", title: t("pick.one") })); return; }
    ui.clear(detail, h("div", { class: "hr-card-head" }, h("div", { class: "eco-muted" }, "#", ui.ltr(String(r.seq)), " · ", ui.ltr((r.at || "").replace("T", " "))), h("h2", {}, ui.ltr(r.event))),
      ui.section(t("audit.who"), ui.props([[t("audit.actor"), ui.ltr(r.actor)], [t("audit.ip"), r.ip ? ui.ltr(r.ip) : null], [t("audit.category"), r.category]])),
      ui.section(t("audit.detail"), Object.keys(r.detail || {}).length ? ui.props(Object.entries(r.detail).map(([k, v]) => [k, h("code", { class: "hr-code", text: typeof v === "object" ? JSON.stringify(v) : String(v) })])) : h("span", { class: "eco-muted", text: t("none") })),
      ui.section(t("audit.chain"), ui.props([[t("audit.hash"), h("code", { class: "hr-code", text: r.hash || "" })], [t("audit.prev"), h("code", { class: "hr-code", text: r.prev || "" })]])));
  }
  async function load() {
    const v = conds.values(), t0 = performance.now();
    g.setLoading();
    try {
      const rows = await api("GET", "/api/admin/audit?limit=" + v.limit + (v.category ? "&category=" + encodeURIComponent(v.category) : ""));
      const a = (v.actor || "").toLowerCase(), e = (v.event || "").toLowerCase();
      g.setRows(rows.filter((r) => (!a || (r.actor || "").toLowerCase().includes(a)) && (!e || (r.event || "").toLowerCase().includes(e))));
      sc.result({ chips: conds.chips(), ms: Math.round(performance.now() - t0) });
      if (g.view()[0]) g.select(g.view()[0].seq);
      if (can("admin.system.read")) {
        const hh = await api("GET", "/api/admin/health");
        ui.clear(integrity, h("div", { class: "hr-pad" }, hh.audit.ok ? ui.banner("ok", t("audit.intact", { n: hh.audit.entries })) : ui.banner("bad", t("audit.broken", { seq: hh.audit.first_bad_seq }))));
      }
    } catch (err) { g.setError(err.message); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Backups and recovery
function backupsScreen({ shell }) {
  const top = h("div", { class: "hr-kpi-row" }), detail = h("div", { class: "hr-detail" });
  const g = ui.grid([
    { key: "rehearsal", label: t("backup.rehearsal"), type: "status", width: 120, frozen: true, status: (r) => (!r.rehearsal ? "neutral" : r.rehearsal.ok ? "ok" : "bad"), label_of: (s, r) => (!r.rehearsal ? t("backup.not_rehearsed") : r.rehearsal.ok ? t("passed") : t("failed")) },
    { key: "name", label: t("backup.name"), type: "code", width: 260, total: "count" },
    { key: "created_at", label: t("backup.when"), type: "date", width: 160, value: (r) => (r.created_at || "").slice(0, 19).replace("T", " ") },
    { key: "reason", label: t("backup.reason"), width: 150, render: (r) => ui.badge(has("reason." + r.reason) ? t("reason." + r.reason) : r.reason, r.reason === "pre-update" ? "accent" : "neutral", r.reason === "pre-update" ? "star" : null) },
    { key: "kept", label: t("backup.kept"), width: 220, value: (r) => (r.kept_forever ? t("backup.forever") : t("backup.rotating")) },
  ], { rowKey: "name", selection: "single", layoutKey: "SYS9070", emptyText: t("backup.empty"), onSelect: (sel) => draw(sel[0]) });
  const make = ui.button({ label: t("backup.create"), icon: "archive", kind: "primary", onClick: async () => {
    ui.toast({ kind: "info", text: t("working") });
    try { const r = await api("POST", "/api/admin/backups"); ui.toast({ kind: r.rehearsal.ok ? "ok" : "bad", title: r.rehearsal.ok ? t("backup.made", { name: r.name }) : t("failed_title"), text: r.rehearsal.ok ? "" : r.rehearsal.problems.join("; "), keep: true }); load(r.name); }
    catch (e) { fail(e); }
  } });
  const sc = screen({ code: "SYS9070", title: t("nav.backups"), path: [t("g.system")], shell, toolbar: [make],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", export: () => g.exportCSV("backups"), exportLabel: t("export") }, grid: g, detail, detailKey: "SYS9070:detail", note: top });
  async function act(b, action) {
    if (action === "restore" && !(await ui.confirm({ title: t("backup.restore"), text: t("backup.confirm_restore", { name: b.name }), danger: true, okLabel: t("backup.restore") }))) return;
    try {
      const r = await api("POST", "/api/admin/backups/" + encodeURIComponent(b.name) + "/" + action);
      if (action === "restore") { changed(); ui.toast({ kind: "ok", title: t("backup.restored"), keep: true }); }
      else ui.toast({ kind: r.ok ? "ok" : "bad", title: r.ok ? t("backup.check_ok") : t("failed_title"), text: r.ok ? b.name : (r.problems || []).join("; ") });
      load(b.name);
    } catch (e) { fail(e); }
  }
  function draw(b) {
    if (!b) { ui.clear(detail, ui.empty({ icon: "archive", title: t("pick.one") })); return; }
    ui.clear(detail, h("div", { class: "hr-card-head" }, h("div", { class: "eco-muted" }, ui.ltr((b.created_at || "").replace("T", " "))), h("h2", {}, ui.ltr(b.name))),
      ui.section(t("backup.about"), ui.props([[t("backup.reason"), has("reason." + b.reason) ? t("reason." + b.reason) : b.reason], [t("backup.kept"), b.kept_forever ? t("backup.forever") : t("backup.rotating")],
        [t("backup.rehearsal"), b.rehearsal ? ui.statusChip(b.rehearsal.ok ? "ok" : "bad", b.rehearsal.ok ? t("passed") : t("failed")) : t("backup.not_rehearsed")],
        b.rehearsal && b.rehearsal.problems && b.rehearsal.problems.length ? [t("problem"), b.rehearsal.problems.join("; ")] : null])),
      ui.section(t("backup.actions"), h("div", { class: "hr-stack" },
        h("div", { class: "hr-row" }, ui.button({ label: t("backup.verify"), icon: "check-circle", onClick: () => act(b, "verify") }), ui.button({ label: t("backup.rehearse"), icon: "refresh", onClick: () => act(b, "rehearse") })),
        can("admin.backup.restore") ? h("div", {}, ui.button({ label: t("backup.restore"), icon: "rotate", kind: "danger", onClick: () => act(b, "restore") }), h("p", { class: "eco-muted hr-small", text: t("backup.restore_help") })) : null)),
      h("div", { class: "hr-pad" }, ui.banner("info", t("backup.help"))));
  }
  async function load(select) {
    const t0 = performance.now();
    g.setLoading();
    try {
      const [list, hh, st] = await Promise.all([api("GET", "/api/admin/backups"), can("admin.system.read") ? api("GET", "/api/admin/health").catch(() => null) : null, can("admin.settings.manage") ? api("GET", "/api/admin/settings").catch(() => null) : null]);
      g.setRows(list);
      sc.result({ ms: Math.round(performance.now() - t0) });
      const last = list[0], rec = hh && hh.recovery;
      ui.clear(top, ui.kpi({ label: t("backup.last"), value: last ? (last.created_at || "").slice(0, 16).replace("T", " ") : t("none"), icon: "archive", status: last && last.rehearsal && last.rehearsal.ok ? "run" : "down", hint: last && last.rehearsal ? (last.rehearsal.ok ? t("backup.rehearsed_ok") : t("failed")) : "" }),
        ui.kpi({ label: t("backup.count"), value: String(list.length), icon: "layers", hint: t("backup.kept_n", { n: list.filter((b) => b.kept_forever).length }) }),
        ui.kpi({ label: t("settings.backup_hours"), value: st ? String(st.backup_hours) : "—", unit: t("unit.hours"), icon: "clock" }),
        ui.kpi({ label: t("health.recovery"), value: rec ? rec.version : t("none"), icon: "shield", status: rec ? (rec.intact ? "run" : "down") : "planned", hint: rec ? (rec.intact ? t("backup.installer_ok") : t("problem")) : t("backup.installer_none") }));
      const pick = select || (list[0] || {}).name;
      if (pick) g.select(pick);
    } catch (e) { g.setError(e.message); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ System health
function healthScreen({ shell }) {
  const body = h("div", { class: "hr-page" });
  const sc = screen({ code: "SYS9100", title: t("nav.health"), path: [t("g.system")], shell, standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh" }, body });
  const tile = (ic, title, ok, main, sub) => h("div", { class: ["hr-tile", ok === true ? "is-ok" : ok === false ? "is-bad" : "is-neutral"] },
    h("div", { class: "hr-tile-top" }, h("span", { class: "hr-tile-icon" }, ui.icon(ic, 18)), h("span", { class: "hr-tile-title", text: title }),
      ok === null ? null : ui.statusChip(ok ? "ok" : "bad", ok ? t("ok") : t("problem"))),
    h("div", { class: "hr-tile-main" }, main), sub ? h("div", { class: "hr-tile-sub eco-muted" }, sub) : null);
  async function load() {
    try {
      const x = await api("GET", "/api/admin/health");
      const all = x.journal.ok && x.audit.ok && (!x.recovery || x.recovery.intact) && !!x.last_backup;
      ui.clear(body, all ? ui.banner("ok", t("health.all_ok"), { title: t("health.summary") }) : ui.banner("warn", t("health.some"), { title: t("health.summary") }),
        h("div", { class: "hr-tiles" },
          tile("shield", t("health.journal"), x.journal.ok, t("health.lines", { n: ui.fmtNumber(x.journal.lines) }), t("health.journal_help")),
          tile("history", t("health.audit"), x.audit.ok, t("health.lines", { n: ui.fmtNumber(x.audit.entries) }), t("health.audit_help")),
          tile("archive", t("health.last_backup"), !!(x.last_backup && x.last_backup.rehearsal && x.last_backup.rehearsal.ok), x.last_backup ? ui.ltr((x.last_backup.created_at || "").slice(0, 16).replace("T", " ")) : t("none"), x.last_backup ? x.last_backup.name : t("health.no_backup")),
          tile("download", t("health.recovery"), x.recovery ? x.recovery.intact : null, x.recovery ? ui.ltr(x.recovery.version) : t("none"), x.recovery ? t("health.recovery_help") : t("backup.installer_none")),
          tile("calendar-check", t("health.attendance"), x.attendance ? !!x.attendance.history_file : null, x.attendance && x.attendance.history_file ? t("ok") : t("none"), null),
          tile("table", t("health.excel"), x.attendance ? (x.attendance.excel_desktop === null ? null : x.attendance.excel_desktop) : null,
            x.attendance && x.attendance.excel_desktop === null ? t("not_applicable") : x.attendance && x.attendance.excel_desktop ? t("found") : t("health.no_excel_short"), x.attendance && x.attendance.excel_desktop === false ? t("attendance.no_excel") : null),
          tile("key", t("health.signing"), x.signing ? !(x.signing.problems || []).length : null, ui.ltr(x.signing ? x.signing.backend : ""), null),
          tile("monitor", t("health.device"), null, x.device ? x.device.name : "", x.device ? h("small", {}, ui.ltr(x.device.id)) : null)),
        ui.card({ title: t("health.product"), icon: "info", body: ui.props([[t("health.version"), ui.ltr(x.product.version)], [t("health.data_versions"), ui.ltr(String(x.product.data_version) + " / " + String(x.product.program_data_version))],
          [t("health.company"), x.company.name + " (" + x.company.code + ") · " + t("company.source." + x.company.source)], [t("health.home"), ui.ltr(x.product.home)], [t("health.registry"), ui.ltr(x.registry.applied_seq + " / " + x.registry.journal_seq)], [t("health.signing_problems"), x.signing && x.signing.problems && x.signing.problems.length ? x.signing.problems.join("; ") : t("none")]], { cols: 2 }) }));
    } catch (e) { ui.clear(body, ui.banner("bad", e.message)); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Settings
function settingsScreen({ shell }) {
  const body = h("div", { class: "hr-page hr-narrow" });
  let s = null;
  const save = ui.button({ label: t("save"), icon: "save", kind: "primary", onClick: () => store() });
  const sc = screen({ code: "SYS9060", title: t("nav.settings"), path: [t("g.system")], shell, toolbar: [save], body });
  let auto, lang, hours;
  async function load() {
    try {
      s = await api("GET", "/api/admin/settings");
      auto = ui.toggle({ label: t("settings.autostart"), checked: s.autostart, hint: t("settings.autostart_help") });
      lang = ui.segmented({ value: s.language, options: [["en", "English"], ["ar", "العربية"]], onChange: (v) => { lang.value_ = v; } });
      lang.value_ = s.language;
      hours = ui.input({ type: "number", value: s.backup_hours, min: "1", max: "168", width: "120px" });
      const c = S.info.company || {};
      ui.clear(body,
        ui.card({ title: t("settings.server"), subtitle: t("settings.server_sub"), icon: "monitor", body: h("div", { class: "hr-stack" }, auto,
          ui.field(t("settings.language"), lang, { hint: t("settings.language_hint") }), ui.field(t("settings.backup_hours"), hours, { hint: t("settings.backup_hint") })) }),
        ui.card({ title: t("settings.mine"), subtitle: t("settings.mine_sub"), icon: "user", body: h("div", { class: "hr-stack" },
          ui.field(ui.kitText("theme"), ui.segmented({ value: document.documentElement.dataset.theme || "light", options: [["light", ui.kitText("light"), "sun"], ["dark", ui.kitText("dark"), "moon"]], onChange: setTheme })),
          ui.field(ui.kitText("density"), ui.segmented({ value: document.documentElement.dataset.density || "compact", options: [["compact", ui.kitText("compact")], ["comfortable", ui.kitText("comfortable")]],
            onChange: (d) => { ui.prefs.set("density", d); ui.configure({ density: d }); window.dispatchEvent(new Event("eco-refresh")); } })),
          ui.field(ui.kitText("language"), ui.segmented({ value: S.lang, options: [["en", "English"], ["ar", "العربية"]], onChange: setLanguage }))) }),
        ui.card({ title: t("settings.company"), subtitle: t("settings.company_sub"), icon: "building", body: h("div", { class: "hr-stack" }, ui.props([[t("setup.company_name"), c.name], [t("field.code"), c.code ? ui.ltr(c.code) : null],
          [t("setup.source"), c.source ? t("company.source." + c.source) : null]]), c.provisional ? ui.banner("warn", t("company.provisional_help")) : null) }),
        ui.card({ title: t("eco.title"), subtitle: t("eco.sub"), icon: "link", body: eco }),
        ...(can("admin.settings.manage") ? [ui.card({ title: t("paytarget.title"), subtitle: t("paytarget.sub"), icon: "link", body: payBox })] : []));
      loadEco();
      loadPayTarget();
    } catch (e) { ui.clear(body, ui.banner("bad", e.message)); }
  }
  async function store() {
    try { await api("PUT", "/api/admin/settings", { autostart: auto.querySelector("input").checked, language: lang.value_, backup_hours: Number(hours.value) }); ui.toast({ kind: "ok", title: t("saved") }); }
    catch (e) { fail(e); }
  }
  // Integration (GMES): the product publishes HR's workforce truth to manufacturing by itself. The key is write-only:
  // the server answers only whether one is stored ("set" / "not set"), never the key.
  const eco = h("div", { class: "hr-stack" });
  let ecoUrl, ecoNode, ecoEvery, ecoKey, ecoClear;
  const when = (v) => (v ? ui.ltr(String(v).slice(0, 19).replace("T", " ")) : t("none"));
  async function loadEco() {
    let x;
    try { x = await api("GET", "/api/admin/integration"); } catch (e) { ui.clear(eco, ui.banner("bad", e.message)); return; }
    ecoUrl = ui.input({ value: x.gmes_url, placeholder: "http://127.0.0.1:4700", dir: "ltr" });
    ecoNode = ui.input({ value: x.node, dir: "ltr", width: "200px" });
    ecoEvery = ui.input({ type: "number", value: x.interval_seconds, min: "10", max: "3600", width: "120px" });
    ecoKey = ui.input({ type: "password", value: "", dir: "ltr", autocomplete: "new-password", placeholder: x.key_set ? t("eco.key_keep") : t("eco.key_enter") });
    ecoClear = x.key_set ? ui.checkbox({ label: t("eco.key_clear") }) : null;
    const ob = x.outbox || {}, last = x.last;
    const state = !x.enabled ? ui.statusChip("neutral", t("eco.off")) : x.running ? ui.statusChip("ok", t("eco.running")) : ui.statusChip("bad", t("eco.stopped"));
    const key = x.key_set ? ui.badge(t("eco.key_set"), "ok", "key") : ui.badge(x.key_unreadable ? t("eco.key_unreadable") : t("eco.key_not_set"), "warn", "key");
    ui.clear(eco,
      ui.banner("info", t("eco.alone")),
      h("div", { class: "hr-row" }, state, key),
      ui.field(t("eco.url"), ecoUrl, { hint: t("eco.url_hint") }),
      ui.field(t("eco.node"), ecoNode, { hint: t("eco.node_hint") }),
      ui.field(t("eco.interval"), ecoEvery, { hint: t("eco.interval_hint") }),
      ui.field(t("eco.key"), ecoKey, { hint: t("eco.key_hint") }), ecoClear,
      h("div", { class: "hr-kpi-row" },
        ui.kpi({ label: t("eco.pending"), value: String(ob.pending || 0), icon: "clock", status: ob.pending ? "idle" : null }),
        ui.kpi({ label: t("eco.delivered"), value: String(ob.delivered || 0), icon: "check" }),
        ui.kpi({ label: t("eco.rejected"), value: String(ob.rejected || 0), icon: "alert", status: ob.rejected ? "down" : null })),
      ui.props([[t("eco.last_delivery"), when(x.last_delivered_at)], [t("eco.last_run"), last ? when(last.at) : t("none")],
        last ? [t("eco.last_counts"), t("eco.counts", { staged: String(last.staged || 0), sent: String(last.sent || 0), delivered: String(last.delivered || 0), rejected: String(last.rejected || 0) })] : null,
        last && last.stopped_by ? [t("eco.stopped_by"), last.stopped_by] : null, last && last.error ? [t("problem"), last.error] : null]),
      h("div", { class: "hr-row" }, ui.button({ label: t("eco.save"), icon: "save", kind: "primary", onClick: () => storeEco() }),
        ui.button({ label: t("eco.send_now"), icon: "arrow-up", disabled: !x.enabled, onClick: () => sendEco() })));
  }
  async function storeEco() {
    const fields = { gmes_url: ecoUrl.value.trim(), node: ecoNode.value.trim(), interval_seconds: Number(ecoEvery.value) };
    if (ecoKey.value) fields.key = ecoKey.value;
    if (ecoClear && ecoClear.querySelector("input").checked) fields.clear_key = true;
    try { await api("PUT", "/api/admin/integration", fields); ecoKey.value = ""; ui.toast({ kind: "ok", title: t("saved") }); loadEco(); }
    catch (e) { fail(e); }
  }
  // Payroll to accounting: where an approved pay run sends its totals. The key is write-only, like the GMES key.
  const payBox = h("div", { class: "hr-stack" });
  async function loadPayTarget() {
    if (!can("admin.settings.manage")) return;
    let x;
    try { x = await api("GET", "/api/payroll/target"); } catch (e) { ui.clear(payBox, ui.banner("bad", e.message)); return; }
    const url = ui.input({ value: x.url || "", placeholder: "http://127.0.0.1:4100", dir: "ltr" });
    const key = ui.input({ type: "password", value: "", dir: "ltr", autocomplete: "new-password", placeholder: x.key_set ? t("paytarget.key_keep") : t("eco.key_enter") });
    ui.clear(payBox, ui.banner("info", t("paytarget.help")),
      h("div", { class: "hr-row" }, x.key_set ? ui.badge(t("paytarget.key_set"), "ok", "key") : ui.badge(t("paytarget.key_not_set"), "warn", "key")),
      ui.field(t("paytarget.url"), url, { hint: t("paytarget.url_hint") }), ui.field(t("paytarget.key"), key, { hint: t("paytarget.key_hint") }),
      h("div", { class: "hr-row" }, ui.button({ label: t("paytarget.save"), icon: "save", kind: "primary", onClick: async () => {
        try { await api("PUT", "/api/payroll/target", { url: url.value.trim(), ...(key.value ? { key: key.value } : {}) }); ui.toast({ kind: "ok", title: t("saved") }); loadPayTarget(); } catch (e) { fail(e); } } })));
  }
  async function sendEco() {
    ui.toast({ kind: "info", text: t("working") });
    try {
      const r = await api("POST", "/api/admin/integration/run");
      const bad = r.stopped_by || r.error;
      ui.toast({ kind: bad ? "bad" : "ok", title: bad ? t("eco.not_sent") : t("eco.sent"), text: bad ? String(bad) : t("eco.counts", { staged: String(r.staged || 0), sent: String(r.sent || 0), delivered: String(r.delivered || 0), rejected: String(r.rejected || 0) }), keep: !!bad });
      loadEco();
    } catch (e) { fail(e); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Dashboard
function dashboardScreen({ shell }) {
  const body = h("div", { class: "hr-dash" });
  async function load() {
    try {
      const R = await refs(true);
      const [hh, audit, users, found] = await Promise.all([can("admin.system.read") ? api("GET", "/api/admin/health").catch(() => null) : null,
        can("admin.audit.read") ? api("GET", "/api/admin/audit?limit=8").catch(() => []) : [], can("admin.users.manage") ? api("GET", "/api/admin/users").catch(() => []) : [],
        advisorFindings().catch(() => [])]);
      const emp = R.employees, active = emp.filter((e) => e.employment_status === "Active").length, leave = emp.filter((e) => e.employment_status === "Leave").length;
      const depts = R.units.filter((u) => u.type === "department");
      const filled = R.positions.filter((p) => emp.some((e) => e.position_id === p.id && e.employment_status !== "Terminated")).length;
      const byDept = depts.map((d) => [d, emp.filter((e) => { const u = R.unitOf(e); return e.employment_status !== "Terminated" && u && (u.id === d.id || u.parent_id === d.id); }).length]).sort((a, b) => b[1] - a[1]).slice(0, 8);
      const statuses = ["Active", "Leave", "Suspended", "Terminated"].map((s) => [s, emp.filter((e) => e.employment_status === s).length]);
      const serious = found.filter((f) => f.severity !== "tip"), tips = found.length - serious.length;
      const hires = emp.filter((e) => e.hire_date && e.employment_status !== "Terminated").sort((a, b) => b.hire_date.localeCompare(a.hire_date)).slice(0, 5);
      const c = S.info.company || {};
      const first = String(S.me.display_name || S.me.user || "").split(/\s+/)[0];
      // quick actions (Mizan's dashboard card): only what this person may do
      const quick = [["EMP1010", "user-plus", "dash.q.employee", "hr.employees.write"], ["ATT2010", "calendar-check", "dash.q.attendance", "hr.attendance.upload"],
        ["SHF3010", "calendar", "dash.q.roster", "hr.shifts.read"], ["SKL2010", "shield", "dash.q.qualification", "hr.skills.write"], ["ADV1010", "clipboard-check", "dash.q.advisor", null],
        ["SYS9070", "archive", "dash.q.backup", "admin.backup.manage"]].filter(([code, , , perm]) => shell.screens[code] && (!perm || can(perm)));
      const card = (o) => ui.card(o);
      ui.clear(body,
        h("div", { class: "hr-dash-head" }, h("div", {}, h("h1", { text: t("home.hello", { name: first }) }),
          h("p", { class: "hr-dash-sub" }, c.name ? t("dash.subtitle", { company: c.name }) + " · " : "", new Date().toLocaleDateString(S.lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" }))),
          h("span", { class: "eco-grow" }), h("div", { class: "hr-row" }, shell.screens.EMP1010 && can("hr.employees.write") ? ui.button({ label: t("new.employee"), icon: "user-plus", kind: "primary", onClick: () => shell.open("EMP1010") }) : null,
            ui.button({ label: t("dash.search"), icon: "search", onClick: () => shell.palette(), kbd: "Ctrl K" }))),
        c.provisional ? ui.banner("warn", t("company.provisional_help"), { title: t("company.provisional") }) : null,
        h("div", { class: "hr-kpis" },
          ui.kpi({ label: t("dash.employees"), value: ui.fmtNumber(emp.filter((e) => e.employment_status !== "Terminated").length), icon: "users", tone: 2, hint: t("dash.active_n", { n: active }) }),
          ui.kpi({ label: t("dash.on_leave"), value: ui.fmtNumber(leave), icon: "calendar", tone: 4, hint: t("dash.today") }),
          ui.kpi({ label: t("dash.positions"), value: filled + " / " + R.positions.length, icon: "id-card", tone: 1, hint: R.positions.length ? t("dash.filled_pct", { n: Math.round((filled / R.positions.length) * 100) }) : t("dash.filled") }),
          ui.kpi({ label: t("dash.attention"), value: String(serious.length), icon: "clipboard-check", status: found.some((f) => f.severity === "error") ? "bad" : serious.length ? "warn" : "ok", hint: t("dash.attention_hint", { n: tips }) })),
        h("div", { class: "hr-dash-grid" },
          card({ title: t("dash.by_department"), subtitle: t("dash.by_department_sub"), icon: "chart", tone: 2, body: byDept.length ? ui.barChart({ labels: byDept.map(([d]) => (d.name || d.code).length > 16 ? (d.name || d.code).slice(0, 15) + "…" : d.name || d.code), series: [{ label: t("dash.employees"), values: byDept.map(([, n]) => n) }], height: 230, width: 760 })
            : ui.empty({ icon: "chart", title: t("dash.no_data"), text: t("dash.no_data_help") }), actions: shell.screens.ORG1010 ? [ui.button({ label: t("nav.structure"), kind: "ghost", size: "sm", icon: "sitemap", onClick: () => shell.open("ORG1010") })] : null }),
          card({ title: t("dash.quick"), icon: "zap", tone: 4, actions: [ui.kbd("Ctrl"), ui.kbd("K")], cls: "hr-quick-card", body: h("div", { class: "hr-quick-list" }, quick.map(([code, ic, key]) =>
            h("button", { type: "button", class: "hr-quick-item", onclick: () => shell.open(code) }, h("span", { class: "hr-quick-ic" }, ui.icon(ic, 16)), h("span", { text: t(key) }), ui.icon(ui.isRTL() ? "chev-left" : "chev-right", 14, "eco-muted")))) })),
        h("div", { class: "hr-dash-2" },
          card({ title: t("dash.status"), icon: "activity", tone: 5, body: emp.length ? ui.donut({ parts: statuses.map(([s, n]) => ({ label: value(s), value: n, status: { Active: "ok", Leave: "idle", Suspended: "hold", Terminated: "neutral" }[s] })), centerLabel: t("dash.employees") })
            : ui.empty({ icon: "users", title: t("emp.empty") }) }),
          card({ title: t("nav.advisor"), icon: "clipboard-check", cls: "hr-flush", actions: shell.screens.ADV1010 ? [ui.button({ label: t("dash.open_all"), size: "sm", onClick: () => shell.open("ADV1010") })] : null,
            body: serious.length ? h("ul", { class: "hr-adv-list" }, serious.slice(0, 5).map((f) => h("li", {}, ui.icon(f.severity === "error" ? "x-octagon" : "alert", 16, f.severity === "error" ? "hr-bad" : "hr-warn"),
              h("button", { type: "button", class: "eco-linkbtn", text: t("adv." + f.id + ".title", f.vars), onclick: () => shell.open("ADV1010") }), h("span", { class: "eco-count", text: String(f.items.length || "") }))))
              : h("div", { class: "hr-row hr-pad2" }, ui.icon("check-circle", 18, "hr-ok"), h("span", { text: tips ? t("dash.only_tips", { n: tips }) : ui.kitText("all_clear") })) })),
        h("div", { class: "hr-dash-2" },
          card({ title: t("dash.new_hires"), icon: "user-check", tone: 3, cls: "hr-flush", body: hires.length ? h("ul", { class: "hr-list" }, hires.map((e) => h("li", {}, ui.avatar(e.preferred_name || e.code, 30),
            h("div", {}, h("b", { text: e.preferred_name || e.code }), h("small", { class: "eco-muted", text: [R.name(R.jobOf(e)), R.name(R.unitOf(e))].filter(Boolean).join(" · ") || e.code })), h("span", { class: "eco-grow" }), ui.ltr(e.hire_date, "eco-muted"))))
            : h("div", { class: "hr-pad2 eco-muted", text: t("none") }) }),
          audit.length ? card({ title: t("dash.activity"), icon: "history", cls: "hr-flush", body: h("ul", { class: "hr-activity" }, audit.map((a) => h("li", {}, h("span", { class: "hr-dot" }), h("div", {}, h("b", { text: eventText(a) }),
            h("small", { class: "eco-muted" }, ui.ltr(a.actor), " · ", ui.ltr((a.at || "").slice(0, 16).replace("T", " ")))))) ), actions: [ui.button({ label: t("nav.audit"), kind: "ghost", size: "sm", onClick: () => shell.open("SEC9030") })] })
            : hh ? card({ title: t("dash.system"), icon: "shield", body: systemChecks(hh), actions: [ui.button({ label: t("nav.health"), kind: "ghost", size: "sm", onClick: () => shell.open("SYS9100") })] }) : null),
        audit.length && hh ? card({ title: t("dash.system"), icon: "shield", body: systemChecks(hh), actions: [ui.button({ label: t("nav.health"), kind: "ghost", size: "sm", onClick: () => shell.open("SYS9100") })] }) : null,
        users.length ? ui.kpiStrip([{ label: t("dash.users"), value: users.filter((u) => u.active).length, hint: t("dash.can_sign_in") }, { label: t("dash.departments"), value: depts.length, hint: t("dash.units_n", { n: R.units.length }) },
          { label: t("nav.jobs"), value: R.jobs.length }, { label: t("nav.skills"), value: R.skills.length }, { label: t("nav.shifts"), value: R.shifts.length }]) : null);
    } catch (e) { ui.clear(body, ui.banner("bad", e.message)); }
  }
  load();
  return { el: body, onActivate: () => { if (S.refs === null) load(); } };
}
/** An audit line in plain words ("Employee E000123 saved") instead of its code ("record.saved"). */
function eventText(a) {
  const d = a.detail || {}, base = has("event." + a.event) ? t("event." + a.event) : a.event;
  if (d.entity && d.code) return base + ": " + (has("entity." + d.entity) ? t("entity." + d.entity) : d.entity) + " " + d.code;
  if (d.user) return base + ": " + d.user;
  if (d.profile) return base + ": " + profileName(d.profile);
  return base;
}
function systemChecks(hh) {
  return h("div", { class: "hr-checks" }, [[hh.journal.ok, t("health.journal")], [hh.audit.ok, t("health.audit")], [!!(hh.last_backup && hh.last_backup.rehearsal && hh.last_backup.rehearsal.ok), t("health.last_backup")],
    [hh.recovery ? hh.recovery.intact : null, t("health.recovery")]].map(([ok, k]) => h("div", { class: "hr-check" }, ui.icon(ok === null ? "info" : ok ? "check-circle" : "x-octagon", 16, ok === null ? "eco-muted" : ok ? "hr-ok" : "hr-bad"), h("span", { text: k }))));
}

// ------------------------------------------------------------------ the guide system (Mizan's design: guide mode, help panel, "how do I", guided tours)
// Guide mode, per person: off (help only when asked), basic (+ the Advisor's warnings on the record itself),
// full (+ tips inside the forms and what each figure is made of). F1 or "?" opens the help panel beside the work.
const guideMode = () => ui.prefs.get("guide", "full");
const guideAtLeast = (m) => ({ off: 0, basic: 1, full: 2 })[guideMode()] >= ({ off: 0, basic: 1, full: 2 })[m];
const view = () => document.querySelector(".eco-view:not([hidden])");
const inView = (sel) => () => { const v = view(); return v ? v.querySelector(sel) : null; };
// "How do I ...": each task is a guided tour that opens the screens it needs; its words are task.<id>.<n>.t / .x
const TASKS = [
  { id: "hire", icon: "user-plus", screens: ["EMP1010"], steps: [["EMP1010", ".eco-toolbar-start .eco-btn-primary"], ["EMP1010", ".eco-cond"], ["EMP1010", ".eco-resultbar .eco-seg"], ["EMP1010", ".eco-gh-filter"], ["EMP1010", ".hr-detail .eco-tabs-inner"]] },
  { id: "journey", icon: "trending-up", screens: ["EMP2010"], steps: [["EMP2010", ".hr-journey-head"], ["EMP2010", ".hr-play"], ["EMP2010", ".hr-journey-figures"], ["EMP2010", ".hr-timeline-box"]] },
  { id: "plan", icon: "calendar-check", screens: ["SHF2010", "SHF3010"], steps: [["SHF2010", ".eco-toolbar-start .eco-btn-primary"], ["SHF3010", ".eco-toolbar-start .eco-btn"], ["SHF3010", ".hr-day"], ["SHF3010", ".hr-legend"]] },
  { id: "penalty", icon: "scale", screens: ["DSC1010", "DSC2010"], steps: [["DSC1010", ".eco-screen-grid"], ["DSC2010", ".eco-toolbar-start .eco-btn-primary"], ["DSC2010", ".eco-resultbar .eco-seg"], ["DSC2010", ".eco-toolbar-start .eco-btn:nth-child(3)"], ["ADV1010", ".eco-advice"]] },
  { id: "certify", icon: "shield", screens: ["SKL3010", "SKL2010"], steps: [["SKL3010", ".hr-legend"], ["SKL3010", ".hr-q"], ["SKL2010", ".eco-resultbar .eco-seg"]] },
  { id: "rights", icon: "key", screens: ["SEC9020", "SEC9010"], steps: [["SEC9020", ".hr-plist"], ["SEC9020", ".hr-pm-cell"], ["SEC9020", ".hr-record-head .eco-btn"], ["SEC9010", ".eco-toolbar-start .eco-btn-primary"]] },
  { id: "backup", icon: "archive", screens: ["SYS9070", "SYS9100"], steps: [["SYS9070", ".eco-toolbar-start .eco-btn-primary"], ["SYS9070", ".eco-screen-grid"], ["SYS9100", ".hr-tiles"]] },
  { id: "advisor", icon: "clipboard-check", screens: ["ADV1010"], steps: [["ADV1010", ".hr-kpis"], ["ADV1010", ".eco-seg"], ["ADV1010", ".eco-advice-fix"], ["ADV1010", ".eco-advice-items"]] },
];
function runTask(id) {
  const task = TASKS.find((x) => x.id === id);
  if (!task || !S.shell) return;
  const drawer = ui.openDrawer();
  drawer && drawer.close();
  const steps = task.steps.filter(([code]) => S.shell.screens[code]).map(([code, sel], i) => ({
    title: t(`task.${id}.${i + 1}.t`), text: t(`task.${id}.${i + 1}.x`), target: inView(sel),
    before: async () => { if (S.shell.active() !== code) { S.shell.open(code); await new Promise((r) => setTimeout(r, 900)); } },
  }));
  if (!steps.length) { ui.toast({ kind: "warn", text: t("guide.no_rights") }); return; }
  ui.tour(steps, { onEnd: (done) => done && ui.toast({ kind: "ok", title: t("guide.done"), text: t(`task.${id}.title`) }) });
}
function taskList(filter = "") {
  const q = filter.trim().toLowerCase();
  const list = TASKS.filter((x) => x.screens.some((c) => S.shell && S.shell.screens[c]) && (!q || (t(`task.${x.id}.title`) + " " + t(`task.${x.id}.keywords`)).toLowerCase().includes(q)));
  return h("div", { class: "hr-tasks" }, list.length ? list.map((x) => h("button", { type: "button", class: "hr-task", onclick: () => runTask(x.id) },
    h("span", { class: "hr-quick-ic" }, ui.icon(x.icon, 16)), h("span", {}, h("b", { text: t(`task.${x.id}.title`) }), h("small", { class: "eco-muted", text: t("guide.steps_n", { n: x.steps.length }) })),
    ui.icon("play", 14, "eco-muted"))) : h("p", { class: "eco-muted", text: t("guide.no_task") }));
}
function openHelp() {
  const code = S.shell && S.shell.active();
  const sc = code && S.shell.screens[code];
  const find = ui.input({ type: "search", placeholder: t("guide.search_ph") });
  const tasksBox = h("div", {}, taskList());
  find.addEventListener("input", () => ui.clear(tasksBox, taskList(find.value)));
  const about = code && has("about." + code) ? t("about." + code) : t("about.HOME");
  const mode = ui.segmented({ size: "sm", value: guideMode(), options: [["off", t("guide.off")], ["basic", t("guide.basic")], ["full", t("guide.full")]],
    onChange: (v) => { ui.prefs.set("guide", v); window.dispatchEvent(new Event("eco-refresh")); ui.toast({ kind: "ok", text: { off: t("guide.mode_off"), basic: t("guide.mode_basic"), full: t("guide.mode_full") }[v] }); } });
  ui.drawer({ title: sc ? sc.title : t("guide.title"), subtitle: code && code !== "HOME" ? code + (has("sub." + code) ? " · " + t("sub." + code) : "") : t("guide.subtitle"), icon: "help", width: 460,
    body: h("div", { class: "hr-help" },
      h("section", {}, h("h3", { text: t("guide.about_screen") }), about.split(/\n{2,}/).map((p) => h("p", { text: p }))),
      h("section", {}, h("h3", { text: t("guide.how_do_i") }), find, tasksBox),
      h("section", {}, h("h3", { text: t("guide.mode") }), mode, h("p", { class: "eco-muted hr-small", text: t("guide.mode_help") })),
      h("section", { class: "hr-help-keys" }, h("h3", { text: t("guide.keys") }), ui.props([["F1", t("guide.key_f1")], ["Ctrl K", t("guide.key_k")], ["F5", t("guide.key_f5")], ["Ctrl E", t("guide.key_e")]])),
      S.shell.screens.HLP1010 ? ui.button({ label: t("guide.open_center"), icon: "bookmark", onClick: () => { ui.openDrawer() && ui.openDrawer().close(); S.shell.open("HLP1010"); } }) : null) });
}
function helpCenterScreen({ shell }) {
  const find = ui.searchBox({ placeholder: t("guide.search_center"), width: "420px" });
  const body = h("div", { class: "hr-page hr-help-center" });
  const draw = () => {
    const q = find.querySelector("input").value.trim().toLowerCase();
    const match = (code) => !q || (t(SCREENS[code][0]) + " " + (has("about." + code) ? t("about." + code) : "") + " " + (has(SCREENS[code][0] + ".help") ? t(SCREENS[code][0] + ".help") : "")).toLowerCase().includes(q);
    ui.clear(body,
      ui.card({ title: t("guide.how_do_i"), subtitle: t("guide.tasks_sub"), icon: "play", tone: 1, body: taskList(q) }),
      h("div", { class: "hr-help-grid" }, MENU.map(([id, ic, codes]) => {
        const mine = codes.filter((c) => shell.screens[c] && match(c));
        return mine.length ? ui.card({ title: t("g." + id), icon: ic, tone: 2, body: h("div", { class: "hr-help-topics" }, mine.map((c) => h("details", { class: "hr-topic" },
          h("summary", {}, ui.icon(SCREENS[c][1], 15), h("b", { text: t(SCREENS[c][0]) }), h("small", { class: "eco-muted", text: c })),
          has("sub." + c) ? h("p", { class: "hr-topic-sub", text: t("sub." + c) }) : null,
          ...(has("about." + c) ? t("about." + c).split(/\n{2,}/).map((p) => h("p", { text: p })) : []),
          ui.button({ label: t("guide.open_screen"), icon: "arrow-up", size: "sm", onClick: () => shell.open(c) })))) }) : null;
      })));
  };
  find.querySelector("input").addEventListener("input", draw);
  const sc = screen({ code: "HLP1010", title: t("nav.help"), path: [t("g.system")], shell, headExtra: find, body });
  draw();
  return { el: sc.el };
}
/** The Advisor's findings about one record (basic guide mode and up): shown on the record itself, like Mizan's advice on a document. */
async function recordWarnings(code) {
  if (!guideAtLeast("basic")) return null;
  S.findings = S.findings || (await advisorFindings().catch(() => []));
  const mine = S.findings.filter((f) => f.severity !== "tip" && f.items.some((it) => (it.label || "").startsWith(code + " ")));
  return mine.length ? h("div", { class: "hr-record-warnings" }, mine.map((f) => ui.banner(f.severity === "error" ? "bad" : "warn", has("adv." + f.id + ".fix") ? t("adv." + f.id + ".fix", f.vars) : "",
    { title: t("adv." + f.id + ".title", f.vars) }))) : null;
}

// ------------------------------------------------------------------ the shell
// ------------------------------------------------------------------ People operations (WP-H2 to WP-H5): recruitment, overtime, training, leave
const nextCode = (prefix, rows, width = 4) => { let n = 0; for (const r of rows) { const m = new RegExp("^" + prefix + "(\\d+)$").exec(r.code); if (m) n = Math.max(n, Number(m[1])); } return prefix + String(n + 1).padStart(width, "0"); };
const presetCode = (entity, prefix, extra = {}) => async () => ({ code: nextCode(prefix, await api("GET", "/api/" + entity + "?deleted=1")), ...extra });
const jobName = (R, r) => (R() && R().byId.get(r.job_id) ? R().byId.get(r.job_id).title : "");
const empLabel = (R, id) => (R() ? R().label(R().byId.get(id)) : "");
/** A button that changes one field of the selected record (the approve / reject / cancel of a workflow); the server decides who may. */
const changeAction = (entity, fields, label, icon, perm, when, kind) => ({ key: entity + label, label, icon, perm, kind, when,
  run: async (r, ctx) => { try { await api("PUT", "/api/" + entity + "/" + encodeURIComponent(r.code), { fields: typeof fields === "function" ? fields(r) : fields, expected_ver: r.ver }); changed(); ui.toast({ kind: "ok", title: t("saved"), text: r.code }); ctx.reload(); } catch (e) { fail(e); } } });
const badgeOf = (v, kinds) => (v ? ui.badge(value(v), (kinds && kinds[v]) || "neutral") : "");
const STATE_KIND = { draft: "neutral", approved: "info", open: "info", filled: "ok", cancelled: "neutral", requested: "warn", rejected: "bad" };

const headcountScreen = registerScreen("headcount_plan", "REC1010", "nav.headcount", (R) => [
  { key: "code", label: t("field.code"), type: "code", width: 170, frozen: true, total: "count" }, { key: "period", label: t("field.period"), type: "code", width: 90 },
  { key: "job", label: t("field.job_id"), width: 170, value: (r) => jobName(R, r) }, { key: "work_center_code", label: t("field.work_center_code"), type: "code", width: 130 },
  { key: "planned_fte", label: t("field.planned_fte"), type: "number", width: 110, total: "sum" }, { key: "source", label: t("field.source"), width: 150, value: (r) => value(r.source) }, { key: "note", label: t("field.note"), width: 300 },
], { write: "hr.recruitment.write", group: "g.recruitment", fetch: true, people: false, icon: "chart", preset: () => ({ source: "manual" }),
  tools: [{ label: "rec.propose", icon: "sparkles", perm: "hr.recruitment.write", run: (ctx) => proposeHeadcount(ctx) }] });
async function proposeHeadcount(ctx) {
  const out = h("div");
  try {
    const r = await api("POST", "/api/recruitment/propose-headcount", { apply: false });
    if (!r.proposals.length) { ui.toast({ kind: "info", title: t("rec.propose"), text: t("rec.propose_none") }); return; }
    ui.dialog({ title: t("rec.propose"), icon: "sparkles", width: 640, body: h("div", { class: "hr-stack" }, h("p", { class: "eco-dialog-text", text: t("rec.propose_help") }),
      ui.props(r.proposals.map((p) => [p.work_center_code + " · " + p.period, t("rec.propose_line", { avg: p.average_required, fte: p.planned_fte, days: p.days })])), out),
    actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("rec.propose_save"), kind: "primary", icon: "save", onClick: async () => {
      try { const s = await api("POST", "/api/recruitment/propose-headcount", { apply: true }); ui.toast({ kind: "ok", title: t("saved"), text: t("rec.propose_saved", { n: s.saved.length }) }); ctx.reload(); return true; }
      catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
  } catch (e) { fail(e); }
}
const agenciesScreen = registerScreen("agency", "REC1050", "nav.agencies", () => [
  { key: "code", label: t("field.code"), type: "code", width: 110, frozen: true, total: "count" }, { key: "name", label: t("field.name"), width: 220 }, { key: "contact", label: t("field.contact"), width: 200 },
  { key: "fee_percent", label: t("field.fee_percent"), type: "number", width: 100 }, { key: "active", label: t("field.active"), width: 90, value: (r) => (r.active === 0 ? t("no") : t("yes")) },
], { write: "hr.recruitment.write", group: "g.recruitment", fetch: true, people: false, icon: "building", preset: () => ({ active: 1 }) });
const requisitionsScreen = registerScreen("hire_requisition", "REC1020", "nav.requisitions", (R) => [
  { key: "status", label: t("field.status"), width: 110, frozen: true, render: (r) => badgeOf(r.status, STATE_KIND), value: (r) => value(r.status) }, { key: "code", label: t("field.code"), type: "code", width: 110 },
  { key: "job", label: t("field.job_id"), width: 170, value: (r) => jobName(R, r) }, { key: "count", label: t("field.count"), type: "number", width: 80, total: "sum" }, { key: "filled", label: t("field.filled"), type: "number", width: 80, total: "sum" },
  { key: "employment_type", label: t("field.employment_type"), width: 120, value: (r) => value(r.employment_type) }, { key: "reason", label: t("field.reason"), width: 120, value: (r) => value(r.reason) },
  { key: "needed_by", label: t("field.needed_by"), type: "date", width: 110 }, { key: "approved_by", label: t("field.approved_by"), type: "code", width: 110 }, { key: "note", label: t("field.note"), width: 260 },
], { write: "hr.recruitment.write", group: "g.recruitment", fetch: true, people: false, icon: "clipboard", preset: presetCode("hire_requisition", "REQ-", { employment_type: "regular", reason: "crew_gap" }),
  actions: [changeAction("hire_requisition", { status: "approved" }, "act.approve", "check", "hr.recruitment.approve", (r) => r.status === "draft", "primary"),
    changeAction("hire_requisition", { status: "open" }, "act.open", "play", "hr.recruitment.approve", (r) => r.status === "approved"),
    changeAction("hire_requisition", { status: "cancelled" }, "act.cancel", "x", "hr.recruitment.write", (r) => ["draft", "approved", "open"].includes(r.status))] });
const candidatesScreen = registerScreen("candidate", "REC1030", "nav.candidates", (R) => [
  { key: "stage", label: t("field.stage"), width: 130, frozen: true, render: (r) => badgeOf(r.stage, { hired: "ok", offered: "info", rejected: "bad", withdrawn: "neutral" }), value: (r) => t("stage." + r.stage) },
  { key: "code", label: t("field.code"), type: "code", width: 110 }, { key: "display_name", label: t("field.display_name"), width: 200 },
  { key: "requisition", label: t("field.requisition_id"), width: 130, value: (r) => (R() && R().byId.get(r.requisition_id) ? R().byId.get(r.requisition_id).code : "") },
  { key: "source", label: t("field.source"), width: 110, value: (r) => value(r.source) }, { key: "stage_date", label: t("field.stage_date"), type: "date", width: 110 }, { key: "note", label: t("field.note"), width: 260 },
], { write: "hr.recruitment.write", group: "g.recruitment", fetch: true, people: false, icon: "user-plus", preset: presetCode("candidate", "CAN-", { source: "referral", stage: "applied" }),
  actions: [{ key: "advance", label: "act.advance", icon: "chev-right", kind: "primary", perm: "hr.recruitment.write", when: (r) => ["applied", "screened", "interviewed"].includes(r.stage),
    run: (r, ctx) => changeAction("candidate", { stage: { applied: "screened", screened: "interviewed", interviewed: "offered" }[r.stage] }, "", "", "", null).run(r, ctx) },
  changeAction("candidate", { stage: "rejected" }, "act.reject", "x", "hr.recruitment.write", (r) => ["applied", "screened", "interviewed", "offered"].includes(r.stage)),
  { key: "hire", label: "act.hire", icon: "user-plus", kind: "primary", perm: "hr.recruitment.write", when: (r) => r.stage === "offered", run: (r, ctx) => hireDialog(r, ctx) }] });
function hireDialog(cand, ctx) {
  const R = ctx.R, req = R.byId.get(cand.requisition_id) || {};
  const date = ui.input({ type: "date", value: localToday() }), end = ui.input({ type: "date" });
  const type = ui.select({ options: ["regular", "fixed_term", "agency", "intern"].map((v) => [v, value(v)]), value: req.employment_type || "regular" });
  const position = ui.select({ options: R.positions.map((p) => [p.id, R.label(p)]), placeholder: "—", value: req.position_id || "" });
  const out = h("div");
  ui.dialog({ title: t("act.hire") + " · " + cand.display_name, subtitle: req.code || "", icon: "user-plus", width: 560,
    body: h("div", { class: "hr-stack" }, ui.banner("info", t("rec.hire_help")), h("div", { class: "eco-form" }, ui.field(t("field.hire_date"), date, { required: true }), ui.field(t("field.employment_type"), type),
      ui.field(t("field.position_id"), position), ui.field(t("field.end_date"), end, { hint: t("hint.contract_end") })), out),
    actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("act.hire"), kind: "primary", icon: "user-plus", onClick: async () => {
      try {
        const r = await api("POST", "/api/recruitment/candidates/" + encodeURIComponent(cand.code) + "/hire", { hire_date: date.value, employment_type: type.value, position_id: position.value || null, contract_end: end.value || null });
        changed(); ui.toast({ kind: "ok", title: t("rec.hired", { code: r.employee }), text: t("rec.hired_help"), keep: true }); ctx.reload(); return true;
      } catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
}
const onboardingScreen = registerScreen("onboarding_task", "REC1040", "nav.onboarding", (R) => [
  { key: "done", label: t("field.status"), width: 110, frozen: true, render: (r) => (r.done_on ? ui.badge(t("onb.done"), "ok") : ui.badge(t("onb.open"), "warn")), value: (r) => (r.done_on ? t("onb.done") : t("onb.open")) },
  { key: "employee", label: t("field.employee_id"), width: 220, value: (r) => empLabel(R, r.employee_id) }, { key: "kind", label: t("field.kind"), width: 170, value: (r) => t("onb." + r.kind) },
  { key: "due", label: t("field.due"), type: "date", width: 110 }, { key: "done_on", label: t("field.done_on"), type: "date", width: 110 },
], { write: "hr.recruitment.write", group: "g.recruitment", fetch: true, people: false, icon: "clipboard-check",
  actions: [changeAction("onboarding_task", () => ({ done_on: localToday() }), "act.mark_done", "check", "hr.recruitment.write", (r) => !r.done_on, "primary")] });
const contractsScreen = registerScreen("contract", "REC1060", "nav.contracts", (R) => [
  { key: "code", label: t("field.code"), type: "code", width: 130, frozen: true, total: "count" }, { key: "employee", label: t("field.employee_id"), width: 220, value: (r) => empLabel(R, r.employee_id) },
  { key: "employment_type", label: t("field.employment_type"), width: 120, value: (r) => value(r.employment_type) }, { key: "start_date", label: t("field.start_date"), type: "date", width: 110 },
  { key: "end_date", label: t("field.end_date"), type: "date", width: 110 }, { key: "reason", label: t("field.reason"), width: 200 },
], { write: "hr.recruitment.write", group: "g.recruitment", fetch: true, people: false, icon: "id-card",
  tools: [{ label: "rec.expire", icon: "history", perm: "hr.recruitment.write", run: async (ctx) => { try { const r = await api("POST", "/api/recruitment/expire-contracts", {}); changed(); ui.toast({ kind: "ok", title: t("rec.expired", { n: r.ended.length }) }); ctx.reload(); } catch (e) { fail(e); } } }] });

const overtimeScreen = registerScreen("overtime_request", "OVT1010", "nav.overtime", (R) => [
  { key: "status", label: t("field.status"), width: 110, frozen: true, render: (r) => badgeOf(r.status, STATE_KIND), value: (r) => value(r.status) }, { key: "code", label: t("field.code"), type: "code", width: 100 },
  { key: "employee", label: t("field.employee_id"), width: 220, value: (r) => empLabel(R, r.employee_id) }, { key: "work_date", label: t("plan.day"), type: "date", width: 110 },
  { key: "planned_minutes", label: t("field.planned_minutes"), type: "number", width: 110, total: "sum" }, { key: "kind", label: t("field.kind"), width: 110, value: (r) => t("ot." + r.kind) },
  { key: "reason", label: t("field.reason"), width: 240 }, { key: "requested_by", label: t("field.requested_by"), type: "code", width: 110 }, { key: "approved_by", label: t("field.approved_by"), type: "code", width: 110 },
], { write: "hr.overtime.write", group: "g.overtime", fetch: true, people: false, icon: "clock", preset: presetCode("overtime_request", "OT-", { kind: "day" }),
  actions: [changeAction("overtime_request", { status: "approved" }, "act.approve", "check", "hr.overtime.approve", (r) => r.status === "requested", "primary"),
    changeAction("overtime_request", { status: "rejected" }, "act.reject", "x", "hr.overtime.approve", (r) => r.status === "requested")] });
function overtimeFiguresScreen({ shell }) {
  const conds = ui.conditionPanel([{ key: "period", label: t("field.period"), placeholder: "YYYY-MM", dir: "ltr", default: lastMonth() }], { key: "OVT1020", onSubmit: () => load() });
  const g = ui.grid([
    { key: "employee", label: t("field.employee_id"), type: "code", width: 110, frozen: true, total: "count" },
    ...["day", "night", "rest_day", "holiday"].map((k) => ({ key: k, label: t("ot." + k), type: "number", width: 100, total: "sum", value: (r) => r.minutes[k] })),
    { key: "total_minutes", label: t("ovt.total"), type: "number", width: 100, total: "sum" },
    { key: "premium", label: t("ovt.premium"), width: 250, value: (r) => `${r.premium_bp.day / 100}% · ${r.premium_bp.night / 100}% · ${r.premium_bp.rest_day / 100}% · ${r.premium_bp.holiday / 100}%` },
    { key: "substitute_days", label: t("ovt.substitute"), type: "number", width: 120, total: "sum" },
  ], { rowKey: "employee", selection: "single", totals: true, layoutKey: "OVT1020", emptyText: t("empty") });
  const notes = h("div", { class: "hr-pad" });
  const sc = screen({ code: "OVT1020", title: t("nav.overtime_figures"), path: [t("g.overtime")], shell,
    toolbar: [ui.button({ label: t("ovt.policy"), icon: "settings", disabled: !can("hr.overtime.read"), onClick: () => policyDialog() })],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", export: () => g.exportCSV("overtime"), exportLabel: t("export"), columns: () => g.columnsDialog() }, conditions: conds, grid: g, note: notes });
  async function load() {
    g.setLoading();
    try {
      const r = await api("GET", "/api/overtime/figures?period=" + encodeURIComponent(conds.values().period || lastMonth()));
      g.setRows(r.employees);
      ui.clear(notes, ui.banner("info", r.policy.source_note), r.exceptions.length ? ui.banner("warn", t("ovt.exceptions", { n: r.exceptions.length }) + ": " + r.exceptions.map((x) => `${x.employee} ${x.date} (${x.minutes})`).join(" · ")) : null);
      sc.result({ chips: conds.chips() });
    } catch (e) { g.setError(e.message); }
  }
  async function policyDialog() {
    const p = await api("GET", "/api/overtime/policy");
    const keys = ["premium_day_bp", "premium_night_bp", "rest_day_premium_bp", "holiday_premium_bp", "night_allowance_bp", "max_daily_minutes_incl_ot", "max_weekly_ot_minutes", "max_monthly_ot_minutes", "night_from", "night_to"];
    const inputs = Object.fromEntries(keys.map((k) => [k, ui.input({ value: String(p[k]), dir: "ltr" })]));
    const out = h("div");
    ui.dialog({ title: t("ovt.policy"), icon: "settings", width: 620, body: h("div", { class: "hr-stack" }, ui.banner("warn", p.source_note), h("div", { class: "eco-form" }, keys.map((k) => ui.field(t("policy." + k), inputs[k]))), out),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("save"), kind: "primary", icon: "save", disabled: !can("hr.overtime.approve"), onClick: async () => {
        const body = Object.fromEntries(keys.map((k) => [k, k === "night_from" || k === "night_to" ? inputs[k].value : Number(inputs[k].value)]));
        try { await api("PUT", "/api/overtime/policy", body); ui.toast({ kind: "ok", title: t("saved") }); load(); return true; } catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Payroll (WP-H6): salary profiles, the month's adjustments, pay runs
const pounds = (minor) => minor / 100;
const toMinor = (text) => Math.round(Number(String(text).replace(/,/g, "")) * 100);
const PAY_STATE = { calculated: "warn", approved: "ok", reversed: "neutral" };
function payProfilesScreen({ shell }) {
  const g = ui.grid([
    { key: "employee_code", label: t("field.employee_id"), type: "code", width: 110, frozen: true, total: "count" },
    { key: "effective_from", label: t("pay.effective_from"), type: "date", width: 120 },
    { key: "basic", label: t("pay.basic"), type: "number", digits: 2, width: 120, total: "sum", value: (r) => pounds(r.basic_minor) },
    { key: "allowance", label: t("pay.allowance"), type: "number", digits: 2, width: 120, total: "sum", value: (r) => pounds(r.allowance_minor) },
    { key: "insurable", label: t("pay.insurable"), type: "number", digits: 2, width: 130, total: "sum", value: (r) => pounds(r.insurable_minor) },
    { key: "cost_center", label: t("pay.cost_center"), type: "code", width: 120 }, { key: "note", label: t("field.note"), width: 240 },
    { key: "created_by", label: t("pay.by"), type: "code", width: 110 },
  ], { rowKey: "key", selection: "single", totals: true, layoutKey: "PAY1010", emptyText: t("empty"), onSelect: () => { edit.disabled = !can("hr.payroll.write"); }, onOpen: (r) => can("hr.payroll.write") && dialog(r) });
  const edit = ui.button({ label: t("edit"), icon: "edit", disabled: true, onClick: () => dialog(g.selected()[0]) });
  const add = ui.button({ label: t("pay.new_profile"), icon: "plus", kind: "primary", disabled: !can("hr.payroll.write"), onClick: () => dialog(null) });
  const sc = screen({ code: "PAY1010", title: t("nav.pay_profiles"), path: [t("g.payroll")], shell, toolbar: [add, edit],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", export: () => g.exportCSV("pay-profiles"), exportLabel: t("export"), columns: () => g.columnsDialog() }, grid: g });
  async function load() {
    g.setLoading();
    try { g.setRows((await api("GET", "/api/payroll/profiles")).map((r) => ({ ...r, key: r.employee_code + "@" + r.effective_from }))); sc.result({}); } catch (e) { g.setError(e.message); }
  }
  function dialog(cur) {
    const f = {
      employee: ui.input({ value: cur ? cur.employee_code : "", dir: "ltr" }), from: ui.input({ type: "date", value: cur ? cur.effective_from : localToday() }),
      basic: ui.input({ value: cur ? String(pounds(cur.basic_minor)) : "", dir: "ltr" }), allowance: ui.input({ value: cur ? String(pounds(cur.allowance_minor)) : "0", dir: "ltr" }),
      insurable: ui.input({ value: cur ? String(pounds(cur.insurable_minor)) : "", dir: "ltr" }), cc: ui.input({ value: cur ? cur.cost_center || "" : "", dir: "ltr" }), note: ui.input({ value: cur ? cur.note || "" : "" }),
    };
    const out = h("div");
    ui.dialog({ title: t("pay.new_profile"), icon: "id-card", width: 560, body: h("div", { class: "hr-stack" }, ui.banner("info", t("pay.profile_help")), h("div", { class: "eco-form" },
      ui.field(t("field.employee_id"), f.employee, { required: true }), ui.field(t("pay.effective_from"), f.from, { required: true }), ui.field(t("pay.basic"), f.basic, { required: true }),
      ui.field(t("pay.allowance"), f.allowance), ui.field(t("pay.insurable"), f.insurable, { hint: t("pay.insurable_hint") }), ui.field(t("pay.cost_center"), f.cc, { hint: t("pay.cost_center_hint") }), ui.field(t("field.note"), f.note)), out),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("save"), kind: "primary", icon: "save", onClick: async () => {
        try {
          const fields = { effective_from: f.from.value, basic_minor: toMinor(f.basic.value), allowance_minor: toMinor(f.allowance.value || "0"), insurable_minor: toMinor(f.insurable.value || f.basic.value), cost_center: f.cc.value, note: f.note.value };
          await api("PUT", "/api/payroll/profiles/" + encodeURIComponent(f.employee.value.trim()), { fields }); ui.toast({ kind: "ok", title: t("saved") }); load(); return true;
        } catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
  }
  load();
  return { el: sc.el };
}
function payAdjustmentsScreen({ shell }) {
  const conds = ui.conditionPanel([{ key: "period", label: t("field.period"), placeholder: "YYYY-MM", dir: "ltr", default: lastMonth() }], { key: "PAY1020", onSubmit: () => load() });
  const g = ui.grid([
    { key: "employee_code", label: t("field.employee_id"), type: "code", width: 110, frozen: true, total: "count" }, { key: "kind", label: t("field.kind"), width: 190, value: (r) => t("pay.kind." + r.kind) },
    { key: "amount", label: t("pay.value"), type: "number", digits: 2, width: 130, value: (r) => (r.kind === "unpaid_absence_days" ? r.value : pounds(r.value)) },
    { key: "note", label: t("field.note"), width: 280 }, { key: "created_by", label: t("pay.by"), type: "code", width: 110 },
  ], { rowKey: "id", selection: "single", totals: true, layoutKey: "PAY1020", emptyText: t("empty"), onSelect: (sel) => { del.disabled = !sel.length || !can("hr.payroll.write"); } });
  const del = ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: async () => { try { await api("DELETE", "/api/payroll/adjustments/" + g.selected()[0].id); load(); } catch (e) { fail(e); } } });
  const add = ui.button({ label: t("pay.new_adjustment"), icon: "plus", kind: "primary", disabled: !can("hr.payroll.write"), onClick: () => dialog() });
  const sc = screen({ code: "PAY1020", title: t("nav.pay_adjustments"), path: [t("g.payroll")], shell, toolbar: [add, del],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", export: () => g.exportCSV("pay-adjustments"), exportLabel: t("export"), columns: () => g.columnsDialog() }, conditions: conds, grid: g });
  const period = () => conds.values().period || lastMonth();
  async function load() {
    g.setLoading();
    try { g.setRows(await api("GET", "/api/payroll/adjustments?period=" + encodeURIComponent(period()))); sc.result({ chips: conds.chips() }); } catch (e) { g.setError(e.message); }
  }
  function dialog() {
    const emp = ui.input({ dir: "ltr" }), kind = ui.select({ options: ["unpaid_absence_days", "bonus", "deduction"].map((k) => [k, t("pay.kind." + k)]), value: "unpaid_absence_days" }), val = ui.input({ dir: "ltr" }), note = ui.input({}), out = h("div");
    ui.dialog({ title: t("pay.new_adjustment") + " · " + period(), icon: "id-card", width: 520, body: h("div", { class: "hr-stack" }, ui.banner("info", t("pay.adjustment_help")), h("div", { class: "eco-form" },
      ui.field(t("field.employee_id"), emp, { required: true }), ui.field(t("field.kind"), kind), ui.field(t("pay.value"), val, { required: true, hint: t("pay.value_hint") }), ui.field(t("field.note"), note)), out),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("save"), kind: "primary", icon: "save", onClick: async () => {
        try {
          const v = kind.value === "unpaid_absence_days" ? Number(val.value) : toMinor(val.value);
          await api("POST", "/api/payroll/adjustments", { period: period(), employee: emp.value.trim(), kind: kind.value, value: v, note: note.value }); ui.toast({ kind: "ok", title: t("saved") }); load(); return true;
        } catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
  }
  load();
  return { el: sc.el };
}
function payRunsScreen({ shell }) {
  const money = (minor) => pounds(minor).toLocaleString(S.lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const g = ui.grid([
    { key: "status", label: t("field.status"), width: 120, frozen: true, render: (r) => ui.badge(t("pay.state." + r.status), PAY_STATE[r.status] || "neutral"), value: (r) => t("pay.state." + r.status) },
    { key: "period", label: t("field.period"), type: "code", width: 90 }, { key: "run", label: t("pay.run"), type: "number", width: 70 }, { key: "headcount", label: t("pay.headcount"), type: "number", width: 100, total: "sum" },
    ...[["gross_earnings", "pay.gross"], ["overtime", "pay.overtime"], ["night_allowance", "pay.night"], ["employer_social_insurance", "pay.er_si"], ["employee_social_insurance", "pay.ee_si"], ["salary_tax", "pay.tax"], ["other_deductions", "pay.other"], ["net_payable", "pay.net"]]
      .map(([k, label]) => ({ key: k, label: t(label), type: "number", digits: 2, width: 120, total: "sum", value: (r) => pounds(r.totals[k]) })),
    { key: "calculated_by", label: t("pay.calculated_by"), type: "code", width: 120 }, { key: "approved_by", label: t("pay.approved_by"), type: "code", width: 120 }, { key: "pay_date", label: t("pay.pay_date"), type: "date", width: 110 },
    { key: "delivery", label: t("pay.delivery"), width: 170, value: (r) => (r.delivery ? t("pay.delivery." + r.delivery.state) : "") },
  ], { rowKey: "key", selection: "single", totals: true, layoutKey: "PAY2010", emptyText: t("pay.no_runs"), onSelect: () => buttons(), onOpen: () => slips() });
  const sel = () => g.selected()[0];
  const b = {
    calc: ui.button({ label: t("pay.calculate"), icon: "table", kind: "primary", disabled: !can("hr.payroll.run"), onClick: () => calcDialog() }),
    slips: ui.button({ label: t("pay.slips"), icon: "table", disabled: true, onClick: () => slips() }),
    approve: ui.button({ label: t("act.approve"), icon: "check", disabled: true, onClick: () => approveDialog() }),
    reverse: ui.button({ label: t("pay.reverse"), icon: "rotate", kind: "danger", disabled: true, onClick: () => reverseDialog() }),
    send: ui.button({ label: t("pay.send"), icon: "arrow-up", disabled: !can("hr.payroll.approve"), onClick: async () => { try { const r = await api("POST", "/api/payroll/deliver", {}); ui.toast({ kind: r.stopped_by ? "warn" : "ok", title: t("pay.sent", { n: r.delivered }), text: r.stopped_by || "" }); load(); } catch (e) { fail(e); } } }),
  };
  function buttons() {
    const r = sel();
    b.slips.disabled = !r || !can("hr.payroll.read");
    b.approve.disabled = !r || r.status !== "calculated" || !can("hr.payroll.approve");
    b.reverse.disabled = !r || r.status !== "approved" || !can("hr.payroll.approve");
  }
  const sc = screen({ code: "PAY2010", title: t("nav.pay_runs"), path: [t("g.payroll")], shell, toolbar: [b.calc, b.slips, b.approve, b.reverse, b.send],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", export: () => g.exportCSV("pay-runs"), exportLabel: t("export"), columns: () => g.columnsDialog() }, grid: g });
  async function load() {
    g.setLoading();
    try { g.setRows((await api("GET", "/api/payroll/runs")).map((r) => ({ ...r, key: r.period + "#" + r.run }))); sc.result({}); buttons(); } catch (e) { g.setError(e.message); }
  }
  const previousMonth = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return ui.isoDate(d).slice(0, 7); };
  function calcDialog() {
    const period = ui.input({ value: previousMonth(), dir: "ltr" }), out = h("div");
    ui.dialog({ title: t("pay.calculate"), icon: "table", width: 480, body: h("div", { class: "hr-stack" }, ui.banner("info", t("pay.calculate_help")), h("div", { class: "eco-form" }, ui.field(t("field.period"), period, { required: true })), out),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("pay.calculate"), kind: "primary", icon: "table", onClick: async () => {
        try { const r = await api("POST", "/api/payroll/calculate", { period: period.value.trim() }); ui.toast({ kind: r.warnings.length ? "warn" : "ok", title: t("pay.calculated", { n: r.headcount }), text: r.warnings.join(" · "), keep: !!r.warnings.length }); load(); return true; }
        catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
  }
  async function slips() {
    const r = sel(); if (!r) return;
    try {
      const rows = await api("GET", `/api/payroll/runs/${r.period}/${r.run}/slips`);
      const sg = ui.grid([
        { key: "employee_code", label: t("field.employee_id"), type: "code", width: 100, frozen: true, total: "count" }, { key: "cost_center", label: t("pay.cost_center"), type: "code", width: 100 },
        ...[["basic", "pay.basic"], ["allowance", "pay.allowance"], ["absence", "pay.absence"], ["bonus", "pay.kind.bonus"], ["overtime", "pay.overtime"], ["night_allowance", "pay.night"], ["gross", "pay.gross"], ["si_employee", "pay.ee_si"], ["tax", "pay.tax"], ["other_deductions", "pay.other"], ["net", "pay.net"]]
          .map(([k, label]) => ({ key: k, label: t(label), type: "number", digits: 2, width: 110, total: "sum", value: (x) => pounds(x[k]) })),
      ], { rowKey: "employee_code", selection: "single", totals: true, emptyText: t("empty") });
      sg.setRows(rows);
      ui.dialog({ title: t("pay.slips") + " · " + r.period + " #" + r.run, icon: "table", width: 1100, body: h("div", { class: "hr-stack" }, sg.el), actions: [{ label: t("close"), kind: "primary", value: true }] });
    } catch (e) { fail(e); }
  }
  function approveDialog() {
    const r = sel(), date = ui.input({ type: "date", value: r.pay_date }), out = h("div");
    ui.dialog({ title: t("act.approve") + " · " + r.period + " #" + r.run, icon: "check", width: 560, body: h("div", { class: "hr-stack" }, ui.banner("info", t("pay.approve_help")),
      ui.props([[t("pay.headcount"), String(r.headcount)], [t("pay.gross"), money(r.totals.gross_earnings + r.totals.overtime + r.totals.night_allowance)], [t("pay.net"), money(r.totals.net_payable)], [t("pay.fingerprint"), r.fingerprint.slice(0, 16)]]),
      r.warnings.length ? ui.banner("warn", r.warnings.join(" · ")) : null, h("div", { class: "eco-form" }, ui.field(t("pay.pay_date"), date)), out),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("act.approve"), kind: "primary", icon: "check", onClick: async () => {
        try { await api("POST", `/api/payroll/runs/${r.period}/${r.run}/approve`, { fingerprint: r.fingerprint, pay_date: date.value }); ui.toast({ kind: "ok", title: t("pay.approved") }); load(); return true; }
        catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
  }
  function reverseDialog() {
    const r = sel(), reason = ui.input({}), out = h("div");
    ui.dialog({ title: t("pay.reverse") + " · " + r.period + " #" + r.run, icon: "rotate", width: 520, body: h("div", { class: "hr-stack" }, ui.banner("warn", t("pay.reverse_help")), h("div", { class: "eco-form" }, ui.field(t("field.reason"), reason, { required: true })), out),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("pay.reverse"), kind: "danger", icon: "rotate", onClick: async () => {
        try { await api("POST", `/api/payroll/runs/${r.period}/${r.run}/reverse`, { reason: reason.value }); ui.toast({ kind: "ok", title: t("pay.reversed") }); load(); return true; }
        catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
  }
  load();
  return { el: sc.el };
}

const coursesScreen = registerScreen("course", "TRN1010", "nav.courses", (R) => [
  { key: "code", label: t("field.code"), type: "code", width: 110, frozen: true, total: "count" }, { key: "name", label: t("field.name"), width: 220 },
  { key: "skill", label: t("field.skill_id"), width: 170, value: (r) => (R() && R().byId.get(r.skill_id) ? R().label(R().byId.get(r.skill_id)) : "") },
  { key: "grants_level", label: t("field.grants_level"), type: "number", width: 90 }, { key: "validity_months", label: t("field.validity_months"), type: "number", width: 100 },
  { key: "duration_hours", label: t("field.duration_hours"), type: "number", width: 100 }, { key: "onboarding_kind", label: t("field.onboarding_kind"), width: 150, value: (r) => (r.onboarding_kind ? t("onb." + r.onboarding_kind) : "") },
], { write: "hr.training.write", group: "g.training", fetch: true, people: false, icon: "bookmark" });
const sessionsScreen = registerScreen("training_session", "TRN2010", "nav.sessions", (R) => [
  { key: "status", label: t("field.status"), width: 110, frozen: true, render: (r) => badgeOf(r.status, { done: "ok", planned: "info", cancelled: "neutral" }), value: (r) => value(r.status) }, { key: "code", label: t("field.code"), type: "code", width: 110 },
  { key: "course", label: t("field.course_id"), width: 200, value: (r) => (R() && R().byId.get(r.course_id) ? R().label(R().byId.get(r.course_id)) : "") }, { key: "session_date", label: t("field.session_date"), type: "date", width: 110 },
  { key: "trainer", label: t("field.trainer"), width: 150 }, { key: "attendees", label: t("field.attendees"), width: 300, value: (r) => attendeesText(r) },
], { write: "hr.training.write", group: "g.training", fetch: true, people: false, icon: "calendar-check", preset: presetCode("training_session", "TS-", { session_date: localToday() }),
  actions: [{ key: "complete", label: "act.complete", icon: "check", kind: "primary", perm: "hr.training.write", when: (r) => r.status === "planned", run: (r, ctx) => completeDialog(r, ctx) }] });
function attendeesOf(r) { try { const a = JSON.parse(r.attendees || "[]"); return a.map((x) => (typeof x === "string" ? { employee_code: x } : x)); } catch (_) { return []; } }
const attendeesText = (r) => attendeesOf(r).map((a) => a.employee_code + (a.result ? " (" + t("result." + a.result) + ")" : "")).join(", ");
function completeDialog(sess, ctx) {
  const people = attendeesOf(sess), picks = people.map((a) => ui.select({ options: [["pass", t("result.pass")], ["fail", t("result.fail")]], value: "pass" })), out = h("div");
  ui.dialog({ title: t("act.complete") + " · " + sess.code, subtitle: sess.session_date, icon: "check", width: 520,
    body: h("div", { class: "hr-stack" }, ui.banner("info", t("trn.complete_help")), h("div", { class: "eco-form" }, people.map((a, i) => ui.field(a.employee_code, picks[i]))), out),
    actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("act.complete"), kind: "primary", icon: "check", onClick: async () => {
      try {
        const r = await api("POST", "/api/training/sessions/" + encodeURIComponent(sess.code) + "/complete", { results: people.map((a, i) => ({ employee_code: a.employee_code, result: picks[i].value })) });
        changed(); ui.toast({ kind: "ok", title: t("trn.completed", { n: r.qualified.length }), keep: true }); ctx.reload(); return true;
      } catch (e) { ui.clear(out, ui.banner("bad", e.message)); return false; } } }] });
}

const leaveTypesScreen = registerScreen("leave_type", "LEV1010", "nav.leave_types", () => [
  { key: "code", label: t("field.code"), type: "code", width: 110, frozen: true, total: "count" }, { key: "name", label: t("field.name"), width: 220 }, { key: "paid", label: t("field.paid"), width: 80, value: (r) => (r.paid === 0 ? t("no") : t("yes")) },
  { key: "annual_days", label: t("field.annual_days"), type: "number", width: 110 }, { key: "carry_over_days", label: t("field.carry_over_days"), type: "number", width: 120 }, { key: "active", label: t("field.active"), width: 80, value: (r) => (r.active === 0 ? t("no") : t("yes")) },
], { write: "hr.leave.write", group: "g.leave", fetch: true, people: false, icon: "tag", preset: () => ({ paid: 1, active: 1 }) });
const leaveRequestsScreen = registerScreen("leave_request", "LEV2010", "nav.leave_requests", (R) => [
  { key: "status", label: t("field.status"), width: 110, frozen: true, render: (r) => badgeOf(r.status, STATE_KIND), value: (r) => value(r.status) }, { key: "code", label: t("field.code"), type: "code", width: 100 },
  { key: "employee", label: t("field.employee_id"), width: 220, value: (r) => empLabel(R, r.employee_id) }, { key: "type", label: t("field.leave_type_id"), width: 150, value: (r) => (R() && R().byId.get(r.leave_type_id) ? R().byId.get(r.leave_type_id).name : "") },
  { key: "from_date", label: t("field.from_date"), type: "date", width: 110 }, { key: "to_date", label: t("field.to_date"), type: "date", width: 110 }, { key: "days", label: t("field.days"), type: "number", width: 70, total: "sum" },
  { key: "approver", label: t("field.approver"), type: "code", width: 110 }, { key: "note", label: t("field.note"), width: 220 },
], { write: "hr.leave.write", group: "g.leave", fetch: true, people: false, icon: "calendar", preset: presetCode("leave_request", "LV-"),
  actions: [changeAction("leave_request", { status: "approved" }, "act.approve", "check", "hr.leave.approve", (r) => r.status === "requested", "primary"),
    changeAction("leave_request", { status: "rejected" }, "act.reject", "x", "hr.leave.approve", (r) => r.status === "requested"),
    changeAction("leave_request", { status: "cancelled" }, "act.cancel", "x", "hr.leave.write", (r) => r.status === "requested" || r.status === "approved")] });
function leaveBalanceScreen({ shell }) {
  let R = null;
  const conds = ui.conditionPanel([{ key: "employee", label: t("field.employee_id"), type: "select", options: [], required: true }, { key: "year", label: t("field.year"), default: localToday().slice(0, 4) }], { key: "LEV3010", onSubmit: () => load() });
  const g = ui.grid([{ key: "leave_type", label: t("field.leave_type_id"), type: "code", width: 130, frozen: true }, { key: "name", label: t("field.name"), width: 220 },
    { key: "entitlement", label: t("lev.entitlement"), type: "number", width: 110, value: (r) => (r.entitlement === null ? "—" : r.entitlement) }, { key: "used", label: t("lev.used"), type: "number", width: 90 },
    { key: "left", label: t("lev.left"), type: "number", width: 90, value: (r) => (r.left === null ? "—" : r.left) }], { rowKey: "leave_type", selection: "single", layoutKey: "LEV3010", emptyText: t("empty") });
  const sc = screen({ code: "LEV3010", title: t("nav.leave_balance"), path: [t("g.leave")], shell, standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh" }, conditions: conds, grid: g });
  async function load() {
    const v = conds.values();
    if (!v.employee) return;
    g.setLoading();
    try { const r = await api("GET", `/api/leave/balance?employee=${encodeURIComponent(v.employee)}&year=${encodeURIComponent(v.year || localToday().slice(0, 4))}`); g.setRows(r.balances); sc.result({ chips: conds.chips() }); }
    catch (e) { g.setError(e.message); }
  }
  refs().then((r) => { R = r; const sel = conds.control("employee"); for (const e of r.employees) sel.append(h("option", { value: e.code, text: R.label(e) })); load(); });
  return { el: sc.el };
}

function staffingScreen({ shell }) {
  const today = localToday();
  const conds = ui.conditionPanel([{ key: "days", label: t("cmp.period"), type: "daterange", required: true, default: [today, addDays(today, 13)], span: 2 }], { key: "STF2010", onSubmit: () => load() });
  const g = ui.grid([
    { key: "date", label: t("plan.day"), type: "date", width: 110, frozen: true }, { key: "shift", label: t("field.shift_id"), type: "code", width: 80 },
    { key: "lines", label: t("stf.lines"), width: 240, value: (r) => r.lines.map((l) => `${l.line} ${l.headcount}`).join(" · ") },
    { key: "required", label: t("stf.required"), type: "number", width: 100, total: "sum" }, { key: "scheduled", label: t("stf.scheduled"), type: "number", width: 100, total: "sum" },
    { key: "gap", label: t("stf.gap"), type: "number", width: 90, total: "sum", render: (r) => (r.gap ? h("span", { class: "hr-bad", text: String(r.gap) }) : "0") },
    { key: "skills", label: t("stf.skills"), width: 380, value: (r) => r.skills.map((s) => `${s.skill} L${s.level}: ${s.covered}/${s.required}`).join(" · ") },
  ], { rowKey: (r) => r.date + r.shift, selection: "single", totals: true, layoutKey: "STF2010", emptyText: t("stf.empty"), rowStatus: (r) => (r.gap ? "down" : null) });
  const sc = screen({ code: "STF2010", title: t("nav.staffing"), path: [t("g.planning")], shell, standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("staffing"), exportLabel: t("export"), columns: () => g.columnsDialog() },
    conditions: conds, grid: g, note: h("div", { class: "hr-pad" }, ui.banner("info", t("stf.note"))) });
  async function load() {
    const v = conds.values();
    g.setLoading();
    try { g.setRows(await api("GET", `/api/staffing/gap?from=${v.days[0]}&to=${v.days[1]}`)); sc.result({ chips: conds.chips() }); } catch (e) { g.setError(e.message); }
  }
  load();
  return { el: sc.el };
}

const SCREENS = {
  HOME: ["nav.home", "dashboard", null, dashboardScreen],
  ADV1010: ["nav.advisor", "clipboard-check", null, advisorScreen],
  EMP1010: ["nav.employees", "users", "hr.employees.read", employeesScreen],
  EMP2010: ["nav.journey", "trending-up", "hr.employees.read", journeyScreen],
  ATT2010: ["nav.attendance", "calendar-check", "hr.attendance.read", attendanceScreen],
  ORG1010: ["nav.structure", "sitemap", "hr.org.read", structureScreen],
  ORG1020: ["nav.jobs", "briefcase", "hr.org.read", jobsScreen],
  ORG1030: ["nav.positions", "id-card", "hr.org.read", positionsScreen],
  SHF3010: ["nav.roster", "calendar-check", "hr.shifts.read", rosterScreen],
  SHF2010: ["nav.assignments", "users", "hr.shifts.read", assignmentsScreen],
  SHF1010: ["nav.shifts", "clock", "hr.shifts.read", shiftsScreen],
  SHF1020: ["nav.calendars", "calendar", "hr.shifts.read", calendarsScreen],
  SHF3020: ["nav.compare", "activity", "hr.shifts.read", compareScreen],
  STF2010: ["nav.staffing", "alert", "hr.shifts.read", staffingScreen],
  REC1010: ["nav.headcount", "chart", "hr.recruitment.read", headcountScreen],
  REC1020: ["nav.requisitions", "clipboard", "hr.recruitment.read", requisitionsScreen],
  REC1030: ["nav.candidates", "user-plus", "hr.recruitment.read", candidatesScreen],
  REC1040: ["nav.onboarding", "clipboard-check", "hr.recruitment.read", onboardingScreen],
  REC1050: ["nav.agencies", "building", "hr.recruitment.read", agenciesScreen],
  REC1060: ["nav.contracts", "id-card", "hr.recruitment.read", contractsScreen],
  OVT1010: ["nav.overtime", "clock", "hr.overtime.read", overtimeScreen],
  OVT1020: ["nav.overtime_figures", "table", "hr.overtime.read", overtimeFiguresScreen],
  PAY2010: ["nav.pay_runs", "table", "hr.payroll.read", payRunsScreen],
  PAY1010: ["nav.pay_profiles", "chart", "hr.payroll.read", payProfilesScreen],
  PAY1020: ["nav.pay_adjustments", "edit", "hr.payroll.read", payAdjustmentsScreen],
  TRN1010: ["nav.courses", "bookmark", "hr.training.read", coursesScreen],
  TRN2010: ["nav.sessions", "calendar-check", "hr.training.read", sessionsScreen],
  LEV2010: ["nav.leave_requests", "calendar", "hr.leave.read", leaveRequestsScreen],
  LEV3010: ["nav.leave_balance", "table", "hr.leave.read", leaveBalanceScreen],
  LEV1010: ["nav.leave_types", "tag", "hr.leave.read", leaveTypesScreen],
  SKL3010: ["nav.matrix", "table", "hr.skills.read", matrixScreen],
  SKL2010: ["nav.qualifications", "shield", "hr.skills.read", qualificationsScreen],
  SKL1010: ["nav.skills", "tag", "hr.skills.read", skillsScreen],
  DSC2010: ["nav.violations", "flag", "hr.discipline.read", violationsScreen],
  DSC1010: ["nav.penalty_rules", "scale", "hr.discipline.read", rulesScreen],
  SEC9010: ["nav.users", "user", "admin.users.manage", usersScreen],
  SEC9020: ["nav.profiles", "shield", "admin.users.manage", profilesScreen],
  SEC9030: ["nav.audit", "history", "admin.audit.read", auditScreen],
  SYS9070: ["nav.backups", "archive", "admin.backup.manage", backupsScreen],
  SYS9100: ["nav.health", "activity", "admin.system.read", healthScreen],
  SYS9060: ["nav.settings", "settings", "admin.settings.manage", settingsScreen],
  HLP1010: ["nav.help", "bookmark", null, helpCenterScreen],
};
const MENU = [["people", "users", ["EMP1010", "EMP2010", "ATT2010", "ADV1010"]], ["planning", "calendar-check", ["SHF3010", "SHF2010", "SHF1010", "SHF1020", "SHF3020", "STF2010"]],
  ["recruitment", "user-plus", ["REC1010", "REC1020", "REC1030", "REC1040", "REC1060", "REC1050"]], ["overtime", "clock", ["OVT1010", "OVT1020"]], ["payroll", "chart", ["PAY2010", "PAY1010", "PAY1020"]], ["training", "bookmark", ["TRN2010", "TRN1010"]], ["leave", "calendar", ["LEV2010", "LEV3010", "LEV1010"]], ["skills", "tag", ["SKL3010", "SKL2010", "SKL1010"]], ["discipline", "scale", ["DSC2010", "DSC1010"]], ["organisation", "sitemap", ["ORG1010", "ORG1020", "ORG1030"]], ["security", "shield", ["SEC9010", "SEC9020", "SEC9030"]], ["system", "settings", ["SYS9070", "SYS9100", "SYS9060", "HLP1010"]]];
function showShell() {
  const screens = {};
  for (const [code, [key, icon, perm, create]] of Object.entries(SCREENS)) {
    if (perm && !can(perm)) continue;
    screens[code] = { title: t(key), icon, create, path: [], keywords: t(key + ".help") };
  }
  screens.HOME.hidden = true;
  const menu = [{ id: "home", code: "HOME", label: t("nav.home"), icon: "dashboard" }].concat(MENU.map(([id, icon, codes]) => ({ id, label: t("g." + id), icon,
    children: codes.filter((c) => screens[c]).map((c) => ({ code: c, label: screens[c].title, icon: screens[c].icon })) }))).filter((g) => g.code || g.children.length);
  const c = S.info.company || {};
  const shell = ui.createShell({
    product: { name: t("product.name"), short: "HR", edition: t("edition") }, company: c.name ? { name: c.name, code: c.code, note: c.provisional ? t("company.provisional") : t("company.source." + c.source) } : null,
    user: { name: S.me.display_name, role: profileName(S.me.profile), detail: S.me.user }, menu, screens, home: "HOME", maxTabs: 10, hideCodesInMenu: true, searchExample: "EMP1010",
    onTheme: setTheme, onLanguage: setLanguage,
    topActions: [ui.button({ label: t("guide.button"), icon: "help", kind: "top", title: t("guide.title") + " (F1)", onClick: () => openHelp(), cls: "hr-guide-btn" })],
    // actions in the screen search (Ctrl+K), as in Mizan's command palette: only what this person may do
    commands: [
      can("hr.employees.write") ? { title: t("new.employee"), icon: "user-plus", keywords: "new add hire employee", run: () => editRecord("employee", null).then((ok) => ok && shell.open("EMP1010")) } : null,
      can("hr.org.write") ? { title: t("new.position"), icon: "id-card", keywords: "new position", run: () => editRecord("position", null) } : null,
      can("hr.shifts.write") ? { title: t("new.shift_assignment"), icon: "calendar-check", keywords: "assign shift", run: () => editRecord("shift_assignment", null, { kind: "regular", valid_from: localToday() }) } : null,
      can("hr.skills.write") ? { title: t("new.employee_skill"), icon: "shield", keywords: "certify qualification skill", run: () => editRecord("employee_skill", null, { level: 3, certified_on: localToday() }) } : null,
      can("admin.backup.manage") ? { title: t("backup.create"), icon: "archive", keywords: "backup now", run: async () => { try { const r = await api("POST", "/api/admin/backups"); ui.toast({ kind: r.rehearsal.ok ? "ok" : "bad", title: t("backup.made", { name: r.name }), keep: true }); } catch (e) { fail(e); } } } : null,
      { title: t("password.title"), icon: "key", keywords: "password", run: () => showPassword(false) },
    ].filter(Boolean),
    onActivate: () => ui.prefs.set("tabs", [...document.querySelectorAll(".eco-view")].map((v) => v.dataset.code)),
    userMenu: [{ label: t("password.title"), icon: "key", onSelect: () => showPassword(false) },
      { label: t("nav.signout"), icon: "logout", onSelect: async () => { try { await api("POST", "/api/logout"); } catch (_) { /* signed out anyway */ } S.me = null; ui.prefs.set("tabs", []); showLogin(); } }],
  });
  S.shell = shell;
  document.addEventListener("keydown", (ev) => { if (ev.key === "F1") { ev.preventDefault(); openHelp(); } });
  if (!ui.prefs.get("guide:welcomed", false) && guideAtLeast("basic")) {  // the first visit offers the tour of the product
    ui.prefs.set("guide:welcomed", true);
    setTimeout(() => ui.toast({ kind: "info", title: t("guide.welcome"), text: t("guide.welcome_text"), timeout: 12000 }), 1500);
  }
  document.body.replaceChildren(shell.el);
  const conn = ui.statusItem("wifi", ui.kitText("connected"), "is-ok"), clock = ui.statusItem("clock", ui.fmtTime());
  shell.setStatus([conn, ui.statusItem("building", (c.name || "") + (c.code ? " · " + c.code : "")), c.provisional ? ui.statusItem("alert", t("company.provisional"), "is-warn") : null,
    ui.statusItem("user", S.me.user + " · " + profileName(S.me.profile)), clock, ui.statusItem(null, t("product.name") + " " + S.info.version, "is-end"),
    ui.statusItem("globe", S.lang === "ar" ? "العربية" : "English")].filter(Boolean));
  setInterval(() => { clock.lastChild.textContent = ui.fmtTime(); }, 1000);
  setInterval(async () => {
    let ok = false;
    try { ok = (await fetch("/api/info", { cache: "no-store" })).ok; } catch (_) { ok = false; }
    conn.className = "eco-status-item " + (ok ? "is-ok" : "is-bad");
    conn.lastChild.textContent = ok ? ui.kitText("connected") : ui.kitText("disconnected");
  }, 15000);
  shell.start(ui.prefs.get("tabs", []));
}

boot();
