"""A hand-rolled JSON Schema subset checker, importable by scripts.

Extracted from ``templates/dispatch/tests/test_task_packet_schema.py`` so that
more than one consumer can reach it without copying it. The public surface is
exactly four names:

* ``validate(instance, schema, path="$", assert_formats=())`` -> a list of
  human-readable violation strings, empty when the instance satisfies the
  schema;
* ``UnsupportedKeyword``, an Exception;
* ``SUPPORTED_KEYWORDS`` and ``ANNOTATION_KEYWORDS``, two disjoint non-empty
  frozensets;
* ``FORMAT_CHECKERS``, a mapping from format name to a predicate over a
  string, consulted only when a caller opts into asserting formats.

A schema keyword that is neither enforced (``SUPPORTED_KEYWORDS``) nor
knowingly constraint-free (``ANNOTATION_KEYWORDS``) raises
``UnsupportedKeyword``, naming the keyword. A supported keyword in a form this
checker does not enforce raises the same way. The audit is eager and total: it
walks the whole schema, descending into ``allOf`` and ``oneOf`` branches,
``not``, ``if`` and ``then``, ``propertyNames``, an ``additionalProperties``
subschema, and every ``$defs`` definition whether referenced or not, so a
subschema no instance reaches still raises.

Composition is enforced:

* ``$defs`` / ``$ref`` -- internal pointers of the form ``#/...`` only. An
  external ``$ref`` cannot be fetched and a dangling one is a broken pointer,
  not "no constraint", so either raises.
* ``allOf`` -- every branch holds, and every branch's violations are reported.
* ``if`` / ``then`` -- ``then`` binds only when ``if`` is satisfied; a failing
  ``if`` is a condition, not a violation.
* ``oneOf`` -- exactly one branch holds; matching none is distinguishable from
  matching several.
* ``not`` -- the subschema must not hold.
* ``propertyNames`` -- every key of an object satisfies a subschema.
* ``minItems``, ``minProperties``, ``maximum`` -- the obvious bounds, with
  ``maximum`` mirroring ``minimum`` and neither applied to a boolean.
* ``additionalProperties`` in its subschema form -- every property ``properties``
  does not name must satisfy that subschema; ``False`` still forbids extras and
  names each one, ``True`` and absent still constrain nothing.

Format assertion is opt-in. ``validate`` takes ``assert_formats``, an
iterable of format names to enforce for that call; the default is empty and
behaves exactly as before. A name in ``assert_formats`` with no entry in
``FORMAT_CHECKERS`` raises ``UnsupportedKeyword`` rather than silently
certifying what was never checked. ``format`` constrains strings only: a
non-string instance under a format schema is unaffected, per the
specification.

The governing rule does not move: a construct the checker cannot enforce raises
rather than passing.
"""
from __future__ import annotations

import json
import re

SUPPORTED_KEYWORDS = frozenset({
    "type", "required", "properties", "additionalProperties", "items",
    "enum", "const", "pattern", "minLength", "minimum", "uniqueItems",
    "$defs", "$ref", "allOf", "if", "then", "oneOf", "not",
    "propertyNames", "minItems", "minProperties", "maximum",
})

ANNOTATION_KEYWORDS = frozenset({
    "$schema", "$id", "title", "description", "default", "examples",
    "deprecated", "format", "$comment",
})


class UnsupportedKeyword(Exception):
    """A schema keyword (or form) this checker does not enforce."""


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid(value):
    """True for the canonical hyphenated UUID spelling, case-insensitively."""
    return _UUID_RE.match(value) is not None


FORMAT_CHECKERS = {
    "uuid": _is_uuid,
}


_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    # `{"type": "null"}` audits clean -- `type` is a supported keyword -- and then
    # raised KeyError here the first time an instance reached it, which is a checker
    # that accepts a schema it cannot check. Added 2026-08-30 while writing
    # session-binding/v0, whose nullable branches are expressed the way this checker
    # requires: `oneOf` with an explicit null branch, never a union type list.
    "null": type(None),
}


