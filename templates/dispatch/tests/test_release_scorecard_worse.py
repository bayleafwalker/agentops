"""Coordinator-authored oracle for ``release_scorecard.py`` -- the trend detector.

T-6a/T-6b pinned the two cost halves and T-7's sibling pinned the assembly
(``build_scorecard``). This file pins the one function that reads a *series* of
those scorecards and says whether the loop is getting worse:

``detect_worse(scorecards) -> dict``

``scorecards`` arrives in release order, oldest first. The pathway names what
"worse" looks like so it is recognizable rather than argued about: rework rounds
up, escalations up, or frontier turns flat while the frontier's own cost rises
-- any one of them for two consecutive releases. Two consecutive releases means the signal worsened
across two consecutive TRANSITIONS, so it takes THREE scorecards to fire. One bad
release is noise; two in a row is a trend, and that shape is what most of the
tests below exist to hold down.

Three properties are load-bearing and are asserted directly:

* the three signals are INDEPENDENT. Each one fires alone, in its own named
  test, with the other two held clean -- a detector that fires on the wrong
  signal, or that ORs them together internally, fails here.
* equality pulls in OPPOSITE directions across the signals. ``rework_rounds``
  equal is not a rise and must not fire; ``turns`` equal with cost rising IS
  "flat" and must fire. An implementation that reuses one comparison operator
  everywhere gets exactly one of these wrong.
* "not enough series" is not "not worse". Fewer than three scorecards sets
  ``insufficient_series`` True so a caller cannot read one as the other.

The cost half ``turns_flat_cost_up`` reads is
``cost_usd["frontier_usage_equivalent_usd"]``, NOT the billed total. The signal
asks "am I burning more frontier attention-equivalent for the same number of
turns", and that is the half that moves with coordinator behaviour. A worker
that costs more money is a different question and must not fire this alarm --
see ``WorkerHalfIsNotTheSignalTests``.

``detect_worse`` is pure: no file reads, no writes, no argv.

Written against the packet spec only. ``release_scorecard.py`` exists and
carries the five earlier functions, but not ``detect_worse`` -- so this oracle
fails at attribute lookup. That is the declared red.
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


#: The three keys ``detect_worse`` returns, exactly.
TOP_LEVEL_KEYS = frozenset({"worse", "signals", "insufficient_series"})

#: The fixed signal order. ``signals`` is sorted by this and not by discovery
#: order, so two runs over the same data read the same.
SIGNAL_ORDER = ("rework", "escalations", "turns_flat_cost_up")


def card(release, rework, turns, escalations, cost, worker=0.001):
    """Return a minimal scorecard-shaped dict.

    Deliberately hand-written rather than produced by ``build_scorecard``: the
    detector must be gradeable on a synthetic series, and coupling the two
    would make this oracle fail for the assembly's reasons instead of its own.
    Only the fields the rule actually reads are populated, plus the
    surrounding shape so a detector that indexes the real scorecard layout
    finds what it expects. ``cost`` is the frontier usage-equivalent -- the
    half the signal is about -- and ``worker`` is the billed money, held at a
    constant trickle unless a test moves it deliberately.
    """
    return {
        "schema_version": "workflow-scorecard/v1",
        "release": release,
        "frontier": {"rework_rounds": rework, "turns": turns},
        "escalations": {"count": escalations},
        "cost_usd": {
            "frontier_usage_equivalent_usd": cost,
            "worker_billed_usd": worker,
            "total_billed_usd": worker,
            "commensurable": False,
            "total_reliable": True,
        },
    }


def series(*specs):
    """Build a release series, auto-naming releases r1, r2, ... oldest first."""
    return [
        card(f"r{index}", rework, turns, escalations, cost)
        for index, (rework, turns, escalations, cost) in enumerate(specs, start=1)
    ]


# A loop that is genuinely improving: rework falling, escalations falling,
# turns falling, cost falling. Nothing may fire on this, and it is the clean
# background against which the single-signal series below are built.
IMPROVING = series((3, 10, 3, 5.0), (2, 8, 2, 4.0), (1, 6, 1, 3.0))


class DetectWorseContractTests(unittest.TestCase):
    """The return shape itself, independent of which signals fire."""

    def test_returns_exactly_the_three_declared_keys(self):
        result = scorecard.detect_worse(IMPROVING)
        self.assertEqual(set(result), TOP_LEVEL_KEYS)

    def test_clean_improving_series_is_not_worse(self):
        result = scorecard.detect_worse(IMPROVING)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])
        self.assertIs(result["insufficient_series"], False)


class InsufficientSeriesTests(unittest.TestCase):
    """Fewer than three scorecards cannot show a two-transition trend.

    The honest answer is "not enough series to say", which is a different claim
    from "not worse" -- hence the separate flag.
    """

    def test_zero_scorecards(self):
        result = scorecard.detect_worse([])
        self.assertIs(result["insufficient_series"], True)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])

    def test_one_scorecard(self):
        result = scorecard.detect_worse(series((1, 10, 1, 1.0)))
        self.assertIs(result["insufficient_series"], True)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])

    def test_two_scorecards_even_when_both_transitions_would_be_bad(self):
        # Every signal worsens across this single transition. One transition is
        # still not a trend, and the series is too short regardless.
        pair = series((1, 5, 1, 1.0), (9, 50, 9, 9.0))
        result = scorecard.detect_worse(pair)
        self.assertIs(result["insufficient_series"], True)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])

    def test_three_scorecards_clears_the_flag(self):
        result = scorecard.detect_worse(IMPROVING)
        self.assertIs(result["insufficient_series"], False)


class SingleSignalTests(unittest.TestCase):
    """Each signal fires ALONE, with the other two held clean."""

    def test_rework_rising_twice_fires_only_rework(self):
        # rework 1 -> 2 -> 3; escalations and turns and cost all falling.
        rising = series((1, 10, 3, 5.0), (2, 8, 2, 4.0), (3, 6, 1, 3.0))
        result = scorecard.detect_worse(rising)
        self.assertIs(result["worse"], True)
        self.assertEqual([s["signal"] for s in result["signals"]], ["rework"])
        self.assertEqual(result["signals"][0]["releases"], ["r1", "r2", "r3"])
        self.assertEqual(result["signals"][0]["values"], [1, 2, 3])

    def test_escalations_rising_twice_fires_only_escalations(self):
        # escalations 1 -> 2 -> 3; rework, turns and cost all falling.
        rising = series((3, 10, 1, 5.0), (2, 8, 2, 4.0), (1, 6, 3, 3.0))
        result = scorecard.detect_worse(rising)
        self.assertIs(result["worse"], True)
        self.assertEqual([s["signal"] for s in result["signals"]], ["escalations"])
        self.assertEqual(result["signals"][0]["releases"], ["r1", "r2", "r3"])
        self.assertEqual(result["signals"][0]["values"], [1, 2, 3])

    def test_turns_flat_while_cost_rises_fires_only_that_signal(self):
        # turns held at 6 while cost climbs 3 -> 4 -> 5: paying more for the
        # same amount of frontier attention, which is the whole point of the
        # signal. rework and escalations falling so neither can be credited.
        flat = series((3, 6, 3, 3.0), (2, 6, 2, 4.0), (1, 6, 1, 5.0))
        result = scorecard.detect_worse(flat)
        self.assertIs(result["worse"], True)
        self.assertEqual(
            [s["signal"] for s in result["signals"]], ["turns_flat_cost_up"]
        )
        self.assertEqual(result["signals"][0]["releases"], ["r1", "r2", "r3"])
        self.assertEqual(
            result["signals"][0]["values"], [[6, 3.0], [6, 4.0], [6, 5.0]]
        )

    def test_turns_rising_while_cost_rises_also_fires_the_flat_signal(self):
        # ">= " means turns that FAIL TO DROP, so outright rising turns with
        # rising cost is the worse case of the same shape and must fire.
        climbing = series((3, 6, 3, 3.0), (2, 7, 2, 4.0), (1, 9, 1, 5.0))
        result = scorecard.detect_worse(climbing)
        self.assertIs(result["worse"], True)
        self.assertEqual(
            [s["signal"] for s in result["signals"]], ["turns_flat_cost_up"]
        )
        self.assertEqual(
            result["signals"][0]["values"], [[6, 3.0], [7, 4.0], [9, 5.0]]
        )


class OneBadReleaseIsNoiseTests(unittest.TestCase):
    """A signal that rises once and then falls is not a trend."""

    def test_rework_up_then_down_does_not_fire(self):
        bounce = series((1, 10, 3, 5.0), (2, 8, 2, 4.0), (1, 6, 1, 3.0))
        result = scorecard.detect_worse(bounce)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])
        self.assertIs(result["insufficient_series"], False)

    def test_escalations_up_then_down_does_not_fire(self):
        bounce = series((3, 10, 1, 5.0), (2, 8, 2, 4.0), (1, 6, 1, 3.0))
        result = scorecard.detect_worse(bounce)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])

    def test_turns_flat_cost_up_once_then_turns_drop_does_not_fire(self):
        # First transition: turns flat at 6, cost 3 -> 4, so that transition is
        # bad. Second: turns drop to 4, so the signal breaks and there is no
        # pair of consecutive bad transitions.
        bounce = series((3, 6, 3, 3.0), (2, 6, 2, 4.0), (1, 4, 1, 5.0))
        result = scorecard.detect_worse(bounce)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])


class EqualityTests(unittest.TestCase):
    """Equality means opposite things for the count signals and the flat one.

    An implementation that uses a single comparison operator everywhere gets
    exactly one of these two tests wrong, which is why they are stated together.
    """

    def test_equal_rework_across_both_transitions_does_not_fire(self):
        flat_rework = series((2, 10, 3, 5.0), (2, 8, 2, 4.0), (2, 6, 1, 3.0))
        result = scorecard.detect_worse(flat_rework)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])

    def test_equal_escalations_across_both_transitions_does_not_fire(self):
        flat_escalations = series((3, 10, 2, 5.0), (2, 8, 2, 4.0), (1, 6, 2, 3.0))
        result = scorecard.detect_worse(flat_escalations)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])

    def test_equal_turns_with_rising_cost_does_fire(self):
        # The mirror of the case above: here equality IS the finding, because
        # "flat" is literally what the signal is named for.
        flat_turns = series((3, 5, 3, 1.0), (2, 5, 2, 2.0), (1, 5, 1, 3.0))
        result = scorecard.detect_worse(flat_turns)
        self.assertIs(result["worse"], True)
        self.assertEqual(
            [s["signal"] for s in result["signals"]], ["turns_flat_cost_up"]
        )

    def test_equal_cost_with_flat_turns_does_not_fire(self):
        # Cost must strictly RISE. Flat turns at flat cost is standing still,
        # not paying more for the same attention.
        flat_both = series((3, 5, 3, 2.0), (2, 5, 2, 2.0), (1, 5, 1, 2.0))
        result = scorecard.detect_worse(flat_both)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])


class TurnsDroppingTests(unittest.TestCase):
    """Turns dropping is the programme's goal and never a finding."""

    def test_turns_dropping_while_cost_rises_does_not_fire(self):
        # Cost climbs 1 -> 2 -> 3 the whole way, but turns fall 9 -> 7 -> 5.
        # The signal is about turns FAILING to drop, so this must stay quiet
        # even though the cost line alone looks bad.
        dropping = series((3, 9, 3, 1.0), (2, 7, 2, 2.0), (1, 5, 1, 3.0))
        result = scorecard.detect_worse(dropping)
        self.assertIs(result["worse"], False)
        self.assertEqual(result["signals"], [])


