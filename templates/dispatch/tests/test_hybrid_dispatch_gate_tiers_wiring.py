"""Coordinator hand-pass oracle: the tiers are wired, and cannot shrink the gate set.

`gate_tiers.py` (#118) decides the tier rules. This file pins that the
coordinator actually uses them, and that using them cannot make a candidate
cheaper -- the criterion in `agentops#2046` that stratification "does not skip
the final required repository gate".

Three seams, because a defect in any one of them reopens the hole:

* the packet schema must ACCEPT a stratified packet -- with
  ``additionalProperties: false`` at the root, an unaccepted field is a packet
  that cannot be frozen at all, and stratification would be unusable;
* ``run_registered_commands`` must run tiers in order and may stop early;
* the gate evidence must carry ``required-gates-complete``, which is false
  whenever a granted gate has not run green -- including when the run stopped
  early on purpose.

Rule 11: the subject is ``hybrid_dispatch.py`` and the two protected JSON files
it reads. It runs no git; the only subprocesses are the trivial shell commands
the function under test is defined to run.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
HYBRID = ROOT / "templates/dispatch/hybrid"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch_tier_wiring_subject", SCRIPTS / "hybrid_dispatch.py")

MANIFEST = {
    "hybrid": {
        "commands": {
            "green-a": "true",
            "green-b": "true",
            "red": "false",
        }
    }
}


def _packet(granted, gate_tiers=None) -> dict:
    packet = {"allowed_command_ids": list(granted), "limits": {"timeout_seconds": 60}}
    if gate_tiers is not None:
        packet["gate_tiers"] = gate_tiers
    return packet


class PolicyTests(unittest.TestCase):
    def test_the_policy_requires_the_completeness_gate(self):
        policy = json.loads((HYBRID / "hybrid-dispatch.v1.json").read_text())
        self.assertIn("required-gates-complete", policy["gates"]["post"])


class SchemaTests(unittest.TestCase):
    """The root is additionalProperties:false, so an unaccepted field is not a
    lenient packet -- it is a packet that cannot be frozen."""

    def setUp(self):
        self.schema = json.loads((HYBRID / "task-packet.schema.json").read_text())

    def test_the_schema_accepts_a_stratified_packet(self):
        self.assertIn("gate_tiers", self.schema["properties"])

    def test_stratification_is_optional(self):
        self.assertNotIn("gate_tiers", self.schema["required"])

    def test_only_the_three_tiers_are_accepted(self):
        node = self.schema["properties"]["gate_tiers"]
        self.assertFalse(node["additionalProperties"])
        self.assertEqual(set(node["properties"]), {"fast", "focused", "full"})


class RunOrderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.worktree = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run(self, packet, **kw):
        return dispatch.run_registered_commands(self.worktree, packet, MANIFEST, **kw)

    def test_commands_run_in_tier_order(self):
        packet = _packet(["green-b", "green-a"], {"fast": ["green-a"], "full": ["green-b"]})
        self.assertEqual([r["command_id"] for r in self._run(packet)], ["green-a", "green-b"])

    def test_each_result_records_the_tier_it_ran_in(self):
        packet = _packet(["green-a", "green-b"], {"fast": ["green-a"], "full": ["green-b"]})
        self.assertEqual([r["tier"] for r in self._run(packet)], ["fast", "full"])

    def test_an_undeclared_packet_runs_every_granted_command(self):
        packet = _packet(["green-a", "green-b"])
        self.assertEqual([r["command_id"] for r in self._run(packet)], ["green-a", "green-b"])

    def test_stop_early_abandons_the_later_tiers(self):
        # The value of a fast falsifier: the suite it rejects is never paid for.
        packet = _packet(["red", "green-b"], {"fast": ["red"], "full": ["green-b"]})
        results = self._run(packet, stop_early=True)
        self.assertEqual([r["command_id"] for r in results], ["red"])

    def test_the_cold_run_does_not_stop_early(self):
        # At freeze every starts_red command must be observed red on its own
        # account, so the default must keep running after the first red.
        packet = _packet(["red", "green-b"], {"fast": ["red"], "full": ["green-b"]})
        self.assertEqual(
            [r["command_id"] for r in self._run(packet)], ["red", "green-b"]
        )


class CompletenessGateTests(unittest.TestCase):
    """The criterion, at the seam that decides a disposition."""

    def test_a_fast_tier_green_alone_does_not_complete_the_gate_set(self):
        # THE falsifier. Stopping early is legal; calling the result complete
        # is not.
        packet = _packet(["fastid", "fullid"], {"fast": ["fastid"], "full": ["fullid"]})
        ran = [{"command_id": "fastid", "exit_code": 0}]
        self.assertFalse(dispatch.required_gates_complete(packet, ran))

    def test_every_tier_green_completes_the_gate_set(self):
        packet = _packet(["fastid", "fullid"], {"fast": ["fastid"], "full": ["fullid"]})
        ran = [
            {"command_id": "fastid", "exit_code": 0},
            {"command_id": "fullid", "exit_code": 0},
        ]
        self.assertTrue(dispatch.required_gates_complete(packet, ran))

    def test_an_undeclared_packet_still_requires_every_granted_gate(self):
        packet = _packet(["a", "b"])
        self.assertFalse(
            dispatch.required_gates_complete(packet, [{"command_id": "a", "exit_code": 0}])
        )

    def test_the_gate_appears_in_the_evidence_the_coordinator_builds(self):
        # A predicate computed and dropped would leave the disposition exactly
        # as permissive as before the row.
        source = (SCRIPTS / "hybrid_dispatch.py").read_text()
        self.assertIn(
            '"required-gates-complete": required_gates_complete(packet, command_results),',
            source,
        )

    def test_the_gate_stage_stops_early(self):
        source = (SCRIPTS / "hybrid_dispatch.py").read_text()
        self.assertIn(
            "run_registered_commands(worktree, packet, manifest, stop_early=True)", source
        )


if __name__ == "__main__":
    unittest.main()
