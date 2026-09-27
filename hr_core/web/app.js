// HR-System screens (phase 2.5). One page, plain JavaScript, no library.
// Every text goes through t(key): the dictionaries are /ui/i18n/en.json and /ui/i18n/ar.json (same keys, checked by
// TEST_HR_DELIVERY.py). Every value from the server is written with textContent, never as HTML.
"use strict";

const S = { info: null, me: null, dict: {}, fallback: {}, lang: "en" };
const $ = (sel) => document.querySelector(sel);

function t(key, vars) {
  let s = S.dict[key] ?? S.fallback[key] ?? key;
  for (const [k, v] of Object.entries(vars || {})) s = s.replace("{" + k + "}", v);
  return s;
}

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "text") e.textContent = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) if (kid !== null && kid !== undefined) e.append(kid instanceof Node ? kid : String(kid));
  return e;
}

async function api(method, path, body) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (method !== "GET") { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body || {}); }
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch (_) { data = null; }
  if (r.status === 401 && !path.startsWith("/api/login")) { S.me = null; go("login"); throw new Error(t("err.signin")); }
  if (!r.ok) throw new Error((data && (t("code." + data.error) !== "code." + data.error ? t("code." + data.error) : data.message)) || r.status);
  return data;
}

async function loadLang(lang) {
  S.fallback = await (await fetch("/ui/i18n/en.json")).json();
  S.dict = lang === "en" ? S.fallback : await (await fetch("/ui/i18n/" + lang + ".json")).json();
  S.lang = lang;
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  $("#lang").value = lang;
}

function can(perm) { return !!(S.me && S.me.permissions.includes(perm)); }
function go(page, q) { location.hash = "#/" + page + (q ? "?" + q : ""); }
function msg(kind, text) { return el("div", { class: "msg " + kind, text }); }
function field(label, input) { return el("div", {}, el("label", { text: label }), input); }
function busy(button, fn) {
  return async (ev) => {
    ev && ev.preventDefault();
    button.disabled = true;
    try { await fn(); } finally { button.disabled = false; }
  };
}

// ------------------------------------------------------------------ frame
const PAGES = [
  ["home", "nav.home", null], ["employees", "nav.employees", "hr.employees.read"], ["organisation", "nav.organisation", "hr.org.read"],
  ["attendance", "nav.attendance", "hr.attendance.read"], ["users", "nav.users", "admin.users.manage"],
  ["backups", "nav.backups", "admin.backup.manage"], ["health", "nav.health", "admin.system.read"], ["settings", "nav.settings", "admin.settings.manage"],
];

function frame(page) {
  const signedIn = !!S.me;
  $("#logout").textContent = t("nav.signout");
  $("#logout").hidden = !signedIn;  // the header stays: the language can be chosen before signing in
  $("#who").textContent = signedIn ? S.me.display_name : "";
  $("#brand").textContent = t("product.name");
  const nav = $("#nav");
  nav.replaceChildren(...(signedIn ? PAGES.filter(([, , p]) => !p || can(p)).map(([id, key]) =>
    el("a", { href: "#/" + id, class: id === page ? "on" : null, text: t(key) })) : []));
  const c = S.info && S.info.company;
  $("#foot").textContent = t("product.name") + " " + (S.info ? S.info.version : "") + (c ? " · " + c.name + " (" + c.code + ")" : "") +
    (c && c.provisional ? " · " + t("company.provisional") : "");
  document.title = t("product.name");
}

