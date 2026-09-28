"""HR-System's secured service (phase 2): the one place where a person's request meets the data.

Opens this installation's device, the signed journal, the registry, the accounts and the backups, and puts a
permission check and an audit entry in front of every operation. The HTTP server (hr_core/api.py) is a thin
translation of this class; nothing reaches the registry or the accounts without passing `require`.
Standard library only.
"""

import os

from . import signing
from .auth import PERMISSIONS, Auth, AuthError
from .backup import Backups, BackupError, recover_lost_journal
from .device import Device
from .journal import Journal
from . import scheduling, skills
from .registry import ENTITIES, Conflict, Registry, RegistryError

WRITE_PERM = {"org_unit": "hr.org.write", "job": "hr.org.write", "position": "hr.org.write", "employee": "hr.employees.write",
              "shift": "hr.shifts.write", "work_calendar": "hr.shifts.write", "shift_assignment": "hr.shifts.write", "roster_override": "hr.shifts.write",
              "skill": "hr.skills.write", "employee_skill": "hr.skills.write"}
READ_PERM = {"org_unit": "hr.org.read", "job": "hr.org.read", "position": "hr.org.read", "employee": "hr.employees.read",
             "shift": "hr.shifts.read", "work_calendar": "hr.shifts.read", "shift_assignment": "hr.shifts.read", "roster_override": "hr.shifts.read",
             "skill": "hr.skills.read", "employee_skill": "hr.skills.read"}


