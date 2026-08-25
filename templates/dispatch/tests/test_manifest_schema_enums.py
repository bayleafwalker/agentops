"""The manifest schema's enums, against what the fleet and the code actually do.

Two enums in ``manifest.schema.json`` were narrower than reality, and nothing
noticed until `validate_dispatch_manifest.py` was pointed at every repo in the
tree for the first time: nine repos failed, and eight of them failed only
because the schema had not kept up.

Both are the same shape as the ``skills.selected`` drift that started the v5.9
pass -- an enum written once, copied from somewhere, and then outlived by the
thing it copied. This file pins the values back to their authorities so that a
later tidy-up has to argue with a test instead of a hunch.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCHEMA_PATH = ROOT / "templates/dispatch/manifest.schema.json"
CALLER_MODE_DOC = ROOT / "docs/plans/agentops/caller-mode-routing-runtime-handover.md"
VERIFICATION_VALIDATOR = ROOT / "templates/dispatch/scripts/validate_verification_artifacts.py"

SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _harness_enum() -> list[str]:
    return SCHEMA["properties"]["routing"]["properties"]["default_harness"]["enum"]


def _family_enum() -> list[str]:
    return SCHEMA["properties"]["verification"]["properties"][
        "command_families"]["items"]["enum"]


class CallerHarnessTests(unittest.TestCase):
    """``caller`` is a routing mode with a written contract, not a typo."""

    def test_caller_is_admitted(self):
        self.assertIn(
            "caller", _harness_enum(),
            "six repos declare default_harness 'caller' and the contract for it "
            "was accepted on 2026-07-22; the schema refused all six")

    def test_the_contract_that_justifies_it_still_exists(self):
        # The anchor. If the contract is ever withdrawn, this fails and someone
        # has to decide about the enum on purpose rather than by drift.
        self.assertTrue(CALLER_MODE_DOC.is_file(), CALLER_MODE_DOC)
        self.assertIn(
            'default_harness = "caller"',
            CALLER_MODE_DOC.read_text(encoding="utf-8"),
            "the caller-mode contract no longer states the value the schema admits")

    def test_the_concrete_harnesses_are_still_admitted(self):
        # Widening must not have replaced anything.
        for harness in ("claude", "codex", "opencode"):
            self.assertIn(harness, _harness_enum())

    def test_an_unknown_harness_is_still_refused(self):
        self.assertNotIn("gpt", _harness_enum())


class CommandFamilyTests(unittest.TestCase):
    """The families in use across the tree, and the code's own looser rule."""

    def test_the_families_real_manifests_declare_are_admitted(self):
        # security / process-semantics / package are declared by outctl and the
        # bounded-output starter. They are ordinary families for a Python
        # package repo and were refused for no reason but the enum's age.
        for family in ("security", "process-semantics", "package"):
            with self.subTest(family=family):
                self.assertIn(family, _family_enum())

    def test_the_original_families_survive(self):
        for family in ("unit", "integration", "lint", "typecheck", "architecture",
                       "docs", "kustomize", "secrets", "docker", "full-suite"):
            with self.subTest(family=family):
                self.assertIn(family, _family_enum())

    def test_the_enum_is_stricter_than_the_code_and_that_is_recorded(self):
        # validate_verification_artifacts.py checks command_families with
        # _string_list -- any list of strings passes. So the enum is the ONLY
        # place these names are constrained, which is why it can be wrong
        # without anything failing at runtime, and why widening it is safe.
        source = VERIFICATION_VALIDATOR.read_text(encoding="utf-8")
        self.assertIn("_string_list(verification.get(\"command_families\")", source,
                      "the runtime validator no longer treats command_families as "
                      "a free string list; if it now enforces its own set, the two "
                      "must be reconciled rather than left to disagree")

    def test_the_enum_has_no_duplicates(self):
        self.assertEqual(len(_family_enum()), len(set(_family_enum())))
        self.assertEqual(len(_harness_enum()), len(set(_harness_enum())))


if __name__ == "__main__":
    unittest.main()
