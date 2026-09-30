"""Request signing for machine calls (plan 50 WP-X2): a signature over METHOD|path?query|sha256(body)|timestamp.

The HMAC key is the SHA-256 of the machine key (hex): receivers keep only that hash, so both sides can compute it. A signature
older than five minutes, or made for another method, path or body, is refused. Additive: an unsigned request is still accepted
unless ECO_REQUIRE_SIGNATURE=1. Real time, never the simulated day: this is about the wire.
The same algorithm is in Mizan (modules/eco/signing.ts) and GMES (kernel/signing.ts); all three tests pin the same vector.
Standard library only.
"""

import hashlib
import hmac
import re
import time

WINDOW_MS = 5 * 60_000


def sha256hex(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def sign_request(key_hash, method, path_with_query, body, timestamp):
    text = f"{method.upper()}|{path_with_query}|{sha256hex(body)}|{timestamp}"
    return hmac.new(key_hash.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def signature_headers(key, method, path_with_query, body, now_ms=None):
    now = int(time.time() * 1000) if now_ms is None else now_ms
    return {"x-eco-ts": str(now), "x-eco-sig": sign_request(sha256hex(key), method, path_with_query, body, now)}


def check_signature(key_hash, method, path_with_query, raw_body, ts, sig, required, now_ms=None):
    """None when the request is acceptable; otherwise the reason (a code)."""
    if ts is None and sig is None:
        return "auth.signature_required" if required else None
    if not isinstance(ts, str) or not isinstance(sig, str) or not re.fullmatch(r"\d{10,16}", ts) or not re.fullmatch(r"[0-9a-f]{64}", sig):
        return "auth.signature_malformed"
    now = int(time.time() * 1000) if now_ms is None else now_ms
    if abs(now - int(ts)) > WINDOW_MS:
        return "auth.signature_expired"
    want = sign_request(key_hash, method, path_with_query, raw_body, int(ts))
    return None if hmac.compare_digest(want, sig) else "auth.signature_invalid"
