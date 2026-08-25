"""Oracle for the composition row of ``templates/dispatch/scripts/schema_check.py``.

The previous row extracted the hand-rolled checker into a module and made it
honest: a keyword it cannot enforce raises ``UnsupportedKeyword`` instead of
being skipped in silence. That left it enforcing eleven keywords -- and left
*both* real schema files in this repo raising, because both use constructs the
checker does not implement. An honest checker that refuses everything you point
it at is honest and useless.

This row's purpose is to make both real schema files genuinely checkable:

* ``$defs`` / ``$ref``, internal pointers only. An **external** ``$ref`` cannot
  be fetched, so it must keep raising; a ``$ref`` that does not resolve must
  raise too, because treating a broken pointer as "no constraint" is the exact
  silence this module exists to end, wearing a different hat.
* ``allOf`` -- every branch holds, and every branch's violations are reported.
* ``if`` / ``then`` -- ``then`` applies only when ``if`` is satisfied. A failing
  ``if`` is a *condition*, not a violation. ``else`` is out of scope: it is
  unused in this repo and must keep raising.
* ``oneOf`` -- exactly one branch. Zero is a violation and so is two or more,
  and the two messages must be distinguishable.
* ``not`` -- the subschema must not hold.
* ``propertyNames`` -- every key of an object satisfies a subschema.
* ``minItems``, ``minProperties``, ``maximum`` -- the obvious bounds, with
  ``maximum`` mirroring ``minimum`` including that a boolean is not a number.
* ``additionalProperties`` in its **subschema** form -- every property not named
  in ``properties`` must satisfy that subschema. The other three forms are
  unchanged: ``False`` forbids extras and names each one, ``True`` and absent
  constrain nothing.

Because the subschema form is now enforced, ``additionalProperties`` drops out
of the *shape* audit entirely -- all four of its forms are handled. The other
three shape rules are untouched and still raise: ``items`` as a positional
list, ``type`` as a union list, and a bare boolean in schema position.

Three things this file exists to hold, beyond the keyword list:

1. **The audit follows composition.** The eager, total audit is the module's
   core guarantee: it walks the whole schema, including branches no instance
   reaches, because the question is whether the schema is honestly enforced.
   Once these keywords are handled the audit must descend into all of them --
   ``allOf`` branches, ``oneOf`` branches, ``not``, ``if``, ``then``,
   ``propertyNames``, an ``additionalProperties`` subschema, and every ``$defs``
   definition, referenced or not. An implementation that handles composition at
   validation time but not at audit time reintroduces the silence one level in.

2. **The payoff is real, and it is both files.** ``task-packet.schema.json``
   must return a verdict and every committed packet must validate against it
   with zero violations. ``manifest.schema.json`` must return a verdict too --
   its three ``additionalProperties`` subschema nodes become enforced
   constraints, and one of them
   (``instruction_set.properties.skill_lock.oneOf[0]``) is reachable *only*
   through ``oneOf``. So both the audit and the checker must follow ``oneOf``,
   and ``RealManifestSchemaTests`` pins that with an instance that can only be
   rejected if the constraint behind ``oneOf`` is actually applied.

3. **Recognising a keyword is not enforcing it.** See
   ``CompositionDiscriminationTests``.

Conventions follow ``test_schema_check.py``: the subject is loaded with
importlib, nothing is asserted about message *wording* (only breadcrumbs and
offending names, via ``assertIn``), and every "this must raise" claim about a
keyword outside this row's scope is conditioned on ``SUPPORTED_KEYWORDS``
membership so a later row can implement it without editing this file.

KNOWN CONFLICT, deliberately not papered over: seven tests in the previous
row's oracle (``test_schema_check.py``) assert that the *subschema* form of
``additionalProperties`` raises, three of them unconditionally, and that
``manifest.schema.json`` is refused. This row makes both false on purpose. That
file needs a coordinator hand-pass; this oracle does not restate its claims and
cannot satisfy them.
"""
from __future__ import annotations

import copy
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
DISPATCH_MANIFEST_PATH = ROOT / "agentops.dispatch.json"
PACKET_DIR = ROOT / "docs/evidence/packets"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


schema_check = _load("schema_check_composition_subject", SCRIPTS / "schema_check.py")

validate = schema_check.validate
UnsupportedKeyword = schema_check.UnsupportedKeyword

#: The keywords this row adds. A floor, not a ceiling.
COMPOSITION_FLOOR = frozenset({
    "$defs", "$ref", "allOf", "if", "then", "oneOf", "not",
    "propertyNames", "minItems", "minProperties", "maximum",
})

#: Constraint-bearing keywords still out of scope after this row. Each must
#: raise today. Conditioned on SUPPORTED_KEYWORDS below so a later row can
#: implement one -- but none of them may ever be reclassified as an annotation,
#: because every one changes which instances are valid.
STILL_UNIMPLEMENTED = (
    "else", "anyOf", "patternProperties", "dependentSchemas",
    "dependentRequired", "contains", "exclusiveMinimum", "exclusiveMaximum",
    "multipleOf", "maxItems", "maxLength", "maxProperties",
)

#: Supported keywords in a form the checker still cannot enforce, keyed by the
#: name the exception has to carry. ``additionalProperties`` is deliberately
#: absent: all four of its forms are enforced after this row.
SHAPE_DEFECTS = {
    "items": {"type": "array", "items": [{"type": "string"}, {"type": "integer"}]},
    "type": {"type": ["string", "null"]},
}

#: One of the above, for the many places that only need a single specimen.
SHAPE_DEFECT = SHAPE_DEFECTS["items"]

#: A schema node whose only defect is a keyword nobody will ever implement.
NAME_DEFECT = {"type": "string", "totallyBogusKeyword": 1}


def _handled(keyword: str) -> bool:
    return (keyword in schema_check.SUPPORTED_KEYWORDS
            or keyword in schema_check.ANNOTATION_KEYWORDS)


