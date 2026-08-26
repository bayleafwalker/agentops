"""Coordinator-authored oracle for ``frontier_reliability.frontier_reliability``
(agentops#2254, debt entry 10: "the frontier side has no way to say 'not
measured', and this one is in the measuring instrument").

``worker_totals`` carries ``cost_reported`` and ``cost_unreported_tasks`` so a
reader can tell a worker half that measured zero from one that measured nothing.
``frontier_totals`` carries no such thing. The Stop hook appends one cumulative
snapshot per assistant turn, so a scorecard generated *during* the session it
measures has no row to read yet and reports ``sessions: 0``, ``turns: 0``,
``usage_equivalent_usd: 0.0``. That is arithmetically correct and reads to any
human as *the coordinator cost nothing*. This row adds the verdict and nothing
else -- no wiring into ``build_scorecard``, no CLI, no file I/O.

What this file pins:

* **The reduction rule is ``frontier_totals``' reduction rule.** Whether a
  session survives, and which of its snapshots is the survivor, is decided by
  ``reduce_sessions`` -- imported from ``release_scorecard``, never restated.
  Two functions answering the same question differently is a defect this repo
  has already had to undo once (``_path_allowed`` versus ``_matches_any``), and
  ``churn_metrics`` was made to import ``MUTATION_TOOLS`` for the same reason.
  ``AgreesWithFrontierTotalsTests`` pins it as an equality over every fixture in
  this file, not as a spot check.

* **An empty sink is NOT reported.** This is the defect itself, and it is the
  single most likely wrong implementation: ``all(...)`` over no survivors is
  vacuously ``True``, so the natural one-liner certifies exactly the case the
  row exists to catch. ``VacuousTruthTests`` exists solely for that stub, which
  passes every other test in this file.

* **Measured zero is not unmeasured.** A surviving row carrying
  ``cost_usd: 0`` is *measured*, and a session that ran up no cost must report
  ``True`` with a total of ``0.0``. The inverse stub -- treating a zero cost as
  a missing one -- is the second-most-likely error and gets its own class,
  because it would make every genuinely free session unreported and hide the
  real defect behind noise.

* **Unreported sessions are named, in sorted order.** ``worker_totals`` names
  its silent tasks in ``cost_unreported_tasks`` rather than only counting them,
  because a total you cannot attribute is a total you cannot chase. The
  frontier half is held to the same standard.

* **Any iterable, consumed once.** ``rows`` is whatever ``frontier_totals``
  would take. This codebase has fixed the same "asks its argument for a length,
  or loops it twice" defect three times already -- ``worker_totals``,
  ``build_scorecard`` and ``churn_metrics``. A fourth is not allowed in.

Choices made where the spec left room, all of them asserted below so a reader
can find the decision rather than infer it:

* **"Carried a cost figure" means the key is present and numeric.** A survivor
  whose ``cost_usd`` is absent, ``None``, or a non-number is unreported. A
  bool is not a number here: ``True`` is not a cost, and Python would otherwise
  admit it as ``1``.
* **Rows the reduction drops cannot affect the verdict.** A row with no
  ``session`` is dropped by ``reduce_sessions``, so a sink consisting only of
  such rows is empty, which is unreported for the empty-sink reason and not for
  a missing-cost one. Pinned rather than left to follow.
* **The verdict is about cost only.** ``turns`` and the other counters are not
  consulted. A session that reported a cost and nothing else is reported: the
  question this answers is whether the money figure was measured.
* ``sessions`` is carried on the result so the verdict can be read without also
  calling ``frontier_totals``, and it is pinned equal to it.

Rule 11: this file imports ``release_scorecard`` and ``frontier_reliability``
and nothing else of the repo's own; it runs no git and no subprocess.

The fixture shape was checked against the live sink rows the Stop hook writes:
``{"session": ..., "ts": ..., "cost_usd": ..., "turns": ..., "out": ...}``, and
against ``reduce_sessions``' survivor key ``(ts, cost_usd, out)``.
"""
from __future__ import annotations

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
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ``release_scorecard.py`` is the source of both ``reduce_sessions`` and
# ``frontier_totals``; it is loaded once here and shared.
scorecard = _load_module("frontier_reliability_reference", SCRIPTS / "release_scorecard.py")


def _verdict(rows):
    """Load the subject lazily, so its absence fails tests rather than import."""
    module = _load_module("frontier_reliability_subject", SCRIPTS / "frontier_reliability.py")
    return module.frontier_reliability(rows)


