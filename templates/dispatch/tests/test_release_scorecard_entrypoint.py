"""Oracle for ``release_scorecard.py`` as a COMMAND, not as a function.

T-6a/T-6b/T-6c pinned the pure computation; T-6d pinned ``main(argv)`` and the
readers. Every one of those oracles calls ``main(argv)`` in process. Run the
file the way the row says a scorecard is produced -- as a command -- and
nothing happens at all::

    $ python templates/dispatch/scripts/release_scorecard.py \
          --release v5 --sink ... --receipts ... --out ...
    $ echo $?
    0            # and no file is written

There is no ``if __name__ == "__main__":`` block, so the module defines its
functions and exits. The row says the scorecard is produced by running a
command; the existing oracles graded a function. This packet closes that gap.

Everything here therefore drives the script through ``subprocess`` with
``[sys.executable, str(script), ...]``. Nothing is imported from it: importing
is exactly the move that hid the missing entry point for four packets.

Three properties are load-bearing:

* the file is RUNNABLE, and its exit status is ``main``'s return value;
* the four required flags are VALIDATED. Today a missing ``--release``
  silently yields ``"release": null`` in a written scorecard, which is worse
  than failing -- a scorecard naming no release gets filed against the wrong
  one. A rejected invocation must also leave NO output file behind: an
  implementation that errors after writing has already corrupted the evidence
  directory;
* the entry point adds NO NONDETERMINISM. Two runs over the same inputs differ
  only in ``recorded_at``.

Error wording is the implementer's to choose: only a non-zero status and a
non-empty stderr are asserted, never a message.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# This oracle is run under strace at freeze time, where a write into the
# repository is a finding. The subject is run in a child process, so the
# child's environment is where it matters (see ``_env``).
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/release_scorecard.py"


#: Two sink rows, two distinct sessions, shaped the way the Stop hook writes
#: them (one cumulative snapshot per assistant turn).
SINK_ROWS = (
    {"ts": "2026-08-24T10:00:00Z", "session": "loop-early",
     "model": "claude-opus-5", "out": 120, "cost_usd": 1.0, "turns": 1,
     "assistant_msgs": 2, "tool_calls": 1, "duration_s": 22,
     "rework_rounds": 0},
    {"ts": "2026-08-24T10:05:00Z", "session": "loop-mid",
     "model": "claude-opus-5", "out": 310, "cost_usd": 2.0, "turns": 4,
     "assistant_msgs": 7, "tool_calls": 6, "duration_s": 140,
     "rework_rounds": 1},
)


def _receipt(task_id, recorded_at, cost_usd, tokens):
    """A receipt shaped like docs/evidence/receipts/<task>/receipt.json."""
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "task_id": task_id,
        "repo_id": "agentops",
        "attempt": 1,
        "recorded_at": recorded_at,
        "route": "mechanical_bulk",
        "harness_model": "opencode-go/deepseek-v4-flash",
        "driver_steps": [
            {"step": "run", "attempt": 1, "exit_code": 0, "stderr": "",
             "receipt": {"spend": {"cost_usd": cost_usd, "tokens": tokens,
                                   "cost_reported": True}}},
        ],
        "gate": {"evidence": {"gates": {"diff-nonempty": True},
                              "passed": True}},
    }


RECEIPTS = (
    _receipt("V5-M02-alpha", "2026-08-24T10:01:00Z", 0.020864, 292309),
    _receipt("V5-M11-bravo", "2026-08-24T10:06:00Z", 0.011111, 140002),
)

ESCALATIONS = (
    {"type": "workflow.escalation", "actor": "dispatch-release",
     "summary": "task V5-M11-bravo escalated to frontier",
     "metadata": {"task_id": "V5-M11-bravo", "repo_id": "agentops",
                  "stop_condition": "diff-empty"},
     "recorded_at": "2026-08-24T10:04:00Z"},
)


def _env():
    """Child environment that never writes bytecode into the repository."""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


class EntrypointTestCase(unittest.TestCase):
    """Every case gets a real directory and runs the script as a program."""

    def setUp(self):
        self.assertTrue(
            SCRIPT.exists(),
            f"no script to grade: {SCRIPT} does not exist",
        )
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

        self.sink = self.tmp / "session-costs.jsonl"
        self._write_lines(self.sink, SINK_ROWS)
        self.escalations = self.tmp / "escalations.jsonl"
        self._write_lines(self.escalations, ESCALATIONS)
        self.receipts_root = self.tmp / "receipts"
        self.receipts_root.mkdir(parents=True, exist_ok=True)
        for receipt in RECEIPTS:
            task_dir = self.receipts_root / receipt["task_id"]
            task_dir.mkdir(parents=True, exist_ok=True)
            (task_dir / "receipt.json").write_text(
                json.dumps(receipt), encoding="utf-8")
        self.out = self.tmp / "scorecard.json"

    @staticmethod
    def _write_lines(path: Path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )

    def run_script(self, args):
        """Run the subject as a command and return the CompletedProcess."""
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, env=_env(), cwd=str(self.tmp),
        )

    def full_args(self, out=None, extra=()):
        return [
            "--release", "v5",
            "--sink", str(self.sink),
            "--receipts", str(self.receipts_root),
            "--out", str(out if out is not None else self.out),
            *extra,
        ]


class RunnableAsACommandTests(EntrypointTestCase):
    """The failing test this packet exists for."""

    def test_running_the_script_as_a_command_writes_the_scorecard(self):
        """The row says the scorecard is produced by RUNNING a command.

        Today the file has no ``__main__`` block: the process exits 0 having
        written nothing, so the release ships with no scorecard and a green
        exit status saying it did.
        """
        result = self.run_script(self.full_args(
            extra=["--escalations", str(self.escalations)]))
        self.assertEqual(
            result.returncode, 0,
            "running the script as a command did not exit 0 "
            f"(stdout={result.stdout!r} stderr={result.stderr!r})",
        )
        self.assertTrue(
            self.out.exists(),
            "running the script as a command wrote no scorecard at --out -- "
            "the module has no __main__ entry point, so it defines its "
            "functions and exits 0 having done nothing",
        )
        written = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(
            written["release"], "v5",
            "the scorecard written by the command does not name the release "
            "it was given",
        )
        for key in ("frontier", "worker", "cost_usd"):
            self.assertIn(
                key, written,
                f"the scorecard written by the command has no {key!r} key",
            )

    def test_the_exit_status_is_mains_return_value(self):
        """A successful run returns 0, and the shell must see that 0."""
        result = self.run_script(self.full_args())
        self.assertEqual(
            result.returncode, 0,
            "a fully-specified run did not exit 0 "
            f"(stderr={result.stderr!r})",
        )
        self.assertTrue(
            self.out.exists(),
            "a fully-specified run exited 0 without writing --out",
        )


class RequiredArgumentTests(EntrypointTestCase):

    REQUIRED = ("--release", "--sink", "--receipts", "--out")

    def test_each_required_flag_is_required(self):
        """A missing flag must fail loudly and write nothing.

        Today a missing ``--release`` yields a written scorecard carrying
        ``"release": null`` and exit 0 -- a scorecard naming no release gets
        filed against the wrong one, which is worse than no scorecard at all.
        """
        for flag in self.REQUIRED:
            with self.subTest(flag=flag):
                out = self.tmp / f"scorecard-missing-{flag.lstrip('-')}.json"
                args = self.full_args(out=out)
                index = args.index(flag)
                # When --out itself is the omitted flag, ``out`` is the path
                # the complete invocation would have used; nothing may appear
                # there either.
                args = args[:index] + args[index + 2:]
                result = self.run_script(args)
                self.assertNotEqual(
                    result.returncode, 0,
                    f"omitting {flag} exited 0 -- a required argument was "
                    "silently defaulted",
                )
                self.assertTrue(
                    result.stderr.strip(),
                    f"omitting {flag} said nothing on stderr",
                )
                self.assertFalse(
                    out.exists(),
                    f"omitting {flag} still wrote a scorecard at {out} -- an "
                    "implementation that errors after writing has already "
                    "corrupted the evidence directory",
                )


class HelpAndUnknownFlagTests(EntrypointTestCase):

    def test_help_exits_zero_and_names_the_flags(self):
        result = self.run_script(["--help"])
        self.assertEqual(
            result.returncode, 0,
            f"--help did not exit 0 (stderr={result.stderr!r})",
        )
        self.assertIn(
            "--release", result.stdout,
            "--help does not mention --release on stdout",
        )
        self.assertIn(
            "--out", result.stdout,
            "--help does not mention --out on stdout",
        )

    def test_an_unknown_flag_is_rejected(self):
        """Silently ignoring a flag is how a typo becomes a wrong scorecard."""
        result = self.run_script(self.full_args(
            extra=["--not-a-real-flag", "whatever"]))
        self.assertNotEqual(
            result.returncode, 0,
            "an unknown flag was silently ignored rather than rejected",
        )


class OptionalArgumentTests(EntrypointTestCase):

    def test_the_optional_flags_stay_optional(self):
        """No --escalations, no --since, no --until is a complete run."""
        result = self.run_script(self.full_args())
        self.assertEqual(
            result.returncode, 0,
            "a run with no optional flags did not exit 0 "
            f"(stderr={result.stderr!r})",
        )
        self.assertTrue(
            self.out.exists(),
            "a run with no optional flags wrote no scorecard",
        )
        written = json.loads(self.out.read_text(encoding="utf-8"))
        self.assertEqual(
            written["escalations"]["count"], 0,
            "omitting --escalations did not produce a zero escalation count",
        )


class WrittenFileShapeTests(EntrypointTestCase):

    def test_the_written_file_is_indent_two_json_ending_in_a_newline(self):
        result = self.run_script(self.full_args(
            extra=["--escalations", str(self.escalations)]))
        self.assertEqual(
            result.returncode, 0,
            f"the run did not exit 0 (stderr={result.stderr!r})",
        )
        self.assertTrue(
            self.out.exists(), "the run wrote no scorecard at --out",
        )
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


class DeterminismTests(EntrypointTestCase):

    def test_two_runs_over_the_same_inputs_differ_only_in_recorded_at(self):
        """The entry point must add no nondeterminism of its own."""
        first_out = self.tmp / "scorecard-first.json"
        second_out = self.tmp / "scorecard-second.json"
        cards = []
        for out in (first_out, second_out):
            result = self.run_script(self.full_args(
                out=out, extra=["--escalations", str(self.escalations)]))
            self.assertEqual(
                result.returncode, 0,
                f"the run writing {out.name} did not exit 0 "
                f"(stderr={result.stderr!r})",
            )
            self.assertTrue(
                out.exists(), f"the run writing {out.name} wrote nothing",
            )
            card = json.loads(out.read_text(encoding="utf-8"))
            card.pop("recorded_at", None)
            cards.append(card)
        self.assertEqual(
            cards[0], cards[1],
            "two runs over identical inputs produced different scorecards "
            "once recorded_at is removed -- the entry point introduced "
            "nondeterminism",
        )


if __name__ == "__main__":
    unittest.main()
