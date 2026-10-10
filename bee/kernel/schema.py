"""Minimal JSON-Schema (draft-07 subset) validator for ToolBus arguments.

The ToolBus must validate tool arguments against the REGISTERED schema before
executing a handler — checking only "args is a dict" lets unknown keys,
missing required keys and wrong types straight through to privileged handlers.

This is deliberately NOT a full JSON-Schema implementation: it covers exactly
the subset the registered tool schemas use (type / object+properties+required+
additionalProperties / items / enum / anyOf / minLength / minimum / maximum).
Unrecognized keywords are ignored; every keyword we DO enforce is checked
before the handler runs (the caller converts violations into
MalformedArgsError, so a violation means "not executed").
"""
from __future__ import annotations


def _type_ok(value, t: str) -> bool:
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return True


def _check(value, schema, path: str, errors: list[str]) -> None:
    if not isinstance(schema, dict) or not schema:
        return
    t = schema.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_type_ok(value, x) for x in ts):
            errors.append(f"{path or '$'}: expected type {ts}, got {type(value).__name__}")
            return  # deeper checks on a wrongly-typed value are noise
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path or '$'}: {value!r} is not one of {schema['enum']}")
    if "anyOf" in schema:
        branches = schema["anyOf"]
        if not any((_check(value, b, path, tmp := []) or not tmp) for b in branches):
            errors.append(f"{path or '$'}: matches none of the anyOf branches")
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req not in value:
                errors.append(f"{path or '$'}: missing required argument '{req}'")
        ap = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                _check(v, props[k], f"{path}.{k}" if path else k, errors)
            elif ap is False:
                errors.append(f"{path or '$'}: unknown argument '{k}'")
            elif isinstance(ap, dict):
                _check(v, ap, f"{path}.{k}" if path else k, errors)
    if isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, el in enumerate(value):
                _check(el, items, f"{path}[{i}]", errors)
    if isinstance(value, str) and "minLength" in schema \
            and len(value) < int(schema["minLength"]):
        errors.append(f"{path or '$'}: shorter than minLength {schema['minLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path or '$'}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path or '$'}: {value} > maximum {schema['maximum']}")


def validate_args(args, schema: dict) -> list[str]:
    """Return a list of human-readable violations ([] means valid)."""
    errors: list[str] = []
    _check(args, schema or {}, "", errors)
    return errors
