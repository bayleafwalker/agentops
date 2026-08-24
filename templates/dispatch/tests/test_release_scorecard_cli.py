"""Coordinator-authored oracle for ``release_scorecard.py`` -- the I/O shell.

T-6a pinned the frontier reduction, T-6b the worker half, T-6c the assembly
(``build_scorecard``). All three are pure: they take lists and return a dict.
This packet adds the shell that makes a scorecard producible by running one
command, and nothing else:

* ``load_sink_rows(path)``   -- read the Stop-hook JSON-lines sink
* ``load_receipts(root)``    -- read ``<root>/<task>/receipt.json``
* ``filter_by_window(records, start, end, key)`` -- half-open ``[start, end)``
* ``filter_by_project(rows, project)`` -- scope the shared sink to one repo
* ``main(argv)``             -- wire the four together and write the scorecard

The sink is GLOBAL: the Stop hook appends to
``/projects/dev/.claude/session-costs.jsonl`` from every repository on the
machine, so without ``--project`` an agentops release counts whatever else ran
in the same window. ``main`` also writes a ``scope`` block recording the
project and the window it used -- a scorecard that does not say what it counted
cannot be compared with another one. ``filter_by_project`` and ``scope`` are
pinned in detail by ``test_release_scorecard_scope.py``; this file pins them
where they meet the shell.

Three properties are load-bearing and are asserted directly:

* the readers are TOLERANT. The sink is appended to by a shell hook on every
  assistant turn; one truncated line from an interrupted write must not cost a
  release its whole scorecard. A corrupt line is skipped, never fatal.
* ``load_receipts`` is ORDERED. Sorting by ``task_id`` is what makes a
  scorecard reproducible rather than filesystem-order dependent.
* ``main`` DELEGATES. The file it writes must equal ``build_scorecard`` called
  directly with the same loaded inputs. A CLI that re-totals its own way is
  exactly how the two paths drift apart -- and how the quadratic bug T-6a
  exists to prevent walks back in through a second door.

The window is half-open. A record exactly at ``end`` belongs to the next
release, not this one; counting it in both is how two adjacent scorecards
silently double-count a task.

Nothing here shells out to git or resolves tags -- the window is given, not
discovered. Real files under ``tempfile.TemporaryDirectory`` are used
throughout: this packet is about I/O, so a mocked filesystem would test
nothing.

Written against the packet spec only. ``release_scorecard.py`` exists and
carries the T-6a/T-6b/T-6c functions, but none of the four above -- so this
oracle fails at attribute lookup. That is the declared red.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
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


scorecard = _load_module("release_scorecard_cli_subject",
                         SCRIPTS / "release_scorecard.py")


#: Three sink rows, three distinct sessions, one per third of the window. Each
#: is a whole cumulative snapshot the way the Stop hook really writes them.
SINK_ROWS = (
    {"ts": "2026-08-24T10:00:00Z", "session": "loop-early",
     "model": "claude-opus-5", "out": 120, "cost_usd": 1.0, "turns": 1,
     "assistant_msgs": 2, "tool_calls": 1, "duration_s": 22,
     "rework_rounds": 0},
    {"ts": "2026-08-24T10:05:00Z", "session": "loop-mid",
     "model": "claude-opus-5", "out": 310, "cost_usd": 2.0, "turns": 4,
     "assistant_msgs": 7, "tool_calls": 6, "duration_s": 140,
     "rework_rounds": 1},
    {"ts": "2026-08-24T10:10:00Z", "session": "loop-late",
     "model": "claude-opus-5", "out": 505, "cost_usd": 4.0, "turns": 8,
     "assistant_msgs": 14, "tool_calls": 12, "duration_s": 305,
     "rework_rounds": 2},
)

#: The window used by the bounded run. ``10:10:00Z`` is BOTH the ``--until``
#: and the ts of "loop-late", so the half-open rule decides whether the late
#: session lands in this release or the next one.
SINCE = "2026-08-24T10:03:00Z"
UNTIL = "2026-08-24T10:10:00Z"


def _receipt(task_id, recorded_at, cost_usd, tokens, attempt=1,
             cost_reported=True, passed=True):
    """A receipt shaped like docs/evidence/receipts/<task>/receipt.json.

    The spend the worker reports lives under driver_steps -> the "run" entry ->
    receipt -> spend; T-6b pins that lift. This oracle only needs receipts real
    enough that ``worker_totals`` reads them the same way it will in
    production, plus the top-level ``recorded_at`` the window filters on.
    """
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "task_id": task_id,
        "repo_id": "agentops",
        "attempt": attempt,
        "recorded_at": recorded_at,
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
        ],
        "gate": {"evidence": {"gates": {"diff-nonempty": True},
                              "passed": passed}},
    }


#: Three receipts. Their task ids sort in an order deliberately unrelated to
#: both their recorded_at order and the order the directories get created in.
RECEIPT_EARLY = _receipt("V5-M02-alpha", "2026-08-24T10:01:00Z", 0.020864,
                         292309)
RECEIPT_MID = _receipt("V5-M11-bravo", "2026-08-24T10:06:00Z", 0.011111,
                       140002)
RECEIPT_LATE = _receipt("V5-M30-charlie", "2026-08-24T10:11:00Z", 0.000004,
                        61, attempt=2)
RECEIPTS = (RECEIPT_EARLY, RECEIPT_MID, RECEIPT_LATE)

#: Two escalations, both inside the bounded window, so that whether the shell
#: also filters escalations (the spec bounds the sink and the receipts only)
#: cannot change any assertion here.
ESCALATIONS = (
    {"type": "workflow.escalation", "actor": "dispatch-release",
     "summary": "task V5-M11-bravo escalated to frontier",
     "detail": "gate evidence empty after attempt 2",
     "metadata": {"task_id": "V5-M11-bravo", "repo_id": "agentops",
                  "step": "gate", "exit_code": 1, "driver": "opencode",
                  "stop_condition": "diff-empty"},
     "recorded_at": "2026-08-24T10:04:00Z"},
    {"type": "workflow.escalation", "actor": "dispatch-release",
     "summary": "task V5-M02-alpha escalated to frontier",
     "detail": "worker exceeded its cap",
     "metadata": {"task_id": "V5-M02-alpha", "repo_id": "agentops",
                  "step": "run", "exit_code": 2, "driver": "opencode",
                  "stop_condition": "cap-exceeded"},
     "recorded_at": "2026-08-24T10:07:00Z"},
)


#: A sink the way the real one looks: shared by every repository on the
#: machine. Two agentops sessions, one sibling ``agentops-web`` session, and
#: one row written before the field existed and so carrying no ``project`` at
#: all. Scoping to "agentops" must keep the first two only.
PROJECT_SINK_ROWS = (
    {"ts": "2026-08-24T10:00:00Z", "session": "loop-ours-1",
     "project": "agentops", "model": "claude-opus-5", "out": 120,
     "cost_usd": 1.0, "turns": 1, "assistant_msgs": 2, "tool_calls": 1,
     "duration_s": 22, "rework_rounds": 0},
    {"ts": "2026-08-24T10:05:00Z", "session": "loop-sibling",
     "project": "agentops-web", "model": "claude-opus-5", "out": 310,
     "cost_usd": 8.0, "turns": 4, "assistant_msgs": 7, "tool_calls": 6,
     "duration_s": 140, "rework_rounds": 1},
    {"ts": "2026-08-24T10:06:00Z", "session": "loop-ours-2",
     "project": "agentops", "model": "claude-opus-5", "out": 200,
     "cost_usd": 2.0, "turns": 3, "assistant_msgs": 4, "tool_calls": 3,
     "duration_s": 60, "rework_rounds": 0},
    {"ts": "2026-08-24T10:07:00Z", "session": "loop-unlabelled",
     "model": "claude-opus-5", "out": 90, "cost_usd": 16.0, "turns": 2,
     "assistant_msgs": 3, "tool_calls": 2, "duration_s": 40,
     "rework_rounds": 0},
)

#: The frontier cost of PROJECT_SINK_ROWS scoped to "agentops" (1.0 + 2.0) and
#: unscoped (all four sessions), by hand.
PROJECT_SCOPED_COST = 3.0
PROJECT_UNSCOPED_COST = 27.0


def _write_lines(path: Path, records) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def _write_receipts(root: Path, receipts) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for receipt in receipts:
        task_dir = root / receipt["task_id"]
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "receipt.json").write_text(
            json.dumps(receipt), encoding="utf-8",
        )
    return root


class TempDirTestCase(unittest.TestCase):
    """Every case gets a real directory; this packet is about real I/O."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


