#!/usr/bin/env python3
"""The task-packet schema, and a checker for the subset of JSON Schema it uses.

This lived inside ``tests/test_task_packet_schema.py``, which meant it ran over
committed packets at test time and never over the packet being dispatched.
``hybrid_dispatch.py`` listed ``packet-schema-valid`` among the pre-gates it
reported satisfied and compared the packet against nothing, so the V6-K packet
was frozen with ``debt`` as a string -- the schema requires an array -- reported
``status: fit``, and was dispatched twice on that basis.

It is promoted here so the dispatch path and the test suite use one checker.

There is no ``jsonschema`` on this host, so the checker is hand-written. That is
survivable only if it refuses to be quietly incomplete: ``unsupported_keywords``
walks a schema and returns every keyword this module does not implement, and
``check_schema_is_supported`` raises on the first one. A checker that skips a
keyword it does not know reports "valid" for a document it never checked, which
is the failure this module exists to end -- so the honesty is enforced rather
than requested in a docstring.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "hybrid" / "task-packet.schema.json"

_TYPES: dict[str, Any] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}

#: Keywords ``validate`` implements. Anything outside this set is a keyword the
#: schema author wrote and this checker would silently ignore.
SUPPORTED_KEYWORDS = frozenset({
    "type", "required", "properties", "additionalProperties", "items",
    "enum", "const", "pattern", "minLength", "minimum", "maximum",
    "minItems", "maxItems", "uniqueItems",
    # The version-conditional half of the schema. Before the coverage guard
    # existed these were ignored outright, so the v1/v2 acceptance-property
    # shapes and v3's required action_class were declared in the schema and
    # enforced by nothing that reads it.
    "allOf", "anyOf", "oneOf", "not", "if", "then", "else", "$ref", "$defs",
})

#: Keywords that carry no constraint and are safe to pass over: annotations and
#: the document's own identity.
ANNOTATION_KEYWORDS = frozenset({
    "$schema", "$id", "title", "description", "default", "examples", "comment",
    "$comment", "deprecated",
})


class SchemaCoverageError(ValueError):
    """The schema uses a keyword this checker does not implement."""


def load_schema(path: Path = SCHEMA_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


#: Keywords whose value is a map of name -> subschema.
_SUBSCHEMA_MAPS = frozenset({"properties", "$defs"})
#: Keywords whose value is a single subschema.
_SUBSCHEMA_SINGLE = frozenset({"items", "if", "then", "else", "not", "additionalProperties"})
#: Keywords whose value is a list of subschemas.
_SUBSCHEMA_LISTS = frozenset({"allOf", "anyOf", "oneOf"})


def unsupported_keywords(schema: Any, path: str = "$") -> list[str]:
    """Every ``path: keyword`` in ``schema`` that ``validate`` would ignore."""
    found: list[str] = []
    if not isinstance(schema, dict):
        return found
    for key, value in schema.items():
        if key in ANNOTATION_KEYWORDS:
            continue
        if key not in SUPPORTED_KEYWORDS:
            found.append(f"{path}: {key}")
            continue
        if key in _SUBSCHEMA_MAPS and isinstance(value, dict):
            for name, child in value.items():
                found.extend(unsupported_keywords(child, f"{path}.{key}.{name}"))
        elif key in _SUBSCHEMA_SINGLE and isinstance(value, dict):
            found.extend(unsupported_keywords(value, f"{path}.{key}"))
        elif key in _SUBSCHEMA_LISTS and isinstance(value, list):
            for index, child in enumerate(value):
                found.extend(unsupported_keywords(child, f"{path}.{key}[{index}]"))
    return found


def check_schema_is_supported(schema: dict[str, Any]) -> None:
    """Raise unless every keyword in ``schema`` is one ``validate`` implements."""
    unsupported = unsupported_keywords(schema)
    if unsupported:
        raise SchemaCoverageError(
            "task-packet.schema.json uses keywords this checker does not "
            "implement, so a packet could pass without being checked against "
            "them: " + ", ".join(sorted(unsupported))
        )


def _resolve(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local ``#/$defs/name`` pointer. Remote refs are not supported."""
    if not ref.startswith("#/"):
        raise SchemaCoverageError(f"only local $ref is supported, got {ref!r}")
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaCoverageError(f"$ref {ref!r} does not resolve")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaCoverageError(f"$ref {ref!r} is not a schema")
    return node


def validate(
    instance: Any,
    schema: dict[str, Any],
    path: str = "$",
    root: dict[str, Any] | None = None,
) -> list[str]:
    """Return a list of human-readable violations.

    Covers only the constructs the packet schema actually uses; see
    ``SUPPORTED_KEYWORDS``, which ``check_schema_is_supported`` holds to the
    schema so the two cannot drift apart in silence.
    """
    errors: list[str] = []
    if root is None:
        root = schema
    if "$ref" in schema:
        return validate(instance, _resolve(schema["$ref"], root), path, root)
    expected = schema.get("type")
    if expected:
        wanted = _TYPES[expected]
        # bool is an int in Python; the schema means them separately.
        if expected == "integer" and isinstance(instance, bool):
            errors.append(f"{path}: expected integer, got boolean")
            return errors
        if not isinstance(instance, wanted):
            errors.append(
                f"{path}: expected {expected}, got {type(instance).__name__}")
            return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")
    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if pattern and not re.match(pattern, instance):
            errors.append(f"{path}: {instance!r} does not match {pattern}")
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < min_length:
            errors.append(f"{path}: shorter than minLength {min_length}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: {instance} below minimum {minimum}")
        maximum = schema.get("maximum")
        if maximum is not None and instance > maximum:
            errors.append(f"{path}: {instance} above maximum {maximum}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate(value, properties[key], f"{path}.{key}", root))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {key!r} is not allowed")
    if isinstance(instance, list):
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                errors.extend(validate(item, item_schema, f"{path}[{index}]", root))
        if schema.get("uniqueItems"):
            hashable = [json.dumps(i, sort_keys=True) for i in instance]
            if len(set(hashable)) != len(hashable):
                errors.append(f"{path}: items are not unique")
        min_items = schema.get("minItems")
        if min_items is not None and len(instance) < min_items:
            errors.append(f"{path}: has {len(instance)} items, minItems {min_items}")
        max_items = schema.get("maxItems")
        if max_items is not None and len(instance) > max_items:
            errors.append(f"{path}: has {len(instance)} items, maxItems {max_items}")

    for index, subschema in enumerate(schema.get("allOf", [])):
        errors.extend(validate(instance, subschema, f"{path}/allOf[{index}]", root))
    any_of = schema.get("anyOf")
    if any_of and all(validate(instance, s, path, root) for s in any_of):
        errors.append(f"{path}: matches none of the anyOf branches")
    one_of = schema.get("oneOf")
    if one_of is not None:
        matched = sum(1 for s in one_of if not validate(instance, s, path, root))
        if matched != 1:
            errors.append(f"{path}: matches {matched} oneOf branches, expected 1")
    if "not" in schema and not validate(instance, schema["not"], path, root):
        errors.append(f"{path}: matches a schema it must not match")
    if "if" in schema:
        branch = "then" if not validate(instance, schema["if"], path, root) else "else"
        if branch in schema:
            errors.extend(validate(instance, schema[branch], f"{path}/{branch}", root))
    return errors


def validate_against_packet_schema(packet: dict[str, Any]) -> list[str]:
    """Check ``packet`` against the committed schema, coverage first."""
    schema = load_schema()
    check_schema_is_supported(schema)
    return validate(packet, schema)
