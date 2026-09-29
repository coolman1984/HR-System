"""Users, profiles, permissions and sessions (phase 2) — the BAMS model, re-implemented for HR.

* Accounts and profiles are DURABLE: every change is an `admin` line in the signed journal and data/auth.db is a
  fold of it (so auth.db can be lost and rebuilt). Sessions, failed-login counters and lockouts are LOCAL only.
* Passwords: salted PBKDF2-HMAC-SHA256, 600 000 rounds (as BAMS); only the hash is stored anywhere.
* Permissions are `module.object.action` keys (the ecosystem format, as in Mizan), checked on the SERVER for every
  request and recomputed each time, so a change or a disabled account takes effect immediately.
* Profiles fill the permissions in one step; `administrator` is locked to every right; the last active
  administrator can never be disabled, deleted or reduced.
* 5 wrong passwords lock an account for 15 minutes; sessions end after 30 minutes idle or 12 hours.
Standard library only.
"""

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from datetime import datetime, timedelta, timezone

from .canonical import canonical
from .journal import SharedConnection, now

PERMISSIONS = {
    "hr.org.read": "See the organisation, jobs and positions",
    "hr.org.write": "Create and change org units, jobs and positions",
    "hr.employees.read": "See employees",
    "hr.employees.write": "Create and change employees",
    "hr.employees.delete": "Move employees and org records to the Recycle Bin",
    "hr.recycle.restore": "Restore records from the Recycle Bin",
    "hr.import.run": "Import the organisation and employee workbooks",
    "admin.users.manage": "Manage users, profiles and permissions",
    "admin.audit.read": "Read the security and activity audit",
    "admin.backup.manage": "Create, verify and rehearse backups",
    "admin.backup.restore": "Restore data from a backup (a compensating change)",
    "admin.system.read": "See system health, journal verification and devices",
    "hr.attendance.read": "See attendance, its history and exports",
    "hr.attendance.upload": "Upload attendance files and roll an upload back",
    "admin.settings.manage": "Change this installation's settings (start with Windows, language)",
    "hr.shifts.read": "See shifts, calendars, assignments and the planned schedule",
    "hr.shifts.write": "Plan shifts: define them, assign people, change or swap a day",
    "hr.skills.read": "See skills and who is qualified",
    "hr.skills.write": "Define skills and record qualifications",
    "hr.discipline.read": "See the penalty schedule, violations and decisions",
    "hr.discipline.write": "Keep the penalty schedule, propose violations from attendance or enter them",
    "hr.discipline.approve": "Decide violations: approve the penalty or waive it (final)",
}
# Rights added after data version 0: hr_core/upgrade.py gives them to the built-in profiles of older installations.
ADDED_IN_DATA_VERSION_1 = {"administrator": ["hr.attendance.read", "hr.attendance.upload", "admin.settings.manage"],
                           "hr_officer": ["hr.attendance.read", "hr.attendance.upload"], "viewer": ["hr.attendance.read"]}
ADDED_IN_DATA_VERSION_2 = {"administrator": ["hr.shifts.read", "hr.shifts.write", "hr.skills.read", "hr.skills.write"],
                           "hr_officer": ["hr.shifts.read", "hr.shifts.write", "hr.skills.read", "hr.skills.write"],
                           "viewer": ["hr.shifts.read", "hr.skills.read"], "auditor": ["hr.shifts.read", "hr.skills.read"]}
ADDED_IN_DATA_VERSION_3 = {"administrator": ["hr.discipline.read", "hr.discipline.write", "hr.discipline.approve"],
                           "hr_officer": ["hr.discipline.read", "hr.discipline.write"], "auditor": ["hr.discipline.read"]}