def _resolve_pointer(document, ref):
    """Resolve an internal JSON Pointer of the form ``#/a/b`` against document.

    Returns ``None`` for anything that is not an internal pointer or does not
    resolve, so callers can treat "external" and "dangling" identically: both
    are constructs this checker cannot honestly apply.
    """
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    node = document
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif (isinstance(node, list) and part.isdigit()
              and int(part) < len(node)):
            node = node[int(part)]
        else:
            return None
    return node


def _audit_schema(schema, path, root, seen=None, defects=None):
    """Walk the whole schema eagerly, collecting every unenforceable construct.

    ``root`` is the top-level schema document that internal ``$ref`` pointers
    resolve against. ``seen`` guards the recursion against a ``$defs``
    definition that points back at itself; a node already audited is a node
    already known to be honest, and is reported once, not once per path that
    reaches it. ``defects`` is the list being accumulated; each entry carries
    the breadcrumb of the offending node and names the offending keyword.
    """
    if defects is None:
        defects = []
    if isinstance(schema, bool):
        defects.append(f"{path}: boolean schema is not supported")
        return defects
    if not isinstance(schema, dict):
        defects.append(
            f"{path}: schema must be an object, got {type(schema).__name__}")
        return defects
    if seen is None:
        seen = set()
    marker = id(schema)
    if marker in seen:
        return defects
    seen.add(marker)
    for keyword, value in schema.items():
        if keyword in ANNOTATION_KEYWORDS:
            continue
        if keyword not in SUPPORTED_KEYWORDS:
            defects.append(f"{path}: unsupported keyword {keyword!r}")
            continue
        if keyword == "type":
            if not isinstance(value, str):
                defects.append(f"{path}: type as a union list is not supported")
        elif keyword == "items":
            if isinstance(value, list):
                defects.append(
                    f"{path}: items as a positional list is not supported")
            else:
                _audit_schema(value, f"{path}.items", root, seen, defects)
        elif keyword == "properties":
            for prop_name, prop_schema in value.items():
                _audit_schema(prop_schema, f"{path}.properties.{prop_name}",
                              root, seen, defects)
        elif keyword == "additionalProperties":
            if isinstance(value, dict):
                _audit_schema(value, f"{path}.additionalProperties",
                              root, seen, defects)
            elif not isinstance(value, bool):
                defects.append(
                    f"{path}: additionalProperties must be a boolean or a "
                    f"subschema")
        elif keyword == "$defs":
            for name, definition in value.items():
                _audit_schema(definition, f"{path}.$defs.{name}",
                              root, seen, defects)
        elif keyword == "$ref":
            target = _resolve_pointer(root, value)
            if target is None:
                defects.append(
                    f"{path}: $ref {value!r} is not an internal, resolvable "
                    f"pointer")
            else:
                _audit_schema(target, f"{path}@{value}", root, seen, defects)
        elif keyword in ("allOf", "oneOf"):
            if not isinstance(value, list):
                defects.append(f"{path}: {keyword} must be a list of schemas")
            else:
                for index, subschema in enumerate(value):
                    _audit_schema(subschema, f"{path}.{keyword}[{index}]",
                                  root, seen, defects)
        elif keyword == "not":
            _audit_schema(value, f"{path}.not", root, seen, defects)
        elif keyword == "if":
            _audit_schema(value, f"{path}.if", root, seen, defects)
        elif keyword == "then":
            _audit_schema(value, f"{path}.then", root, seen, defects)
        elif keyword == "propertyNames":
            _audit_schema(value, f"{path}.propertyNames", root, seen, defects)
        elif keyword in ("minItems", "minProperties", "maximum"):
            if (not isinstance(value, (int, float))
                    or isinstance(value, bool)):
                defects.append(f"{path}: {keyword} must be a number")
    return defects


