"""Where one installation lives, and which company it belongs to (phase 2.5, docs/HR_DELIVERY.md).

  <home>/config.json     settings and the company identity (never inside the program folder)
  <home>/data/           journal, business tables, accounts, attendance history, device identity
  <home>/backups/        verified backups (pre-update backups are kept forever)
  <home>/recovery/       the last known-good installer, with its version and SHA-256
  <home>/logs/

The installed program uses %ProgramData%\\HR-System, so updating or removing the program never touches the data.
HR_HOME points somewhere else (tests, a second installation).

Company identity (ADR-HR-006): the company id is the namespace of every shared id, so it is set once and never
changed silently. It comes from the application that owns the company (Mizan) when there is one ("owner"); a
standalone HR creates a local one, marked provisional ("local"). Adopting an owner's identity later is an explicit
step (planned), never an edit of config.json: a registry built for one company refuses to open under another.
Standard library only.
"""

import json
import os
import re
import secrets
import sys
import time
import uuid

CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,19}$")
SOURCES = ("owner", "local")
OWNER_APPS = ("mizan",)
DEFAULTS = {"host": "127.0.0.1", "port": 8766, "autostart": True, "language": "en", "backup_hours": 6}


class HomeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def installed():
    """True inside the compiled program (Nuitka sets __compiled__ on every module; frozen tools set sys.frozen)."""
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def default_home():
    if os.environ.get("HR_HOME"):
        return os.path.abspath(os.environ["HR_HOME"])
    if installed():
        base = os.environ.get("ProgramData") or os.environ.get("ALLUSERSPROFILE") or os.path.expanduser("~")
        return os.path.join(base, "HR-System")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hr-home")


def uuid7():
    """A time-ordered UUID (RFC 9562 v7), the ecosystem's form for a new company id (GMES identity map E4.2)."""
    ms = int(time.time() * 1000)
    raw = ms.to_bytes(6, "big") + secrets.token_bytes(10)
    b = bytearray(raw)
    b[6] = (b[6] & 0x0F) | 0x70
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


class Home:
    def __init__(self, path=None):
        self.path = os.path.abspath(path or default_home())
        self.data = os.path.join(self.path, "data")
        self.backups = os.path.join(self.path, "backups")
        self.recovery = os.path.join(self.path, "recovery")
        self.logs = os.path.join(self.path, "logs")
        self.config_path = os.path.join(self.path, "config.json")
        for d in (self.path, self.data, self.backups, self.recovery, self.logs):
            os.makedirs(d, exist_ok=True)

    # ------------------------------------------------------------------ settings
    def config(self):
        try:
            with open(self.config_path, encoding="utf-8") as fh:
                stored = json.load(fh)
        except FileNotFoundError:
            stored = {}
        except ValueError as exc:
            raise HomeError("config.unreadable", f"{self.config_path} is not valid JSON ({exc}); fix or remove it") from None
        return {**DEFAULTS, **stored}

    def _write(self, cfg):
        tmp = self.config_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({k: v for k, v in cfg.items()}, fh, indent=1, sort_keys=True)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.config_path)  # never a half-written settings file

    def set(self, **changes):
        allowed = {"autostart", "language", "backup_hours", "port", "host"}
        unknown = set(changes) - allowed
        if unknown:
            raise HomeError("config.field", f"not a setting: {sorted(unknown)[0]}")
        if "language" in changes and changes["language"] not in ("en", "ar"):
            raise HomeError("config.language", "language is en or ar")
        if "backup_hours" in changes:
            try:
                changes["backup_hours"] = int(changes["backup_hours"])
            except (TypeError, ValueError):
                raise HomeError("config.backup_hours", "the backup interval is a whole number of hours") from None
            if not 1 <= changes["backup_hours"] <= 168:
                raise HomeError("config.backup_hours", "the backup interval is 1 to 168 hours")
        if "autostart" in changes:
            changes["autostart"] = bool(changes["autostart"])
        cfg = self.config()
        cfg.update(changes)
        self._write(cfg)
        return cfg

    # ------------------------------------------------------------------ company identity
    def company(self):
        return self.config().get("company")

    def set_company(self, source, code, name, company_id=None, owner_app=None):
        """Once only. `owner`: the id comes from the application that owns the company (Mizan). `local`: a new
        provisional id for a standalone HR."""
        if self.company():
            raise HomeError("company.set", "this installation already belongs to a company; its identity never changes silently")
        if source not in SOURCES:
            raise HomeError("company.source", "the company identity comes from its owner application or is created locally")
        code, name = (code or "").strip().upper(), (name or "").strip()
        if not CODE.match(code):
            raise HomeError("company.code", "company code: 1-20 capital letters, digits, dash or underscore")
        if not name:
            raise HomeError("company.name", "the company name is required")
        if source == "owner":
            if owner_app not in OWNER_APPS:
                raise HomeError("company.owner", f"the owner application is one of {', '.join(OWNER_APPS)}")
            try:
                company_id = str(uuid.UUID(company_id or ""))
            except ValueError:
                raise HomeError("company.id", "paste the company id exactly as the owner application shows it") from None
        else:
            company_id, owner_app = uuid7(), None
        cfg = self.config()
        cfg["company"] = {"id": company_id, "code": code, "name": name, "source": source, "owner_app": owner_app,
                          "provisional": source == "local", "set_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self._write(cfg)
        return cfg["company"]
