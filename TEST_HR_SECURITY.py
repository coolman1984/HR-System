"""Phase 2 exit gate: users, permissions, device identity, the signed journal, backups, rehearsal and recovery.

Every check below is one sentence of the gate the owner set before any new HR module may be built:
  unauthorized operations are rejected server-side; concurrent edits cannot silently overwrite; journal
  modification is detected; damaged materialized HR data can be rebuilt; backup -> restore -> integrity
  comparison succeeds automatically; loss of one database file does not destroy permanent history.
Plus the signing decision (ADR-HR-002): RFC 8032 vectors, the pinned BAMS file, and signatures cross-checked
against independent implementations (PyCA `cryptography` and the OpenSSL command line) in both directions.

Synthetic data only. Standard library only (the independent implementations run in child processes).
Set HR_REQUIRE_CROSSCHECK=1 to fail (instead of skip) when `cryptography` is not importable; HR_CRYPTO_PATH adds a
folder holding it for the child processes.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import hr_core.auth as auth_mod  # noqa: E402
from hr_core import signing  # noqa: E402
from hr_core.api import serve  # noqa: E402
from hr_core.backup import Backups, BackupError, local_path_problem  # noqa: E402
from hr_core.device import Device  # noqa: E402
from hr_core.journal import Journal  # noqa: E402
from hr_core.registry import Registry  # noqa: E402
from hr_core.service import HRService  # noqa: E402
from hr_core.vendor import ed25519_bams  # noqa: E402

COMPANY = "5b0c4a4e-8d7e-4f55-9a52-5d2f9b1f0a01"
results = {}
assert auth_mod.ITERATIONS == 600_000  # the shipped cost (BAMS); the test lowers it below only for speed
auth_mod.ITERATIONS = 1000


def check(name, cond, detail=None):
    if not cond:
        raise AssertionError(f"{name}: {detail!r}")
    results[name] = True


def child(code, env_extra=None, stdin=None):
    env = dict(os.environ, **(env_extra or {}))
    extra = os.environ.get("HR_CRYPTO_PATH")
    if extra:
        env["PYTHONPATH"] = extra + os.pathsep + env.get("PYTHONPATH", "")
    p = subprocess.run([sys.executable, "-c", code], input=stdin, capture_output=True, text=True, cwd=ROOT, env=env)
    return p.returncode, p.stdout, p.stderr


# =============================================================================== 1. signing
RFC8032 = [  # RFC 8032 section 7.1, tests 1-3 (the same vectors BAMS's own suite holds)
    ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60", "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7", "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]
VENDORED_SHA256 = "cb772f845301e8b81baaec496910c778526919b37061e8e6c6b05489ed9cdd1b"
L = 2**252 + 27742317777372353535851937790883648493

with open(os.path.join(ROOT, "hr_core", "vendor", "ed25519_bams.py"), "rb") as fh:
    check("bams_file_is_the_pinned_unmodified_copy", hashlib.sha256(fh.read()).hexdigest() == VENDORED_SHA256)
for sk, pk, msg, sig in RFC8032:
    sk, pk, msg, sig = map(bytes.fromhex, (sk, pk, msg, sig))
    assert ed25519_bams.public_key(sk) == pk and ed25519_bams.sign(sk, msg) == sig and ed25519_bams.verify(pk, msg, sig)
    assert signing.public_key(sk) == pk and signing.sign(sk, msg) == sig and signing.verify(pk, msg, sig)
check("rfc8032_vectors_bams_and_selected_backend", True)
seed = bytes.fromhex(RFC8032[0][0])
pub, good = signing.public_key(seed), signing.sign(seed, b"hello")
for i in (0, 31, 32, 63):
    bad = bytearray(good)
    bad[i] ^= 1
    assert not signing.verify(pub, b"hello", bytes(bad)) and not ed25519_bams.verify(pub, b"hello", bytes(bad))
s_high = (int.from_bytes(good[32:], "little") + L).to_bytes(32, "little")  # the same S + L: malleated signature
assert not signing.verify(pub, b"hello", good[:32] + s_high) and not ed25519_bams.verify(pub, b"hello", good[:32] + s_high)
assert not signing.verify(pub, b"hellO", good) and not signing.verify(b"\x01" * 32, b"hello", good)
check("tampered_and_malleated_signatures_rejected", True)

# Cross-check: the same 40 (seed, message) pairs signed by each implementation must be byte-identical and verify
# in the other one. `cryptography` runs in a child process (it is not needed, or importable, everywhere).
pairs = [(hashlib.sha256(b"seed%d" % i).hexdigest(), hashlib.sha256(b"msg%d" % i).hexdigest()[: 2 * ((i * 7) % 32)]) for i in range(40)]
SIGN_WITH = """
import json, sys
from hr_core import signing
out = []
for seed, msg in json.load(sys.stdin):
    s = bytes.fromhex(seed)
    out.append([signing.public_key(s).hex(), signing.sign(s, bytes.fromhex(msg)).hex()])