def _sites(defect):
    """Every composition site a defect can hide in, as whole schemas.

    Module-level so both the audit tests and the discrimination tests can walk
    the same list without one class reaching into the other.
    """
    return {
        "allOf[0]": {"allOf": [defect, {"type": "object"}]},
        "allOf[1]": {"allOf": [{"type": "object"}, defect]},
        "oneOf[0]": {"oneOf": [defect, {"type": "array"}]},
        "oneOf[1]": {"oneOf": [{"type": "array"}, defect]},
        "not": {"not": defect},
        "if": {"if": defect, "then": {"type": "object"}},
        "then": {"if": {"type": "object"}, "then": defect},
        "propertyNames": {"type": "object", "propertyNames": defect},
        "additionalProperties (subschema)": {
            "type": "object", "additionalProperties": defect,
        },
        "$defs (referenced)": {
            "properties": {"a": {"$ref": "#/$defs/thing"}},
            "$defs": {"thing": defect},
        },
        "$defs (never referenced)": {
            "type": "object", "$defs": {"orphan": defect},
        },
        "nested under properties": {
            "type": "object",
            "properties": {"a": {"allOf": [defect]}},
        },
        "nested under items": {
            "type": "array", "items": {"oneOf": [defect, {"type": "null"}]},
        },
    }


class _RaiseMixin(unittest.TestCase):

    def assert_raises_naming(self, needle, instance, schema):
        with self.assertRaises(UnsupportedKeyword) as caught:
            validate(instance, schema)
        self.assertIn(
            needle, str(caught.exception),
            "the exception must name what it could not enforce")
        return str(caught.exception)


class CompositionSurfaceTests(unittest.TestCase):
    """The keyword sets after this row: wider, still disjoint, still honest."""

    def test_the_composition_keywords_are_supported(self):
        missing = COMPOSITION_FLOOR - schema_check.SUPPORTED_KEYWORDS
        self.assertEqual(
            missing, frozenset(),
            "this row implements these; a checker that does not claim them "
            "cannot validate either real schema in this repo")

    def test_no_composition_keyword_is_parked_as_an_annotation(self):
        for keyword in sorted(COMPOSITION_FLOOR):
            with self.subTest(keyword=keyword):
                self.assertNotIn(
                    keyword, schema_check.ANNOTATION_KEYWORDS,
                    f"{keyword} changes which instances are valid, and $defs "
                    f"holds subschemas the audit must walk; calling either an "
                    f"annotation is a silent skip")

    def test_the_two_sets_are_still_disjoint(self):
        self.assertEqual(
            schema_check.SUPPORTED_KEYWORDS & schema_check.ANNOTATION_KEYWORDS,
            frozenset())

    def test_the_eleven_original_keywords_are_still_supported(self):
        original = frozenset({
            "type", "required", "properties", "additionalProperties", "items",
            "enum", "const", "pattern", "minLength", "minimum", "uniqueItems",
        })
        self.assertEqual(original - schema_check.SUPPORTED_KEYWORDS, frozenset())


class OutOfScopeKeywordTests(_RaiseMixin):
    """What this row does NOT implement must still be loud."""

    def test_each_out_of_scope_keyword_raises(self):
        for keyword in STILL_UNIMPLEMENTED:
            with self.subTest(keyword=keyword):
                if keyword in schema_check.SUPPORTED_KEYWORDS:
                    self.skipTest(f"{keyword} is now enforced; a later row's job")
                self.assert_raises_naming(
                    keyword, {}, {"type": "object", keyword: {}})

    def test_no_out_of_scope_keyword_is_parked_as_an_annotation(self):
        for keyword in STILL_UNIMPLEMENTED:
            with self.subTest(keyword=keyword):
                self.assertNotIn(keyword, schema_check.ANNOTATION_KEYWORDS)

    def test_else_specifically_raises(self):
        # Called out because it is the sibling of two keywords this row does
        # implement, and the easiest one to wave through by accident.
        if _handled("else"):
            self.skipTest("else is now handled; a later row's job")
        self.assert_raises_naming(
            "else", {},
            {"if": {"type": "object"}, "then": {"type": "object"},
             "else": {"type": "string"}})

    def test_a_keyword_no_one_will_ever_implement_still_raises(self):
        self.assert_raises_naming("totallyBogusKeyword", "x", NAME_DEFECT)


class SurvivingShapeAuditTests(_RaiseMixin):
    """The three unenforceable *forms* this row does not touch.

    ``additionalProperties`` as a subschema is now enforced and has left this
    list. The rest have not: a positional ``items`` list, a union ``type``, and
    a bare boolean in schema position are still constructs the checker cannot
    apply, and a checker that returns ``[]`` for them is certifying something it
    never looked at.
    """

    def test_each_surviving_unenforceable_form_raises(self):
        for keyword, schema in SHAPE_DEFECTS.items():
            with self.subTest(keyword=keyword):
                self.assert_raises_naming(keyword, [], schema)

    def test_a_boolean_schema_still_raises(self):
        for boolean_schema in (True, False):
            with self.subTest(schema=boolean_schema):
                with self.assertRaises(UnsupportedKeyword):
                    validate("x", boolean_schema)

    def test_a_boolean_subschema_still_raises(self):
        for schema in ({"type": "object", "properties": {"a": True}},
                       {"type": "array", "items": False}):
            with self.subTest(schema=schema):
                with self.assertRaises(UnsupportedKeyword):
                    validate({} if schema["type"] == "object" else [], schema)


