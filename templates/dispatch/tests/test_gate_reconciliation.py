"""A configured gate with nothing computing it must fail closed, on both sides.

Pre-dispatch, ``validate_packet`` ended with ``return list(policy["gates"]["pre"])``
-- the policy's own list, echoed back whatever had been checked. Six of the eight
names were computed by nothing anywhere in these scripts, so a schema-invalid
packet was reported ``fit`` under ``packet-schema-valid`` and dispatched twice.

Post-dispatch the shape was subtler: ``post_gates`` builds a real
name-to-computed-value dict, but ``passed`` is ``all(gates.values())`` and a
policy gate absent from that dict contributes nothing to an ``all()``. Adding a
gate to the policy file would therefore have made dispatch *easier* to pass.

Both halves now reconcile against the policy. These are the tests that fail if
either stops doing so.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
POLICY_PATH = ROOT / "templates/dispatch/hybrid/hybrid-dispatch.v1.json"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load("hybrid_dispatch_reconciliation_subject", SCRIPTS / "hybrid_dispatch.py")
POLICY = json.loads(POLICY_PATH.read_text(encoding="utf-8"))


class EveryConfiguredPreGateHasAnEvaluator(unittest.TestCase):
    def test_the_committed_policy_registers_all_of_its_pre_gates(self) -> None:
        missing = [
            name for name in POLICY["gates"]["pre"]
            if name not in dispatch.PRE_GATE_EVALUATORS
        ]
        self.assertEqual([], missing)

    def test_every_registration_names_where_it_is_decided(self) -> None:
        """A gate deferred to another phase must say which code decides it."""
        for name, (phase, evaluator) in dispatch.PRE_GATE_EVALUATORS.items():
            with self.subTest(gate=name):
                self.assertIn(phase, (dispatch.VALIDATE_PHASE, dispatch.PREPARE_PHASE))
                if evaluator is None:
                    self.assertIn(
                        name, dispatch.GATE_EVALUATOR_NAMES,
                        "a gate with no inline evaluator must name its owner")

    def test_no_gate_is_registered_that_the_policy_does_not_configure(self) -> None:
        orphans = [
            name for name in dispatch.PRE_GATE_EVALUATORS
            if name not in POLICY["gates"]["pre"]
        ]
        self.assertEqual([], orphans)


class PostGatesReconcileWithPolicy(unittest.TestCase):
    """The first tests ``post_gates`` has ever had."""

    def _worktree(self) -> tuple[Path, str]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        run = lambda *a: subprocess.run(
            ["git", "-C", str(root), *a], check=True, capture_output=True)
        run("init", "-q", "-b", "main")
        run("config", "user.email", "fixture@example.invalid")
        run("config", "user.name", "fixture")
        (root / "src").mkdir()
        (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        run("add", "-A")
        run("commit", "-qm", "base")
        commit = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True).stdout.strip()
        (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
        return root, commit

    def _packet(self, commit: str) -> dict:
        return {
            "task_id": "FIXTURE-1",
            "starting_commit": commit,
            "writable_patch_paths": ["src/**"],
            "protected_paths": [],
            "allowed_command_ids": [],
            "acceptance_properties": [],
        }

    def _manifest(self) -> dict:
        return {"repo_id": "fixture", "hybrid": {"protected_paths": [], "commands": {}}}

    def test_a_policy_gate_nothing_computes_is_reported_and_blocks(self) -> None:
        worktree, commit = self._worktree()
        policy = {"gates": {"post": POLICY["gates"]["post"] + ["invented-post-gate"]}}
        evidence = dispatch.post_gates(
            worktree, self._packet(commit), self._manifest(), worktree, policy)
        self.assertIn("invented-post-gate", evidence["unevaluated_gates"])
        self.assertIs(False, evidence["gates"]["invented-post-gate"])
        self.assertFalse(evidence["passed"], "an unevaluated gate must fail closed")

    def test_the_committed_policy_leaves_nothing_unaccounted_for(self) -> None:
        """Every configured post-gate is either computed here or deferred by name.

        ``coordinator-review-recorded`` is the deferred one: it is settled at
        disposition, not by inspecting the worktree. Before this reconciliation
        it was simply absent from the dict, which meant ``all(gates.values())``
        never considered it.
        """
        worktree, commit = self._worktree()
        evidence = dispatch.post_gates(
            worktree, self._packet(commit), self._manifest(), worktree, POLICY)
        self.assertEqual([], evidence["unevaluated_gates"])
        accounted = set(evidence["gates"]) | set(evidence["deferred_gates"])
        self.assertEqual([], [g for g in POLICY["gates"]["post"] if g not in accounted])
        self.assertEqual(
            {"coordinator-review-recorded": "load_independent_review+self_candidate_class"},
            evidence["deferred_gates"])

    def test_a_deferred_gate_names_an_owner_that_exists(self) -> None:
        for gate, owner in dispatch.POST_GATE_OWNERS.items():
            with self.subTest(gate=gate):
                self.assertIn(gate, POLICY["gates"]["post"])
                for function in owner.split("+"):
                    self.assertTrue(
                        hasattr(dispatch, function),
                        f"{gate} defers to {function}, which does not exist")

    def test_omitting_the_policy_reconciles_nothing_rather_than_guessing(self) -> None:
        worktree, commit = self._worktree()
        evidence = dispatch.post_gates(
            worktree, self._packet(commit), self._manifest(), worktree)
        self.assertEqual([], evidence["unevaluated_gates"])


if __name__ == "__main__":
    unittest.main()
