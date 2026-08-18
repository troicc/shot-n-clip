"""Minimal JSON Schema (draft-07 subset) validator — no external dependency.

Supports the keywords used by schemas/v2/*.json: type, required,
additionalProperties, properties, items, enum, const, minLength, minItems,
maxItems, minimum, maximum, pattern. Returns field-level error strings.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool,
    "number": (int, float), "integer": int,
}


def _type_ok(value: Any, t: str) -> bool:
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    py = _TYPES.get(t)
    if py is None:
        return True
    if t == "string":
        return isinstance(value, str)
    return isinstance(value, py)


def validate(instance: Any, schema: dict, path: str = "$",
             errors: Optional[List[str]] = None) -> List[str]:
    if errors is None:
        errors = []
    if not isinstance(schema, dict):
        return errors

    # const
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
        return errors

    # enum
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
        return errors

    # type (may be a list — nullable unions)
    types = schema.get("type")
    if types is not None:
        candidates = types if isinstance(types, list) else [types]
        if isinstance(instance, NoneType) and "null" not in candidates:
            errors.append(f"{path}: null not allowed (type={candidates})")
            return errors
        if not any(instance is None and c == "null" or
                   (instance is not None and _type_ok(instance, c))
                   for c in candidates):
            errors.append(f"{path}: expected type {candidates}, got "
                          f"{type(instance).__name__}")
            return errors
    if instance is None:
        return errors

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match pattern "
                          f"{schema['pattern']!r}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} > maximum {schema['maximum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: {len(instance)} items < minItems "
                          f"{schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: {len(instance)} items > maxItems "
                          f"{schema['maxItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                validate(item, item_schema, f"{path}[{i}]", errors)

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required field '{key}'")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    errors.append(f"{path}: unexpected field '{key}'")
        for key, sub in props.items():
            if key in instance:
                validate(instance[key], sub, f"{path}.{key}", errors)

    return errors


NoneType = type(None)


def validate_file(data: Any, schema_path: str) -> List[str]:
    import json
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)
    return validate(data, schema)
