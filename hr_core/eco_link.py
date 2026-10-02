"""The installed product publishes HR's workforce truth to manufacturing (GMES) by itself (ecosystem plan, Phase A).

`eco_publisher.py` builds the contracts, keeps the outbox and delivers; this module runs it INSIDE the product:

  * Configured from a screen (Settings -> Integration (GMES)): config.json `eco` = {gmes_url, node, interval_seconds}
    (hr_core/home.py validates it). An empty address = the link is off and HR works on its own.
  * The GMES key is a secret, so it is never a setting: it is kept in data/node/gmes.key, beside device.key. Backups
    copy named databases and the PUBLIC device.json only (hr_core/backup.py), so the key never lands in a backup; it
    is never returned by the API, never written to a log line or to the audit. On Windows it is protected with DPAPI
    (CryptProtectData, machine scope: a copy of the data folder on another PC cannot read it); elsewhere it is a plain
    file readable by the owner only (mode 0600).
  * A background thread started by Product.open() when an address is set, stopped by Product.close(), restarted when
    the settings change. Every cycle opens its OWN connections in the thread that runs it (SQLite objects never cross
    threads): the outbox, and a READ-ONLY view of the registry (hr.db opened with mode=ro, so publishing can never
    write or repair HR's records). Attendance comes from the locked engine bound to this installation's data folder.
  * The last report (time, staged, sent, delivered, rejected, stopped_by, outbox counts) is kept in memory for the
    screen; a cycle that did or failed something is one line in logs/eco-link.log (never the key).

`python eco_publisher.py` with the ECO_* environment variables keeps working unchanged (a second, manual way).
Standard library only.
"""

import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .home import HomeError

KEY_FILE = "gmes.key"
KEY_TEXT = re.compile(r"^[\x21-\x7e]{1,512}$")  # sent as an HTTP header: printable, no space, no line break
_DPAPI_MARK, _PLAIN_MARK = b"hr-dpapi-1\n", b"hr-plain-1\n"
_ENTROPY = b"HR-System eco.gmes_key"
LOG_FILE, LOG_MAX = "eco-link.log", 1 << 20


