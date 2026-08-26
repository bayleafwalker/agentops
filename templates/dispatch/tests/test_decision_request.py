"""A decision must be classified before it can be emitted, not after.

``check_decision_briefs.py`` reads Markdown, so it can only catch an escalation
once someone has written it into a file the sweep covers. It cannot stop an
agent, a CLI, or a handover generator from emitting one, and section-local
citation proves proximity rather than support.

These are the tests for the other end: the record kinds, the fields a kind
cannot omit, and the rule that only ratifications and new value choices reach
the owner queue. The last test is the one that matters -- a queue rendered from
records satisfies the Markdown backstop by construction, which is the point at
which the backstop stops being the thing holding the line.

The eight escalations of 2026-08-26 are reconciled in
``docs/plans/agentops/2026-08-26-false-escalation-reconciliation.md``; five of
them were gates or already-derived answers, which is why those are their own
kinds here.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


decisions = _load("decision_request_subject", SCRIPTS / "decision_request.py")
check = _load("check_decision_briefs_for_render", SCRIPTS / "check_decision_briefs.py")


def _ref(location="hybrid_dispatch.py:420", scope="the pre-gate list in policy"):
    return {"location": location, "stated_scope": scope}


def _record(**overrides):
    record = {
        "schema_version": "agentops-decision/v1",
        "id": "D-1",
        "kind": "resolution",
        "claim": "The pre-gate list was echoed rather than computed.",
        "governing_refs": [_ref()],
        "resolved_action": "Registered an evaluator per gate; unregistered gates fail closed.",
    }
    record.update(overrides)
    return record


class TheKindsCarryTheirOwnObligations(unittest.TestCase):
    def test_a_valid_resolution_passes(self):
        self.assertEqual([], decisions.violations(_record()))

    def test_a_resolution_must_say_what_was_done(self):
        record = _record()
        del record["resolved_action"]
        self.assertTrue(decisions.violations(record))

    def test_a_ratification_must_name_its_authority(self):
        record = _record(kind="ratification", recommendation="Accept.")
        record.pop("resolved_action")
        self.assertTrue(decisions.violations(record))
        record["authority_required"] = "the designated human acceptance event"
        self.assertEqual([], decisions.violations(record))

    def test_a_new_value_choice_must_say_what_is_left_unsettled(self):
        """If nothing is left over, the answer was derivable."""
        record = _record(kind="new-value-choice", recommendation="Option B.")
        record.pop("resolved_action")
        self.assertTrue(decisions.violations(record))
        record["unresolved_delta"] = ""
        self.assertTrue(decisions.violations(record))
        record["unresolved_delta"] = (
            "Section 2a fixes two kinds of cost and says nothing about which "
            "imputed usage counts toward the frontier figure.")
        self.assertEqual([], decisions.violations(record))

    def test_every_record_must_cite_governing_text(self):
        record = _record(governing_refs=[])
        self.assertTrue(decisions.violations(record))

    def test_a_citation_must_state_the_scope_it_was_read_as_having(self):
        """The field the eight failures would each have had to fill in wrongly."""
        for evasion in ("n/a", "unknown", "unscoped", "TBD"):
            with self.subTest(scope=evasion):
                record = _record(governing_refs=[_ref(scope=evasion)])
                problems = decisions.violations(record)
                self.assertTrue(problems)
                self.assertIn("stated_scope", " ".join(problems))

    def test_an_unknown_kind_is_refused(self):
        self.assertTrue(decisions.violations(_record(kind="open-question")))


class OnlyDecisionsReachTheOwner(unittest.TestCase):
    def _queueable(self):
        return [
            _record(id="R-1"),
            _record(id="A-1", kind="authorization",
                    authority_required="a delegated operational authority",
                    resolved_action=None) | {"resolved_action": None},
            _record(id="N-1", kind="new-value-choice",
                    recommendation="Sibling subagent_totals.",
                    unresolved_delta=(
                        "Section 2a separates imputed from metered and does not "
                        "say which imputed usage counts.")),
        ]

    def test_resolutions_and_gates_are_dropped_at_the_boundary(self):
        records = [
            _record(id="R-1"),
            {k: v for k, v in _record(
                id="A-1", kind="authorization",
                authority_required="a delegated operational authority").items()
             if k != "resolved_action"},
            {k: v for k, v in _record(
                id="N-1", kind="new-value-choice",
                recommendation="Sibling subagent_totals.",
                unresolved_delta=(
                    "Section 2a separates imputed from metered and does not say "
                    "which imputed usage counts.")).items()
             if k != "resolved_action"},
        ]
        queue = decisions.owner_queue(records)
        self.assertEqual(["N-1"], [r["id"] for r in queue])

    def test_an_invalid_record_cannot_be_queued(self):
        with self.assertRaises(decisions.DecisionError):
            decisions.owner_queue([_record(governing_refs=[])])


class TheRenderedQueueSatisfiesTheBackstop(unittest.TestCase):
    """Rendered Markdown must pass check_decision_briefs by construction."""

    def _render_and_check(self, records, name="2026-09-03-rendered.md"):
        markdown = decisions.render(records)
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / name).write_text(markdown, encoding="utf-8")
            return markdown, check.faults(directory)

    def test_a_queue_with_one_genuine_escalation_passes_the_check(self):
        records = [
            _record(id="R-1"),
            {k: v for k, v in _record(
                id="N-1", kind="new-value-choice",
                claim="Counting subagent usage changes what the central metric denotes.",
                recommendation="Sibling subagent_totals; leave frontier_totals untouched.",
                governing_refs=[_ref("docs/dispatch/handover-2026-08-23-metanarrative-v5.md §2a",
                                     "imputed versus metered cost, not which imputed usage counts")],
                unresolved_delta=(
                    "Whether the v5 baseline is recomputed or retired once the "
                    "frontier figure changes meaning.")).items()
             if k != "resolved_action"},
        ]
        markdown, problems = self._render_and_check(records)
        self.assertEqual([], problems, markdown)
        self.assertIn("new value choice", markdown)
        self.assertIn("§2a", markdown)

    def test_an_all_derivable_pass_renders_nothing_open(self):
        markdown, problems = self._render_and_check([_record(id="R-1"), _record(id="R-2")])
        self.assertEqual([], problems, markdown)
        self.assertIn("Nothing is open", markdown)

    def test_the_rendered_queue_states_the_counts(self):
        markdown = decisions.render([_record(id="R-1"), _record(id="R-2")])
        self.assertIn("0 of 2 outcomes are the owner's", markdown)


class TheSchemaIsFullyChecked(unittest.TestCase):
    def test_the_checker_implements_every_keyword_the_schema_uses(self):
        self.assertEqual(
            [], decisions.packet_schema.unsupported_keywords(decisions.load_schema()))


if __name__ == "__main__":
    unittest.main()