async function route() {
  const [page, query] = (location.hash.replace(/^#\/?/, "") || "home").split("?");
  const params = new URLSearchParams(query || "");
  S.info = await (await fetch("/api/info")).json();
  if (!S.lang_set) { await loadLang(localStorage.getItem("hr.lang") || S.info.language || "en"); S.lang_set = true; }
  const main = $("#main");
  if (S.info.error) { frame(null); main.replaceChildren(pageError()); return; }
  if (S.info.setup_needed) { frame(null); main.replaceChildren(pageSetup()); return; }
  if (!S.me && page !== "login") {
    try { S.me = await api("GET", "/api/me"); } catch (_) { return; }
  }
  if (S.me && S.me.must_change && page !== "password") return go("password");
  frame(page);
  const pages = { login: pageLogin, home: pageHome, employees: pageEmployees, organisation: pageOrganisation, attendance: pageAttendance,
                  users: pageUsers, backups: pageBackups, health: pageHealth, settings: pageSettings, password: pagePassword };
  main.replaceChildren(el("p", { class: "muted", text: "…" }));
  try { main.replaceChildren(await (pages[page] || pageHome)(params)); }
  catch (e) { main.replaceChildren(msg("bad", e.message)); }
}

// ------------------------------------------------------------------ first run, errors, sign-in
function pageError() {
  return el("div", { class: "card narrow" }, el("h1", { text: t("error.title") }), msg("bad", S.info.error.message), el("p", { class: "muted", text: t("error.help") }));
}

function pageSetup() {
  const local = S.info.local;
  const src = el("select", {}, el("option", { value: "local", text: t("setup.source.local") }), el("option", { value: "owner", text: t("setup.source.owner") }));
  const cid = el("input", { placeholder: "xxxxxxxx-xxxx-7xxx-xxxx-xxxxxxxxxxxx", dir: "ltr" });
  const idRow = field(t("setup.company_id"), cid);
  idRow.hidden = true;
  src.addEventListener("change", () => { idRow.hidden = src.value !== "owner"; });
  const code = el("input", { dir: "ltr" }), name = el("input"), user = el("input", { dir: "ltr" }), dname = el("input"), pw = el("input", { type: "password" });
  const out = el("div");
  const btn = el("button", { type: "submit", text: t("setup.install") });
  const form = el("form", {}, el("h2", { text: t("setup.company") }), el("p", { class: "muted", text: t("setup.company_help") }),
    field(t("setup.source"), src), idRow, field(t("setup.company_code"), code), field(t("setup.company_name"), name),
    el("h2", { text: t("setup.admin") }), field(t("user.username"), user), field(t("user.display_name"), dname), field(t("user.password"), pw),
    el("p", { class: "muted", text: t("user.password_rule") }), btn, out);
  form.addEventListener("submit", busy(btn, async () => {
    try {
      await api("POST", "/api/setup/install", { company: { source: src.value, owner_app: src.value === "owner" ? "mizan" : null, id: cid.value.trim(), code: code.value, name: name.value },
                                                admin: { username: user.value, display_name: dname.value, password: pw.value } });
      go("login"); route();
    } catch (e) { out.replaceChildren(msg("bad", e.message)); }
  }));
  return el("div", { class: "card narrow" }, el("h1", { text: t("setup.title") }), local ? form : msg("warn", t("setup.local_only")));
}

function pageLogin(params) {
  const user = el("input", { autocomplete: "username", dir: "ltr" }), pw = el("input", { type: "password", autocomplete: "current-password" });
  const out = el("div"), btn = el("button", { type: "submit", text: t("login.submit") });
  const form = el("form", {}, field(t("user.username"), user), field(t("user.password"), pw), el("p"), btn, out);
  form.addEventListener("submit", busy(btn, async () => {
    try {
      S.me = await api("POST", "/api/login", { username: user.value, password: pw.value });
      go(S.me.must_change ? "password" : (params.get("next") || "home"));
    } catch (e) { out.replaceChildren(msg("bad", e.message)); }
  }));
  return el("div", { class: "card narrow" }, el("h1", { text: t("login.title") }), form);
}

function pagePassword() {
  const old = el("input", { type: "password" }), neu = el("input", { type: "password" }), again = el("input", { type: "password" });
  const out = el("div"), btn = el("button", { type: "submit", text: t("password.save") });
  const form = el("form", {}, S.me.must_change ? msg("warn", t("password.must")) : null, field(t("password.old"), old), field(t("password.new"), neu),
    field(t("password.again"), again), el("p", { class: "muted", text: t("user.password_rule") }), btn, out);
  form.addEventListener("submit", busy(btn, async () => {
    if (neu.value !== again.value) return out.replaceChildren(msg("bad", t("password.differ")));
    try { await api("POST", "/api/password", { old: old.value, new: neu.value }); S.me = await api("GET", "/api/me"); out.replaceChildren(msg("good", t("saved"))); go("home"); }
    catch (e) { out.replaceChildren(msg("bad", e.message)); }
  }));
  return el("div", { class: "card narrow" }, el("h1", { text: t("password.title") }), form);
}

function pageHome() {
  const tiles = PAGES.filter(([id, , p]) => id !== "home" && (!p || can(p)))
    .map(([id, key]) => el("a", { class: "tile", href: "#/" + id }, el("strong", { text: t(key) }), el("span", { class: "muted", text: t(key + ".help") })));
  const c = S.info.company;
  return el("div", {}, el("h1", { text: t("home.hello", { name: S.me.display_name }) }),
    c && c.provisional ? msg("warn", t("company.provisional_help")) : null, el("div", { class: "grid" }, tiles),
    el("p", {}, el("a", { href: "#/password", text: t("password.title") })));
}

// ------------------------------------------------------------------ employees and organisation
const ENTITY = {
  employee: ["code", "preferred_name", "legal_name", "employment_status", "worker_type", "hire_date", "termination_date", "home_site_id", "position_id", "manager_id", "legacy_number"],
  org_unit: ["type", "code", "name", "parent_id"],
  job: ["code", "title", "family", "level", "critical"],
  position: ["code", "job_id", "org_unit_id", "reports_to_id", "status"],
};
const CHOICES = { employment_status: ["Active", "Leave", "Suspended", "Terminated"], type: ["site", "business_unit", "department", "section"] };

async function refs() {
  const [units, jobs, positions, employees] = await Promise.all(["org_unit", "job", "position", "employee"].map((e) => api("GET", "/api/" + e).catch(() => [])));
  const label = (r) => r.code + (r.name || r.title || r.preferred_name ? " — " + (r.name || r.title || r.preferred_name) : "");
  return {
    home_site_id: units.filter((u) => u.type === "site"), parent_id: units, org_unit_id: units.filter((u) => u.type !== "company"),
    job_id: jobs, position_id: positions, reports_to_id: positions, manager_id: employees, label,
    company: units.find((u) => u.type === "company"),
    byId: Object.fromEntries([...units, ...jobs, ...positions, ...employees].map((r) => [r.id, label(r)])),
  };
}

function editor(entity, row, R, done) {
  const inputs = {};
  const out = el("div"), btn = el("button", { type: "submit", text: t("save") });
  const fields = ENTITY[entity].map((f) => {
    let input;
    if (CHOICES[f] && !(entity === "org_unit" && row && f === "type")) input = el("select", {}, el("option", { value: "", text: "—" }), CHOICES[f].map((v) => el("option", { value: v, text: t("value." + v) })));
    else if (R[f]) input = el("select", {}, el("option", { value: "", text: "—" }), R[f].map((r) => el("option", { value: r.id, text: R.label(r) })));
    else if (f === "critical") input = el("select", {}, el("option", { value: "0", text: t("no") }), el("option", { value: "1", text: t("yes") }));
    else input = el("input", { type: f.endsWith("_date") ? "date" : "text", dir: f === "code" ? "ltr" : null });
    if (row && row[f] !== null && row[f] !== undefined) input.value = String(row[f]);
    if (row && (f === "code" || f === "type")) input.disabled = true;
    inputs[f] = input;
    return field(t("field." + f), input);
  });
  const form = el("form", { class: "card" }, el("h2", { text: row ? t("edit") + " " + row.code : t("new." + entity) }), el("div", { class: "row" }, fields), el("p"), btn, " ",
    el("button", { type: "button", class: "ghost", text: t("cancel"), onclick: () => done(false) }), out);
  form.addEventListener("submit", busy(btn, async () => {
    const values = {};
    for (const [f, input] of Object.entries(inputs)) if (f !== "code") values[f] = input.value === "" ? null : (f === "critical" ? Number(input.value) : input.value);
    if (entity === "org_unit" && row) values.type = row.type;
    if (entity === "org_unit" && values.type === "site" && !values.parent_id && R.company) values.parent_id = R.company.id;  // a site belongs to the company
    const code = inputs.code.value.trim();
    if (!code) return out.replaceChildren(msg("bad", t("field.code") + " ?"));
    try {
      await api("PUT", "/api/" + entity + "/" + encodeURIComponent(code), { fields: values, expected_ver: row ? row.ver : null });
      done(true);
    } catch (e) { out.replaceChildren(msg("bad", e.message)); }
  }));
  return form;
}

async function entityPage(entity, columns, writePerm) {
  const box = el("div");
  const draw = async (note) => {
    const [rows, R] = await Promise.all([api("GET", "/api/" + entity), refs()]);
    const edit = el("div");
    const open = (row) => edit.replaceChildren(editor(entity, row, R, async (saved) => { edit.replaceChildren(); if (saved) await draw(t("saved")); }));
    const table = el("table", {}, el("tr", {}, columns.map((c) => el("th", { text: t("field." + c) })), el("th")),
      rows.filter((r) => entity !== "org_unit" || r.type !== "company").map((r) => el("tr", {},
        columns.map((c) => el("td", { text: c.endsWith("_id") ? (R.byId[r[c]] || "") : (CHOICES[c] ? t("value." + r[c]) : (r[c] ?? "")) })),
        el("td", {}, can(writePerm) ? el("button", { class: "link", type: "button", text: t("edit"), onclick: () => open(r) }) : null, " ",
          can("hr.employees.delete") ? el("button", { class: "link", type: "button", text: t("delete"), onclick: async () => {
            if (!confirm(t("confirm.delete", { code: r.code }))) return;
            try { await api("DELETE", "/api/" + entity + "/" + encodeURIComponent(r.code) + "?ver=" + r.ver + (r.type ? "&type=" + r.type : "")); await draw(t("moved_to_bin")); }
            catch (e) { box.prepend(msg("bad", e.message)); }
          } }) : null))));
    box.replaceChildren(note ? msg("good", note) : "", can(writePerm) ? el("p", {}, el("button", { type: "button", text: t("new." + entity), onclick: () => open(null) })) : "",
      edit, rows.length ? table : el("p", { class: "muted", text: t("empty") }));
  };
  await draw();
  return box;
}

async function pageEmployees() {
  return el("div", {}, el("h1", { text: t("nav.employees") }),
    await entityPage("employee", ["code", "preferred_name", "employment_status", "position_id", "hire_date"], "hr.employees.write"), await recycleBin(["employee"]));
}

async function pageOrganisation(params) {
  const tab = params.get("tab") || "org_unit";
  const tabs = el("div", { class: "tabs" }, ["org_unit", "job", "position"].map((e) =>
    el("button", { type: "button", class: e === tab ? "on" : null, text: t("tab." + e), onclick: () => go("organisation", "tab=" + e) })));
  const cols = { org_unit: ["type", "code", "name", "parent_id"], job: ["code", "title", "family", "level"], position: ["code", "job_id", "org_unit_id", "status"] }[tab];
  return el("div", {}, el("h1", { text: t("nav.organisation") }), tabs, await entityPage(tab, cols, "hr.org.write"), await recycleBin(["org_unit", "job", "position"]));
}

async function recycleBin(entities) {
  if (!can("hr.recycle.restore")) return el("span");
  const bin = await api("GET", "/api/recycle");
  const rows = entities.flatMap((e) => (bin[e] || []).map((r) => [e, r]));
  if (!rows.length) return el("span");
  return el("div", { class: "card" }, el("h2", { text: t("recycle.title") }), el("table", {}, rows.map(([e, r]) => el("tr", {},
    el("td", { text: t("tab." + e) }), el("td", { text: r.code }), el("td", { text: r.name || r.title || r.preferred_name || "" }),
    el("td", {}, el("button", { class: "link", type: "button", text: t("restore"), onclick: async () => {
      await api("POST", "/api/" + e + "/" + encodeURIComponent(r.code) + "/restore", { type: r.type || null }); route();
    } }))))));
}

// ------------------------------------------------------------------ attendance (the migrated application)
async function pageAttendance() {
  const h = can("admin.system.read") ? await api("GET", "/api/admin/health").catch(() => null) : null;
  const excel = h && h.attendance ? h.attendance.excel_desktop : null;
  return el("div", {}, el("h1", { text: t("nav.attendance") }),
    excel === false ? msg("warn", t("attendance.no_excel")) : null,
    el("iframe", { class: "attendance", src: "/attendance", title: t("nav.attendance") }));
}

// ------------------------------------------------------------------ users and profiles
async function pageUsers() {
  const [users, profiles] = await Promise.all([api("GET", "/api/admin/users"), api("GET", "/api/admin/profiles")]);
  const out = el("div");
  const profileSelect = (value) => el("select", {}, profiles.map((p) => el("option", { value: p.code, text: t("profile." + p.code) !== "profile." + p.code ? t("profile." + p.code) : p.name, selected: p.code === value })));
  const list = el("table", {}, el("tr", {}, ["user.username", "user.display_name", "user.profile", "user.active", ""].map((k) => el("th", { text: k ? t(k) : "" }))),
    users.map((u) => {
      const prof = profileSelect(u.profile), active = el("input", { type: "checkbox" });
      active.checked = !!u.active;
      return el("tr", {}, el("td", { text: u.code }), el("td", { text: u.display_name }), el("td", {}, prof), el("td", {}, active),
        el("td", {}, el("button", { class: "link", type: "button", text: t("save"), onclick: async () => {
          try { await api("PATCH", "/api/admin/users/" + u.code, { fields: { profile: prof.value, active: active.checked ? 1 : 0 }, expected_ver: u.ver }); route(); }
          catch (e) { out.replaceChildren(msg("bad", e.message)); }
        } }), " ", el("button", { class: "link", type: "button", text: t("user.reset_password"), onclick: async () => {
          const pw = prompt(t("user.new_password_for", { user: u.code }));
          if (!pw) return;
          try { await api("POST", "/api/admin/users/" + u.code + "/password", { password: pw }); out.replaceChildren(msg("good", t("user.password_was_reset"))); }
          catch (e) { out.replaceChildren(msg("bad", e.message)); }
        } })));
    }));
  const nu = el("input", { dir: "ltr" }), nd = el("input"), np = el("input", { type: "password" }), nprof = profileSelect("viewer");
  const btn = el("button", { type: "submit", text: t("user.create") });
  const form = el("form", { class: "card" }, el("h2", { text: t("user.new") }), el("div", { class: "row" }, field(t("user.username"), nu), field(t("user.display_name"), nd),
    field(t("user.first_password"), np), field(t("user.profile"), nprof)), el("p", { class: "muted", text: t("user.password_rule") }), btn);
  form.addEventListener("submit", busy(btn, async () => {
    try { await api("POST", "/api/admin/users", { username: nu.value, display_name: nd.value, password: np.value, profile: nprof.value }); route(); }
    catch (e) { out.replaceChildren(msg("bad", e.message)); }
  }));
  const all = [...new Set(profiles.flatMap((p) => p.perms))].concat(PERMS).filter((v, i, a) => a.indexOf(v) === i).sort();
  const profileCards = profiles.map((p) => {
    const boxes = all.map((perm) => { const c = el("input", { type: "checkbox", value: perm }); c.checked = p.perms.includes(perm); c.disabled = p.code === "administrator"; return el("label", {}, c, t("perm." + perm)); });
    return el("div", { class: "card" }, el("h2", { text: (t("profile." + p.code) !== "profile." + p.code ? t("profile." + p.code) : p.name) }), el("div", { class: "perms" }, boxes),
      p.code === "administrator" ? el("p", { class: "muted", text: t("profile.admin_locked") }) : el("button", { type: "button", text: t("save"), onclick: async () => {
        const perms = boxes.map((b) => b.firstChild).filter((c) => c.checked).map((c) => c.value);
        try { await api("PUT", "/api/admin/profiles/" + p.code, { name: p.name, perms, expected_ver: p.ver }); route(); }
        catch (e) { out.replaceChildren(msg("bad", e.message)); }
      } }));
  });
  return el("div", {}, el("h1", { text: t("nav.users") }), out, list, form, el("h1", { text: t("profile.title") }), profileCards);
}
const PERMS = ["hr.org.read", "hr.org.write", "hr.employees.read", "hr.employees.write", "hr.employees.delete", "hr.recycle.restore", "hr.import.run",
  "hr.attendance.read", "hr.attendance.upload", "admin.users.manage", "admin.audit.read", "admin.backup.manage", "admin.backup.restore", "admin.system.read", "admin.settings.manage"];

// ------------------------------------------------------------------ backups, health, settings
async function pageBackups() {
  const list = await api("GET", "/api/admin/backups");
  const out = el("div");
  const act = (name, action) => async () => {
    if (action === "restore" && !confirm(t("backup.confirm_restore", { name }))) return;
    out.replaceChildren(msg("warn", t("working")));
    try {
      const r = await api("POST", "/api/admin/backups/" + name + "/" + action);
      out.replaceChildren(msg(r.ok === false ? "bad" : "good", action === "restore" ? t("backup.restored") : (r.ok ? t("backup.check_ok") : (r.problems || []).join("; "))));
    } catch (e) { out.replaceChildren(msg("bad", e.message)); }
  };
  const make = el("button", { type: "button", text: t("backup.create") });
  make.addEventListener("click", busy(make, async () => {
    out.replaceChildren(msg("warn", t("working")));
    try { const r = await api("POST", "/api/admin/backups"); out.replaceChildren(msg(r.rehearsal.ok ? "good" : "bad", r.rehearsal.ok ? t("backup.made", { name: r.name }) : r.rehearsal.problems.join("; "))); route(); }
    catch (e) { out.replaceChildren(msg("bad", e.message)); }
  }));
  return el("div", {}, el("h1", { text: t("nav.backups") }), el("p", { class: "muted", text: t("backup.help") }), make, out,
    el("table", {}, el("tr", {}, ["backup.name", "backup.when", "backup.reason", "backup.rehearsal", ""].map((k) => el("th", { text: k ? t(k) : "" }))),
      list.map((b) => el("tr", {}, el("td", { text: b.name + (b.kept_forever ? " ★" : "") }), el("td", { text: b.created_at }), el("td", { text: t("reason." + b.reason) }),
        el("td", {}, b.rehearsal ? el("span", { class: b.rehearsal.ok ? "ok" : "no", text: b.rehearsal.ok ? t("passed") : t("failed") }) : "—"),
        el("td", {}, ["verify", "rehearse"].map((a) => [el("button", { class: "link", type: "button", text: t("backup." + a), onclick: act(b.name, a) }), " "]),
          can("admin.backup.restore") ? el("button", { class: "link", type: "button", text: t("backup.restore"), onclick: act(b.name, "restore") }) : null)))));
}

async function pageHealth() {
  const h = await api("GET", "/api/admin/health");
  const yes = (v) => el("span", { class: v ? "ok" : "no", text: v ? t("ok") : t("problem") });
  const rec = h.recovery;
  return el("div", {}, el("h1", { text: t("nav.health") }), el("div", { class: "card" }, el("dl", {},
    el("dt", { text: t("health.version") }), el("dd", { text: h.product.version + " (" + t("health.data_version") + " " + h.product.data_version + ")" }),
    el("dt", { text: t("health.company") }), el("dd", { text: h.company.name + " (" + h.company.code + ") · " + t("company.source." + h.company.source) }),
    el("dt", { text: t("health.journal") }), el("dd", {}, yes(h.journal.ok), " ", t("health.lines", { n: h.journal.lines })),
    el("dt", { text: t("health.audit") }), el("dd", {}, yes(h.audit.ok)),
    el("dt", { text: t("health.signing") }), el("dd", { text: h.signing.backend }),
    el("dt", { text: t("health.last_backup") }), el("dd", { text: h.last_backup ? h.last_backup.created_at + " · " + (h.last_backup.rehearsal && h.last_backup.rehearsal.ok ? t("passed") : t("failed")) : t("none") }),
    el("dt", { text: t("health.attendance") }), el("dd", { text: h.attendance.history_file ? t("ok") : t("none") }),
    el("dt", { text: t("health.excel") }), el("dd", { text: h.attendance.excel_desktop === null ? t("not_applicable") : (h.attendance.excel_desktop ? t("found") : t("attendance.no_excel")) }),
    el("dt", { text: t("health.recovery") }), el("dd", { text: rec ? rec.version + " · " + (rec.intact ? t("ok") : t("problem")) : t("none") }),
    el("dt", { text: t("health.home") }), el("dd", { text: h.product.home, dir: "ltr" }))));
}

async function pageSettings() {
  const s = await api("GET", "/api/admin/settings");
  const auto = el("input", { type: "checkbox" }), lang = el("select", {}, el("option", { value: "en", text: "English" }), el("option", { value: "ar", text: "العربية" }));
  const hours = el("input", { type: "number", min: "1", max: "24" });
  auto.checked = s.autostart; lang.value = s.language; hours.value = s.backup_hours;
  const out = el("div"), btn = el("button", { type: "submit", text: t("save") });
  const form = el("form", { class: "card" }, el("label", {}, auto, " ", t("settings.autostart")), el("p", { class: "muted", text: t("settings.autostart_help") }),
    field(t("settings.language"), lang), field(t("settings.backup_hours"), hours), el("p"), btn, out);
  form.addEventListener("submit", busy(btn, async () => {
    try { await api("PUT", "/api/admin/settings", { autostart: auto.checked, language: lang.value, backup_hours: Number(hours.value) }); out.replaceChildren(msg("good", t("saved"))); }
    catch (e) { out.replaceChildren(msg("bad", e.message)); }
  }));
  return el("div", {}, el("h1", { text: t("nav.settings") }), form);
}

// ------------------------------------------------------------------ start
$("#logout").addEventListener("click", async () => { try { await api("POST", "/api/logout"); } catch (_) { } S.me = null; go("login"); });
$("#lang").addEventListener("change", async (e) => { localStorage.setItem("hr.lang", e.target.value); await loadLang(e.target.value); route(); });
window.addEventListener("hashchange", route);
route();
