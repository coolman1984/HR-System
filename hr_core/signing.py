"""Ed25519 signing for the HR journal, with ONE preferred standard implementation and ONE reviewed fallback.

Order (ADR-HR-002, docs/HR_SECURITY.md):
1. `cryptography` (PyCA, OpenSSL) — the well-established standard library, used whenever it can be imported.
   The offline Windows package will bundle it with an embedded Python runtime (one build per architecture);
   with the customer's own Python of any version it would need a separate compiled `cffi` per version × architecture.
2. `hr_core/vendor/ed25519_bams.py` — BAMS's pure-Python RFC 8032 implementation, byte-for-byte, never edited.

Ed25519 is deterministic: both produce the SAME signature for the same key and message, so a journal signed by one
is verified by the other (tested both ways). HR_SIGNING_BACKEND=cryptography|bams forces a backend (tests, diagnosis).
Standard library only at import time.
"""

import os

_forced = os.environ.get("HR_SIGNING_BACKEND", "").strip().lower()


def _load_cryptography():
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

    raw = serialization.Encoding.Raw

    def public_key(seed):
        return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(raw, serialization.PublicFormat.Raw)

    def sign(seed, msg):
        return Ed25519PrivateKey.from_private_bytes(seed).sign(msg)

    def verify(pub, msg, sig):
        try:
            Ed25519PublicKey.from_public_bytes(pub).verify(sig, msg)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    return "cryptography", public_key, sign, verify


def _load_bams():
    from .vendor import ed25519_bams as e

    return "bams-ed25519", e.public_key, e.sign, e.verify


# RFC 8032 §7.1 test 1: a backend is used only after it reproduces this exactly.
_SELFTEST = ("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
             "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
             "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b")
PROBLEMS = []  # why a backend was not used (shown by health checks)


def _accept(loader):
    """Load a backend and prove it with the RFC vector. A broken install of `cryptography` can fail with
    ImportError, OSError or even a Rust panic (pyo3 PanicException, a BaseException) — observed on a machine
    whose cffi backend was missing — so everything except an interrupt is caught and recorded."""
    try:
        name, pk, sg, vf = loader()
        seed, pub, sig = (bytes.fromhex(x) for x in _SELFTEST)
        if pk(seed) != pub or sg(seed, b"") != sig or not vf(pub, b"", sig) or vf(pub, b"x", sig):
            raise RuntimeError("failed the RFC 8032 self-test")
        return name, pk, sg, vf
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:  # noqa: BLE001 — see docstring
        PROBLEMS.append(f"{loader.__name__}: {type(exc).__name__}: {str(exc)[:200]}")
        return None


if _forced == "bams":
    _chosen = _accept(_load_bams)
elif _forced == "cryptography":
    _chosen = _accept(_load_cryptography)
else:
    _chosen = _accept(_load_cryptography) or _accept(_load_bams)
if _chosen is None:
    raise ImportError("no working Ed25519 backend: " + "; ".join(PROBLEMS))
BACKEND, _public_key, _sign, _verify = _chosen


def generate_seed():
    return os.urandom(32)


def public_key(seed):
    return _public_key(seed)


def sign(seed, msg):
    return _sign(seed, msg)


def verify(pub, msg, sig):
    return bool(_verify(pub, msg, sig))
