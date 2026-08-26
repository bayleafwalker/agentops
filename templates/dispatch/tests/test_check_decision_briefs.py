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


class TheEightEscalationsOf20260826(unittest.TestCase):
    """The incidents themselves, as fixtures.

    Reconciled in ``docs/plans/agentops/2026-08-26-false-escalation-reconciliation.md``.
    Seven were false and one was genuine, so both directions are pinned here: a
    gate that only ever fires is as useless as one that never does, and
    over-escalation is the failure this project actually has.
    """

    def _faults(self, body: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-01-incident.md").write_text(body, encoding="utf-8")
            return check.faults(directory)

    def test_a_verified_criterion_presented_as_a_question_is_caught(self) -> None:
        """Incident 1: all six criteria verified at file and line, then asked anyway."""
        self.assertTrue(self._faults(
            "# Accept agentops#2046?\n\n"
            "All six acceptance criteria were checked. This is an owner decision.\n"
        ))

    def test_policy_application_dressed_as_policy_making_is_caught(self) -> None:
        """Incident 2: the ruling already said 'on this class', not 'on this route'."""
        self.assertTrue(self._faults(
            "# Route versus authority\n\n"
            "Are these one axis or two? Your decision, since the doctrine is\n"
            "unsettled and a second route may be coming.\n"
        ))

    def test_a_stale_record_presented_as_a_decision_is_caught(self) -> None:
        """Incident 3: 179 commits behind and 23 dirty files; measured, 29 and clean."""
        self.assertTrue(self._faults(
            "# The devbox checkout\n\n"
            "It is 179 commits behind with 23 dirty files. The owner's call\n"
            "whether to keep or dispose of it.\n"
        ))

    def test_a_permission_gate_presented_as_a_decision_is_caught(self) -> None:
        """Incident 5: an authorization gate is ratification, not deliberation."""
        self.assertTrue(self._faults(
            "# Global hook registration\n\n"
            "The tool call was refused, so this is genuinely yours to decide.\n"
        ))

    def test_an_unmeasured_scope_presented_as_a_finding_is_caught(self) -> None:
        """Incident 6: 'unscoped' is an unfinished task, not a finding."""
        self.assertTrue(self._faults(
            "# Subagent spend\n\n"
            "The scope of this is unknown, so it awaits your ruling.\n"
        ))

    def test_finding_e_is_left_alone(self) -> None:
        """Incident 8: the one genuine escalation must pass, classified and cited.

        Its shape is the target the other seven should have been rewritten into:
        the axis named in the document's own words, and the governing text
        pointed at rather than recalled.
        """
        self.assertEqual([], self._faults(
            "# Finding E - subagent spend is uncounted\n\n"
            "## Why this one is genuinely yours\n\n"
            "This is a new value choice, not a derivable question and not merely\n"
            "ratification. Handover section 2a fixed a definition that folding\n"
            "subagent usage into frontier_totals would reopen, and\n"
            "release_scorecard.py guards it with total_billed_usd ==\n"
            "worker_billed_usd. Changing what the central metric denotes makes\n"
            "every historical figure non-comparable.\n"
        ))

    def test_the_reconciliation_document_itself_passes(self) -> None:
        """Dogfooding: the record of the eight must satisfy the rule it describes."""
        path = check.BRIEF_DIR / "2026-08-26-false-escalation-reconciliation.md"
        self.assertTrue(path.is_file(), "the reconciliation record is missing")
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / path.name).write_text(
                path.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertEqual([], check.faults(directory))


class TheRepositoryPasses(unittest.TestCase):
    def test_live_briefs_are_clean(self) -> None:
        self.assertEqual([], check.faults())

    def test_grandfather_list_only_shrinks(self) -> None:
        """Every grandfathered document must still exist, or the list is stale.

        Looked up across the whole checked sweep rather than in
        ``docs/plans/agentops`` alone: three entries were added when the sweep
        widened, and they live in ``docs/assessments``.
        """
        present = {path.name for path in check.checked_documents()}
        for name in check.GRANDFATHERED:
            self.assertIn(
                name, present,
                f"{name} is grandfathered but is no longer a checked document; "
                "drop it from the list",
            )

    def test_the_sweep_is_content_scoped_not_directory_scoped(self) -> None:
        """A new directory of briefs must not silently escape the check."""
        names = {str(p.relative_to(check.ROOT)) for p in check.checked_documents()}
        self.assertIn("docs/dispatch/handover-2026-08-23-metanarrative-v5.md", names)
        self.assertIn("docs/plans/agentops/2026-08-26-open-owner-decisions.md", names)
        self.assertTrue(
            all(not n.startswith(check.EXCLUDED_PREFIXES) for n in names),
            "excluded prefixes must not be swept")

    def test_the_skill_that_teaches_the_rule_is_excluded(self) -> None:
        """It quotes every phrase the check looks for, and escalates nothing."""
        skill = "templates/dispatch/skills/escalation-gate/SKILL.md"
        self.assertTrue((check.ROOT / skill).is_file())
        self.assertTrue(skill.startswith(check.EXCLUDED_PREFIXES))

    def test_a_cited_past_ruling_is_not_an_escalation(self) -> None:
        """"owner ruling" quoted or dated is a citation, not a claim of openness."""
        self.assertIsNone(check.OWNER_LANGUAGE.search(
            "`mechanical_bulk` is self_candidate (owner ruling quoted there)"))
        self.assertIsNone(check.OWNER_LANGUAGE.search(
            "max_attempts is 3 (owner ruling, 2026-08-24)."))
        self.assertIsNotNone(check.OWNER_LANGUAGE.search(
            "`#2100` needs an owner ruling, not engineering."))

    def test_a_citation_elsewhere_does_not_satisfy_the_escalating_section(self) -> None:
        """The change that made the citation half discriminate at all.

        Measured before it landed: the old whole-file rule fired on 129 of 172
        documents, because these documents always name other documents.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "2026-09-02-probe.md").write_text(
                "# Background\n\n"
                "Everything here is derivable; see hybrid_dispatch.py and Rule 4.\n\n"
                "## What is yours to decide\n\n"
                "This one is a new value choice and is genuinely yours.\n",
                encoding="utf-8",
            )
            problems = check.faults(directory)
            self.assertTrue(problems, "a section that cites nothing must be caught")
            self.assertIn("What is yours to decide", " ".join(problems))

    def test_a_subsection_is_not_treated_as_its_own_section(self) -> None:
        """A bare ``##`` followed by ``###`` is uncitable by construction."""
        blocks = check.sections("# Top\n\n## Parent\n\n### Child\n\nbody\n")
        self.assertEqual(2, len(blocks))
        self.assertIn("### Child", blocks[1])


if __name__ == "__main__":
    unittest.main()
