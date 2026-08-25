"""Coordinator-authored oracle: opt-in format assertion for schema_check.

Recorded debt: `schema_check` lists `format` among its annotation keywords.
That is *correct* JSON Schema -- format is an annotation unless a validator
opts into asserting it -- but it means `manifest.schema.json`'s
`"format": "uuid"` on `authority_repo_uuid` is formally unchecked, and the
checker will certify a non-UUID there while claiming to enforce every construct
it accepts.

The repair is not to start asserting formats. `validate` is on the live
dispatch path and every manifest in `/projects/dev` is checked with it, so
turning assertion on by default would change what production accepts as a side
effect of paying a documentation debt. The repair is to let a caller *ask*.

The subject is `templates/dispatch/scripts/schema_check.py`, which gains:

    FORMAT_CHECKERS
        A mapping from format name to a predicate over a string. It must
        contain "uuid". A caller can read it to discover what can be asserted.

    validate(instance, schema, path="$", assert_formats=())
        `assert_formats` names the formats to enforce. Empty -- the default --
        must behave exactly as today, because that is what production calls.

Two rules make this honest rather than decorative:

* a format named in `assert_formats` with no checker in `FORMAT_CHECKERS`
  raises `UnsupportedKeyword`. Silently ignoring it is precisely the defect
  being repaired -- certifying what was never checked.
* `format` applies only to strings. A non-string instance is unaffected, per
  the specification; the type keyword is what constrains type.

Rule 11: the subject is `schema_check.py`. No git, no subprocess, no file I/O.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load_module("schema_check_formats_subject", SCRIPTS / "schema_check.py")

UUID_SCHEMA = {"type": "string", "format": "uuid"}
GOOD_UUID = "1deb57d0-af6f-479c-811a-b5b7254841f9"


class RegistryTests(unittest.TestCase):
    def test_the_registry_exists_and_names_uuid(self):
        self.assertIn("uuid", checker.FORMAT_CHECKERS)

    def test_the_registry_maps_names_to_predicates(self):
        self.assertTrue(callable(checker.FORMAT_CHECKERS["uuid"]))

    def test_format_is_still_an_annotation_keyword(self):
        # It must stay an annotation: a schema may name a format nobody asserts
        # and must not become unauditable for it.
        self.assertIn("format", checker.ANNOTATION_KEYWORDS)


class DefaultBehaviourTests(unittest.TestCase):
    """The default is what production calls. It must not move."""

    def test_a_bad_uuid_passes_when_no_format_is_asserted(self):
        self.assertEqual(checker.validate("not-a-uuid", UUID_SCHEMA), [])

    def test_a_bad_uuid_passes_with_an_empty_assert_formats(self):
        self.assertEqual(checker.validate("not-a-uuid", UUID_SCHEMA, assert_formats=()), [])

    def test_the_real_manifest_schema_still_audits_clean(self):
        import json
        schema = json.loads((ROOT / "templates/dispatch/manifest.schema.json").read_text())
        self.assertEqual(checker.audit_schema(schema), [])


class AssertedFormatTests(unittest.TestCase):
    def test_a_good_uuid_passes_when_asserted(self):
        self.assertEqual(
            checker.validate(GOOD_UUID, UUID_SCHEMA, assert_formats=("uuid",)), []
        )

    def test_a_bad_uuid_fails_when_asserted(self):
        errors = checker.validate("not-a-uuid", UUID_SCHEMA, assert_formats=("uuid",))
        self.assertEqual(len(errors), 1)

    def test_the_error_names_the_path_and_the_format(self):
        errors = checker.validate("nope", UUID_SCHEMA, assert_formats=("uuid",), path="$.id")
        self.assertIn("$.id", errors[0])
        self.assertIn("uuid", errors[0])

    def test_assert_formats_accepts_any_iterable(self):
        for value in (["uuid"], ("uuid",), {"uuid"}, frozenset({"uuid"})):
            self.assertEqual(len(checker.validate("nope", UUID_SCHEMA, assert_formats=value)), 1)

    def test_a_format_not_named_is_not_asserted(self):
        schema = {"type": "string", "format": "date-time"}
        self.assertEqual(checker.validate("nonsense", schema, assert_formats=("uuid",)), [])

    def test_a_nested_property_is_asserted_too(self):
        schema = {"type": "object", "properties": {"id": UUID_SCHEMA}}
        errors = checker.validate({"id": "nope"}, schema, assert_formats=("uuid",))
        self.assertEqual(len(errors), 1)
        self.assertIn("id", errors[0])

    def test_items_are_asserted_too(self):
        schema = {"type": "array", "items": UUID_SCHEMA}
        errors = checker.validate([GOOD_UUID, "nope"], schema, assert_formats=("uuid",))
        self.assertEqual(len(errors), 1)


class UnknownFormatTests(unittest.TestCase):
    def test_asserting_a_format_with_no_checker_raises(self):
        # Certifying what was never checked is the defect being repaired; a
        # caller that asks for an unavailable assertion must be told, not
        # quietly given nothing.
        with self.assertRaises(checker.UnsupportedKeyword):
            checker.validate("x", {"type": "string", "format": "ipv6"},
                             assert_formats=("ipv6",))

    def test_asking_for_an_unknown_format_raises_even_when_absent_from_the_schema(self):
        with self.assertRaises(checker.UnsupportedKeyword):
            checker.validate("x", {"type": "string"}, assert_formats=("ipv6",))


class UuidCheckerTests(unittest.TestCase):
    def test_the_canonical_form_is_accepted(self):
        self.assertTrue(checker.FORMAT_CHECKERS["uuid"](GOOD_UUID))

    def test_uppercase_is_accepted(self):
        self.assertTrue(checker.FORMAT_CHECKERS["uuid"](GOOD_UUID.upper()))

    def test_the_urn_form_is_rejected(self):
        self.assertFalse(checker.FORMAT_CHECKERS["uuid"]("urn:uuid:" + GOOD_UUID))

    def test_the_braced_form_is_rejected(self):
        self.assertFalse(checker.FORMAT_CHECKERS["uuid"]("{" + GOOD_UUID + "}"))

    def test_a_wrong_length_is_rejected(self):
        self.assertFalse(checker.FORMAT_CHECKERS["uuid"](GOOD_UUID[:-1]))

    def test_a_non_hex_character_is_rejected(self):
        self.assertFalse(checker.FORMAT_CHECKERS["uuid"](GOOD_UUID[:-1] + "z"))

    def test_missing_hyphens_are_rejected(self):
        self.assertFalse(checker.FORMAT_CHECKERS["uuid"](GOOD_UUID.replace("-", "")))


class NonStringTests(unittest.TestCase):
    """format applies to strings only. The type keyword constrains type."""

    def test_a_number_is_not_a_format_violation(self):
        schema = {"format": "uuid"}
        self.assertEqual(checker.validate(7, schema, assert_formats=("uuid",)), [])

    def test_a_null_is_not_a_format_violation(self):
        schema = {"format": "uuid"}
        self.assertEqual(checker.validate(None, schema, assert_formats=("uuid",)), [])


if __name__ == "__main__":
    unittest.main()