class AdditionalPropertiesTests(_RaiseMixin):
    """All four forms of ``additionalProperties``, the new one included."""

    SUBSCHEMA = {
        "type": "object",
        "properties": {"named": {"type": "integer"}},
        "additionalProperties": {"type": "string", "minLength": 2},
    }

    def test_the_subschema_form_accepts_conforming_extras(self):
        self.assertEqual(
            validate({"named": 1, "extra": "ok", "other": "fine"},
                     self.SUBSCHEMA), [])

    def test_the_subschema_form_rejects_a_non_conforming_extra(self):
        errors = validate({"named": 1, "extra": 7}, self.SUBSCHEMA)
        self.assertTrue(
            errors,
            "7 is not a string; the additionalProperties subschema must be "
            "applied, not merely recognised")

    def test_the_offending_key_carries_its_own_breadcrumb(self):
        errors = validate({"extra": 7}, self.SUBSCHEMA, "$.root")
        self.assertTrue(errors, errors)
        for message in errors:
            with self.subTest(message=message):
                self.assertTrue(message.startswith("$.root.extra"), message)

    def test_named_properties_are_exempt_from_the_subschema(self):
        # `named` is an integer by its own subschema, which the
        # additionalProperties subschema would reject. `properties` wins.
        self.assertEqual(validate({"named": 1}, self.SUBSCHEMA), [])

    def test_every_offending_extra_is_reported(self):
        errors = validate({"a": 1, "b": 2}, self.SUBSCHEMA)
        self.assertGreaterEqual(len(errors), 2, errors)
        joined = " | ".join(errors)
        self.assertIn("a", joined)
        self.assertIn("b", joined)

    def test_the_subschema_form_nests(self):
        schema = {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": False,
                "required": ["enabled"],
                "properties": {"enabled": {"type": "boolean"}},
            },
        }
        self.assertEqual(validate({"cls": {"enabled": True}}, schema), [])
        self.assertTrue(validate({"cls": {}}, schema))
        self.assertTrue(validate({"cls": {"enabled": True, "x": 1}}, schema))

    def test_false_still_forbids_extras_and_names_them(self):
        schema = {"type": "object", "additionalProperties": False,
                  "properties": {"a": {"type": "string"}}}
        self.assertEqual(validate({"a": "x"}, schema), [])
        errors = validate({"a": "x", "extra": 1, "other": 2}, schema)
        self.assertEqual(len(errors), 2, errors)
        joined = " | ".join(errors)
        self.assertIn("extra", joined)
        self.assertIn("other", joined)

    def test_true_and_absent_still_constrain_nothing(self):
        for extra in ({"additionalProperties": True}, {}):
            with self.subTest(form=extra or "absent"):
                schema = {"type": "object",
                          "properties": {"a": {"type": "string"}}, **extra}
                self.assertEqual(validate({"a": "x", "anything": [1, 2]}, schema), [])

    def test_the_subschema_form_no_longer_raises(self):
        # The correction this row folds in: refusing this construct is what
        # made manifest.schema.json permanently uncheckable.
        result = validate({"anything": "x"},
                          {"type": "object",
                           "additionalProperties": {"type": "string"}})
        self.assertIsInstance(result, list)

    def test_a_defect_inside_the_subschema_still_raises(self):
        self.assert_raises_naming(
            "totallyBogusKeyword", {},
            {"type": "object", "additionalProperties": NAME_DEFECT})


class RefTests(_RaiseMixin):
    """``$defs`` and ``$ref``: internal pointers, resolved or refused."""

    SCHEMA = {
        "type": "object",
        "properties": {"pin": {"$ref": "#/$defs/sha"}},
        "$defs": {"sha": {"type": "string", "pattern": "^[0-9a-f]{4}$"}},
    }

    def test_a_ref_is_resolved_and_satisfied(self):
        self.assertEqual(validate({"pin": "abcd"}, self.SCHEMA), [])

    def test_a_ref_is_resolved_and_enforced(self):
        errors = validate({"pin": "zzzz"}, self.SCHEMA)
        self.assertTrue(
            errors, "the referenced subschema must actually be applied")
        self.assertTrue(errors[0].startswith("$.pin"), errors[0])

    def test_a_ref_inside_items(self):
        schema = {
            "type": "array",
            "items": {"$ref": "#/$defs/word"},
            "$defs": {"word": {"type": "string", "minLength": 2}},
        }
        self.assertEqual(validate(["ab", "cd"], schema), [])
        errors = validate(["ab", "c"], schema)
        self.assertTrue(errors, "a $ref inside items must be enforced")
        self.assertTrue(errors[0].startswith("$[1]"), errors[0])

    def test_defs_alone_imposes_no_constraint(self):
        # A definition nobody references constrains nothing -- but it is still
        # audited (see AuditFollowsCompositionTests).
        schema = {"type": "string", "$defs": {"unused": {"type": "integer"}}}
        self.assertEqual(validate("anything", schema), [])

    def test_an_external_ref_raises(self):
        for ref in ("https://example.invalid/other.schema.json",
                    "other.schema.json#/$defs/thing",
                    "./sibling.json"):
            with self.subTest(ref=ref):
                self.assert_raises_naming(
                    "$ref", {"pin": "abcd"},
                    {"type": "object", "properties": {"pin": {"$ref": ref}}})

    def test_a_dangling_internal_ref_raises(self):
        # Silently treating an unresolvable pointer as "no constraint" is the
        # same bug this module exists to prevent.
        self.assert_raises_naming(
            "$ref", {"pin": "abcd"},
            {"type": "object",
             "properties": {"pin": {"$ref": "#/$defs/nowhere"}},
             "$defs": {"sha": {"type": "string"}}})

    def test_a_ref_with_no_defs_at_all_raises(self):
        self.assert_raises_naming("$ref", "x", {"$ref": "#/$defs/anything"})