def _row(session, ts="2026-08-26T00:00:00Z", **fields):
    """A Stop-hook snapshot. ``cost_usd`` is set unless explicitly removed."""
    row = {"session": session, "ts": ts, "turns": 1, "out": 0, "cost_usd": 0.25}
    row.update(fields)
    return row


def _no_cost(session, **fields):
    row = _row(session, **fields)
    del row["cost_usd"]
    return row


class OneShotIterable:
    """Yields once and records how many times iteration was attempted."""

    def __init__(self, items):
        self._items = list(items)
        self.passes = 0

    def __iter__(self):
        self.passes += 1
        yield from self._items


class ShapeTests(unittest.TestCase):

    def test_returns_the_three_documented_keys(self):
        result = _verdict([_row("s1")])
        self.assertEqual(set(result), {"reported", "unreported_sessions", "sessions"})

    def test_reported_is_a_bool_and_sessions_an_int(self):
        result = _verdict([_row("s1")])
        self.assertIsInstance(result["reported"], bool)
        self.assertIsInstance(result["sessions"], int)
        self.assertIsInstance(result["unreported_sessions"], list)


class VacuousTruthTests(unittest.TestCase):
    """The defect itself. ``all(...)`` over no survivors is True, and that stub
    passes every other test in this file."""

    def test_an_empty_sink_is_not_reported(self):
        result = _verdict([])
        self.assertFalse(result["reported"])
        self.assertEqual(result["sessions"], 0)

    def test_a_sink_of_only_sessionless_rows_is_not_reported(self):
        rows = [{"ts": "2026-08-26T00:00:00Z", "cost_usd": 5.0},
                {"session": "", "cost_usd": 5.0}]
        result = _verdict(rows)
        self.assertFalse(result["reported"])
        self.assertEqual(result["sessions"], 0)

    def test_an_empty_sink_names_no_unreported_session(self):
        # It is unreported because there is nothing there, not because some
        # named session went silent. Reporting a phantom id would send a reader
        # chasing a session that does not exist.
        self.assertEqual(_verdict([])["unreported_sessions"], [])


class MeasuredZeroIsNotUnmeasuredTests(unittest.TestCase):
    """The inverse stub: treating a zero cost as a missing one."""

    def test_a_session_costing_zero_is_reported(self):
        result = _verdict([_row("s1", cost_usd=0)])
        self.assertTrue(result["reported"])
        self.assertEqual(result["unreported_sessions"], [])

    def test_a_float_zero_is_reported(self):
        self.assertTrue(_verdict([_row("s1", cost_usd=0.0)])["reported"])

    def test_a_zero_turn_session_that_reported_cost_is_reported(self):
        # The verdict is about the money figure, not about activity.
        self.assertTrue(_verdict([_row("s1", turns=0, cost_usd=0.0)])["reported"])


class MissingCostTests(unittest.TestCase):

    def test_a_survivor_with_no_cost_key_is_unreported(self):
        result = _verdict([_no_cost("s1")])
        self.assertFalse(result["reported"])
        self.assertEqual(result["unreported_sessions"], ["s1"])

    def test_a_none_cost_is_unreported(self):
        result = _verdict([_row("s1", cost_usd=None)])
        self.assertFalse(result["reported"])
        self.assertEqual(result["unreported_sessions"], ["s1"])

    def test_a_non_numeric_cost_is_unreported(self):
        result = _verdict([_row("s1", cost_usd="0.25")])
        self.assertFalse(result["reported"])
        self.assertEqual(result["unreported_sessions"], ["s1"])

    def test_a_bool_cost_is_unreported(self):
        # ``True`` is not a cost. Python would otherwise admit it as 1.
        result = _verdict([_row("s1", cost_usd=True)])
        self.assertFalse(result["reported"])
        self.assertEqual(result["unreported_sessions"], ["s1"])

    def test_one_silent_session_among_many_makes_the_whole_half_unreported(self):
        rows = [_row("s1"), _row("s2"), _no_cost("s3")]
        result = _verdict(rows)
        self.assertFalse(result["reported"])
        self.assertEqual(result["unreported_sessions"], ["s3"])
        self.assertEqual(result["sessions"], 3)

    def test_unreported_sessions_are_sorted(self):
        rows = [_no_cost("zebra"), _no_cost("alpha"), _no_cost("m"), _row("ok")]
        self.assertEqual(_verdict(rows)["unreported_sessions"],
                         ["alpha", "m", "zebra"])

    def test_all_reporting_sessions_yield_an_empty_name_list(self):
        result = _verdict([_row("s1"), _row("s2")])
        self.assertTrue(result["reported"])
        self.assertEqual(result["unreported_sessions"], [])


