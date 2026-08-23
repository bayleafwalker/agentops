"""Coordinator-authored oracle for the L-1 driver (V5-P3, REQ-001..REQ-005)."""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release", SCRIPTS / "dispatch_release.py")


def _packet(tmp: Path) -> Path:
    packet = {
        "task_id": "T-DRIVER",
        "repo_id": "repo-x",
        "starting_commit": "0" * 40,
        "worktree": {"root": str(tmp / "wt"), "branch": "hybrid/t-driver"},
    }
    path = tmp / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    return path


class FakeRunner:
    """Scripted stand-in for subprocess: records every command and its cwd."""

    def __init__(self, exits: dict[str, int], dispositions: dict[str, str] | None = None):
        self.exits = exits
        self.dispositions = dispositions or {}
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        if cmd[0] == "auditctl":
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(cmd, self.exits.get("gh", 0), "https://example/pr/1\n", "")
        step = cmd[-1]
        code = self.exits.get(step, 0)
        payload = {"stage": step}
        if step == "gate":
            payload["disposition"] = self.dispositions.get("gate", "candidate")
        if step == "run":
            payload["worker_session"] = {
                "session_id": "ses_1", "path": "/tmp/wt/T-DRIVER.worker-session.json", "sha256": "ab" * 32,
            }
        return subprocess.CompletedProcess(cmd, code, json.dumps(payload), "boom" if code else "")

    def steps(self):
        return [c[-1] for c, _ in self.calls if c[0] != "auditctl" and c[0] != "gh"]


class DriverTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.packet = _packet(self.tmp)
        self.repo_root = self.tmp / "coordinator"
        self.repo_root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _drive(self, runner, **kw):
        kw.setdefault("dry_run", False)
        kw.setdefault("base_branch", "main")
        kw.setdefault("auditctl_bin", "auditctl")
        return driver.drive(self.packet, self.repo_root, runner=runner, **kw)

    # REQ-001 — step order is fixed and a failure stops the sequence
    def test_req001_order_is_fixed_and_not_configurable(self):
        self.assertEqual(driver.STEPS, ("prepare", "run", "gate", "receipt"))
        self.assertIsInstance(driver.STEPS, tuple)
        import inspect
        self.assertNotIn("steps", inspect.signature(driver.drive).parameters)
        runner = FakeRunner({})
        code, report = self._drive(runner, dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(runner.steps(), ["prepare", "run", "gate", "receipt"])

    def test_req001_failure_stops_later_steps(self):
        for failing in ("prepare", "run", "gate"):
            with self.subTest(failing=failing):
                runner = FakeRunner({failing: 3})
                code, report = self._drive(runner)
                self.assertNotEqual(code, 0)
                expected = list(driver.STEPS[: driver.STEPS.index(failing) + 1])
                self.assertEqual(runner.steps(), expected)
                self.assertFalse(any(c[0] == "gh" for c, _ in runner.calls))

    # REQ-002 — the driver never merges
    def test_req002_source_has_no_merge_or_default_branch_push(self):
        src = (SCRIPTS / "dispatch_release.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r'"merge"')
        self.assertNotRegex(src, r"pr\s*merge")
        self.assertNotRegex(src, r'"push"')
        self.assertNotRegex(src, r"git\s+(merge|push)")

    def test_req002_only_gh_call_is_pr_create(self):
        runner = FakeRunner({})
        code, report = self._drive(runner)
        self.assertEqual(code, 0)
        gh_calls = [c for c, _ in runner.calls if c[0] == "gh"]
        self.assertEqual(len(gh_calls), 1)
        self.assertEqual(gh_calls[0][1:3], ["pr", "create"])
        self.assertNotIn("merge", " ".join(gh_calls[0]))

    def test_req002_pr_skipped_with_reason_when_not_candidate(self):
        # Amended for L-4 (spec M-2, Amendment 1). This used to pin "a red gate
        # exits 0 with the PR skipped and a reason"; L-4 replaced that mechanism
        # with one cheap retry and then the gate-red-twice stop, so do not
        # restore the old assertions. REQ-002's actual requirement is unchanged
        # and still pinned below: work the driver cannot vouch for is never
        # handed off -- no gh, no PR.
        runner = FakeRunner({"gate": 2}, {"gate": "coordinator_review_required"})
        code, report = self._drive(runner)
        self.assertNotEqual(code, 0)
        self.assertEqual(report["stop"]["condition"], "gate-red-twice")
        self.assertFalse(any(c[0] == "gh" for c, _ in runner.calls))
        self.assertFalse((report["pr"] or {}).get("opened"))
        # The retry is cheap (the worktree already exists, so prepare is not
        # re-run) and bounded (MAX_GATE_ATTEMPTS): one prepare, two gates.
        self.assertEqual(runner.steps().count("prepare"), 1)
        self.assertEqual(runner.steps().count("gate"), driver.MAX_GATE_ATTEMPTS)

    # REQ-003 — the receipt is attached to the PR
    def test_req003_receipt_written_before_pr_and_is_the_body(self):
        seen = {}

        class Probe(FakeRunner):
            def __call__(self, cmd, cwd):
                if cmd[0] == "gh":
                    body = Path(cmd[cmd.index("--body-file") + 1])
                    seen["existed"] = body.exists()
                    seen["body"] = json.loads(body.read_text()) if body.exists() else None
                return super().__call__(cmd, cwd)

        runner = Probe({})
        code, report = self._drive(runner)
        self.assertEqual(code, 0)
        self.assertTrue(seen["existed"])
        self.assertEqual(seen["body"]["stage"], "receipt")
        self.assertEqual(seen["body"]["gate"]["disposition"], "candidate")
        self.assertEqual(report["pr"]["body_file"], report["receipt_path"])
        self.assertTrue(report["pr"]["opened"])

    def test_req003_dry_run_does_everything_but_open(self):
        runner = FakeRunner({})
        code, report = self._drive(runner, dry_run=True)
        self.assertEqual(code, 0)
        self.assertTrue(Path(report["receipt_path"]).exists())
        self.assertFalse(any(c[0] == "gh" for c, _ in runner.calls))
        self.assertTrue(report["pr"]["skipped"])
        self.assertEqual(report["pr"]["command"][:3], ["gh", "pr", "create"])
        self.assertIn("dry-run", report["pr"]["reason"])

    # REQ-004 — a failed step escalates rather than continuing
    def test_req004_failure_writes_escalation_and_exits_nonzero(self):
        runner = FakeRunner({"run": 4})
        code, report = self._drive(runner)
        self.assertEqual(code, 4)
        audit = [c for c, _ in runner.calls if c[0] == "auditctl"]
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0][1:4], ["add", "--type", "workflow.escalation"])
        self.assertEqual(report["escalation"]["sink"], "auditctl")
        self.assertEqual(report["escalation"]["metadata"]["step"], "run")
        self.assertEqual(runner.steps(), ["prepare", "run"])

    def test_req004_gate_without_disposition_is_a_failure(self):
        class NoVerdict(FakeRunner):
            def __call__(self, cmd, cwd):
                r = super().__call__(cmd, cwd)
                if cmd[-1] == "gate":
                    return subprocess.CompletedProcess(cmd, 3, "hybrid-dispatch: claim expired", "")
                return r

        runner = NoVerdict({})
        code, report = self._drive(runner)
        self.assertEqual(code, 3)
        self.assertEqual(runner.steps(), ["prepare", "run", "gate"])
        self.assertIsNotNone(report["escalation"])

    def test_req004_missing_auditctl_degrades_but_still_fails(self):
        runner = FakeRunner({"prepare": 2})
        code, report = self._drive(runner, auditctl_bin="/nonexistent/auditctl")
        self.assertEqual(code, 2)
        self.assertEqual(report["escalation"]["sink"], "unavailable")

    # REQ-005 — the coordinator checkout is untouched
    def test_req005_no_git_anywhere_and_pr_runs_in_worktree(self):
        runner = FakeRunner({})
        code, report = self._drive(runner)
        self.assertEqual(code, 0)
        for cmd, cwd in runner.calls:
            self.assertNotEqual(cmd[0], "git", cmd)
            self.assertNotEqual(cwd, self.repo_root, cmd)
        gh = [(c, cwd) for c, cwd in runner.calls if c[0] == "gh"]
        self.assertEqual(gh[0][1], driver.worktree_path(json.loads(self.packet.read_text())))
        src = (SCRIPTS / "dispatch_release.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r'\[\s*"git"', src))
        self.assertNotIn('"-C"', src)

    def test_cli_dry_run_end_to_end_with_stubbed_hybrid(self):
        # Exercise main() argument plumbing against a stub python that echoes a receipt.
        stub = self.tmp / "py"
        stub.write_text(
            "#!/bin/sh\nstep=$(eval echo \\${$#})\n"
            "printf '{\"stage\":\"%s\",\"disposition\":\"candidate\"}' \"$step\"\n"
        )
        stub.chmod(0o755)
        code, report = driver.drive(
            self.packet, self.repo_root, dry_run=True, base_branch="main", python_bin=str(stub),
        )
        self.assertEqual(code, 0)
        self.assertEqual([s["step"] for s in report["steps"]], list(driver.STEPS))
        self.assertTrue(report["pr"]["skipped"])


class StageReceiptTests(unittest.TestCase):
    """A stage's receipt is the only record of what it observed. Keeping only
    stderr made a run that finished cleanly and changed nothing look identical
    to one that never reached the model."""

    def test_each_step_keeps_the_receipt_it_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runner = FakeRunner({})
            code, report = driver.drive(
                _packet(tmp_path), tmp_path, dry_run=True, runner=runner,
                base_branch="main", auditctl_bin="auditctl",
            )
            self.assertEqual(code, 0)
            for entry in report["steps"]:
                self.assertIn("receipt", entry, f"{entry['step']} dropped its receipt")
                self.assertEqual(entry["receipt"]["stage"], entry["step"])

    def test_worker_session_path_reaches_the_final_receipt(self) -> None:
        """L-1b: the PR body is the receipt file, so the transcript's location
        has to be in it or a reviewer cannot find the transcript."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            code, report = driver.drive(
                _packet(tmp_path), tmp_path, dry_run=True, runner=FakeRunner({}),
                base_branch="main", auditctl_bin="auditctl",
            )
            self.assertEqual(code, 0)
            final = json.loads(Path(report["receipt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(final["worker_session"]["path"], "/tmp/wt/T-DRIVER.worker-session.json")
            self.assertEqual(final["worker_session"]["sha256"], "ab" * 32)

    def test_unparseable_stdout_is_kept_as_a_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            class NoisyRunner(FakeRunner):
                def __call__(self, cmd, cwd):
                    result = super().__call__(cmd, cwd)
                    if cmd[-1] == "prepare":
                        return subprocess.CompletedProcess(cmd, 0, "not json at all", "")
                    return result

            runner = NoisyRunner({})
            _, report = driver.drive(
                _packet(tmp_path), tmp_path, dry_run=True, runner=runner,
                base_branch="main", auditctl_bin="auditctl",
            )
            prepare = [e for e in report["steps"] if e["step"] == "prepare"][0]
            self.assertNotIn("receipt", prepare)
            self.assertEqual(prepare["stdout_tail"], "not json at all")


if __name__ == "__main__":
    unittest.main()
