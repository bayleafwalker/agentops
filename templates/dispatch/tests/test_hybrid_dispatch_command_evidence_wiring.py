"""Coordinator hand-pass oracle: the command boundary is read and enforced.

`command_evidence.py` (#127) reads the exact-registered-command boundary out of
a worker stream. This file pins that the coordinator does three things with it:

* parses the stream once, in a named place, rather than twice differently;
* puts the evidence on the run receipt, so a corpus read later can see whether
  the boundary held on each run;
* treats an ungranted command that COMPLETED as a containment breach -- the
  same class of escape as a write outside the disposable worktree, and equally
  not retryable.

The third is the one that matters. A metric computed and dropped would leave
the disposition exactly as permissive as before, which is how `context_churn`
came to be enforced and unrecorded for months.

Rule 11: the subject is `hybrid_dispatch.py`. No git, no subprocess.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch_cmd_wiring_subject", SCRIPTS / "hybrid_dispatch.py")

GRANTED = "agentops.dispatch.tests.example"
MANIFEST = {"hybrid": {"commands": {GRANTED: "python test_example.py"}}}
PACKET = {"allowed_command_ids": [GRANTED]}


def _bash(command: str, status: str = "completed") -> dict:
    return {
        "type": "tool_use",
        "part": {"tool": "bash", "state": {"status": status, "input": {"command": command}}},
    }


class StreamEventsTests(unittest.TestCase):
    """The parse is named once. dispatch_worker parses as the stream arrives so
    churn can be enforced live; the after-the-fact readers have only stdout."""

    def test_json_lines_are_parsed(self):
        events = dispatch.stream_events('{"a": 1}\n{"b": 2}\n')
        self.assertEqual(events, [{"a": 1}, {"b": 2}])

    def test_non_json_lines_are_skipped(self):
        # A worker's stdout is not guaranteed to be pure JSON; a stray line
        # must not lose the events around it.
        events = dispatch.stream_events('{"a": 1}\nnot json at all\n{"b": 2}\n')
        self.assertEqual(events, [{"a": 1}, {"b": 2}])

    def test_a_json_scalar_is_not_an_event(self):
        self.assertEqual(dispatch.stream_events("42\n"), [])

    def test_empty_input_is_empty(self):
        self.assertEqual(dispatch.stream_events(""), [])
        self.assertEqual(dispatch.stream_events(None), [])


class EvidenceTests(unittest.TestCase):
    def test_the_coordinator_reads_the_boundary(self):
        result = dispatch.command_evidence_for(
            [_bash("python test_example.py")], PACKET, MANIFEST
        )
        self.assertIs(result["exact_execution_proven"], True)
        self.assertEqual(result["granted_commands_run"], [GRANTED])

    def test_a_denied_foreign_call_is_the_boundary_holding(self):
        result = dispatch.command_evidence_for(
            [_bash("ls -la /tmp", status="error"), _bash("python test_example.py")],
            PACKET,
            MANIFEST,
        )
        self.assertEqual(result["ungranted_attempts"], 1)
        self.assertEqual(result["ungranted_completed"], 0)
        self.assertIs(result["exact_execution_proven"], True)

    def test_a_completed_foreign_call_is_a_failure(self):
        result = dispatch.command_evidence_for(
            [_bash("ls -la /tmp"), _bash("python test_example.py")], PACKET, MANIFEST
        )
        self.assertEqual(result["ungranted_completed"], 1)
        self.assertIs(result["exact_execution_proven"], False)


class WiringTests(unittest.TestCase):
    """Source-level, because the run stage cannot be exercised without a worker
    binary, and a predicate computed and dropped is the defect to prevent."""

    def setUp(self):
        self.source = (SCRIPTS / "hybrid_dispatch.py").read_text()

    def test_the_evidence_is_attached_to_the_run_transcript(self):
        self.assertIn('transcript["command_evidence"] = command_evidence_for(', self.source)

    def test_the_receipt_records_whether_only_registered_commands_ran(self):
        self.assertIn('"registered_commands_only": not ungranted_ran,', self.source)

    def test_the_receipt_records_the_proof_itself(self):
        self.assertIn('"exact_execution_proven": transcript["command_evidence"][', self.source)

    def test_an_ungranted_command_that_completed_is_a_containment_breach(self):
        # The disposition, not merely a field: this is what stops the packet.
        self.assertIn('if breach or ungranted_ran', self.source)

    def test_the_breach_exit_covers_the_command_boundary_too(self):
        # Both escapes leave through the same door, with the same exit code.
        self.assertIn("            if breach or ungranted_ran:\n                return 3", self.source)

    def test_the_evidence_is_read_before_the_disposition_is_decided(self):
        # Ordering is load-bearing: computing it after the disposition would
        # record the breach and still mint a candidate.
        self.assertLess(
            self.source.index("ungranted_ran = transcript"),
            self.source.index('{"disposition": "containment_breach"}'),
        )


if __name__ == "__main__":
    unittest.main()
