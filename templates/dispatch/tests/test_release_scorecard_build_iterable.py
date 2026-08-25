"""Coordinator-authored oracle for ``release_scorecard.build_scorecard`` --
shape of the arguments, not shape of the answer.

``test_release_scorecard_iterable.py`` widened ``worker_totals`` to accept any
iterable of receipts: it materialises its argument once up front because it
reads the receipts in one pass but needs the length twice (``attempts``, and the
empty-corpus rule behind ``cost_reported``). That row is merged and green.

``build_scorecard`` has the same defect one level up and was not widened. It
takes ``len(escalations)`` for ``escalations.count`` while also looping over
``escalations`` to lift task ids and stop conditions, so a generator of
escalation records raises ``TypeError: object of type 'generator' has no
len()`` -- after the loop has already drained it. A caller who wants to stream
escalations cannot, which means widening ``worker_totals`` alone did not deliver
the end-to-end capability it looked like it delivered.

Reading the signature -- ``build_scorecard(release, rows, receipts,
escalations, recorded_at, scope=None)`` -- three arguments carry corpora and are
pinned here:

* ``rows`` is only ever looped (``frontier_totals`` -> ``reduce_sessions``), so
  it already accepts any iterable. Pinned anyway: it is part of the promised
  end-to-end capability, and a widening implemented by materialising the wrong
  argument, or a future ``len(rows)``, must fail here.
* ``receipts`` is handed straight to the already-widened ``worker_totals``, so
  it also works today. Pinned for the same reason: ``build_scorecard`` must not
  reach around its delegate and measure the receipts itself.
* ``escalations`` is the one that is broken. It is the declared red.

``release``, ``recorded_at`` and ``scope`` are scalars and are not touched.

Two failure modes are pinned beyond "does not raise":

* **Double consumption.** A one-shot iterable looped twice yields nothing the
  second time. If the second pass is the one that counts, the answer is a
  silent zero on a corpus that was not empty -- an escalation count of 0 for a
  release that escalated four times is worse than a crash. The counting
  fixtures below assert both that iteration STARTS exactly once and that the
  totals are the real ones, so a re-iteration is caught whether it raises,
  reports zeros, or double-counts.
* **The empty corpus.** ``worker_totals([])`` reports ``cost_reported: False``
  on purpose -- with nothing measured, "nothing failed to report" is not a
  measured zero -- and ``build_scorecard`` carries that up as
  ``cost_usd.total_reliable``. A careless materialisation (``escalations =
  escalations or []``, a length taken after a partial drain) is exactly where
  that answer comes back wrong, so every empty case is asserted against the
  empty-list answer key for key.

This is a widening, not a change. The list answers below are stated as literal
expected values rather than as a second call to ``build_scorecard``: a
self-comparison passes even when both sides move together, which would let the
list behaviour drift silently under cover of this row. Those baselines are
GREEN today and must stay green.

Nothing here asserts HOW the widening is done. ``list(...)`` is the obvious
implementation; a running counter, a tuple, or a two-pass over a materialised
copy would all satisfy this file.
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


scorecard = _load_module("release_scorecard_subject",
                         SCRIPTS / "release_scorecard.py")


#: The eight top-level keys, spelled as literals so that a widening which also
#: adds or drops a key is caught here rather than absorbed by a dict compare.
TOP_LEVEL_KEYS = frozenset({
    "schema_version", "release", "recorded_at",
    "frontier", "worker", "escalations", "cost_usd", "scope",
})

RELEASE = "v5"
RECORDED_AT = "2026-08-24T10:30:00Z"


#: The sink corpus from ``test_release_scorecard_build.py``: session "loop-a"
#: stopped four times and its snapshots supersede each other (the surviving one
#: costs 2.75), "loop-b" and "loop-c" stopped once each, and one row carries no
#: session id at all because the real sink carries those too. Interleaved the
#: way the shared sink appends.
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


def _receipt(task_id, attempt, cost_usd, tokens, cost_reported, passed=True):
    """A receipt shaped like docs/evidence/receipts/*/receipt.json.

    The spend the worker reports lives under driver_steps -> the "run" entry ->
    receipt -> spend, with decoy figures on the neighbouring steps, and the
    first-pass signal lives at gate.evidence.passed. Same construction the
    build and worker oracles use, so these receipts are read here exactly as
    they will be in production.
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


#: Six receipts over five tasks, deliberately heterogeneous so a wrong answer
#: is distinguishable from a right one on every reported key: non-round spends
#: and token counts, "retried" appearing twice so attempts (6) differ from
#: tasks (5), "retried"'s first attempt failing its gate so only three of five
#: tasks are first passes (rate 0.6, which no off-by-one produces), and
#: "silent" reporting no cost so ``cost_reported`` is False with a non-empty
#: ``cost_unreported_tasks``. Dropping any one receipt moves at least four keys.
RECEIPTS: tuple[dict, ...] = (
    _receipt("alpha", 1, 0.020864, 292309, True, True),
    _receipt("bravo", 1, 0.1375, 41022, True, True),
    _receipt("charlie", 1, 0.004, 9001, True, False),
    _receipt("retried", 1, 0.25, 40000, True, False),
    _receipt("retried", 2, 0.5, 80000, True, True),
    _receipt("silent", 1, 0.0, 12345, False, True),
)

#: The same corpus minus the silent route: every receipt reported, so
#: ``cost_reported`` -- and with it ``cost_usd.total_reliable`` -- is True. Kept
#: so the reliability flag is pinned in BOTH directions across the widening; a
#: fixture that only ever produces False would not notice a flag stuck low.
REPORTING_RECEIPTS: tuple[dict, ...] = RECEIPTS[:-1]


#: Four escalation records over two tasks, shaped like the JSON-lines records
#: ``dispatch_release.py`` appends and ``load_sink_rows`` reads back.
#: "V5-M13-retry-branch" escalated twice, so ``count`` (4) is not ``len(tasks)``
#: (2). The second of its two carries no ``stop_condition`` -- the driver
#: stopped on an exit code, not a declared condition -- so it must be omitted
#: rather than contribute a None. The last record carries no ``metadata`` dict
#: at all: it contributes nothing to tasks or stop_conditions but still counts,
#: which is precisely the case where a widening that conflates "records seen in
#: the loop" with ``len(escalations)`` reports 3 instead of 4.
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
    {"type": "workflow.escalation", "actor": "dispatch-release",
     "summary": "escalation recorded without metadata",
     "detail": "hand-filed by the operator",
     "recorded_at": "2026-08-24T10:25:12Z"},
)


#: The whole answer for (SINK_ROWS, RECEIPTS, ESCALATIONS), by hand.
#:
#: frontier: the three surviving snapshots only -- 2.75 + 1.25 + 0.35 = 4.35,
#: turns 8 + 4 + 1, msgs 14 + 7 + 1, tools 12 + 6 + 0, duration 305 + 140 + 18,
#: rework 2 + 1 + 0. Summing every row instead would report 106.75.
#: worker: 0.020864 + 0.1375 + 0.004 + 0.25 + 0.5 + 0.0 = 0.912364 over
#: 292309 + 41022 + 9001 + 40000 + 80000 + 12345 = 474677 tokens.
#: escalations: four records, two tasks, two stop conditions.
#: cost_usd: the money is the worker figure and only the worker figure.
EXPECTED: dict = {
    "schema_version": "workflow-scorecard/v1",
    "release": RELEASE,
    "recorded_at": RECORDED_AT,
    "frontier": {
        "sessions": 3,
        "turns": 13,
        "assistant_msgs": 22,
        "tool_calls": 18,
        "duration_s": 463,
        "usage_equivalent_usd": 4.35,
        "rework_rounds": 3,
    },
    "worker": {
        "attempts": 6,
        "tasks": 5,
        "billed_usd": 0.912364,
        "tokens": 474677,
        "cost_reported": False,
        "cost_unreported_tasks": ["silent"],
        "first_pass_tasks": 3,
        "first_pass_rate": 0.6,
    },
    "escalations": {
        "count": 4,
        "tasks": ["V5-M13-retry-branch", "V5-M22-silent-route"],
        "stop_conditions": ["cap-exceeded", "diff-empty"],
    },
    "cost_usd": {
        "worker_billed_usd": 0.912364,
        "frontier_usage_equivalent_usd": 4.35,
        "total_billed_usd": 0.912364,
        "commensurable": False,
        "total_reliable": False,
    },
    "scope": {},
}

#: The answer when all three corpora are empty, by hand. ``cost_reported`` and
#: ``total_reliable`` are False, not True: nothing was measured, so "nothing
#: failed to report" is not a measured zero. This is the answer a careless
#: materialisation of an empty generator most often gets wrong.
EXPECTED_EMPTY: dict = {
    "schema_version": "workflow-scorecard/v1",
    "release": RELEASE,
    "recorded_at": RECORDED_AT,
    "frontier": {
        "sessions": 0,
        "turns": 0,
        "assistant_msgs": 0,
        "tool_calls": 0,
        "duration_s": 0,
        "usage_equivalent_usd": 0.0,
        "rework_rounds": 0,
    },
    "worker": {
        "attempts": 0,
        "tasks": 0,
        "billed_usd": 0.0,
        "tokens": 0,
        "cost_reported": False,
        "cost_unreported_tasks": [],
        "first_pass_tasks": 0,
        "first_pass_rate": 0.0,
    },
    "escalations": {"count": 0, "tasks": [], "stop_conditions": []},
    "cost_usd": {
        "worker_billed_usd": 0.0,
        "frontier_usage_equivalent_usd": 0.0,
        "total_billed_usd": 0.0,
        "commensurable": False,
        "total_reliable": False,
    },
    "scope": {},
}


class _CountingIterable:
    """An iterable that yields its items once and records every start.

    ``starts`` counts how many times ``__iter__`` was entered. A second pass
    yields nothing at all -- exactly like a spent generator -- so an
    implementation that loops twice sees an empty second pass rather than an
    error, which is the silent-zeros bug this fixture exists to catch.
    """

    def __init__(self, items):
        self._items = list(items)
        self._spent = False
        self.starts = 0

    def __iter__(self):
        self.starts += 1
        if not self._spent:
            self._spent = True
            for item in self._items:
                yield item


class _RecordingStream:
    """A one-shot generator that records what it actually handed over.

    ``emitted`` is appended to as each item leaves the generator, so a
    consumer that stops early (a ``next()`` peek that is never put back, an
    ``islice``, a ``zip`` against something shorter) leaves ``emitted`` short of
    the corpus. Dropped records are dropped money, so this is asserted
    separately from the totals.
    """

    def __init__(self, items):
        self.items = list(items)
        self.emitted = []
        self.starts = 0

    def __iter__(self):
        self.starts += 1
        for item in self.items:
            self.emitted.append(item)
            yield item


def _fresh(corpus):
    """A fresh mutable copy, so mutation by the subject cannot leak fixtures."""
    return copy.deepcopy(list(corpus))


def _build(rows=SINK_ROWS, receipts=RECEIPTS, escalations=ESCALATIONS,
           release=RELEASE, recorded_at=RECORDED_AT):
    """Five positional arguments, exactly as ``main`` calls it minus scope."""
    return scorecard.build_scorecard(release, rows, receipts, escalations,
                                     recorded_at)


class BuildScorecardListBaselineTest(unittest.TestCase):
    """The frozen answer for lists. GREEN today; this row must not move it.

    Stated as literal expected values rather than as a comparison against
    another ``build_scorecard`` call, so that a change to what lists report
    fails here instead of passing by agreeing with itself.
    """

    def test_list_baseline_is_the_whole_scorecard_by_value(self):
        card = _build(_fresh(SINK_ROWS), _fresh(RECEIPTS), _fresh(ESCALATIONS))
        self.assertIsInstance(card, dict)
        self.assertEqual(set(card), set(TOP_LEVEL_KEYS))
        self.assertEqual(card, EXPECTED)

    def test_empty_list_baseline_reports_false_not_reliable(self):
        card = _build([], [], [])
        self.assertEqual(card, EXPECTED_EMPTY)
        self.assertIs(card["worker"]["cost_reported"], False)
        self.assertIs(card["cost_usd"]["total_reliable"], False)
        self.assertEqual(card["escalations"]["count"], 0)

    def test_fully_reporting_list_baseline_is_reliable(self):
        """The reliability flag pinned in the other direction: with the silent
        route dropped from the corpus, ``total_reliable`` is True."""
        card = _build(_fresh(SINK_ROWS), _fresh(REPORTING_RECEIPTS),
                      _fresh(ESCALATIONS))
        self.assertIs(card["worker"]["cost_reported"], True)
        self.assertIs(card["cost_usd"]["total_reliable"], True)
        self.assertEqual(card["worker"]["attempts"], 5)
        self.assertEqual(card["worker"]["cost_unreported_tasks"], [])


class BuildScorecardRowsIterableTest(unittest.TestCase):
    """``rows`` is only ever looped, so it already accepts any iterable. Pinned
    so a widening that materialises the wrong argument, or a later ``len(rows)``
    added alongside one, fails here."""

    def test_generator_of_rows_gives_the_same_scorecard(self):
        card = _build(rows=(row for row in _fresh(SINK_ROWS)))
        self.assertEqual(card, EXPECTED)

    def test_other_non_sequence_iterables_of_rows_agree(self):
        for label, make in (
            ("iterator", lambda rows: iter(rows)),
            ("tuple", tuple),
            ("genexp", lambda rows: (row for row in rows)),
            ("map", lambda rows: map(lambda row: row, rows)),
        ):
            with self.subTest(container=label):
                self.assertEqual(_build(rows=make(_fresh(SINK_ROWS))), EXPECTED)

    def test_empty_generator_of_rows_answers_as_the_empty_list(self):
        card = _build(rows=(row for row in []), receipts=[], escalations=[])
        self.assertEqual(card, EXPECTED_EMPTY)

    def test_rows_iterable_is_started_exactly_once(self):
        counting = _CountingIterable(_fresh(SINK_ROWS))
        card = _build(rows=counting)
        self.assertEqual(card, EXPECTED,
                         "rows were re-iterated: a spent second pass yields "
                         "nothing, so the frontier half silently zeroed")
        self.assertEqual(counting.starts, 1,
                         "build_scorecard must iterate rows exactly once; it "
                         f"was started {counting.starts} times")

    def test_no_row_is_dropped(self):
        stream = _RecordingStream(_fresh(SINK_ROWS))
        card = _build(rows=stream)
        self.assertEqual(stream.emitted, list(_fresh(SINK_ROWS)),
                         "rows were not fully consumed -- records handed over "
                         "were dropped before they were counted")
        self.assertEqual(card["frontier"], EXPECTED["frontier"])


class BuildScorecardReceiptsIterableTest(unittest.TestCase):
    """``receipts`` goes straight to the already-widened ``worker_totals``.
    Pinned so ``build_scorecard`` cannot reach around its delegate and measure
    the receipts itself."""

    def test_generator_of_receipts_gives_the_same_scorecard(self):
        card = _build(receipts=(receipt for receipt in _fresh(RECEIPTS)))
        self.assertEqual(card, EXPECTED)

    def test_other_non_sequence_iterables_of_receipts_agree(self):
        for label, make in (
            ("iterator", lambda items: iter(items)),
            ("tuple", tuple),
            ("genexp", lambda items: (item for item in items)),
            ("map", lambda items: map(lambda item: item, items)),
        ):
            with self.subTest(container=label):
                self.assertEqual(_build(receipts=make(_fresh(RECEIPTS))),
                                 EXPECTED)

    def test_empty_generator_of_receipts_answers_as_the_empty_list(self):
        """The dangerous empty case reaching the top level: an empty receipt
        corpus must still report ``total_reliable: False``."""
        card = _build(rows=[], receipts=(item for item in []), escalations=[])
        self.assertEqual(card, EXPECTED_EMPTY)
        self.assertIs(card["cost_usd"]["total_reliable"], False)

    def test_receipts_iterable_is_started_exactly_once(self):
        counting = _CountingIterable(_fresh(RECEIPTS))
        card = _build(receipts=counting)
        self.assertEqual(card, EXPECTED,
                         "receipts were re-iterated: the second pass is empty, "
                         "so attempts and billed_usd silently zeroed")
        self.assertEqual(counting.starts, 1,
                         "build_scorecard must iterate receipts exactly once; "
                         f"it was started {counting.starts} times")

    def test_no_receipt_is_dropped(self):
        stream = _RecordingStream(_fresh(RECEIPTS))
        card = _build(receipts=stream)
        self.assertEqual([item["task_id"] for item in stream.emitted],
                         [item["task_id"] for item in RECEIPTS],
                         "receipts were not fully consumed -- a dropped "
                         "receipt is dropped money")
        self.assertEqual(card["worker"], EXPECTED["worker"])


class BuildScorecardEscalationsIterableTest(unittest.TestCase):
    """``escalations`` is the broken one: it is looped AND ``len()``-ed. RED
    today with ``TypeError: object of type 'generator' has no len()``."""

    def test_generator_of_escalations_gives_the_same_scorecard(self):
        card = _build(escalations=(item for item in _fresh(ESCALATIONS)))
        self.assertEqual(card, EXPECTED)

    def test_other_non_sequence_iterables_of_escalations_agree(self):
        for label, make in (
            ("iterator", lambda items: iter(items)),
            ("tuple", tuple),
            ("genexp", lambda items: (item for item in items)),
            ("map", lambda items: map(lambda item: item, items)),
        ):
            with self.subTest(container=label):
                self.assertEqual(_build(escalations=make(_fresh(ESCALATIONS))),
                                 EXPECTED)

    def test_generator_function_of_escalations_agrees(self):
        """A hand-written generator function, which is what a caller streaming
        escalation records off a JSON-lines file would actually pass."""
        def stream():
            for item in _fresh(ESCALATIONS):
                yield item

        self.assertEqual(_build(escalations=stream()), EXPECTED)

    def test_empty_generator_of_escalations_answers_as_the_empty_list(self):
        card = _build(rows=[], receipts=[], escalations=(item for item in []))
        self.assertEqual(card, EXPECTED_EMPTY)
        self.assertEqual(card["escalations"],
                         {"count": 0, "tasks": [], "stop_conditions": []})

    def test_empty_generator_of_escalations_with_a_real_corpus(self):
        """Zero escalations alongside a real sink and real receipts: the
        escalation block zeroes and NOTHING ELSE moves."""
        card = _build(escalations=(item for item in []))
        self.assertEqual(card["escalations"],
                         {"count": 0, "tasks": [], "stop_conditions": []})
        self.assertEqual(card["frontier"], EXPECTED["frontier"])
        self.assertEqual(card["worker"], EXPECTED["worker"])
        self.assertEqual(card["cost_usd"], EXPECTED["cost_usd"])

    def test_escalations_iterable_is_started_exactly_once(self):
        """Both halves matter. A second pass over a spent iterable yields
        nothing rather than raising, so an implementation that loops once to
        lift task ids and again to count would report ``count: 0`` for a
        release that escalated four times while looking perfectly healthy --
        the scorecard assertion catches that. An implementation that
        materialises a copy and then re-reads the ORIGINAL would pass the
        scorecard assertion while still being a two-pass read -- the ``starts``
        assertion catches that."""
        counting = _CountingIterable(_fresh(ESCALATIONS))
        card = _build(escalations=counting)
        self.assertEqual(card, EXPECTED,
                         "escalations were re-iterated: the second pass is "
                         "empty, so the count silently zeroed")
        self.assertEqual(counting.starts, 1,
                         "build_scorecard must iterate escalations exactly "
                         f"once; it was started {counting.starts} times")

    def test_empty_escalations_iterable_is_started_exactly_once(self):
        """The same single-pass guarantee with nothing to yield, where a
        re-iteration is otherwise invisible."""
        counting = _CountingIterable([])
        card = _build(rows=[], receipts=[], escalations=counting)
        self.assertEqual(card, EXPECTED_EMPTY)
        self.assertEqual(counting.starts, 1)

    def test_no_escalation_is_dropped(self):
        """Guards the other direction of a single-pass fix. A ``next()`` peek
        or an ``islice`` satisfies "consumed once" while losing records; the
        metadata-less fourth record is the one a length-from-the-loop
        implementation loses, and it is worth a whole escalation in the count."""
        stream = _RecordingStream(_fresh(ESCALATIONS))
        card = _build(escalations=stream)
        self.assertEqual([item["recorded_at"] for item in stream.emitted],
                         [item["recorded_at"] for item in ESCALATIONS],
                         "escalations were not fully consumed -- records handed "
                         "over were dropped before they were counted")
        self.assertEqual(card["escalations"]["count"], len(ESCALATIONS))
        self.assertEqual(card["escalations"], EXPECTED["escalations"])


class BuildScorecardAllArgumentsIterableTest(unittest.TestCase):
    """The end-to-end capability: all three corpora streamed in one call.

    A partial widening -- one argument fixed while another is still ``len()``-ed
    -- fails here even if it passed the per-argument class above, because these
    calls hand every corpus over as a one-shot iterable at the same time.
    """

    def test_all_three_as_generators_give_the_same_scorecard(self):
        card = _build(
            rows=(row for row in _fresh(SINK_ROWS)),
            receipts=(item for item in _fresh(RECEIPTS)),
            escalations=(item for item in _fresh(ESCALATIONS)),
        )
        self.assertEqual(card, EXPECTED)

    def test_all_three_as_iterators_give_the_same_scorecard(self):
        card = _build(rows=iter(_fresh(SINK_ROWS)),
                      receipts=iter(_fresh(RECEIPTS)),
                      escalations=iter(_fresh(ESCALATIONS)))
        self.assertEqual(card, EXPECTED)

    def test_all_three_are_each_started_exactly_once(self):
        rows = _CountingIterable(_fresh(SINK_ROWS))
        receipts = _CountingIterable(_fresh(RECEIPTS))
        escalations = _CountingIterable(_fresh(ESCALATIONS))
        card = _build(rows=rows, receipts=receipts, escalations=escalations)
        self.assertEqual(card, EXPECTED)
        self.assertEqual(
            (rows.starts, receipts.starts, escalations.starts), (1, 1, 1),
            "each corpus must be iterated exactly once; got starts "
            f"rows={rows.starts} receipts={receipts.starts} "
            f"escalations={escalations.starts}")

    def test_all_three_are_fully_consumed(self):
        rows = _RecordingStream(_fresh(SINK_ROWS))
        receipts = _RecordingStream(_fresh(RECEIPTS))
        escalations = _RecordingStream(_fresh(ESCALATIONS))
        card = _build(rows=rows, receipts=receipts, escalations=escalations)
        self.assertEqual(len(rows.emitted), len(SINK_ROWS))
        self.assertEqual(len(receipts.emitted), len(RECEIPTS))
        self.assertEqual(len(escalations.emitted), len(ESCALATIONS))
        self.assertEqual(card, EXPECTED)

    def test_all_three_empty_generators_answer_as_empty_lists(self):
        card = _build(rows=(row for row in []),
                      receipts=(item for item in []),
                      escalations=(item for item in []))
        self.assertEqual(card, EXPECTED_EMPTY)
        self.assertIs(card["cost_usd"]["total_reliable"], False)

    def test_streamed_scope_argument_still_rides_along(self):
        """The optional trailing ``scope`` is a scalar dict and is unaffected by
        the widening: it must still be carried through verbatim when the three
        corpora arrive as generators."""
        scope = {"project": "agentops", "since": "2026-08-24T00:00:00Z",
                 "until": None}
        card = scorecard.build_scorecard(
            RELEASE,
            (row for row in _fresh(SINK_ROWS)),
            (item for item in _fresh(RECEIPTS)),
            (item for item in _fresh(ESCALATIONS)),
            RECORDED_AT,
            scope,
        )
        self.assertEqual(card, dict(EXPECTED, scope=scope))


class BuildScorecardListsUnaffectedTest(unittest.TestCase):
    """A widening must not drain, reorder or mutate what a list caller gave it.
    ``main`` hands ``build_scorecard`` lists it goes on to use."""

    def test_list_arguments_are_not_consumed_or_reordered(self):
        rows = _fresh(SINK_ROWS)
        receipts = _fresh(RECEIPTS)
        escalations = _fresh(ESCALATIONS)
        identities = ([id(item) for item in rows],
                      [id(item) for item in receipts],
                      [id(item) for item in escalations])
        first = _build(rows, receipts, escalations)
        self.assertEqual(
            ([id(item) for item in rows], [id(item) for item in receipts],
             [id(item) for item in escalations]),
            identities,
            "build_scorecard drained, reordered or replaced its arguments")
        self.assertEqual(_build(rows, receipts, escalations), first,
                         "a second call on the same lists answered differently")


if __name__ == "__main__":
    unittest.main()
