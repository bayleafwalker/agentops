"""A hand-rolled JSON Schema subset checker, importable by scripts.

Extracted from ``templates/dispatch/tests/test_task_packet_schema.py`` so that
more than one consumer can reach it without copying it. The public surface is
exactly four names:

* ``validate(instance, schema, path="$")`` -> a list of human-readable
  violation strings, empty when the instance satisfies the schema;
* ``UnsupportedKeyword``, an Exception;
* ``SUPPORTED_KEYWORDS`` and ``ANNOTATION_KEYWORDS``, two disjoint non-empty
  frozensets.

A schema keyword that is neither enforced (``SUPPORTED_KEYWORDS``) nor
knowingly constraint-free (``ANNOTATION_KEYWORDS``) raises
``UnsupportedKeyword``, naming the keyword. A supported keyword in a form this
checker does not enforce raises the same way. The audit is eager: it walks the
whole schema, so a subschema no instance reaches still raises.
"""
from __future__ import annotations

import json
import re

SUPPORTED_KEYWORDS = frozenset({
    "type", "required", "properties", "additionalProperties", "items",
    "enum", "const", "pattern", "minLength", "minimum", "uniqueItems",
})

ANNOTATION_KEYWORDS = frozenset({
    "$schema", "$id", "title", "description", "default", "examples",
    "deprecated", "format", "$comment",
})


class UnsupportedKeyword(Exception):
    """A schema keyword (or form) this checker does not enforce."""


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}


def _audit_schema(schema, path):
    """Walk the whole schema eagerly, raising on anything unenforceable."""
    if isinstance(schema, bool):
        raise UnsupportedKeyword(f"{path}: boolean schema is not supported")
    if not isinstance(schema, dict):
        raise UnsupportedKeyword(
            f"{path}: schema must be an object, got {type(schema).__name__}")
    for keyword, value in schema.items():
        if keyword in ANNOTATION_KEYWORDS:
            continue
        if keyword not in SUPPORTED_KEYWORDS:
            raise UnsupportedKeyword(f"{path}: unsupported keyword {keyword!r}")
        if keyword == "type":
            if not isinstance(value, str):
                raise UnsupportedKeyword(
                    f"{path}: type as a union list is not supported")
        elif keyword == "additionalProperties":
            if not isinstance(value, bool):
                raise UnsupportedKeyword(
                    f"{path}: additionalProperties as a subschema is not supported")
        elif keyword == "items":
            if isinstance(value, list):
                raise UnsupportedKeyword(
                    f"{path}: items as a positional list is not supported")
            _audit_schema(value, f"{path}.items")
        elif keyword == "properties":
            for prop_name, prop_schema in value.items():
                _audit_schema(prop_schema, f"{path}.properties.{prop_name}")


def validate(instance, schema, path="$"):
    """Return a list of human-readable violations, empty when valid."""
    _audit_schema(schema, path)
    errors = []
    expected = schema.get("type")
    if expected:
        if expected in ("integer", "number") and isinstance(instance, bool):
            errors.append(f"{path}: expected {expected}, got boolean")
            return errors
        wanted = _TYPES[expected]
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

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                errors.extend(validate(value, properties[key], f"{path}.{key}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property {key!r} is not allowed")
    if isinstance(instance, list):
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                errors.extend(validate(item, item_schema, f"{path}[{index}]"))
        if schema.get("uniqueItems"):
            hashable = [json.dumps(i, sort_keys=True) for i in instance]
            if len(set(hashable)) != len(hashable):
                errors.append(f"{path}: items are not unique")
    return errors