class MultipleSignalTests(unittest.TestCase):
    def test_two_signals_firing_are_both_present_in_the_fixed_order(self):
        # rework 1 -> 2 -> 3 AND escalations 1 -> 2 -> 3 together, with turns
        # falling and cost falling so the third signal stays quiet. The output
        # order must be the declared order, not the order a scan discovers them
        # in -- so ``escalations`` may not sort ahead of ``rework``.
        both = series((1, 10, 1, 5.0), (2, 8, 2, 4.0), (3, 6, 3, 3.0))
        result = scorecard.detect_worse(both)
        self.assertIs(result["worse"], True)
        self.assertEqual(
            [s["signal"] for s in result["signals"]], ["rework", "escalations"]
        )
        self.assertEqual(result["signals"][0]["values"], [1, 2, 3])
        self.assertEqual(result["signals"][1]["values"], [1, 2, 3])

    def test_all_three_signals_fire_together_in_the_fixed_order(self):
        # rework up, escalations up, turns flat at 6 with cost climbing.
        everything = series((1, 6, 1, 3.0), (2, 6, 2, 4.0), (3, 6, 3, 5.0))
        result = scorecard.detect_worse(everything)
        self.assertIs(result["worse"], True)
        self.assertEqual([s["signal"] for s in result["signals"]], list(SIGNAL_ORDER))

    def test_signal_names_are_drawn_only_from_the_declared_set(self):
        everything = series((1, 6, 1, 3.0), (2, 6, 2, 4.0), (3, 6, 3, 5.0))
        result = scorecard.detect_worse(everything)
        for entry in result["signals"]:
            self.assertIn(entry["signal"], SIGNAL_ORDER)
            self.assertEqual(set(entry), {"signal", "releases", "values"})