def audit_schema(schema, path="$"):
    """Report every construct the checker cannot enforce, one entry each.

    Returns a list of human-readable strings, empty when the schema is
    enforceable end to end. Never raises: it reports, where ``validate``
    refuses. Each entry carries the breadcrumb of the offending node and names
    the offending keyword.
    """
    return _audit_schema(schema, path, schema)


def validate(instance, schema, path="$", assert_formats=()):
    """Return a list of human-readable violations, empty when valid.

    ``assert_formats`` names the formats to enforce for this call; it accepts
    any iterable and defaults to empty, which behaves exactly as before. A
    name with no entry in ``FORMAT_CHECKERS`` raises ``UnsupportedKeyword``
    rather than silently certifying what was never checked.
    """
    assert_formats = frozenset(assert_formats)
    for name in assert_formats:
        if name not in FORMAT_CHECKERS:
            raise UnsupportedKeyword(
                f"{path}: no checker for asserted format {name!r}")
    defects = _audit_schema(schema, path, schema)
    if defects:
        raise UnsupportedKeyword(defects[0])
    return _validate(instance, schema, path, schema, assert_formats)


def _validate(instance, schema, path, root, assert_formats=()):
    """Recursive validation core; ``root`` anchors internal ``$ref`` pointers."""
    errors = []

    if "$ref" in schema:
        target = _resolve_pointer(root, schema["$ref"])
        if target is None:
            raise UnsupportedKeyword(
                f"{path}: $ref {schema['$ref']!r} is not an internal, "
                f"resolvable pointer")
        errors.extend(_validate(instance, target, path, root, assert_formats))

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
        fmt = schema.get("format")
        if fmt in assert_formats and not FORMAT_CHECKERS[fmt](instance):
            errors.append(
                f"{path}: {instance!r} does not match format {fmt}")
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
        min_properties = schema.get("minProperties")
        if min_properties is not None and len(instance) < min_properties:
            errors.append(f"{path}: fewer than minProperties {min_properties}")
        property_names = schema.get("propertyNames")
        if property_names is not None:
            for key in instance:
                errors.extend(
                    _validate(key, property_names, f"{path}.{key}", root,
                              assert_formats))
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties")
        for key, value in instance.items():
            if key in properties:
                errors.extend(
                    _validate(value, properties[key], f"{path}.{key}", root,
                              assert_formats))
            elif additional is False:
                errors.append(
                    f"{path}: additional property {key!r} is not allowed")
            elif isinstance(additional, dict):
                errors.extend(
                    _validate(value, additional, f"{path}.{key}", root,
                              assert_formats))
    if isinstance(instance, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(instance) < min_items:
            errors.append(f"{path}: fewer than minItems {min_items}")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                errors.extend(
                    _validate(item, item_schema, f"{path}[{index}]", root,
                              assert_formats))
        if schema.get("uniqueItems"):
            hashable = [json.dumps(i, sort_keys=True) for i in instance]
            if len(set(hashable)) != len(hashable):
                errors.append(f"{path}: items are not unique")

    for branch in schema.get("allOf", []):
        errors.extend(_validate(instance, branch, path, root, assert_formats))

    if "if" in schema and not _validate(instance, schema["if"], path, root,
                                        assert_formats):
        then = schema.get("then")
        if then is not None:
            errors.extend(_validate(instance, then, path, root, assert_formats))

    one_of = schema.get("oneOf")
    if one_of is not None:
        matches = [branch for branch in one_of
                   if not _validate(instance, branch, path, root,
                                    assert_formats)]
        if len(matches) == 0:
            errors.append(f"{path}: matched none of the oneOf branches")
        elif len(matches) > 1:
            errors.append(f"{path}: matched more than one oneOf branch")

    not_schema = schema.get("not")
    if not_schema is not None and not _validate(instance, not_schema, path,
                                                root, assert_formats):
        errors.append(f"{path}: must not satisfy the 'not' subschema")

    return errors
