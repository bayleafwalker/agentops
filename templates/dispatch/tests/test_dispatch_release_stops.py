"""Coordinator-authored oracle for spec row M-1 — L-2 stop conditions in the L-1 driver.

One failing fixture per encoded stop condition (`release-boundary`,
`command-not-allowed` pre-flight and post-gate, `path-outside-writable`,
`gate-red-twice`), plus the negative case. Written against the M-1 spec only:
the driver does not implement any of this yet, so every test here fails today.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_stops_subject", SCRIPTS / "dispatch_release.py")

EXPECTED_CONDITIONS = (
    "release-boundary",
    "command-not-allowed",
    "path-outside-writable",
    "gate-red-twice",
)


class FakeRunner:
    """Scripted stand-in for subprocess: records every command and its cwd.

    ``gate_extra`` is the gate stage's evidence — ``command_results``,
    ``touched_paths``, ``passed``. The real gate nests it under ``evidence``
    while stubbed receipts keep it flat, so ``nest_evidence`` switches between
    the two shapes the driver has to read.
    """

    def __init__(
        self,
        auditctl_bin: str,
        exits: dict[str, int] | None = None,
        disposition: str = "candidate",
        gate_extra: dict[str, Any] | None = None,
        nest_evidence: bool = False,
    ):
        self.auditctl_bin = auditctl_bin
        self.exits = exits or {}
        self.disposition = disposition
        self.gate_extra = gate_extra or {}
        self.nest_evidence = nest_evidence
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        if cmd[0] == self.auditctl_bin:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(
                cmd, self.exits.get("gh", 0), "https://example/pr/1\n", "",
            )
        step = cmd[-1]
        code = self.exits.get(step, 0)
        payload: dict[str, Any] = {"stage": step}
        if step == "gate":
            payload["disposition"] = self.disposition
            if self.nest_evidence:
                payload["evidence"] = dict(self.gate_extra)
            else:
                payload.update(self.gate_extra)
        return subprocess.CompletedProcess(cmd, code, json.dumps(payload), "boom" if code else "")

    def steps(self) -> list[str]:
        return [c[-1] for c, _ in self.calls if c[0] not in (self.auditctl_bin, "gh")]

    def audit_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == self.auditctl_bin]

    def gh_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == "gh"]


class StopConditionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "coordinator"
        self.repo_root.mkdir()
        # A path that exists is all write_escalation needs to treat the sink as
        # reachable; the runner is fake, so nothing is ever executed.
        self.auditctl = self.tmp / "auditctl"
        self.auditctl.write_text("", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _packet(self, **extra: Any) -> Path:
        packet = {
            "task_id": "T-DRIVER",
            "repo_id": "repo-x",
            "starting_commit": "0" * 40,
            "worktree": {"root": str(self.tmp / "wt"), "branch": "hybrid/t-driver"},
        }
        packet.update(extra)
        path = self.tmp / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def _runner(self, **kw) -> FakeRunner:
        return FakeRunner(str(self.auditctl), **kw)

    def _drive(self, packet_path: Path, runner: FakeRunner, **kw):
        kw.setdefault("dry_run", False)
        kw.setdefault("base_branch", "main")
        return driver.drive(
            packet_path, self.repo_root, runner=runner, auditctl_bin=str(self.auditctl), **kw,
        )

    def _assert_no_stop(self, report: dict):
        """A run that violated nothing still carries the key, set to None."""
        self.assertTrue("stop" in report, "report has no 'stop' key")
        self.assertIsNone(report["stop"])

    def _assert_stopped(self, code: int, report: dict, runner: FakeRunner, condition: str):
        """The four consequences the spec attaches to any fired stop condition."""
        self.assertNotEqual(code, 0)
        self.assertTrue("stop" in report, "report has no 'stop' key")
        stop = report["stop"]
        self.assertIsNotNone(stop, "a fired stop condition must populate report['stop']")
        self.assertEqual(stop["condition"], condition)
        self.assertTrue(stop.get("detail"), "detail must name the offending value(s)")
        self.assertIsInstance(stop["detail"], str)
        audit = runner.audit_calls()
        self.assertEqual(len(audit), 1, "the stop escalates exactly once")
        self.assertEqual(audit[0][1:4], ["add", "--type", "workflow.escalation"])
        self.assertEqual(report["escalation"]["metadata"]["stop_condition"], condition)
        # A stop is the driver refusing to hand work onward: the PR is the
        # hand-off, so it must not exist in any form for a stopped run.
        self.assertEqual(runner.gh_calls(), [])

    # The constant is the contract's vocabulary: order is pinned so a reader of
    # a report can map a condition name back to a spec clause.
    def test_stop_conditions_constant(self):
        self.assertIsInstance(driver.STOP_CONDITIONS, tuple)
        self.assertEqual(driver.STOP_CONDITIONS, EXPECTED_CONDITIONS)

    def test_attempts_path_is_keyword_only_and_optional(self):
        params = inspect.signature(driver.drive).parameters
        self.assertIn("attempts_path", params)
        self.assertEqual(params["attempts_path"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(params["attempts_path"].default)

    # 1. release-boundary
    def test_release_boundary_stops_before_any_stage(self):
        packet = self._packet(release_boundary=True)
        runner = self._runner()
        code, report = self._drive(packet, runner)
        self._assert_stopped(code, report, runner, "release-boundary")
        # Pre-flight: a release boundary must not spend a worker run to discover
        # itself, so not one stage may have been invoked.
        self.assertEqual(report["steps"], [])
        self.assertEqual(runner.steps(), [])

    def test_release_boundary_false_is_not_a_boundary(self):
        packet = self._packet(release_boundary=False)
        runner = self._runner()
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        self._assert_no_stop(report)
        self.assertEqual(len(runner.gh_calls()), 1)

    # 2a. command-not-allowed, pre-flight
    def test_command_not_allowed_preflight_stops_before_any_stage(self):
        packet = self._packet(
            allowed_command_ids=["pytest"],
            oracle={"starts_red": "pytest"},
            acceptance_properties=[
                {"id": "P1", "command_id": "pytest"},
                {"id": "P2", "command_id": "curl-the-internet"},
            ],
        )
        runner = self._runner()
        code, report = self._drive(packet, runner)
        self._assert_stopped(code, report, runner, "command-not-allowed")
        self.assertIn("curl-the-internet", report["stop"]["detail"])
        self.assertEqual(report["steps"], [])
        self.assertEqual(runner.steps(), [])

    def test_preflight_has_nothing_to_violate_without_the_keys(self):
        # A packet that never declares an allowlist has not violated one; the
        # driver must not invent a stop out of absent keys.
        runner = self._runner()
        code, report = self._drive(self._packet(), runner)
        self.assertEqual(code, 0)
        self._assert_no_stop(report)

    # 2b. command-not-allowed, post-gate. Amendment 1: the same evidence reaches
    # the driver nested under `evidence` from the real gate and flat from a stub,
    # and both shapes have to fire the condition.
    def test_command_not_allowed_post_gate_stops_before_pr(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                packet = self._packet(allowed_command_ids=["pytest"])
                runner = self._runner(nest_evidence=nested, gate_extra={
                    "command_results": [
                        {"command_id": "pytest", "exit_code": 0},
                        {"command_id": "npm-install", "exit_code": 0},
                    ],
                })
                code, report = self._drive(packet, runner)
                self._assert_stopped(code, report, runner, "command-not-allowed")
                self.assertIn("npm-install", report["stop"]["detail"])
                # The gate ran and told us what it ran; the sequence stops on
                # that evidence rather than continuing to the hand-off.
                self.assertEqual(
                    [s["step"] for s in report["steps"]], ["prepare", "run", "gate"],
                )

    # 3. path-outside-writable
    def test_path_outside_writable_stops_before_pr(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                packet = self._packet(writable_patch_paths=["src/**", "docs/notes.md"])
                runner = self._runner(nest_evidence=nested, gate_extra={
                    "touched_paths": ["src/a/b.py", "docs/notes.md", "infra/prod.tf"],
                })
                code, report = self._drive(packet, runner)
                self._assert_stopped(code, report, runner, "path-outside-writable")
                self.assertIn("infra/prod.tf", report["stop"]["detail"])

    def test_paths_inside_the_writable_globs_do_not_stop(self):
        # Pins the glob convention itself: `src/**` covers arbitrary depth and an
        # exact path matches itself, so a compliant patch reaches the PR.
        for nested in (False, True):
            with self.subTest(nested=nested):
                packet = self._packet(writable_patch_paths=["src/**", "docs/notes.md"])
                runner = self._runner(nest_evidence=nested, gate_extra={
                    "touched_paths": ["src/a/deep/c.py", "docs/notes.md"],
                })
                code, report = self._drive(packet, runner)
                self.assertEqual(code, 0)
                self._assert_no_stop(report)
                self.assertEqual(len(runner.gh_calls()), 1)

    # 4. gate-red-twice
    def _red_then_green(self) -> FakeRunner:
        """A gate that is red once and green on the retry L-4 spends for it."""

        class RedThenGreen(FakeRunner):
            def __call__(self, cmd, cwd):
                if cmd[-1] == "gate" and any(c[-1] == "gate" for c, _ in self.calls):
                    self.exits, self.disposition = {}, "candidate"
                return super().__call__(cmd, cwd)

        return RedThenGreen(
            str(self.auditctl), exits={"gate": 2}, disposition="coordinator_review_required",
        )

    def test_first_red_gate_is_recorded_but_does_not_stop(self):
        # Amended for L-4 (spec M-2, Amendment 1). This used to pin "one red gate
        # skips the PR with a reason and exits 0"; L-4 answers the first red with
        # one cheap retry instead, so that reason string no longer exists and must
        # not be restored. What survives is that the first red is recorded and is
        # not itself a stop.
        packet = self._packet()
        runner = self._red_then_green()
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        self._assert_no_stop(report)
        self.assertEqual(len(runner.gh_calls()), 1, "a green retry reaches the hand-off")
        ledger = driver.worktree_path(json.loads(packet.read_text())).parent / "T-DRIVER.attempts.json"
        self.assertTrue(ledger.exists(), f"the default ledger {ledger} was not written")
        self.assertEqual(json.loads(ledger.read_text())["0" * 40], 1)

    def test_second_red_gate_on_the_same_commit_stops(self):
        # Amended for L-4 (spec M-2, Amendment 1). The first drive can no longer
        # be a plain red run -- that would spend its own retry and stop inside
        # this call -- so it is the red-then-green run that leaves exactly one
        # red in the ledger. The point of the fixture is unchanged: the ledger is
        # what carries a red across drive() calls, and a fresh drive() on the
        # same starting_commit does not get a clean slate.
        packet = self._packet()
        first = self._red_then_green()
        code, _ = self._drive(packet, first)
        # A completed run, not a stopped one: its retry went green and handed
        # off. What it leaves behind is the single red in the ledger.
        self.assertEqual(code, 0)
        self.assertEqual(len(first.gh_calls()), 1)
        second = self._runner(exits={"gate": 2}, disposition="coordinator_review_required")
        code, report = self._drive(packet, second)
        self._assert_stopped(code, report, second, "gate-red-twice")
        # The ledger already held a red for this commit, so this run has no cheap
        # retry left to spend: it stops on the gate it just ran.
        self.assertEqual(second.steps().count("gate"), 1)

    def test_gate_receipt_marked_not_passed_counts_as_red(self):
        # "Red" is not only a non-zero exit: a candidate disposition carrying
        # passed=false is a failing gate and must consume an attempt too --
        # whether the flag arrives nested under `evidence` or flat.
        for nested, commit in ((False, "a" * 40), (True, "b" * 40)):
            with self.subTest(nested=nested):
                packet = self._packet(starting_commit=commit)
                for _ in range(2):
                    runner = self._runner(nest_evidence=nested, gate_extra={"passed": False})
                    code, report = self._drive(packet, runner)
                self._assert_stopped(code, report, runner, "gate-red-twice")

    def test_green_gates_never_fire_the_condition(self):
        packet = self._packet()
        for _ in range(3):
            runner = self._runner()
            code, report = self._drive(packet, runner)
            self.assertEqual(code, 0)
            self._assert_no_stop(report)

    # The negative case: nothing declared, nothing violated, PR opened.
    def test_clean_run_has_no_stop_and_opens_the_pr(self):
        packet = self._packet(
            allowed_command_ids=["pytest"],
            oracle={"starts_red": "pytest"},
            acceptance_properties=[{"id": "P1", "command_id": "pytest"}],
            writable_patch_paths=["src/**"],
        )
        runner = self._runner(gate_extra={
            "command_results": [{"command_id": "pytest", "exit_code": 0}],
            "touched_paths": ["src/a.py"],
        })
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        self._assert_no_stop(report)
        self.assertIsNone(report["escalation"])
        self.assertEqual(runner.audit_calls(), [])
        self.assertTrue(report["pr"]["opened"])


if __name__ == "__main__":
    unittest.main()