class LinkError(HomeError):
    """A refused integration request (answered 400 with its code, as every settings error)."""


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------- the secret
def _dpapi(data, protect, entropy=_ENTROPY):
    """Windows Data Protection API through ctypes (standard library). Machine scope (CRYPTPROTECT_LOCAL_MACHINE):
    the program may run as another Windows user after a restart, but a copy of the file on another PC is useless."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    src, ent = ctypes.create_string_buffer(data, len(data)), ctypes.create_string_buffer(entropy, len(entropy))
    blob_in = Blob(len(data), ctypes.cast(src, ctypes.POINTER(ctypes.c_char)))
    blob_ent = Blob(len(entropy), ctypes.cast(ent, ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    flags = 0x1 | 0x4  # CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE
    if not fn(ctypes.byref(blob_in), None, ctypes.byref(blob_ent), None, None, flags, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "the Windows data protection refused the GMES key")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


class KeyStore:
    """The GMES key in data/node/gmes.key (never in config.json, a backup, a log line or the audit). The Mizan key of the payroll link is kept the same
    way in data/node/mizan.key (another file name and entropy)."""

    def __init__(self, data_dir, filename=KEY_FILE, entropy=_ENTROPY):
        self.dir = os.path.join(data_dir, "node")
        self.path = os.path.join(self.dir, filename)
        self.entropy = entropy

    @staticmethod
    def check(key):
        if not isinstance(key, str) or not KEY_TEXT.match(key):
            raise LinkError("integration.key", "the GMES key is 1-512 printable characters without spaces (copy it from GMES)")
        return key

    def exists(self):
        return os.path.isfile(self.path)

    def save(self, key):
        self.check(key)
        raw = key.encode("ascii")
        data = _DPAPI_MARK + _dpapi(raw, True, self.entropy) if os.name == "nt" else _PLAIN_MARK + raw
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # owner only (as device.key)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def load(self):
        """The key, or None when there is none or it cannot be read here (e.g. the folder was copied to another PC)."""
        try:
            with open(self.path, "rb") as fh:
                data = fh.read()
        except OSError:
            return None
        try:
            if data.startswith(_DPAPI_MARK):
                return _dpapi(data[len(_DPAPI_MARK):], False, self.entropy).decode("ascii") if os.name == "nt" else None
            if data.startswith(_PLAIN_MARK):
                return data[len(_PLAIN_MARK):].decode("ascii")
        except (OSError, UnicodeDecodeError):
            return None
        return None

    def remove(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


# ---------------------------------------------------------------------- the registry, read only
class ReadOnlyRegistry:
    """What eco_publisher reads from the registry (`list`, `by_id`), through a read-only connection of its own.
    Opening hr_core.registry.Registry would open the journal too and may REPAIR (write) on open; the link never writes."""

    def __init__(self, data_dir, company_id):
        from .registry import ENTITIES
        self.entities, self.company_id = set(ENTITIES), company_id
        self.db = sqlite3.connect(Path(os.path.abspath(os.path.join(data_dir, "hr.db"))).as_uri() + "?mode=ro", uri=True)
        self.db.row_factory = sqlite3.Row

    def _entity(self, entity):
        if entity not in self.entities:
            raise ValueError(f"unknown entity {entity!r}")
        return entity

    @staticmethod
    def _row(row):
        if row is None:
            return None
        out = dict(row)
        if "attrs" in out:
            out["attrs"] = json.loads(out["attrs"]) if out["attrs"] else {}
        return out

    def list(self, entity, include_deleted=False):
        where = "" if include_deleted else "WHERE deleted = 0"
        return [self._row(r) for r in self.db.execute(f"SELECT * FROM {self._entity(entity)} {where} ORDER BY code")]

    def by_id(self, entity, gid):
        return self._row(self.db.execute(f"SELECT * FROM {self._entity(entity)} WHERE id = ?", (gid,)).fetchone())

    def close(self):
        self.db.close()


def outbox_counts(data_dir):
    path = os.path.join(data_dir, "eco_outbox.db")
    if not os.path.isfile(path):
        return {}
    db = sqlite3.connect(Path(os.path.abspath(path)).as_uri() + "?mode=ro", uri=True)
    try:
        return dict(db.execute("SELECT state, COUNT(*) FROM entity GROUP BY state").fetchall())
    except sqlite3.Error:
        return {}
    finally:
        db.close()


# ---------------------------------------------------------------------- the link
class EcoLink:
    def __init__(self, home, company_id, attendance, journal=None):
        self.home, self.company_id, self.attendance, self.journal = home, company_id, attendance, journal
        self.keys = KeyStore(home.data)
        self.last = None                 # the last cycle's report (in memory; the screen shows it)
        self.last_delivered_at = None    # the last cycle that sent something and GMES answered every batch
        self._cycle = threading.Lock()   # one cycle at a time: the thread's and "Send now"
        self._state = threading.Lock()
        self._thread, self._stop = None, None

    def settings(self):
        return self.home.config()["eco"]

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def status(self):
        """For the screen. NEVER the key: only whether one is stored and readable here."""
        cfg, key = self.settings(), self.keys.load()
        return {"gmes_url": cfg["gmes_url"], "node": cfg["node"], "interval_seconds": cfg["interval_seconds"],
                "enabled": bool(cfg["gmes_url"]), "key_set": key is not None,
                "key_unreadable": key is None and self.keys.exists(), "running": self.running,
                "last": self.last, "last_delivered_at": self.last_delivered_at, "outbox": outbox_counts(self.home.data)}

    # ------------------------------------------------------------------ the thread
    def start(self):
        """Start the background cycles when an address is set. False (and nothing started) when HR runs alone."""
        with self._state:
            if self.running:
                return True
            cfg = self.settings()
            if not cfg["gmes_url"]:
                return False
            stop = threading.Event()
            self._stop = stop
            self._thread = threading.Thread(target=self._loop, args=(stop,), name="hr-eco-link", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout=30):
        with self._state:
            thread, stop = self._thread, self._stop
            self._thread = self._stop = None
        if stop is not None:
            stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)  # a cycle in flight ends within the publisher's HTTP timeout

    def restart(self):
        self.stop()
        return self.start()

    def _loop(self, stop):
        while not stop.is_set():
            interval = 60
            try:
                interval = self.settings()["interval_seconds"]
                self.run_once("automatic")
            except Exception as exc:  # a cycle reports; it never ends the thread (the type only: a text may hold data)
                self._log({"at": _now(), "origin": "automatic", "error": type(exc).__name__})
            stop.wait(max(10, int(interval)))

    # ------------------------------------------------------------------ one cycle
    def run_once(self, origin="manual"):
        import eco_publisher  # compiled into the program (tools/build_windows.py); imported only when publishing
        with self._cycle:
            cfg, key = self.settings(), self.keys.load()
            if not cfg["gmes_url"]:
                raise LinkError("integration.disabled", "set the GMES address first: without it HR works on its own")
            report = {"at": _now(), "origin": origin}
            publisher = eco_publisher.Publisher(self.company_id, cfg["gmes_url"], key or "", cfg["node"], self.home.data)
            registry = None
            try:
                if os.path.isfile(os.path.join(self.home.data, "hr.db")):
                    registry = ReadOnlyRegistry(self.home.data, self.company_id)
                    publisher.registry = registry
                rows = self.attendance.engine.current_rows(force=True)
                report.update(publisher.run_once(rows))
            except (PermissionError, RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
                text = str(exc)
                if key:
                    text = text.replace(key, "***")  # an answer that echoes the key must not carry it further
                report["error"] = f"{type(exc).__name__}: {text}"[:500]
                try:
                    report["outbox"] = publisher.outbox.counts()
                except sqlite3.Error:
                    report["outbox"] = {}
            finally:
                if registry is not None:
                    registry.close()
                publisher.outbox.db.close()
            if not key:
                report["key_missing"] = True
            if report.get("sent") and "error" not in report and "stopped_by" not in report:
                self.last_delivered_at = report["at"]
            self.last = report
            if report.get("staged") or report.get("sent") or "error" in report or "stopped_by" in report:
                self._log(report)
            return report

    def _log(self, report):
        try:
            path = os.path.join(self.home.logs, LOG_FILE)
            if os.path.isfile(path) and os.path.getsize(path) > LOG_MAX:
                os.replace(path, path + ".1")
            line = {k: v for k, v in report.items() if k != "problems"}
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            pass

    # ------------------------------------------------------------------ settings from the screen
    def change(self, fields, actor, ip=None):
        """New settings and/or a new key, checked completely before anything is written; the link restarts with them.
        `key`: a new key (empty or absent = keep the stored one); `clear_key`: remove the stored key.
        Audited without the key: only whether it changed."""
        if not isinstance(fields, dict):
            raise HomeError("config.eco", "the integration settings are an object")
        allowed = {"gmes_url", "node", "interval_seconds", "key", "clear_key"}
        unknown = set(fields) - allowed
        if unknown:
            raise HomeError("config.field", f"not an integration setting: {sorted(unknown)[0]}")
        settings = {k: fields[k] for k in ("gmes_url", "node", "interval_seconds") if k in fields}
        new = self.home.check_eco(settings, self.settings())
        key = fields.get("key")
        key = None if key is None or key == "" else KeyStore.check(key)
        clear = bool(fields.get("clear_key"))
        if key is not None and clear:
            raise LinkError("integration.key", "either a new key or removing the key, not both")
        if key is not None:
            self.keys.save(key)
        elif clear:
            self.keys.remove()
        self.home.set(eco=new)
        detail = dict(new, key="changed" if key is not None else "removed" if clear else "unchanged")
        if self.journal is not None:
            self.journal.audit("security", "integration.changed", actor, detail, ip)
        self.restart()
        return self.status()