class HRService:
    def __init__(self, data_dir, company_id, company_code="COMPANY", company_name="Company",
                 backup_dir=None, extra_backup_dirs=(), keep=14, allow_new_journal=False, attachments=()):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        backup_dir = backup_dir or os.path.join(data_dir, "backups")
        journal_path = os.path.join(data_dir, "hr_journal.db")
        restored_from = None
        if not os.path.exists(journal_path) and any(os.path.exists(os.path.join(data_dir, f)) for f in ("hr.db", "auth.db")):
            restored_from = recover_lost_journal(data_dir, [backup_dir, *extra_backup_dirs])
            if restored_from is None and not allow_new_journal:
                raise RuntimeError("the permanent journal (hr_journal.db) is missing and no verified backup holds it; "
                                   "put back hr_journal.db or start with allow_new_journal=True to re-record the tables as a new history")
        self.device = Device(data_dir)
        self.journal = Journal(data_dir, self.device)
        self.registry = Registry(data_dir, company_id, company_code, company_name, journal=self.journal)
        self.auth = Auth(data_dir, self.journal)
        self.backups = Backups(data_dir, self.journal, self.registry, self.auth, backup_dir, extra_backup_dirs, keep, attachments)
        self.journal.audit("system", "service.started", "system", {
            "device": self.device.device_id, "signing_backend": signing.BACKEND,
            "cloned_from": self.device.cloned_from, "journal_restored_from": restored_from})
        if self.device.cloned_from:
            self.journal.audit("security", "device.clone_detected", "system", {"previous_device": self.device.cloned_from, "new_device": self.device.device_id})

    # ------------------------------------------------------------------ sessions
    def login(self, username, password, ip=None):
        try:
            token, user = self.auth.login(username, password, ip)
        except AuthError as exc:
            self.journal.audit("security", "login.failed" if exc.code != "auth.locked" else "login.locked", (username or "")[:50], {"code": exc.code}, ip)
            raise
        self.journal.audit("security", "login.ok", user["code"], {}, ip)
        return token, user

    def logout(self, token, user=None, ip=None):
        self.auth.logout(token)
        if user:
            self.journal.audit("security", "logout", user["code"], {}, ip)

    def session(self, token):
        return self.auth.session(token)

    def me(self, user):
        return {"user": user["code"], "display_name": user["display_name"], "profile": user["profile"],
                "must_change": bool(user["must_change"]), "permissions": sorted(self.auth.permissions(user))}

    def require(self, user, perm, ip=None, what=None):
        """The server-side gate. Recomputed on every call from the durable accounts."""
        if user is None:
            raise AuthError("auth.required", "please sign in", 401)
        if user["must_change"] and perm != "self":
            raise AuthError("auth.must_change", "change your password first", 403)
        if perm != "self" and perm not in self.auth.permissions(user):
            self.journal.audit("security", "permission.denied", user["code"], {"permission": perm, "what": what}, ip)
            raise AuthError("perm.denied", f"you do not have the right {perm} ({PERMISSIONS.get(perm, perm)})", 403)

    def change_own_password(self, user, old, new, ip=None):
        self.require(user, "self", ip)
        try:
            self.auth.change_own_password(user, old, new)
        except AuthError as exc:
            self.journal.audit("security", "password.change_failed", user["code"], {"code": exc.code}, ip)
            raise
        self.journal.audit("security", "password.changed", user["code"], {}, ip)

    # ------------------------------------------------------------------ business data
    def list(self, user, entity, include_deleted=False, ip=None):
        self._entity(entity)
        self.require(user, READ_PERM[entity], ip, entity)
        return self.registry.list(entity, include_deleted)

    def recycle_bin(self, user, ip=None):
        self.require(user, "hr.org.read", ip, "recycle")
        return {e: [r for r in self.registry.list(e, True) if r["deleted"]] for e in ENTITIES
                if READ_PERM[e] in self.auth.permissions(user)}

    def save(self, user, entity, code, fields, expected_ver=None, ip=None):
        """Create (no current record) or change (expected_ver REQUIRED: a stale or missing version is a 409,
        never a silent overwrite)."""
        self._entity(entity)
        self.require(user, WRITE_PERM[entity], ip, f"{entity}:{code}")
        cur = self.registry.get(entity, code, org_type=fields.get("type") if entity == "org_unit" else None, include_deleted=True)
        if cur and expected_ver is None:
            raise Conflict("ver.required", f"{entity} {code} exists: send the version you edited (expected_ver)")
        if not cur and expected_ver is not None:
            raise Conflict("ver.conflict", f"{entity} {code} does not exist any more")
        if entity == "employee_skill" and cur and fields.get("certified_on") and fields["certified_on"] != cur.get("certified_on") \
                and fields.get("expires_on") == cur.get("expires_on"):
            # recertified with the old expiry still in the form: if that expiry came from the skill's validity, it moves too
            skill = self.registry.by_id("skill", cur["skill_id"])
            if cur.get("expires_on") == skills.default_expiry(cur.get("certified_on"), skill and skill.get("validity_months")):
                fields = dict(fields, expires_on=None)
        if entity == "employee_skill" and not fields.get("expires_on"):
            skill = self.registry.by_id("skill", fields.get("skill_id") or (cur or {}).get("skill_id"))
            expiry = skills.default_expiry(fields.get("certified_on") or (cur or {}).get("certified_on"), skill and skill.get("validity_months"))
            if expiry:
                fields = dict(fields, expires_on=expiry)  # a blank expiry takes the skill's validity
        seq = self._commit(user, ip, f"{'Changed' if cur else 'Created'} {entity} {code}",
                           [self.registry.op_put(entity, code, fields, expected_ver)], "record.saved", entity, code)
        return {"seq": seq, "row": self.registry.get(entity, code, org_type=fields.get("type") if entity == "org_unit" else None)}

    def delete(self, user, entity, code, expected_ver, org_type=None, ip=None):
        """Moves the record to the Recycle Bin (soft delete); nothing is erased."""
        self._entity(entity)
        self.require(user, "hr.employees.delete", ip, f"{entity}:{code}")
        return self._commit(user, ip, f"Moved {entity} {code} to the Recycle Bin",
                            [self.registry.op_delete(entity, code, expected_ver, org_type)], "record.deleted", entity, code)

    def restore(self, user, entity, code, org_type=None, ip=None):
        self._entity(entity)
        self.require(user, "hr.recycle.restore", ip, f"{entity}:{code}")
        return self._commit(user, ip, f"Restored {entity} {code} from the Recycle Bin",
                            [self.registry.op_restore(entity, code, org_type)], "record.restored", entity, code)

    def _commit(self, user, ip, label, ops, event, entity, code):
        try:
            seq = self.registry.commit(user["code"], label, ops)
        except RegistryError as exc:
            self.journal.audit("activity", "change.refused", user["code"],
                               {"entity": entity, "code": code, "reason": exc.code}, ip)
            raise
        self.journal.audit("activity", event, user["code"], {"entity": entity, "code": code, "journal_seq": seq}, ip)
        return seq

    @staticmethod
    def _entity(entity):
        if entity not in ENTITIES:
            raise RegistryError("entity.unknown", f"unknown entity {entity}")

    # ------------------------------------------------------------------ accounts
    def users(self, user, ip=None):
        self.require(user, "admin.users.manage", ip, "users")
        return self.auth.users()

    def profiles(self, user, ip=None):
        self.require(user, "admin.users.manage", ip, "profiles")
        return self.auth.profiles()

    def create_user(self, user, username, display_name, password, profile, extra_perms=(), ip=None):
        self.require(user, "admin.users.manage", ip, f"user:{username}")
        seq = self.auth.create_user(user["code"], username, display_name, password, profile, extra_perms)
        self.journal.audit("security", "user.created", user["code"], {"user": username, "profile": profile, "extra_perms": sorted(extra_perms)}, ip)
        return seq

    def update_user(self, user, username, fields, expected_ver, ip=None):
        self.require(user, "admin.users.manage", ip, f"user:{username}")
        if expected_ver is None:
            raise AuthError("ver.required", "send the version you edited (expected_ver)", 409)
        seq = self.auth.update_user(user["code"], username, fields, expected_ver)
        self.journal.audit("security", "user.changed", user["code"], {"user": username, "fields": sorted(fields)}, ip)
        return seq

    def reset_password(self, user, username, new_password, ip=None):
        self.require(user, "admin.users.manage", ip, f"user:{username}")
        seq = self.auth.reset_password(user["code"], username, new_password)
        self.journal.audit("security", "password.reset", user["code"], {"user": username}, ip)
        return seq

    def save_profile(self, user, code, name, perms, expected_ver=None, ip=None):
        self.require(user, "admin.users.manage", ip, f"profile:{code}")
        seq = self.auth.save_profile(user["code"], code, name, perms, expected_ver)
        self.journal.audit("security", "profile.saved", user["code"], {"profile": code, "perms": sorted(perms)}, ip)
        return seq

    def bootstrap_admin(self, username, display_name, password, ip=None):
        seq = self.auth.bootstrap_admin(username, display_name, password)
        self.journal.audit("security", "setup.first_admin", username, {}, ip)
        return seq

    # ------------------------------------------------------------------ audit, health, backups
    # ------------------------------------------------------------------ the planned schedule (phase 3)
    def schedule(self, user, first, last, employee_code=None, ip=None):
        self.require(user, "hr.shifts.read", ip, "schedule")
        plan = scheduling.Schedule(self.registry)
        ids = None
        if employee_code:
            emp = self.registry.get("employee", employee_code)
            if not emp:
                raise RegistryError("employee.not_found", f"employee {employee_code} does not exist")
            ids = [emp["id"]]
        try:
            return plan.days(first, last, ids)
        except scheduling.ScheduleError as exc:
            raise RegistryError(exc.code, str(exc)) from None

    def compare(self, user, first, last, attendance_rows, ip=None):
        """Planned days against attendance (needs both rights: it shows both)."""
        self.require(user, "hr.attendance.read", ip, "schedule.compare")
        days = self.schedule(user, first, last, None, ip)
        return scheduling.compare(days, attendance_rows, scheduling.Schedule(self.registry).employees)

    def swap(self, user, work_date, code_a, code_b, reason, ip=None):
        """Two people exchange their shifts of one day: two day changes in ONE save (both or neither)."""
        self.require(user, "hr.shifts.write", ip, f"swap:{code_a}:{code_b}")
        a, b = self.registry.get("employee", code_a), self.registry.get("employee", code_b)
        if not a or not b or a["id"] == b["id"]:
            raise RegistryError("swap.people", "a swap needs two different, existing employees")
        plan = scheduling.Schedule(self.registry)
        da, db = plan.day(a["id"], work_date), plan.day(b["id"], work_date)
        if da["status"] != "work" and db["status"] != "work":
            raise RegistryError("swap.nothing", "neither person works that day: there is nothing to swap")
        shift_id = lambda d: next((s["id"] for s in plan.shifts.values() if s["code"] == d["shift_code"] and not s["deleted"]), None) if d["status"] == "work" else None  # noqa: E731
        why = (reason or "").strip() or "swap"
        ops = []
        for emp, other, day in ((a, b, db), (b, a, da)):
            code = f"{emp['code']}-{work_date}"
            cur = self.registry.get("roster_override", code)
            ops.append(self.registry.op_put("roster_override", code, {"employee_id": emp["id"], "work_date": work_date, "shift_id": shift_id(day),
                                                                     "reason": f"{why} (with {other['code']})"}, cur["ver"] if cur else None))
        return self._commit(user, ip, f"Swapped {code_a} and {code_b} on {work_date}", ops, "schedule.swapped", "roster_override", f"{code_a}/{code_b}")

    def audit_entries(self, user, category=None, limit=200, ip=None):
        self.require(user, "admin.audit.read", ip, "audit")
        return self.journal.audit_entries(category, limit)

    def health(self, user=None, ip=None):
        if user is not None:
            self.require(user, "admin.system.read", ip, "health")
        latest = self.backups.latest()
        return {"journal": self.journal.verify(), "audit": self.journal.verify_audit(),
                "signing": {"backend": signing.BACKEND, "problems": signing.PROBLEMS},
                "device": {"id": self.device.device_id, "name": self.device.name, "cloned_from": self.device.cloned_from},
                "registry": {"applied_seq": self.registry.applied_seq(), "journal_seq": self.journal.last_seq()},
                "last_backup": latest}

    def backup_create(self, user, ip=None):
        self.require(user, "admin.backup.manage", ip, "backup")
        made = self.backups.create(user["code"], "manual")
        made["rehearsal"] = self.backups.rehearse(made["path"], user["code"])
        return {k: v for k, v in made.items() if k != "path"}

    def backup_list(self, user, ip=None):
        self.require(user, "admin.backup.manage", ip, "backup")
        return self.backups.list()

    def backup_verify(self, user, name, ip=None):
        self.require(user, "admin.backup.manage", ip, f"backup:{name}")
        return self.backups.verify(self.backups.path_of(name))

    def backup_rehearse(self, user, name, ip=None):
        self.require(user, "admin.backup.manage", ip, f"backup:{name}")
        return self.backups.rehearse(self.backups.path_of(name), user["code"])

    def backup_restore(self, user, name, ip=None):
        self.require(user, "admin.backup.restore", ip, f"backup:{name}")
        return self.backups.restore(self.backups.path_of(name), user["code"])

    def close(self):
        self.backups.stop()
        self.auth.close()
        self.registry.close()


__all__ = ["HRService", "AuthError", "BackupError", "Conflict", "RegistryError"]
