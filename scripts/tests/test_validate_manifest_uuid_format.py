"""``authority_repo_uuid`` must be a UUID when present, and absent when absent.

``schemas/dispatch-manifest.schema.json`` declares ``"format": "uuid"`` on
``authority_repo_uuid``. But ``format`` is an annotation keyword by default --
correct JSON Schema, and it meant the checker would happily certify a
non-UUID unless the caller opts in with ``assert_formats``. That is the
"certifying what was never checked" defect V6-I was written to end, and
``validate_dispatch_manifest.py`` is the caller that opts in
(``ASSERTED_SCHEMA_FORMATS = ("uuid",)``).

Two boundaries are deliberate and are pinned here rather than left to be
rediscovered:

* **The field stays optional.** Most manifests in the fleet carry none.
  Requiring one is a separate and much larger claim, and it should not ride
  along on a format decision. An absent value passes.
* **A present value must be what the schema says it is.**

The checker itself is imported from ``schema_check.FORMAT_CHECKERS`` rather
than restated, so this file exercises the one enforcement path that still
exists: ``schema_check`` plus ``validate_dispatch_manifest.py``'s asserted
formats.

This is the non-hybrid remainder of the original file. S2 item 6 deleted
``validate_hybrid_dispatch.py`` along with the
rest of the hybrid-dispatch path (TS-2: "both dispatch paths retire"; see
docs/plans/2026-09-17-target-state.md), and it is not part of the goal-state
restore. The cases that depended on ``validate_hybrid_dispatch``'s own
stricter (canonical-only, case-sensitive) UUID rule -- distinct from
``schema_check``'s spec-compliant, case-insensitive one -- went with it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts"
SCHEMA_PATH = ROOT / "schemas/dispatch-manifest.schema.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


manifest_validator = _load_module(
    "uuid_format_manifest_validator", SCRIPTS / "validate_dispatch_manifest.py")
schema_check = manifest_validator.schema_check

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
VALID = "1308d624-3413-4327-a891-9d9cdfc2d4ea"


def _clean_manifest():
    """The smallest manifest the schema admits, as a v1 document."""
    return {
        "schema_version": 1,
        "repo_id": "fixture-repo",
        "adoption_level": "observable",
        "routing": {
            "default_harness": "claude",
            "default_model_alias": "fast-build",
            "action_classes": {"build": {"enabled": True}},
        },
        "skills": {"selected": ["dispatch-build"]},
        "verification": {"command_families": ["unit"]},
        "hooks": {"level": "audit", "publishers": ["git"]},
    }


def _check(value, present=True):
    """Validate an otherwise-clean manifest carrying (or not) authority_repo_uuid."""
    instance = _clean_manifest()
    if present:
        instance["authority_repo_uuid"] = value
    return schema_check.validate(
        instance, SCHEMA, assert_formats=manifest_validator.ASSERTED_SCHEMA_FORMATS)


class AcceptedTests(unittest.TestCase):

    def test_a_valid_uuid_passes(self):
        self.assertEqual(_check(VALID), [])

    def test_an_absent_field_passes(self):
        # The field is optional and stays optional. This is the assertion
        # that would fail first if someone later conflated "assert the
        # format" with "require the field".
        self.assertEqual(_check(None, present=False), [])

    def test_an_uppercase_uuid_is_accepted(self):
        # schema_check.FORMAT_CHECKERS["uuid"] follows the JSON Schema spec,
        # which is case-insensitive; unlike the retired hybrid-dispatch
        # checker, nothing in the kept path is stricter than that.
        self.assertEqual(_check(VALID.upper()), [])


class RejectedTests(unittest.TestCase):

    def test_a_malformed_value_is_rejected(self):
        errors = _check("not-a-uuid")
        self.assertTrue(errors)
        self.assertTrue(any("authority_repo_uuid" in e for e in errors))

    def test_the_urn_and_unhyphenated_spellings_are_rejected(self):
        for spelling in (f"urn:uuid:{VALID}", VALID.replace("-", "")):
            with self.subTest(spelling=spelling):
                self.assertTrue(_check(spelling))

    def test_a_non_string_is_rejected(self):
        for value in (12345, ["a"], {"a": 1}, True):
            with self.subTest(value=value):
                self.assertTrue(_check(value))

    def test_an_empty_string_is_rejected(self):
        self.assertTrue(_check(""))


class ProvenanceTests(unittest.TestCase):

    def test_the_format_is_actually_asserted(self):
        # Passing assert_formats is what turns the schema's "format": "uuid"
        # claim from an annotation into an enforced check; without it this
        # whole file would be silently vacuous.
        self.assertIn("uuid", manifest_validator.ASSERTED_SCHEMA_FORMATS)

    def test_uuid_has_a_registered_checker(self):
        self.assertIn("uuid", schema_check.FORMAT_CHECKERS)


class TheRealManifestsTests(unittest.TestCase):
    """Every committed manifest must satisfy what was just turned on."""

    def test_every_dispatch_manifest_in_the_repo_passes(self):
        manifests = sorted(ROOT.glob("*.dispatch.json"))
        self.assertGreater(len(manifests), 0)
        for path in manifests:
            with self.subTest(manifest=path.name):
                instance = json.loads(path.read_text())
                errors = schema_check.validate(
                    instance, SCHEMA,
                    assert_formats=manifest_validator.ASSERTED_SCHEMA_FORMATS)
                self.assertEqual(errors, [])

    def test_this_repos_manifest_carries_a_uuid(self):
        # agentops is the authority repo; if its own identity stopped being a
        # UUID the assertion above would be vacuous for the one manifest that
        # matters most.
        manifest = json.loads((ROOT / "agentops.dispatch.json").read_text())
        self.assertIsInstance(manifest.get("authority_repo_uuid"), str)


if __name__ == "__main__":
    unittest.main()
