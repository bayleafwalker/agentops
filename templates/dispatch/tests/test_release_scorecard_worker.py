"""Coordinator-authored oracle for ``release_scorecard.py`` -- the worker half.

``reduce_sessions``/``frontier_totals`` (T-6a) read the Claude Code Stop-hook
sink. That sink never sees an OpenCode worker at all, so a loop run scored from
the hook alone undercounts itself by exactly the cheap half of the dispatch. The
other source is the per-task receipt: ``hybrid_dispatch.worker_spend`` writes
what the worker actually spent into the ``run`` driver step, and this file pins
the two functions that lift it back out:

``worker_spend_from_receipt(receipt)`` -> {cost_usd, tokens, cost_reported}
``worker_totals(receipts)``            -> the eight aggregate fields

``worker_spend_from_receipt`` mirrors the receipt and keeps the receipt's own
``cost_usd`` spelling. ``worker_totals`` *reports*, and what it reports is real
metered spend, so its money key is named ``billed_usd`` -- distinct from the
frontier half's imputed ``usage_equivalent_usd``. See
``test_release_scorecard_naming.py``.

``cost_reported`` is the load-bearing field. A route whose provider reports no
cost yields 0.0, which is indistinguishable from a free model; ``cost_reported``
records which case it was, so a corpus is never read as "this route is free"
when it is really "this route did not say". Dropping it is the failure this
oracle exists to catch, and it is asserted in both directions.

Written against the packet spec only. ``release_scorecard.py`` exists but does
not yet carry these two functions, so this oracle fails at attribute lookup --
that is the declared red.
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


#: The three keys ``worker_spend_from_receipt`` returns, exactly. ``worker_spend``
#: also emits cap_usd/within_cap/ceiling fields; those are policy, not spend, and
#: must not be carried through.
SPEND_KEYS = frozenset({"cost_usd", "tokens", "cost_reported"})

#: The eight keys ``worker_totals`` returns, exactly. The money key is
#: ``billed_usd``: this half is real metered spend, and nothing named
#: ``cost_usd`` may appear here, because that is the spelling the frontier
#: half's imputed figure used to share.
TOTALS_KEYS = frozenset({
    "attempts", "tasks", "billed_usd", "tokens", "cost_reported",
    "cost_unreported_tasks", "first_pass_tasks", "first_pass_rate",
})

#: The zero answer for any receipt whose structure does not reach a ``spend``.
ZERO_SPEND = {"cost_usd": 0.0, "tokens": 0, "cost_reported": False}


#: A receipt shaped exactly like a real one
#: (docs/evidence/receipts/V5-M13-retry-branch/receipt.json): four driver steps
#: in real order, the figure nested driver_steps -> the "run" entry -> receipt ->
#: spend, and the spend carrying its cap/ceiling siblings. The ``run`` step sits
#: at index 2, and the ``prepare`` and ``gate`` steps carry decoy numbers, so an
#: implementation that reaches for ``driver_steps[1]`` -- or for the first step
#: that happens to have a nested receipt -- reads the wrong one and fails.
REAL_SHAPED_RECEIPT = {
    "schema_version": "agentops-hybrid-receipt/v1",
    "task_id": "V5-M13-retry-branch",
    "repo_id": "agentops",
    "attempt": 1,
    "route": "mechanical_bulk",
    "harness_model": "opencode-go/deepseek-v4-flash",
    "driver_steps": [
        {"step": "prepare", "attempt": 1, "exit_code": 0,
         "receipt": {"spend": {"cost_usd": 99.0, "tokens": 999999,
                               "cost_reported": False}}},
        {"step": "gate", "attempt": 1, "exit_code": 0,
         "receipt": {"spend": {"cost_usd": 88.0, "tokens": 888888,
                               "cost_reported": False}}},
        {"step": "run", "attempt": 1, "exit_code": 0, "stderr": "",
         "receipt": {
             "schema_version": "agentops-hybrid-receipt/v1",
             "task_id": "V5-M13-retry-branch",
             "attempt": 1,
             "spend": {
                 "cost_usd": 0.020864,
                 "tokens": 292309,
                 "cost_reported": True,
                 "cap_usd": 3.0,
                 "within_cap": True,
                 "soft_token_ceiling": 1200000,
                 "hard_token_ceiling": 2000000,
                 "soft_token_ceiling_exceeded": False,
                 "within_hard_token_ceiling": True,
             },
         }},
        {"step": "receipt", "attempt": 1, "exit_code": 0,
         "receipt": {"spend": {"cost_usd": 77.0, "tokens": 777777,
                               "cost_reported": False}}},
    ],
    "gate": {"evidence": {"gates": {"diff-nonempty": True}, "passed": True}},
}

#: A receipt with no ``driver_steps`` key at all -- an aborted packet that never
#: reached the driver.
NO_DRIVER_STEPS_RECEIPT = {"task_id": "no-steps", "attempt": 1}

#: Driver steps present, but the run never happened: prepare failed and the
#: driver stopped. No "run" entry to read.
NO_RUN_STEP_RECEIPT = {
    "task_id": "no-run",
    "attempt": 1,
    "driver_steps": [
        {"step": "prepare", "attempt": 1, "exit_code": 1},
        {"step": "receipt", "attempt": 1, "exit_code": 0},
    ],
}

#: A ``run`` step that produced no nested receipt -- the worker died before it
#: wrote one, so exit_code is nonzero and the step is bare.
RUN_WITHOUT_RECEIPT = {
    "task_id": "run-bare",
    "attempt": 1,
    "driver_steps": [{"step": "run", "attempt": 1, "exit_code": 137,
                      "stderr": "killed"}],
}

#: A nested receipt from a harness that reported no spend block at all. This is
#: the case that must NOT be read as a free run: no spend means no data, and the
#: zero result says so with cost_reported False.
RUN_RECEIPT_WITHOUT_SPEND = {
    "task_id": "no-spend",
    "attempt": 1,
    "driver_steps": [{"step": "run", "attempt": 1, "exit_code": 0,
                      "receipt": {"task_id": "no-spend", "attempt": 1}}],
}

#: A retry that re-ran the step inside one packet: two "run" entries. The LAST
#: is the attempt that produced the receipt. The first carries the larger figure
#: so "take the first run" and "take the max" both fail.
TWO_RUN_STEPS_RECEIPT = {
    "task_id": "two-runs",
    "attempt": 2,
    "driver_steps": [
        {"step": "prepare", "attempt": 1, "exit_code": 0},
        {"step": "run", "attempt": 1, "exit_code": 1,
         "receipt": {"spend": {"cost_usd": 5.5, "tokens": 500000,
                               "cost_reported": True}}},
        {"step": "run", "attempt": 2, "exit_code": 0,
         "receipt": {"spend": {"cost_usd": 0.25, "tokens": 40000,
                               "cost_reported": True}}},
        {"step": "receipt", "attempt": 2, "exit_code": 0},
    ],
}


def _receipt(task_id, attempt, cost, tokens, reported, passed):
    """Build one minimal receipt of the real shape.

    Fixtures below are declared as module-level constants; this only nests the
    four load-bearing places (driver_steps -> run -> receipt -> spend, plus
    gate.evidence.passed) so a twelve-receipt corpus stays readable.
    ``passed=None`` omits the ``gate`` chain entirely.
    """
    receipt = {
        "task_id": task_id,
        "attempt": attempt,
        "driver_steps": [
            {"step": "prepare", "attempt": attempt, "exit_code": 0},
            {"step": "run", "attempt": attempt, "exit_code": 0,
             "receipt": {"task_id": task_id, "attempt": attempt,
                         "spend": {"cost_usd": cost, "tokens": tokens,
                                   "cost_reported": reported,
                                   "cap_usd": 3.0, "within_cap": True}}},
        ],
    }
    if passed is not None:
        receipt["gate"] = {"evidence": {"passed": passed}}
    return receipt


#: Four distinct tasks, five receipts. Three tasks passed on attempt 1; "late"
#: failed its first attempt and passed on its second, which is not a first pass.
#: This is both the 3/4 = 0.75 rate case and the attempts(5) != tasks(4) case.
FOUR_TASK_CORPUS = (
    _receipt("t-a", 1, 0.10, 1000, True, True),
    _receipt("t-b", 1, 0.20, 2000, True, True),
    _receipt("t-c", 1, 0.30, 3000, True, True),
    _receipt("t-late", 1, 0.40, 4000, True, False),
    _receipt("t-late", 2, 0.50, 5000, True, True),
)

#: A task whose attempt-1 receipt carries no ``gate`` chain at all (the gate
#: never ran), one whose gate has no ``evidence``, and one whose evidence has no
#: ``passed``. A missing chain is not a pass, and none of the three may raise.
MISSING_GATE_CORPUS = (
    _receipt("g-none", 1, 0.01, 100, True, None),
    {"task_id": "g-no-evidence", "attempt": 1, "gate": {},
     "driver_steps": [{"step": "run", "attempt": 1,
                       "receipt": {"spend": {"cost_usd": 0.02, "tokens": 200,
                                             "cost_reported": True}}}]},
    {"task_id": "g-no-passed", "attempt": 1,
     "gate": {"evidence": {"gates": {"diff-nonempty": True}}},
     "driver_steps": [{"step": "run", "attempt": 1,
                       "receipt": {"spend": {"cost_usd": 0.03, "tokens": 300,
                                             "cost_reported": True}}}]},
)

#: The whole reason ``cost_reported`` exists, as a pair. Both receipts
#: contribute exactly 0.0 to billed_usd and are indistinguishable in the money
#: column; only "silent" did not say, and only "silent" may be named.
ZERO_COST_PAIR = (
    _receipt("free-and-said-so", 1, 0.0, 12000, True, True),
    _receipt("silent", 1, 0.0, 34000, False, True),
)

#: Every receipt reports. The aggregate cost_reported must be True here -- a
#: stub that hardcodes False fails on this corpus, as one that hardcodes True
#: fails on ZERO_COST_PAIR and MIXED_REPORTING_CORPUS.
ALL_REPORTING_CORPUS = (
    _receipt("r-a", 1, 0.125, 1000, True, True),
    _receipt("r-b", 1, 0.375, 3000, True, True),
)

#: Three tasks, one of which did not report. The aggregate is unreliable and
#: must say so, and exactly that task is named. "z-quiet" sorts last by task_id
#: but is not last in input order, so the list is genuinely sorted, not merely
#: appended in encounter order.
MIXED_REPORTING_CORPUS = (
    _receipt("m-a", 1, 1.0, 10, True, True),
    _receipt("z-quiet", 1, 0.0, 20, False, True),
    _receipt("m-b", 1, 2.0, 30, True, True),
)

#: 0.1 + 0.2 == 0.30000000000000004 in float. The spec rounds billed_usd to 6 dp,
#: so the answer is exactly 0.3.
FLOAT_TAIL_CORPUS = (
    _receipt("f-a", 1, 0.1, 1, True, True),
    _receipt("f-b", 1, 0.2, 2, True, True),
)

#: Three tasks, one first pass: 1/3 = 0.3333333... rounds to 0.3333 at 4 dp.
THIRDS_CORPUS = (
    _receipt("h-a", 1, 0.0, 0, True, True),
    _receipt("h-b", 1, 0.0, 0, True, False),
    _receipt("h-c", 1, 0.0, 0, True, False),
)


def _copies(*groups):
    """Flatten fixture tuples into one fresh, mutable list of fresh receipts."""
    out = []
    for group in groups:
        out.extend(copy.deepcopy(item) for item in group)
    return out


class WorkerSpendFromReceiptTests(unittest.TestCase):
    """``worker_spend_from_receipt`` -- lift the run step's spend, or zero."""

    def test_it_reads_the_run_step_of_a_real_shaped_receipt(self):
        spend = scorecard.worker_spend_from_receipt(
            copy.deepcopy(REAL_SHAPED_RECEIPT)
        )
        self.assertEqual(spend["cost_usd"], 0.020864)
        self.assertEqual(spend["tokens"], 292309)
        self.assertIs(spend["cost_reported"], True)

    def test_it_reports_exactly_the_three_spend_keys(self):
        spend = scorecard.worker_spend_from_receipt(
            copy.deepcopy(REAL_SHAPED_RECEIPT)
        )
        self.assertEqual(
            set(spend), set(SPEND_KEYS),
            "cap/ceiling policy fields leaked into the spend figure",
        )

    def test_it_does_not_read_a_neighbouring_driver_step(self):
        # The prepare/gate/receipt steps carry decoy spends; the run step is at
        # index 2. Reading any fixed index but 2 lands on a decoy.
        spend = scorecard.worker_spend_from_receipt(
            copy.deepcopy(REAL_SHAPED_RECEIPT)
        )
        for decoy in (99.0, 88.0, 77.0):
            with self.subTest(decoy=decoy):
                self.assertNotEqual(
                    spend["cost_usd"], decoy,
                    "a non-run driver step was read as the worker's spend",
                )

    def test_a_receipt_with_no_driver_steps_is_zero(self):
        self.assertEqual(
            scorecard.worker_spend_from_receipt(
                copy.deepcopy(NO_DRIVER_STEPS_RECEIPT)
            ),
            ZERO_SPEND,
        )

    def test_driver_steps_without_a_run_are_zero(self):
        self.assertEqual(
            scorecard.worker_spend_from_receipt(
                copy.deepcopy(NO_RUN_STEP_RECEIPT)
            ),
            ZERO_SPEND,
        )

    def test_a_run_step_without_a_nested_receipt_is_zero(self):
        self.assertEqual(
            scorecard.worker_spend_from_receipt(
                copy.deepcopy(RUN_WITHOUT_RECEIPT)
            ),
            ZERO_SPEND,
        )

    def test_a_nested_receipt_without_a_spend_is_zero(self):
        self.assertEqual(
            scorecard.worker_spend_from_receipt(
                copy.deepcopy(RUN_RECEIPT_WITHOUT_SPEND)
            ),
            ZERO_SPEND,
        )

    def test_no_missing_structure_ever_raises(self):
        # Stated once more as a property: none of the degenerate shapes, nor an
        # empty dict, may propagate a KeyError/TypeError to the scorecard.
        for name, receipt in (
            ("empty", {}),
            ("no-driver-steps", NO_DRIVER_STEPS_RECEIPT),
            ("no-run", NO_RUN_STEP_RECEIPT),
            ("run-bare", RUN_WITHOUT_RECEIPT),
            ("no-spend", RUN_RECEIPT_WITHOUT_SPEND),
        ):
            with self.subTest(shape=name):
                self.assertEqual(
                    scorecard.worker_spend_from_receipt(copy.deepcopy(receipt)),
                    ZERO_SPEND,
                )

    def test_the_last_of_two_run_steps_wins(self):
        spend = scorecard.worker_spend_from_receipt(
            copy.deepcopy(TWO_RUN_STEPS_RECEIPT)
        )
        self.assertEqual(
            spend["cost_usd"], 0.25,
            "a re-run step did not supersede the earlier attempt",
        )
        self.assertEqual(spend["tokens"], 40000)

    def test_it_leaves_the_receipt_untouched(self):
        receipt = copy.deepcopy(REAL_SHAPED_RECEIPT)
        before = copy.deepcopy(receipt)
        scorecard.worker_spend_from_receipt(receipt)
        self.assertEqual(
            receipt, before,
            "worker_spend_from_receipt mutated the receipt it was handed",
        )


