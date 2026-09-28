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
const value = (v) => (v && has("value." + v) ? t("value." + v) : v);
const profileName = (code, fallback) => (has("profile." + code) ? t("profile." + code) : fallback || code);
function fail(e) { ui.toast({ kind: "bad", title: t("failed_title"), text: e.message, timeout: 7000 }); }

// ------------------------------------------------------------------ start
async function boot() {
  ui.configure({ prefix: "hr", product: "hr" });
  S.info = await (await fetch("/api/info")).json();
  await loadLang(ui.prefs.get("lang", S.info.language || "en"));
  ui.configure({ lang: S.lang, theme: ui.prefs.get("theme", "light"), density: ui.prefs.get("density", "compact") });
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
  document.body.replaceChildren(h("div", { class: "hr-door" }, brand, h("main", { class: "hr-door-main" }, tools, h("div", { class: ["hr-door-card", wide && "is-wide"] }, content))));
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
  const [units, jobs, positions, employees, shifts, calendars, skillList] = await Promise.all([get("org_unit", "hr.org.read"), get("job", "hr.org.read"), get("position", "hr.org.read"),
    get("employee", "hr.employees.read"), get("shift", "hr.shifts.read"), get("work_calendar", "hr.shifts.read"), get("skill", "hr.skills.read")]);
  const byId = new Map([...units, ...jobs, ...positions, ...employees, ...shifts, ...calendars, ...skillList].map((r) => [r.id, r]));
  const name = (r) => (r ? r.name || r.title || r.preferred_name || (r.job_id && byId.get(r.job_id) ? byId.get(r.job_id).title : "") || r.code : "");
  const label = (r) => (r ? r.code + " · " + name(r) : "");
  const unitOf = (emp) => { const p = emp && byId.get(emp.position_id); return p ? byId.get(p.org_unit_id) : null; };
  const jobOf = (emp) => { const p = emp && byId.get(emp.position_id); return p ? byId.get(p.job_id) : null; };
  S.refs = { units, jobs, positions, employees, shifts, calendars, skills: skillList, byId, name, label, unitOf, jobOf, company: units.find((u) => u.type === "company") };
  return S.refs;
}
const changed = () => { S.refs = null; };

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
};
// records whose code is made from their content (one per person and day, per person and skill ...)
const AUTO_CODE = {
  shift_assignment: (v, R) => { const e = R.byId.get(v.employee_id); return e && v.valid_from ? e.code + "-" + v.valid_from + "-" + (v.kind === "temporary" ? "T" : "R") : ""; },
  employee_skill: (v, R) => { const e = R.byId.get(v.employee_id), k = R.byId.get(v.skill_id); return e && k ? e.code + "-" + k.code : ""; },
};
const localToday = () => ui.isoDate(new Date());
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
      icon: { employee: "user", org_unit: "sitemap", job: "briefcase", position: "id-card", shift: "clock", work_calendar: "calendar", shift_assignment: "calendar-check", skill: "tag", employee_skill: "shield" }[entity],
      width: entity === "employee" ? 680 : 560,
      body: h("div", { class: "hr-editor" }, sections, out), onClose: (r) => resolve(r === true),
      actions: [{ label: t("cancel"), kind: "ghost", value: false }, { label: t("save"), kind: "primary", icon: "save", onClick: async () => {
        const values = {};
        const nums = new Set(FORM[entity].flatMap(([, fs]) => fs.filter(([, o]) => o.num).map(([f]) => f)));
        for (const [f, c] of Object.entries(inputs)) {
          if (f === "code") continue;
          const raw = c.getValue ? c.getValue() : c.value;
          values[f] = raw === "" && !c.getValue ? null : f === "critical" || nums.has(f) ? Number(raw) : raw;
        }
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
  ], { rowKey: "id", selection: "multi", totals: true, layoutKey: "EMP1010", emptyText: t("emp.empty"), onSelect: (sel) => { draw(sel); buttons(sel); }, onOpen: (r) => !r.deleted && can("hr.employees.write") && edit(r) });

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
  const sc = ui.screen({ code: "EMP1010", title: t("nav.employees"), path: [t("g.people")], shell, toolbar: [act.add, act.edit, act.bin, act.restore],
    standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh", reset: () => { conds.reset(); load(); }, resetLabel: t("reset"), export: () => g.exportCSV("employees"), exportLabel: t("export"), columns: () => g.columnsDialog() },
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
      ]),
      !e.deleted && can("hr.employees.write") ? h("div", { class: "hr-pad hr-row" }, ui.button({ label: t("edit"), icon: "edit", onClick: () => edit(e) })) : null);
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
  const sc = ui.screen({ code: "ORG1010", title: t("nav.structure"), path: [t("g.organisation")], shell, toolbar: [act.add, act.edit, act.bin],
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
      onSelect: (sel) => { act.edit.disabled = sel.length !== 1 || !can(o.write); act.bin.disabled = !sel.length || !can("hr.employees.delete"); drawDetail(sel[0]); },
      onOpen: (r) => can(o.write) && editRecord(entity, r).then((ok) => ok && load()) });
    const act = {
      add: ui.button({ label: t("new." + entity), icon: "plus", kind: "primary", disabled: !can(o.write), onClick: () => editRecord(entity, null).then((ok) => ok && load()) }),
      edit: ui.button({ label: t("edit"), icon: "edit", disabled: true, onClick: () => editRecord(entity, g.selected()[0]).then((ok) => ok && load()) }),
      bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: () => binRecords(entity, g.selected()).then((ok) => ok && load()) }),
    };
    const sc = ui.screen({ code, title: t(titleKey), path: [t(o.group)], shell, toolbar: [act.add, act.edit, act.bin],
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
      try { R = await refs(true); g.setRows(o.rows(R)); sc.result({ ms: Math.round(performance.now() - t0) }); drawDetail(null); }
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
    onSelect: (sel) => { const a = sel[0]; act.edit.disabled = !a || !can("hr.shifts.write") || stateOf(a) === "ended"; act.bin.disabled = !a || a.valid_from < today || !can("hr.employees.delete"); },
    onOpen: (r) => can("hr.shifts.write") && editRecord("shift_assignment", r).then((ok) => ok && load()) });
  const act = {
    add: ui.button({ label: t("new.shift_assignment"), icon: "plus", kind: "primary", disabled: !can("hr.shifts.write"), onClick: () => editRecord("shift_assignment", null, { kind: "regular", valid_from: today }).then((ok) => ok && load()) }),
    edit: ui.button({ label: t("asg.edit_or_end"), icon: "edit", disabled: true, onClick: () => editRecord("shift_assignment", g.selected()[0]).then((ok) => ok && load()) }),
    bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: () => binRecords("shift_assignment", g.selected()).then((ok) => ok && load()) }),
  };
  const sc = ui.screen({ code: "SHF2010", title: t("nav.assignments"), path: [t("g.planning")], shell, toolbar: [act.add, act.edit, act.bin],
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
  const sc = ui.screen({ code: "SHF3010", title: t("nav.roster"), path: [t("g.planning")], shell,
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
      g = ui.grid(cols(), { rows: list, rowKey: "id", selection: "single", totals: true, layoutKey: null, rowHeight: 36, emptyText: t("plan.empty") });
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
  const sc = ui.screen({ code: "SHF3020", title: t("nav.compare"), path: [t("g.planning")], shell,
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
    onSelect: (sel) => { act.edit.disabled = !sel.length || !can("hr.skills.write"); act.bin.disabled = !sel.length || !can("hr.employees.delete"); },
    onOpen: (r) => can("hr.skills.write") && editRecord("employee_skill", r).then((ok) => ok && load()) });
  const act = {
    add: ui.button({ label: t("new.employee_skill"), icon: "plus", kind: "primary", disabled: !can("hr.skills.write"), onClick: () => editRecord("employee_skill", null, { level: 3, certified_on: today }).then((ok) => ok && load()) }),
    edit: ui.button({ label: t("qual.recertify"), icon: "refresh", disabled: true, onClick: () => editRecord("employee_skill", g.selected()[0]).then((ok) => ok && load()) }),
    bin: ui.button({ label: t("delete"), icon: "trash", kind: "danger", disabled: true, onClick: () => binRecords("employee_skill", g.selected()).then((ok) => ok && load()) }),
  };
  const sc = ui.screen({ code: "SKL2010", title: t("nav.qualifications"), path: [t("g.skills")], shell, toolbar: [act.add, act.edit, act.bin],
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
  const sc = ui.screen({ code: "SKL3010", title: t("nav.matrix"), path: [t("g.skills")], shell, toolbar: [legend],
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
      { rows, rowKey: "id", selection: "single", totals: true, rowHeight: 32, emptyText: skillCols.length ? t("empty") : t("qual.no_skills") });
      g.el.classList.add("hr-roster");
      ui.clear(host, g.el);
    } catch (e) { ui.clear(host, ui.empty({ icon: "x-octagon", title: e.message })); }
  }
  load();
  return { el: sc.el };
}

// ------------------------------------------------------------------ Attendance (the migrated application, behind the same sign-in)
function attendanceScreen({ shell }) {
  const note = h("div");
  const sc = ui.screen({ code: "ATT2010", title: t("nav.attendance"), path: [t("g.people")], shell,
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
  const sc = ui.screen({ code: "SEC9010", title: t("nav.users"), path: [t("g.security")], shell,
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
const PERM_GROUPS = [["perm_group.people", ["hr.employees.read", "hr.employees.write", "hr.employees.delete", "hr.recycle.restore", "hr.import.run"]],
  ["perm_group.organisation", ["hr.org.read", "hr.org.write"]], ["perm_group.attendance", ["hr.attendance.read", "hr.attendance.upload"]],
  ["perm_group.planning", ["hr.shifts.read", "hr.shifts.write"]], ["perm_group.skills", ["hr.skills.read", "hr.skills.write"]],
    ["perm_group.administration", ["admin.users.manage", "admin.audit.read", "admin.system.read", "admin.settings.manage"]], ["perm_group.backups", ["admin.backup.manage", "admin.backup.restore"]]];
function profilesScreen({ shell }) {
  let profiles = [], current = null;
  const list = h("div", { class: "hr-plist" }), matrix = h("div", { class: "hr-matrix" });
  const sc = ui.screen({ code: "SEC9020", title: t("nav.profiles"), path: [t("g.security")], shell, standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh" },
    body: ui.split(h("div", { class: "hr-side" }, h("div", { class: "hr-side-head" }, h("strong", { text: t("profile.title") })), list), matrix, { key: "SEC9020:side", initial: 260, min: 200, second: false }) });
  function draw() {
    ui.clear(list, profiles.map((p) => h("button", { type: "button", class: ["hr-plist-item", current && current.code === p.code && "is-on"], onclick: () => { current = p; draw(); } },
      h("span", { class: "hr-plist-icon" }, ui.icon(p.code === "administrator" ? "shield" : "users", 16)), h("div", {}, h("b", { text: profileName(p.code, p.name) }), h("small", { class: "eco-muted", text: t("user.rights", { n: p.perms.length }) })))));
    if (!current) { ui.clear(matrix, ui.empty({ icon: "shield", title: t("pick.one") })); return; }
    const locked = current.code === "administrator";
    const boxes = {};
    ui.clear(matrix, h("div", { class: "hr-record-head" }, h("span", { class: "hr-record-icon" }, ui.icon("shield", 20)), h("div", { class: "hr-record-titles" }, h("div", { class: "eco-muted" }, ui.ltr(current.code)), h("h2", { text: profileName(current.code, current.name) })),
      locked ? null : ui.button({ label: t("save"), icon: "save", kind: "primary", onClick: async () => {
        const perms = Object.entries(boxes).filter(([, c]) => c.checked).map(([p]) => p);
        try { await api("PUT", "/api/admin/profiles/" + current.code, { name: current.name, perms, expected_ver: current.ver }); ui.toast({ kind: "ok", title: t("saved"), text: profileName(current.code, current.name) }); load(current.code); }
        catch (e) { fail(e); }
      } })),
    locked ? h("div", { class: "hr-pad" }, ui.banner("info", t("profile.admin_locked"))) : null,
    h("div", { class: "hr-perm-grid" }, PERM_GROUPS.map(([gk, perms]) => h("section", { class: "hr-perm-group" }, h("h3", { text: t(gk) }), perms.map((p) => {
      const c = h("input", { type: "checkbox", class: "eco-check", checked: current.perms.includes(p), disabled: locked });
      boxes[p] = c;
      return h("label", { class: "hr-perm-row" }, c, h("div", {}, h("span", { text: t("perm." + p) }), h("small", { class: "eco-muted" }, ui.ltr(p))));
    })))));
  }
  async function load(keep) {
    try { profiles = await api("GET", "/api/admin/profiles"); current = profiles.find((p) => p.code === (keep || (current && current.code))) || profiles.find((p) => p.code === "hr_officer") || profiles[0]; draw(); }
    catch (e) { ui.clear(matrix, ui.empty({ icon: "x-octagon", title: e.message })); }
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
  const sc = ui.screen({ code: "SEC9030", title: t("nav.audit"), path: [t("g.security")], shell,
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
  const sc = ui.screen({ code: "SYS9070", title: t("nav.backups"), path: [t("g.system")], shell, toolbar: [make],
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
  const sc = ui.screen({ code: "SYS9100", title: t("nav.health"), path: [t("g.system")], shell, standard: { inquiry: () => load(), inquiryLabel: t("refresh"), inquiryIcon: "refresh" }, body });
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
  const sc = ui.screen({ code: "SYS9060", title: t("nav.settings"), path: [t("g.system")], shell, toolbar: [save], body });
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
          [t("setup.source"), c.source ? t("company.source." + c.source) : null]]), c.provisional ? ui.banner("warn", t("company.provisional_help")) : null) }));
    } catch (e) { ui.clear(body, ui.banner("bad", e.message)); }
  }
  async function store() {
    try { await api("PUT", "/api/admin/settings", { autostart: auto.querySelector("input").checked, language: lang.value_, backup_hours: Number(hours.value) }); ui.toast({ kind: "ok", title: t("saved") }); }
    catch (e) { fail(e); }
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
      const [hh, audit, users] = await Promise.all([can("admin.system.read") ? api("GET", "/api/admin/health").catch(() => null) : null,
        can("admin.audit.read") ? api("GET", "/api/admin/audit?limit=8").catch(() => []) : [], can("admin.users.manage") ? api("GET", "/api/admin/users").catch(() => []) : []]);
      const emp = R.employees, active = emp.filter((e) => e.employment_status === "Active").length, leave = emp.filter((e) => e.employment_status === "Leave").length;
      const depts = R.units.filter((u) => u.type === "department");
      const filled = R.positions.filter((p) => emp.some((e) => e.position_id === p.id)).length;
      const byDept = depts.map((d) => [d, emp.filter((e) => { const u = R.unitOf(e); return u && (u.id === d.id || u.parent_id === d.id); }).length]).sort((a, b) => b[1] - a[1]).slice(0, 8);
      const statuses = ["Active", "Leave", "Suspended", "Terminated"].map((s) => [s, emp.filter((e) => e.employment_status === s).length]);
      const c = S.info.company || {};
      const quick = (code, ic, key) => (shell.screens[code] ? h("button", { type: "button", class: "hr-quick", onclick: () => shell.open(code) }, h("span", { class: "hr-quick-ic" }, ui.icon(ic, 18)), h("span", { text: t(key) })) : null);
      ui.clear(body,
        h("div", { class: "hr-dash-head" }, h("div", {}, h("h1", { text: t("home.hello", { name: S.me.display_name }) }), h("span", { class: "eco-muted" }, c.name || "", " · ", new Date().toLocaleDateString(S.lang === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" }))),
          h("span", { class: "eco-grow" }), h("div", { class: "hr-row" }, quick("EMP1010", "user-plus", "nav.employees"), quick("ATT2010", "calendar-check", "nav.attendance"), quick("SYS9070", "archive", "nav.backups"))),
        c.provisional ? ui.banner("warn", t("company.provisional_help"), { title: t("company.provisional") }) : null,
        h("div", { class: "hr-kpis" },
          ui.kpi({ label: t("dash.employees"), value: ui.fmtNumber(emp.length), icon: "users", hint: t("dash.active_n", { n: active }), status: "run" }),
          ui.kpi({ label: t("dash.on_leave"), value: ui.fmtNumber(leave), icon: "calendar", status: "idle", hint: t("dash.today") }),
          ui.kpi({ label: t("dash.departments"), value: ui.fmtNumber(depts.length), icon: "sitemap", hint: t("dash.units_n", { n: R.units.length }) }),
          ui.kpi({ label: t("dash.positions"), value: filled + " / " + R.positions.length, icon: "id-card", hint: t("dash.filled"), status: "setup" }),
          ui.kpi({ label: t("dash.users"), value: users.length ? String(users.filter((u) => u.active).length) : "—", icon: "shield", hint: t("dash.can_sign_in"), status: "hold" })),
        h("div", { class: "hr-dash-grid" }, h("div", { class: "hr-dash-col" },
          ui.card({ title: t("dash.by_department"), subtitle: t("dash.by_department_sub"), icon: "chart", body: byDept.length ? ui.barChart({ labels: byDept.map(([d]) => d.code), series: [{ label: t("dash.employees"), values: byDept.map(([, n]) => n) }], height: 240, width: 760 })
            : ui.empty({ icon: "chart", title: t("dash.no_data"), text: t("dash.no_data_help") }), actions: shell.screens.ORG1010 ? [ui.button({ label: t("nav.structure"), kind: "ghost", size: "sm", icon: "sitemap", onClick: () => shell.open("ORG1010") })] : null }),
          audit.length ? ui.card({ title: t("dash.activity"), icon: "history", body: h("ul", { class: "hr-activity" }, audit.map((a) => h("li", {}, h("span", { class: "hr-dot" }), h("div", {}, h("b", {}, ui.ltr(a.event)),
            h("small", { class: "eco-muted" }, ui.ltr(a.actor), " · ", ui.ltr((a.at || "").slice(0, 16).replace("T", " ")))))) ), actions: [ui.button({ label: t("nav.audit"), kind: "ghost", size: "sm", onClick: () => shell.open("SEC9030") })] }) : null),
          h("div", { class: "hr-dash-col" },
          ui.card({ title: t("dash.status"), icon: "activity", body: h("div", { class: "hr-bars" }, statuses.map(([s, n]) => h("div", { class: "hr-bar-row" }, h("span", { text: value(s) }),
            ui.progress(n, Math.max(1, emp.length), { label: String(n), status: STATUS_ST[s] }))) ) }),
          hh ? ui.card({ title: t("dash.system"), icon: "shield", body: h("div", { class: "hr-checks" },
            [[hh.journal.ok, t("health.journal")], [hh.audit.ok, t("health.audit")], [!!(hh.last_backup && hh.last_backup.rehearsal && hh.last_backup.rehearsal.ok), t("health.last_backup")], [hh.recovery ? hh.recovery.intact : null, t("health.recovery")]]
              .map(([ok, k]) => h("div", { class: "hr-check" }, ui.icon(ok === null ? "info" : ok ? "check-circle" : "x-octagon", 16, ok === null ? "eco-muted" : ok ? "hr-ok" : "hr-bad"), h("span", { text: k })))),
          actions: [ui.button({ label: t("nav.health"), kind: "ghost", size: "sm", onClick: () => shell.open("SYS9100") })] }) : null)));
    } catch (e) { ui.clear(body, ui.banner("bad", e.message)); }
  }
  load();
  return { el: body, onActivate: () => { if (S.refs === null) load(); } };
}

// ------------------------------------------------------------------ the shell
const SCREENS = {
  HOME: ["nav.home", "dashboard", null, dashboardScreen],
  EMP1010: ["nav.employees", "users", "hr.employees.read", employeesScreen],
  ATT2010: ["nav.attendance", "calendar-check", "hr.attendance.read", attendanceScreen],
  ORG1010: ["nav.structure", "sitemap", "hr.org.read", structureScreen],
  ORG1020: ["nav.jobs", "briefcase", "hr.org.read", jobsScreen],
  ORG1030: ["nav.positions", "id-card", "hr.org.read", positionsScreen],
  SHF3010: ["nav.roster", "calendar-check", "hr.shifts.read", rosterScreen],
  SHF2010: ["nav.assignments", "users", "hr.shifts.read", assignmentsScreen],
  SHF1010: ["nav.shifts", "clock", "hr.shifts.read", shiftsScreen],
  SHF1020: ["nav.calendars", "calendar", "hr.shifts.read", calendarsScreen],
  SHF3020: ["nav.compare", "activity", "hr.shifts.read", compareScreen],
  SKL3010: ["nav.matrix", "table", "hr.skills.read", matrixScreen],
  SKL2010: ["nav.qualifications", "shield", "hr.skills.read", qualificationsScreen],
  SKL1010: ["nav.skills", "tag", "hr.skills.read", skillsScreen],
  SEC9010: ["nav.users", "user", "admin.users.manage", usersScreen],
  SEC9020: ["nav.profiles", "shield", "admin.users.manage", profilesScreen],
  SEC9030: ["nav.audit", "history", "admin.audit.read", auditScreen],
  SYS9070: ["nav.backups", "archive", "admin.backup.manage", backupsScreen],
  SYS9100: ["nav.health", "activity", "admin.system.read", healthScreen],
  SYS9060: ["nav.settings", "settings", "admin.settings.manage", settingsScreen],
};
const MENU = [["people", "users", ["EMP1010", "ATT2010"]], ["planning", "calendar-check", ["SHF3010", "SHF2010", "SHF1010", "SHF1020", "SHF3020"]], ["skills", "tag", ["SKL3010", "SKL2010", "SKL1010"]], ["organisation", "sitemap", ["ORG1010", "ORG1020", "ORG1030"]], ["security", "shield", ["SEC9010", "SEC9020", "SEC9030"]], ["system", "settings", ["SYS9070", "SYS9100", "SYS9060"]]];
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
    onActivate: () => ui.prefs.set("tabs", [...document.querySelectorAll(".eco-view")].map((v) => v.dataset.code)),
    userMenu: [{ label: t("password.title"), icon: "key", onSelect: () => showPassword(false) },
      { label: t("nav.signout"), icon: "logout", onSelect: async () => { try { await api("POST", "/api/logout"); } catch (_) { /* signed out anyway */ } S.me = null; ui.prefs.set("tabs", []); showLogin(); } }],
  });
  S.shell = shell;
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
