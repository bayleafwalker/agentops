"""Coordinator-authored oracle for ``release_scorecard.py`` -- the two kinds.

The sibling oracles pin what ``build_scorecard`` computes. This one pins the
single thing that must never be tidied away again: the scorecard's two cost
halves are NOT the same kind of number, and nothing in the output may add them.

* ``frontier_usage_equivalent_usd`` is ``tokens x a hardcoded 2025 list-price
  table``, computed by ``templates/dispatch/hooks/log-session-cost.sh``. Nothing
  meters it. On a subscription plan it is never billed. It is a
  usage-equivalent: good for comparing releases against each other, meaningless
  as money.
* ``worker_billed_usd`` is OpenCode's own ``step-finish`` accounting -- real
  metered API spend, actually charged.

In the live run the old summed ``total`` read $241.43, of which $0.11 was money
and $241.33 was an imputation. Anyone opening that scorecard reads the total as
spend, which is the exact failure the two-source design existed to prevent.

The contract, therefore:

* ``total_billed_usd`` == ``worker_billed_usd``. There is no other billed money
  in the system.
* ``commensurable`` is ``False``, always, said in the data.
* the five key names are spelled exactly as declared.

This file is deliberately narrow and deliberately redundant with its siblings.
It is the one that fails if someone later renames the keys back to
``frontier``/``worker``/``total``, or reintroduces the sum "for convenience".

The properties are stated as INVARIANCES rather than as fixed numbers, because
an invariance cannot be satisfied by hardcoding:

* moving the frontier figure must not move ``total_billed_usd`` at all.
* moving the worker figure must move ``total_billed_usd`` by exactly as much.

``build_scorecard`` is pure: no file reads, no writes, no argv, no git.
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


#: The five ``cost_usd`` key names, as literal strings. Not read off the module
#: and not derived: this frozenset IS the wire format, and a rename in the
#: subject must fail here rather than silently follow.
COST_KEYS = frozenset({
    "worker_billed_usd",
    "frontier_usage_equivalent_usd",
    "total_billed_usd",
    "commensurable",
    "total_reliable",
})

#: Names the old, conflating contract used. None of them may reappear.
FORBIDDEN_COST_KEYS = frozenset({"frontier", "worker", "total"})


#: A sink corpus with the live run's proportions: a very large imputed frontier
#: figure beside a tiny real worker spend. Two sessions, one of which stopped
#: twice, so ``reduce_sessions`` still has work to do and the frontier figure
#: is not simply the sum of the rows.
SINK_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T09:00:00Z", "session": "loop-a", "model": "claude-opus-5",
     "out": 4000, "cost_usd": 88.5, "turns": 40, "assistant_msgs": 70,
     "tool_calls": 55, "duration_s": 3600, "rework_rounds": 1},
    {"ts": "2026-08-24T09:40:00Z", "session": "loop-a", "model": "claude-opus-5",
     "out": 9000, "cost_usd": 180.25, "turns": 91, "assistant_msgs": 155,
     "tool_calls": 120, "duration_s": 7200, "rework_rounds": 2},
    {"ts": "2026-08-24T09:55:00Z", "session": "loop-b", "model": "claude-opus-5",
     "out": 2500, "cost_usd": 61.08, "turns": 24, "assistant_msgs": 41,
     "tool_calls": 30, "duration_s": 1900, "rework_rounds": 0},
)


def _receipt(task_id, cost_usd, tokens=100000, cost_reported=True, attempt=1):
    """A receipt shaped like docs/evidence/receipts/*/receipt.json.

    The spend lives under driver_steps -> the "run" entry -> receipt -> spend,
    which is the lift T-6b pins; this oracle only needs receipts real enough
    that ``worker_totals`` reads them the way production will.
    """
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "task_id": task_id,
        "repo_id": "agentops",
        "attempt": attempt,
        "route": "mechanical_bulk",
        "harness_model": "opencode-go/deepseek-v4-flash",
        "driver_steps": [
            {"step": "run", "attempt": attempt, "exit_code": 0,
             "receipt": {"spend": {"cost_usd": cost_usd, "tokens": tokens,
                                   "cost_reported": cost_reported}}},
        ],
        "gate": {"evidence": {"gates": {"diff-nonempty": True}, "passed": True}},
    }


RECEIPTS: tuple[dict, ...] = (
    _receipt("V5-M13-retry-branch", 0.062501),
    _receipt("V5-M20-scorecard", 0.048002),
)

RECORDED_AT = "2026-08-24T10:30:00Z"


def _build(rows=SINK_ROWS, receipts=RECEIPTS, escalations=(), release="v5"):
    """Fresh deep copies every call, so no fixture can be mutated across tests."""
    return scorecard.build_scorecard(
        release,
        copy.deepcopy(list(rows)),
        copy.deepcopy(list(receipts)),
        copy.deepcopy(list(escalations)),
        RECORDED_AT,
    )


def _doubled_rows():
    """The same sink with every row's ``cost_usd`` doubled, nothing else touched.

    Doubling every row doubles the reduced survivors' costs too, so the
    frontier usage-equivalent doubles exactly -- without changing turns,
    sessions, or anything the worker half reads.
    """
    rows = copy.deepcopy(list(SINK_ROWS))
    for row in rows:
        row["cost_usd"] = row["cost_usd"] * 2
    return rows


class KeyNamesTests(unittest.TestCase):
    """The names themselves are the contract."""

    def test_cost_block_keys_are_exactly_the_five_declared_names(self):
        cost = _build()["cost_usd"]
        self.assertEqual(
            set(cost), set(COST_KEYS),
            "cost_usd's keys are not exactly the five declared names -- if "
            "they were 'tidied' back to frontier/worker/total, the two kinds "
            "of number have been conflated again",
        )

    def test_the_old_conflating_names_are_gone(self):
        cost = _build()["cost_usd"]
        for name in sorted(FORBIDDEN_COST_KEYS):
            self.assertNotIn(
                name, cost,
                f"cost_usd.{name} is back; that spelling is what let an "
                "imputed list price be read as spend",
            )

    def test_the_key_names_survive_an_empty_corpus(self):
        cost = _build(rows=(), receipts=())["cost_usd"]
        self.assertEqual(
            set(cost), set(COST_KEYS),
            "the cost block changes shape when there is nothing to report",
        )

    def test_the_frontier_and_worker_blocks_are_still_top_level(self):
        """Renaming inside cost_usd must not have hidden the halves themselves.

        Both remain separately visible at the top level; this oracle only
        governs how the two figures are labelled and combined.
        """
        card = _build()
        self.assertIn("frontier", card, "the frontier half vanished")
        self.assertIn("worker", card, "the worker half vanished")


class TotalBilledIsInvariantToTheFrontierTests(unittest.TestCase):
    """Moving the imputed figure must not move the money figure at all."""

    def test_doubling_every_sink_row_does_not_change_total_billed_usd(self):
        base = _build()["cost_usd"]
        doubled = _build(rows=_doubled_rows())["cost_usd"]
        self.assertEqual(
            doubled["total_billed_usd"], base["total_billed_usd"],
            "doubling the frontier's imputed cost moved total_billed_usd -- "
            "the imputation is leaking into the billed figure",
        )
        self.assertEqual(
            doubled["worker_billed_usd"], base["worker_billed_usd"],
            "the worker's billed spend moved when only the sink changed",
        )

    def test_doubling_every_sink_row_does_double_the_usage_equivalent(self):
        """The other side of the invariance: the figure is preserved, not dropped."""
        base = _build()["cost_usd"]
        doubled = _build(rows=_doubled_rows())["cost_usd"]
        self.assertAlmostEqual(
            doubled["frontier_usage_equivalent_usd"],
            base["frontier_usage_equivalent_usd"] * 2, places=6,
            msg="frontier_usage_equivalent_usd did not double when every sink "
                "row's cost doubled -- the usage figure is not being reported",
        )
        self.assertGreater(
            doubled["frontier_usage_equivalent_usd"], 0.0,
            "the frontier usage-equivalent is zero on a non-empty sink",
        )

    def test_removing_the_sink_entirely_leaves_total_billed_usd_alone(self):
        with_sink = _build()["cost_usd"]
        without_sink = _build(rows=())["cost_usd"]
        self.assertEqual(
            without_sink["total_billed_usd"], with_sink["total_billed_usd"],
            "total_billed_usd changed when the frontier sink went away; the "
            "billed total must depend on the receipts alone",
        )
        self.assertEqual(
            without_sink["frontier_usage_equivalent_usd"], 0.0,
            "an empty sink is not a zero usage-equivalent",
        )


class TotalBilledTracksTheWorkerTests(unittest.TestCase):
    """Symmetrically: the money figure follows the receipts, exactly."""

    def test_total_billed_usd_equals_worker_billed_usd(self):
        cost = _build()["cost_usd"]
        self.assertEqual(
            cost["total_billed_usd"], cost["worker_billed_usd"],
            "total_billed_usd is not exactly worker_billed_usd",
        )

    def test_total_billed_usd_is_not_the_sum_of_the_two_halves(self):
        cost = _build()["cost_usd"]
        summed = round(
            cost["frontier_usage_equivalent_usd"] + cost["worker_billed_usd"], 6
        )
        self.assertNotAlmostEqual(
            cost["total_billed_usd"], summed, places=6,
            msg="total_billed_usd is frontier + worker; on this corpus that is "
                "hundreds of dollars of imputation reported as spend",
        )

    def test_no_value_anywhere_in_the_cost_block_holds_the_sum(self):
        cost = _build()["cost_usd"]
        summed = (
            cost["frontier_usage_equivalent_usd"] + cost["worker_billed_usd"]
        )
        for key, value in cost.items():
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            self.assertNotAlmostEqual(
                value, summed, places=6,
                msg=f"cost_usd.{key} holds frontier + worker under another "
                    "name; the sum is the defect, whatever it is called",
            )

    def test_changing_the_receipts_moves_total_billed_usd_by_exactly_that(self):
        base = _build()["cost_usd"]
        richer = _build(receipts=RECEIPTS + (_receipt("V5-M21-doctor", 0.5),))
        self.assertAlmostEqual(
            richer["cost_usd"]["total_billed_usd"],
            round(base["total_billed_usd"] + 0.5, 6), places=6,
            msg="adding a receipt that billed $0.50 did not raise "
                "total_billed_usd by $0.50",
        )
        self.assertEqual(
            richer["cost_usd"]["frontier_usage_equivalent_usd"],
            base["frontier_usage_equivalent_usd"],
            "the frontier usage-equivalent moved when only receipts changed",
        )

    def test_no_receipts_means_nothing_was_billed(self):
        cost = _build(receipts=())["cost_usd"]
        self.assertEqual(
            cost["worker_billed_usd"], 0.0,
            "worker_billed_usd is not 0.0 with no receipts",
        )
        self.assertEqual(
            cost["total_billed_usd"], 0.0,
            "no worker ran, so nothing was billed -- total_billed_usd must be "
            "0.0 and not the frontier's imputed figure",
        )
        self.assertGreater(
            cost["frontier_usage_equivalent_usd"], 0.0,
            "the frontier still burned tokens; its usage-equivalent must stay",
        )

    def test_total_billed_usd_matches_worker_totals_directly(self):
        cost = _build()["cost_usd"]
        self.assertEqual(
            cost["total_billed_usd"],
            scorecard.worker_totals(copy.deepcopy(list(RECEIPTS)))["billed_usd"],
            "total_billed_usd is not what worker_totals reports",
        )


class CommensurableTests(unittest.TestCase):
    """The claim lives in the data, not only in a docstring."""

    def test_commensurable_is_false_on_a_full_corpus(self):
        self.assertIs(
            _build()["cost_usd"]["commensurable"], False,
            "commensurable is not the literal bool False",
        )

    def test_commensurable_is_false_on_empty_inputs(self):
        for label, card in (
            ("no rows", _build(rows=())),
            ("no receipts", _build(receipts=())),
            ("nothing at all", _build(rows=(), receipts=())),
        ):
            with self.subTest(corpus=label):
                self.assertIs(
                    card["cost_usd"]["commensurable"], False,
                    f"commensurable is not False with {label}; the two halves "
                    "are never the same kind of number, empty or not",
                )

    def test_commensurable_is_false_when_only_one_half_has_data(self):
        self.assertIs(
            _build(rows=_doubled_rows(), receipts=())["cost_usd"]["commensurable"],
            False,
            "commensurable became True once a half was empty",
        )


class TotalReliableTests(unittest.TestCase):
    """``total_reliable`` keeps its meaning: did every receipt actually report."""

    def test_total_reliable_is_the_worker_halfs_cost_reported(self):
        card = _build()
        self.assertIs(
            card["cost_usd"]["total_reliable"], True,
            "total_reliable is not True when every receipt reported",
        )
        self.assertEqual(
            card["cost_usd"]["total_reliable"], card["worker"]["cost_reported"],
            "total_reliable diverged from the worker half's cost_reported",
        )

    def test_a_silent_receipt_makes_total_reliable_false(self):
        silent = RECEIPTS + (
            _receipt("V5-M22-silent-route", 0.0, cost_reported=False),
        )
        card = _build(receipts=silent)
        self.assertIs(
            card["cost_usd"]["total_reliable"], False,
            "a route that reported no cost still presents as reliable; 0.0 "
            "from a silent provider is not the same as a free model",
        )
        self.assertIs(
            card["cost_usd"]["commensurable"], False,
            "commensurable is not False on a silent receipt",
        )


class PurityTests(unittest.TestCase):

    def test_build_scorecard_does_not_mutate_its_inputs(self):
        rows = copy.deepcopy(list(SINK_ROWS))
        receipts = copy.deepcopy(list(RECEIPTS))
        escalations: list = []
        before = copy.deepcopy((rows, receipts, escalations))
        scorecard.build_scorecard("v5", rows, receipts, escalations, RECORDED_AT)
        self.assertEqual(
            (rows, receipts, escalations), before,
            "build_scorecard mutated the inputs it was handed",
        )

    def test_repeated_builds_are_equal(self):
        self.assertEqual(
            _build(), _build(),
            "two builds over the same corpus disagree",
        )


if __name__ == "__main__":
    unittest.main()
