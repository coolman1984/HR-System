"""Device identity (phase 2), after BAMS's node identity: every installation has its own id and Ed25519 key.

data/node/device.json  — id, name, public key, machine fingerprint (not secret)
data/node/device.key   — the 32-byte private seed (file mode 0600; never in routine backups, never logged)

Clone detection: if the data folder is copied to another machine, the machine fingerprint differs; the copy
then gets a NEW device identity (its own key), so two machines never sign as the same device. The old identity
is kept in device.json as `previous` for the record.
Standard library only.
"""

import hashlib
import json
import os
import platform
import socket
import uuid

from . import signing


def machine_fingerprint():
    return hashlib.sha256(f"{socket.gethostname()}|{uuid.getnode():012x}|{platform.system()}".encode()).hexdigest()[:32]


def _write_private(path, data):
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class Device:
    def __init__(self, data_dir, name=None, machine=None):
        self.dir = os.path.join(data_dir, "node")
        os.makedirs(self.dir, exist_ok=True)
        self.info_path, self.key_path = os.path.join(self.dir, "device.json"), os.path.join(self.dir, "device.key")
        machine = machine or machine_fingerprint()
        self.cloned_from = None
        if os.path.exists(self.info_path) and os.path.exists(self.key_path):
            info = json.load(open(self.info_path, encoding="utf-8"))
            if info["machine"] != machine:  # the folder was copied to another machine
                self.cloned_from = info["device_id"]
                self._create(name or info["name"] + " (copy)", machine, previous=info)
            else:
                self.info, self.seed = info, open(self.key_path, "rb").read()
        else:
            self._create(name or socket.gethostname(), machine)
        if signing.public_key(self.seed).hex() != self.info["public_key"]:
            raise RuntimeError("device key does not match device.json; refusing to sign as this device")

    def _create(self, name, machine, previous=None):
        self.seed = signing.generate_seed()
        self.info = {"device_id": str(uuid.uuid4()), "name": name, "public_key": signing.public_key(self.seed).hex(), "machine": machine}
        if previous:
            self.info["previous"] = {k: previous[k] for k in ("device_id", "name", "machine")}
        _write_private(self.key_path, self.seed)
        with open(self.info_path + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(self.info, fh, indent=1)
        os.replace(self.info_path + ".tmp", self.info_path)

    @property
    def device_id(self):
        return self.info["device_id"]

    @property
    def name(self):
        return self.info["name"]

    @property
    def public_hex(self):
        return self.info["public_key"]

    @property
    def machine(self):
        return self.info["machine"]

    def sign(self, message):
        return signing.sign(self.seed, message)