class AllOfTests(unittest.TestCase):
    """``allOf``: every branch holds, and every branch is heard from."""

    SCHEMA = {
        "allOf": [
            {"type": "string"},
            {"minLength": 3},
            {"pattern": "^a"},
        ],
    }

    def test_an_instance_satisfying_every_branch_passes(self):
        self.assertEqual(validate("abcd", self.SCHEMA), [])

    def test_one_failing_branch_is_a_violation(self):
        self.assertTrue(
            validate("ab", self.SCHEMA), "the minLength branch is not satisfied")

    def test_violations_from_all_branches_are_reported(self):
        errors = validate("z", self.SCHEMA)
        self.assertGreaterEqual(
            len(errors), 2,
            f"both the minLength and pattern branches fail: {errors}")

    def test_all_of_composes_with_sibling_keywords(self):
        schema = {
            "type": "object",
            "properties": {"n": {"type": "integer"}},
            "allOf": [{"required": ["n"]}],
        }
        self.assertEqual(validate({"n": 1}, schema), [])
        self.assertTrue(validate({}, schema), "the allOf branch requires n")

    def test_every_message_still_carries_the_breadcrumb(self):
        schema = {"type": "object",
                  "properties": {"a": {"allOf": [{"type": "string"},
                                                 {"minLength": 5}]}}}
        errors = validate({"a": "xx"}, schema, "$.packet")
        self.assertTrue(errors, errors)
        for message in errors:
            with self.subTest(message=message):
                self.assertTrue(message.startswith("$.packet.a"), message)


class IfThenTests(unittest.TestCase):
    """``if``/``then``: a condition, not a constraint."""

    SCHEMA = {
        "type": "object",
        "properties": {"kind": {"type": "string"}},
        "if": {"properties": {"kind": {"const": "release"}}},
        "then": {"required": ["gate_set"]},
    }

    def test_the_condition_holds_and_then_is_satisfied(self):
        self.assertEqual(
            validate({"kind": "release", "gate_set": []}, self.SCHEMA), [])

    def test_the_condition_holds_and_then_fails(self):
        errors = validate({"kind": "release"}, self.SCHEMA)
        self.assertTrue(errors, "if matched, so then must be enforced")
        self.assertIn("gate_set", " | ".join(errors))

    def test_the_condition_fails_and_then_imposes_nothing(self):
        self.assertEqual(
            validate({"kind": "ordinary"}, self.SCHEMA), [],
            "a failing `if` is a condition, not a violation")

    def test_a_failing_condition_never_becomes_a_violation_of_its_own(self):
        # The `if` subschema is deliberately unsatisfiable here. Nothing about
        # that may be reported.
        schema = {"if": {"type": "integer"}, "then": {"minimum": 10}}
        self.assertEqual(validate("a string", schema), [])

    def test_the_condition_is_evaluated_against_the_same_instance(self):
        schema = {
            "type": "object",
            "if": {"required": ["a"]},
            "then": {"required": ["b"]},
        }
        self.assertEqual(validate({}, schema), [])
        self.assertEqual(validate({"a": 1, "b": 2}, schema), [])
        self.assertTrue(validate({"a": 1}, schema))


class OneOfTests(unittest.TestCase):
    """``oneOf``: exactly one, with zero and many told apart."""

    SCHEMA = {"oneOf": [{"type": "string"}, {"type": "integer"}]}

    def test_exactly_one_match_passes(self):
        self.assertEqual(validate("x", self.SCHEMA), [])
        self.assertEqual(validate(3, self.SCHEMA), [])

    def test_zero_matches_is_a_violation(self):
        self.assertTrue(validate([], self.SCHEMA),
                        "an array matches neither branch")

    def test_two_matches_is_a_violation(self):
        schema = {"oneOf": [{"type": "string"}, {"minLength": 1}]}
        self.assertTrue(
            validate("x", schema),
            "'x' satisfies both branches; oneOf demands exactly one")

    def test_zero_and_many_are_distinguishable(self):
        none_matched = validate(3, {"oneOf": [{"type": "string"},
                                              {"type": "array"}]})
        many_matched = validate("x", {"oneOf": [{"type": "string"},
                                                {"minLength": 1}]})
        self.assertTrue(none_matched and many_matched)
        self.assertNotEqual(
            none_matched[0], many_matched[0],
            "a reader must be able to tell 'matched nothing' from 'matched "
            "more than one'; the same message for both hides which it was")

    def test_a_one_of_message_carries_the_breadcrumb(self):
        errors = validate({"a": []}, {
            "type": "object",
            "properties": {"a": {"oneOf": [{"type": "string"},
                                           {"type": "integer"}]}}})
        self.assertTrue(errors, errors)
        for message in errors:
            with self.subTest(message=message):
                self.assertTrue(message.startswith("$.a"), message)

    def test_one_of_composes_with_sibling_keywords(self):
        schema = {
            "type": "object",
            "required": ["a"],
            "oneOf": [{"required": ["b"]}, {"required": ["c"]}],
        }
        self.assertEqual(validate({"a": 1, "b": 2}, schema), [])
        self.assertTrue(validate({"a": 1, "b": 2, "c": 3}, schema))
        self.assertTrue(validate({"b": 2}, schema))


class NotTests(unittest.TestCase):
    """``not``: the subschema must fail."""

    def test_an_instance_failing_the_subschema_passes(self):
        self.assertEqual(validate("x", {"not": {"type": "integer"}}), [])

    def test_an_instance_satisfying_the_subschema_is_a_violation(self):
        self.assertTrue(
            validate(3, {"not": {"type": "integer"}}),
            "the instance satisfies the `not` subschema and must be reported")

    def test_not_of_a_constraint_free_subschema_rejects_everything(self):
        # `{}` imposes nothing, so everything satisfies it, so `not {}` is
        # satisfied by nothing.
        for instance in ("x", 1, [], {}):
            with self.subTest(instance=instance):
                self.assertTrue(validate(instance, {"not": {}}))

    def test_a_not_message_carries_the_breadcrumb(self):
        errors = validate({"a": 3}, {
            "type": "object",
            "properties": {"a": {"not": {"type": "integer"}}}})
        self.assertTrue(errors, errors)
        for message in errors:
            with self.subTest(message=message):
                self.assertTrue(message.startswith("$.a"), message)


