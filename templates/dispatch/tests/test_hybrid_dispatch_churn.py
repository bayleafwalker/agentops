"""Coordinator-authored oracle for hand-pass 2 (handover §3c, amendment 3) --
items A and B over ``hybrid_dispatch.py`` and the canonical example packet.

A  a failed tool call spends no churn step
B  the default reasoning budget is 12

Written against the hand-pass spec only: neither item is implemented, so every
test here fails. Rule 11 keeps this file to its own subject -- it never imports
``dispatch_release.py``, and it runs no git and no foreign subprocess.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
HYBRID = ROOT / "templates/dispatch/hybrid"
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch_churn_subject", SCRIPTS / "hybrid_dispatch.py")

#: One non-mutating tool that is not ``read``, so a step-budget fixture is never
#: also a repeated-read fixture.
STEP_TOOL = "glob"


def _tool(tool: str, status: str = "completed", path: str | None = None) -> dict:
    state: dict = {"status": status}
    if path:
        state["input"] = {"filePath": path}
    return {"type": "tool_use", "part": {"tool": tool, "state": state}}


def _defaults() -> dict:
    """The limits a packet that declares no ``context_churn`` runs under.

    Item A's budget fixtures are counted against this rather than a literal, so
    the oracle pins one number (item B) in one place instead of two that drift.
    """
    return dispatch.context_churn_limits({})


class FailedCallsSpendNoChurnStepTests(unittest.TestCase):
    """Item A. V5-M9 died three times because the guard counted the harness's
    own failures -- a profile-refused ``bash``, a ``grep`` that blew the Ripgrep
    record limit -- as the worker going in circles."""

    def test_a_an_errored_call_before_a_completed_mutation_yields_no_verdict(self):
        # The exact V5-M9 shape: failures burn the budget before the first write
        # is even attempted. With a budget of one, only counting the errors can
        # produce a verdict here.
        limits = {"max_reasoning_steps_without_mutation": 1, "max_repeated_reads_per_path": 4}
        events = [
            _tool("bash", status="error"),
            _tool("grep", status="error"),
            _tool("write"),
        ]
        self.assertIsNone(dispatch.churn_verdict(events, limits))

    def test_a_twelve_completed_steps_pass_and_thirteen_trip_the_guard(self):
        limits = _defaults()
        self.assertIsNone(dispatch.churn_verdict([_tool(STEP_TOOL)] * 12, limits))
        verdict = dispatch.churn_verdict([_tool(STEP_TOOL)] * 13, limits)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "churn_no_mutation")

    def test_a_errored_calls_never_exhaust_the_budget_however_many(self):
        # A worker whose every tool call is being refused is not circling; the
        # count is padded far past the limit so no off-by-one can pass this.
        events = [_tool("bash", status="error"), _tool("grep", status="aborted")] * 20
        self.assertIsNone(dispatch.churn_verdict(events, _defaults()))

    def test_a_two_failed_mutations_cost_neither_a_step_nor_a_verdict(self):
        # Under three attempts there is no worker_cannot_write to report, and
        # the attempts themselves are not evidence of circling either.
        limits = {"max_reasoning_steps_without_mutation": 1, "max_repeated_reads_per_path": 4}
        events = [_tool("edit", status="error"), _tool("write", status="denied")]
        self.assertIsNone(dispatch.churn_verdict(events, limits))

    def test_a_three_failed_mutations_still_win_over_the_churn_verdict(self):
        # Both could fire on this stream, and which one the operator is told
        # matters: "denied inside its own workspace" is a different fact from
        # "going in circles", and only the first names the thing to fix.
        limits = {"max_reasoning_steps_without_mutation": 1, "max_repeated_reads_per_path": 4}
        events = [_tool("write", status="error")] * 3
        verdict = dispatch.churn_verdict(events, limits)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "worker_cannot_write")

    def test_a_a_completed_mutation_still_resets_the_step_counter(self):
        # 22 steps in total, either side of one completed write: without the
        # reset this trips, so the fixture proves the reset survived item A.
        limits = _defaults()
        events = [_tool(STEP_TOOL)] * 11 + [_tool("write")] + [_tool(STEP_TOOL)] * 11
        self.assertIsNone(dispatch.churn_verdict(events, limits))

    def test_a_only_completed_reads_count_toward_the_repeated_read_limit(self):
        limits = {"max_reasoning_steps_without_mutation": 100, "max_repeated_reads_per_path": 2}
        errored = [_tool("read", status="error", path="src/a.py")] * 5
        # A read that errored returned no content, so it is not evidence that
        # the worker has looked at the same file twice.
        self.assertIsNone(dispatch.churn_verdict(errored, limits))
        completed = [_tool("read", path="src/a.py")] * 3
        verdict = dispatch.churn_verdict(completed, limits)
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict[0], "churn_repeated_reads")


class DefaultChurnBudgetTests(unittest.TestCase):
    """Item B. Every workspace the loop builds is a full clone of the
    repository, and 8 steps is not enough room to orient in one."""

    def test_b_the_undeclared_default_is_twelve_and_nothing_else_moves(self):
        # Asserted as the whole dict: the other three values are part of the
        # contract, and a partial assertion would let one of them drift.
        self.assertEqual(
            dispatch.context_churn_limits({}),
            {
                "max_repeated_reads_per_path": 4,
                "max_reasoning_steps_without_mutation": 12,
                "max_identical_context_tokens": 250000,
                "handoff_when_candidate_ready": True,
            },
        )

    def test_b_a_packet_that_declares_its_own_budget_still_wins(self):
        declared = {
            "max_repeated_reads_per_path": 4,
            "max_reasoning_steps_without_mutation": 5,
            "max_identical_context_tokens": 250000,
            "handoff_when_candidate_ready": True,
        }
        resolved = dispatch.context_churn_limits({"context_churn": declared})
        self.assertEqual(resolved["max_reasoning_steps_without_mutation"], 5)
        # The declared value is deliberately below the new default: without
        # this, "wins" would also hold for a resolver that ignores the packet.
        self.assertEqual(dispatch.context_churn_limits({})["max_reasoning_steps_without_mutation"], 12)

    def test_b_the_example_packet_does_not_contradict_the_default(self):
        example = json.loads(
            (HYBRID / "example-task-packet.json").read_text(encoding="utf-8")
        )
        churn = example["context_churn"]
        self.assertEqual(churn["max_reasoning_steps_without_mutation"], 12)
        # The other three are unchanged in the canonical example too, so a
        # reader copying it inherits exactly the resolved defaults.
        self.assertEqual(churn["max_repeated_reads_per_path"], 4)
        self.assertEqual(churn["max_identical_context_tokens"], 250000)
        self.assertIs(churn["handoff_when_candidate_ready"], True)


if __name__ == "__main__":
    unittest.main()
