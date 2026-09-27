"""Verified backups, automatic restore rehearsal and compensating restore (phase 2) — the BAMS model for HR.

A backup is a folder  <dest>/hr-<UTC time>-<n>/  holding consistent online copies (SQLite backup API) of
  hr.db          business tables (a fold of the journal)
  auth.db        users and profiles (sessions, failed-login counters and lockouts are stripped)
  hr_journal.db  the permanent signed journal and the audit log
  device.json    this installation's PUBLIC identity (the private device.key is never in a backup)
  history.db     (phase 2.5) the attendance application's history, copied while no upload runs
  manifest.json  SHA-256 and size of every file, the journal's length and last hash, the registry fingerprint,
                 signed by this installation's device.

A backup counts only once verified: every file's hash and `PRAGMA integrity_check`, the manifest signature, and a
journal that verifies end to end. After every automatic backup a REHEARSAL copies it to a temporary folder,
opens it as a real installation would, rebuilds the business tables and the accounts from the journal, and
compares fingerprints with what was backed up. The result is audited and kept beside the backup.

Restore never rolls history back: the backup's business rows become ONE new `restore` line in the live journal
(a compensating change that can itself be undone). Accounts are not restored (as in BAMS: a restore must not
bring back a removed user or an old password). Standard library only.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import signing
from .canonical import canonical
from .journal import Journal, now

FILES = ("hr.db", "auth.db", "hr_journal.db")
KEEP = "keep-"  # name prefix of the backups kept forever (taken before an update)
FORMAT = "hr-backup-1"


class BackupError(Exception):
    pass


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ro(path):
    """Read-only connection. A proper file URI, so Windows drive letters and spaces in folder names work."""
    return sqlite3.connect(Path(os.path.abspath(path)).as_uri() + "?mode=ro", uri=True)


def _integrity(path):
    db = _ro(path)
    try:
        return db.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        db.close()


def _copy_db(src_path, dest_path):
    """Online copy through a fresh connection: it reads the last committed state (WAL snapshot) and cannot be
    blocked by, or pick up, a transaction left open on the live connection."""
    src, dst = _ro(src_path), sqlite3.connect(dest_path)
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode = DELETE")  # one self-contained file, no -wal beside it
    finally:
        dst.close()
        src.close()


def _state(path):
    """What tells an attachment changed since the last backup (its copy in a backup is not byte-identical)."""
    st = os.stat(path)
    return [str(st.st_mtime_ns), st.st_size]  # a string: nanoseconds exceed the integers canonical JSON carries exactly


def _manifest_digest(manifest):
    body = {k: v for k, v in manifest.items() if k != "signature"}
    return hashlib.sha256(canonical(body).encode("utf-8")).digest()


def local_path_problem(path):
    """Backups go to local disks only (a network share can vanish or be read by others)."""
    p = str(path)
    if p.startswith("\\\\") or p.startswith("//"):
        return "network (UNC) paths are refused; use a local or removable disk"
    return None


class Backups:
    def __init__(self, data_dir, journal, registry, auth, dest=None, extra=(), keep=14, attachments=()):
        """`attachments`: other databases of this installation that are not folds of the journal (the attendance
        history), each (file name, path, lock). Each is copied while its lock is held, so no upload is half in it."""
        self.data_dir, self.journal, self.registry, self.auth = data_dir, journal, registry, auth
        self.attachments = list(attachments)
        self.dest = dest or os.path.join(data_dir, "backups")
        self.extra = list(extra)
        for d in [self.dest] + self.extra:
            problem = local_path_problem(d)
            if problem:
                raise BackupError(f"{d}: {problem}")
        self.keep = keep
        self.lock = threading.Lock()
        self._timer = None

    # ------------------------------------------------------------------ create
    def create(self, actor, reason="manual"):
        with self.lock:
            os.makedirs(self.dest, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            prefix = KEEP if reason == "pre-update" else "hr-"  # pre-update backups are never removed by retention
            n, name = 1, f"{prefix}{stamp}-1"
            while os.path.exists(os.path.join(self.dest, name)):
                n += 1
                name = f"{prefix}{stamp}-{n}"
            work = os.path.join(self.dest, "." + name + ".partial")
            os.makedirs(work)
            try:
                # one consistent moment: no journal line, fold or account change can run in between
                with self.journal.lock, self.registry.lock, self.auth.lock:
                    _copy_db(self.registry.path, os.path.join(work, "hr.db"))
                    _copy_db(self.auth.path, os.path.join(work, "auth.db"))
                    _copy_db(self.journal.path, os.path.join(work, "hr_journal.db"))
                    fingerprint = self.registry.fingerprint()
                    jv = self.journal.verify()
                    attached = {}
                    for fname, path, lock in self.attachments:
                        with lock:
                            if os.path.isfile(path):
                                _copy_db(path, os.path.join(work, fname))
                                attached[fname] = _state(path)
                a = sqlite3.connect(os.path.join(work, "auth.db"))
                a.executescript("DELETE FROM session; DELETE FROM failure; VACUUM;")  # live secrets stay home
                a.close()
                device = self.journal.device
                if device is not None:
                    with open(os.path.join(work, "device.json"), "w", encoding="utf-8") as fh:
                        json.dump({k: device.info[k] for k in ("device_id", "name", "public_key", "machine")}, fh, indent=1)
                files = {f: {"sha256": _sha256(os.path.join(work, f)), "size": os.path.getsize(os.path.join(work, f))}
                         for f in sorted(os.listdir(work))}
                manifest = {"format": FORMAT, "name": name, "created_at": now(), "actor": actor, "reason": reason,
                            "company_id": self.registry.company_id, "files": files,
                            "journal": {"lines": jv["lines"], "last_hash": jv["last_hash"], "ok": jv["ok"]},
                            "registry": {"fingerprint": fingerprint}, "attachments": attached,
                            "device": device.device_id if device else None, "signing_backend": signing.BACKEND}
                if device is not None:
                    manifest["signature"] = device.sign(_manifest_digest(manifest)).hex()
                with open(os.path.join(work, "manifest.json"), "w", encoding="utf-8") as fh:
                    json.dump(manifest, fh, indent=1, sort_keys=True)
                final = os.path.join(self.dest, name)
                os.replace(work, final)
            except BaseException:
                shutil.rmtree(work, ignore_errors=True)
                raise
            check = self.verify(final)
            if not check["ok"]:
                self.journal.audit("system", "backup.failed", actor, {"name": name, "problems": check["problems"]})
                shutil.rmtree(final, ignore_errors=True)
                raise BackupError("the new backup did not verify: " + "; ".join(check["problems"]))
            copies = []
            for d in self.extra:
                try:
                    os.makedirs(d, exist_ok=True)
                    shutil.copytree(final, os.path.join(d, name))
                    if self.verify(os.path.join(d, name))["ok"]:
                        copies.append(d)
                except OSError as exc:
                    self.journal.audit("system", "backup.copy_failed", actor, {"name": name, "dest": d, "error": type(exc).__name__})
            self.journal.audit("system", "backup.created", actor, {"name": name, "reason": reason, "journal_lines": jv["lines"], "copies": len(copies)})
            self._retain()
            return {"name": name, "path": final, "manifest": manifest, "copies": copies}

    def _retain(self):
        for d in [self.dest] + self.extra:
            if not os.path.isdir(d):
                continue
            names = sorted(n for n in os.listdir(d) if n.startswith("hr-") and os.path.isdir(os.path.join(d, n)))  # never KEEP
            for old in names[:-self.keep] if self.keep else []:
                shutil.rmtree(os.path.join(d, old), ignore_errors=True)

    # ------------------------------------------------------------------ list / verify
    def path_of(self, name):
        if not name or "/" in name or "\\" in name or name.startswith("."):
            raise BackupError("unknown backup")
        path = os.path.join(self.dest, name)
        if not os.path.isfile(os.path.join(path, "manifest.json")):
            raise BackupError("unknown backup")
        return path

    def list(self):
        out = []
        if os.path.isdir(self.dest):
            for n in sorted(os.listdir(self.dest), reverse=True):
                mf = os.path.join(self.dest, n, "manifest.json")
                if n.startswith(("hr-", KEEP)) and os.path.isfile(mf):
                    m = json.load(open(mf, encoding="utf-8"))
                    reh = os.path.join(self.dest, n, "rehearsal.json")
                    out.append({"name": n, "created_at": m["created_at"], "reason": m["reason"], "actor": m["actor"],
                                "journal_lines": m["journal"]["lines"], "kept_forever": n.startswith(KEEP),
                                "attachments": sorted(m.get("attachments", {})),
                                "rehearsal": json.load(open(reh, encoding="utf-8")) if os.path.isfile(reh) else None})
        return out

    def latest(self):
        items = self.list()
        return items[0] if items else None

    @staticmethod
    def verify(path):
        """Every file present with its recorded hash, every database passes integrity_check, the manifest is
        signed by a device the backup's own journal registered, and the journal verifies end to end."""
        problems = []
        try:
            manifest = json.load(open(os.path.join(path, "manifest.json"), encoding="utf-8"))
        except (OSError, ValueError):
            return {"ok": False, "problems": ["manifest.json is missing or unreadable"]}
        if manifest.get("format") != FORMAT:
            problems.append("unknown backup format")
        for f in FILES:
            if f not in manifest.get("files", {}):
                problems.append(f"{f} is not in the manifest")
        for f, meta in manifest.get("files", {}).items():
            fp = os.path.join(path, f)
            if not os.path.isfile(fp):
                problems.append(f"{f} is missing")
            elif _sha256(fp) != meta["sha256"] or os.path.getsize(fp) != meta["size"]:
                problems.append(f"{f} does not match its recorded hash")
            elif f.endswith(".db"):
                try:
                    res = _integrity(fp)
                except sqlite3.DatabaseError as exc:
                    res = str(exc)
                if res != "ok":
                    problems.append(f"{f} integrity_check: {res}")
        if problems:
            return {"ok": False, "problems": problems}
        j = Journal.__new__(Journal)  # read-only view: no schema changes, no device registration
        j.db = _ro(os.path.join(path, "hr_journal.db"))
        j.db.row_factory = sqlite3.Row
        try:
            jv = j.verify()
            if not jv["ok"]:
                problems.append(f"journal line {jv['first_bad_seq']}: {jv['reason']}")
            elif jv["last_hash"] != manifest["journal"]["last_hash"] or jv["lines"] != manifest["journal"]["lines"]:
                problems.append("the journal is not the one the manifest describes")
            if manifest.get("device"):
                pub = None
                for r in j.db.execute("SELECT ops FROM journal WHERE kind = 'device'"):
                    for o in json.loads(r["ops"]):
                        if o["row"]["id"] == manifest["device"]:
                            pub = bytes.fromhex(o["row"]["public_key"])
                sig = manifest.get("signature")
                if pub is None or not sig or not signing.verify(pub, _manifest_digest(manifest), bytes.fromhex(sig)):
                    problems.append("the manifest signature does not verify")
        finally:
            j.db.close()
        return {"ok": not problems, "problems": problems}

    # ------------------------------------------------------------------ rehearsal
    def rehearse(self, path, actor="system"):
        """Restore the backup into a temporary folder as a real installation would, rebuild everything from the
        journal and compare. Never touches the live data. The result is audited and kept beside the backup."""
        from .auth import Auth
        from .registry import Registry
        checks, tmp = {}, tempfile.mkdtemp(prefix="hr_rehearsal_")
        result = {"at": now(), "ok": False, "checks": checks, "problems": []}
        try:
            v = self.verify(path)
            checks["backup_verified"] = v["ok"]
            result["problems"] += v["problems"]
            if v["ok"]:
                manifest = json.load(open(os.path.join(path, "manifest.json"), encoding="utf-8"))
                for f in FILES:
                    shutil.copy2(os.path.join(path, f), os.path.join(tmp, f))
                checks["copied_to_temporary_folder"] = True
                journal = Journal(tmp)  # no device: a rehearsal must never sign anything
                before = journal.last_seq()
                reg = Registry(tmp, manifest["company_id"], journal=journal)
                auth = Auth(tmp, journal)
                checks["opened_without_new_lines"] = journal.last_seq() == before
                stored = reg.fingerprint()
                checks["tables_match_manifest"] = stored == manifest["registry"]["fingerprint"]
                reg.rebuild()
                checks["rebuilt_from_journal_identical"] = reg.fingerprint() == stored
                accounts = canonical(auth._rows())
                auth.rebuild()
                checks["accounts_rebuilt_identical"] = canonical(auth._rows()) == accounts
                checks["journal_verified"] = journal.verify()["ok"]
                checks["audit_verified"] = journal.verify_audit()["ok"]
                auth.close()
                reg.close()
                result["problems"] += [f"{k} failed" for k, ok in checks.items() if not ok]
                result["ok"] = not result["problems"]
        except Exception as exc:  # a rehearsal reports; it never crashes the server
            result["problems"].append(f"{type(exc).__name__}: {exc}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            result["temporary_folder_removed"] = not os.path.exists(tmp)
        try:
            with open(os.path.join(path, "rehearsal.json"), "w", encoding="utf-8") as fh:
                json.dump(result, fh, indent=1)
        except OSError:
            pass
        self.journal.audit("system", "backup.rehearsal_passed" if result["ok"] else "backup.rehearsal_failed", actor,
                           {"name": os.path.basename(path), "problems": result["problems"]})
        return result

    # ------------------------------------------------------------------ restore
    def backup_rows(self, path):
        """The business rows stored in a verified backup (read from a temporary copy)."""
        from .registry import Registry
        v = self.verify(path)
        if not v["ok"]:
            raise BackupError("the backup does not verify: " + "; ".join(v["problems"]))
        tmp = tempfile.mkdtemp(prefix="hr_restore_")
        try:
            for f in FILES:
                shutil.copy2(os.path.join(path, f), os.path.join(tmp, f))
            reg = Registry(tmp, self.registry.company_id, journal=Journal(tmp))
            rows = reg._all_rows()
            reg.close()
            return rows
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def restore(self, path, actor):
        """Make the live data equal to the backup with ONE compensating journal line (history is kept)."""
        rows = self.backup_rows(path)
        seq = self.registry.restore_state(rows, actor, f"Restored from backup {os.path.basename(path)}")
        self.journal.audit("security", "backup.restored", actor, {"name": os.path.basename(path), "journal_seq": seq})
        return seq

    # ------------------------------------------------------------------ automatic
    def auto(self, actor="system"):
        """Back up if anything changed since the last backup, then rehearse the new backup."""
        last = self.latest()
        current = self.journal.verify()["last_hash"]
        if last:
            m = json.load(open(os.path.join(self.dest, last["name"], "manifest.json"), encoding="utf-8"))
            unchanged = all(m.get("attachments", {}).get(f) == (_state(p) if os.path.isfile(p) else None) for f, p, _ in self.attachments)
            if m["journal"]["last_hash"] == current and unchanged and last["rehearsal"] and last["rehearsal"]["ok"]:
                return None
        made = self.create(actor, "automatic")
        made["rehearsal"] = self.rehearse(made["path"], actor)
        return made

    def start(self, hours=6):
        """Run `auto` now (in the background) and then every `hours`."""
        def tick():
            try:
                self.auto()
            except Exception as exc:
                try:
                    self.journal.audit("system", "backup.failed", "system", {"error": f"{type(exc).__name__}: {exc}"})
                except Exception:
                    pass
            self._timer = threading.Timer(hours * 3600, tick)
            self._timer.daemon = True
            self._timer.start()
        self._timer = threading.Timer(0, tick)
        self._timer.daemon = True
        self._timer.start()

    def stop(self):
        if self._timer:
            self._timer.cancel()


def recover_lost_journal(data_dir, backup_dirs):
    """The journal file is gone but the tables are not: put back the newest backup's journal that verifies.
    The registry and accounts then record what the backup lacked as one `recovery` line on start."""
    candidates = []
    for d in backup_dirs:
        if os.path.isdir(d):
            candidates += [os.path.join(d, n) for n in os.listdir(d) if n.startswith(("hr-", KEEP))]
    for path in sorted(candidates, key=_age, reverse=True):
        if Backups.verify(path)["ok"]:
            shutil.copy2(os.path.join(path, "hr_journal.db"), os.path.join(data_dir, "hr_journal.db"))
            return os.path.basename(path)
    return None


def recover_lost_attachment(data_dir, backup_dirs, fname):
    """An attachment (the attendance history) is gone: put back the newest verified backup's copy. It is not a
    fold of the journal, so this is the only way back; the caller audits it. None when no backup holds it."""
    candidates = []
    for d in backup_dirs:
        if os.path.isdir(d):
            candidates += [os.path.join(d, n) for n in os.listdir(d) if n.startswith(("hr-", KEEP))]
    for path in sorted(candidates, key=_age, reverse=True):
        if os.path.isfile(os.path.join(path, fname)) and Backups.verify(path)["ok"]:
            shutil.copy2(os.path.join(path, fname), os.path.join(data_dir, fname))
            return os.path.basename(path)
    return None


def _age(path):
    """Newest first across both name forms: the time stamp follows the prefix."""
    name = os.path.basename(path)
    return name[len(KEEP):] if name.startswith(KEEP) else name[len("hr-"):]