class PropertyNamesTests(unittest.TestCase):
    """``propertyNames``: every key of an object, as a string."""

    SCHEMA = {
        "type": "object",
        "propertyNames": {"pattern": "^[A-Za-z0-9._-]+$"},
    }

    def test_conforming_keys_pass(self):
        self.assertEqual(
            validate({"repo.tests": "x", "gate-1": "y"}, self.SCHEMA), [])

    def test_an_empty_object_passes(self):
        self.assertEqual(validate({}, self.SCHEMA), [])

    def test_one_offending_key_is_reported_and_named(self):
        errors = validate({"ok": "x", "not ok!": "y"}, self.SCHEMA)
        self.assertTrue(errors, "'not ok!' does not match the key pattern")
        self.assertIn(
            "not ok!", " | ".join(errors),
            "the message must identify which key was rejected")

    def test_keys_are_checked_as_strings(self):
        # The subschema is applied to the key, never to the value.
        schema = {"type": "object",
                  "propertyNames": {"type": "string", "minLength": 3}}
        self.assertEqual(validate({"abc": 1}, schema), [])
        self.assertTrue(validate({"ab": 1}, schema))

    def test_property_names_composes_with_properties(self):
        schema = {
            "type": "object",
            "propertyNames": {"minLength": 2},
            "properties": {"ok": {"type": "integer"}},
        }
        self.assertEqual(validate({"ok": 1}, schema), [])
        self.assertTrue(validate({"ok": "not an integer"}, schema))
        self.assertTrue(validate({"x": 1}, schema))


class BoundsTests(unittest.TestCase):
    """``minItems``, ``minProperties``, ``maximum``."""

    def test_min_items_accepts_a_long_enough_array(self):
        self.assertEqual(validate(["a"], {"type": "array", "minItems": 1}), [])

    def test_min_items_rejects_a_short_array(self):
        errors = validate([], {"type": "array", "minItems": 1})
        self.assertTrue(errors, "an empty array is below minItems 1")
        self.assertTrue(errors[0].startswith("$"), errors[0])

    def test_min_items_is_not_applied_to_a_string(self):
        # len("") < 1 too, but minItems has nothing to say about a string.
        self.assertEqual(validate("", {"minItems": 1}), [])

    def test_min_properties_accepts_a_full_enough_object(self):
        self.assertEqual(
            validate({"a": 1}, {"type": "object", "minProperties": 1}), [])

    def test_min_properties_rejects_a_sparse_object(self):
        errors = validate({}, {"type": "object", "minProperties": 1})
        self.assertTrue(errors, "an empty object is below minProperties 1")
        self.assertTrue(errors[0].startswith("$"), errors[0])

    def test_maximum_accepts_a_small_enough_number(self):
        for value in (5, 4, 4.5):
            with self.subTest(value=value):
                self.assertEqual(
                    validate(value, {"type": "number", "maximum": 5}), [])

    def test_maximum_rejects_a_large_number(self):
        errors = validate(6, {"type": "integer", "maximum": 5})
        self.assertTrue(errors, "6 is above maximum 5")
        self.assertTrue(errors[0].startswith("$"), errors[0])

    def test_maximum_is_inclusive(self):
        self.assertEqual(validate(5, {"maximum": 5}), [])

    def test_maximum_is_not_applied_to_a_boolean(self):
        # True == 1 in Python. A boolean is not a number here, exactly as for
        # `minimum`; the `type` keyword is what rejects it.
        self.assertEqual(validate(True, {"maximum": 0}), [])
        self.assertEqual(validate(False, {"maximum": -1}), [])

    def test_minimum_and_maximum_bracket_together(self):
        schema = {"type": "integer", "minimum": 30, "maximum": 5400}
        self.assertEqual(validate(900, schema), [])
        self.assertTrue(validate(29, schema))
        self.assertTrue(validate(5401, schema))


class AuditFollowsCompositionTests(_RaiseMixin):
    """The sharpest tests in this row: the eager audit must descend.

    The audit is total on purpose -- it walks branches no instance reaches,
    because the question is not "did this instance pass" but "is this schema
    honestly enforced". Now that composition is implemented, an unsupported
    keyword or an unenforceable form can hide inside an ``allOf`` branch, a
    ``oneOf`` branch, a ``not``, an ``if``, a ``then``, a ``propertyNames``, an
    ``additionalProperties`` subschema, or a ``$defs`` definition. An
    implementation whose audit stops at the composition boundary reports a clean
    bill of health for a subschema it never looked at -- the same silence, one
    level further in.
    """

    def test_an_unsupported_keyword_hiding_in_composition_raises(self):
        for site, schema in _sites(NAME_DEFECT).items():
            with self.subTest(site=site):
                self.assert_raises_naming("totallyBogusKeyword", {}, schema)

    def test_an_unenforceable_form_hiding_in_composition_raises(self):
        for keyword, defect in SHAPE_DEFECTS.items():
            for site, schema in _sites(defect).items():
                with self.subTest(keyword=keyword, site=site):
                    self.assert_raises_naming(keyword, {}, schema)

    def test_a_boolean_subschema_hiding_in_composition_raises(self):
        for site, schema in _sites(True).items():
            if site.startswith("additionalProperties"):
                # `additionalProperties: true` is a legal, meaningful form
                # ("no constraint"), not a boolean standing in for a schema.
                continue
            with self.subTest(site=site):
                with self.assertRaises(UnsupportedKeyword):
                    validate({}, schema)

    def test_an_out_of_scope_keyword_hiding_in_composition_raises(self):
        for keyword in STILL_UNIMPLEMENTED:
            if keyword in schema_check.SUPPORTED_KEYWORDS:
                continue
            defect = {"type": "object", keyword: {}}
            for site, schema in _sites(defect).items():
                with self.subTest(keyword=keyword, site=site):
                    self.assert_raises_naming(keyword, {}, schema)

    def test_the_audit_runs_even_when_the_instance_fails_early(self):
        # A type violation at the root stops validation descending. It must not
        # stop the audit: the schema is what is being audited.
        schema = {"type": "object",
                  "properties": {"a": {"allOf": [NAME_DEFECT]}}}
        self.assert_raises_naming("totallyBogusKeyword", "not an object", schema)

    def test_a_clean_composition_schema_does_not_raise(self):
        # The counterweight: the audit must not have become a blanket refusal.
        schema = {
            "type": "object",
            "properties": {"a": {"$ref": "#/$defs/word"}},
            "$defs": {"word": {"type": "string", "minLength": 1}},
            "additionalProperties": {"type": "integer"},
            "allOf": [{"required": ["a"]}],
            "oneOf": [{"required": ["a"]}, {"required": ["zzz"]}],
            "not": {"required": ["forbidden"]},
            "if": {"required": ["a"]},
            "then": {"minProperties": 1},
            "propertyNames": {"pattern": "^[a-z]+$"},
        }
        self.assertEqual(validate({"a": "x"}, schema), [])


