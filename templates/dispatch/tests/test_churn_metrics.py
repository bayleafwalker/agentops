"""Coordinator-authored oracle for ``churn_metrics.churn_metrics`` (agentops#2046,
the measurement half of "record enough receipt metrics to detect repeated reads,
long no-mutation loops, cached-token churn, and fixed coordinator overhead").

``churn_verdict`` stops a worker that has stopped making progress, and records
nothing when it does not stop. ``churn_stop`` is ``None`` on every healthy run,
so a worker that read one path four times against a limit of four leaves exactly
the same trace as one that read it once: nothing. There is no way to tell "at the
limit" from "nowhere near it", and no trend to read across packets. This row adds
the counters and nothing else -- no receipt wiring, no CLI, no file I/O.

What this file pins:

* **The counting rules are the verdict's rules.** Two functions answering the
  same question differently is a defect this repo has already had to undo once
  (``_path_allowed`` versus ``_matches_any``). Every rule ``churn_verdict``
  applies -- only ``tool_use``; a *completed* mutation resets; a failed mutation
  attempt does not reset and is a failed mutation rather than an incomplete tool
  event; a non-mutation call that did not complete is skipped entirely and does
  not spend a step; reads are keyed on ``part.state.input.filePath`` -- gets its
  own test here. The mutation tool set is imported from ``hybrid_dispatch`` so
  the two cannot drift.

* **The metrics agree with the verdict.** For any stream and any positive
  limits, ``churn_verdict`` returns ``None`` exactly when no metric exceeds its
  limit and no ``worker_cannot_write`` run occurred; and when it does fire, the
  reason it names is the first breach in stream order.
  ``max_steps_without_mutation`` and ``max_repeated_reads`` may legitimately
  exceed the number the verdict *reported*, because the verdict returns early
  and stops counting while the metrics see the whole stream -- what must agree
  is the threshold crossing, not the printed figure.

* **The maximum, not the value at the end.** ``max_steps_without_mutation`` is
  the high-water mark over the whole stream.
  ``MaximumNotTheFinalRunTests`` exists solely for the most likely wrong
  implementation: reporting ``steps_since_mutation`` as it stood when the stream
  ended. That stub is silently wrong on exactly the streams worth measuring --
  a worker that circled nineteen times and then finally wrote reports 0 -- and
  it passes every other test in this file, so it gets its own class.

* **Any iterable, consumed once.** ``events`` is whatever ``churn_verdict``
  would take. This codebase has fixed the same "asks its argument for a length,
  or loops it twice" defect twice already, in ``worker_totals`` and
  ``build_scorecard``; a third is not allowed in.

Choices made where the spec left room, all of them asserted below so a reader
can find the decision rather than infer it:

* ``tool_events`` counts ``tool_use`` events whose ``state.status`` is
  ``"completed"`` -- completed mutations included, since ``churn_verdict``
  considers those too (they reset the run). Failed mutation attempts and
  incomplete non-mutation calls are *not* in it; they are reported by
  ``failed_mutation_runs`` and ``incomplete_tool_events``. The partition is
  pinned by ``test_the_four_categories_partition_the_tool_use_events``.
* ``failed_mutation_runs`` counts *runs*, one per maximal run of failed mutation
  attempts of length three or more -- a run of five failures is one, not three
  and not five. "Consecutive" means what it means inside ``churn_verdict``:
  only a completed mutation ends a run, so unrelated reads and greps between two
  failed writes do not break it.
* Ties for ``most_read_path`` are not pinned to an order. The test asserts only
  that the returned path is one that actually attained ``max_repeated_reads``.
* The agreement property is stated for *positive* limits.
  ``churn_verdict`` disables a check on a falsy limit (``if max_steps and ...``)
  while the metrics carry no limits at all, so a zero or missing limit is
  outside the property by construction rather than a disagreement.
* ``worker_cannot_write`` returns first and therefore pre-empts. The agreement
  property is written to accommodate that honestly instead of being weakened:
  the "verdict is None" biconditional includes ``failed_mutation_runs == 0`` as
  a conjunct, and the reason-specific direction runs verdict->metric
  unconditionally but metric->reason only modulo an earlier-firing reason. No
  case was found where the two genuinely cannot agree.

Rule 11: this file imports ``hybrid_dispatch`` and ``churn_metrics`` and nothing
else of the repo's own; it runs no git and no subprocess.

The fixture shape was checked against real captured OpenCode streams under
``docs/evidence/receipts/*/worker-stdout.txt``: ``{"type": "tool_use", "part":
{"type": "tool", "tool": "read", "state": {"status": "completed", "input":
{"filePath": ...}}}}``, with ``"error"`` the status a refused or failed call
actually arrives with.
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


# ``hybrid_dispatch.py`` is large; it is loaded once here and shared, and it is
# the source of both ``churn_verdict`` and ``MUTATION_TOOLS``.
dispatch = _load_module("churn_metrics_verdict_subject", SCRIPTS / "hybrid_dispatch.py")


def _metrics(events):
    """Load the subject lazily, so its absence fails tests rather than import."""
    module = _load_module("churn_metrics_subject", SCRIPTS / "churn_metrics.py")
    return module.churn_metrics(events)


#: One non-mutating tool that is not ``read``, so a step-budget fixture is never
#: also a repeated-read fixture.
STEP_TOOL = "glob"

#: One mutating tool, taken from the subject set rather than written out.
MUTATION_TOOL = sorted(dispatch.MUTATION_TOOLS)[0]

EXPECTED_KEYS = {
    "tool_events",
    "max_steps_without_mutation",
    "max_repeated_reads",
    "most_read_path",
    "distinct_paths_read",
    "completed_mutations",
    "failed_mutation_runs",
    "incomplete_tool_events",
}


def _tool(tool: str, status: str = "completed", path: str | None = None) -> dict:
    """One ``tool_use`` event in the shape the stream parser actually delivers."""
    state: dict = {"status": status}
    if path is not None:
        state["input"] = {"filePath": path}
    return {"type": "tool_use", "part": {"type": "tool", "tool": tool, "state": state}}


def _step(status: str = "completed") -> dict:
    return _tool(STEP_TOOL, status)


def _read(path: str | None = "a.py", status: str = "completed") -> dict:
    return _tool("read", status, path)


def _mutate(status: str = "completed") -> dict:
    return _tool(MUTATION_TOOL, status)


def _limits(steps: int, reads: int) -> dict:
    return {
        "max_reasoning_steps_without_mutation": steps,
        "max_repeated_reads_per_path": reads,
    }


class _CountingIterable:
    """An iterable that reports how many times something started iterating it.

    A one-shot iterable looped twice yields nothing the second time, so a double
    consumption shows up as silent zeros rather than an exception -- the worse
    bug. Counting the starts catches it whichever way it manifests.
    """

    def __init__(self, events):
        self._events = list(events)
        self.starts = 0

    def __iter__(self):
        self.starts += 1
        yield from self._events


class ShapeOfTheAnswerTests(unittest.TestCase):
    """The dict is exactly these keys, with these types, on every stream."""

    def test_empty_stream_reports_measured_zeros_and_no_path(self):
        result = _metrics([])
        self.assertEqual(set(result), EXPECTED_KEYS)
        self.assertEqual(result["tool_events"], 0)
        self.assertEqual(result["max_steps_without_mutation"], 0)
        self.assertEqual(result["max_repeated_reads"], 0)
        self.assertEqual(result["distinct_paths_read"], 0)
        self.assertEqual(result["completed_mutations"], 0)
        self.assertEqual(result["failed_mutation_runs"], 0)
        self.assertEqual(result["incomplete_tool_events"], 0)
        # ``None`` and not ``""``: no read was counted, so no path reached the
        # maximum, and a receipt must not name a file that was never read.
        self.assertIsNone(result["most_read_path"])

    def test_key_set_is_exact_on_a_populated_stream(self):
        result = _metrics(
            [_read("a.py"), _mutate(), _step(), _step("error"), _mutate("error")]
        )
        self.assertEqual(set(result), EXPECTED_KEYS)
        for key in EXPECTED_KEYS - {"most_read_path"}:
            self.assertIsInstance(result[key], int, key)
            self.assertNotIsInstance(result[key], bool, key)
        self.assertIsInstance(result["most_read_path"], str)

    def test_a_populated_stream_is_not_all_zeros(self):
        """The all-zeros stub must fail loudly, not merely fail somewhere."""
        result = _metrics(
            [
                _read("a.py"),
                _read("a.py"),
                _step(),
                _mutate(),
                _step("error"),
                _mutate("error"),
                _mutate("error"),
                _mutate("error"),
            ]
        )
        self.assertEqual(result["tool_events"], 4)
        self.assertEqual(result["max_steps_without_mutation"], 3)
        self.assertEqual(result["max_repeated_reads"], 2)
        self.assertEqual(result["most_read_path"], "a.py")
        self.assertEqual(result["distinct_paths_read"], 1)
        self.assertEqual(result["completed_mutations"], 1)
        self.assertEqual(result["failed_mutation_runs"], 1)
        self.assertEqual(result["incomplete_tool_events"], 1)


class TheSameTermsAsTheVerdictTests(unittest.TestCase):
    """Each counting rule ``churn_verdict`` applies, applied here identically.

    A metric that disagrees with the guard it is meant to explain is worse than
    no metric: the receipt would contradict the stop on the same run.
    """

    def test_only_tool_use_events_are_counted(self):
        noise = [
            {"type": "step_start", "part": {"type": "step-start"}},
            {"type": "step_finish", "part": {"type": "step-finish", "tokens": {}}},
            {"type": "text", "part": {"type": "text", "text": "thinking"}},
            # A non-``tool_use`` event carrying a tool-shaped part is still not a
            # tool event: ``churn_verdict`` keys on ``type`` alone.
            {
                "type": "message",
                "part": {"tool": "read", "state": {"status": "completed",
                                                   "input": {"filePath": "a.py"}}},
            },
        ]
        result = _metrics(noise)
        self.assertEqual(result["tool_events"], 0)
        self.assertEqual(result["max_steps_without_mutation"], 0)
        self.assertEqual(result["max_repeated_reads"], 0)
        self.assertIsNone(result["most_read_path"])
        # Interleaving the same noise around real events changes nothing.
        real = [_step(), _read("a.py"), _mutate()]
        interleaved = []
        for event in real:
            interleaved.extend(noise)
            interleaved.append(event)
        self.assertEqual(_metrics(interleaved), _metrics(real))

    def test_every_tool_in_the_imported_mutation_set_resets_the_run(self):
        """The set is ``hybrid_dispatch.MUTATION_TOOLS``, not a local restatement."""
        self.assertTrue(dispatch.MUTATION_TOOLS)
        for tool in sorted(dispatch.MUTATION_TOOLS):
            with self.subTest(tool=tool):
                result = _metrics(
                    [_step(), _step(), _tool(tool), _step()]
                )
                self.assertEqual(result["completed_mutations"], 1)
                # High-water 2 from before the reset, 1 after it.
                self.assertEqual(result["max_steps_without_mutation"], 2)
                self.assertEqual(result["failed_mutation_runs"], 0)

    def test_a_completed_mutation_is_not_itself_a_step(self):
        # ``churn_verdict`` ``continue``s on a completed mutation without
        # incrementing, so three steps around two writes is a run of two, not
        # three.
        result = _metrics([_step(), _mutate(), _step(), _step(), _mutate()])
        self.assertEqual(result["max_steps_without_mutation"], 2)
        self.assertEqual(result["completed_mutations"], 2)
        self.assertEqual(result["tool_events"], 5)

    def test_a_failed_mutation_does_not_reset_the_run(self):
        # An attempt is not progress. The run spans the denied write.
        result = _metrics([_step(), _mutate("error"), _step()])
        self.assertEqual(result["max_steps_without_mutation"], 2)
        self.assertEqual(result["completed_mutations"], 0)

    def test_a_failed_mutation_is_not_an_incomplete_tool_event(self):
        """"Being denied inside its own workspace" is a different fact.

        ``churn_verdict`` charges a failed mutation to its own counter and never
        to the stall budget, and the two must not be conflated on the receipt.
        """
        result = _metrics([_mutate("error"), _mutate("error")])
        self.assertEqual(result["incomplete_tool_events"], 0)
        self.assertEqual(result["failed_mutation_runs"], 0)  # a run of two
        self.assertEqual(result["max_steps_without_mutation"], 0)
        self.assertEqual(result["tool_events"], 0)

    def test_an_incomplete_non_mutation_event_spends_no_step(self):
        """V5-M9 died on this three times: the harness failing, not the worker
        circling. A refused bash and a grep over ripgrep's record limit must not
        exhaust the budget meant to catch a worker going in circles."""
        result = _metrics([_step("error")] * 10)
        self.assertEqual(result["max_steps_without_mutation"], 0)
        self.assertEqual(result["incomplete_tool_events"], 10)
        self.assertEqual(result["tool_events"], 0)
        # Nor does an incomplete call interrupt a run that surrounds it.
        result = _metrics([_step(), _step("error"), _step()])
        self.assertEqual(result["max_steps_without_mutation"], 2)
        self.assertEqual(result["incomplete_tool_events"], 1)

    def test_statuses_other_than_error_are_also_incomplete(self):
        # The rule is ``status != "completed"``, not ``status == "error"``: a
        # stream truncated by the verdict's own terminate leaves the last call
        # ``running`` or ``pending``.
        result = _metrics([_step("running"), _step("pending"), _step(None)])
        self.assertEqual(result["incomplete_tool_events"], 3)
        self.assertEqual(result["max_steps_without_mutation"], 0)
        self.assertEqual(_metrics([_mutate("running")])["failed_mutation_runs"], 0)
        self.assertEqual(_metrics([_mutate("running")])["incomplete_tool_events"], 0)

    def test_reads_are_keyed_on_the_file_path(self):
        result = _metrics(
            [_read("a.py"), _read("b.py"), _read("a.py"), _read("a.py")]
        )
        self.assertEqual(result["max_repeated_reads"], 3)
        self.assertEqual(result["most_read_path"], "a.py")
        self.assertEqual(result["distinct_paths_read"], 2)

    def test_a_read_with_no_path_is_not_counted(self):
        result = _metrics([_read(None), _read(None), _read(None)])
        self.assertEqual(result["max_repeated_reads"], 0)
        self.assertIsNone(result["most_read_path"])
        self.assertEqual(result["distinct_paths_read"], 0)
        # It is still a completed tool step, exactly as in ``churn_verdict``.
        self.assertEqual(result["max_steps_without_mutation"], 3)
        self.assertEqual(result["tool_events"], 3)

    def test_an_incomplete_read_is_not_counted_as_a_read(self):
        # ``churn_verdict`` reaches its read bookkeeping only past the
        # ``status != "completed"`` skip, so a denied read of an external path
        # never lands in its dict.
        result = _metrics([_read("a.py", "error")] * 5)
        self.assertEqual(result["max_repeated_reads"], 0)
        self.assertEqual(result["distinct_paths_read"], 0)
        self.assertIsNone(result["most_read_path"])
        self.assertEqual(result["incomplete_tool_events"], 5)

    def test_repeated_reads_are_counted_anywhere_in_the_stream(self):
        """The verdict's dict is never cleared -- not by a mutation, not by
        distance. Four reads of one path separated by writes are four reads."""
        events = [
            _read("a.py"),
            _mutate(),
            _read("b.py"),
            _read("a.py"),
            _mutate(),
            _step(),
            _read("a.py"),
        ]
        result = _metrics(events)
        self.assertEqual(result["max_repeated_reads"], 3)
        self.assertEqual(result["most_read_path"], "a.py")
        self.assertEqual(result["distinct_paths_read"], 2)

    def test_a_tie_names_a_path_that_actually_reached_the_maximum(self):
        # No tie-break order is pinned; naming a path that did not reach the
        # maximum, or naming none at all, is what is forbidden.
        result = _metrics([_read("a.py"), _read("b.py"), _read("a.py"), _read("b.py")])
        self.assertEqual(result["max_repeated_reads"], 2)
        self.assertIn(result["most_read_path"], {"a.py", "b.py"})
        self.assertEqual(result["distinct_paths_read"], 2)

    def test_failed_mutation_runs_counts_runs_not_failures(self):
        # A run of five denied writes is the single fact "the worker cannot
        # write here", reported once -- the condition ``churn_verdict`` calls
        # ``worker_cannot_write``.
        self.assertEqual(_metrics([_mutate("error")] * 5)["failed_mutation_runs"], 1)
        self.assertEqual(_metrics([_mutate("error")] * 3)["failed_mutation_runs"], 1)
        self.assertEqual(_metrics([_mutate("error")] * 2)["failed_mutation_runs"], 0)

    def test_only_a_completed_mutation_ends_a_run_of_failed_attempts(self):
        """``churn_verdict`` resets ``failed_mutations`` on a completed mutation
        and nowhere else, so reads and greps between denied writes do not break
        the run. Counting them as a break would let a worker that is being
        denied look healthy by reading between attempts."""
        interleaved = [
            _mutate("error"),
            _read("a.py"),
            _mutate("error"),
            _step(),
            _step("error"),
            _mutate("error"),
        ]
        self.assertEqual(_metrics(interleaved)["failed_mutation_runs"], 1)
        # A completed mutation does break it: two runs of two, not one of four.
        broken = [_mutate("error")] * 2 + [_mutate()] + [_mutate("error")] * 2
        self.assertEqual(_metrics(broken)["failed_mutation_runs"], 0)
        # ... and two runs that each reach three are two.
        two = (
            [_mutate("error")] * 3
            + [_mutate(), _step()]
            + [_mutate("error")] * 4
        )
        self.assertEqual(_metrics(two)["failed_mutation_runs"], 2)

    def test_the_four_categories_partition_the_tool_use_events(self):
        """``tool_events`` is the completed events -- mutations included, since
        the verdict considers those too. Failed mutations and incomplete
        non-mutation calls sit in their own counters and in neither of those."""
        events = (
            [_step(), _read("a.py"), _mutate()]          # 3 completed
            + [_mutate("error")] * 4                      # failed mutations
            + [_step("error"), _read("b.py", "error")]    # incomplete
        )
        result = _metrics(events)
        self.assertEqual(result["tool_events"], 3)
        self.assertEqual(result["completed_mutations"], 1)
        self.assertEqual(result["incomplete_tool_events"], 2)
        self.assertEqual(result["failed_mutation_runs"], 1)
        # Completed non-mutation steps are exactly the ones the verdict charges
        # to the stall budget.
        self.assertEqual(result["tool_events"] - result["completed_mutations"], 2)


class MaximumNotTheFinalRunTests(unittest.TestCase):
    """The most likely wrong implementation, given its own class.

    Reporting ``steps_since_mutation`` as it stood at the end of the stream --
    rather than its high-water mark -- passes every other test in this file and
    is silently wrong on precisely the streams worth measuring. A worker that
    circled nineteen times and then finally wrote would report 0, and the whole
    point of the row (seeing "close to the limit" before it becomes a stop)
    would be lost with no symptom at all.
    """

    def test_a_run_ended_by_a_mutation_still_reports_its_height(self):
        events = [_step()] * 19 + [_mutate()]
        result = _metrics(events)
        self.assertEqual(result["max_steps_without_mutation"], 19)

    def test_the_highest_of_several_runs_wins_not_the_last(self):
        events = (
            [_step()] * 3
            + [_mutate()]
            + [_step()] * 9      # the high-water mark
            + [_mutate()]
            + [_step()] * 2      # the value at the end
        )
        result = _metrics(events)
        self.assertEqual(result["max_steps_without_mutation"], 9)

    def test_the_maximum_survives_a_stream_ending_in_a_mutation_burst(self):
        events = [_step()] * 7 + [_mutate()] * 4
        self.assertEqual(_metrics(events)["max_steps_without_mutation"], 7)
        self.assertEqual(_metrics(events)["completed_mutations"], 4)

    def test_the_final_run_and_the_maximum_are_pinned_apart(self):
        # Belt and braces: a stub returning the final run gives 0 here, and a
        # stub returning the total completed step count gives 12.
        events = [_step()] * 5 + [_mutate()] + [_step()] * 7 + [_mutate()]
        self.assertEqual(_metrics(events)["max_steps_without_mutation"], 7)


class ArgumentIsAnyIterableConsumedOnceTests(unittest.TestCase):
    """``events`` is any iterable of events, drained exactly once.

    ``worker_totals`` and ``build_scorecard`` each had to be widened after
    asking a generator for a length or looping it twice. A third is not allowed
    in, so the shape of the argument is pinned here rather than assumed.
    """

    EVENTS = [
        _read("a.py"),
        _step(),
        _read("a.py"),
        _mutate(),
        _step("error"),
        _mutate("error"),
        _read("a.py"),
    ]

    def _expected(self):
        return _metrics(list(self.EVENTS))

    def test_a_generator_totals_identically_to_a_list(self):
        expected = self._expected()
        self.assertEqual(_metrics(event for event in self.EVENTS), expected)

    def test_a_one_shot_iterator_totals_identically_to_a_list(self):
        expected = self._expected()
        self.assertEqual(_metrics(iter(self.EVENTS)), expected)

    def test_a_tuple_totals_identically_to_a_list(self):
        self.assertEqual(_metrics(tuple(self.EVENTS)), self._expected())

    def test_the_iterable_is_started_exactly_once(self):
        source = _CountingIterable(self.EVENTS)
        result = _metrics(source)
        self.assertEqual(source.starts, 1)
        self.assertEqual(result, self._expected())

    def test_an_empty_generator_matches_the_empty_list(self):
        self.assertEqual(_metrics(iter([])), _metrics([]))


def _clean_stream():
    return [_read("a.py"), _step(), _mutate(), _read("b.py"), _mutate()]


#: ``(name, events, limits, expected verdict reason or None)``.
#:
#: Clean, exactly at the limit, one over, far over, breaching both in either
#: order, and breaching after a ``worker_cannot_write`` run. Every case is
#: checked in both directions: the verdict's reason against the table, and the
#: metrics against the verdict.
AGREEMENT_TABLE = [
    ("clean", _clean_stream(), _limits(12, 4), None),
    ("steps exactly at the limit", [_step()] * 4, _limits(4, 4), None),
    ("steps one over", [_step()] * 5, _limits(4, 4), "churn_no_mutation"),
    ("steps far over", [_step()] * 20, _limits(4, 4), "churn_no_mutation"),
    ("reads exactly at the limit", [_read("a.py")] * 4, _limits(50, 4), None),
    ("reads one over", [_read("a.py")] * 5, _limits(50, 4), "churn_repeated_reads"),
    ("reads far over", [_read("a.py")] * 12, _limits(50, 4), "churn_repeated_reads"),
    (
        # Both breach on the same event; the verdict checks the step budget
        # before the read tally, so the step reason is the one reported.
        "both breached, steps first",
        [_read("a.py")] * 3,
        _limits(2, 2),
        "churn_no_mutation",
    ),
    (
        # Reads breach early and the verdict returns there, so it never sees the
        # sixty steps that follow. The metrics do -- and must still agree about
        # which thresholds were crossed.
        "both breached, reads first",
        [_read("a.py")] * 2 + [_step()] * 60,
        _limits(50, 1),
        "churn_repeated_reads",
    ),
    (
        # ``worker_cannot_write`` returns first and pre-empts a step breach that
        # the metrics still record.
        "cannot write pre-empts a step breach",
        [_mutate("error")] * 3 + [_step()] * 20,
        _limits(4, 4),
        "worker_cannot_write",
    ),
    (
        # Two denied writes never reach the ``worker_cannot_write`` condition,
        # so the step breach is reported and no run is counted.
        "failed writes below the run threshold",
        [_mutate("error")] * 2 + [_step()] * 10,
        _limits(4, 4),
        "churn_no_mutation",
    ),
    (
        # Denied writes interleaved with steps: the run still reaches three, and
        # the incomplete steps in between spend no budget.
        "cannot write across interleaved steps",
        [_mutate("error"), _step("error"), _mutate("error"), _step("error"),
         _mutate("error")],
        _limits(2, 2),
        "worker_cannot_write",
    ),
    (
        # Ten harness failures and nothing else: no breach of anything.
        "incomplete calls breach nothing",
        [_step("error")] * 10,
        _limits(2, 2),
        None,
    ),
    (
        "a long run rescued by a mutation still breached at its height",
        [_step()] * 6 + [_mutate()] + [_step()],
        _limits(4, 4),
        "churn_no_mutation",
    ),
]


class MetricsAgreeWithTheVerdictTests(unittest.TestCase):
    """The property that matters most: the counters explain the guard.

    ``churn_verdict`` returns at the first breach and stops counting, so where a
    stream breaches, ``max_steps_without_mutation`` and ``max_repeated_reads``
    may exceed the figure the verdict reported. What must hold is the threshold
    crossing, not the printed number. ``worker_cannot_write`` returns first, so
    it can pre-empt a breach the metrics record; that is accommodated explicitly
    below rather than by relaxing what is asserted.
    """

    def test_the_table_is_not_vacuous(self):
        """Each case fires the reason it says it does, so the agreement checks
        below are exercised against real stops and real clean runs."""
        for name, events, limits, expected in AGREEMENT_TABLE:
            with self.subTest(case=name):
                stop = dispatch.churn_verdict(list(events), limits)
                self.assertEqual(None if stop is None else stop[0], expected)
        reasons = {expected for _, _, _, expected in AGREEMENT_TABLE}
        self.assertEqual(
            reasons,
            {None, "churn_no_mutation", "churn_repeated_reads", "worker_cannot_write"},
        )

    def test_a_clean_verdict_means_no_metric_exceeds_its_limit(self):
        for name, events, limits, _ in AGREEMENT_TABLE:
            with self.subTest(case=name):
                stop = dispatch.churn_verdict(list(events), limits)
                result = _metrics(list(events))
                breached = (
                    result["max_steps_without_mutation"]
                    > limits["max_reasoning_steps_without_mutation"]
                    or result["max_repeated_reads"]
                    > limits["max_repeated_reads_per_path"]
                    or result["failed_mutation_runs"] > 0
                )
                self.assertEqual(stop is None, not breached)

    def test_a_reason_the_verdict_fires_is_a_limit_the_metrics_exceed(self):
        """verdict -> metric, unconditionally. If the guard stopped a worker for
        circling, the receipt must show a run above the limit; anything else and
        the receipt contradicts the stop on the same run."""
        for name, events, limits, expected in AGREEMENT_TABLE:
            with self.subTest(case=name):
                result = _metrics(list(events))
                if expected == "churn_no_mutation":
                    self.assertGreater(
                        result["max_steps_without_mutation"],
                        limits["max_reasoning_steps_without_mutation"],
                    )
                elif expected == "churn_repeated_reads":
                    self.assertGreater(
                        result["max_repeated_reads"],
                        limits["max_repeated_reads_per_path"],
                    )
                elif expected == "worker_cannot_write":
                    self.assertGreaterEqual(result["failed_mutation_runs"], 1)

    def test_a_metric_over_its_limit_means_the_verdict_fired(self):
        """metric -> verdict. The converse direction, modulo pre-emption: a
        breach the metrics see always produces *a* stop, and produces its own
        reason unless an earlier breach in stream order claimed the return."""
        earlier = {"worker_cannot_write", "churn_repeated_reads", "churn_no_mutation"}
        for name, events, limits, expected in AGREEMENT_TABLE:
            with self.subTest(case=name):
                result = _metrics(list(events))
                if (
                    result["max_steps_without_mutation"]
                    > limits["max_reasoning_steps_without_mutation"]
                ):
                    self.assertIsNotNone(expected)
                    self.assertIn(expected, earlier)
                if (
                    result["max_repeated_reads"]
                    > limits["max_repeated_reads_per_path"]
                ):
                    self.assertIsNotNone(expected)
                    self.assertIn(expected, earlier)

    def test_the_metrics_agree_at_the_point_the_verdict_stopped(self):
        """The honest form of "they may differ", stated without reading a message.

        Truncate each breaching stream to the shortest prefix on which the
        verdict fires -- that is exactly what the verdict saw. On that prefix the
        metric already exceeds the limit, and on the full stream it is at least
        as large. It may be larger, because the verdict stopped counting; it may
        never be smaller, which would mean the metric missed a run the guard had
        already seen.
        """
        for name, events, limits, expected in AGREEMENT_TABLE:
            if expected not in {"churn_no_mutation", "churn_repeated_reads"}:
                continue
            with self.subTest(case=name):
                metric, limit = (
                    ("max_steps_without_mutation",
                     limits["max_reasoning_steps_without_mutation"])
                    if expected == "churn_no_mutation"
                    else ("max_repeated_reads",
                          limits["max_repeated_reads_per_path"])
                )
                prefix = next(
                    events[: n + 1]
                    for n in range(len(events))
                    if dispatch.churn_verdict(events[: n + 1], limits) is not None
                )
                self.assertGreater(_metrics(list(prefix))[metric], limit)
                self.assertGreaterEqual(
                    _metrics(list(events))[metric], _metrics(list(prefix))[metric]
                )

    def test_far_over_shows_the_whole_stream_not_the_stopping_point(self):
        """Where the verdict returned at the fifth step, the metrics report
        twenty. This is the trend signal the row exists for -- "just over" and
        "far past" must not look the same on the receipt."""
        events = [_step()] * 20
        limits = _limits(4, 4)
        stop = dispatch.churn_verdict(list(events), limits)
        assert stop is not None
        self.assertEqual(stop[0], "churn_no_mutation")
        # The verdict returns on the fifth step and sees no more of the stream.
        self.assertIsNone(dispatch.churn_verdict(events[:4], limits))
        self.assertIsNotNone(dispatch.churn_verdict(events[:5], limits))
        self.assertEqual(_metrics(events)["max_steps_without_mutation"], 20)

    def test_at_the_limit_and_nowhere_near_it_are_distinguishable(self):
        """The defect this row closes: both runs carry ``churn_stop: None``, so
        without these counters the receipt cannot tell them apart."""
        limits = _limits(12, 4)
        at_limit = [_read("a.py")] * 4 + [_mutate()]
        nowhere_near = [_read("a.py"), _mutate()]
        self.assertIsNone(dispatch.churn_verdict(list(at_limit), limits))
        self.assertIsNone(dispatch.churn_verdict(list(nowhere_near), limits))
        self.assertEqual(_metrics(at_limit)["max_repeated_reads"], 4)
        self.assertEqual(_metrics(nowhere_near)["max_repeated_reads"], 1)
        self.assertNotEqual(_metrics(at_limit), _metrics(nowhere_near))


if __name__ == "__main__":
    unittest.main()
