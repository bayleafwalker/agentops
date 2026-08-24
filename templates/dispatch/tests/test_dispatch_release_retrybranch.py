"""Coordinator-authored oracle for spec row M-13 — a retry must be able to push.

V5-M12 attempt 2 produced a correct diff, passed every gate, and then died at
the push:

    ! [rejected] hybrid/v5-m12-scan-hardening -> hybrid/v5-m12-scan-hardening
    hint: Updates were rejected because the remote contains work that you do
    hint: not have locally.

The packet's branch name is fixed in ``worktree.branch``, and attempt 1 had
already pushed it. Every retry that reaches the PR step hits this; none had
reached it before, which is why it surfaced only now.

Force-pushing is the wrong answer. Attempt 1's branch is evidence -- its diff
is what the retry was authored against, and V5-M12's rejection notice points at
it -- so a retry gets its own branch and leaves the earlier one alone. That is
the same ruling the owner made about the attempt counter: the record stays
honest and the mechanism moves.

Written against the M-13 spec row only.
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

BRANCH = "hybrid/t-driver"
TASK_ID = "T-DRIVER"
STARTING_COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
COMMITTED_SHA = "fedcba9876543210fedcba9876543210fedcba98"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load("dispatch_release_retrybranch_subject", SCRIPTS / "dispatch_release.py")


class Runner:
    """Records every command; answers the ones the PR step needs."""

    def __init__(self, auditctl: str):
        self.calls: list[tuple[list[str], Any]] = []
        self.auditctl = auditctl

    def __call__(self, cmd, cwd=None):
        self.calls.append((list(cmd), cwd))
        if cmd[0] == "git" and "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, COMMITTED_SHA + "\n", "")
        if cmd[0] == "git" and cmd[1] == "remote" and "get-url" in cmd:
            return subprocess.CompletedProcess(
                cmd, 0, "git@example.invalid:c/repo.git\n", "")
        stage = cmd[-1]
        payload: dict[str, Any] = {"stage": stage, "task_id": TASK_ID}
        if stage == "run":
            payload["worker"] = {"exit_code": 0, "stdout": "{}\n", "stderr": ""}
            payload["spend"] = {"cost_usd": 0.01, "tokens": 100}
        if stage == "gate":
            payload["disposition"] = "candidate"
            payload["evidence"] = {"passed": True, "gates": {"diff-nonempty": True}}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

    def pushes(self):
        return [c for c, _ in self.calls if c[0] == "git" and "push" in c]

    def gh(self):
        return [c for c, _ in self.calls if c[0] == "gh"]


class RetryBranchTests(unittest.TestCase):
    """§M-13 — a retry pushes somewhere it is allowed to push."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "coordinator"
        self.repo_root.mkdir()
        self.auditctl = self.tmp / "auditctl"
        self.auditctl.write_text("", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _resolve(self, attempt=None):
        fn = getattr(driver, "packet_branch", None)
        self.assertIsNotNone(
            fn, "the driver has no packet_branch; the branch is still fixed",
        )
        packet: dict[str, Any] = {"worktree": {"branch": BRANCH}}
        if attempt is not None:
            packet["attempt"] = attempt
        return fn(packet)

    # 1. The name a first attempt pushes is unchanged. Every packet merged to
    # date used it, and renaming them retroactively would orphan their history.
    def test_a_first_attempt_keeps_the_declared_branch(self):
        self.assertEqual(self._resolve(1), BRANCH)
        self.assertEqual(self._resolve(None), BRANCH, "a packet with no attempt is the first")

    # 2. A retry gets its own, and says which attempt it is.
    def test_a_retry_gets_its_own_branch_naming_the_attempt(self):
        for attempt in (2, 3):
            with self.subTest(attempt=attempt):
                resolved = self._resolve(attempt)
                self.assertNotEqual(
                    resolved, BRANCH,
                    f"attempt {attempt} would push over attempt 1's branch",
                )
                self.assertIn(BRANCH, resolved, "the packet's branch is no longer recognisable")
                self.assertIn(str(attempt), resolved, "the branch does not name the attempt")
        self.assertNotEqual(
            self._resolve(2), self._resolve(3), "two retries collide with each other",
        )

    # 3. The one that actually broke: the push refspec and gh --head must name
    # the SAME remote branch, or the PR is opened against a ref that has nothing
    # on it. They are built in different places, which is how they can disagree.
    def test_the_push_and_the_pull_request_agree_on_the_remote_branch(self):
        for attempt in (1, 2):
            with self.subTest(attempt=attempt):
                packet_path = self.tmp / f"p{attempt}.json"
                packet_path.write_text(json.dumps({
                    "task_id": TASK_ID,
                    "repo_id": "repo-x",
                    "starting_commit": STARTING_COMMIT,
                    "attempt": attempt,
                    "worktree": {"root": str(self.tmp / "wt"), "branch": BRANCH},
                }), encoding="utf-8")
                worktree = driver.worktree_path(json.loads(packet_path.read_text()))
                worktree.mkdir(parents=True, exist_ok=True)
                runner = Runner(str(self.auditctl))
                code, report = driver.drive(
                    packet_path, self.repo_root, runner=runner,
                    auditctl_bin=str(self.auditctl), base_branch="trunk", dry_run=False,
                )
                self.assertEqual(code, 0, json.dumps(report.get("pr"), indent=2))
                pushes = runner.pushes()
                self.assertTrue(pushes, "nothing was pushed")
                refspec = pushes[0][-1]
                remote_ref = refspec.split(":")[-1]
                gh = runner.gh()
                self.assertTrue(gh, "gh pr create never ran")
                head = gh[0][gh[0].index("--head") + 1]
                self.assertEqual(
                    head, remote_ref,
                    "gh --head names a different branch than the one pushed; the PR "
                    "would be opened against a ref that has nothing on it",
                )
                self.assertEqual(
                    remote_ref, self._resolve(attempt),
                    "the pushed branch is not the resolved one",
                )
                self.assertEqual(report["pr"]["push"]["branch"], remote_ref)

    # 4. A retry must not touch the earlier attempt's branch at all: it is the
    # evidence the retry was authored against.
    def test_a_retry_never_writes_over_the_earlier_branch(self):
        packet_path = self.tmp / "p.json"
        packet_path.write_text(json.dumps({
            "task_id": TASK_ID, "repo_id": "repo-x",
            "starting_commit": STARTING_COMMIT, "attempt": 2,
            "worktree": {"root": str(self.tmp / "wt"), "branch": BRANCH},
        }), encoding="utf-8")
        worktree = driver.worktree_path(json.loads(packet_path.read_text()))
        worktree.mkdir(parents=True, exist_ok=True)
        runner = Runner(str(self.auditctl))
        code, _ = driver.drive(
            packet_path, self.repo_root, runner=runner,
            auditctl_bin=str(self.auditctl), base_branch="trunk", dry_run=False,
        )
        self.assertEqual(code, 0)
        for cmd in runner.pushes():
            self.assertNotIn("--force", " ".join(cmd), "the retry force-pushed")
            self.assertNotIn("+", cmd[-1], "the refspec forces an update")
            self.assertNotEqual(
                cmd[-1].split(":")[-1], BRANCH,
                "the retry pushed onto attempt 1's branch",
            )


if __name__ == "__main__":
    unittest.main()