class OverlappingWindowTests(unittest.TestCase):
    """One entry per window, so a longer bad run is not collapsed to one."""

    def test_four_release_rework_climb_yields_two_windows(self):
        # rework 1 -> 2 -> 3 -> 4 gives three consecutive bad transitions, and
        # therefore two overlapping three-release windows: r1..r3 and r2..r4.
        climb = series(
            (1, 12, 4, 6.0), (2, 10, 3, 5.0), (3, 8, 2, 4.0), (4, 6, 1, 3.0)
        )
        result = scorecard.detect_worse(climb)
        self.assertIs(result["worse"], True)
        self.assertEqual([s["signal"] for s in result["signals"]], ["rework", "rework"])
        self.assertEqual(
            [s["releases"] for s in result["signals"]],
            [["r1", "r2", "r3"], ["r2", "r3", "r4"]],
        )
        self.assertEqual([s["values"] for s in result["signals"]], [[1, 2, 3], [2, 3, 4]])

    def test_four_release_series_with_only_the_later_window_bad(self):
        # rework 3 -> 1 -> 2 -> 3: the first transition improves, so only the
        # r2..r4 window has two consecutive bad transitions.
        late = series(
            (3, 12, 4, 6.0), (1, 10, 3, 5.0), (2, 8, 2, 4.0), (3, 6, 1, 3.0)
        )
        result = scorecard.detect_worse(late)
        self.assertIs(result["worse"], True)
        self.assertEqual([s["signal"] for s in result["signals"]], ["rework"])
        self.assertEqual(result["signals"][0]["releases"], ["r2", "r3", "r4"])
        self.assertEqual(result["signals"][0]["values"], [1, 2, 3])


