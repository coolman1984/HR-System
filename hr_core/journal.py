"""HR-System's permanent journal and audit log (data/hr_journal.db) — phase 2.

One journal for every durable change (business data, users and profiles, devices), and one audit log
for security and activity events. Both are append-only (database triggers refuse UPDATE/DELETE) and
hash-chained in the ecosystem's unified format (ADR-026: SHA-256(domain LF canonical(line)), `prev`).

Signing (phase 2): every journal line written by a registered device carries an Ed25519 signature over
its hash (`hr_core.signing`: the standard `cryptography` library, else BAMS's reviewed implementation).
A device registers itself with a signed `device` line. Once any line is signed, an unsigned line after it
is a failure, so signatures cannot be silently stripped. Lines written before signing existed (phase 1)
keep their original, unchanged hashes.

Materialised stores (hr.db business tables, auth.db users) are folds of this journal; the journal is never
restored backwards. Standard library only.
"""

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone

from . import signing
from .canonical import GENESIS, canonical, line_hash

DOMAIN = "HR-JOURNAL1"
AUDIT_DOMAIN = "HR-AUDIT1"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def open_journal(data_dir):
    """The journal of this installation, signing as this installation's device (the normal way to open it)."""
    from .device import Device
    return Journal(data_dir, Device(data_dir))