class LoadSinkRowsTests(TempDirTestCase):

    def test_a_clean_sink_round_trips_in_order(self):
        path = _write_lines(self.tmp / "session-costs.jsonl", SINK_ROWS)
        self.assertEqual(
            scorecard.load_sink_rows(str(path)), list(SINK_ROWS),
            "a clean JSON-lines sink did not round-trip to its rows in order",
        )

    def test_a_truncated_line_is_skipped_not_fatal(self):
        """The whole reason the reader is tolerant.

        The sink is appended to by a shell hook on every assistant turn. An
        interrupted write leaves half a line behind, and that half line must
        not cost the release its entire scorecard.
        """
        path = self.tmp / "session-costs.jsonl"
        path.write_text(
            json.dumps(SINK_ROWS[0]) + "\n"
            + '{"ts": "2026-\n'
            + json.dumps(SINK_ROWS[1]) + "\n",
            encoding="utf-8",
        )
        load = scorecard.load_sink_rows  # missing attribute is an error, not this
        try:
            rows = load(str(path))
        except Exception as exc:  # noqa: BLE001 -- the point of the test
            self.fail(
                "a truncated sink line raised "
                f"{type(exc).__name__}: {exc} -- one interrupted hook write "
                "must not cost a release its whole scorecard",
            )
        self.assertEqual(
            rows, [SINK_ROWS[0], SINK_ROWS[1]],
            "the truncated line was not skipped, or took its good neighbours "
            "with it",
        )

    def test_blank_bad_and_non_dict_lines_are_all_skipped(self):
        path = self.tmp / "session-costs.jsonl"
        path.write_text(
            "\n"
            "   \n"
            '{"ts": "2026-\n'
            "42\n"
            + json.dumps(SINK_ROWS[0]) + "\n",
            encoding="utf-8",
        )
        rows = scorecard.load_sink_rows(str(path))
        self.assertEqual(
            rows, [SINK_ROWS[0]],
            "only the one valid row must survive a sink carrying a blank "
            "line, a whitespace line, a truncated line and a bare number",
        )

    def test_a_json_list_line_is_not_a_row(self):
        path = self.tmp / "session-costs.jsonl"
        path.write_text(
            "[1, 2, 3]\n" + json.dumps(SINK_ROWS[0]) + "\n", encoding="utf-8",
        )
        self.assertEqual(
            scorecard.load_sink_rows(str(path)), [SINK_ROWS[0]],
            "a line that parsed to a list was kept -- a row must be a dict",
        )

    def test_a_missing_sink_returns_an_empty_list(self):
        missing = self.tmp / "no-such-dir" / "session-costs.jsonl"
        load = scorecard.load_sink_rows  # missing attribute is an error, not this
        try:
            rows = load(str(missing))
        except Exception as exc:  # noqa: BLE001 -- the point of the test
            self.fail(
                f"a missing sink raised {type(exc).__name__}: {exc} -- it "
                "must return [] instead",
            )
        self.assertEqual(rows, [], "a missing sink is not an empty list")

    def test_an_empty_sink_returns_an_empty_list(self):
        path = self.tmp / "session-costs.jsonl"
        path.write_text("", encoding="utf-8")
        self.assertEqual(
            scorecard.load_sink_rows(str(path)), [],
            "an empty sink file is not an empty list",
        )


