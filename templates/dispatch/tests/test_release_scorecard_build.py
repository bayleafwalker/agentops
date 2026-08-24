"""Coordinator-authored oracle for ``release_scorecard.py`` -- the assembly.

T-6a pinned the frontier half (``reduce_sessions``/``frontier_totals``, read out
of the Claude Code Stop-hook sink) and T-6b pinned the worker half
(``worker_spend_from_receipt``/``worker_totals``, read out of the per-task
packet receipts). Neither half substitutes for the other: the Claude Code hooks
never observe an OpenCode worker, so a loop run scored from the sink alone
undercounts itself by the whole cheap half; and the receipts know nothing about
frontier turns. This file pins the one function that joins them:

``build_scorecard(release, rows, receipts, escalations, recorded_at,
scope=None)`` -> dict

``scope`` is the optional trailing parameter added when the sink was
scoped to a project: the dict recording what the scorecard was built from.
It is pinned in detail by ``test_release_scorecard_scope.py``; this file
only carries it in the declared top-level key set. Every call here still
passes five positional arguments, which must keep working.

Three properties are load-bearing and are asserted directly:

* it DELEGATES. ``frontier`` must equal ``frontier_totals(rows)`` and ``worker``
  must equal ``worker_totals(receipts)`` for the same inputs. A scorecard that
  re-implements either half is free to drift from it, and the quadratic bug
  T-6a exists to prevent would walk straight back in through the assembly --
  so a naive-sum frontier figure is asserted against by value too.
* BOTH halves stay separately visible. Empty receipts must not collapse the
  output to the frontier figure; the worker half is present with zeroes.
* ``total_reliable`` carries T-6b's "free vs did not say" distinction into the
  top-level figure: whether every contributing receipt actually reported.

The two halves are NOT the same kind of number and must never be added. The
frontier figure is ``tokens x a hardcoded list-price table`` computed by
``hooks/log-session-cost.sh``; nothing meters it and on a subscription plan it
is never billed. It is a usage-equivalent, useful for comparing releases
against each other and meaningless as money. The worker figure is OpenCode's
own ``step-finish`` accounting -- real metered API spend, actually charged.
Adding them produces a number that will be read as spend by whoever opens the
scorecard next. So ``cost_usd`` carries exactly:

* ``worker_billed_usd`` -- the only money.
* ``frontier_usage_equivalent_usd`` -- the imputed figure, preserved and
  renamed rather than hidden.
* ``total_billed_usd`` -- EQUAL to ``worker_billed_usd``. There is no other
  billed money in the system, so a reader asking "what did this cost" gets the
  true answer without having to know any of the above.
* ``commensurable`` -- always ``False``, said in the data rather than only in a
  docstring so a consumer can assert on it.
* ``total_reliable`` -- the worker half's ``cost_reported``.

No key may hold ``frontier + worker``. That sum is the defect.

``build_scorecard`` is pure: no file reads, no writes, no argv, no git.

Written against the packet spec only. ``release_scorecard.py`` exists and
carries the four T-6a/T-6b functions, but not ``build_scorecard`` -- so this
oracle fails at attribute lookup. That is the declared red.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    if not path.exists():
        raise ModuleNotFoundError(f"no module to grade: {path} does not exist")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


scorecard = _load_module("release_scorecard_subject", SCRIPTS / "release_scorecard.py")


#: The eight keys ``build_scorecard`` returns, exactly. Extra keys are a
#: schema change and must be declared, not smuggled in. ``scope`` is the
#: eighth: what the scorecard was built FROM (project and window), added
#: because two scorecards over different windows are not comparable and
#: nothing in either one used to say so.
TOP_LEVEL_KEYS = frozenset({
    "schema_version", "release", "recorded_at",
    "frontier", "worker", "escalations", "cost_usd", "scope",
})

#: The five keys the ``cost_usd`` block carries, exactly. Spelled as literals:
#: a rename back to frontier/worker/total is the regression this pins.
COST_KEYS = frozenset({
    "worker_billed_usd",
    "frontier_usage_equivalent_usd",
    "total_billed_usd",
    "commensurable",
    "total_reliable",
})

#: The literal schema tag. Spelled out here rather than read off the module so
#: that renaming the constant in the subject cannot silently rename the wire
#: format.
SCHEMA_VERSION = "workflow-scorecard/v1"


#: A small realistic sink corpus. Session "loop-a" stopped four times, so it
#: contributes four CUMULATIVE snapshots that supersede each other; the right
#: frontier answer is its last one (cost 2.75), and summing all four is the
#: quadratic bug. Sessions "loop-b" and "loop-c" stopped once each. The rows
#: are interleaved the way the shared sink really appends them, and one row
#: with no session id is present because the sink carries those too.
SINK_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T10:00:04Z", "session": "loop-a", "model": "claude-opus-5",
     "out": 120, "cost_usd": 0.4, "turns": 1, "assistant_msgs": 2,
     "tool_calls": 1, "duration_s": 22, "rework_rounds": 0},
    {"ts": "2026-08-24T10:03:12Z", "session": "loop-b", "model": "claude-opus-5",
     "out": 310, "cost_usd": 1.25, "turns": 4, "assistant_msgs": 7,
     "tool_calls": 6, "duration_s": 140, "rework_rounds": 1},
    {"ts": "2026-08-24T10:06:41Z", "session": "loop-a", "model": "claude-opus-5",
     "out": 260, "cost_usd": 1.1, "turns": 3, "assistant_msgs": 5,
     "tool_calls": 4, "duration_s": 95, "rework_rounds": 0},
    {"ts": "2026-08-24T10:11:55Z", "session": "loop-a", "model": "claude-opus-5",
     "out": 380, "cost_usd": 1.9, "turns": 5, "assistant_msgs": 9,
     "tool_calls": 8, "duration_s": 190, "rework_rounds": 1},
    {"ts": "2026-08-24T10:15:02Z", "session": "loop-c", "model": "claude-opus-5",
     "out": 90, "cost_usd": 0.35, "turns": 1, "assistant_msgs": 1,
     "tool_calls": 0, "duration_s": 18, "rework_rounds": 0},
    {"ts": "2026-08-24T10:20:37Z", "session": "loop-a", "model": "claude-opus-5",
     "out": 505, "cost_usd": 2.75, "turns": 8, "assistant_msgs": 14,
     "tool_calls": 12, "duration_s": 305, "rework_rounds": 2},
    {"ts": "2026-08-24T10:21:00Z", "model": "claude-opus-5", "out": 5,
     "cost_usd": 99.0, "turns": 99, "assistant_msgs": 99, "tool_calls": 99,
     "duration_s": 9999, "rework_rounds": 9},
)

#: The correct frontier cost for SINK_ROWS: the surviving snapshot of each of
#: the three sessions, 2.75 + 1.25 + 0.35. Written out by hand so the assertion
#: does not depend on the subject agreeing with itself.
REDUCED_FRONTIER_COST = 4.35

#: What summing every row would report instead -- the quadratic bug, plus the
#: sessionless row. Asserted against by value: a scorecard built on it must fail.
NAIVE_FRONTIER_COST = 106.75


def _receipt(task_id, attempt, cost_usd, tokens, cost_reported, passed=True):
    """A receipt shaped like docs/evidence/receipts/*/receipt.json.

    The spend the worker actually reports lives under driver_steps -> the "run"
    entry -> receipt -> spend, with decoy figures on the neighbouring steps.
    T-6b already pins that lift; this oracle only needs receipts real enough
    that ``worker_totals`` reads them the same way it will in production.
    """
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "task_id": task_id,
        "repo_id": "agentops",
        "attempt": attempt,
        "route": "mechanical_bulk",
        "harness_model": "opencode-go/deepseek-v4-flash",
        "driver_steps": [
            {"step": "prepare", "attempt": attempt, "exit_code": 0,
             "receipt": {"spend": {"cost_usd": 99.0, "tokens": 999999,
                                   "cost_reported": False}}},
            {"step": "run", "attempt": attempt, "exit_code": 0, "stderr": "",
             "receipt": {"spend": {"cost_usd": cost_usd, "tokens": tokens,
                                   "cost_reported": cost_reported,
                                   "cap_usd": 3.0, "within_cap": True}}},
            {"step": "receipt", "attempt": attempt, "exit_code": 0,
             "receipt": {"spend": {"cost_usd": 77.0, "tokens": 777777,
                                   "cost_reported": False}}},
        ],
        "gate": {"evidence": {"gates": {"diff-nonempty": True},
                              "passed": passed}},
    }


#: Three receipts from three tasks, every one of which reported its cost. The
#: figures have six significant places so a total that rounds early or late is
#: visible. 0.020864 + 0.011111 + 0.000004 = 0.031979.
REPORTING_RECEIPTS: tuple[dict, ...] = (
    _receipt("V5-M13-retry-branch", 1, 0.020864, 292309, True),
    _receipt("V5-M20-scorecard", 1, 0.011111, 140002, True),
    _receipt("V5-M21-doctor", 2, 0.000004, 61, True),
)

#: The correct worker cost for REPORTING_RECEIPTS, by hand.
REPORTING_WORKER_COST = 0.031979

#: The same corpus with one route that returned no cost figure. Its 0.0 is
#: indistinguishable from a free model, so the combined total must stop
#: presenting itself as reliable -- this is T-6b's distinction reaching the top.
SILENT_RECEIPTS: tuple[dict, ...] = (
    _receipt("V5-M13-retry-branch", 1, 0.020864, 292309, True),
    _receipt("V5-M22-silent-route", 1, 0.0, 88000, False),
)

#: Three escalations over two tasks. "V5-M13-retry-branch" escalated twice, so
#: the count is 3 while it appears once in ``tasks``. The second of its two
#: carries no ``stop_condition`` at all -- the driver stopped on an exit code,
#: not on a declared condition -- so it must be omitted rather than contribute
#: a None that would sort-crash or leak into the list. The two present
#: conditions are given in reverse sorted order.
ESCALATIONS: tuple[dict, ...] = (
    {"type": "workflow.escalation", "actor": "dispatch-release",
     "summary": "task V5-M13-retry-branch escalated to frontier",
     "detail": "gate evidence empty after attempt 2",
     "metadata": {"task_id": "V5-M13-retry-branch", "repo_id": "agentops",
                  "step": "gate", "exit_code": 1,
                  "starting_commit": "a1b2c3d", "driver": "opencode",
                  "stop_condition": "diff-empty"},
     "recorded_at": "2026-08-24T10:08:00Z"},
    {"type": "workflow.escalation", "actor": "dispatch-release",
     "summary": "task V5-M22-silent-route escalated to frontier",
     "detail": "worker exceeded its cap",
     "metadata": {"task_id": "V5-M22-silent-route", "repo_id": "agentops",
                  "step": "run", "exit_code": 2,
                  "starting_commit": "e4f5a6b", "driver": "opencode",
                  "stop_condition": "cap-exceeded"},
     "recorded_at": "2026-08-24T10:14:20Z"},
    {"type": "workflow.escalation", "actor": "dispatch-release",
     "summary": "task V5-M13-retry-branch escalated to frontier",
     "detail": "driver died",
     "metadata": {"task_id": "V5-M13-retry-branch", "repo_id": "agentops",
                  "step": "run", "exit_code": 137,
                  "starting_commit": "a1b2c3d", "driver": "opencode"},
     "recorded_at": "2026-08-24T10:19:41Z"},
)

#: An unusual but legal recorded_at: an offset rather than Z, and sub-second
#: precision. It must survive verbatim, not be normalised or re-derived.
ODD_RECORDED_AT = "2026-08-24T10:22:03.481729+03:00"


def _lists(*corpora):
    """Fresh mutable copies, so mutation by the subject cannot leak fixtures."""
    return [copy.deepcopy(list(corpus)) for corpus in corpora]


class BuildScorecardTests(unittest.TestCase):

    def _build(self, rows=SINK_ROWS, receipts=REPORTING_RECEIPTS,
               escalations=ESCALATIONS, release="v5",
               recorded_at="2026-08-24T10:30:00Z"):
        rows, receipts, escalations = _lists(rows, receipts, escalations)
        return scorecard.build_scorecard(release, rows, receipts, escalations,
                                         recorded_at)

    def test_it_returns_exactly_the_eight_top_level_keys(self):
        card = self._build()
        self.assertIsInstance(card, dict, "build_scorecard did not return a dict")
        self.assertEqual(
            set(card), set(TOP_LEVEL_KEYS),
            "the scorecard's top-level keys are not exactly the declared eight",
        )

    def test_schema_version_is_the_literal_string(self):
        self.assertEqual(
            self._build()["schema_version"], SCHEMA_VERSION,
            "schema_version is not the literal 'workflow-scorecard/v1'",
        )

    def test_release_and_recorded_at_are_carried_through_verbatim(self):
        card = self._build(release="v5")
        self.assertEqual(card["release"], "v5", "release was not carried through")
        self.assertEqual(
            card["recorded_at"], "2026-08-24T10:30:00Z",
            "recorded_at was not carried through",
        )
        odd = self._build(release="v5.1-rc2+freeze", recorded_at=ODD_RECORDED_AT)
        self.assertEqual(
            odd["release"], "v5.1-rc2+freeze",
            "an unusual release string was rewritten instead of carried through",
        )
        self.assertEqual(
            odd["recorded_at"], ODD_RECORDED_AT,
            "recorded_at was normalised; it must be carried through verbatim",
        )

    def test_frontier_half_is_delegated_to_frontier_totals(self):
        card = self._build()
        self.assertEqual(
            card["frontier"], scorecard.frontier_totals(list(SINK_ROWS)),
            "the frontier half is not what frontier_totals returns for the "
            "same rows -- build_scorecard re-implemented it",
        )

    def test_worker_half_is_delegated_to_worker_totals(self):
        card = self._build()
        self.assertEqual(
            card["worker"], scorecard.worker_totals(list(REPORTING_RECEIPTS)),
            "the worker half is not what worker_totals returns for the same "
            "receipts -- build_scorecard re-implemented it",
        )

    def test_frontier_is_computed_from_the_reduced_rows(self):
        card = self._build()
        self.assertAlmostEqual(
            card["frontier"]["cost_usd"], REDUCED_FRONTIER_COST, places=6,
            msg="the frontier cost is not the reduced figure",
        )
        self.assertNotAlmostEqual(
            card["frontier"]["cost_usd"], NAIVE_FRONTIER_COST, places=6,
            msg="the scorecard summed every sink row -- this is the quadratic "
                "bug T-6 exists to prevent, now baked into the scorecard",
        )
        self.assertEqual(
            card["frontier"]["sessions"], 3,
            "the four snapshots of session loop-a were not reduced to one",
        )

    def test_cost_block_carries_exactly_the_five_declared_keys(self):
        cost = self._build()["cost_usd"]
        self.assertEqual(
            set(cost), set(COST_KEYS),
            "cost_usd does not carry exactly worker_billed_usd/"
            "frontier_usage_equivalent_usd/total_billed_usd/commensurable/"
            "total_reliable",
        )

    def test_worker_billed_usd_is_the_worker_figure(self):
        cost = self._build()["cost_usd"]
        self.assertAlmostEqual(
            cost["worker_billed_usd"], REPORTING_WORKER_COST, places=6,
            msg="cost_usd.worker_billed_usd is not the worker figure",
        )
        self.assertEqual(
            cost["worker_billed_usd"],
            scorecard.worker_totals(list(REPORTING_RECEIPTS))["cost_usd"],
            "worker_billed_usd is not what worker_totals reports",
        )

    def test_frontier_usage_equivalent_usd_preserves_the_frontier_figure(self):
        """Renamed and re-labelled, not hidden. The figure is still useful."""
        cost = self._build()["cost_usd"]
        self.assertEqual(
            cost["frontier_usage_equivalent_usd"],
            scorecard.frontier_totals(list(SINK_ROWS))["cost_usd"],
            "frontier_usage_equivalent_usd is not frontier_totals' cost_usd -- "
            "the imputed figure was dropped or recomputed instead of renamed",
        )
        self.assertAlmostEqual(
            cost["frontier_usage_equivalent_usd"], REDUCED_FRONTIER_COST,
            places=6,
            msg="the frontier usage-equivalent is not the reduced figure",
        )

    def test_total_billed_usd_equals_worker_billed_usd_exactly(self):
        """The frontier half is 4.35 imputed against 0.031979 of real money.

        An implementation that sums reports 4.381979 here, which is not money.
        The equality is exact, not almost-equal: total_billed_usd IS the worker
        figure, not a rounding of something near it.
        """
        cost = self._build()["cost_usd"]
        self.assertEqual(
            cost["total_billed_usd"], cost["worker_billed_usd"],
            "total_billed_usd is not exactly worker_billed_usd -- an imputed "
            "list price is being reported as billed money",
        )
        self.assertAlmostEqual(
            cost["total_billed_usd"], REPORTING_WORKER_COST, places=6,
            msg="total_billed_usd is not the real metered spend",
        )
        self.assertNotAlmostEqual(
            cost["total_billed_usd"],
            REDUCED_FRONTIER_COST + REPORTING_WORKER_COST, places=6,
            msg="total_billed_usd is frontier + worker -- the category error "
                "this contract exists to remove",
        )

    def test_no_key_in_the_cost_block_holds_frontier_plus_worker(self):
        cost = self._build()["cost_usd"]
        summed = REDUCED_FRONTIER_COST + REPORTING_WORKER_COST
        self.assertEqual(
            set(cost), set(COST_KEYS),
            "cost_usd carries a key outside the declared five, which is where "
            "a resurrected sum would hide",
        )
        for key, value in cost.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            self.assertNotAlmostEqual(
                value, summed, places=6,
                msg=f"cost_usd.{key} holds frontier + worker; the two halves "
                    "are not the same kind of number and must not be added",
            )

    def test_commensurable_is_the_literal_false(self):
        """Said in the data, so a consumer can assert on it."""
        cost = self._build()["cost_usd"]
        self.assertIs(
            cost["commensurable"], False,
            "cost_usd.commensurable is not the bool False -- a falsy stand-in "
            "does not carry the claim",
        )

    def test_total_reliable_is_false_when_a_receipt_did_not_report_its_cost(self):
        """The 'free vs did not say' distinction reaching the top-level figure.

        A route whose provider reports nothing contributes 0.0, which reads
        exactly like a free model. The combined total must not be presentable
        as reliable when the worker half was silent.
        """
        card = self._build(receipts=SILENT_RECEIPTS)
        self.assertIs(
            card["cost_usd"]["total_reliable"], False,
            "total_reliable is not False even though a receipt reported no "
            "cost -- a silent route is being presented as a trustworthy total",
        )
        self.assertEqual(
            card["cost_usd"]["total_reliable"],
            card["worker"]["cost_reported"],
            "total_reliable diverged from the worker half's cost_reported",
        )
        self.assertEqual(
            card["worker"]["cost_unreported_tasks"], ["V5-M22-silent-route"],
            "the silent task is not named in the worker half",
        )

    def test_total_reliable_is_true_when_every_receipt_reported(self):
        card = self._build(receipts=REPORTING_RECEIPTS)
        self.assertIs(
            card["cost_usd"]["total_reliable"], True,
            "total_reliable is not True even though every receipt reported",
        )

    def test_empty_receipts_do_not_become_a_complete_scorecard(self):
        """Both halves stay separately visible when the worker never ran."""
        card = self._build(receipts=())
        self.assertIn(
            "worker", card,
            "the worker half vanished when there were no receipts",
        )
        self.assertEqual(
            card["worker"], scorecard.worker_totals([]),
            "the empty worker half is not what worker_totals([]) returns",
        )
        self.assertEqual(
            card["worker"]["attempts"], 0, "the empty worker half is not zeroed",
        )
        self.assertEqual(
            card["worker"]["tasks"], 0, "the empty worker half is not zeroed",
        )
        self.assertEqual(
            card["cost_usd"]["worker_billed_usd"], 0.0,
            "cost_usd.worker_billed_usd is not 0.0 with no receipts",
        )
        self.assertAlmostEqual(
            card["cost_usd"]["frontier_usage_equivalent_usd"],
            REDUCED_FRONTIER_COST, places=6,
            msg="the frontier half changed when the receipts went away",
        )
        self.assertEqual(
            card["cost_usd"]["total_billed_usd"], 0.0,
            "no worker ran, so nothing was billed -- total_billed_usd must be "
            "0.0 and not the frontier's imputed figure",
        )
        self.assertIs(
            card["cost_usd"]["commensurable"], False,
            "commensurable is not False on an empty worker half",
        )
        self.assertEqual(
            card["cost_usd"]["total_reliable"],
            card["worker"]["cost_reported"],
            "total_reliable is not the worker half's cost_reported",
        )

    def test_escalations_count_tasks_and_stop_conditions(self):
        esc = self._build()["escalations"]
        self.assertEqual(
            set(esc), {"count", "tasks", "stop_conditions"},
            "the escalations block does not carry exactly count/tasks/"
            "stop_conditions",
        )
        self.assertEqual(
            esc["count"], 3,
            "two escalations on one task must still count as two",
        )
        self.assertEqual(
            esc["tasks"], ["V5-M13-retry-branch", "V5-M22-silent-route"],
            "escalation tasks are not the distinct task ids, sorted",
        )
        self.assertEqual(
            esc["stop_conditions"], ["cap-exceeded", "diff-empty"],
            "stop conditions are not the distinct declared conditions, sorted, "
            "with the record that carried none omitted",
        )
        self.assertNotIn(
            None, esc["stop_conditions"],
            "a record with no stop_condition contributed None",
        )

    def test_empty_escalations_give_zero_and_empty_lists(self):
        esc = self._build(escalations=())["escalations"]
        self.assertEqual(esc["count"], 0, "an empty escalation list is not count 0")
        self.assertEqual(esc["tasks"], [], "tasks is not an empty list")
        self.assertEqual(
            esc["stop_conditions"], [], "stop_conditions is not an empty list",
        )

    def test_it_does_not_mutate_its_inputs(self):
        rows, receipts, escalations = _lists(SINK_ROWS, REPORTING_RECEIPTS,
                                             ESCALATIONS)
        before = copy.deepcopy((rows, receipts, escalations))
        scorecard.build_scorecard("v5", rows, receipts, escalations,
                                  "2026-08-24T10:30:00Z")
        self.assertEqual(
            (rows, receipts, escalations), before,
            "build_scorecard mutated the inputs it was handed",
        )


if __name__ == "__main__":
    unittest.main()
