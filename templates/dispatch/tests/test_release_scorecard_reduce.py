"""Coordinator-authored oracle for ``release_scorecard.py`` -- reduce before you sum.

The Claude Code Stop hook appends one row per assistant turn to the session-cost
sink, and every row is a *cumulative snapshot of the session so far*. Rows for
one session therefore supersede each other rather than adding to each other. A
consumer that sums the raw sink over-counts roughly quadratically in the number
of stops per session: measured 2026-08-23, the naive sum reported $56,485
against $3,825 actually spent across 97 sessions.

This file pins the two functions that stand between the sink and any scorecard:

``reduce_sessions(rows)``   -> {session id: the one surviving row}
``frontier_totals(rows)``   -> the seven aggregate fields, over survivors only

The money-shaped total ``frontier_totals`` reports is named ``usage_equivalent_usd``
(see ``test_release_scorecard_naming.py``); the sink rows it reads still carry
``cost_usd``, which is why the fixtures below spell both.

Written against the packet spec only. ``templates/dispatch/scripts/release_scorecard.py``
does not exist yet, so this oracle fails at import -- that is the declared red.
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


#: Five cumulative snapshots of ONE session, in sink order. This is the fixture
#: the whole packet exists for: the right answer is the LAST snapshot, and the
#: sum of all five is the quadratic bug. Every field grows monotonically, the
#: way a cumulative snapshot does.
FIVE_SNAPSHOTS: tuple[dict, ...] = (
    {"ts": "2026-08-24T14:00:01Z", "session": "quad", "model": "claude-opus-5",
     "out": 100, "cost_usd": 0.5, "turns": 1, "assistant_msgs": 2,
     "tool_calls": 0, "duration_s": 10, "rework_rounds": 0},
    {"ts": "2026-08-24T14:02:11Z", "session": "quad", "model": "claude-opus-5",
     "out": 200, "cost_usd": 1.5, "turns": 2, "assistant_msgs": 4,
     "tool_calls": 1, "duration_s": 40, "rework_rounds": 0},
    {"ts": "2026-08-24T14:05:30Z", "session": "quad", "model": "claude-opus-5",
     "out": 300, "cost_usd": 3.0, "turns": 3, "assistant_msgs": 6,
     "tool_calls": 4, "duration_s": 90, "rework_rounds": 1},
    {"ts": "2026-08-24T14:11:09Z", "session": "quad", "model": "claude-opus-5",
     "out": 400, "cost_usd": 6.25, "turns": 5, "assistant_msgs": 10,
     "tool_calls": 9, "duration_s": 200, "rework_rounds": 1},
    {"ts": "2026-08-24T14:19:48Z", "session": "quad", "model": "claude-opus-5",
     "out": 500, "cost_usd": 10.0, "turns": 8, "assistant_msgs": 16,
     "tool_calls": 13, "duration_s": 410, "rework_rounds": 2},
)

#: What an implementation that sums every row would report for FIVE_SNAPSHOTS.
#: Written out by hand so the test can assert the correct answer is NOT this.
NAIVE_SUM_OF_FIVE_SNAPSHOTS: dict = {
    "turns": 19, "assistant_msgs": 38, "tool_calls": 27,
    "duration_s": 750, "usage_equivalent_usd": 21.25, "rework_rounds": 4,
}

#: Two stops inside the same wall-clock second. ``ts`` has one-second
#: resolution, so the timestamps are indistinguishable; the snapshots are
#: monotonic, so the larger one is the later one. The larger is placed FIRST in
#: input order, which kills "keep whatever came last" and any stable sort that
#: only looks at ``ts``.
TIED_TS_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T09:00:00Z", "session": "tie-ts", "out": 900,
     "cost_usd": 9.0, "turns": 9, "assistant_msgs": 18, "tool_calls": 7,
     "duration_s": 300, "rework_rounds": 3},
    {"ts": "2026-08-24T09:00:00Z", "session": "tie-ts", "out": 200,
     "cost_usd": 2.0, "turns": 2, "assistant_msgs": 4, "tool_calls": 1,
     "duration_s": 60, "rework_rounds": 0},
)

#: Same second AND same cost -- a cheap turn that spent nothing new. ``out`` is
#: the last member of the ordering tuple and is the only field left to decide.
#: The winner is again not last in input order.
TIED_COST_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T09:30:00Z", "session": "tie-cost", "out": 900,
     "cost_usd": 4.0, "turns": 7, "assistant_msgs": 14, "tool_calls": 5,
     "duration_s": 250, "rework_rounds": 2},
    {"ts": "2026-08-24T09:30:00Z", "session": "tie-cost", "out": 100,
     "cost_usd": 4.0, "turns": 1, "assistant_msgs": 2, "tool_calls": 0,
     "duration_s": 20, "rework_rounds": 0},
)

#: Three sessions whose stops interleave, as they do in a real sink shared by
#: concurrent agents. Each must reduce independently -- a reducer that keeps one
#: global maximum, or that assumes a session's rows are contiguous, fails here.
INTERLEAVED_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T10:00:00Z", "session": "alpha", "out": 10,
     "cost_usd": 1.0, "turns": 1, "assistant_msgs": 1, "tool_calls": 1,
     "duration_s": 10, "rework_rounds": 0},
    {"ts": "2026-08-24T10:00:05Z", "session": "beta", "out": 20,
     "cost_usd": 2.0, "turns": 2, "assistant_msgs": 2, "tool_calls": 2,
     "duration_s": 20, "rework_rounds": 0},
    {"ts": "2026-08-24T10:00:09Z", "session": "alpha", "out": 30,
     "cost_usd": 3.0, "turns": 3, "assistant_msgs": 3, "tool_calls": 3,
     "duration_s": 30, "rework_rounds": 1},
    {"ts": "2026-08-24T10:00:12Z", "session": "gamma", "out": 40,
     "cost_usd": 4.0, "turns": 4, "assistant_msgs": 4, "tool_calls": 4,
     "duration_s": 40, "rework_rounds": 0},
    {"ts": "2026-08-24T10:00:20Z", "session": "beta", "out": 50,
     "cost_usd": 5.0, "turns": 5, "assistant_msgs": 5, "tool_calls": 5,
     "duration_s": 50, "rework_rounds": 2},
    {"ts": "2026-08-24T10:00:33Z", "session": "alpha", "out": 60,
     "cost_usd": 6.0, "turns": 6, "assistant_msgs": 6, "tool_calls": 6,
     "duration_s": 60, "rework_rounds": 3},
)

#: Rows that cannot be attributed to a session: one with no ``session`` key at
#: all, one with an empty string. Both are dropped whole -- they must not create
#: a key (not ``None``, not ``""``) and must not reach any total. Their numbers
#: are deliberately huge so that leaking them anywhere is unmissable.
UNATTRIBUTED_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T11:00:00Z", "out": 999999, "cost_usd": 999.0,
     "turns": 999, "assistant_msgs": 999, "tool_calls": 999,
     "duration_s": 99999, "rework_rounds": 99},
    {"ts": "2026-08-24T11:00:01Z", "session": "", "out": 888888,
     "cost_usd": 888.0, "turns": 888, "assistant_msgs": 888, "tool_calls": 888,
     "duration_s": 88888, "rework_rounds": 88},
)

#: A survivor that the hook wrote before it learned to emit every field. Missing
#: numerics count as 0; nothing here may raise KeyError or TypeError.
SPARSE_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T12:00:00Z", "session": "sparse", "cost_usd": 0.25},
    {"ts": "2026-08-24T12:00:30Z", "session": "sparse", "cost_usd": 1.25,
     "turns": 4},
)

#: One row with no ``ts`` at all against one that has one. A missing ``ts``
#: sorts as the empty string, i.e. earliest, so the timestamped row wins even
#: though its cost is smaller -- ``ts`` is the first member of the tuple.
MISSING_TS_ROWS: tuple[dict, ...] = (
    {"session": "no-ts", "out": 5000, "cost_usd": 50.0, "turns": 50,
     "assistant_msgs": 50, "tool_calls": 50, "duration_s": 500,
     "rework_rounds": 5},
    {"ts": "2026-08-24T13:00:00Z", "session": "no-ts", "out": 10,
     "cost_usd": 0.1, "turns": 1, "assistant_msgs": 1, "tool_calls": 1,
     "duration_s": 5, "rework_rounds": 0},
)

#: Costs chosen so that plain float addition leaves a tail in either order:
#: 0.1 + 0.2 == 0.30000000000000004. The spec rounds to 6 dp, so the answer is
#: exactly 0.3 and an implementation that forgets to round fails. The third
#: session carries a superseded snapshot too, so the rounding case also has to
#: be reduced first.
FLOAT_TAIL_ROWS: tuple[dict, ...] = (
    {"ts": "2026-08-24T15:00:00Z", "session": "f1", "cost_usd": 0.1},
    {"ts": "2026-08-24T15:00:01Z", "session": "f2", "cost_usd": 0.05},
    {"ts": "2026-08-24T15:00:09Z", "session": "f2", "cost_usd": 0.2},
)

#: The seven keys ``frontier_totals`` returns, exactly. The money-shaped one is
#: ``usage_equivalent_usd``, never ``cost_usd``: the figure is tokens priced off
#: a hardcoded list-price table, not spend anyone was billed, and the sink field
#: it is summed from keeps its own name (``cost_usd``) regardless.
TOTALS_KEYS = frozenset(
    {"sessions", "turns", "assistant_msgs", "tool_calls", "duration_s",
     "usage_equivalent_usd", "rework_rounds"}
)


def _rows(*groups) -> list:
    """Flatten fixture tuples into one fresh, mutable sink list."""
    out: list = []
    for group in groups:
        out.extend(copy.deepcopy(row) for row in group)
    return out


class ReduceSessionsTests(unittest.TestCase):
    """``reduce_sessions`` -- one surviving row per session, newest wins."""

    def test_a_multi_stop_session_reduces_to_its_last_snapshot(self):
        reduced = scorecard.reduce_sessions(_rows(FIVE_SNAPSHOTS))
        self.assertEqual(
            set(reduced), {"quad"},
            "five snapshots of one session did not reduce to one session",
        )
        self.assertEqual(
            reduced["quad"]["cost_usd"], 10.0,
            "the survivor is not the newest snapshot",
        )
        self.assertEqual(reduced["quad"]["turns"], 8)
        self.assertEqual(reduced["quad"]["out"], 500)

    def test_an_identical_timestamp_is_broken_by_magnitude(self):
        # The larger row is FIRST in input order, so "keep the last one seen"
        # and a sort on ts alone both pick the smaller and under-report.
        reduced = scorecard.reduce_sessions(_rows(TIED_TS_ROWS))
        self.assertEqual(
            reduced["tie-ts"]["cost_usd"], 9.0,
            "a tied timestamp picked the smaller snapshot",
        )
        self.assertEqual(reduced["tie-ts"]["turns"], 9)

    def test_a_tied_cost_is_broken_by_output_tokens(self):
        reduced = scorecard.reduce_sessions(_rows(TIED_COST_ROWS))
        self.assertEqual(
            reduced["tie-cost"]["out"], 900,
            "a tied ts and cost did not fall through to out",
        )
        self.assertEqual(reduced["tie-cost"]["turns"], 7)

    def test_interleaved_sessions_reduce_independently(self):
        reduced = scorecard.reduce_sessions(_rows(INTERLEAVED_ROWS))
        self.assertEqual(set(reduced), {"alpha", "beta", "gamma"})
        for session, cost in (("alpha", 6.0), ("beta", 5.0), ("gamma", 4.0)):
            with self.subTest(session=session):
                self.assertEqual(
                    reduced[session]["cost_usd"], cost,
                    f"{session} kept the wrong snapshot",
                )

    def test_a_row_without_a_session_is_dropped_whole(self):
        reduced = scorecard.reduce_sessions(_rows(UNATTRIBUTED_ROWS))
        self.assertEqual(
            reduced, {},
            "an unattributable row was given a key",
        )

    def test_unattributable_rows_do_not_disturb_real_ones(self):
        reduced = scorecard.reduce_sessions(
            _rows(INTERLEAVED_ROWS, UNATTRIBUTED_ROWS)
        )
        self.assertEqual(set(reduced), {"alpha", "beta", "gamma"})

    def test_a_missing_timestamp_sorts_earliest(self):
        reduced = scorecard.reduce_sessions(_rows(MISSING_TS_ROWS))
        self.assertEqual(
            reduced["no-ts"]["cost_usd"], 0.1,
            "a row with no ts beat a timestamped row",
        )

    def test_missing_numeric_fields_do_not_raise(self):
        reduced = scorecard.reduce_sessions(_rows(SPARSE_ROWS))
        self.assertEqual(set(reduced), {"sparse"})
        self.assertEqual(reduced["sparse"]["cost_usd"], 1.25)

    def test_an_empty_sink_reduces_to_an_empty_mapping(self):
        self.assertEqual(scorecard.reduce_sessions([]), {})

    def test_the_input_is_left_untouched(self):
        rows = _rows(FIVE_SNAPSHOTS, INTERLEAVED_ROWS, UNATTRIBUTED_ROWS)
        before = copy.deepcopy(rows)
        scorecard.reduce_sessions(rows)
        self.assertEqual(
            rows, before,
            "reduce_sessions mutated the sink it was handed",
        )
        self.assertEqual(
            len(rows), len(before),
            "reduce_sessions changed the length of the input list",
        )


class FrontierTotalsTests(unittest.TestCase):
    """``frontier_totals`` -- aggregates over survivors, never over the sink."""

    def test_it_reports_exactly_the_seven_keys(self):
        totals = scorecard.frontier_totals(_rows(FIVE_SNAPSHOTS))
        self.assertEqual(set(totals), set(TOTALS_KEYS))

    def test_five_snapshots_total_to_one_session(self):
        totals = scorecard.frontier_totals(_rows(FIVE_SNAPSHOTS))
        self.assertEqual(totals["sessions"], 1)
        self.assertEqual(totals["usage_equivalent_usd"], 10.0)
        self.assertEqual(totals["turns"], 8)
        self.assertEqual(totals["assistant_msgs"], 16)
        self.assertEqual(totals["tool_calls"], 13)
        self.assertEqual(totals["duration_s"], 410)
        self.assertEqual(totals["rework_rounds"], 2)

    def test_the_answer_is_not_the_sum_of_every_row(self):
        # The quadratic bug, stated as an inequality: an implementation that
        # sums the raw sink cannot also satisfy the equalities above.
        totals = scorecard.frontier_totals(_rows(FIVE_SNAPSHOTS))
        for field, naive in NAIVE_SUM_OF_FIVE_SNAPSHOTS.items():
            with self.subTest(field=field):
                self.assertNotEqual(
                    totals[field], naive,
                    f"{field} equals the naive sum-of-all-rows figure "
                    f"({naive}) -- the sink was summed, not reduced",
                )

    def test_totals_span_every_session_once(self):
        totals = scorecard.frontier_totals(_rows(INTERLEAVED_ROWS))
        self.assertEqual(totals["sessions"], 3)
        # survivors: alpha 6.0/6, beta 5.0/5, gamma 4.0/4
        self.assertEqual(totals["usage_equivalent_usd"], 15.0)
        self.assertEqual(totals["turns"], 15)
        self.assertEqual(totals["assistant_msgs"], 15)
        self.assertEqual(totals["tool_calls"], 15)
        self.assertEqual(totals["duration_s"], 150)
        # alpha 3 + beta 2 + gamma 0 -- the earlier alpha/beta rows carried
        # smaller counts and must not be added on top.
        self.assertEqual(totals["rework_rounds"], 5)

    def test_unattributable_rows_contribute_nothing(self):
        clean = scorecard.frontier_totals(_rows(INTERLEAVED_ROWS))
        dirty = scorecard.frontier_totals(
            _rows(INTERLEAVED_ROWS, UNATTRIBUTED_ROWS)
        )
        self.assertEqual(
            dirty, clean,
            "a row with no session id reached the totals",
        )

    def test_missing_numeric_fields_count_as_zero(self):
        totals = scorecard.frontier_totals(_rows(SPARSE_ROWS))
        self.assertEqual(totals["sessions"], 1)
        self.assertEqual(totals["usage_equivalent_usd"], 1.25)
        self.assertEqual(totals["turns"], 4)
        self.assertEqual(totals["assistant_msgs"], 0)
        self.assertEqual(totals["tool_calls"], 0)
        self.assertEqual(totals["duration_s"], 0)
        self.assertEqual(totals["rework_rounds"], 0)

    def test_an_empty_sink_totals_to_zero(self):
        totals = scorecard.frontier_totals([])
        self.assertEqual(set(totals), set(TOTALS_KEYS))
        for key in TOTALS_KEYS:
            with self.subTest(key=key):
                self.assertEqual(totals[key], 0, f"{key} is not zero")

    def test_cost_is_rounded_to_six_decimal_places(self):
        totals = scorecard.frontier_totals(_rows(FLOAT_TAIL_ROWS))
        self.assertEqual(totals["sessions"], 2)
        self.assertEqual(
            totals["usage_equivalent_usd"], 0.3,
            "0.1 + 0.2 was not rounded to 6 dp",
        )

    def test_it_takes_the_raw_sink_not_the_reduced_mapping(self):
        # frontier_totals reduces internally; handing it the same list twice
        # must give the same answer, and that answer must match a hand
        # reduction of the same rows.
        rows = _rows(FIVE_SNAPSHOTS, INTERLEAVED_ROWS, TIED_TS_ROWS)
        totals = scorecard.frontier_totals(rows)
        self.assertEqual(totals["sessions"], len(scorecard.reduce_sessions(rows)))
        self.assertEqual(totals["sessions"], 5)
        self.assertEqual(totals, scorecard.frontier_totals(rows))

    def test_the_input_is_left_untouched(self):
        rows = _rows(FIVE_SNAPSHOTS, UNATTRIBUTED_ROWS)
        before = copy.deepcopy(rows)
        scorecard.frontier_totals(rows)
        self.assertEqual(
            rows, before,
            "frontier_totals mutated the sink it was handed",
        )


if __name__ == "__main__":
    unittest.main()