class LoadReceiptsTests(TempDirTestCase):

    def test_receipts_come_back_sorted_by_task_id(self):
        """Reproducibility, not filesystem order.

        The directories are created newest-task-first so that any reader
        relying on creation or directory order returns a different list.
        """
        root = _write_receipts(self.tmp / "receipts",
                               (RECEIPT_LATE, RECEIPT_EARLY, RECEIPT_MID))
        receipts = scorecard.load_receipts(str(root))
        self.assertEqual(
            [r["task_id"] for r in receipts],
            ["V5-M02-alpha", "V5-M11-bravo", "V5-M30-charlie"],
            "receipts are not sorted by task_id -- a scorecard built from "
            "them is filesystem-order dependent",
        )
        self.assertEqual(
            receipts, [RECEIPT_EARLY, RECEIPT_MID, RECEIPT_LATE],
            "the parsed receipts are not the receipts that were written",
        )

    def test_a_corrupt_receipt_is_skipped_and_the_rest_survive(self):
        root = _write_receipts(self.tmp / "receipts",
                               (RECEIPT_EARLY, RECEIPT_MID))
        broken = root / "V5-M99-broken"
        broken.mkdir(parents=True, exist_ok=True)
        (broken / "receipt.json").write_text(
            '{"task_id": "V5-M99-broken", "driver_ste', encoding="utf-8",
        )
        load = scorecard.load_receipts  # missing attribute is an error, not this
        try:
            receipts = load(str(root))
        except Exception as exc:  # noqa: BLE001 -- the point of the test
            self.fail(
                f"a corrupt receipt raised {type(exc).__name__}: {exc} -- it "
                "must be skipped, not fatal",
            )
        self.assertEqual(
            receipts, [RECEIPT_EARLY, RECEIPT_MID],
            "the corrupt receipt was not skipped, or took its neighbours "
            "with it",
        )

    def test_a_task_directory_without_a_receipt_is_skipped(self):
        root = _write_receipts(self.tmp / "receipts", (RECEIPT_EARLY,))
        (root / "V5-M77-nothing-yet").mkdir(parents=True, exist_ok=True)
        (root / "V5-M78-other-files").mkdir(parents=True, exist_ok=True)
        (root / "V5-M78-other-files" / "notes.md").write_text(
            "no receipt here", encoding="utf-8",
        )
        self.assertEqual(
            scorecard.load_receipts(str(root)), [RECEIPT_EARLY],
            "a task directory carrying no receipt.json was not skipped",
        )

    def test_a_missing_root_returns_an_empty_list(self):
        missing = self.tmp / "no-such-receipts-root"
        load = scorecard.load_receipts  # missing attribute is an error, not this
        try:
            receipts = load(str(missing))
        except Exception as exc:  # noqa: BLE001 -- the point of the test
            self.fail(
                f"a missing receipts root raised {type(exc).__name__}: {exc} "
                "-- it must return [] instead",
            )
        self.assertEqual(
            receipts, [], "a missing receipts root is not an empty list",
        )

    def test_an_empty_root_returns_an_empty_list(self):
        root = self.tmp / "receipts"
        root.mkdir(parents=True, exist_ok=True)
        self.assertEqual(
            scorecard.load_receipts(str(root)), [],
            "an empty receipts root is not an empty list",
        )