class ReductionRuleTests(unittest.TestCase):
    """The survivor is the newest snapshot, and only the survivor is judged."""

    def test_a_later_snapshot_supersedes_an_earlier_silent_one(self):
        rows = [_no_cost("s1", ts="2026-08-26T00:00:00Z"),
                _row("s1", ts="2026-08-26T01:00:00Z", cost_usd=1.5)]
        result = _verdict(rows)
        self.assertTrue(result["reported"])
        self.assertEqual(result["sessions"], 1)

    def test_a_later_silent_snapshot_supersedes_an_earlier_reporting_one(self):
        rows = [_row("s1", ts="2026-08-26T00:00:00Z", cost_usd=1.5),
                _no_cost("s1", ts="2026-08-26T01:00:00Z")]
        result = _verdict(rows)
        self.assertFalse(result["reported"])
        self.assertEqual(result["unreported_sessions"], ["s1"])

    def test_a_session_is_counted_once_however_many_snapshots(self):
        rows = [_row("s1", ts=f"2026-08-26T0{i}:00:00Z") for i in range(1, 5)]
        self.assertEqual(_verdict(rows)["sessions"], 1)


class AgreesWithFrontierTotalsTests(unittest.TestCase):
    """``sessions`` is the same number ``frontier_totals`` reports, on every
    fixture in this file -- the reduction is imported, not restated."""

    FIXTURES = (
        [],
        [_row("s1")],
        [_row("s1"), _row("s2"), _no_cost("s3")],
        [_no_cost("s1", ts="2026-08-26T00:00:00Z"),
         _row("s1", ts="2026-08-26T01:00:00Z")],
        [{"ts": "2026-08-26T00:00:00Z", "cost_usd": 5.0}],
        [_row("s1", cost_usd=0), _no_cost("s2")],
    )
    # NOTE: a ``cost_usd: None`` row is deliberately absent from these
    # fixtures. ``frontier_totals`` raises TypeError on one -- ``row.get(
    # "cost_usd", 0)`` defaults only a *missing* key, never a null -- which is
    # a real defect found by this oracle and recorded as its own debt entry.
    # It is out of scope here: this row adds a verdict and changes no summing.
    # ``MissingCostTests.test_a_none_cost_is_unreported`` still pins that the
    # verdict handles the null, which is what this module owns.

    def test_sessions_matches_frontier_totals_on_every_fixture(self):
        for rows in self.FIXTURES:
            with self.subTest(rows=rows):
                self.assertEqual(_verdict(list(rows))["sessions"],
                                 scorecard.frontier_totals(list(rows))["sessions"])

    def test_a_reported_half_can_still_total_zero(self):
        # The whole point: 0.0 with reported True is a measured zero, and it is
        # a different object from 0.0 with reported False.
        rows = [_row("s1", cost_usd=0.0)]
        self.assertEqual(scorecard.frontier_totals(list(rows))["usage_equivalent_usd"], 0.0)
        self.assertTrue(_verdict(list(rows))["reported"])
        self.assertFalse(_verdict([])["reported"])
        self.assertEqual(scorecard.frontier_totals([])["usage_equivalent_usd"], 0.0)


class OneShotIterableTests(unittest.TestCase):

    def test_a_generator_is_accepted_and_consumed_exactly_once(self):
        source = OneShotIterable([_row("s1"), _no_cost("s2")])
        result = _verdict(iter(source))
        self.assertEqual(result["sessions"], 2)
        self.assertEqual(result["unreported_sessions"], ["s2"])

    def test_the_argument_is_iterated_at_most_once(self):
        source = OneShotIterable([_row("s1"), _row("s2")])
        _verdict(source)
        self.assertLessEqual(source.passes, 1)

    def test_a_generator_expression_gives_the_same_answer_as_a_list(self):
        rows = [_row("s1"), _no_cost("s2"), _row("s3", cost_usd=0)]
        self.assertEqual(_verdict(row for row in rows), _verdict(list(rows)))


class DoesNotMutateItsInputTests(unittest.TestCase):

    def test_rows_are_unchanged(self):
        rows = [_row("s1"), _no_cost("s2")]
        before = [dict(row) for row in rows]
        _verdict(rows)
        self.assertEqual(rows, before)


if __name__ == "__main__":
    unittest.main()