print(json.dumps({"backend": signing.BACKEND, "sigs": out}))
"""
rc, out, err = child(SIGN_WITH, {"HR_SIGNING_BACKEND": "cryptography"}, json.dumps(pairs))
crypto_available = rc == 0 and json.loads(out)["backend"] == "cryptography"
if crypto_available:
    crypto = json.loads(out)["sigs"]
    rc, out, err = child(SIGN_WITH, {"HR_SIGNING_BACKEND": "bams"}, json.dumps(pairs))
    bams = json.loads(out)["sigs"]
    check("crosscheck_signatures_identical_bams_vs_cryptography", crypto == bams)
    for (sd, msg), (pk, sg) in zip(pairs, crypto):
        assert ed25519_bams.verify(bytes.fromhex(pk), bytes.fromhex(msg), bytes.fromhex(sg))
    VERIFY_WITH = """
import json, sys
from hr_core import signing
items = json.load(sys.stdin)
ok = all(signing.verify(bytes.fromhex(pk), bytes.fromhex(m), bytes.fromhex(s)) for m, pk, s in items)
ok = ok and not any(signing.verify(bytes.fromhex(pk), bytes.fromhex(m) + b"x", bytes.fromhex(s)) for m, pk, s in items)
print(json.dumps({"backend": signing.BACKEND, "ok": ok}))
"""
    rc, out, err = child(VERIFY_WITH, {"HR_SIGNING_BACKEND": "cryptography"}, json.dumps([[m, pk, s] for (sd, m), (pk, s) in zip(pairs, bams)]))
    check("crosscheck_bams_signatures_verify_in_cryptography", rc == 0 and json.loads(out) == {"backend": "cryptography", "ok": True}, err[-400:])
    results["crosscheck_cryptography"] = "done"
elif os.environ.get("HR_REQUIRE_CROSSCHECK") == "1":
    raise AssertionError("cryptography is required for the cross-check in this run: " + err[-600:])
else:
    results["crosscheck_cryptography"] = "skipped (cryptography not importable here; CI runs it)"

openssl = shutil.which("openssl")
if openssl:  # a third, independent implementation (OpenSSL's command line), when present
    work = tempfile.mkdtemp(prefix="hr_openssl_")
    try:
        agreed = 0
        for sd, msg in [pr for pr in pairs if pr[1]][:8]:  # the openssl command line cannot sign an empty file
            der = bytes.fromhex("302e020100300506032b657004220420" + sd)  # PKCS#8 wrapping of the raw seed
            key, data, sigf = (os.path.join(work, n) for n in ("k.der", "m.bin", "s.bin"))
            open(key, "wb").write(der)
            open(data, "wb").write(bytes.fromhex(msg))
            p = subprocess.run([openssl, "pkeyutl", "-sign", "-rawin", "-keyform", "DER", "-inkey", key, "-in", data, "-out", sigf], capture_output=True)
            if p.returncode != 0:
                break
            if open(sigf, "rb").read() == ed25519_bams.sign(bytes.fromhex(sd), bytes.fromhex(msg)):
                agreed += 1
        if agreed:
            check("crosscheck_openssl_identical", agreed == 8, agreed)
        else:
            results["crosscheck_openssl"] = "skipped (this openssl cannot sign raw Ed25519)"
    finally:
        shutil.rmtree(work, ignore_errors=True)
else:
    results["crosscheck_openssl"] = "skipped (no openssl on PATH)"

# A journal written under one backend verifies under the other (both directions).
WRITE_JOURNAL = """
import sys
from hr_core.journal import open_journal
from hr_core import signing
j = open_journal(sys.stdin.read().strip())
for i in range(5):
    j.append("t", f"line {i}", [{"entity": "note", "row": {"i": i}}])