class WorkerTotalsTests(unittest.TestCase):
    """``worker_totals`` -- the corpus view, and what it refuses to hide."""

    def test_it_reports_exactly_the_eight_keys(self):
        totals = scorecard.worker_totals(_copies(FOUR_TASK_CORPUS))
        self.assertEqual(set(totals), set(TOTALS_KEYS))

    def test_attempts_and_tasks_differ_when_a_task_retried(self):
        totals = scorecard.worker_totals(_copies(FOUR_TASK_CORPUS))
        self.assertEqual(
            totals["attempts"], 5,
            "a retry's receipt was not counted as an attempt",
        )
        self.assertEqual(
            totals["tasks"], 4,
            "two receipts for one task were counted as two tasks",
        )

    def test_a_retrys_spend_still_counts(self):
        # Spend is spend: the failed first attempt burned real money and both
        # receipts must land in the totals.
        totals = scorecard.worker_totals(_copies(FOUR_TASK_CORPUS))
        self.assertEqual(totals["billed_usd"], 1.5)
        self.assertEqual(totals["tokens"], 15000)

    def test_all_reporting_receipts_give_a_reliable_total(self):
        totals = scorecard.worker_totals(_copies(ALL_REPORTING_CORPUS))
        self.assertIs(
            totals["cost_reported"], True,
            "every receipt reported, yet the total called itself unreliable",
        )
        self.assertEqual(totals["cost_unreported_tasks"], [])
        self.assertEqual(totals["billed_usd"], 0.5)

    def test_one_silent_receipt_makes_the_whole_total_unreliable(self):
        totals = scorecard.worker_totals(_copies(MIXED_REPORTING_CORPUS))
        self.assertIs(
            totals["cost_reported"], False,
            "a corpus containing an unreported cost claimed to be complete",
        )
        self.assertEqual(
            totals["cost_unreported_tasks"], ["z-quiet"],
            "the silent task was not named",
        )
        self.assertEqual(totals["billed_usd"], 3.0)

    def test_a_reported_zero_is_not_an_unreported_zero(self):
        # The whole reason cost_reported exists. Both receipts add 0.0 to the
        # money column; only the silent one is unreliable, and an implementation
        # that infers "no cost means no report" fails both halves at once.
        totals = scorecard.worker_totals(_copies(ZERO_COST_PAIR))
        self.assertEqual(totals["billed_usd"], 0.0)
        self.assertEqual(totals["tokens"], 46000)
        self.assertEqual(
            totals["cost_unreported_tasks"], ["silent"],
            "a zero cost that WAS reported was named as unreported, "
            "or the genuinely silent one was not named",
        )
        self.assertIs(totals["cost_reported"], False)

    def test_a_free_but_reporting_corpus_stays_reliable(self):
        totals = scorecard.worker_totals(
            _copies((ZERO_COST_PAIR[0],))
        )
        self.assertEqual(totals["billed_usd"], 0.0)
        self.assertIs(
            totals["cost_reported"], True,
            "a genuinely free run was misread as a run that did not say",
        )
        self.assertEqual(totals["cost_unreported_tasks"], [])

    def test_three_of_four_tasks_first_pass_is_three_quarters(self):
        totals = scorecard.worker_totals(_copies(FOUR_TASK_CORPUS))
        self.assertEqual(totals["first_pass_tasks"], 3)
        self.assertEqual(totals["first_pass_rate"], 0.75)

    def test_a_task_that_only_passed_on_attempt_two_is_not_a_first_pass(self):
        # "t-late" has a passing attempt-2 receipt. Counting any passing
        # receipt, rather than the attempt-1 one, gives 4/4 here.
        totals = scorecard.worker_totals(_copies(FOUR_TASK_CORPUS))
        self.assertNotEqual(
            totals["first_pass_tasks"], 4,
            "a pass on the second attempt was counted as a first pass",
        )

    def test_a_failing_attempt_one_gate_is_not_a_first_pass(self):
        only_failed = _copies((FOUR_TASK_CORPUS[3],))
        totals = scorecard.worker_totals(only_failed)
        self.assertEqual(totals["tasks"], 1)
        self.assertEqual(totals["first_pass_tasks"], 0)
        self.assertEqual(totals["first_pass_rate"], 0.0)

    def test_a_missing_gate_chain_is_not_a_first_pass(self):
        totals = scorecard.worker_totals(_copies(MISSING_GATE_CORPUS))
        self.assertEqual(totals["tasks"], 3)
        self.assertEqual(
            totals["first_pass_tasks"], 0,
            "an absent gate/evidence/passed chain was treated as a pass",
        )
        self.assertEqual(totals["first_pass_rate"], 0.0)

    def test_a_task_with_no_attempt_one_receipt_is_not_a_first_pass(self):
        # Only the attempt-2 receipt survived collection; nothing says the
        # first attempt passed, so it did not.
        totals = scorecard.worker_totals(_copies((FOUR_TASK_CORPUS[4],)))
        self.assertEqual(totals["tasks"], 1)
        self.assertEqual(totals["attempts"], 1)
        self.assertEqual(totals["first_pass_tasks"], 0)
        self.assertEqual(totals["first_pass_rate"], 0.0)

    def test_an_empty_corpus_is_zero_and_not_a_measured_zero(self):
        totals = scorecard.worker_totals([])
        self.assertEqual(set(totals), set(TOTALS_KEYS))
        self.assertEqual(totals["attempts"], 0)
        self.assertEqual(totals["tasks"], 0)
        self.assertEqual(totals["billed_usd"], 0.0)
        self.assertEqual(totals["tokens"], 0)
        self.assertEqual(totals["cost_unreported_tasks"], [])
        self.assertEqual(
            totals["first_pass_rate"], 0.0,
            "an empty corpus divided by zero tasks",
        )
        self.assertEqual(totals["first_pass_tasks"], 0)
        self.assertIs(
            totals["cost_reported"], False,
            "an empty corpus reported cost_reported True -- with no receipts "
            "nothing reported anything, so the zero is not a measured zero; "
            "'nothing failed to report' is not the same claim as 'this was "
            "measured and came to zero'",
        )

    def test_cost_is_rounded_to_six_decimal_places(self):
        totals = scorecard.worker_totals(_copies(FLOAT_TAIL_CORPUS))
        self.assertEqual(
            totals["billed_usd"], 0.3,
            "0.1 + 0.2 was not rounded to 6 dp",
        )

    def test_first_pass_rate_is_rounded_to_four_decimal_places(self):
        totals = scorecard.worker_totals(_copies(THIRDS_CORPUS))
        self.assertEqual(totals["tasks"], 3)
        self.assertEqual(totals["first_pass_tasks"], 1)
        self.assertEqual(
            totals["first_pass_rate"], 0.3333,
            "1/3 was not rounded to 4 dp",
        )

    def test_tokens_stay_an_int(self):
        totals = scorecard.worker_totals(_copies(FOUR_TASK_CORPUS))
        self.assertIsInstance(
            totals["tokens"], int,
            "the token total is not an int",
        )

    def test_it_leaves_the_corpus_untouched(self):
        receipts = _copies(FOUR_TASK_CORPUS, MIXED_REPORTING_CORPUS,
                           MISSING_GATE_CORPUS)
        before = copy.deepcopy(receipts)
        scorecard.worker_totals(receipts)
        self.assertEqual(
            receipts, before,
            "worker_totals mutated the receipts it was handed",
        )
        self.assertEqual(
            len(receipts), len(before),
            "worker_totals changed the length of the input list",
        )


if __name__ == "__main__":
    unittest.main()