class ReleasesAndValuesTests(unittest.TestCase):
    """``releases`` and ``values`` carry the right three entries, oldest first."""

    def test_release_ids_are_taken_from_the_scorecards_not_synthesised(self):
        named = [
            card("2026.08.1", 1, 10, 3, 5.0),
            card("2026.08.2", 2, 8, 2, 4.0),
            card("2026.08.3", 3, 6, 1, 3.0),
        ]
        result = scorecard.detect_worse(named)
        self.assertEqual(
            result["signals"][0]["releases"], ["2026.08.1", "2026.08.2", "2026.08.3"]
        )

    def test_values_are_three_long_and_ordered_oldest_first(self):
        named = [
            card("2026.08.1", 1, 10, 3, 5.0),
            card("2026.08.2", 2, 8, 2, 4.0),
            card("2026.08.3", 3, 6, 1, 3.0),
        ]
        result = scorecard.detect_worse(named)
        entry = result["signals"][0]
        self.assertEqual(len(entry["releases"]), 3)
        self.assertEqual(len(entry["values"]), 3)
        self.assertEqual(entry["values"], [1, 2, 3])

    def test_flat_signal_values_are_turn_cost_pairs_at_each_release(self):
        flat = [
            card("2026.08.1", 3, 6, 3, 3.0),
            card("2026.08.2", 2, 6, 2, 4.5),
            card("2026.08.3", 1, 6, 1, 5.25),
        ]
        result = scorecard.detect_worse(flat)
        entry = result["signals"][0]
        self.assertEqual(entry["signal"], "turns_flat_cost_up")
        self.assertEqual(entry["values"], [[6, 3.0], [6, 4.5], [6, 5.25]])