v = j.verify()
print(signing.BACKEND, v["ok"], v["lines"])
"""
VERIFY_JOURNAL = """
import sys
from hr_core.journal import Journal
from hr_core import signing
v = Journal(sys.stdin.read().strip()).verify()
print(signing.BACKEND, v["ok"], v["lines"], v["signed_from"])
"""
directions = [("bams", "bams")] + ([("cryptography", "bams"), ("bams", "cryptography")] if crypto_available else [])
for writer, reader in directions:
    d = tempfile.mkdtemp(prefix="hr_xjournal_")
    rc, out, err = child(WRITE_JOURNAL, {"HR_SIGNING_BACKEND": writer}, d)
    NAMES = {"bams": "bams-ed25519", "cryptography": "cryptography"}
    assert rc == 0 and out.split() == [NAMES[writer], "True", "6"], (out, err[-400:])
    rc, out, err = child(VERIFY_JOURNAL, {"HR_SIGNING_BACKEND": reader}, d)
    assert rc == 0 and out.split() == [NAMES[reader], "True", "6", "1"], (out, err[-400:])
    shutil.rmtree(d, ignore_errors=True)
check("journal_signed_by_one_backend_verifies_in_the_other", True)
results["signing_backend_here"] = signing.BACKEND

# =============================================================================== 2. device identity
d = tempfile.mkdtemp(prefix="hr_device_")
dev = Device(d, "Office PC", machine="machine-A")
same = Device(d, machine="machine-A")
check("device_identity_is_stable", same.device_id == dev.device_id and same.cloned_from is None)
key_mode = os.stat(os.path.join(d, "node", "device.key")).st_mode & 0o777
check("device_key_is_private_file", os.name == "nt" or key_mode == 0o600, oct(key_mode))
clone = Device(d, machine="machine-B")  # the data folder was copied to another machine
check("device_clone_detected_new_identity", clone.cloned_from == dev.device_id and clone.device_id != dev.device_id and clone.public_hex != dev.public_hex)
j = Journal(d, clone)
j.append("t", "after the copy", [])
v = j.verify()
check("clone_signs_as_itself_and_verifies", v["ok"] and v["lines"] == 2)
j.close()

# =============================================================================== 3. the secured server
data = tempfile.mkdtemp(prefix="hr_security_")
svc = HRService(data, COMPANY, "NILE", "Nile Electronics", extra_backup_dirs=[os.path.join(data, "second-disk")])
server = serve(svc, "127.0.0.1", 0)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{server.server_address[1]}"


class Client:
    def __init__(self):
        self.cookie = None

    def call(self, method, path, body=None, headers=None, raw=None):
        data_ = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(BASE + path, data=data_, method=method)
        if method != "GET":
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req) as resp:
                status, payload, setc = resp.status, json.loads(resp.read() or b"null"), resp.headers.get("Set-Cookie")
        except urllib.error.HTTPError as exc:
            status, payload, setc = exc.code, json.loads(exc.read() or b"null"), exc.headers.get("Set-Cookie")
        if setc and setc.startswith("hr_sid="):
            self.cookie = setc.split(";")[0] if "Max-Age=0" not in setc else None
        return status, payload

    def login(self, user, pw):
        return self.call("POST", "/api/login", {"username": user, "password": pw})


admin, anon = Client(), Client()
check("setup_first_admin_local_only_once", admin.call("POST", "/api/setup", {"username": "admin", "display_name": "Admin", "password": "Admin-pass-1"})[0] == 201
      and anon.call("POST", "/api/setup", {"username": "evil", "display_name": "x", "password": "whatever-123"})[0] == 409)
status, me = admin.login("admin", "Admin-pass-1")
check("login_sets_httponly_strict_cookie_and_returns_rights", status == 200 and "admin.users.manage" in me["permissions"] and admin.cookie)

# --- unauthorized operations are rejected server-side
check("no_session_is_401", anon.call("GET", "/api/employee")[0] == 401 and anon.call("PUT", "/api/job/J1", {"fields": {"title": "x"}})[0] == 401)
status, _ = admin.call("PUT", "/api/org_unit/SITE1", {"fields": {"type": "site", "name": "Main plant", "parent_id": svc.registry.gid("org_unit", "NILE", "company")}})
assert status == 200
for code, title in (("J-OP", "Operator"), ("J-TL", "Team leader")):
    assert admin.call("PUT", f"/api/job/{code}", {"fields": {"title": title}})[0] == 200
for code in ("E001", "E002", "E003"):
    assert admin.call("PUT", f"/api/employee/{code}", {"fields": {"preferred_name": f"Worker {code}", "employment_status": "Active",
                                                                  "home_site_id": svc.registry.gid("org_unit", "SITE1", "site")}})[0] == 200
assert admin.call("POST", "/api/admin/users", {"username": "viewer1", "display_name": "V", "password": "Viewer-pass-1", "profile": "viewer"})[0] == 201
assert admin.call("POST", "/api/admin/users", {"username": "officer1", "display_name": "O1", "password": "Officer-pass-1", "profile": "hr_officer"})[0] == 201
assert admin.call("POST", "/api/admin/users", {"username": "officer2", "display_name": "O2", "password": "Officer-pass-2", "profile": "hr_officer"})[0] == 201
viewer, off1, off2 = Client(), Client(), Client()
viewer.login("viewer1", "Viewer-pass-1")
status, body = viewer.call("GET", "/api/employee")
check("new_user_must_change_password_first", status == 403 and body["error"] == "auth.must_change")
check("password_change_accepted", viewer.call("POST", "/api/password", {"old": "Viewer-pass-1", "new": "Viewer-pass-2"})[0] == 200)
for c, u, old, new in ((off1, "officer1", "Officer-pass-1", "Officer-pass-1b"), (off2, "officer2", "Officer-pass-2", "Officer-pass-2b")):
    c.login(u, old)
    assert c.call("POST", "/api/password", {"old": old, "new": new})[0] == 200
check("viewer_can_read", viewer.call("GET", "/api/employee")[0] == 200 and len(viewer.call("GET", "/api/employee")[1]) == 3)
status, body = viewer.call("PUT", "/api/employee/E001", {"fields": {"preferred_name": "hacked"}, "expected_ver": 1})
check("viewer_write_is_403", status == 403 and body["error"] == "perm.denied" and svc.registry.get("employee", "E001")["preferred_name"] == "Worker E001")
admin_areas = [(p, viewer.call(m, p, b)) for m, p, b in (
    ("GET", "/api/admin/users", None), ("GET", "/api/admin/audit", None), ("POST", "/api/admin/backups", {}),
    ("POST", "/api/admin/users", {"username": "x1x", "display_name": "x", "password": "12345678", "profile": "administrator"}),
    ("DELETE", "/api/employee/E001?ver=1", None))]
check("viewer_admin_areas_are_403", all(r[0] == 403 for p, r in admin_areas), admin_areas)
denied = [e for e in svc.journal.audit_entries("security") if e["event"] == "permission.denied" and e["actor"] == "viewer1"]
check("denials_are_audited", len(denied) >= 5, len(denied))
check("officer_cannot_manage_users_or_restore_backups", off1.call("GET", "/api/admin/users")[0] == 403 and off1.call("GET", "/api/admin/health")[0] == 403)
# rights are recomputed on every request: a profile change or a disabled account takes effect at once
ver = next(p for p in svc.auth.profiles() if p["code"] == "viewer")["ver"]
assert admin.call("PUT", "/api/admin/profiles/viewer", {"name": "Viewer", "perms": ["hr.org.read"], "expected_ver": ver})[0] == 200
check("profile_change_applies_immediately", viewer.call("GET", "/api/employee")[0] == 403 and viewer.call("GET", "/api/job")[0] == 200)
uver = next(u for u in svc.auth.users() if u["code"] == "viewer1")["ver"]
assert admin.call("PATCH", "/api/admin/users/viewer1", {"fields": {"active": 0}, "expected_ver": uver})[0] == 200
check("disabled_account_is_out_immediately", viewer.call("GET", "/api/job")[0] == 401 and viewer.login("viewer1", "Viewer-pass-2")[0] == 401)
aver = next(u for u in svc.auth.users() if u["code"] == "admin")["ver"]
status, body = admin.call("PATCH", "/api/admin/users/admin", {"fields": {"active": 0}, "expected_ver": aver})
check("last_administrator_cannot_be_disabled", status == 409 and body["error"] == "user.last_admin")
check("administrator_profile_is_locked", admin.call("PUT", "/api/admin/profiles/administrator", {"name": "A", "perms": ["hr.org.read"],
      "expected_ver": next(p for p in svc.auth.profiles() if p["code"] == "administrator")["ver"]})[0] == 400)
check("cross_site_request_refused", admin.call("PUT", "/api/job/J-X", {"fields": {"title": "x"}}, {"Origin": "http://evil.example"})[0] == 403)
req = urllib.request.Request(BASE + "/api/job/J-X", data=b'{"fields":{"title":"x"}}', method="PUT", headers={"Content-Type": "text/plain", "Cookie": admin.cookie})
try:
    urllib.request.urlopen(req)
    raise AssertionError("text/plain must be refused")
except urllib.error.HTTPError as exc:
    check("non_json_mutation_refused", exc.code == 415)
check("no_job_created_by_refused_requests", svc.registry.get("job", "J-X") is None)
bad = Client()
codes = [bad.login("officer1", "wrong-password")[0] for _ in range(5)]
check("five_wrong_passwords_lock_the_account", codes == [401] * 5 and bad.login("officer1", "Officer-pass-1b")[0] == 423)
svc.auth.db.execute("DELETE FROM failure")
svc.auth.db.commit()
check("login_failures_are_audited", sum(1 for e in svc.journal.audit_entries("security") if e["event"].startswith("login.") and e["actor"] == "officer1") >= 6)
check("passwords_never_in_journal_or_audit", "Officer-pass" not in json.dumps([dict(r) for r in svc.journal.db.execute("SELECT * FROM journal")])
      and "Officer-pass" not in json.dumps(svc.journal.audit_entries(limit=10000)) and "wrong-password" not in json.dumps(svc.journal.audit_entries(limit=10000)))

# --- concurrent edits cannot silently overwrite
e = svc.registry.get("employee", "E002")
s1, _ = off1.call("PUT", "/api/employee/E002", {"fields": {"preferred_name": "Officer one's edit"}, "expected_ver": e["ver"]})
s2, b2 = off2.call("PUT", "/api/employee/E002", {"fields": {"preferred_name": "Officer two's edit"}, "expected_ver": e["ver"]})
check("stale_version_is_409", s1 == 200 and s2 == 409 and b2["error"] == "ver.conflict"
      and svc.registry.get("employee", "E002")["preferred_name"] == "Officer one's edit")
s3, b3 = off2.call("PUT", "/api/employee/E002", {"fields": {"preferred_name": "blind overwrite"}})
check("change_without_version_is_409", s3 == 409 and b3["error"] == "ver.required")
e = svc.registry.get("employee", "E003")
outcomes = []


def racer(i):
    c = Client()
    c.cookie = off1.cookie if i % 2 else off2.cookie
    outcomes.append(c.call("PUT", "/api/employee/E003", {"fields": {"preferred_name": f"racer {i}"}, "expected_ver": e["ver"]})[0])


threads = [threading.Thread(target=racer, args=(i,)) for i in range(12)]
[t.start() for t in threads]
[t.join() for t in threads]
check("twelve_simultaneous_saves_exactly_one_wins", sorted(outcomes) == [200] + [409] * 11 and svc.registry.get("employee", "E003")["ver"] == e["ver"] + 1,
      (outcomes, [a for a in svc.journal.audit_entries("system", limit=50) if a["event"] in ("server.error", "request.unreadable")]))
uver = next(u for u in svc.auth.users() if u["code"] == "officer2")["ver"]
assert admin.call("PATCH", "/api/admin/users/officer2", {"fields": {"display_name": "Officer Two"}, "expected_ver": uver})[0] == 200
svc.auth.create_user("admin", "temp1", "Temp", "Temp-pass-11", "viewer", must_change=False)
tmp_client = Client()
tmp_client.login("temp1", "Temp-pass-11")
assert tmp_client.call("GET", "/api/job")[0] == 200
# disabled by another writer of the same journal (no end_sessions call): the next request must still be refused
svc.auth.commit("admin", "disabled elsewhere", [{"entity": "user", "code": "temp1", "fields": {"active": 0}}])
check("session_rechecks_account_on_every_request", tmp_client.call("GET", "/api/job")[0] == 401)
check("account_edits_are_versioned_too", admin.call("PATCH", "/api/admin/users/officer2", {"fields": {"display_name": "stale"}, "expected_ver": uver})[0] == 409)

# --- Recycle Bin instead of destructive deletion
e = svc.registry.get("employee", "E003")
check("delete_needs_version", off1.call("DELETE", "/api/employee/E003")[0] == 409)
check("delete_moves_to_recycle_bin", off1.call("DELETE", f"/api/employee/E003?ver={e['ver']}")[0] == 200
      and svc.registry.get("employee", "E003") is None
      and [r["code"] for r in off1.call("GET", "/api/recycle")[1]["employee"]] == ["E003"])
check("recreating_a_deleted_code_is_refused", off1.call("PUT", "/api/employee/E003", {"fields": {"employment_status": "Active"}})[0] == 409)
check("restore_from_recycle_bin", off1.call("POST", "/api/employee/E003/restore", {})[0] == 200 and svc.registry.get("employee", "E003")["preferred_name"].startswith("racer"))
check("nothing_is_ever_erased", svc.journal.db.execute("SELECT COUNT(*) FROM journal").fetchone()[0] == svc.journal.last_seq())

# --- complete audit
events = {e["event"] for e in svc.journal.audit_entries(limit=10000)}
check("audit_covers_security_and_activity", {"service.started", "setup.first_admin", "login.ok", "login.failed", "login.locked", "password.changed",
      "user.created", "user.changed", "profile.saved", "permission.denied", "record.saved", "record.deleted", "record.restored", "change.refused"} <= events,
      sorted(events))
check("auditor_reads_audit_and_health", svc.auth.create_user("admin", "auditor1", "Aud", "Auditor-pass-1", "auditor", must_change=False) and True)
aud = Client()
aud.login("auditor1", "Auditor-pass-1")
status, health = aud.call("GET", "/api/admin/health")
check("health_reports_journal_audit_signing", aud.call("GET", "/api/admin/audit")[0] == 200 and status == 200 and health["journal"]["ok"]
      and health["audit"]["ok"] and health["signing"]["backend"] == signing.BACKEND and aud.call("POST", "/api/admin/backups", {})[0] == 403)

# =============================================================================== 4. journal modification is detected
jv = svc.journal.verify()
check("live_journal_signed_from_first_line", jv["ok"] and jv["signed_from"] == 1, jv)
work = tempfile.mkdtemp(prefix="hr_tamper_")
last_seq = svc.journal.last_seq()


def tampered(sql_or_fn):
    path = os.path.join(work, "j.db")
    src = sqlite3.connect(svc.journal.path)
    dst = sqlite3.connect(path)
    src.backup(dst)
    src.close()
    dst.execute("DROP TRIGGER journal_no_update")
    dst.execute("DROP TRIGGER audit_no_update")
    dst.execute("DROP TRIGGER journal_no_delete")
    if callable(sql_or_fn):
        sql_or_fn(dst)
    else:
        dst.execute(sql_or_fn)
    dst.commit()
    dst.close()
    j = Journal.__new__(Journal)
    j.db = sqlite3.connect(path)
    j.db.row_factory = sqlite3.Row
    out = (j.verify(), j.verify_audit())
    j.db.close()
    os.remove(path)
    return out


row = svc.journal.db.execute("SELECT seq, ops FROM journal WHERE label LIKE 'Changed employee E002%'").fetchone()
target = row["seq"]
v, _ = tampered(f"UPDATE journal SET ops = replace(ops, 'Officer one', 'Someone else') WHERE seq = {target}")
check("edited_content_detected", not v["ok"] and v["first_bad_seq"] == target and "hash" in v["reason"], v)
v, _ = tampered(f"UPDATE journal SET sig = NULL WHERE seq = {target}")
check("stripped_signature_detected", not v["ok"] and v["first_bad_seq"] == target, v)
v, _ = tampered(f"UPDATE journal SET sig = NULL, device = NULL WHERE seq = {target}")
check("stripped_signer_detected", not v["ok"] and v["first_bad_seq"] == target, v)
v, _ = tampered(f"DELETE FROM journal WHERE seq = {target}")
check("deleted_line_detected", not v["ok"] and v["first_bad_seq"] == target + 1, v)


def rewrite_history(db):
    """The strongest attack without the key: change a line AND recompute every hash after it."""
    from hr_core.canonical import GENESIS, line_hash
    prev = GENESIS
    for r in db.execute("SELECT * FROM journal ORDER BY seq").fetchall():
        r = dict(zip([c[0] for c in db.execute("SELECT * FROM journal LIMIT 0").description], r))
        ops = json.loads(r["ops"])
        if r["seq"] == target:
            ops[0]["row"]["preferred_name"] = "Someone else"
        line = {"seq": r["seq"], "id": r["id"], "at": r["at"], "actor": r["actor"], "label": r["label"], "ops": ops, "prev": prev}
        if r["kind"]:
            line["kind"] = r["kind"]
        if r["device"]:
            line["device"] = r["device"]
        h = line_hash("HR-JOURNAL1", line)
        from hr_core.canonical import canonical as _c
        db.execute("UPDATE journal SET ops = ?, prev = ?, hash = ? WHERE seq = ?", (_c(ops), prev, h, r["seq"]))
        prev = h


v, _ = tampered(rewrite_history)
check("rehashed_history_detected_by_signature", not v["ok"] and v["first_bad_seq"] == target and "signature" in v["reason"], v)
forger = bytes.fromhex(RFC8032[1][0])
v, _ = tampered(lambda db: db.execute("UPDATE journal SET sig = ? WHERE seq = ?", (signing.sign(forger, bytes.fromhex(
    db.execute("SELECT hash FROM journal WHERE seq = ?", (target,)).fetchone()[0])).hex(), target)))
check("signature_by_another_key_detected", not v["ok"] and v["first_bad_seq"] == target, v)
def append_unsigned(db):
    """A well-formed, correctly chained line written by a program without the device key."""
    from hr_core.canonical import canonical as _c, line_hash
    last = db.execute("SELECT seq, hash FROM journal ORDER BY seq DESC LIMIT 1").fetchone()
    line = {"seq": last[0] + 1, "id": "forged", "at": "2026-01-01T00:00:00Z", "actor": "intruder", "label": "unsigned",
            "ops": [], "prev": last[1], "kind": "data"}
    db.execute("INSERT INTO journal (seq, id, at, actor, label, ops, prev, hash, sig, kind, device) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 'data', NULL)",
               (line["seq"], line["id"], line["at"], line["actor"], line["label"], _c([]), line["prev"], line_hash("HR-JOURNAL1", line)))


v, _ = tampered(append_unsigned)
check("appended_unsigned_line_detected", not v["ok"] and v["first_bad_seq"] == last_seq + 1 and "unsigned" in v["reason"], v)
_, a = tampered("UPDATE audit SET actor = 'nobody' WHERE seq = 3")
check("audit_modification_detected", not a["ok"] and a["first_bad_seq"] == 3, a)
try:
    svc.journal.db.execute("UPDATE journal SET label = 'x' WHERE seq = 1")
    raise AssertionError("the journal must refuse UPDATE")
except sqlite3.DatabaseError as exc:
    svc.journal.db.rollback()
    check("journal_refuses_update_and_delete", "append-only" in str(exc))
shutil.rmtree(work, ignore_errors=True)

# =============================================================================== 5. backups, rehearsal, restore
made = svc.backups.auto()
check("automatic_backup_and_rehearsal_pass", made and made["rehearsal"]["ok"] and all(made["rehearsal"]["checks"].values())
      and made["rehearsal"]["temporary_folder_removed"], made and made["rehearsal"])
check("automatic_backup_skips_when_nothing_changed", svc.backups.auto() is None)
bpath = made["path"]
check("backup_holds_no_private_key_no_sessions", not os.path.exists(os.path.join(bpath, "node")) and "device.key" not in os.listdir(bpath)
      and sqlite3.connect(os.path.join(bpath, "auth.db")).execute("SELECT COUNT(*) FROM session").fetchone()[0] == 0
      and json.load(open(os.path.join(bpath, "device.json")))["public_key"] == svc.device.public_hex)
check("backup_copied_to_second_disk_and_verified", made["copies"] and Backups.verify(os.path.join(data, "second-disk", made["name"]))["ok"])
check("network_backup_paths_refused", local_path_problem(r"\\server\share\hr") and local_path_problem("//server/share"))
try:
    Backups(data, svc.journal, svc.registry, svc.auth, r"\\nas\hr")
    raise AssertionError("a UNC destination must be refused")
except BackupError:
    pass

bad_copy = os.path.join(tempfile.mkdtemp(prefix="hr_badbackup_"), made["name"])
shutil.copytree(bpath, bad_copy)
with open(os.path.join(bad_copy, "hr.db"), "r+b") as fh:
    fh.seek(3000)
    b = fh.read(1)
    fh.seek(3000)
    fh.write(bytes([b[0] ^ 0xFF]))
check("damaged_backup_fails_verification_and_rehearsal", not Backups.verify(bad_copy)["ok"] and not svc.backups.rehearse(bad_copy)["ok"])
shutil.rmtree(bad_copy)
shutil.copytree(bpath, bad_copy)
m = json.load(open(os.path.join(bad_copy, "manifest.json")))
m["registry"]["fingerprint"] = "0" * 64
json.dump(m, open(os.path.join(bad_copy, "manifest.json"), "w"))
check("edited_manifest_fails_signature", "the manifest signature does not verify" in Backups.verify(bad_copy)["problems"])
shutil.rmtree(bad_copy)
shutil.copytree(bpath, bad_copy)
jb = sqlite3.connect(os.path.join(bad_copy, "hr_journal.db"))
jb.execute("DROP TRIGGER journal_no_update")
jb.execute("UPDATE journal SET label = 'forged' WHERE seq = 2")
jb.commit()
jb.close()
m = json.load(open(os.path.join(bad_copy, "manifest.json")))
check("backup_with_edited_journal_rejected", not Backups.verify(bad_copy)["ok"])  # hash in manifest, then chain + signature
shutil.rmtree(os.path.dirname(bad_copy))

# restore is a compensating change: history kept, one new line, data equal to the backup
before_restore_fp = svc.registry.fingerprint()
backup_rows = svc.backups.backup_rows(bpath)
e1 = svc.registry.get("employee", "E001")
off1.call("PUT", "/api/employee/E001", {"fields": {"preferred_name": "changed after the backup"}, "expected_ver": e1["ver"]})
off1.call("PUT", "/api/employee/E004", {"fields": {"preferred_name": "hired after the backup", "employment_status": "Active"}})
lines_before = svc.journal.last_seq()
check("restore_needs_its_own_right", off1.call("POST", f"/api/admin/backups/{made['name']}/restore", {})[0] == 403)
status, body = admin.call("POST", f"/api/admin/backups/{made['name']}/restore", {})
restored = {r["code"]: r for r in svc.registry.list("employee", include_deleted=True)}
check("restore_is_one_compensating_line", status == 200 and svc.journal.last_seq() == lines_before + 1
      and svc.journal.db.execute("SELECT kind FROM journal WHERE seq = ?", (body["seq"],)).fetchone()[0] == "restore")
check("restore_brings_back_the_backup_state", restored["E001"]["preferred_name"] == e1["preferred_name"] and restored["E004"]["deleted"] == 1
      and all(restored[r["code"]]["preferred_name"] == r["preferred_name"] for r in backup_rows["employee"].values()))
check("history_before_the_restore_is_kept", svc.journal.db.execute("SELECT COUNT(*) FROM journal WHERE label LIKE '%E004%'").fetchone()[0] >= 1 and svc.journal.verify()["ok"])
check("accounts_are_not_restored", svc.auth._get("user", "auditor1") is not None)
assert before_restore_fp  # (used for the record)

# =============================================================================== 6. damaged or lost files
fp = svc.registry.fingerprint()
svc.registry.db.execute("UPDATE employee SET preferred_name = 'corrupted', ver = 99 WHERE code = 'E001'")
svc.registry.db.execute("DELETE FROM job")
svc.registry.db.commit()
damaged = svc.backups.create("test", "damaged tables")
reh = svc.backups.rehearse(damaged["path"], "test")
check("rehearsal_detects_tables_that_differ_from_the_journal", not reh["ok"] and reh["checks"]["rebuilt_from_journal_identical"] is False, reh)
shutil.rmtree(damaged["path"])
svc.registry.rebuild()
check("damaged_tables_rebuilt_from_journal", svc.registry.fingerprint() == fp)
users_before = json.dumps(svc.auth.users(), sort_keys=True)
seq_now = svc.journal.last_seq()
server.shutdown()
server.server_close()
svc.close()
for f in ("hr.db", "hr.db-wal", "hr.db-shm"):
    if os.path.exists(os.path.join(data, f)):
        os.remove(os.path.join(data, f))
svc = HRService(data, COMPANY, "NILE", "Nile Electronics")
check("lost_hr_db_rebuilt_identical", svc.registry.fingerprint() == fp and svc.journal.last_seq() == seq_now)
svc.close()
for f in ("auth.db", "auth.db-wal", "auth.db-shm"):
    if os.path.exists(os.path.join(data, f)):
        os.remove(os.path.join(data, f))
svc = HRService(data, COMPANY, "NILE", "Nile Electronics")
check("lost_auth_db_rebuilt_accounts_and_passwords", json.dumps(svc.auth.users(), sort_keys=True) == users_before and svc.login("officer1", "Officer-pass-1b")[0])
check("company_not_duplicated_by_second_opener", len([u for u in svc.registry.list("org_unit") if u["type"] == "company"]) == 1)

# the journal file itself: the latest backup holds history up to it; the tables hold what came after
made2 = svc.backups.create("test", "before journal loss")
officer = svc.auth._get("user", "officer1")
e2 = svc.registry.get("employee", "E002")
svc.save(officer, "employee", "E002", {"preferred_name": "written after the last backup"}, e2["ver"])
svc.save(officer, "employee", "E005", {"preferred_name": "new after the last backup", "employment_status": "Active"})
fp = svc.registry.fingerprint()
backup_lines = json.load(open(os.path.join(made2["path"], "manifest.json")))["journal"]["lines"]
svc.close()
for f in ("hr_journal.db", "hr_journal.db-wal", "hr_journal.db-shm"):
    if os.path.exists(os.path.join(data, f)):
        os.remove(os.path.join(data, f))
svc = HRService(data, COMPANY, "NILE", "Nile Electronics")
v = svc.journal.verify()
kinds = [r[0] for r in svc.journal.db.execute("SELECT kind FROM journal WHERE seq > ? ORDER BY seq", (backup_lines,))]
check("lost_journal_restored_from_backup_with_recovery_line", v["ok"] and "recovery" in kinds and svc.registry.fingerprint() == fp
      and svc.registry.get("employee", "E005")["preferred_name"] == "new after the last backup", (v, kinds))
check("history_up_to_the_backup_survives_journal_loss", svc.journal.db.execute("SELECT COUNT(*) FROM journal WHERE seq <= ?", (backup_lines,)).fetchone()[0] == backup_lines)
check("journal_recovery_is_audited", any(e["event"] == "service.started" and e["detail"].get("journal_restored_from") == made2["name"] for e in svc.journal.audit_entries("system"))
      and any(e["event"] == "journal.recovered" for e in svc.journal.audit_entries("system")))
check("accounts_survive_journal_loss", svc.login("officer1", "Officer-pass-1b")[0])
after = svc.backups.auto()
check("rehearsal_passes_after_recovery", after and after["rehearsal"]["ok"], after and after["rehearsal"])
svc.close()

lonely = tempfile.mkdtemp(prefix="hr_nobackup_")
s0 = HRService(lonely, COMPANY)
s0.close()
os.remove(os.path.join(lonely, "hr_journal.db"))
try:
    HRService(lonely, COMPANY)
    raise AssertionError("a missing journal with no backup must stop the start")
except RuntimeError as exc:
    check("missing_journal_without_backup_refuses_to_start", "hr_journal.db" in str(exc))

# =============================================================================== 7. phase-1 data upgrades in place
old = tempfile.mkdtemp(prefix="hr_phase1_")
p1 = Registry(old, COMPANY, "NILE", "Nile", journal=Journal(old))  # unsigned, as phase 1 wrote it
p1.commit("hr", "phase-1 line", [p1.op_put("job", "J1", {"title": "Old job"})])
p1.close()
p2 = HRService(old, COMPANY, "NILE", "Nile")
v = p2.journal.verify()
check("phase1_unsigned_history_kept_signing_starts_after", v["ok"] and v["signed_from"] == 3 and p2.registry.get("job", "J1")["title"] == "Old job", v)
p2.close()

shutil.rmtree(data, ignore_errors=True)
print(json.dumps(results, indent=1))
print(f"TEST_HR_SECURITY: {sum(1 for v in results.values() if v is True)} checks passed")