class RealTaskPacketSchemaTests(unittest.TestCase):
    """Payoff, part one: the packet schema becomes enforceable, end to end.

    ``task-packet.schema.json`` uses ``$defs``, ``$ref``, ``allOf``,
    ``if``/``then``, ``minItems`` and ``maximum``. Before this row the checker
    refused it outright, so nothing in this repo could actually be validated
    against the schema it declares. After this row it must return a verdict --
    and the verdict on every committed packet must be clean.
    """

    @classmethod
    def setUpClass(cls):
        assert TASK_PACKET_SCHEMA_PATH.is_file(), TASK_PACKET_SCHEMA_PATH
        cls.schema = json.loads(
            TASK_PACKET_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.packet_paths = sorted(PACKET_DIR.glob("*.json"))

    def test_there_are_packets_to_check(self):
        # Guards the whole class against passing vacuously if the directory
        # moves or the glob stops matching.
        self.assertTrue(
            self.packet_paths,
            f"no packets found under {PACKET_DIR}; the end-to-end proof below "
            f"would pass by matching nothing")

    def test_the_schema_still_uses_the_composition_keywords(self):
        # The anchor for this class. If the schema is ever rewritten without
        # composition, the tests below stop proving anything -- and this one
        # says so out loud instead of passing quietly.
        self.assertIn("$defs", self.schema)
        self.assertIsInstance(self.schema["allOf"], list)
        self.assertTrue(self.schema["allOf"])
        first = self.schema["allOf"][0]
        self.assertIn("if", first)
        self.assertIn("then", first)
        self.assertIn(
            "$ref", json.dumps(first["then"]),
            "the conditional branch is expected to reach a $defs definition")

    def test_the_schema_returns_a_verdict_instead_of_raising(self):
        result = validate({}, self.schema)
        self.assertIsInstance(
            result, list,
            "the packet schema must be checkable after this row; refusing it "
            "is what made the checker useless")

    def test_every_committed_packet_validates_with_zero_violations(self):
        for packet_path in self.packet_paths:
            with self.subTest(packet=packet_path.name):
                packet = json.loads(packet_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    validate(packet, self.schema), [],
                    f"{packet_path.name} does not satisfy "
                    f"task-packet.schema.json")

    def _a_real_packet(self):
        return copy.deepcopy(
            json.loads(self.packet_paths[0].read_text(encoding="utf-8")))

    def test_the_conditional_defs_branch_actually_bites(self):
        # allOf -> if -> then -> $ref, exercised against the real file. Every
        # committed packet is schema_version v2, whose acceptance properties
        # must carry a stable `id`. Remove it and the v2 branch must object.
        packet = self._a_real_packet()
        self.assertEqual(packet["schema_version"], "agentops-task/v2")
        self.assertTrue(packet["acceptance_properties"])
        removed = packet["acceptance_properties"][0].pop("id", None)
        self.assertIsNotNone(
            removed, "the anchor: a v2 acceptance property carries an id")
        self.assertTrue(
            validate(packet, self.schema),
            "the v2 branch of the schema's allOf/if/then/$ref requires an id "
            "on every acceptance property; a checker that reports [] here has "
            "walked past the whole composition")

    def test_the_other_conditional_branch_selects_differently(self):
        # Same packet, relabelled v1. The v1 definition is closed and has no
        # `id`, so the *other* branch must now object -- which is only possible
        # if `if` really is discriminating on schema_version.
        packet = self._a_real_packet()
        packet["schema_version"] = "agentops-task/v1"
        self.assertTrue(
            validate(packet, self.schema),
            "a v2-shaped acceptance property under the v1 label must be "
            "rejected by the v1 definition")

    def test_a_real_maximum_in_the_schema_bites(self):
        packet = self._a_real_packet()
        ceiling = self.schema["properties"]["limits"]["properties"][
            "timeout_seconds"]["maximum"]
        packet["limits"]["timeout_seconds"] = ceiling + 1
        self.assertTrue(
            validate(packet, self.schema),
            "timeout_seconds carries a maximum in the real schema")

    def test_a_real_min_items_in_the_schema_bites(self):
        packet = self._a_real_packet()
        self.assertEqual(
            self.schema["properties"]["readable_context_paths"]["minItems"], 1)
        packet["readable_context_paths"] = []
        self.assertTrue(
            validate(packet, self.schema),
            "readable_context_paths carries minItems 1 in the real schema")


class RealManifestSchemaTests(unittest.TestCase):
    """Payoff, part two: ``manifest.schema.json`` becomes checkable too.

    It carries the subschema form of ``additionalProperties`` in three nodes.
    Two are plain ``properties`` descents; the third
    (``instruction_set.properties.skill_lock.oneOf[0]``) sits behind ``oneOf``,
    so both the audit and the checker have to follow composition to reach it.
    Each node's anchor is asserted separately, so a rewrite of the manifest
    fails loudly rather than making these tests vacuous.
    """

    @classmethod
    def setUpClass(cls):
        assert MANIFEST_SCHEMA_PATH.is_file(), MANIFEST_SCHEMA_PATH
        cls.manifest = json.loads(
            MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))

    def _node(self, *keys):
        node = self.manifest
        for key in keys:
            self.assertIsInstance(
                node, (dict, list),
                f"manifest.schema.json no longer has a node at {keys}")
            node = node[key]
        return node

    def _action_classes(self):
        return self._node("properties", "routing", "properties", "action_classes")

    def _commands(self):
        return self._node("properties", "hybrid", "properties", "commands")

    def _skill_lock(self):
        return self._node("properties", "instruction_set", "properties",
                          "skill_lock")

    def test_the_three_subschema_nodes_are_still_there(self):
        # The anchors. Kept from when these were "shape defects": they are what
        # makes every assertion below about a real construct rather than a
        # hypothetical one.
        self.assertIsInstance(
            self._action_classes()["additionalProperties"], dict,
            "routing.action_classes is expected to use the subschema form")
        self.assertIsInstance(
            self._commands()["additionalProperties"], dict,
            "hybrid.commands is expected to use the subschema form")
        skill_lock = self._skill_lock()
        self.assertIsInstance(skill_lock["oneOf"], list)
        self.assertIsInstance(
            skill_lock["oneOf"][0]["additionalProperties"], dict,
            "instruction_set.skill_lock.oneOf[0] is expected to use the "
            "subschema form -- this is the node reachable only through oneOf")

    def test_the_whole_manifest_schema_returns_a_verdict(self):
        result = validate({}, self.manifest)
        self.assertIsInstance(
            result, list,
            "a manifest schema that always raises cannot validate anything; "
            "this row exists to end that")

    def test_the_action_classes_node_enforces_its_subschema(self):
        node = self._action_classes()
        self.assertEqual(validate({"mechanical_bulk": {"enabled": True}}, node), [])
        self.assertTrue(
            validate({"mechanical_bulk": {"enabled": "yes"}}, node),
            "'yes' is not a boolean; the value subschema must be applied")
        self.assertTrue(
            validate({"mechanical_bulk": {}}, node),
            "the value subschema requires `enabled`")
        self.assertTrue(
            validate({}, node), "the node carries minProperties")

    def test_the_commands_node_enforces_its_subschema_and_key_rules(self):
        node = self._commands()
        self.assertEqual(validate({"repo.tests": "python3 -m unittest"}, node), [])
        self.assertTrue(
            validate({"repo.tests": ""}, node),
            "an empty command violates minLength inside the value subschema")
        self.assertTrue(
            validate({"not a command id": "x"}, node),
            "the key violates propertyNames")
        self.assertTrue(validate({}, node), "the node carries minProperties")

    def test_the_one_of_reachable_node_enforces_its_subschema(self):
        # The sharpest one. This constraint exists only inside oneOf[0]. If the
        # checker ignores the additionalProperties subschema there, branch 0
        # degenerates to "is an object" -- which this instance satisfies -- so
        # oneOf sees exactly one match and reports nothing. The only way to
        # produce a violation here is to actually apply the digest pattern.
        node = self._skill_lock()
        self.assertTrue(
            validate({"some-skill": "not-a-sha256"}, node),
            "a bad digest must be rejected; a checker that skips the "
            "additionalProperties subschema behind oneOf reports [] here")

    def test_the_one_of_reachable_node_accepts_a_conforming_instance(self):
        node = self._skill_lock()
        self.assertEqual(validate({"some-skill": "0" * 64}, node), [])

    def test_the_sibling_one_of_branch_still_works(self):
        node = self._skill_lock()
        self.assertEqual(
            validate([{"id": "s", "digest": "0" * 64}], node), [],
            "the array branch of skill_lock must still be satisfiable")

    def test_the_manifest_composition_keywords_are_all_supported(self):
        for keyword in ("oneOf", "not", "propertyNames", "minProperties",
                        "minItems", "maximum", "if", "then", "$defs", "$ref",
                        "allOf", "additionalProperties"):
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, schema_check.SUPPORTED_KEYWORDS)


