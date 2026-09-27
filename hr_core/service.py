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
from .registry import ENTITIES, Conflict, Registry, RegistryError

WRITE_PERM = {"org_unit": "hr.org.write", "job": "hr.org.write", "position": "hr.org.write", "employee": "hr.employees.write"}
READ_PERM = {"org_unit": "hr.org.read", "job": "hr.org.read", "position": "hr.org.read", "employee": "hr.employees.read"}


class HRService:
    def __init__(self, data_dir, company_id, company_code="COMPANY", company_name="Company",
                 backup_dir=None, extra_backup_dirs=(), keep=14, allow_new_journal=False):
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
        self.backups = Backups(data_dir, self.journal, self.registry, self.auth, backup_dir, extra_backup_dirs, keep)
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
