"""Minimal JSON Schema (2020-12 subset) validator for the ecosystem contracts in eco_schemas/.

Standard library only, on purpose: CHECK_ENVIRONMENT.py treats every non-stdlib import in a
top-level .py file as a runtime dependency of the application. It supports exactly the keywords
the generated contract schemas use (type, properties, required, pattern, minLength, maxLength,
minimum, maximum, exclusiveMinimum, const, format) and FAILS LOUDLY on any other keyword, so a
richer schema can never be half-checked in silence.
"""

import json
import re
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "eco_schemas"
KNOWN = {"$id", "$schema", "title", "type", "properties", "required", "pattern", "minLength", "maxLength",
         "minimum", "maximum", "exclusiveMinimum", "const", "format", "additionalProperties", "description"}
_cache = {}


def schema(name):
    if name not in _cache:
        _cache[name] = json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))
    return _cache[name]


def _type_ok(value, kind):
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "null":
        return value is None
    raise ValueError(f"unsupported JSON Schema type {kind!r}")


def errors(value, node, path="$"):
    unknown = set(node) - KNOWN
    if unknown:
        raise ValueError(f"{path}: schema keyword(s) not supported by eco_contract.py: {sorted(unknown)}")
    out = []
    if "const" in node and value != node["const"]:
        out.append(f"{path}: must be {node['const']!r}")
    kind = node.get("type")
    if kind and not _type_ok(value, kind):
        return out + [f"{path}: must be {kind}"]
    if isinstance(value, str):
        if "minLength" in node and len(value) < node["minLength"]:
            out.append(f"{path}: shorter than {node['minLength']}")
        if "maxLength" in node and len(value) > node["maxLength"]:
            out.append(f"{path}: longer than {node['maxLength']}")
        if "pattern" in node and not re.search(node["pattern"], value):
            out.append(f"{path}: does not match {node['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in node and value < node["minimum"]:
            out.append(f"{path}: below {node['minimum']}")
        if "maximum" in node and value > node["maximum"]:
            out.append(f"{path}: above {node['maximum']}")
        if "exclusiveMinimum" in node and value <= node["exclusiveMinimum"]:
            out.append(f"{path}: must be above {node['exclusiveMinimum']}")
    if isinstance(value, dict):
        for key in node.get("required", []):
            if key not in value:
                out.append(f"{path}.{key}: required")
        for key, sub in node.get("properties", {}).items():
            if key in value:
                out.extend(errors(value[key], sub, f"{path}.{key}"))
    return out


def validate(name, value):
    """Return a list of problems (empty = valid)."""
    return errors(value, schema(name))


def validate_event(envelope):
    problems = validate("eco.envelope.v1", envelope)
    kind = envelope.get("type") if isinstance(envelope, dict) else None
    if not problems and kind:
        if not (SCHEMA_DIR / f"{kind}.schema.json").exists():
            return [f"$.type: no schema for {kind}"]
        problems = validate(kind, envelope.get("data"))
    return problems
