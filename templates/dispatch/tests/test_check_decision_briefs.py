"""The decision-brief check must fire on the document that motivated it.

A check that cannot fail is decoration. This suite pins both directions: a brief
that escalates without classifying is caught, and a brief that classifies and
cites is left alone. The third test is the one that matters -- it reconstructs
the shape of the four false escalations of 2026-08-26 and asserts the check
rejects it.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


check = _load("check_decision_briefs_subject", SCRIPTS / "check_decision_briefs.py")


class TheCheckDiscriminates(unittest.TestCase):
    def _brief(self, tmp: str, body: str) -> Path:
        d = Path(tmp)
        (d / "2026-09-01-probe.md").write_text(body, encoding="utf-8")
        return d

    def test_unclassified_escalation_is_caught(self) -> None:
        """The exact shape of the 2026-08-26 false escalations."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._brief(tmp, (
                "# Three open items\n\n"
                "## What's actually yours to decide\n\n"
                "1. Whether to keep the mandatory reference patch.\n"
                "2. Whether dispatch is a capped capability or a line of work.\n"
                "This is genuinely yours because the doctrine is unsettled.\n"
            ))
            problems = check.faults(d)
            self.assertTrue(problems, "an unclassified owner decision must be caught")
            self.assertIn("never classifies it", " ".join(problems))

    def test_classified_and_cited_brief_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = self._brief(tmp, (
                "# One decision\n\n"
                "Item A is **derivable** -- Rule 4 enumerates the owner touchpoints\n"
                "and this is not among them; see hybrid_dispatch.py and section 2.\n"
                "Item B needs authorization only, so it is ratification: bring the\n"
                "resolved action. Item C is a new value choice and is the owner's call.\n"
            ))
            self.assertEqual([], check.faults(d))

    def test_classified_but_uncited_is_caught(self) -> None:
        """A remembered scope is not a constraint; the brief must point at it."""
        with tempfile.TemporaryDirectory() as tmp:
            d = self._brief(tmp, (
                "# One decision\n\n"
                "This is a new value choice and therefore the owner's call,\n"
                "because the two-kinds doctrine would be reopened by it.\n"
            ))
            problems = check.faults(d)
            self.assertTrue(problems)
            self.assertIn("without citing the governing text", " ".join(problems))

    def test_brief_with_no_owner_language_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = self._brief(tmp, "# A plan\n\nSteps 1, 2, 3. Nothing is escalated.\n")
            self.assertEqual([], check.faults(d))


class TheRepositoryPasses(unittest.TestCase):
    def test_live_briefs_are_clean(self) -> None:
        self.assertEqual([], check.faults())

    def test_grandfather_list_only_shrinks(self) -> None:
        """Every grandfathered brief must still exist, or the list is stale."""
        for name in check.GRANDFATHERED:
            self.assertTrue(
                (check.BRIEF_DIR / name).is_file(),
                f"{name} is grandfathered but no longer exists; drop it from the list",
            )


if __name__ == "__main__":
    unittest.main()