class FilterByWindowTests(unittest.TestCase):

    RECORDS = (
        {"id": "before", "ts": "2026-08-24T09:59:59Z"},
        {"id": "at-start", "ts": "2026-08-24T10:00:00Z"},
        {"id": "inside", "ts": "2026-08-24T10:05:00Z"},
        {"id": "at-end", "ts": "2026-08-24T10:10:00Z"},
        {"id": "after", "ts": "2026-08-24T10:10:01Z"},
    )
    START = "2026-08-24T10:00:00Z"
    END = "2026-08-24T10:10:00Z"

    def _ids(self, records, start, end, key="ts"):
        return [r["id"] for r in
                scorecard.filter_by_window(list(records), start, end, key)]

    def test_the_window_is_inclusive_at_start(self):
        self.assertIn(
            "at-start", self._ids(self.RECORDS, self.START, self.END),
            "a record exactly at start was dropped -- the window is "
            "half-open [start, end), inclusive at the lower bound",
        )

    def test_the_window_is_exclusive_at_end(self):
        """The boundary that silently double-counts a release otherwise.

        A record stamped exactly at ``end`` is the first record of the NEXT
        release. Counting it in both scorecards inflates them both.
        """
        kept = self._ids(self.RECORDS, self.START, self.END)
        self.assertNotIn(
            "at-end", kept,
            "a record exactly at end was kept -- it belongs to the next "
            "release, and counting it here double-counts it",
        )
        self.assertEqual(
            kept, ["at-start", "inside"],
            "the half-open window [start, end) did not keep exactly the "
            "records at and after start and strictly before end",
        )

    def test_a_none_start_means_no_lower_bound(self):
        self.assertEqual(
            self._ids(self.RECORDS, None, self.END),
            ["before", "at-start", "inside"],
            "a None start did not mean 'no lower bound'",
        )

    def test_a_none_end_means_no_upper_bound(self):
        self.assertEqual(
            self._ids(self.RECORDS, self.START, None),
            ["at-start", "inside", "at-end", "after"],
            "a None end did not mean 'no upper bound'",
        )

    def test_both_bounds_none_keeps_everything(self):
        self.assertEqual(
            self._ids(self.RECORDS, None, None),
            [r["id"] for r in self.RECORDS],
            "an unbounded window did not keep every record",
        )

    def test_a_record_missing_the_key_is_excluded(self):
        records = list(self.RECORDS) + [{"id": "no-ts"}]
        self.assertNotIn(
            "no-ts", self._ids(records, self.START, self.END),
            "a record with no timestamp was kept -- a record that cannot be "
            "placed in time cannot be attributed to a release",
        )
        self.assertNotIn(
            "no-ts", self._ids(records, None, None),
            "a record with no timestamp was kept even on an unbounded window "
            "-- it is unattributable regardless of the bounds",
        )

    def test_a_record_whose_key_is_not_a_string_is_excluded(self):
        records = list(self.RECORDS) + [
            {"id": "numeric-ts", "ts": 1756029600},
            {"id": "null-ts", "ts": None},
        ]
        kept = self._ids(records, self.START, self.END)
        self.assertNotIn(
            "numeric-ts", kept,
            "a record whose timestamp was a number was kept -- it cannot be "
            "compared against an ISO-8601 bound",
        )
        self.assertNotIn(
            "null-ts", kept, "a record whose timestamp was null was kept",
        )
        self.assertEqual(
            self._ids(records, None, None), ["before", "at-start", "inside",
                                             "at-end", "after"],
            "the non-string timestamps were kept on an unbounded window",
        )

    def test_the_key_argument_is_honoured(self):
        records = (
            {"id": "a", "ts": "2026-08-24T09:00:00Z",
             "recorded_at": "2026-08-24T10:05:00Z"},
            {"id": "b", "ts": "2026-08-24T10:05:00Z",
             "recorded_at": "2026-08-24T09:00:00Z"},
        )
        self.assertEqual(
            self._ids(records, self.START, self.END, "recorded_at"), ["a"],
            "filter_by_window did not filter on the key it was given",
        )

    def test_it_does_not_mutate_its_input(self):
        records = [dict(r) for r in self.RECORDS]
        before = [dict(r) for r in records]
        scorecard.filter_by_window(records, self.START, self.END, "ts")
        self.assertEqual(
            records, before,
            "filter_by_window mutated the list it was handed",
        )


