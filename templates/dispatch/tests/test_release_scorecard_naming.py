"""Coordinator-authored oracle for ``release_scorecard.py`` -- one name, one kind.

#91 fixed the top-level ``cost_usd`` block so an imputed list price is never
added to real metered spend. One nesting level down the trap was still set:

* ``frontier_totals(rows)`` returned a key literally called ``cost_usd``. It
  holds tokens priced off the hardcoded 2025 table in ``log-session-cost.sh``.
  Nobody is billed that. A reader printing ``card["frontier"]["cost_usd"]``
  saw $174.33 and every reason to call it money.
* ``worker_totals(receipts)`` returned a key also called ``cost_usd``, which
  *is* money -- metered OpenCode spend off the per-task receipts.

Two keys, the same name, opposite meanings, sitting directly beneath the block
whose entire purpose is to keep them apart. That is how the bug comes back, so
this file makes the names themselves the contract:

``frontier_totals``          -> ``usage_equivalent_usd``, never ``cost_usd``
``worker_totals``            -> ``billed_usd``, never ``cost_usd``
``worker_spend_from_receipt`` -> keeps ``cost_usd``: it mirrors the receipt

The third line is deliberate and is asserted, not merely tolerated. That
function is a reader, not a reporter: it lifts fields out of a receipt whose
own schema spells the field ``cost_usd``, and renaming it there would put the
oracle at odds with the artifact on disk. Nobody may "tidy" it for symmetry.

The second defect closed here is smaller and in the same function.
``worker_totals([])`` used to report ``cost_reported: True`` -- reading the
rule as "nothing failed to report". With no receipts nothing reported anything,
so the zero is not a measured zero, and a scorecard built from no receipts must
not present its total as reliable.

Written against the packet spec only. ``release_scorecard.py`` still spells
both figures ``cost_usd``, so this oracle fails on the key sets -- that is the
declared red.
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


#: The seven keys ``frontier_totals`` returns, exactly, as literal strings.
#: Not derived from the module: this frozenset IS the contract, so a rename in
#: the subject fails here rather than silently following along.
FRONTIER_KEYS = frozenset({
    "sessions",
    "turns",
    "assistant_msgs",
    "tool_calls",
    "duration_s",
    "usage_equivalent_usd",
    "rework_rounds",
})

#: The eight keys ``worker_totals`` returns, exactly, as literal strings.
WORKER_KEYS = frozenset({
    "attempts",
    "tasks",
    "billed_usd",
    "tokens",
    "cost_reported",
    "cost_unreported_tasks",
    "first_pass_tasks",
    "first_pass_rate",
})

#: The three keys ``worker_spend_from_receipt`` returns, exactly. This one
#: KEEPS ``cost_usd``; see the module docstring.
SPEND_KEYS = frozenset({"cost_usd", "tokens", "cost_reported"})

#: The banned spelling. It is banned in the two *reporters* only.
AMBIGUOUS_NAME = "cost_usd"


def _is_money_name(name: str) -> bool:
    """Does this key name claim to hold a currency figure?

    Deliberately syntactic. A future key called ``spend_usd`` or ``cost_usd``
    is caught by the shared-name test below without anyone remembering to add
    it to a list, which is the only way a naming oracle survives contact with
    later packets.
    """
    return name.endswith("_usd") or name == AMBIGUOUS_NAME


#: Two cumulative snapshots of one session plus a second session, so the
#: reduction actually has something to do and the totals are not trivially
#: zero. Sink rows carry the sink's OWN ``cost_usd`` field name -- that name is
#: not this packet's to change, and the fixture spells it on purpose.
SINK_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T10:00:00Z", "session": "loop-a", "project": "agentops",
     "model": "claude-opus-5", "out": 120, "cost_usd": 1.0, "turns": 1,
     "assistant_msgs": 2, "tool_calls": 1, "duration_s": 30,
     "rework_rounds": 0},
    {"ts": "2026-08-24T10:05:00Z", "session": "loop-a", "project": "agentops",
     "model": "claude-opus-5", "out": 480, "cost_usd": 4.25, "turns": 5,
     "assistant_msgs": 9, "tool_calls": 7, "duration_s": 210,
     "rework_rounds": 2},
    {"ts": "2026-08-24T10:06:00Z", "session": "loop-b", "project": "agentops",
     "model": "claude-opus-5", "out": 90, "cost_usd": 0.75, "turns": 2,
     "assistant_msgs": 3, "tool_calls": 2, "duration_s": 45,
     "rework_rounds": 1},
)

#: The reduced frontier figure for SINK_ROWS, by hand: 4.25 (loop-a's surviving
#: snapshot) + 0.75 (loop-b) == 5.0. Summing every row would give 6.0.
FRONTIER_USAGE_EQUIVALENT = 5.0


def _receipt(task_id, cost_usd, tokens, cost_reported=True, attempt=1,
             passed=True):
    """A receipt shaped like docs/evidence/receipts/<task>/receipt.json.

    The spend is nested driver_steps -> the ``run`` entry -> receipt -> spend,
    and it spells the field ``cost_usd`` because the artifact on disk does.
    """
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "task_id": task_id,
        "repo_id": "agentops",
        "attempt": attempt,
        "recorded_at": "2026-08-24T10:07:00Z",
        "route": "mechanical_bulk",
        "harness_model": "opencode-go/deepseek-v4-flash",
        "driver_steps": [
            {"step": "materialize", "attempt": attempt, "exit_code": 0,
             "stderr": ""},
            {"step": "run", "attempt": attempt, "exit_code": 0, "stderr": "",
             "receipt": {"spend": {"cost_usd": cost_usd, "tokens": tokens,
                                   "cost_reported": cost_reported,
                                   "cap_usd": 2.0, "within_cap": True}}},
        ],
        "gate": {"evidence": {"gates": {"diff-nonempty": True},
                              "passed": passed}},
    }


REPORTING_RECEIPT = _receipt("V5-M20-scorecard", 0.048002, 292309)
SILENT_RECEIPT = _receipt("V5-M22-silent-route", 0.0, 41000,
                          cost_reported=False)

#: The billed figure for the one reporting receipt, by hand.
WORKER_BILLED = 0.048002


def _rows():
    return copy.deepcopy(list(SINK_ROWS))


def _receipts(*receipts):
    return [copy.deepcopy(receipt) for receipt in receipts]


class FrontierTotalsNamingTests(unittest.TestCase):
    """The imputed figure must not be spelled like money."""

    def test_it_reports_exactly_the_seven_declared_names(self):
        totals = scorecard.frontier_totals(_rows())
        self.assertEqual(
            set(totals), set(FRONTIER_KEYS),
            "frontier_totals' keys are not exactly the seven declared names",
        )

    def test_the_imputed_figure_is_named_usage_equivalent_usd(self):
        totals = scorecard.frontier_totals(_rows())
        self.assertIn(
            "usage_equivalent_usd", totals,
            "frontier_totals does not report usage_equivalent_usd",
        )
        self.assertAlmostEqual(
            totals["usage_equivalent_usd"], FRONTIER_USAGE_EQUIVALENT,
            places=6,
            msg="usage_equivalent_usd is not the reduced survivors' figure -- "
                "the rename dropped or recomputed the value",
        )

    def test_frontier_totals_reports_no_key_named_cost_usd(self):
        """The whole point. Stated as an absence so nobody can add it back.

        $174.33 of tokens priced off a hardcoded table is not $174.33 of
        spend, and a key called ``cost_usd`` invites every reader to treat it
        as though it were.
        """
        totals = scorecard.frontier_totals(_rows())
        self.assertNotIn(
            AMBIGUOUS_NAME, totals,
            "frontier_totals still reports 'cost_usd' -- an imputed list "
            "price under the same name real metered spend uses is exactly the "
            "conflation #91 removed one level up",
        )

    def test_it_reports_no_key_named_cost_usd_for_an_empty_sink_either(self):
        totals = scorecard.frontier_totals([])
        self.assertEqual(set(totals), set(FRONTIER_KEYS))
        self.assertNotIn(
            AMBIGUOUS_NAME, totals,
            "the empty sink took a different shape from a populated one",
        )

    def test_the_sink_rows_own_cost_usd_field_is_not_renamed_by_reading(self):
        """It reads ``row['cost_usd']``; only what it REPORTS is renamed."""
        rows = _rows()
        before = copy.deepcopy(rows)
        scorecard.frontier_totals(rows)
        self.assertEqual(
            rows, before,
            "frontier_totals rewrote the sink rows it was handed",
        )
        self.assertIn(
            AMBIGUOUS_NAME, rows[0],
            "the fixture's sink row lost its own cost_usd field",
        )


class WorkerTotalsNamingTests(unittest.TestCase):
    """The metered figure must not share a name with the imputed one."""

    def test_it_reports_exactly_the_eight_declared_names(self):
        totals = scorecard.worker_totals(_receipts(REPORTING_RECEIPT))
        self.assertEqual(
            set(totals), set(WORKER_KEYS),
            "worker_totals' keys are not exactly the eight declared names",
        )

    def test_the_metered_figure_is_named_billed_usd(self):
        totals = scorecard.worker_totals(_receipts(REPORTING_RECEIPT))
        self.assertIn(
            "billed_usd", totals,
            "worker_totals does not report billed_usd",
        )
        self.assertAlmostEqual(
            totals["billed_usd"], WORKER_BILLED, places=6,
            msg="billed_usd is not the receipts' metered spend -- the rename "
                "dropped or recomputed the value",
        )

    def test_worker_totals_reports_no_key_named_cost_usd(self):
        totals = scorecard.worker_totals(_receipts(REPORTING_RECEIPT))
        self.assertNotIn(
            AMBIGUOUS_NAME, totals,
            "worker_totals still reports 'cost_usd' -- the name it used to "
            "share with the frontier half's imputed figure",
        )

    def test_it_reports_no_key_named_cost_usd_for_an_empty_corpus_either(self):
        totals = scorecard.worker_totals([])
        self.assertEqual(set(totals), set(WORKER_KEYS))
        self.assertNotIn(
            AMBIGUOUS_NAME, totals,
            "the empty corpus took a different shape from a populated one",
        )


class NoSharedMoneyNameTests(unittest.TestCase):
    """The invariant, stated over the pair rather than over one function."""

    def test_the_two_reporters_share_no_currency_key_name(self):
        frontier = scorecard.frontier_totals(_rows())
        worker = scorecard.worker_totals(_receipts(REPORTING_RECEIPT))
        frontier_money = {k for k in frontier if _is_money_name(k)}
        worker_money = {k for k in worker if _is_money_name(k)}
        self.assertTrue(
            frontier_money,
            "frontier_totals reports no currency-named key at all -- the "
            "imputed figure was dropped rather than renamed",
        )
        self.assertTrue(
            worker_money,
            "worker_totals reports no currency-named key at all -- the "
            "billed figure was dropped rather than renamed",
        )
        self.assertEqual(
            frontier_money & worker_money, set(),
            "frontier_totals and worker_totals report a currency figure under "
            f"the same key name ({sorted(frontier_money & worker_money)}) -- "
            "one is an imputed list price nobody was billed and the other is "
            "metered spend; a shared name is how they get added together",
        )

    def test_neither_reporter_uses_the_ambiguous_name(self):
        frontier = scorecard.frontier_totals(_rows())
        worker = scorecard.worker_totals(_receipts(REPORTING_RECEIPT))
        for label, totals in (("frontier_totals", frontier),
                              ("worker_totals", worker)):
            with self.subTest(function=label):
                self.assertNotIn(
                    AMBIGUOUS_NAME, totals,
                    f"{label} reports 'cost_usd'; that spelling now belongs "
                    "only to the receipt-mirroring reader",
                )

    def test_the_two_figures_are_different_numbers_on_this_corpus(self):
        """Names apart, the values must not have been crossed over.

        The fixture is chosen so the two figures cannot be confused: $5.00
        imputed against $0.048002 metered.
        """
        frontier = scorecard.frontier_totals(_rows())
        worker = scorecard.worker_totals(_receipts(REPORTING_RECEIPT))
        self.assertAlmostEqual(
            frontier["usage_equivalent_usd"], FRONTIER_USAGE_EQUIVALENT,
            places=6,
            msg="the frontier figure is not the imputed one",
        )
        self.assertAlmostEqual(
            worker["billed_usd"], WORKER_BILLED, places=6,
            msg="the worker figure is not the metered one",
        )
        self.assertNotAlmostEqual(
            frontier["usage_equivalent_usd"], worker["billed_usd"], places=6,
            msg="the two halves report the same number -- one was computed "
                "from the other's inputs",
        )


class SpendReaderKeepsTheReceiptsNameTests(unittest.TestCase):
    """``worker_spend_from_receipt`` mirrors the receipt: cost_usd STAYS.

    This is not an oversight and must not be "tidied" into billed_usd for
    symmetry with ``worker_totals``. The function is a reader whose job is to
    lift three fields out of an artifact on disk whose schema spells the field
    ``cost_usd``; renaming it here would put the oracle at odds with every
    receipt ``hybrid_dispatch.worker_spend`` has ever written.
    """

    def test_worker_spend_from_receipt_still_returns_cost_usd_on_purpose(self):
        spend = scorecard.worker_spend_from_receipt(
            copy.deepcopy(REPORTING_RECEIPT))
        self.assertEqual(
            set(spend), set(SPEND_KEYS),
            "worker_spend_from_receipt's keys are not exactly cost_usd/"
            "tokens/cost_reported",
        )
        self.assertIn(
            AMBIGUOUS_NAME, spend,
            "worker_spend_from_receipt lost its 'cost_usd' key -- it mirrors "
            "the receipt's own field names and is not a reporter; renaming it "
            "here breaks the mirror for no gain",
        )
        self.assertAlmostEqual(
            spend[AMBIGUOUS_NAME], WORKER_BILLED, places=6,
            msg="worker_spend_from_receipt's cost_usd is not the run step's "
                "spend",
        )

    def test_the_zero_result_keeps_the_same_three_names(self):
        spend = scorecard.worker_spend_from_receipt({"driver_steps": []})
        self.assertEqual(
            set(spend), set(SPEND_KEYS),
            "the zero result is a different shape from the real one",
        )
        self.assertEqual(spend[AMBIGUOUS_NAME], 0.0)
        self.assertIs(spend["cost_reported"], False)


class EmptyCorpusIsNotAMeasuredZeroTests(unittest.TestCase):
    """``cost_reported`` answers "was this measured", not "did nothing fail"."""

    def test_an_empty_corpus_is_not_reported(self):
        totals = scorecard.worker_totals([])
        self.assertIs(
            totals["cost_reported"], False,
            "worker_totals([])['cost_reported'] is True -- with no receipts "
            "nothing reported anything, so the 0.0 is not a measured zero. "
            "'nothing failed to report' is a different claim from 'this was "
            "measured and came to zero', and only the second one makes a "
            "total reliable",
        )
        self.assertEqual(
            totals["billed_usd"], 0.0,
            "the empty corpus is not zeroed",
        )
        self.assertEqual(
            totals["cost_unreported_tasks"], [],
            "the empty corpus named a silent task it never saw",
        )

    def test_one_reporting_receipt_is_reported(self):
        totals = scorecard.worker_totals(_receipts(REPORTING_RECEIPT))
        self.assertIs(
            totals["cost_reported"], True,
            "a single receipt that reported its cost did not make the total "
            "reported -- the existing rule still stands for a non-empty "
            "corpus",
        )
        self.assertEqual(totals["cost_unreported_tasks"], [])

    def test_one_non_reporting_receipt_is_not_reported(self):
        totals = scorecard.worker_totals(_receipts(SILENT_RECEIPT))
        self.assertIs(
            totals["cost_reported"], False,
            "a receipt whose provider reported no cost was read as a free "
            "run rather than a silent one",
        )
        self.assertEqual(
            totals["cost_unreported_tasks"], ["V5-M22-silent-route"],
            "the silent task was not named",
        )

    def test_the_empty_and_silent_answers_agree(self):
        """Two different reasons, one honest answer: not measured."""
        self.assertIs(
            scorecard.worker_totals([])["cost_reported"],
            scorecard.worker_totals(_receipts(SILENT_RECEIPT))["cost_reported"],
        )

    def test_a_scorecard_over_no_receipts_is_not_reliable(self):
        """The consequence, pinned where a reader will meet it.

        ``total_reliable`` is the worker half's ``cost_reported``, so a
        scorecard built from an empty receipts directory now says False. That
        is the honest answer -- nothing was measured -- and it is a deliberate
        change from the old True.
        """
        card = scorecard.build_scorecard(
            "v5", _rows(), [], [], "2026-08-24T10:30:00Z")
        self.assertIs(
            card["cost_usd"]["total_reliable"], False,
            "a scorecard built from no receipts still calls its total "
            "reliable",
        )
        self.assertEqual(
            card["cost_usd"]["total_reliable"], card["worker"]["cost_reported"],
            "total_reliable is no longer the worker half's cost_reported",
        )
        self.assertEqual(
            card["cost_usd"]["total_billed_usd"], 0.0,
            "no worker ran, yet something was billed",
        )


class BuildScorecardReadsTheRenamedKeysTests(unittest.TestCase):
    """The join must follow the rename rather than keep its own copy."""

    def test_the_cost_block_reads_the_two_renamed_keys(self):
        card = scorecard.build_scorecard(
            "v5", _rows(), _receipts(REPORTING_RECEIPT), [],
            "2026-08-24T10:30:00Z")
        self.assertEqual(
            card["cost_usd"]["frontier_usage_equivalent_usd"],
            scorecard.frontier_totals(_rows())["usage_equivalent_usd"],
            "frontier_usage_equivalent_usd is not frontier_totals' "
            "usage_equivalent_usd",
        )
        self.assertEqual(
            card["cost_usd"]["worker_billed_usd"],
            scorecard.worker_totals(_receipts(REPORTING_RECEIPT))["billed_usd"],
            "worker_billed_usd is not worker_totals' billed_usd",
        )
        self.assertEqual(
            set(card["cost_usd"]),
            {"worker_billed_usd", "frontier_usage_equivalent_usd",
             "total_billed_usd", "commensurable", "total_reliable"},
            "the settled five cost_usd names changed; this packet renames the "
            "two halves' own keys, not the block #91 built over them",
        )

    def test_the_halves_still_carry_their_own_renamed_keys(self):
        card = scorecard.build_scorecard(
            "v5", _rows(), _receipts(REPORTING_RECEIPT), [],
            "2026-08-24T10:30:00Z")
        self.assertIn("usage_equivalent_usd", card["frontier"])
        self.assertNotIn(AMBIGUOUS_NAME, card["frontier"])
        self.assertIn("billed_usd", card["worker"])
        self.assertNotIn(AMBIGUOUS_NAME, card["worker"])


if __name__ == "__main__":
    unittest.main()