class RealDispatchManifestTests(unittest.TestCase):
    """The repo's own manifest, checked against its schema.

    Retired and replaced by the coordinator on 2026-08-25, in the open. This
    class was written while ``agentops.dispatch.json`` was NOT clean --
    ``skills.selected`` carried ``dispatch-wave`` and ``session-handover``,
    which the schema's enum did not admit. That drift is what this whole tract
    set out to find, and pinning it was right while it stood. Its author built
    it to fail loudly rather than go quiet when the fix landed, with the
    message "the hand-pass has landed and this test needs retiring, not
    silence". It did exactly that, which is why this class is being rewritten
    instead of deleted.

    The hand-pass added the three real skills to the enum, so the historical
    anchors are now false and worthless. What replaces them is the invariant
    that made the drift worth finding in the first place, and it is strictly
    stronger: the enum is a copy of a directory listing, so it must agree with
    the directory, and the manifest must not select a skill the schema refuses.
    Those hold forever and fail the next time someone adds a skill and forgets
    the schema -- which is precisely how this drift happened.
    """

    @classmethod
    def setUpClass(cls):
        assert MANIFEST_SCHEMA_PATH.is_file(), MANIFEST_SCHEMA_PATH
        assert DISPATCH_MANIFEST_PATH.is_file(), DISPATCH_MANIFEST_PATH
        cls.schema = json.loads(
            MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.manifest = json.loads(
            DISPATCH_MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.skills_dir = MANIFEST_SCHEMA_PATH.parent / "skills"

    def _enum(self):
        return self.schema["properties"]["skills"]["properties"]["selected"][
            "items"]["enum"]

    def test_the_manifest_is_checkable_at_all(self):
        result = validate(self.manifest, self.schema)
        self.assertIsInstance(
            result, list,
            "the repo's own manifest must be checkable against its own schema")

    def test_the_repo_manifest_now_satisfies_its_own_schema(self):
        self.assertEqual(
            validate(self.manifest, self.schema), [],
            "agentops.dispatch.json is read by every dispatch in this repo; it "
            "must satisfy the schema that describes it")

    def test_the_enum_and_the_skills_directory_agree(self):
        # The enum duplicates a directory listing, which is why it drifted. A
        # name on disk and not in the enum makes a legitimate manifest invalid;
        # a name in the enum and not on disk admits a selection that cannot be
        # materialised. Both are the same bug and both fail here.
        on_disk = {entry.name for entry in self.skills_dir.iterdir()
                   if entry.is_dir()}
        self.assertTrue(on_disk, f"no skills found under {self.skills_dir}")
        enum = set(self._enum())
        self.assertEqual(
            sorted(on_disk - enum), [],
            "skills exist on disk that the schema's enum does not admit")
        self.assertEqual(
            sorted(enum - on_disk), [],
            "the schema's enum names skills that do not exist on disk")

    def test_every_selected_skill_is_admitted_and_present(self):
        selected = self.manifest["skills"]["selected"]
        self.assertTrue(selected, "the manifest selects no skills at all")
        enum = set(self._enum())
        for name in selected:
            with self.subTest(skill=name):
                self.assertIn(name, enum,
                              f"{name} is selected but the schema refuses it")
                self.assertTrue(
                    (self.skills_dir / name).is_dir(),
                    f"{name} is selected but no such skill exists on disk")

    def test_the_check_is_not_vacuous(self):
        # If validate answered [] to everything, every assertion above would
        # pass. One planted violation, on the field that actually drifted.
        drifted = json.loads(json.dumps(self.manifest))
        drifted["skills"]["selected"] = ["not-a-real-skill"]
        self.assertTrue(
            validate(drifted, self.schema),
            "a selected skill outside the enum must still be reported")



class CompositionDiscriminationTests(_RaiseMixin):
    """Tests a keyword-recognising, constraint-free implementation cannot pass.

    This is the class that makes the rest of the row mean something. The
    cheapest way to turn every test above green is to add the new keywords to
    ``SUPPORTED_KEYWORDS``, teach the audit to walk past them, and enforce
    nothing -- at which point ``validate`` returns ``[]`` for every instance and
    both real schemas look pristine. That is precisely the silence this module
    was built to eliminate, restored under a longer keyword list. The
    ``additionalProperties`` subschema form is the most tempting one to fake,
    because "recognise it and stop raising" is a one-line change that makes
    ``manifest.schema.json`` checkable and enforces nothing.

    So every new keyword and form gets at least one instance here that MUST
    produce a violation. If an implementation recognises a keyword and never
    rejects anything with it, the keyword is not supported -- it is decoration.
    """

    MUST_FAIL = {
        "allOf (one branch fails)": (
            {"allOf": [{"type": "string"}, {"minLength": 5}]}, "abc"),
        "if/then (condition holds, then fails)": (
            {"if": {"required": ["a"]}, "then": {"required": ["b"]}}, {"a": 1}),
        "oneOf (zero matches)": (
            {"oneOf": [{"type": "string"}, {"type": "array"}]}, 7),
        "oneOf (two matches)": (
            {"oneOf": [{"type": "string"}, {"minLength": 1}]}, "x"),
        "not (subschema holds)": ({"not": {"type": "integer"}}, 7),
        "propertyNames (one key violates)": (
            {"type": "object", "propertyNames": {"pattern": "^[a-z]+$"}},
            {"ok": 1, "NOT OK": 2}),
        "minItems": ({"type": "array", "minItems": 2}, ["only one"]),
        "minProperties": ({"type": "object", "minProperties": 2}, {"a": 1}),
        "maximum": ({"type": "integer", "maximum": 5}, 6),
        "$ref (referenced constraint fails)": (
            {"properties": {"a": {"$ref": "#/$defs/word"}},
             "$defs": {"word": {"type": "string", "minLength": 3}}},
            {"a": "xy"}),
        "additionalProperties (subschema)": (
            {"type": "object", "additionalProperties": {"type": "string"}},
            {"extra": 7}),
        "additionalProperties (subschema behind oneOf)": (
            {"oneOf": [
                {"type": "object",
                 "additionalProperties": {"type": "string",
                                          "pattern": "^[0-9a-f]{64}$"}},
                {"type": "array"},
            ]},
            {"skill": "not-a-sha"}),
    }

    def test_every_new_keyword_can_actually_fail(self):
        for label, (schema, instance) in self.MUST_FAIL.items():
            with self.subTest(case=label):
                errors = validate(instance, schema)
                self.assertTrue(
                    errors,
                    f"{label}: accepted {instance!r} against {schema!r}; a "
                    f"keyword in SUPPORTED_KEYWORDS that never fails is not "
                    f"supported, it is decoration")

    def test_every_violation_is_a_non_empty_prefixed_string(self):
        for label, (schema, instance) in self.MUST_FAIL.items():
            with self.subTest(case=label):
                for message in validate(instance, schema, "$.root"):
                    self.assertIsInstance(message, str)
                    self.assertTrue(message.strip())
                    self.assertTrue(message.startswith("$.root"), message)

    def test_recognising_a_composition_keyword_is_not_walking_into_it(self):
        """The regression this row is most likely to be broken into.

        An implementation that enforces composition at validation time but
        audits only the top level passes every happy-path test above and then
        certifies a schema whose ``oneOf`` branch it never inspected.
        """
        for keyword, defect in SHAPE_DEFECTS.items():
            for site, schema in _sites(defect).items():
                with self.subTest(keyword=keyword, site=site):
                    with self.assertRaises(
                            UnsupportedKeyword,
                            msg=f"a {keyword} defect inside {site} was not "
                                f"audited"):
                        validate({}, schema)

    def test_an_external_ref_is_never_quietly_dropped(self):
        with self.assertRaises(
                UnsupportedKeyword,
                msg="an unfetchable $ref treated as 'no constraint' is the "
                    "silent skip this module exists to prevent"):
            validate({"a": 1}, {"type": "object",
                                "properties": {"a": {"$ref": "https://x/y.json"}}})


if __name__ == "__main__":
    unittest.main()