ADMIN_PERMS = {p for p in PERMISSIONS if p.startswith("admin.")}
BUILTIN_PROFILES = {
    "administrator": ("Administrator", sorted(PERMISSIONS)),
    "hr_officer": ("HR officer", ["hr.org.read", "hr.org.write", "hr.employees.read", "hr.employees.write", "hr.employees.delete", "hr.recycle.restore", "hr.import.run",
                                 "hr.attendance.read", "hr.attendance.upload", "hr.shifts.read", "hr.shifts.write", "hr.skills.read", "hr.skills.write",
                                 "hr.discipline.read", "hr.discipline.write"]),
    "viewer": ("Viewer", ["hr.org.read", "hr.employees.read", "hr.attendance.read", "hr.shifts.read", "hr.skills.read"]),
    "auditor": ("Auditor", ["hr.org.read", "hr.employees.read", "admin.audit.read", "admin.system.read", "hr.shifts.read", "hr.skills.read",
                         "hr.discipline.read"]),
}
ITERATIONS = 600_000
MIN_PASSWORD = 8
MAX_FAILED, LOCK_MINUTES, IDLE_MINUTES, MAX_HOURS = 5, 15, 30, 12
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")
FIELDS = {"user": ["display_name", "pw", "profile", "extra_perms", "active", "must_change"], "profile": ["name", "perms", "builtin"]}


class AuthError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def hash_password(password, salt=None, iterations=None):
    salt, iterations = salt or secrets.token_hex(16), iterations or ITERATIONS
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations).hex()
    return {"alg": "pbkdf2-sha256", "iter": iterations, "salt": salt, "hash": digest}


