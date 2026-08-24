"""Coordinator-authored oracle for spec row M-9 — the driver commits the diff.

M-8 taught the PR step to add a remote and push, and both work. The branch it
pushes still points at the packet's ``starting_commit``: nothing ever commits
the worker's work. ``post_gates`` reads the diff out of the working tree with
``git diff --name-only <starting_commit>``, and there it stays, uncommitted,
until the worktree is deleted. V5-M6a and V5-M6b pushed branches that carried
nothing. M-9 makes the PR step commit the worktree onto the packet branch
before the remote is added.

Written against the M-9 spec only: the driver runs no ``git commit`` today, so
every test here fails.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"

#: The packet branch, and a base branch that shares nothing with it.
BRANCH = "hybrid/t-driver"
BASE_BRANCH = "trunk-never-pushed"

#: A 40-hex starting_commit for the fake-runner fixtures. Real hex, because the
#: commit message is required to carry a short form of it.
STARTING_COMMIT = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"

#: What the fake ``git`` answers when asked for the new commit's sha.
COMMITTED_SHA = "fedcba9876543210fedcba9876543210fedcba98"

RESOLVED_URL = "git@example.invalid:coordinator/repo.git"

#: The two files the real-git fixture dirties: one already tracked, one the
#: worker created. The untracked one is the whole point — ``git commit -a``
#: would silently drop it.
TRACKED = "tracked.txt"
UNTRACKED = "added.txt"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_commit_subject", SCRIPTS / "dispatch_release.py")


class FakeRunner:
    """Scripted stand-in for subprocess: records every command and its cwd.

    ``exits`` is keyed by stage name, by ``gh``, and by the PR step names, so a
    fixture can fail the commit alone. ``resolve_url`` of ``None`` makes the
    read-only origin query fail the way it does in a checkout with no remote.
    """

    def __init__(
        self,
        auditctl_bin: str,
        exits: dict[str, int] | None = None,
        disposition: str = "candidate",
        resolve_url: str | None = RESOLVED_URL,
        gate_extra: dict[str, Any] | None = None,
    ):
        self.auditctl_bin = auditctl_bin
        self.exits = exits or {}
        self.disposition = disposition
        self.resolve_url = resolve_url
        self.gate_extra = gate_extra or {}
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        if cmd[0] == self.auditctl_bin:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        if cmd[0] == "gh":
            return subprocess.CompletedProcess(
                cmd, self.exits.get("gh", 0), "https://example/pr/1\n", "",
            )
        if cmd[0] == "git":
            return self._git(cmd)
        step = cmd[-1]
        code = self.exits.get(step, 0)
        payload: dict[str, Any] = {"stage": step}
        if step == "gate":
            payload["disposition"] = self.disposition
            payload["evidence"] = dict(self.gate_extra)
        return subprocess.CompletedProcess(cmd, code, json.dumps(payload), "boom" if code else "")

    def _git(self, cmd):
        if "commit" in cmd:
            code = self.exits.get("commit", 0)
            # Real ``git commit`` prints "[branch <short>] <subject>". Offered
            # so a driver that reads the sha off the commit itself and one that
            # asks ``rev-parse`` afterwards are both satisfied.
            out = f"[{BRANCH} {COMMITTED_SHA[:7]}] committed\n" if not code else ""
            return subprocess.CompletedProcess(cmd, code, out, "boom" if code else "")
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, COMMITTED_SHA + "\n", "")
        if "remote" in cmd and "add" not in cmd:
            if self.resolve_url is None:
                return subprocess.CompletedProcess(
                    cmd, 2, "", "error: No such remote 'origin'",
                )
            return subprocess.CompletedProcess(cmd, 0, self.resolve_url + "\n", "")
        name = "remote-add" if "remote" in cmd and "add" in cmd else (
            "push" if "push" in cmd else "git"
        )
        code = self.exits.get(name, 0)
        return subprocess.CompletedProcess(cmd, code, "", "boom" if code else "")

    def git_calls(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.calls if c[0] == "git"]

    def commits(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "commit" in c]

    def remote_adds(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "remote" in c and "add" in c]

    def pushes(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "push" in c]

    def gh_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == "gh"]

    def audit_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == self.auditctl_bin]

    def index_of(self, predicate) -> int:
        for i, (cmd, cwd) in enumerate(self.calls):
            if predicate(cmd, cwd):
                return i
        return -1


class _DriverFixture(unittest.TestCase):
    """Temp dirs, a reachable auditctl path, and a packet — shared setUp."""

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

    def _packet(self, starting_commit: str = STARTING_COMMIT, **extra: Any) -> Path:
        packet = {
            "task_id": "T-DRIVER",
            "repo_id": "repo-x",
            "starting_commit": starting_commit,
            "worktree": {"root": str(self.tmp / "wt"), "branch": BRANCH},
        }
        packet.update(extra)
        path = self.tmp / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def _worktree(self, packet_path: Path) -> Path:
        return driver.worktree_path(json.loads(packet_path.read_text(encoding="utf-8")))

    def _drive(self, packet_path: Path, runner, **kw):
        kw.setdefault("dry_run", False)
        kw.setdefault("base_branch", BASE_BRANCH)
        return driver.drive(
            packet_path, self.repo_root, runner=runner, auditctl_bin=str(self.auditctl), **kw,
        )


class CommitStepTests(_DriverFixture):
    def _runner(self, **kw) -> FakeRunner:
        return FakeRunner(str(self.auditctl), **kw)

    def _require_commit_step(self) -> None:
        """A fixture that asserts the commit did *not* happen proves nothing
        while there is no commit step at all, so each one pins the behaviour it
        is guarding first."""
        self.assertIn(
            "commit", driver.PR_STEP_NAMES, "the PR step has no commit to skip",
        )

    # 1. The step vocabulary. M-9 supersedes M-8's three names: a reader of a
    # failed report has to be able to tell "the commit would not be made" from
    # the three failures M-8 already names, and the ORDER of those four is the
    # contract the fixtures below assert the driver against.
    #
    # What this must not assert is the whole tuple. M-9's original form pinned
    # it exactly, which made this oracle fail the moment M-10c inserted
    # receipt-capture at the head -- a change M-10c's own spec row requires.
    # An oracle that forbids the next specified change is over-specified, and
    # because templates/dispatch/tests/** is protected no worker could ever
    # reconcile the two. M-9's contract is the relative order of its own four
    # names; what precedes them belongs to whoever adds it.
    def test_pr_step_names_keep_m9s_four_in_order(self):
        names = driver.PR_STEP_NAMES
        for name in ("commit", "remote-add", "push", "pr-create"):
            self.assertIn(name, names, f"the PR step lost {name}")
        self.assertEqual(
            [n for n in names if n in {"commit", "remote-add", "push", "pr-create"}],
            ["commit", "remote-add", "push", "pr-create"],
            "M-9's four sub-steps are out of order",
        )

    # 2. The order is the row: a push before the commit is exactly the bug --
    # it puts starting_commit on the remote and gh opens an empty PR.
    def test_candidate_commits_in_the_worktree_before_remote_add_push_and_gh(self):
        packet = self._packet()
        runner = self._runner()
        code, _ = self._drive(packet, runner)
        self.assertEqual(code, 0)

        commits = runner.commits()
        self.assertEqual(len(commits), 1, "the PR step commits exactly once")
        self.assertEqual(
            commits[0][1], self._worktree(packet),
            "the commit is made in the worktree, not the coordinator checkout",
        )

        i_commit = runner.index_of(lambda c, _: c[0] == "git" and "commit" in c)
        i_add = runner.index_of(lambda c, _: c[0] == "git" and "remote" in c and "add" in c)
        i_push = runner.index_of(lambda c, _: c[0] == "git" and "push" in c)
        i_gh = runner.index_of(lambda c, _: c[0] == "gh")
        self.assertLess(i_commit, i_add, "the commit precedes the remote")
        self.assertLess(i_commit, i_push, "a push before the commit pushes starting_commit")
        self.assertLess(i_commit, i_gh)

    # 3. REQ-005: the coordinator checkout is not the worker's workspace. Every
    # git command the driver runs outside the worktree stays read-only, and the
    # commit in particular never stages anything there.
    def test_the_commit_path_never_runs_git_outside_the_worktree(self):
        self._require_commit_step()
        packet = self._packet()
        runner = self._runner()
        code, _ = self._drive(packet, runner)
        self.assertEqual(code, 0)
        worktree = self._worktree(packet)
        mutating = frozenset({"add", "commit", "push", "checkout", "merge", "init"})
        for cmd, cwd in runner.git_calls():
            if cwd == worktree:
                continue
            self.assertFalse(
                mutating & set(cmd), f"git writes outside the worktree: {cmd} (cwd={cwd})",
            )

    # 4. Three dispatches were finished by hand because the report did not say
    # what had been handed onward. The sha is what makes "the branch carried
    # the work" checkable after the worktree is gone.
    def test_report_pr_records_the_commit_sha(self):
        runner = self._runner()
        _, report = self._drive(self._packet(), runner)
        self.assertIn("commit", report["pr"], "report['pr'] has no commit record")
        sha = report["pr"]["commit"]["sha"]
        # Full or abbreviated: the driver may read the sha off the commit's own
        # output or ask rev-parse afterwards, and the spec fixes neither.
        self.assertGreaterEqual(len(sha), 7)
        self.assertTrue(COMMITTED_SHA.startswith(sha), f"not the sha that was committed: {sha}")

    # 5. A commit that fails is the hand-off failing, and is escalated exactly
    # like M-8's other sub-steps. Nothing after it may run: a remote-add and a
    # push over an uncommitted worktree is the empty PR this row removes.
    def test_failed_commit_escalates_once_and_never_reaches_remote_push_or_gh(self):
        runner = self._runner(exits={"commit": 128})
        code, report = self._drive(self._packet(), runner)
        self.assertNotEqual(code, 0)
        self.assertEqual(runner.remote_adds(), [])
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.gh_calls(), [])
        audit = runner.audit_calls()
        self.assertEqual(len(audit), 1, "the failure escalates exactly once")
        self.assertEqual(audit[0][1:4], ["add", "--type", "workflow.escalation"])
        self.assertEqual(report["escalation"]["metadata"]["step"], "pr")
        self.assertEqual(report["pr"]["failed_step"], "commit")
        self.assertFalse(report["pr"]["opened"])

    # 6. A dry run is a rehearsal. It leaves the worktree exactly as the worker
    # left it, the same way it adds no remote and pushes nothing.
    def test_dry_run_commits_nothing(self):
        self._require_commit_step()
        runner = self._runner()
        code, report = self._drive(self._packet(), runner, dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(runner.commits(), [], "a dry run must not touch the worktree")
        self.assertTrue(report["pr"]["skipped"])

    # 7. A disposition the driver cannot vouch for is work that is not handed
    # onward, and a commit on the packet branch is part of the hand-off.
    # Attempt 2 in the packet is what makes this a skip rather than the
    # gate-red-twice stop.
    def test_non_candidate_disposition_reaches_no_commit(self):
        self._require_commit_step()
        runner = self._runner(exits={"gate": 2}, disposition="coordinator_review_required")
        code, report = self._drive(self._packet(attempt=2), runner)
        self.assertEqual(code, 0)
        self.assertTrue(report["pr"]["skipped"])
        self.assertEqual(runner.commits(), [])

    # 8. Every L-2 stop condition means the driver hands nothing onward, and
    # the commit is now the first thing it would hand onward.
    def test_every_stop_condition_reaches_no_commit(self):
        self._require_commit_step()
        cases = {
            "release-boundary": ({"release_boundary": True}, {}),
            "command-not-allowed": (
                {"allowed_command_ids": ["pytest"], "oracle": {"starts_red": "curl-the-internet"}},
                {},
            ),
            "path-outside-writable": (
                {"writable_patch_paths": ["src/**"]},
                {"touched_paths": ["src/a.py", "infra/prod.tf"]},
            ),
        }
        for condition, (extra, gate_extra) in cases.items():
            with self.subTest(condition=condition):
                runner = self._runner(gate_extra=gate_extra)
                code, report = self._drive(self._packet(**extra), runner)
                self.assertEqual(report["stop"]["condition"], condition)
                self.assertNotEqual(code, 0)
                self.assertEqual(runner.commits(), [])

    def test_gate_red_twice_reaches_no_commit(self):
        self._require_commit_step()
        packet = self._packet()
        for _ in range(2):
            runner = self._runner(exits={"gate": 2}, disposition="coordinator_review_required")
            code, report = self._drive(packet, runner)
        self.assertEqual(report["stop"]["condition"], "gate-red-twice")
        self.assertNotEqual(code, 0)
        self.assertEqual(runner.commits(), [])

    # 9. The commit comes before the remote, so an unresolvable remote finds
    # the work already committed. The packet stays green -- a coordinator can
    # push that branch by hand later, which is only possible if it has the work
    # on it.
    def test_unresolvable_remote_still_commits_and_skips_the_pr(self):
        runner = self._runner(resolve_url=None)
        code, report = self._drive(self._packet(), runner)
        self.assertEqual(code, 0)
        self.assertEqual(len(runner.commits()), 1, "the commit precedes remote resolution")
        self.assertEqual(runner.remote_adds(), [])
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.gh_calls(), [])
        self.assertTrue(report["pr"]["skipped"])
        self.assertIsNone(report["stop"])


# The real-git proof of this row -- "the branch tip is a new commit whose
# parent is starting_commit, and its diff against it lists exactly the touched
# paths" -- lives in the sibling test_realgit_dispatch_commit.py, and must stay
# out of this file. This one is the packet's starts_red command, traced under
# strace at freeze time, and the trace resolves git's own AT_FDCWD-relative
# reads (refs/heads/main, objects/pack) against the checkout rather than
# against the temp repo they actually came from. A real git here fails the
# freeze with reads_outside_declared_paths. Plain ``discover`` still runs the
# sibling, so nothing is lost by the split.


if __name__ == "__main__":
    unittest.main()
