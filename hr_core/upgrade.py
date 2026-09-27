"""Moving an installation's data to the program's data version, safely (phase 2.5, ADR-HR-007).

On every start, before the server accepts a request:
  * data written by a NEWER program is refused (never silently opened by an older one);
  * older data gets a verified, rehearsed pre-update backup first (kept forever, `keep-...`), then each step of
    MIGRATIONS runs as journal lines by the actor `upgrade`, and the data version is written after each step;
  * a step that fails puts the data folder back exactly as the pre-update backup holds it and the program stops
    with a plain message (the one case where files are copied back: nothing but the failed step wrote after that
    backup, which is checked first);
  * a power cut in the middle leaves `upgrade-in-progress.json`; the next start continues from the last finished
    step (every step checks what is already done, so repeating one changes nothing).

The last known-good installer is kept in <home>/recovery/known-good with its version and SHA-256. The installer
leaves a copy of itself in recovery/pending; it is promoted only after this version started and verified cleanly.
Standard library only.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import time

from .backup import FILES, Backups, _ro
from .version import DATA_VERSION, VERSION

MARKER = "upgrade-in-progress.json"
VERSION_FILE = "data_version.json"


class UpgradeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------- steps
def _m1_attendance_rights(svc):
    """Data version 1: the built-in profiles of an older installation gain the rights added with the attendance
    screens and the settings (a customised profile keeps what it had and only gains)."""
    from .auth import ADDED_IN_DATA_VERSION_1
    for code, added in sorted(ADDED_IN_DATA_VERSION_1.items()):
        cur = svc.auth._get("profile", code)
        if not cur or cur["deleted"]:
            continue
        want = sorted(set(cur["perms"] or []) | set(added))
        if want != sorted(cur["perms"] or []):
            svc.auth.commit("upgrade", f"Data version 1: profile {code} gains {', '.join(sorted(set(want) - set(cur['perms'] or [])))}",
                            [{"entity": "profile", "code": code, "fields": {"perms": want}, "expected_ver": cur["ver"]}])


MIGRATIONS = [(1, "built-in profiles gain the attendance and settings rights", _m1_attendance_rights)]
assert [n for n, _, _ in MIGRATIONS] == list(range(1, DATA_VERSION + 1)), "one migration per data version"


# ---------------------------------------------------------------------- data version
def read_version(data_dir):
    """The data version on disk; None for a new, empty installation; 0 for data from before versions existed."""
    try:
        with open(os.path.join(data_dir, VERSION_FILE), encoding="utf-8") as fh:
            return int(json.load(fh)["data_version"])
    except FileNotFoundError:
        return 0 if os.path.exists(os.path.join(data_dir, "hr_journal.db")) else None


def write_version(data_dir, n):
    path = os.path.join(data_dir, VERSION_FILE)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump({"data_version": n, "written_by": VERSION, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(path + ".tmp", path)


def _fault(step, where):
    """Planted faults for the delivery tests only (HR_TEST_HOOKS=1): fail:<step> or stall:<step>."""
    if os.environ.get("HR_TEST_HOOKS") != "1":
        return
    fault = os.environ.get("HR_UPGRADE_FAULT", "")
    if fault == f"fail:{step}" and where == "after":
        raise RuntimeError(f"planted failure in step {step}")
    if fault == f"stall:{step}" and where == "after":
        while True:  # the test kills the process here: a power cut after the step's line, before its version
            time.sleep(1)


# ---------------------------------------------------------------------- the whole procedure
def prepare(home, open_service):
    """Returns an open HRService on data at DATA_VERSION, or raises UpgradeError with nothing lost."""
    data = home.data
    found = read_version(data)
    if found is None:
        svc = open_service()
        write_version(data, DATA_VERSION)
        return svc, {"from": None, "to": DATA_VERSION}
    if found > DATA_VERSION:
        raise UpgradeError("data.newer", f"this data was written by a newer HR-System (data version {found}); this program "
                           f"understands up to {DATA_VERSION}. Install that version again (see the recovery folder).")
    marker_path = os.path.join(data, MARKER)
    marker = json.load(open(marker_path, encoding="utf-8")) if os.path.exists(marker_path) else None
    svc = open_service()
    if found == DATA_VERSION and marker is None:
        return svc, {"from": found, "to": DATA_VERSION}
    if marker is None:
        made = svc.backups.create("upgrade", "pre-update")
        rehearsal = svc.backups.rehearse(made["path"], "upgrade")
        if not rehearsal["ok"]:
            svc.close()
            raise UpgradeError("upgrade.backup_failed", "the backup before the update did not pass its rehearsal; nothing "
                               "was changed. Details: " + "; ".join(rehearsal["problems"]))
        marker = {"from": found, "to": DATA_VERSION, "backup": made["name"], "journal_hash": made["manifest"]["journal"]["last_hash"],
                  "program": VERSION, "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        with open(marker_path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(marker, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(marker_path + ".tmp", marker_path)
        svc.journal.audit("system", "upgrade.started", "upgrade", {k: marker[k] for k in ("from", "to", "backup", "program")})
    else:
        svc.journal.audit("system", "upgrade.resumed", "upgrade", {k: marker[k] for k in ("from", "to", "backup", "program")})
    backup_path = os.path.join(home.backups, marker["backup"])
    if not Backups.verify(backup_path)["ok"]:
        svc.close()
        raise UpgradeError("upgrade.backup_missing", f"an interrupted update needs its backup {marker['backup']}, which is "
                           "missing or damaged; nothing more was changed. Ask for help before starting again.")
    try:
        for n, label, step in MIGRATIONS:
            if n <= read_version(data):
                continue
            step(svc)
            _fault(n, "after")
            write_version(data, n)
    except Exception as exc:
        svc.close()
        _put_back(home, marker)
        raise UpgradeError("upgrade.failed", f"the update of the data failed ({type(exc).__name__}: {exc}). The data was "
                           f"put back exactly as the backup {marker['backup']} holds it; install the previous version "
                           "again from the recovery folder.") from exc
    os.remove(marker_path)
    svc.journal.audit("system", "upgrade.done", "upgrade", {"from": marker["from"], "to": DATA_VERSION, "backup": marker["backup"]})
    return svc, {"from": marker["from"], "to": DATA_VERSION, "backup": marker["backup"]}


def _put_back(home, marker):
    """Undo a failed update: the data files become the pre-update backup's again. Allowed only because every journal
    line after that backup was written by the update itself (checked here)."""
    backup = os.path.join(home.backups, marker["backup"])
    db = _ro(os.path.join(home.data, "hr_journal.db"))
    try:
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT seq, hash, actor FROM journal ORDER BY seq").fetchall()
    finally:
        db.close()
    hashes = [r["hash"] for r in rows]
    if marker["journal_hash"] is not None and marker["journal_hash"] not in hashes:
        raise UpgradeError("upgrade.diverged", "the journal no longer contains the state of the pre-update backup; nothing was put back")
    after = rows[hashes.index(marker["journal_hash"]) + 1:] if marker["journal_hash"] else rows
    others = sorted({r["actor"] for r in after} - {"upgrade"})
    if others:
        raise UpgradeError("upgrade.diverged", f"lines by {others} were written after the pre-update backup; nothing was put back")
    manifest = json.load(open(os.path.join(backup, "manifest.json"), encoding="utf-8"))
    for f in list(FILES) + sorted(manifest.get("attachments", {})):
        for side in ("-wal", "-shm"):  # a stale write-ahead log would be replayed onto the restored file
            if os.path.exists(os.path.join(home.data, f + side)):
                os.remove(os.path.join(home.data, f + side))
        shutil.copy2(os.path.join(backup, f), os.path.join(home.data, f + ".restoring"))
        os.replace(os.path.join(home.data, f + ".restoring"), os.path.join(home.data, f))
    if marker["from"]:
        write_version(home.data, marker["from"])
    elif os.path.exists(os.path.join(home.data, VERSION_FILE)):
        os.remove(os.path.join(home.data, VERSION_FILE))  # data from before versions existed: no file, as before
    os.remove(os.path.join(home.data, MARKER))


# ---------------------------------------------------------------------- recovery folder
def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def known_good(home):
    """The installer kept for recovery: its version, and whether it still matches its recorded SHA-256."""
    info_path = os.path.join(home.recovery, "known-good", "installer.json")
    if not os.path.isfile(info_path):
        return None
    info = json.load(open(info_path, encoding="utf-8"))
    exe = os.path.join(home.recovery, "known-good", info["file"])
    return {**info, "intact": os.path.isfile(exe) and _sha256(exe) == info["sha256"]}


def promote_installer(home):
    """After this version started and verified cleanly: the installer it came with becomes the known-good one (only
    one is kept). A pending installer that is not this version, or whose bytes do not match its SHA-256, is discarded."""
    pending = os.path.join(home.recovery, "pending")
    info_path = os.path.join(pending, "installer.json")
    if not os.path.isfile(info_path):
        return None
    try:
        info = json.load(open(info_path, encoding="utf-8"))
        exe = os.path.join(pending, info["file"])
        ok = info.get("version") == VERSION and os.path.isfile(exe) and _sha256(exe).lower() == str(info.get("sha256", "")).lower()
    except (OSError, ValueError, KeyError):
        ok, info = False, {}
    if not ok:
        shutil.rmtree(pending, ignore_errors=True)
        return {"promoted": False, "reason": "the pending installer is not this version or does not match its SHA-256"}
    target = os.path.join(home.recovery, "known-good")
    staging = target + ".new"
    shutil.rmtree(staging, ignore_errors=True)
    os.replace(pending, staging)
    info["sha256"] = info["sha256"].lower()
    with open(os.path.join(staging, "installer.json"), "w", encoding="utf-8") as fh:
        json.dump(info, fh, indent=1)
    shutil.rmtree(target, ignore_errors=True)
    os.replace(staging, target)
    return {"promoted": True, "version": info["version"], "sha256": info["sha256"]}
