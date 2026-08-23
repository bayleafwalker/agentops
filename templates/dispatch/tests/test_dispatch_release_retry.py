"""Coordinator-authored oracle for spec row M-2 — L-4 retry policy in the L-1 driver.

One cheap retry after a red gate (`run`, `gate`, `receipt` only — never
`prepare`), driven off a retry packet that carries the red gate's output into
the worker's `purpose`; a second red hands over to M-1's `gate-red-twice` stop.
Written against the M-2 spec only: the driver spends no retry today, so every
test here fails.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"

#: Markers the fake gate writes on its red pass. The retry packet has to carry
#: these strings, so a driver that invents its own summary instead of forwarding
#: the gate's captured output fails.
RED_STDOUT_MARK = "FAILED tests/test_thing.py::test_widget - AssertionError: 3 != 4"
RED_STDERR_MARK = "ERROR: gate command 'pytest' exited 1"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_retry_subject", SCRIPTS / "dispatch_release.py")


class FakeRunner:
    """Scripted stand-in for subprocess: records every command, cwd and packet path.

    ``gate_script`` is consumed one entry per ``gate`` invocation, so a fixture
    can say "red, then green" and a third gate call raises rather than silently
    reusing the last verdict — that is how the oracle detects a third attempt.
    Each entry is ``(exit_code, disposition, extra)``; ``extra`` is the gate
    evidence, nested under ``evidence`` the way a real gate receipt nests it.
    """

    def __init__(
        self,
        auditctl_bin: str,
        gate_script: list[tuple[int, str, dict[str, Any]]] | None = None,
        exits: dict[str, int] | None = None,
    ):
        self.auditctl_bin = auditctl_bin
        self.gate_script = list(gate_script or [(0, "candidate", {})])
        self.exits = exits or {}
        self.calls: list[tuple[list[str], Path | None]] = []
        self.gate_calls = 0

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        if cmd[0] == self.auditctl_bin:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(
                cmd, self.exits.get("gh", 0), "https://example/pr/1\n", "",
            )
        step = cmd[-1]
        if step == "gate":
            index = self.gate_calls
            self.gate_calls += 1
            if index >= len(self.gate_script):
                raise AssertionError(
                    f"gate invoked {self.gate_calls} times; the script has "
                    f"{len(self.gate_script)} verdicts and MAX_GATE_ATTEMPTS bounds it"
                )
            code, disposition, extra = self.gate_script[index]
            payload: dict[str, Any] = {"stage": "gate", "disposition": disposition}
            payload["evidence"] = dict(extra)
            red = code != 0 or disposition != "candidate" or extra.get("passed") is False
            stdout = json.dumps(payload)
            if red:
                # A real gate's stdout is its receipt and its stderr is the raw
                # command output; the retry has to be able to draw on both.
                stdout = json.dumps({**payload, "stdout_tail": RED_STDOUT_MARK})
            return subprocess.CompletedProcess(cmd, code, stdout, RED_STDERR_MARK if red else "")
        code = self.exits.get(step, 0)
        payload = {"stage": step}
        return subprocess.CompletedProcess(cmd, code, json.dumps(payload), "boom" if code else "")

    def steps(self) -> list[str]:
        # M-8 made the PR step run git (remote add, push); their argv tails are
        # not stage names, so they are excluded here as auditctl and gh are.
        return [c[-1] for c, _ in self.calls if c[0] not in (self.auditctl_bin, "gh", "git")]

    def packets(self) -> list[tuple[str, str]]:
        """(step, --packet argument) for every hybrid_dispatch invocation, in order."""
        out = []
        for cmd, _ in self.calls:
            if cmd[0] in (self.auditctl_bin, "gh") or "--packet" not in cmd:
                continue
            out.append((cmd[-1], cmd[cmd.index("--packet") + 1]))
        return out

    def audit_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == self.auditctl_bin]

    def gh_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == "gh"]


RED_GATE = (2, "coordinator_review_required", {})
GREEN_GATE = (0, "candidate", {})


class RetryPolicyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "coordinator"
        self.repo_root.mkdir()
        # A path that exists is all write_escalation needs to treat the sink as
        # reachable; the runner is fake, so nothing is ever executed.
        self.auditctl = self.tmp / "auditctl"
        self.auditctl.write_text("", encoding="utf-8")
        self.packet_path = self._packet()

    def tearDown(self):
        self._tmp.cleanup()

    def _packet(self, **extra: Any) -> Path:
        packet = {
            "task_id": "T-DRIVER",
            "repo_id": "repo-x",
            "starting_commit": "0" * 40,
            "purpose": "Make the widget add correctly.",
            "writable_patch_paths": ["src/**"],
            "allowed_command_ids": ["pytest"],
            "oracle": {"starts_red": "pytest"},
            "worktree": {"root": str(self.tmp / "wt"), "branch": "hybrid/t-driver"},
        }
        packet.update(extra)
        path = self.tmp / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def _runner(self, **kw) -> FakeRunner:
        return FakeRunner(str(self.auditctl), **kw)

    def _drive(self, runner: FakeRunner, packet_path: Path | None = None, **kw):
        kw.setdefault("dry_run", False)
        kw.setdefault("base_branch", "main")
        return driver.drive(
            packet_path or self.packet_path, self.repo_root,
            runner=runner, auditctl_bin=str(self.auditctl), **kw,
        )

    def _retry(self, report: dict) -> Any:
        """The report key itself is part of the contract, present even at None."""
        self.assertIn("retry", report, "report has no 'retry' key")
        return report["retry"]

    def _retry_packet_path(self) -> Path:
        packet = json.loads(self.packet_path.read_text(encoding="utf-8"))
        return driver.worktree_path(packet).parent / "T-DRIVER.attempt-2.json"

    # 1. The bound itself. Without a named constant a reader cannot tell one
    # retry from an unbounded loop that happens to stop.
    def test_max_gate_attempts_is_two(self):
        self.assertEqual(driver.MAX_GATE_ATTEMPTS, 2)

    # 2. Red then green: one retry, and the retry is the cheap one.
    def test_red_then_green_spends_exactly_one_retry(self):
        runner = self._runner(gate_script=[RED_GATE, GREEN_GATE])
        code, report = self._drive(runner)
        retry = self._retry(report)
        self.assertIsNotNone(retry, "a red first gate must spend a retry")
        self.assertEqual(retry["attempt"], 2)
        self.assertTrue(retry.get("reason"), "the retry records why it was spent")
        # prepare is what makes a dispatch expensive: the worktree already
        # exists and its cold gates are no longer red, so re-running it would
        # buy nothing. Exactly these three stages repeat.
        self.assertEqual(
            runner.steps(),
            ["prepare", "run", "gate", "receipt", "run", "gate", "receipt"],
        )
        self.assertEqual(runner.steps().count("prepare"), 1)
        # Every step entry says which attempt it belongs to, or a report reader
        # cannot tell the first pass from the retried one.
        self.assertEqual(
            [(s["step"], s["attempt"]) for s in report["steps"]],
            [
                ("prepare", 1), ("run", 1), ("gate", 1), ("receipt", 1),
                ("run", 2), ("gate", 2), ("receipt", 2),
            ],
        )
        self.assertIsNone(report["stop"])
        self.assertEqual(code, 0)
        self.assertEqual(len(runner.gh_calls()), 1, "a green retry opens the PR")
        self.assertTrue(report["pr"]["opened"])

    # 3. The retry packet is the frozen packet plus the gate output, and
    # nothing else: a retry that quietly widens the sandbox is not a retry.
    def test_retry_packet_is_the_frozen_packet_plus_retry_context(self):
        runner = self._runner(gate_script=[RED_GATE, GREEN_GATE])
        _, report = self._drive(runner)
        retry = self._retry(report)
        self.assertIsNotNone(retry, "a red first gate must spend a retry")
        written = Path(retry["packet_path"])
        self.assertEqual(written, self._retry_packet_path())
        self.assertTrue(written.exists(), f"retry packet {written} was not written")
        frozen = json.loads(self.packet_path.read_text(encoding="utf-8"))
        retried = json.loads(written.read_text(encoding="utf-8"))

        # A packet with no attempt key is attempt 1, so the retry is 2.
        self.assertEqual(retried["attempt"], 2)
        context = retried["retry_context"]
        self.assertEqual(context["attempt"], 2)
        self.assertIn(RED_STDOUT_MARK, context["stdout_tail"])
        self.assertIn(RED_STDERR_MARK, context["stderr_tail"])
        # The purpose is what actually reaches the worker. A sibling key the
        # prompt never renders tells the model nothing about why it was red.
        self.assertTrue(retried["purpose"].startswith(frozen["purpose"]))
        self.assertIn("retry_context:", retried["purpose"])
        self.assertIn(RED_STDOUT_MARK, retried["purpose"])
        self.assertIn(RED_STDERR_MARK, retried["purpose"])

        for key, value in frozen.items():
            if key == "purpose":
                continue
            self.assertEqual(retried.get(key), value, f"retry packet changed {key!r}")
        self.assertEqual(
            set(retried) - set(frozen), {"attempt", "retry_context"},
            "the retry packet added keys beyond attempt and retry_context",
        )

    # 4. The retried stages must read the retry packet; passing the frozen path
    # would run the same dispatch again and call it a retry.
    def test_retried_stages_are_invoked_with_the_retry_packet(self):
        runner = self._runner(gate_script=[RED_GATE, GREEN_GATE])
        _, report = self._drive(runner)
        self.assertIsNotNone(self._retry(report), "a red first gate must spend a retry")
        frozen = str(self.packet_path)
        expected_retry = str(self._retry_packet_path())
        self.assertEqual(
            runner.packets(),
            [
                ("prepare", frozen), ("run", frozen), ("gate", frozen), ("receipt", frozen),
                ("run", expected_retry), ("gate", expected_retry), ("receipt", expected_retry),
            ],
        )

    # 5. Red twice hands over to M-1's stop rather than retrying again.
    def test_red_gate_twice_stops_and_never_makes_a_third_attempt(self):
        runner = self._runner(gate_script=[RED_GATE, RED_GATE])
        code, report = self._drive(runner)
        self.assertIsNotNone(self._retry(report), "the first red still spends its retry")
        self.assertIsNotNone(report["stop"], "a second red gate fires a stop condition")
        self.assertEqual(report["stop"]["condition"], "gate-red-twice")
        self.assertNotEqual(code, 0)
        self.assertEqual(runner.gate_calls, 2, "MAX_GATE_ATTEMPTS bounds the gate at two")
        audit = runner.audit_calls()
        self.assertEqual(len(audit), 1, "the stop escalates exactly once")
        self.assertEqual(audit[0][1:4], ["add", "--type", "workflow.escalation"])
        # A stop is the driver refusing to hand work onward, and the PR is the
        # hand-off: it must not exist in any form.
        self.assertEqual(runner.gh_calls(), [])

    # 6. The negative case: nothing was red, so nothing is spent.
    def test_green_first_gate_spends_no_retry(self):
        runner = self._runner(gate_script=[GREEN_GATE])
        code, report = self._drive(runner)
        self.assertIsNone(self._retry(report), "a green gate must not spend a retry")
        self.assertEqual(code, 0)
        self.assertEqual(runner.steps(), ["prepare", "run", "gate", "receipt"])
        self.assertEqual([s["attempt"] for s in report["steps"]], [1, 1, 1, 1])
        self.assertEqual(len(runner.gh_calls()), 1)
        self.assertTrue(report["pr"]["opened"])
        self.assertFalse(
            self._retry_packet_path().exists(), "no retry, no retry packet on disk",
        )

    # 7. The retry answers a red gate specifically. A stage that exited non-zero
    # never produced a verdict to feed back, so it escalates as it does today.
    def test_run_failure_escalates_without_a_retry(self):
        runner = self._runner(gate_script=[GREEN_GATE], exits={"run": 3})
        code, report = self._drive(runner)
        self.assertIsNone(self._retry(report), "a stage failure is not a red gate")
        self.assertNotEqual(code, 0)
        self.assertEqual(runner.steps(), ["prepare", "run"])
        self.assertEqual(runner.gate_calls, 0)
        self.assertEqual(runner.gh_calls(), [])

    # 8. The receipt is the PR body and the durable record; a reviewer reading
    # it has to see that this result came from the second attempt.
    def test_final_receipt_carries_the_attempt_number(self):
        runner = self._runner(gate_script=[RED_GATE, GREEN_GATE])
        _, report = self._drive(runner)
        self.assertIsNotNone(self._retry(report), "a red first gate must spend a retry")
        receipt = json.loads(Path(report["receipt_path"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["attempt"], 2)

    # 9. "Must not change": a post-gate stop means the packet is wrong, not the
    # worker, so re-running the worker against the same packet is wasted spend.
    def test_post_gate_stop_spends_no_retry(self):
        runner = self._runner(
            gate_script=[(0, "candidate", {"touched_paths": ["src/a.py", "infra/prod.tf"]})],
        )
        code, report = self._drive(runner)
        self.assertIsNone(self._retry(report), "a wrong packet is not retried")
        self.assertEqual(report["stop"]["condition"], "path-outside-writable")
        self.assertNotEqual(code, 0)
        self.assertEqual(runner.gate_calls, 1)


if __name__ == "__main__":
    unittest.main()
