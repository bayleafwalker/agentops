"""``authority_repo_uuid`` must be a UUID when present, and absent when absent.

``manifest.schema.json`` has declared ``"format": "uuid"`` on
``authority_repo_uuid`` since it was written. But ``format`` is an annotation
keyword by default -- correct JSON Schema, and it meant the checker would
happily certify a non-UUID. The schema made a claim the repository did not keep.
That is the "certifying what was never checked" defect V6-I was written to end,
and this is the caller that opts in.

Two boundaries are deliberate and are pinned here rather than left to be
rediscovered:

* **The field stays optional.** Ten of eighteen manifests carry none. Requiring
  one is a separate and much larger claim -- that every hybrid-eligible
  repository must carry an authority identity -- and it should not ride along on
  a format decision. An absent value passes.
* **A present value must be what the schema says it is.** Measured before this
  was turned on: eight manifests carry the field and all eight were already
  valid, so this rejects nothing that exists and constrains only what is written
  next.

The checker itself is imported from ``schema_check.FORMAT_CHECKERS`` rather than
restated. A second copy of a pattern is how two functions answering the same
question drift apart -- the defect this repo has already had to undo once
(``_path_allowed`` versus ``_matches_any``), and the reason ``churn_metrics``
imports ``MUTATION_TOOLS``. ``test_the_checker_is_the_registered_one`` pins it.

Rule 11: this file imports ``validate_hybrid_dispatch`` and ``schema_check`` and
nothing else of the repo's own; it runs no git and no subprocess.
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


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validator = _load_module("uuid_format_validator", SCRIPTS / "validate_hybrid_dispatch.py")
schema_check = _load_module("uuid_format_schema_check", SCRIPTS / "schema_check.py")

MANIFEST = Path("some-repo.dispatch.json")
VALID = "1308d624-3413-4327-a891-9d9cdfc2d4ea"


def _check(value, present=True):
    manifest = {"authority_repo_uuid": value} if present else {}
    validator.validate_manifest_identity(manifest, MANIFEST)


class AcceptedTests(unittest.TestCase):

    def test_a_valid_uuid_passes(self):
        _check(VALID)

    def test_an_absent_field_passes(self):
        # The field is optional and stays optional. This is the assertion that
        # would fail first if someone later conflated "assert the format" with
        # "require the field".
        _check(None, present=False)

    def test_an_uppercase_uuid_is_rejected_as_non_canonical(self):
        # JSON Schema's uuid format is case-insensitive, and schema_check's
        # generic checker follows the spec. This repository is stricter:
        # validate_verification_artifacts.py:172 has always compared against
        # str(UUID(v)) and rejected any non-canonical spelling. Accepting
        # uppercase here would let one manifest pass one validator and fail the
        # other, which is exactly the drift this file's docstring warns about.
        with self.assertRaisesRegex(ValueError, "canonical"):
            _check(VALID.upper())


class RejectedTests(unittest.TestCase):

    def test_a_malformed_value_is_rejected(self):
        with self.assertRaises(ValueError) as caught:
            _check("not-a-uuid")
        self.assertIn("authority_repo_uuid", str(caught.exception))
        self.assertIn(str(MANIFEST), str(caught.exception))

    def test_an_explicit_null_is_treated_as_absent(self):
        # A null is how JSON spells "no value". Rejecting it would make a
        # manifest that spells the absence explicitly fail where one that omits
        # the key passes, which is a distinction without a difference.
        _check(None)

    def test_the_urn_braced_and_unhyphenated_spellings_are_rejected(self):
        for spelling in (
            f"urn:uuid:{VALID}",
            "{" + VALID + "}",
            VALID.replace("-", ""),
        ):
            with self.subTest(spelling=spelling):
                with self.assertRaises(ValueError):
                    _check(spelling)

    def test_a_non_string_is_rejected(self):
        for value in (12345, ["a"], {"a": 1}, True):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    _check(value)

    def test_an_empty_string_is_rejected(self):
        with self.assertRaises(ValueError):
            _check("")


class ProvenanceTests(unittest.TestCase):

    def test_the_checker_is_the_registered_one(self):
        # Not a second copy of the pattern. Identity cannot be asserted across
        # two independent by-path loads of schema_check -- each produces its own
        # function object -- so this pins the two things that do hold: the
        # validator takes its checker out of FORMAT_CHECKERS by name, and the
        # two agree on every value that distinguishes a uuid checker from a
        # rubber stamp.
        mine = validator._format_checker("uuid")
        theirs = schema_check.FORMAT_CHECKERS["uuid"]
        self.assertEqual(mine.__name__, theirs.__name__)
        for value in (VALID, "not-a-uuid", "",
                      VALID.replace("-", ""), f"urn:uuid:{VALID}"):
            with self.subTest(value=value):
                self.assertEqual(mine(value), theirs(value))

    def test_an_unregistered_format_raises_rather_than_certifying(self):
        with self.assertRaises(ValueError):
            validator._format_checker("definitely-not-a-format")

    def test_every_asserted_format_has_a_checker(self):
        # A mapping of {field: format}, so what is declared is what is checked.
        # The earlier bare tuple could gain a name that asserted nothing while
        # this test still passed.
        self.assertTrue(validator.ASSERTED_MANIFEST_FORMATS)
        for field, name in validator.ASSERTED_MANIFEST_FORMATS.items():
            with self.subTest(field=field, fmt=name):
                self.assertIn(name, schema_check.FORMAT_CHECKERS)

    def test_the_asserted_mapping_is_what_actually_gets_checked(self):
        # Drives the assertion from the constant: every declared field really is
        # rejected when malformed.
        for field in validator.ASSERTED_MANIFEST_FORMATS:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    validator.validate_manifest_identity({field: "not-valid"}, MANIFEST)

    def test_it_agrees_with_the_other_uuid_rule_in_this_repo(self):
        # validate_verification_artifacts.py:172 is the pre-existing rule. The
        # two must accept and reject the same spellings, or a manifest passes
        # one gate and fails the other.
        import uuid as _uuid
        for value in (VALID, VALID.upper(), "not-a-uuid", VALID.replace("-", "")):
            with self.subTest(value=value):
                try:
                    canonical = str(_uuid.UUID(value))
                    theirs_ok = (value == canonical)
                except Exception:
                    theirs_ok = False
                try:
                    _check(value)
                    mine_ok = True
                except ValueError:
                    mine_ok = False
                self.assertEqual(mine_ok, theirs_ok)


class TheRealManifestsTests(unittest.TestCase):
    """Every committed manifest must satisfy what was just turned on."""

    def test_every_dispatch_manifest_in_the_repo_passes(self):
        manifests = sorted(ROOT.glob("*.dispatch.json"))
        self.assertGreater(len(manifests), 0)
        for path in manifests:
            with self.subTest(manifest=path.name):
                validator.validate_manifest_identity(
                    json.loads(path.read_text()), path)

    def test_this_repos_manifest_carries_a_uuid(self):
        # agentops is the authority repo; if its own identity stopped being a
        # UUID the assertion above would be vacuous for the one manifest that
        # matters most.
        manifest = json.loads((ROOT / "agentops.dispatch.json").read_text())
        self.assertIsInstance(manifest.get("authority_repo_uuid"), str)
        validator.validate_manifest_identity(manifest, ROOT / "agentops.dispatch.json")


if __name__ == "__main__":
    unittest.main()
