"""Eco canonical JSON v1 and journal-line hashing (GMES docs/ecosystem/08 F1, ADR-026).

Same definition as BAMS and as @eco/contracts in TypeScript; the shared vectors in
eco_schemas/canonical-v1.json prove all three agree byte for byte.
"""

import hashlib
import json

GENESIS = "0" * 64


def _check(value, path="$"):
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        if abs(value) > 9007199254740991:
            raise ValueError(f"{path}: integer outside the safe range")
        return
    if isinstance(value, float):
        raise ValueError(f"{path}: canonical JSON carries integers only, got {value!r}")
    if isinstance(value, list):
        for i, item in enumerate(value):
            _check(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: keys must be text")
            _check(item, f"{path}.{key}")
        return
    raise ValueError(f"{path}: {type(value).__name__} is not representable in canonical JSON")


def canonical(value):
    _check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def line_hash(domain, line):
    return hashlib.sha256((domain + "\n" + canonical(line)).encode("utf-8")).hexdigest()