def check_password(password, pw):
    if not pw:
        return False
    probe = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(pw["salt"]), int(pw["iter"])).hex()
    return hmac.compare_digest(probe, pw["hash"])


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class Auth:
    def __init__(self, data_dir, journal):
        self.journal = journal
        self.lock = threading.RLock()
        self.path = os.path.join(data_dir, "auth.db")
        self.db = SharedConnection(self.path, self.lock)
        self.db.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS user (id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, display_name, pw, profile, extra_perms, active, must_change,
              ver INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, deleted_at, deleted_by, created_at, created_by, updated_at, updated_by);
            CREATE TABLE IF NOT EXISTS profile (id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE, name, perms, builtin,
              ver INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, deleted_at, deleted_by, created_at, created_by, updated_at, updated_by);
            CREATE TABLE IF NOT EXISTS session (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, ip TEXT, created_at TEXT NOT NULL, last_seen TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS failure (username TEXT PRIMARY KEY, count INTEGER NOT NULL, locked_until TEXT);
        """)
        self.recover()
        missing = [code for code in BUILTIN_PROFILES if not self._get("profile", code)]
        if missing:
            self.commit("system", "Built-in profiles", [{"entity": "profile", "code": c, "fields": {"name": BUILTIN_PROFILES[c][0], "perms": BUILTIN_PROFILES[c][1], "builtin": 1}} for c in missing])

    # ------------------------------------------------------------------ durable state (journal fold)
    def _get(self, entity, code):
        row = self.db.execute(f"SELECT * FROM {entity} WHERE code = ?", (code,)).fetchone()
        return self._decode(row)

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        out = dict(row)
        for k in ("pw", "extra_perms", "perms"):
            if k in out and isinstance(out[k], str):
                out[k] = json.loads(out[k])
        return out

    def _write(self, entity, row):
        cols = ["id", "code"] + FIELDS[entity] + ["ver", "deleted", "deleted_at", "deleted_by", "created_at", "created_by", "updated_at", "updated_by"]
        values = [json.dumps(row.get(c), sort_keys=True) if c in ("pw", "extra_perms", "perms") else row.get(c) for c in cols]
        self.db.execute(f"INSERT OR REPLACE INTO {entity} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", values)

    def applied_seq(self):
        row = self.db.execute("SELECT value FROM meta WHERE key = 'applied_seq'").fetchone()
        return int(row[0]) if row else 0

    def applied_hash(self):
        row = self.db.execute("SELECT value FROM meta WHERE key = 'applied_hash'").fetchone()
        return row[0] if row else None

    def _fold(self, seq, results):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                for r in results:
                    self._write(r["entity"], r["row"])
                self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('applied_seq', ?)", (str(seq),))
                self.db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('applied_hash', ?)", (self.journal.hash_at(seq),))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def _rows(self):
        return {e: {r["id"]: self._decode(r) for r in self.db.execute(f"SELECT * FROM {e}")} for e in FIELDS}

    def recover(self):
        """Fold account lines auth.db has not seen; if auth.db is ahead of a journal restored from a backup,
        record the difference as one new `admin-recovery` line (never rewrite the journal)."""
        with self.lock:
            done, last = self.applied_seq(), self.journal.last_seq()
            if not self.journal.follows(done, self.applied_hash()):
                target = self._rows()
                self.db.executescript("BEGIN; DELETE FROM user; DELETE FROM profile; DELETE FROM meta; COMMIT;")
                self._fold_lines(0)
                current = self._rows()
                missing = [{"entity": e, "row": row} for e in FIELDS for gid, row in target[e].items() if canonical(current[e].get(gid)) != canonical(row)]
                if missing:
                    seq = self.journal.append("system", f"Account recovery: {len(missing)} record(s) re-recorded", missing, kind="admin-recovery")
                    self._fold(seq, missing)
                return
            self._fold_lines(done)

    def _fold_lines(self, after):
        for seq, kind, ops in self.journal.lines_after(after):
            self._fold(seq, [o for o in ops if o.get("entity") in FIELDS])

    def rebuild(self):
        with self.lock:
            self.db.executescript("BEGIN; DELETE FROM user; DELETE FROM profile; DELETE FROM meta; COMMIT;")
            self._fold_lines(0)

    def commit(self, actor, label, ops):
        """ops: {"entity": "user"|"profile", "code", "fields", "expected_ver"?, "delete"?}. One signed journal line."""
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                results = [r for r in (self._plan(op, actor) for op in ops) if r]
                self._check_admin_remains()
            finally:
                self.db.execute("ROLLBACK")
            if not results:
                return None
            seq = self.journal.append(actor, label, results, kind="admin")
            self._fold(seq, results)
            return seq

    def _plan(self, op, actor):
        entity, code, ts = op["entity"], op["code"], now()
        cur = self._get(entity, code)
        if op.get("expected_ver") is not None and (not cur or cur["ver"] != op["expected_ver"]):
            raise AuthError("ver.conflict", f"{entity} {code} was changed meanwhile; reload and try again", 409)
        if op.get("delete"):
            if not cur or cur["deleted"]:
                return None
            if entity == "profile" and cur["builtin"]:
                raise AuthError("profile.builtin", "built-in profiles cannot be deleted")
            full = {**cur, "ver": cur["ver"] + 1, "deleted": 1, "deleted_at": ts, "deleted_by": actor, "updated_at": ts, "updated_by": actor}
        else:
            if cur and cur["deleted"]:
                raise AuthError(f"{entity}.deleted", f"{entity} {code} was deleted; names are never reused")
            row = {f: op["fields"][f] if f in op["fields"] else (cur.get(f) if cur else None) for f in FIELDS[entity]}
            if entity == "user":
                if not USERNAME.match(code):
                    raise AuthError("user.name", "user names are 3-50 lower-case letters, digits, dot, dash or underscore")
                prof = self._get("profile", row["profile"]) if row["profile"] else None
                if not prof or prof["deleted"]:
                    raise AuthError("user.profile", f"profile {row['profile']} does not exist")
                row["extra_perms"] = sorted(set(row["extra_perms"] or []))
                unknown = [p for p in row["extra_perms"] if p not in PERMISSIONS]
                if unknown:
                    raise AuthError("perm.unknown", f"unknown permission {unknown[0]}")
                row["active"], row["must_change"] = int(bool(row["active"] if row["active"] is not None else 1)), int(bool(row["must_change"]))
                if not row["pw"]:
                    raise AuthError("user.password", "a password is required")
            else:
                if cur and cur["builtin"] and code == "administrator" and sorted(row["perms"] or []) != sorted(PERMISSIONS):
                    raise AuthError("profile.locked", "the administrator profile always holds every right")
                row["perms"] = sorted(set(row["perms"] or []))
                unknown = [p for p in row["perms"] if p not in PERMISSIONS]
                if unknown:
                    raise AuthError("perm.unknown", f"unknown permission {unknown[0]}")
                row["builtin"] = int(bool(row["builtin"]))
            if cur and all(canonical(row[f]) == canonical(cur.get(f)) for f in FIELDS[entity]):
                return None
            import uuid as _uuid
            full = {**row, "code": code, "id": cur["id"] if cur else str(_uuid.uuid4()), "ver": (cur["ver"] + 1) if cur else 1, "deleted": 0,
                    "deleted_at": None, "deleted_by": None, "created_at": cur["created_at"] if cur else ts, "created_by": cur["created_by"] if cur else actor,
                    "updated_at": ts, "updated_by": actor}
        self._write(entity, full)
        return {"entity": entity, "row": full}

    def _check_admin_remains(self):
        users = [self._decode(r) for r in self.db.execute("SELECT * FROM user WHERE deleted = 0 AND active = 1")]
        if not users:
            return
        if not any("admin.users.manage" in self.permissions(u) for u in users):
            raise AuthError("user.last_admin", "at least one active user must keep the right to manage users", 409)

    # ------------------------------------------------------------------ queries
    def permissions(self, user):
        if not user or user["deleted"] or not user["active"]:
            return set()
        prof = self._get("profile", user["profile"])
        perms = set(prof["perms"]) if prof and not prof["deleted"] else set()
        return (perms | set(user["extra_perms"] or [])) & set(PERMISSIONS)

    def users(self):
        return [{k: v for k, v in self._decode(r).items() if k != "pw"} for r in self.db.execute("SELECT * FROM user ORDER BY code")]

    def profiles(self):
        return [self._decode(r) for r in self.db.execute("SELECT * FROM profile WHERE deleted = 0 ORDER BY code")]

    def has_users(self):
        return self.db.execute("SELECT 1 FROM user LIMIT 1").fetchone() is not None

    # ------------------------------------------------------------------ account changes
    def create_user(self, actor, username, display_name, password, profile, extra_perms=(), must_change=True):
        _policy(password)
        if self._get("user", username):
            raise AuthError("user.exists", f"user {username} exists (names are never reused)", 409)
        return self.commit(actor, f"User created: {username}", [{"entity": "user", "code": username, "fields": {
            "display_name": display_name, "pw": hash_password(password), "profile": profile, "extra_perms": list(extra_perms), "active": 1, "must_change": int(must_change)}}])

    def bootstrap_admin(self, username, display_name, password):
        """First administrator; only while no user exists (the caller also restricts it to the server machine)."""
        if self.has_users():
            raise AuthError("setup.done", "an administrator already exists", 409)
        _policy(password)
        return self.commit("setup", f"First administrator: {username}", [{"entity": "user", "code": username, "fields": {
            "display_name": display_name, "pw": hash_password(password), "profile": "administrator", "extra_perms": [], "active": 1, "must_change": 0}}])

    def update_user(self, actor, username, fields, expected_ver):
        allowed = {"display_name", "profile", "extra_perms", "active"}
        if set(fields) - allowed:
            raise AuthError("user.fields", f"only {', '.join(sorted(allowed))} can be changed here")
        seq = self.commit(actor, f"User changed: {username}", [{"entity": "user", "code": username, "fields": fields, "expected_ver": expected_ver}])
        if fields.get("active") in (0, False):
            self.end_sessions(username)
        return seq

    def reset_password(self, actor, username, new_password):
        _policy(new_password)
        seq = self.commit(actor, f"Password reset: {username}", [{"entity": "user", "code": username, "fields": {"pw": hash_password(new_password), "must_change": 1}}])
        self.end_sessions(username)
        return seq

    def change_own_password(self, user, old_password, new_password):
        if not check_password(old_password, user["pw"]):
            raise AuthError("auth.wrong_password", "the current password is wrong", 403)
        _policy(new_password)
        if check_password(new_password, user["pw"]):
            raise AuthError("auth.same_password", "choose a different password")
        return self.commit(user["code"], "Own password changed", [{"entity": "user", "code": user["code"], "fields": {"pw": hash_password(new_password), "must_change": 0}}])

    def save_profile(self, actor, code, name, perms, expected_ver=None):
        return self.commit(actor, f"Profile saved: {code}", [{"entity": "profile", "code": code, "fields": {"name": name, "perms": list(perms)}, "expected_ver": expected_ver}])

    # ------------------------------------------------------------------ sessions (local only, never journaled)
    def login(self, username, password, ip=None):
        """Returns (token, user). Raises AuthError. The caller audits both outcomes."""
        username = (username or "").strip().lower()
        with self.lock:
            fail = self.db.execute("SELECT count, locked_until FROM failure WHERE username = ?", (username,)).fetchone()
            if fail and fail["locked_until"] and fail["locked_until"] > now():
                raise AuthError("auth.locked", f"too many wrong passwords; try again after {fail['locked_until']} (UTC)", 423)
            user = self._get("user", username)
            if not user or user["deleted"] or not user["active"] or not check_password(password or "", user["pw"]):
                count = (fail["count"] if fail else 0) + 1
                locked = _ts(datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINUTES)) if count >= MAX_FAILED else None
                self.db.execute("INSERT OR REPLACE INTO failure (username, count, locked_until) VALUES (?, ?, ?)", (username, 0 if locked else count, locked))
                self.db.commit()
                raise AuthError("auth.failed", "wrong user name or password" + (" — the account is now locked for 15 minutes" if locked else ""), 401)
            self.db.execute("DELETE FROM failure WHERE username = ?", (username,))
            token = secrets.token_urlsafe(32)
            self.db.execute("INSERT INTO session (token_hash, user_id, ip, created_at, last_seen) VALUES (?, ?, ?, ?, ?)",
                            (hashlib.sha256(token.encode()).hexdigest(), user["id"], ip, now(), now()))
            self.db.commit()
            return token, user

    def session(self, token):
        """The user of a live session, re-read from the durable accounts on every request (immediate revocation)."""
        if not token:
            return None
        with self.lock:
            th = hashlib.sha256(token.encode()).hexdigest()
            s = self.db.execute("SELECT * FROM session WHERE token_hash = ?", (th,)).fetchone()
            if not s:
                return None
            t = datetime.now(timezone.utc)
            idle = _ts(t - timedelta(minutes=IDLE_MINUTES))
            oldest = _ts(t - timedelta(hours=MAX_HOURS))
            user = self._decode(self.db.execute("SELECT * FROM user WHERE id = ?", (s["user_id"],)).fetchone())
            if s["last_seen"] < idle or s["created_at"] < oldest or not user or user["deleted"] or not user["active"]:
                self.db.execute("DELETE FROM session WHERE token_hash = ?", (th,))
                self.db.commit()
                return None
            self.db.execute("UPDATE session SET last_seen = ? WHERE token_hash = ?", (now(), th))
            self.db.commit()
            return user

    def logout(self, token):
        with self.lock:  # the statement and its commit together: another thread's BEGIN must not fall between them
            self.db.execute("DELETE FROM session WHERE token_hash = ?", (hashlib.sha256((token or "").encode()).hexdigest(),))
            self.db.commit()

    def end_sessions(self, username):
        with self.lock:
            user = self._get("user", username)
            if user:
                self.db.execute("DELETE FROM session WHERE user_id = ?", (user["id"],))
                self.db.commit()

    def close(self):
        self.db.close()


def _policy(password):
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise AuthError("auth.weak_password", f"passwords need at least {MIN_PASSWORD} characters")
