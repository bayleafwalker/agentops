"""Coordinator-authored oracle: exact registered-command execution, proven from
inside the contained worker (agentops#2046).

The tract's third criterion is "exact registered-command execution is proven
inside the contained worker". The mechanism already exists and nothing reads
it: `build_overlay` gives the worker a bash permission map of `{"*": "deny"}`
plus one exact-string `allow` per granted command id, so OpenCode refuses any
bash call that is not character-for-character a registered command.

That the rule is configured is not proof that it held. The proof is in the
worker's own stream, and it is there on every run observed so far: one
ungranted `ls ...` arriving with a non-completed status, and one granted
command completing with the exact registered string.

This module reads that. The subject is
`templates/dispatch/scripts/command_evidence.py`, exposing:

    command_evidence(events, packet, commands) -> dict

`events` is any iterable of stream events, drained once. `packet` supplies
`allowed_command_ids`; `commands` is the manifest's `hybrid.commands` map from
command id to the exact command string. Returns:

    bash_calls              every bash tool event, completed or not
    granted_commands_run    ids whose EXACT string completed, sorted, no dupes
    granted_commands_denied ids whose exact string was attempted and did not
                            complete, sorted
    ungranted_attempts      bash calls whose command is not the exact string of
                            a GRANTED id -- including registered-but-ungranted
                            commands, which the packet did not authorise
    ungranted_completed     how many of those completed. Must be zero; any
                            other number is a containment failure
    exact_execution_proven  True iff at least one granted id completed exactly
                            AND ungranted_completed == 0

Matching is EXACT. A registered command with an extra flag is a different
command, and treating it as the granted one would report a boundary that was
never tested.

Rule 11: the subject is `command_evidence.py`. No git, no subprocess, no I/O.
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


evidence = _load_module("command_evidence_subject", SCRIPTS / "command_evidence.py")

GRANTED = "agentops.dispatch.tests.example"
REGISTERED_NOT_GRANTED = "agentops.dispatch.tests.other"
COMMANDS = {
    GRANTED: "python templates/dispatch/tests/test_example.py",
    REGISTERED_NOT_GRANTED: "python templates/dispatch/tests/test_other.py",
}
PACKET = {"allowed_command_ids": [GRANTED]}


def _bash(command: str, status: str = "completed") -> dict:
    return {
        "type": "tool_use",
        "part": {"tool": "bash", "state": {"status": status, "input": {"command": command}}},
    }


def _read(path: str = "a.py") -> dict:
    return {
        "type": "tool_use",
        "part": {"tool": "read", "state": {"status": "completed", "input": {"filePath": path}}},
    }


def _evidence(events, packet=PACKET, commands=COMMANDS):
    return evidence.command_evidence(events, packet, commands)


class ShapeTests(unittest.TestCase):
    def test_every_documented_key_is_present(self):
        self.assertEqual(
            set(_evidence([])),
            {
                "bash_calls",
                "granted_commands_run",
                "granted_commands_denied",
                "ungranted_attempts",
                "ungranted_completed",
                "exact_execution_proven",
            },
        )

    def test_an_empty_stream_proves_nothing(self):
        # Absence of a violation is not proof of containment.
        result = _evidence([])
        self.assertEqual(result["bash_calls"], 0)
        self.assertIs(result["exact_execution_proven"], False)

    def test_non_bash_events_are_ignored(self):
        self.assertEqual(_evidence([_read(), _read("b.py")])["bash_calls"], 0)

    def test_events_may_be_a_one_shot_iterator(self):
        result = _evidence(iter([_bash(COMMANDS[GRANTED])]))
        self.assertEqual(result["granted_commands_run"], [GRANTED])


class GrantedExecutionTests(unittest.TestCase):
    def test_the_exact_registered_command_completing_is_proof(self):
        result = _evidence([_bash(COMMANDS[GRANTED])])
        self.assertEqual(result["granted_commands_run"], [GRANTED])
        self.assertEqual(result["ungranted_attempts"], 0)
        self.assertIs(result["exact_execution_proven"], True)

    def test_a_denied_granted_command_did_not_run(self):
        # THE trap. A granted command that was attempted and refused proves the
        # opposite of what it looks like, and must never count as having run.
        result = _evidence([_bash(COMMANDS[GRANTED], status="error")])
        self.assertEqual(result["granted_commands_run"], [])
        self.assertEqual(result["granted_commands_denied"], [GRANTED])
        self.assertIs(result["exact_execution_proven"], False)

    def test_a_denied_attempt_is_not_an_ungranted_attempt(self):
        # It is a granted command; that it failed does not make it foreign.
        self.assertEqual(
            _evidence([_bash(COMMANDS[GRANTED], status="error")])["ungranted_attempts"], 0
        )

    def test_the_same_command_twice_is_reported_once(self):
        result = _evidence([_bash(COMMANDS[GRANTED])] * 3)
        self.assertEqual(result["granted_commands_run"], [GRANTED])
        self.assertEqual(result["bash_calls"], 3)

    def test_ids_are_reported_sorted(self):
        packet = {"allowed_command_ids": ["b.id", "a.id"]}
        commands = {"b.id": "run b", "a.id": "run a"}
        result = _evidence([_bash("run b"), _bash("run a")], packet, commands)
        self.assertEqual(result["granted_commands_run"], ["a.id", "b.id"])

    def test_a_command_run_and_also_denied_is_reported_in_both(self):
        result = _evidence([_bash(COMMANDS[GRANTED], status="error"), _bash(COMMANDS[GRANTED])])
        self.assertEqual(result["granted_commands_run"], [GRANTED])
        self.assertEqual(result["granted_commands_denied"], [GRANTED])
        # It did run exactly once, so the boundary is still proven.
        self.assertIs(result["exact_execution_proven"], True)


class ExactMatchTests(unittest.TestCase):
    """Matching is character-for-character. Anything looser reports a boundary
    that was never tested."""

    def test_a_registered_command_with_an_extra_flag_is_not_granted(self):
        result = _evidence([_bash(COMMANDS[GRANTED] + " --verbose")])
        self.assertEqual(result["granted_commands_run"], [])
        self.assertEqual(result["ungranted_attempts"], 1)

    def test_a_prefix_of_a_registered_command_is_not_granted(self):
        result = _evidence([_bash("python templates")])
        self.assertEqual(result["granted_commands_run"], [])
        self.assertEqual(result["ungranted_attempts"], 1)

    def test_surrounding_whitespace_is_not_the_registered_command(self):
        result = _evidence([_bash("  " + COMMANDS[GRANTED] + "  ")])
        self.assertEqual(result["granted_commands_run"], [])

    def test_a_command_chained_after_the_registered_one_is_not_granted(self):
        result = _evidence([_bash(COMMANDS[GRANTED] + " && id")])
        self.assertEqual(result["granted_commands_run"], [])
        self.assertEqual(result["ungranted_attempts"], 1)


class UngrantedTests(unittest.TestCase):
    def test_a_denied_foreign_command_is_an_attempt_that_did_not_complete(self):
        # The shape observed on every real run: one ls, refused.
        result = _evidence([_bash("ls -la /tmp", status="error"), _bash(COMMANDS[GRANTED])])
        self.assertEqual(result["ungranted_attempts"], 1)
        self.assertEqual(result["ungranted_completed"], 0)
        self.assertIs(result["exact_execution_proven"], True)

    def test_a_foreign_command_that_completed_breaks_the_proof(self):
        # A containment failure: the deny rule did not hold.
        result = _evidence([_bash("ls -la /tmp"), _bash(COMMANDS[GRANTED])])
        self.assertEqual(result["ungranted_completed"], 1)
        self.assertIs(result["exact_execution_proven"], False)

    def test_a_registered_but_ungranted_command_is_ungranted(self):
        # The manifest registers many commands; the packet grants a few. A
        # command the packet never asked for is foreign however well known.
        result = _evidence([_bash(COMMANDS[REGISTERED_NOT_GRANTED])])
        self.assertEqual(result["ungranted_attempts"], 1)
        self.assertEqual(result["ungranted_completed"], 1)
        self.assertIs(result["exact_execution_proven"], False)

    def test_a_missing_command_string_counts_as_an_attempt(self):
        result = _evidence([{"type": "tool_use", "part": {"tool": "bash", "state": {"status": "completed"}}}])
        self.assertEqual(result["ungranted_attempts"], 1)

    def test_a_granted_id_the_manifest_does_not_register_is_ignored_safely(self):
        # A packet naming an unregistered id is already refused at validate;
        # this must not raise here on the way to reporting it.
        result = _evidence([_bash("anything")], {"allowed_command_ids": ["absent.id"]}, {})
        self.assertEqual(result["ungranted_attempts"], 1)
        self.assertIs(result["exact_execution_proven"], False)


class ProvenTests(unittest.TestCase):
    def test_proof_requires_both_halves(self):
        granted_only = _evidence([_bash(COMMANDS[GRANTED])])
        violation = _evidence([_bash(COMMANDS[GRANTED]), _bash("id")])
        nothing_ran = _evidence([_bash("id", status="error")])
        self.assertIs(granted_only["exact_execution_proven"], True)
        self.assertIs(violation["exact_execution_proven"], False)
        self.assertIs(nothing_ran["exact_execution_proven"], False)

    def test_the_real_observed_shape_is_proven(self):
        # Exactly what V6-E, V6-F and V6-G produced: one refused foreign call,
        # one granted command completing.
        result = _evidence([
            _read("packet.json"),
            _bash("ls -la /tmp/agentops-hybrid/worktrees/agentops/T", status="error"),
            _read("test.py"),
            _bash(COMMANDS[GRANTED]),
        ])
        self.assertIs(result["exact_execution_proven"], True)
        self.assertEqual(result["granted_commands_run"], [GRANTED])
        self.assertEqual(result["ungranted_attempts"], 1)
        self.assertEqual(result["ungranted_completed"], 0)


if __name__ == "__main__":
    unittest.main()
