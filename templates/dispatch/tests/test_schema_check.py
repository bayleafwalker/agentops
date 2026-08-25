"""Oracle for ``templates/dispatch/scripts/schema_check.py``.

The repo carries a hand-rolled JSON Schema subset checker inside a *test* file
(``test_task_packet_schema.py``). It works, it caught real drift in the packet
schema, and it cannot be imported by any script -- so the second consumer that
now needs it would have to copy it, which is how this repo ended up with
``_path_allowed`` and ``_matches_any`` answering one question twice.

This row extracts that checker into a module and fixes the lie in its
docstring. The docstring claimed unimplemented keywords were "ignored rather
than silently passed off as checked"; in fact they were ignored *silently*, and
the two schemas it is pointed at already use keywords it does not implement. A
constraint the checker skips is a constraint that does not exist. So the module
must refuse: a schema keyword that is neither enforced (``SUPPORTED_KEYWORDS``)
nor knowingly constraint-free (``ANNOTATION_KEYWORDS``) raises
``UnsupportedKeyword``, naming the keyword.

Scope note for whoever reads this next: this row does NOT implement the
composition keywords (``allOf``, ``$ref``, ``if``/``then``, ``oneOf``, ``not``,
``propertyNames``, ``minItems``, ``minProperties``, ``maximum``). Today they
must raise. A later row implements them. This file is therefore written to pin
*behaviour conditioned on ``SUPPORTED_KEYWORDS`` membership*, never on a frozen
literal keyword list: an oracle that made the next row impossible to land would
be a badly designed oracle, but an oracle that let an implementation quietly
drop a keyword would be worse. The bargain is:

* a keyword the module claims to support must actually be enforced (the
  eleven-keyword floor below, plus a satisfy/violate pair for each);
* a keyword the module does not claim must raise;
* a constraint-bearing keyword must never be parked in ANNOTATION_KEYWORDS.

Growing ``SUPPORTED_KEYWORDS`` is legal and this file follows it. Emptying the
enforcement out from under a supported keyword is not, and this file fails.

The audit is on shapes as well as names. A keyword the checker implements can
still appear in a *form* it does not enforce -- ``additionalProperties`` as a
subschema, ``items`` as a positional list, ``type`` as a union list, a boolean
used where a schema object belongs. A name-level audit waves all four through
and the skipped constraint is silent again, one level further down, which is
the same defect wearing a different hat. So those raise too, with the same
exception, eagerly, at any depth.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
TASK_PACKET_SCHEMA_PATH = ROOT / "templates/dispatch/hybrid/task-packet.schema.json"
MANIFEST_SCHEMA_PATH = ROOT / "templates/dispatch/manifest.schema.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


schema_check = _load("schema_check_subject", SCRIPTS / "schema_check.py")

validate = schema_check.validate
UnsupportedKeyword = schema_check.UnsupportedKeyword

#: The keywords this row must enforce. A floor, not a ceiling: the module may
#: support more (that is the next row), but never fewer.
ENFORCED_FLOOR = frozenset({
    "type", "required", "properties", "additionalProperties", "items",
    "enum", "const", "pattern", "minLength", "minimum", "uniqueItems",
})

#: Keywords that carry no constraint and are skipped by name.
ANNOTATION_FLOOR = frozenset({
    "$schema", "$id", "title", "description", "default", "examples",
    "deprecated", "format", "$comment",
})

#: Constraint-bearing keywords this row does not implement. Each must raise
#: today. When a later row implements one it moves into SUPPORTED_KEYWORDS and
#: the raise-tests below step aside for it -- but it may never be reclassified
#: as an annotation, because every one of these changes which instances are
#: valid.
CONSTRAINT_BEARING_UNIMPLEMENTED = (
    "allOf", "anyOf", "oneOf", "not", "$ref", "if", "then", "else",
    "propertyNames", "minItems", "maxItems", "minProperties", "maxProperties",
    "maximum", "exclusiveMinimum", "maxLength", "dependentRequired",
)


def _handled(keyword: str) -> bool:
    """True if the module claims this keyword (enforced or annotation)."""
    return (keyword in schema_check.SUPPORTED_KEYWORDS
            or keyword in schema_check.ANNOTATION_KEYWORDS)


def _subschema_form_enforced() -> bool:
    """True once ``additionalProperties`` as a subschema is actually applied.

    Coordinator amendment, 2026-08-25, recorded rather than quietly made. This
    file was written when the row above it did not implement the subschema form
    of ``additionalProperties``, so the tests below pinned it as *raising* --
    correctly, since a checker that returns ``[]`` for a constraint it never
    applied is exactly what this module exists to prevent. The V5.9-2 row then
    implemented that form, because ``manifest.schema.json`` uses it in three
    places and a manifest that always raises cannot be validated by anything.

    The intent of those tests survives the change unaltered: the subschema form
    must never be silently ignored. What changes is which of the two acceptable
    answers is live -- raise while unenforced, enforce once implemented. This
    probe asks the module which world it is in, so both are pinned and neither
    can degrade into silence. Nothing was deleted to make a packet pass.
    """
    try:
        return validate(
            {"extra": 1},
            {"type": "object", "properties": {},
             "additionalProperties": {"type": "string"}}) != []
    except schema_check.UnsupportedKeyword:
        return False


class PublicSurfaceTests(unittest.TestCase):
    """The seam itself: one function and two frozensets, nothing more."""

    def test_validate_takes_a_default_path(self):
        self.assertEqual(validate("x", {"type": "string"}), [])

    def test_unsupported_keyword_is_an_exception(self):
        self.assertTrue(issubclass(UnsupportedKeyword, Exception))

    def test_both_keyword_sets_are_non_empty_frozensets(self):
        self.assertIsInstance(schema_check.SUPPORTED_KEYWORDS, frozenset)
        self.assertIsInstance(schema_check.ANNOTATION_KEYWORDS, frozenset)
        self.assertTrue(schema_check.SUPPORTED_KEYWORDS)
        self.assertTrue(schema_check.ANNOTATION_KEYWORDS)

    def test_the_two_sets_are_disjoint(self):
        overlap = schema_check.SUPPORTED_KEYWORDS & schema_check.ANNOTATION_KEYWORDS
        self.assertEqual(
            overlap, frozenset(),
            "a keyword cannot be both enforced and constraint-free")

    def test_the_eleven_keywords_of_this_row_are_supported(self):
        missing = ENFORCED_FLOOR - schema_check.SUPPORTED_KEYWORDS
        self.assertEqual(
            missing, frozenset(),
            "these keywords are enforced by the prior-art checker and their "
            "enforcement must survive the extraction")

    def test_the_annotation_keywords_are_declared(self):
        missing = ANNOTATION_FLOOR - schema_check.ANNOTATION_KEYWORDS
        self.assertEqual(
            missing, frozenset(),
            "annotations are skipped by name, not by a catch-all")

    def test_no_constraint_bearing_keyword_is_parked_as_an_annotation(self):
        for keyword in CONSTRAINT_BEARING_UNIMPLEMENTED:
            with self.subTest(keyword=keyword):
                self.assertNotIn(
                    keyword, schema_check.ANNOTATION_KEYWORDS,
                    f"{keyword} changes which instances are valid; calling it "
                    f"an annotation is the silent skip this row exists to kill")


class TypeKeywordTests(unittest.TestCase):
    """``type`` over the six names the dispatch schemas actually use."""

    CASES = {
        "object": ({}, "not an object"),
        "array": ([], "not an array"),
        "string": ("s", 1),
        "integer": (3, "3"),
        "number": (3.5, "3.5"),
        "boolean": (True, "true"),
    }

    def test_each_type_accepts_a_satisfying_instance(self):
        for name, (good, _bad) in self.CASES.items():
            with self.subTest(type=name):
                self.assertEqual(validate(good, {"type": name}), [])

    def test_each_type_rejects_a_violating_instance(self):
        for name, (_good, bad) in self.CASES.items():
            with self.subTest(type=name):
                self.assertTrue(
                    validate(bad, {"type": name}),
                    f"{bad!r} is not a {name} and must be reported")

    def test_an_integer_satisfies_number(self):
        self.assertEqual(validate(3, {"type": "number"}), [])

    def test_a_boolean_is_not_an_integer(self):
        # bool is an int in Python; the schema means them separately.
        self.assertTrue(validate(True, {"type": "integer"}))
        self.assertTrue(validate(False, {"type": "integer"}))

    def test_a_boolean_is_not_a_number(self):
        self.assertTrue(validate(True, {"type": "number"}))

    def test_a_failed_type_check_stops_descending(self):
        schema = {
            "type": "object",
            "required": ["a", "b"],
            "additionalProperties": False,
            "properties": {"a": {"type": "string"}, "b": {"type": "string"}},
        }
        errors = validate("I am a string", schema)
        self.assertEqual(
            len(errors), 1,
            f"one clear type violation, not a cascade: {errors}")
        self.assertTrue(errors[0].startswith("$"))


class ObjectKeywordTests(unittest.TestCase):
    """``required``, ``properties`` and ``additionalProperties: false``."""

    SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "required": ["name"],
        "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
    }

    def test_a_satisfying_object_passes(self):
        self.assertEqual(validate({"name": "x", "count": 2}, self.SCHEMA), [])

    def test_a_missing_required_property_is_reported_by_name(self):
        errors = validate({"count": 2}, self.SCHEMA)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("name", errors[0])

    def test_a_property_subschema_is_applied(self):
        errors = validate({"name": "x", "count": "two"}, self.SCHEMA)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("$.count"), errors[0])

    def test_each_unexpected_key_is_reported_and_named(self):
        errors = validate({"name": "x", "extra": 1, "other": 2}, self.SCHEMA)
        self.assertEqual(len(errors), 2, errors)
        joined = " | ".join(errors)
        self.assertIn("extra", joined)
        self.assertIn("other", joined)

    def test_unexpected_keys_are_allowed_when_the_schema_is_silent(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        self.assertEqual(validate({"name": "x", "extra": 1}, schema), [])


class ArrayKeywordTests(unittest.TestCase):
    """``items`` and ``uniqueItems``."""

    def test_items_accepts_a_satisfying_array(self):
        self.assertEqual(
            validate(["a", "b"], {"type": "array", "items": {"type": "string"}}), [])

    def test_items_reports_the_offending_index(self):
        errors = validate(
            ["a", 7], {"type": "array", "items": {"type": "string"}})
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith("$[1]"), errors[0])

    def test_unique_items_accepts_distinct_values(self):
        self.assertEqual(
            validate(["a", "b"], {"type": "array", "uniqueItems": True}), [])

    def test_unique_items_rejects_repeats(self):
        self.assertTrue(
            validate(["a", "a"], {"type": "array", "uniqueItems": True}))

    def test_unique_items_compares_by_value_not_identity(self):
        # Two distinct dict objects, equal in value, keys written in a
        # different order. Identity comparison misses this.
        instance = [{"x": 1, "y": 2}, {"y": 2, "x": 1}]
        self.assertTrue(
            validate(instance, {"type": "array", "uniqueItems": True}),
            "equal-by-value items are duplicates however their keys are ordered")


class ScalarKeywordTests(unittest.TestCase):
    """``enum``, ``const``, ``pattern``, ``minLength``, ``minimum``."""

    def test_enum_accepts_a_member(self):
        self.assertEqual(validate("b", {"enum": ["a", "b"]}), [])

    def test_enum_rejects_a_non_member(self):
        self.assertTrue(validate("c", {"enum": ["a", "b"]}))

    def test_const_accepts_the_value(self):
        self.assertEqual(validate(1, {"const": 1}), [])

    def test_const_rejects_anything_else(self):
        self.assertTrue(validate(2, {"const": 1}))

    def test_pattern_accepts_a_match(self):
        self.assertEqual(
            validate("agentops#22", {"type": "string",
                                     "pattern": "^[A-Za-z0-9._-]+#[0-9]+$"}), [])

    def test_pattern_rejects_a_non_match(self):
        self.assertTrue(
            validate("no hash here", {"type": "string",
                                      "pattern": "^[A-Za-z0-9._-]+#[0-9]+$"}))

    def test_pattern_is_re_match_not_fullmatch(self):
        # Anchored at the start only: an unanchored tail is fine.
        self.assertEqual(validate("abcdef", {"pattern": "^abc"}), [])
        self.assertEqual(validate("abcdef", {"pattern": "abc"}), [])
        self.assertTrue(validate("xabcdef", {"pattern": "abc"}),
                        "re.match anchors at the start; this must not pass")

    def test_min_length_accepts_a_long_enough_string(self):
        self.assertEqual(validate("ab", {"type": "string", "minLength": 2}), [])

    def test_min_length_rejects_a_short_string(self):
        self.assertTrue(validate("", {"type": "string", "minLength": 1}))

    def test_minimum_accepts_a_large_enough_number(self):
        self.assertEqual(validate(1, {"type": "integer", "minimum": 1}), [])

    def test_minimum_rejects_a_small_number(self):
        self.assertTrue(validate(0, {"type": "integer", "minimum": 1}))

    def test_minimum_is_not_applied_to_a_boolean(self):
        # True == 1 in Python. A boolean is not a number here, so `minimum`
        # has nothing to say about it -- the type keyword is what rejects it.
        self.assertEqual(validate(True, {"minimum": 5}), [])
        self.assertEqual(validate(False, {"minimum": 5}), [])


class BreadcrumbTests(unittest.TestCase):
    """Messages carry the path to the value, not just the fact of a failure."""

    DEEP = {
        "type": "object",
        "properties": {
            "a": {
                "type": "object",
                "properties": {
                    "b": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    }

    def test_a_nested_violation_carries_the_nested_path(self):
        errors = validate({"a": {"b": ["ok", "ok", 3]}}, self.DEEP)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(
            errors[0].startswith("$.a.b[2]"),
            f"expected a $.a.b[2] breadcrumb, got {errors[0]!r}")

    def test_the_path_argument_prefixes_the_breadcrumb(self):
        errors = validate({"a": {"b": [3]}}, self.DEEP, "$.packet")
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(
            errors[0].startswith("$.packet.a.b[0]"),
            f"the caller's breadcrumb must be honoured, got {errors[0]!r}")

    def test_every_message_is_prefixed_with_the_breadcrumb(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["missing"],
            "properties": {"n": {"type": "integer"}},
        }
        errors = validate({"n": "x", "surprise": 1}, schema, "$.root")
        self.assertGreaterEqual(len(errors), 3, errors)
        for message in errors:
            with self.subTest(message=message):
                self.assertTrue(message.startswith("$.root"), message)

    def test_multiple_independent_violations_are_all_reported(self):
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "string"},
                "b": {"type": "integer"},
                "c": {"enum": ["x"]},
            },
        }
        errors = validate({"a": 1, "b": "two", "c": "z"}, schema)
        self.assertEqual(
            len(errors), 3,
            f"all three violations must surface, not just the first: {errors}")


class UnsupportedKeywordTests(unittest.TestCase):
    """The rule this row exists for: an unhandled keyword is loud, not silent.

    Every assertion here is conditioned on ``SUPPORTED_KEYWORDS`` membership, so
    the later row that implements the composition keywords can land without
    editing this file -- and cannot land by quietly widening the skip.
    """

    def _assert_raises_naming(self, keyword, instance, schema):
        with self.assertRaises(UnsupportedKeyword) as caught:
            validate(instance, schema)
        self.assertIn(
            keyword, str(caught.exception),
            "the exception must name the offending keyword")

    def test_a_keyword_no_one_will_ever_implement_always_raises(self):
        # Not conditioned on anything: this is nonsense, it can never be
        # supported, and it must never be tolerated.
        self._assert_raises_naming(
            "totallyBogusKeyword", "x",
            {"type": "string", "totallyBogusKeyword": 1})

    def test_the_unimplemented_constraint_keywords_raise_today(self):
        for keyword in CONSTRAINT_BEARING_UNIMPLEMENTED:
            with self.subTest(keyword=keyword):
                if keyword in schema_check.SUPPORTED_KEYWORDS:
                    self.skipTest(f"{keyword} is now enforced; a later row's job")
                self._assert_raises_naming(keyword, {}, {"type": "object", keyword: {}})

    def test_an_unhandled_keyword_inside_properties_raises(self):
        if _handled("allOf"):
            self.skipTest("allOf is now handled")
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string", "allOf": []}},
        }
        self._assert_raises_naming("allOf", {"a": "x"}, schema)

    def test_an_unhandled_keyword_inside_items_raises(self):
        if _handled("$ref"):
            self.skipTest("$ref is now handled")
        schema = {"type": "array", "items": {"$ref": "#/$defs/thing"}}
        self._assert_raises_naming("$ref", ["x"], schema)

    def test_an_unhandled_keyword_raises_even_where_the_instance_never_reaches_it(self):
        # The schema is what is being audited, not the instance. A checker that
        # only notices keywords it happens to walk past would still be lying
        # about the optional branch it never visited.
        if _handled("minItems"):
            self.skipTest("minItems is now handled")
        schema = {
            "type": "object",
            "properties": {
                "present": {"type": "string"},
                "absent": {"type": "array", "minItems": 1},
            },
        }
        self._assert_raises_naming("minItems", {"present": "x"}, schema)

    def test_a_defs_style_container_is_not_a_hiding_place(self):
        if _handled("$defs"):
            self.skipTest("$defs is now handled")
        self._assert_raises_naming(
            "$defs", "x",
            {"type": "string", "$defs": {"thing": {"type": "string"}}})

    def test_annotation_keywords_do_not_raise_and_add_no_constraint(self):
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://agentops.local/schemas/example.schema.json",
            "$comment": "not a constraint",
            "title": "Example",
            "description": "Annotations carry no constraint.",
            "default": "fallback",
            "examples": ["one", "two"],
            "deprecated": False,
            "format": "uuid",
            "type": "string",
        }
        # `format: uuid` is an annotation here, so a non-uuid string passes.
        self.assertEqual(validate("plainly-not-a-uuid", schema), [])

    def test_annotations_are_also_tolerated_in_a_subschema(self):
        schema = {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "description": "a count", "default": 0},
            },
        }
        self.assertEqual(validate({"n": 1}, schema), [])


#: Schemas whose every keyword *name* is handled, but whose *form* is one this
#: checker does not enforce. Each must raise, naming the keyword. Keyed by the
#: keyword the message has to name.
SHAPE_CASES = {
    "items": (
        {"type": "array", "items": [{"type": "string"}, {"type": "integer"}]},
        ["x", 1]),
    "type": ({"type": ["string", "null"]}, "x"),
}


class ShapeAuditTests(unittest.TestCase):
    """A supported keyword in an unsupported form is still an unchecked one.

    ``additionalProperties: {...}`` passes a name-level audit and then imposes
    nothing -- exactly the silence this row exists to end, hidden one level
    down. These pin the four forms called out in the brief.
    """

    def _assert_raises_naming(self, keyword, instance, schema):
        with self.assertRaises(UnsupportedKeyword) as caught:
            validate(instance, schema)
        self.assertIn(
            keyword, str(caught.exception),
            "the exception must name the offending keyword")

    def test_each_unenforceable_form_raises(self):
        for keyword, (schema, instance) in SHAPE_CASES.items():
            with self.subTest(keyword=keyword):
                self._assert_raises_naming(keyword, instance, schema)

    def test_a_boolean_schema_raises(self):
        # JSON Schema permits `true`/`false` as a whole schema. This checker
        # does not implement either, so it must not pretend to.
        for boolean_schema in (True, False):
            with self.subTest(schema=boolean_schema):
                with self.assertRaises(UnsupportedKeyword):
                    validate("x", boolean_schema)

    def test_a_boolean_subschema_raises(self):
        for schema in ({"type": "object", "properties": {"a": True}},
                       {"type": "array", "items": False}):
            with self.subTest(schema=schema):
                with self.assertRaises(UnsupportedKeyword):
                    validate({} if schema["type"] == "object" else [], schema)

    def test_an_unenforceable_form_raises_where_the_instance_never_reaches_it(self):
        # Same eager rule as the name audit: the schema is what is audited.
        for keyword, (bad, _instance) in SHAPE_CASES.items():
            with self.subTest(keyword=keyword):
                schema = {
                    "type": "object",
                    "properties": {"present": {"type": "string"}, "absent": bad},
                }
                self._assert_raises_naming(keyword, {"present": "x"}, schema)

    def test_an_unenforceable_form_raises_inside_items(self):
        # Exemplified with the union form of `type`, which stays unenforceable.
        # It was `additionalProperties` as a subschema until V5.9-2 implemented
        # that form; the guarantee being pinned -- a bad form nested inside a
        # container still raises -- is unchanged, and is now pinned by a case
        # that no planned row will implement away.
        self._assert_raises_naming(
            "type", [],
            {"type": "array",
             "items": {"type": "object",
                       "properties": {"a": {"type": ["string", "null"]}}}})

    def test_the_enforced_forms_still_do_not_raise(self):
        for schema, instance in (
                ({"type": "object", "additionalProperties": False,
                  "properties": {"a": {"type": "string"}}}, {"a": "x"}),
                ({"type": "array", "items": {"type": "string"}}, ["x"]),
                ({"type": "string"}, "x")):
            with self.subTest(schema=schema):
                self.assertEqual(validate(instance, schema), [])

    def test_additional_properties_true_imposes_nothing_and_does_not_raise(self):
        # `true` and absent both mean "no constraint", so ignoring them is
        # honest -- there is nothing being skipped.
        schema = {"type": "object", "additionalProperties": True,
                  "properties": {"a": {"type": "string"}}}
        self.assertEqual(validate({"a": "x", "extra": 1}, schema), [])

    def test_a_shape_violation_uses_the_same_exception(self):
        # Callers catch one thing, whether the schema named a keyword the
        # checker lacks or used one in a form it cannot enforce.
        with self.assertRaises(UnsupportedKeyword):
            validate([], {"type": "array", "items": [{"type": "string"}]})

    def test_the_subschema_form_is_enforced_or_refused_but_never_ignored(self):
        # The two acceptable answers for additionalProperties as a subschema,
        # and the one that is never acceptable. Before V5.9-2 the module
        # raised; after it, the constraint is applied. Silence -- returning no
        # violations for an extra property of the wrong type -- is the failure
        # this module exists to prevent, and it fails here in both worlds.
        schema = {"type": "object", "properties": {},
                  "additionalProperties": {"type": "string"}}
        try:
            violations = validate({"extra": 1}, schema)
        except UnsupportedKeyword:
            return
        self.assertTrue(
            violations,
            "additionalProperties as a subschema was neither refused nor "
            "enforced: an extra property of the wrong type passed silently")
        self.assertEqual(validate({"extra": "x"}, schema), [])


class RealSchemaTests(unittest.TestCase):
    """The two schemas in the repo, which are why this row exists.

    Both already use keywords this row does not implement. That is the point:
    the checker must say so out loud rather than validate them and report an
    empty list it has no right to. When a later row implements those keywords,
    these tests follow it into the enforced branch.
    """

    def _schema(self, path):
        self.assertTrue(path.is_file(), f"missing schema: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    #: Keywords both real schemas use that this row does not implement. When a
    #: later row implements all of them, the name-audit reason goes quiet.
    COMPOSITION = ("allOf", "$ref", "if", "then", "$defs", "maximum", "minItems")

    def _composition_is_handled(self):
        return all(_handled(keyword) for keyword in self.COMPOSITION)

    def _assert_honest(self, schema, instance):
        if self._composition_is_handled():
            result = validate(instance, schema)
            self.assertIsInstance(result, list)
        else:
            with self.assertRaises(
                    UnsupportedKeyword,
                    msg="this schema uses keywords the checker does not "
                        "implement; returning a verdict on it would be a lie"):
                validate(instance, schema)

    def test_the_task_packet_schema_is_handled_or_refused(self):
        self._assert_honest(self._schema(TASK_PACKET_SCHEMA_PATH), {})

    def _action_classes(self):
        """The real node in manifest.schema.json that carries the shape hole."""
        manifest = self._schema(MANIFEST_SCHEMA_PATH)
        return manifest["properties"]["routing"]["properties"]["action_classes"]

    def test_the_manifest_really_does_use_the_subschema_form(self):
        # The anchor. If this ever stops being true the two tests below are
        # measuring nothing, and this one says so out loud rather than passing
        # vacuously.
        self.assertIsInstance(
            self._action_classes()["additionalProperties"], dict,
            "manifest.schema.json is expected to constrain action_classes "
            "values with the subschema form of additionalProperties")

    def test_the_manifest_shape_hole_is_enforced_or_raises(self):
        # Reason one, isolated: the real node lifted out of the file and
        # wrapped so that the *only* thing wrong is the unenforceable form.
        # This is unconditional. It is not the next row's to silence: until
        # the subschema form is enforced, a checker that returns [] here is
        # certifying a constraint it never applied.
        schema = {
            "type": "object",
            "additionalProperties": self._action_classes()["additionalProperties"],
        }
        if not _subschema_form_enforced():
            with self.assertRaises(UnsupportedKeyword) as caught:
                validate({"mechanical_bulk": {"enabled": True}}, schema)
            self.assertIn("additionalProperties", str(caught.exception))
            return
        # V5.9-2 implemented the form. The node must now actually constrain the
        # values it was written to constrain -- which is a stronger statement
        # than the refusal it replaces, and fails just as loudly on silence.
        self.assertTrue(
            validate({"mechanical_bulk": "not an object"}, schema),
            "the real action_classes subschema accepted a value it constrains")

    def test_the_manifest_composition_reason_raises_on_its_own(self):
        # Reason two, isolated: the composition keyword the same node carries,
        # with no shape defect in sight. This one steps aside for the next row.
        if _handled("minProperties"):
            self.skipTest("minProperties is now handled; a later row's job")
        with self.assertRaises(UnsupportedKeyword) as caught:
            validate({}, {"type": "object", "minProperties": 1})
        self.assertIn("minProperties", str(caught.exception))

    def test_the_manifest_schema_is_refused_and_says_which_reason_is_live(self):
        manifest = self._schema(MANIFEST_SCHEMA_PATH)
        if self._composition_is_handled() and _subschema_form_enforced():
            # Both reasons closed: the manifest is checkable, which is the
            # whole point of the v5.9 rows. It must yield a verdict, and the
            # verdict must be a real one -- a checker that answers [] to
            # everything would pass a weaker assertion than this.
            self.assertEqual(validate(manifest, {"type": "object"}), [])
            self.assertTrue(
                validate({"schema_version": 1}, manifest),
                "the manifest schema accepted an obviously wrong instance")
            return
        with self.assertRaises(UnsupportedKeyword) as caught:
            validate({}, manifest)
        if self._composition_is_handled():
            # The next row landed. The manifest must STILL be refused, and now
            # for the shape alone -- so that implementing the composition
            # keywords cannot look like finishing the job while the subschema
            # form of additionalProperties is still unenforced.
            self.assertIn(
                "additionalProperties", str(caught.exception),
                "with the composition keywords implemented, the only reason "
                "left to refuse the manifest is the unenforceable "
                "additionalProperties form -- and the message must say so")


class DiscriminationTests(unittest.TestCase):
    """Tests that a permissive stub cannot pass.

    ``def validate(*a, **k): return []`` satisfies every "this instance is
    valid" assertion in this file. These exist to catch exactly that class of
    mistake -- a checker that answers "fine" to everything, which is the shape
    the extraction is most likely to be broken into (a keyword's enforcement
    dropped on the way out of the test file, leaving the happy path green).
    Each row below is an instance that MUST produce at least one violation, one
    per implemented keyword.
    """

    CASES = {
        "type": ({"type": "string"}, 1),
        "required": ({"type": "object", "required": ["a"]}, {}),
        "properties": (
            {"type": "object", "properties": {"a": {"type": "string"}}}, {"a": 1}),
        "additionalProperties": (
            {"type": "object", "additionalProperties": False, "properties": {}},
            {"nope": 1}),
        "items": ({"type": "array", "items": {"type": "string"}}, [1]),
        "enum": ({"enum": ["a"]}, "b"),
        "const": ({"const": "a"}, "b"),
        "pattern": ({"type": "string", "pattern": "^a"}, "b"),
        "minLength": ({"type": "string", "minLength": 3}, "ab"),
        "minimum": ({"type": "integer", "minimum": 3}, 2),
        "uniqueItems": ({"type": "array", "uniqueItems": True}, ["a", "a"]),
    }

    def test_every_implemented_keyword_can_fail(self):
        for keyword, (schema, instance) in self.CASES.items():
            with self.subTest(keyword=keyword):
                errors = validate(instance, schema)
                self.assertTrue(
                    errors,
                    f"{keyword} accepted {instance!r} against {schema!r}; a "
                    f"keyword in SUPPORTED_KEYWORDS that never fails is not "
                    f"supported, it is decoration")

    def test_a_name_only_audit_is_not_enough(self):
        """The specific regression: audits keyword names, ignores their form.

        A checker that walks the schema, checks every key against
        SUPPORTED_KEYWORDS | ANNOTATION_KEYWORDS and stops there passes every
        other test in this file. It then meets `additionalProperties: {...}`,
        recognises the name, enforces nothing, and reports []. These rows are
        the ones it cannot survive.
        """
        for keyword, (schema, instance) in SHAPE_CASES.items():
            with self.subTest(keyword=keyword):
                with self.assertRaises(
                        UnsupportedKeyword,
                        msg=f"{keyword} appears in a form this checker does "
                            f"not enforce; recognising the name is not the "
                            f"same as enforcing the constraint"):
                    validate(instance, schema)
        with self.subTest(keyword="boolean schema"):
            with self.assertRaises(UnsupportedKeyword):
                validate({"a": 1}, {"type": "object", "properties": {"a": True}})

    def test_a_violation_is_a_non_empty_string(self):
        errors = validate({"a": 1}, {"type": "object",
                                     "properties": {"a": {"type": "string"}}})
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], str)
        self.assertTrue(errors[0].strip())


if __name__ == "__main__":
    unittest.main()