class MainTests(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.sink = _write_lines(self.tmp / "session-costs.jsonl", SINK_ROWS)
        self.receipts_root = _write_receipts(self.tmp / "receipts", RECEIPTS)
        self.escalations = _write_lines(self.tmp / "escalations.jsonl",
                                        ESCALATIONS)
        self.out = self.tmp / "scorecard.json"

    def _argv(self, out=None, extra=()):
        return [
            "--release", "v5",
            "--sink", str(self.sink),
            "--receipts", str(self.receipts_root),
            "--out", str(out if out is not None else self.out),
        ] + list(extra)

    def _run(self, out=None, extra=()):
        rc = scorecard.main(self._argv(out=out, extra=extra))
        self.assertEqual(
            rc, 0, f"main did not return 0 on a successful run (got {rc!r})",
        )
        return json.loads(Path(out if out is not None else self.out)
                          .read_text(encoding="utf-8"))

    def test_it_writes_exactly_what_build_scorecard_returns(self):
        """The CLI is a shell. It must not invent its own aggregation.

        ``recorded_at`` is the one field main is entitled to originate (the
        spec gives it no flag), so it is checked for shape and then excluded
        from the comparison; every other field must be build_scorecard's --
        including ``scope``, which main builds from --project/--since/--until
        and passes through. This run gives none of the three, so the scope it
        builds is all-None rather than absent.
        """
        written = self._run(extra=["--escalations", str(self.escalations)])
        expected = scorecard.build_scorecard(
            "v5", list(SINK_ROWS), list(RECEIPTS), list(ESCALATIONS),
            written.get("recorded_at"),
            {"project": None, "since": None, "until": None},
        )
        self.assertIsInstance(
            written.get("recorded_at"), str,
            "the scorecard carries no recorded_at string",
        )
        self.assertTrue(
            written["recorded_at"],
            "the scorecard's recorded_at is empty",
        )
        self.assertEqual(
            written, expected,
            "the written scorecard is not build_scorecard's output for the "
            "same loaded inputs -- the CLI re-aggregated its own way, and a "
            "second aggregation is a second thing to drift",
        )

    def test_it_reduces_rather_than_sums_the_sink(self):
        """The quadratic bug must not walk back in through the CLI door."""
        repeated = list(SINK_ROWS) + [
            dict(SINK_ROWS[1], ts="2026-08-24T10:07:00Z", cost_usd=3.0,
                 turns=6, assistant_msgs=9, tool_calls=8, duration_s=200,
                 rework_rounds=2),
        ]
        _write_lines(self.sink, repeated)
        written = self._run()
        self.assertEqual(
            written["frontier"]["sessions"], 3,
            "the two snapshots of session loop-mid were not reduced to one",
        )
        self.assertAlmostEqual(
            written["frontier"]["cost_usd"], 8.0, places=6,
            msg="the frontier cost is not the reduced figure (1.0 + 3.0 + "
                "4.0); summing every row would report 11.0",
        )

    def test_no_escalations_flag_means_an_empty_list_not_an_error(self):
        written = self._run()
        self.assertEqual(
            written["escalations"]["count"], 0,
            "omitting --escalations did not produce a zero escalation count",
        )
        self.assertEqual(
            written["escalations"]["tasks"], [],
            "omitting --escalations did not produce an empty task list",
        )
        self.assertEqual(
            written["escalations"]["stop_conditions"], [],
            "omitting --escalations did not produce empty stop conditions",
        )

    def test_the_escalations_file_is_read_when_given(self):
        written = self._run(extra=["--escalations", str(self.escalations)])
        self.assertEqual(
            written["escalations"]["count"], 2,
            "the escalations file was not read",
        )
        self.assertEqual(
            written["escalations"]["tasks"],
            ["V5-M02-alpha", "V5-M11-bravo"],
            "the escalated task ids are not the distinct ids, sorted",
        )

    def test_it_creates_a_missing_parent_directory_for_out(self):
        nested = self.tmp / "docs" / "evidence" / "scorecards" / "v5.json"
        written = self._run(out=nested)
        self.assertTrue(
            nested.exists(),
            "main did not create the missing parent directory for --out",
        )
        self.assertEqual(
            written["release"], "v5",
            "the scorecard written into the created directory is not the "
            "scorecard",
        )

    def test_the_written_file_is_indent_two_and_ends_with_a_newline(self):
        self._run(extra=["--escalations", str(self.escalations)])
        raw = self.out.read_text(encoding="utf-8")
        self.assertTrue(
            raw.endswith("\n"),
            "the written scorecard does not end with a trailing newline",
        )
        self.assertFalse(
            raw.endswith("\n\n"),
            "the written scorecard ends with more than one newline",
        )
        parsed = json.loads(raw)
        self.assertEqual(
            raw, json.dumps(parsed, indent=2) + "\n",
            "the written scorecard is not json.dumps(..., indent=2) plus one "
            "trailing newline",
        )
        self.assertIn(
            '\n  "release": "v5"', raw,
            "the written scorecard is not indented two spaces",
        )

    def test_since_and_until_bound_the_window(self):
        """The bounded run must be a strictly smaller, different scorecard."""
        unbounded = self._run(extra=["--escalations", str(self.escalations)])
        bounded_out = self.tmp / "scorecard-bounded.json"
        bounded = self._run(
            out=bounded_out,
            extra=["--escalations", str(self.escalations),
                   "--since", SINCE, "--until", UNTIL],
        )
        self.assertNotEqual(
            bounded, unbounded,
            "--since/--until produced the same scorecard as the unbounded "
            "run -- the window was not applied",
        )
        self.assertEqual(
            bounded["frontier"], scorecard.frontier_totals([SINK_ROWS[1]]),
            "the bounded frontier half is not the totals over the single "
            "sink row inside [since, until)",
        )
        self.assertEqual(
            bounded["frontier"]["sessions"], 1,
            "the bounded run kept more than the one in-window session",
        )
        self.assertLess(
            bounded["frontier"]["cost_usd"], unbounded["frontier"]["cost_usd"],
            "the bounded frontier cost is not smaller than the unbounded one",
        )
        self.assertEqual(
            bounded["worker"], scorecard.worker_totals([RECEIPT_MID]),
            "the bounded worker half is not the totals over the single "
            "receipt whose recorded_at is inside [since, until)",
        )
        self.assertEqual(
            bounded["worker"]["tasks"], 1,
            "the bounded run kept more than the one in-window receipt",
        )

    def test_until_is_exclusive_over_the_real_sink(self):
        """The row stamped exactly at --until belongs to the next release."""
        bounded = self._run(extra=["--since", SINCE, "--until", UNTIL])
        self.assertAlmostEqual(
            bounded["frontier"]["cost_usd"], 2.0, places=6,
            msg="the sink row stamped exactly at --until was counted; "
                "--until is exclusive, or two adjacent releases both bill it",
        )

    def test_since_alone_and_until_alone_are_each_a_one_sided_bound(self):
        since_only = self._run(out=self.tmp / "since-only.json",
                               extra=["--since", SINCE])
        self.assertEqual(
            since_only["frontier"], scorecard.frontier_totals(
                [SINK_ROWS[1], SINK_ROWS[2]]),
            "--since alone did not leave the upper bound open",
        )
        until_only = self._run(out=self.tmp / "until-only.json",
                               extra=["--until", UNTIL])
        self.assertEqual(
            until_only["frontier"], scorecard.frontier_totals(
                [SINK_ROWS[0], SINK_ROWS[1]]),
            "--until alone did not leave the lower bound open",
        )

    def test_a_corrupt_sink_line_does_not_cost_the_release_its_scorecard(self):
        with self.sink.open("a", encoding="utf-8") as handle:
            handle.write('{"ts": "2026-08-24T10:12:0\n')
        scorecard.main  # missing attribute is an error, not this test's failure
        try:
            written = self._run()
        except Exception as exc:  # noqa: BLE001 -- the point of the test
            self.fail(
                f"a truncated sink line made main raise {type(exc).__name__}: "
                f"{exc} -- the whole scorecard was lost to one bad line",
            )
        self.assertEqual(
            written["frontier"], scorecard.frontier_totals(list(SINK_ROWS)),
            "the truncated sink line changed the frontier totals",
        )

    def test_an_empty_run_still_writes_a_whole_scorecard(self):
        empty_sink = self.tmp / "empty.jsonl"
        empty_sink.write_text("", encoding="utf-8")
        empty_root = self.tmp / "no-receipts"
        empty_root.mkdir(parents=True, exist_ok=True)
        argv = ["--release", "v5", "--sink", str(empty_sink),
                "--receipts", str(empty_root), "--out",
                str(self.tmp / "empty-scorecard.json")]
        rc = scorecard.main(argv)
        self.assertEqual(rc, 0, "an empty run did not return 0")
        written = json.loads(
            (self.tmp / "empty-scorecard.json").read_text(encoding="utf-8"))
        self.assertEqual(
            written["schema_version"], "workflow-scorecard/v1",
            "the empty scorecard does not carry the schema tag",
        )
        self.assertEqual(
            written["frontier"], scorecard.frontier_totals([]),
            "the empty frontier half is not frontier_totals([])",
        )
        self.assertIn(
            "worker", written,
            "the worker half vanished when there were no receipts",
        )
        self.assertEqual(
            written["worker"], scorecard.worker_totals([]),
            "the empty worker half is not worker_totals([])",
        )


class ProjectScopeTests(TempDirTestCase):
    """``--project`` and the ``scope`` block main writes.

    The sink at ``/projects/dev/.claude/session-costs.jsonl`` is global: the
    Stop hook appends to it from every repository on the machine. Without
    ``--project`` an agentops release counts whatever else happened to run in
    the same window -- on the live run that motivated this, four sessions fell
    inside the window and only some of them were agentops.
    """

    def setUp(self):
        super().setUp()
        self.sink = _write_lines(self.tmp / "session-costs.jsonl",
                                 PROJECT_SINK_ROWS)
        self.receipts_root = _write_receipts(self.tmp / "receipts", RECEIPTS)
        self.out = self.tmp / "scorecard.json"

    def _run(self, out, extra=()):
        argv = [
            "--release", "v5",
            "--sink", str(self.sink),
            "--receipts", str(self.receipts_root),
            "--out", str(out),
        ] + list(extra)
        rc = scorecard.main(argv)
        self.assertEqual(
            rc, 0, f"main did not return 0 (got {rc!r})",
        )
        return json.loads(Path(out).read_text(encoding="utf-8"))

    def test_project_scoping_produces_a_smaller_frontier(self):
        unscoped = self._run(self.tmp / "unscoped.json")
        scoped = self._run(self.tmp / "scoped.json",
                           extra=["--project", "agentops"])
        self.assertLess(
            scoped["frontier"]["cost_usd"], unscoped["frontier"]["cost_usd"],
            "--project did not shrink the frontier half -- the shared sink's "
            "other repositories are still being billed to this release",
        )
        self.assertAlmostEqual(
            unscoped["frontier"]["cost_usd"], PROJECT_UNSCOPED_COST, places=6,
            msg="the unscoped frontier cost is not the whole sink's reduced "
                "survivors",
        )
        self.assertAlmostEqual(
            scoped["frontier"]["cost_usd"], PROJECT_SCOPED_COST, places=6,
            msg="the scoped frontier cost is not the two agentops sessions "
                "only -- 'agentops-web' is a different repository, and the "
                "row carrying no project cannot be attributed to one",
        )
        self.assertEqual(
            scoped["frontier"]["sessions"], 2,
            "the scoped run did not keep exactly the two agentops sessions",
        )
        self.assertEqual(
            scoped["frontier"], scorecard.frontier_totals(
                [PROJECT_SINK_ROWS[0], PROJECT_SINK_ROWS[2]]),
            "the scoped frontier half is not the totals over the agentops "
            "rows alone",
        )

    def test_the_scope_block_records_the_project_and_the_window(self):
        written = self._run(
            self.tmp / "scoped-window.json",
            extra=["--project", "agentops", "--since", SINCE,
                   "--until", UNTIL],
        )
        self.assertEqual(
            written.get("scope"),
            {"project": "agentops", "since": SINCE, "until": UNTIL},
            "the written scorecard does not record what it was built from -- "
            "two scorecards over different windows are not comparable and "
            "nothing in either one says so",
        )

    def test_the_scope_block_is_present_with_nulls_when_no_flag_is_given(self):
        """Absent must not have to be distinguished from unbounded."""
        written = self._run(self.tmp / "bare.json")
        self.assertEqual(
            written.get("scope"),
            {"project": None, "since": None, "until": None},
            "an unscoped run did not write all three scope keys with nulls",
        )

    def test_the_written_file_still_equals_build_scorecard_with_that_scope(self):
        """The shell delegates, scope included."""
        written = self._run(
            self.tmp / "delegated.json",
            extra=["--project", "agentops", "--since", SINCE],
        )
        expected = scorecard.build_scorecard(
            "v5",
            scorecard.filter_by_project(
                scorecard.filter_by_window(list(PROJECT_SINK_ROWS), SINCE,
                                           None, "ts"),
                "agentops"),
            scorecard.filter_by_window(list(RECEIPTS), SINCE, None,
                                       "recorded_at"),
            [],
            written.get("recorded_at"),
            {"project": "agentops", "since": SINCE, "until": None},
        )
        self.assertEqual(
            written, expected,
            "the written scorecard is not build_scorecard's output for the "
            "same loaded, windowed and scoped inputs with the same scope",
        )

    def test_the_project_flag_stays_optional(self):
        written = self._run(self.tmp / "optional.json")
        self.assertEqual(
            written["frontier"], scorecard.frontier_totals(
                list(PROJECT_SINK_ROWS)),
            "omitting --project did not count the whole sink",
        )


if __name__ == "__main__":
    unittest.main()
