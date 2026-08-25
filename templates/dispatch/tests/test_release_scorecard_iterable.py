"""Coordinator-authored oracle for ``release_scorecard.worker_totals`` -- shape
of the argument, not of the answer.

Every other reducer in ``release_scorecard.py`` accepts whatever iterable it is
handed: ``reduce_sessions``, ``frontier_totals``, ``filter_by_window`` and
``filter_by_project`` all only ever loop. ``worker_totals`` is the exception --
it asks ``len(receipts)`` twice (for ``attempts`` and for the ``cost_reported``
non-empty guard) without ever materialising its argument, so a generator, an
``iter(...)``, or any other non-sequence iterable raises ``TypeError: object of
type 'generator' has no len()`` before a single receipt is read.

This row widens the argument to *any iterable of receipts*, and nothing else.
The answer for a list must not move by one key or one digit: the list cases
below are the frozen baseline and they are GREEN against the current code on
purpose. What must go from red to green is only "the same receipts, arriving as
something other than a sequence, total identically".

Two failure modes are pinned beyond "does not raise":

* **The empty generator.** Row #95 established that ``worker_totals([])``
  reports ``cost_reported: False`` -- with nothing measured, "nothing failed to
  report" is not a measured zero. A careless widening (``receipts =
  receipts or []``, or a ``len()`` taken after a partial drain) is most likely
  to reintroduce the wrong answer exactly here, so the empty generator is
  asserted key-for-key against the empty list.
* **Double consumption.** A one-shot iterable looped over twice yields nothing
  the second time. If the second loop is the one that counts attempts, the
  result is silently zero rather than an exception -- the worse bug. The
  fixtures below therefore both count how many times the iterable is started
  and assert the totals are the real ones, so a re-iteration is caught whether
  it raises, returns zeros, or double-counts.

Nothing here asserts *how* the widening is done. ``list(receipts)`` is the
obvious implementation; a running counter, a tuple, or a two-pass over a
materialised copy would all satisfy this file.
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
    if not path.exists():
        raise ModuleNotFoundError(f"no module to grade: {path} does not exist")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


scorecard = _load_module("release_scorecard_subject",
                         SCRIPTS / "release_scorecard.py")


#: The eight keys ``worker_totals`` reports, exactly as the sibling oracles
#: spell them. Used only to prove the comparisons below are whole-dict ones and
#: that no key quietly appears or vanishes when the argument changes shape.
TOTALS_KEYS = frozenset({
    "attempts", "tasks", "billed_usd", "tokens", "cost_reported",
    "cost_unreported_tasks", "first_pass_tasks", "first_pass_rate",
})


def _receipt(task_id, attempt, cost, tokens, reported, passed):
    """Build one minimal receipt of the real shape.

    Same construction the worker oracle uses: the spend lives four levels down,
    driver_steps -> the "run" entry -> receipt -> spend, and the first-pass
    signal lives at gate.evidence.passed. ``passed=None`` omits the gate chain.
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


#: Six receipts over five tasks, deliberately heterogeneous so that a wrong
#: answer is distinguishable from a right one on every single reported key:
#:
#: * distinct, non-round spends and token counts, so a dropped or duplicated
#:   receipt moves ``billed_usd`` and ``tokens``;
#: * ``retried`` appears twice (attempts 6 != tasks 5), so attempt-counting and
#:   task-counting cannot be confused;
#: * ``retried``'s attempt 1 FAILED its gate and its attempt 2 passed, so it is
#:   not a first pass -- only three of five tasks are, giving a first_pass_rate
#:   of 0.6 that no off-by-one produces;
#: * ``silent`` reported no cost, so ``cost_reported`` is False and
#:   ``cost_unreported_tasks`` is a non-empty sorted list -- a corpus where the
#:   reliability flag is True would hide a widening that lost receipts.
CORPUS = [
    _receipt("alpha", 1, 0.020864, 292309, True, True),
    _receipt("bravo", 1, 0.1375, 41022, True, True),
    _receipt("charlie", 1, 0.004, 9001, True, False),
    _receipt("retried", 1, 0.25, 40000, True, False),
    _receipt("retried", 2, 0.5, 80000, True, True),
    _receipt("silent", 1, 0.0, 12345, False, True),
]


class _CountingIterable:
    """An iterable that yields its receipts once and records every start.

    ``starts`` counts how many times ``__iter__`` was entered and ``exhausted``
    counts how many times a pass ran to completion. A second pass yields
    nothing at all -- exactly like a spent generator -- so an implementation
    that loops twice sees an empty second pass rather than an error, which is
    the silent-zeros bug this fixture exists to catch.
    """

    def __init__(self, items):
        self._items = list(items)
        self._spent = False
        self.starts = 0
        self.exhausted = 0

    def __iter__(self):
        self.starts += 1
        if not self._spent:
            self._spent = True
            for item in self._items:
                yield item
        self.exhausted += 1