class WorkerHalfIsNotTheSignalTests(unittest.TestCase):
    """``turns_flat_cost_up`` is about the FRONTIER half, not billed money.

    The two figures are not the same kind of number: the frontier one is an
    imputed list price that tracks coordinator behaviour, the worker one is
    real metered spend on a delegated task. A release that delegated more work
    to a cheap worker is not the "paying more for the same attention" failure
    this signal names, so it must stay quiet.
    """

    def test_worker_cost_climbing_with_flat_frontier_does_not_fire(self):
        # turns held flat at 6 -- the other half of the condition is satisfied
        # -- while worker_billed_usd climbs 0.01 -> 1.0 -> 90.0 and the
        # frontier usage-equivalent stays put at 3.0. A detector reading the
        # billed figure, or a resurrected frontier+worker total, fires here.
        flat_frontier = [
            card("r1", 3, 6, 3, 3.0, worker=0.01),
            card("r2", 2, 6, 2, 3.0, worker=1.0),
            card("r3", 1, 6, 1, 3.0, worker=90.0),
        ]
        result = scorecard.detect_worse(flat_frontier)
        self.assertIs(
            result["worse"], False,
            "a worker whose billed spend climbed fired turns_flat_cost_up; "
            "the signal reads the frontier usage-equivalent, not money",
        )
        self.assertEqual(result["signals"], [])
        self.assertIs(result["insufficient_series"], False)

    def test_the_frontier_half_still_fires_while_worker_spend_falls(self):
        # The mirror: billed money drops the whole way, but the frontier
        # usage-equivalent climbs with flat turns. That IS the alarm.
        rising_frontier = [
            card("r1", 3, 6, 3, 3.0, worker=90.0),
            card("r2", 2, 6, 2, 4.0, worker=1.0),
            card("r3", 1, 6, 1, 5.0, worker=0.01),
        ]
        result = scorecard.detect_worse(rising_frontier)
        self.assertIs(result["worse"], True)
        self.assertEqual(
            [s["signal"] for s in result["signals"]], ["turns_flat_cost_up"]
        )
        self.assertEqual(
            result["signals"][0]["values"], [[6, 3.0], [6, 4.0], [6, 5.0]],
            "values must carry [turns, frontier_usage_equivalent_usd]",
        )


class PurityTests(unittest.TestCase):
    """The detector reads its input and leaves it exactly as it found it."""

    def test_input_list_and_scorecards_are_not_mutated(self):
        given = series((1, 6, 1, 3.0), (2, 6, 2, 4.0), (3, 6, 3, 5.0))
        before = copy.deepcopy(given)
        scorecard.detect_worse(given)
        self.assertEqual(given, before)
        self.assertEqual(len(given), 3)

    def test_repeated_calls_return_equal_results(self):
        given = series((1, 6, 1, 3.0), (2, 6, 2, 4.0), (3, 6, 3, 5.0))
        self.assertEqual(scorecard.detect_worse(given), scorecard.detect_worse(given))


if __name__ == "__main__":
    unittest.main()