class Journal:
    def __init__(self, data_dir, device=None):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "hr_journal.db")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode = WAL; PRAGMA synchronous = FULL;
            CREATE TABLE IF NOT EXISTS journal (
              seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, at TEXT NOT NULL, actor TEXT NOT NULL, label TEXT NOT NULL,
              ops TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL, sig TEXT);
            CREATE TRIGGER IF NOT EXISTS journal_no_update BEFORE UPDATE ON journal BEGIN SELECT RAISE(ABORT, 'hr: the journal is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS journal_no_delete BEFORE DELETE ON journal BEGIN SELECT RAISE(ABORT, 'hr: the journal is append-only'); END;
            CREATE TABLE IF NOT EXISTS audit (
              seq INTEGER PRIMARY KEY, at TEXT NOT NULL, category TEXT NOT NULL, event TEXT NOT NULL, actor TEXT NOT NULL,
              ip TEXT, detail TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit BEGIN SELECT RAISE(ABORT, 'hr: the audit log is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit BEGIN SELECT RAISE(ABORT, 'hr: the audit log is append-only'); END;
        """)
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(journal)")}
        for col in ("kind", "device"):  # phase-1 journals get the new columns; old lines keep NULL
            if col not in cols:
                self.db.execute(f"ALTER TABLE journal ADD COLUMN {col} TEXT")
        self.db.commit()
        self.device = device
        if device is not None and not self._device_registered(device.device_id):
            self.append("device:" + device.name, f"Device registered: {device.name}",
                        [{"entity": "device", "row": {"id": device.device_id, "name": device.name, "public_key": device.public_hex, "machine": device.machine}}],
                        kind="device")

    # ------------------------------------------------------------------ journal
    @staticmethod
    def _line(row, ops):
        line = {"seq": row["seq"], "id": row["id"], "at": row["at"], "actor": row["actor"], "label": row["label"], "ops": ops, "prev": row["prev"]}
        if row["kind"]:
            line["kind"] = row["kind"]
        if row["device"]:
            line["device"] = row["device"]
        return line

    def append(self, actor, label, ops, kind="data"):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")  # serialises writers across connections and processes
            try:
                last = self.db.execute("SELECT seq, hash FROM journal ORDER BY seq DESC LIMIT 1").fetchone()
                seq, prev = (last["seq"] + 1, last["hash"]) if last else (1, GENESIS)
                row = {"seq": seq, "id": str(uuid.uuid4()), "at": now(), "actor": actor, "label": label, "prev": prev,
                       "kind": kind, "device": self.device.device_id if self.device else None}
                h = line_hash(DOMAIN, self._line(row, ops))
                sig = self.device.sign(bytes.fromhex(h)).hex() if self.device else None
                self.db.execute("INSERT INTO journal (seq, id, at, actor, label, ops, prev, hash, sig, kind, device) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (seq, row["id"], row["at"], actor, label, canonical(ops), prev, h, sig, kind, row["device"]))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
            return seq

    def hash_at(self, seq):
        row = self.db.execute("SELECT hash FROM journal WHERE seq = ?", (seq,)).fetchone()
        return row[0] if row else None

    def follows(self, applied_seq, applied_hash):
        """True when a store that folded up to (applied_seq, applied_hash) is a prefix of this journal. False when
        the journal is behind it or has a different line there (the journal was restored from an older backup)."""
        if applied_seq == 0:
            return True
        at = self.hash_at(applied_seq)
        return at is not None and (applied_hash is None or at == applied_hash)

    def last_seq(self):
        row = self.db.execute("SELECT MAX(seq) FROM journal").fetchone()
        return row[0] or 0

    def lines_after(self, seq):
        return [(r["seq"], r["kind"] or "data", json.loads(r["ops"])) for r in self.db.execute("SELECT seq, kind, ops FROM journal WHERE seq > ? ORDER BY seq", (seq,))]

    def _device_registered(self, device_id):
        for r in self.db.execute("SELECT ops FROM journal WHERE kind = 'device'"):
            if any(o["row"]["id"] == device_id for o in json.loads(r["ops"])):
                return True
        return False

    def verify(self):
        """Chain, hashes and signatures of every line. Names the first bad line and why."""
        prev, expect, devices, signed_from = GENESIS, 1, {}, None
        rows = self.db.execute("SELECT * FROM journal ORDER BY seq").fetchall()

        def bad(r, why):
            return {"ok": False, "lines": len(rows), "first_bad_seq": r["seq"], "reason": why, "last_hash": prev, "signed_from": signed_from}

        for r in rows:
            ops = json.loads(r["ops"])
            if r["seq"] != expect or r["prev"] != prev:
                return bad(r, "chain broken (sequence or previous hash)")
            if line_hash(DOMAIN, self._line(r, ops)) != r["hash"]:
                return bad(r, "content does not match its hash")
            if r["kind"] == "device":
                for o in ops:
                    devices.setdefault(o["row"]["id"], bytes.fromhex(o["row"]["public_key"]))
            if r["device"]:
                pub = devices.get(r["device"])
                if pub is None:
                    return bad(r, f"signed by an unknown device {r['device']}")
                if not r["sig"] or not signing.verify(pub, bytes.fromhex(r["hash"]), bytes.fromhex(r["sig"])):
                    return bad(r, "signature does not verify")
                signed_from = signed_from or r["seq"]
            elif signed_from is not None:
                return bad(r, "unsigned line after signing began (signature stripped?)")
            prev, expect = r["hash"], expect + 1
        return {"ok": True, "lines": len(rows), "first_bad_seq": None, "reason": None, "last_hash": prev, "signed_from": signed_from}

    # ------------------------------------------------------------------ audit
    def audit(self, category, event, actor, detail=None, ip=None):
        """category: security | activity | system. Never pass passwords, tokens or keys in detail."""
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                last = self.db.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
                seq, prev = (last["seq"] + 1, last["hash"]) if last else (1, GENESIS)
                entry = {"seq": seq, "at": now(), "category": category, "event": event, "actor": actor or "-", "ip": ip, "detail": detail or {}, "prev": prev}
                h = line_hash(AUDIT_DOMAIN, entry)
                self.db.execute("INSERT INTO audit (seq, at, category, event, actor, ip, detail, prev, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (seq, entry["at"], category, event, entry["actor"], ip, canonical(entry["detail"]), prev, h))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def audit_entries(self, category=None, limit=200):
        where, args = ("WHERE category = ?", (category,)) if category else ("", ())
        rows = self.db.execute(f"SELECT * FROM audit {where} ORDER BY seq DESC LIMIT ?", (*args, limit)).fetchall()
        return [dict(r, detail=json.loads(r["detail"])) for r in rows]

    def verify_audit(self):
        prev, expect = GENESIS, 1
        rows = self.db.execute("SELECT * FROM audit ORDER BY seq").fetchall()
        for r in rows:
            entry = {"seq": r["seq"], "at": r["at"], "category": r["category"], "event": r["event"], "actor": r["actor"], "ip": r["ip"],
                     "detail": json.loads(r["detail"]), "prev": r["prev"]}
            if r["seq"] != expect or r["prev"] != prev or line_hash(AUDIT_DOMAIN, entry) != r["hash"]:
                return {"ok": False, "entries": len(rows), "first_bad_seq": r["seq"]}
            prev, expect = r["hash"], expect + 1
        return {"ok": True, "entries": len(rows), "first_bad_seq": None}

    def close(self):
        self.db.close()