class WorkerTotalsAcceptsAnyIterableTest(unittest.TestCase):
    """``worker_totals`` answers by its receipts, not by their container."""

    def test_list_baseline_is_the_eight_keys_and_does_not_move(self):
        """The frozen baseline. GREEN today; this row must not disturb it.

        Stated as literal expected values rather than as a comparison against
        another call, so that a change to what a list totals fails here instead
        of passing by agreeing with itself.
        """
        totals = scorecard.worker_totals(list(CORPUS))
        self.assertEqual(set(totals), TOTALS_KEYS)
        self.assertEqual(totals, {
            "attempts": 6,
            "tasks": 5,
            "billed_usd": 0.912364,
            "tokens": 474677,
            "cost_reported": False,
            "cost_unreported_tasks": ["silent"],
            "first_pass_tasks": 3,
            "first_pass_rate": 0.6,
        })

    def test_empty_list_baseline_reports_cost_reported_false(self):
        """Row #95's answer for the empty case. GREEN today; frozen here so
        that the empty-generator assertion below has a real target."""
        self.assertEqual(scorecard.worker_totals([]), {
            "attempts": 0,
            "tasks": 0,
            "billed_usd": 0.0,
            "tokens": 0,
            "cost_reported": False,
            "cost_unreported_tasks": [],
            "first_pass_tasks": 0,
            "first_pass_rate": 0.0,
        })

    def test_generator_totals_identically_to_the_same_receipts_as_a_list(self):
        """The row, stated once: same receipts, different container, same
        answer -- key for key, not merely "did not raise"."""
        expected = scorecard.worker_totals(list(CORPUS))
        generator = (receipt for receipt in CORPUS)
        self.assertEqual(scorecard.worker_totals(generator), expected)

    def test_generator_function_totals_identically(self):
        """A hand-written generator function, which is what a caller streaming
        receipts off disk would actually pass."""
        def stream():
            for receipt in CORPUS:
                yield receipt

        expected = scorecard.worker_totals(list(CORPUS))
        self.assertEqual(scorecard.worker_totals(stream()), expected)

    def test_iterator_totals_identically(self):
        """``iter(list)`` -- a sequence's own iterator, which has no ``len``."""
        expected = scorecard.worker_totals(list(CORPUS))
        self.assertEqual(scorecard.worker_totals(iter(CORPUS)), expected)

    def test_tuple_totals_identically(self):
        """A tuple is a sequence and works today; pinned so that a widening
        implemented by special-casing ``list`` is still caught."""
        expected = scorecard.worker_totals(list(CORPUS))
        self.assertEqual(scorecard.worker_totals(tuple(CORPUS)), expected)

    def test_map_and_filter_objects_total_identically(self):
        """Lazy builtins, the other everyday non-sequence iterables."""
        expected = scorecard.worker_totals(list(CORPUS))
        self.assertEqual(
            scorecard.worker_totals(map(lambda receipt: receipt, CORPUS)),
            expected)
        self.assertEqual(
            scorecard.worker_totals(filter(lambda receipt: True, CORPUS)),
            expected)

    def test_empty_generator_answers_exactly_as_the_empty_list(self):
        """The dangerous empty case. ``cost_reported`` must stay False: with
        nothing measured, nothing was reported, and a widening that counts an
        empty generator as "no receipt failed to report" would flip a release's
        reliability flag to True on a corpus of nothing."""
        expected = scorecard.worker_totals([])
        empty = (receipt for receipt in [])
        totals = scorecard.worker_totals(empty)
        self.assertEqual(totals, expected)
        self.assertIs(totals["cost_reported"], False)
        self.assertEqual(totals["attempts"], 0)

    def test_single_receipt_generator_matches_single_receipt_list(self):
        """One receipt is where an off-by-one between the two ``len`` reads
        would show: ``attempts`` 1 and ``cost_reported`` True."""
        one = [_receipt("solo", 1, 0.5, 1000, True, True)]
        expected = scorecard.worker_totals(list(one))
        self.assertEqual(scorecard.worker_totals(iter(one)), expected)
        self.assertIs(expected["cost_reported"], True)

    def test_iterable_is_started_exactly_once(self):
        """Consumption is single-pass, and the answer is the real one.

        Both halves matter. A second pass over a spent iterable yields nothing
        rather than raising, so an implementation that loops twice would report
        ``attempts: 0`` while looking perfectly healthy -- the totals assertion
        catches that -- and an implementation that materialises the argument and
        then re-reads the *original* would pass the totals assertion while still
        being a two-pass read -- the ``starts`` assertion catches that.
        """
        counting = _CountingIterable(CORPUS)
        totals = scorecard.worker_totals(counting)
        self.assertEqual(totals, scorecard.worker_totals(list(CORPUS)))
        self.assertEqual(
            counting.starts, 1,
            "worker_totals must iterate its argument exactly once; it was "
            f"started {counting.starts} times")

    def test_empty_iterable_is_started_exactly_once(self):
        """The same single-pass guarantee with nothing to yield, where a
        re-iteration is otherwise invisible."""
        counting = _CountingIterable([])
        totals = scorecard.worker_totals(counting)
        self.assertEqual(totals, scorecard.worker_totals([]))
        self.assertEqual(counting.starts, 1)

    def test_generator_is_fully_consumed_no_receipt_is_dropped(self):
        """Every receipt handed over is counted. Guards the other direction of
        a single-pass fix: stopping early (a ``next()`` peek that is not put
        back, or an ``islice``) would leave the generator unfinished and the
        totals short."""
        seen = []

        def stream():
            for receipt in CORPUS:
                seen.append(receipt["task_id"])
                yield receipt

        totals = scorecard.worker_totals(stream())
        self.assertEqual(seen, [receipt["task_id"] for receipt in CORPUS])
        self.assertEqual(totals["attempts"], len(CORPUS))

    def test_list_argument_is_not_mutated_or_consumed(self):
        """A widening must not drain what it was given. The caller's list is
        still the same list afterwards, and totalling it again answers the
        same -- ``build_scorecard`` hands ``worker_totals`` a list it did not
        copy."""
        receipts = list(CORPUS)
        before = [id(receipt) for receipt in receipts]
        first = scorecard.worker_totals(receipts)
        self.assertEqual([id(receipt) for receipt in receipts], before)
        self.assertEqual(scorecard.worker_totals(receipts), first)


if __name__ == "__main__":
    unittest.main()
