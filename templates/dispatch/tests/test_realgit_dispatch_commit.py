"""Coordinator-authored oracle for spec row M-9 — the real-git half of the proof.

The ten fake-runner fixtures for this row live in the sibling
``test_dispatch_release_commit.py``, which is the packet's ``starts_red``
command. These two cannot: "the branch tip is a new commit whose parent is
``starting_commit``, and its diff against it lists exactly the touched paths"
is a claim about git's own behaviour, so proving it needs a real repository —
and the freeze-time strace resolves git's own ``AT_FDCWD``-relative reads
(``refs/heads/main``, ``objects/pack``) against the coordinator checkout rather
than against the temp repo they came from, failing the packet with
``reads_outside_declared_paths``.

Hence the filename: it must not match ``test_dispatch_release*.py``, the traced
glob, while plain ``unittest discover`` still picks it up for the full-suite
gate. Do not rename it into that glob, and do not move these fixtures back.

Written against the M-9 spec only: the driver runs no ``git commit`` today, so
both tests here fail.
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


driver = _load_module("dispatch_release_realgit_subject", SCRIPTS / "dispatch_release.py")


class _DriverFixture(unittest.TestCase):
    """Temp dirs, a reachable auditctl path, and a packet — shared setUp."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "coordinator"
        self.repo_root.mkdir()
        # An executable script is what write_escalation needs to treat the sink as
        # reachable: since the resolver was shared with the hooks it applies the
        # same guard everywhere -- executable, and not a compiled binary, because
        # the kernel audit tool answers to this name too. The runner is fake, so
        # nothing is ever executed; the file only has to be the right *shape*.
        self.auditctl = self.tmp / "auditctl"
        self.auditctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.auditctl.chmod(0o755)

    def tearDown(self):
        self._tmp.cleanup()

    def _packet(self, starting_commit: str, **extra: Any) -> Path:
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


class RealGitCommitTests(_DriverFixture):
    """The one fixture backed by a real repository.

    "The branch tip is a new commit whose parent is starting_commit, and its
    diff against starting_commit lists exactly the touched paths" is a claim
    about git's own behaviour; a scripted runner can only confirm which strings
    were passed to it. So this builds a throwaway repo, dirties a real worktree
    the way a worker does, and asserts on real ``git`` output.
    """

    def setUp(self):
        super().setUp()
        # An empty HOME plus no system config: the commit has to supply its own
        # identity. A host with a global user.name would hide that.
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(self.home),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }

    def _git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=self.env,
            text=True, capture_output=True, check=False,
        )

    def _git_ok(self, cwd: Path, *args: str) -> str:
        completed = self._git(cwd, *args)
        self.assertEqual(completed.returncode, 0, f"git {args}: {completed.stderr}")
        return completed.stdout.strip()

    def _setup_git(self, cwd: Path, *args: str) -> str:
        """Fixture-side git, which may name an identity the driver may not."""
        return self._git_ok(
            cwd, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args,
        )

    def _build_repo(self) -> tuple[Path, str]:
        """An origin repo with one commit, and a worker-shaped clone of it."""
        origin = self.tmp / "origin"
        origin.mkdir()
        self._git_ok(origin, "init", "-b", "main")
        (origin / TRACKED).write_text("original\n", encoding="utf-8")
        self._setup_git(origin, "add", TRACKED)
        self._setup_git(origin, "commit", "-m", "seed")
        starting = self._git_ok(origin, "rev-parse", "HEAD")

        worktree = self.tmp / "wt" / "repo-x" / "T-DRIVER"
        worktree.parent.mkdir(parents=True)
        self._git_ok(self.tmp, "clone", str(origin), str(worktree))
        # prepare_workspace removes origin from the worker's clone; the fixture
        # reproduces that, because it is why the PR step re-adds a remote.
        self._git_ok(worktree, "remote", "remove", "origin")
        self._git_ok(worktree, "checkout", "-b", BRANCH, starting)

        # What the worker leaves behind: a tracked file changed and a new file
        # created. The new file is the one a naive ``commit -a`` drops.
        (worktree / TRACKED).write_text("worker was here\n", encoding="utf-8")
        (worktree / UNTRACKED).write_text("new file\n", encoding="utf-8")
        return worktree, starting

    def _runner(self, worktree: Path, touched: list[str]):
        """Real git, fake everything else: the stages and gh never run for real,
        but every ``git`` the driver issues executes against the repo."""
        calls: list[tuple[list[str], Path | None]] = []

        def run(cmd, cwd):
            calls.append((list(cmd), cwd))
            if cmd[0] == "git":
                return subprocess.run(
                    cmd, cwd=cwd, env=self.env, text=True, capture_output=True, check=False,
                )
            if cmd[0] == str(self.auditctl) or cmd[0] == "gh":
                return subprocess.CompletedProcess(cmd, 0, "", "")
            step = cmd[-1]
            payload: dict[str, Any] = {"stage": step}
            if step == "gate":
                payload["disposition"] = "candidate"
                payload["evidence"] = {"touched_paths": list(touched)}
            return subprocess.CompletedProcess(cmd, 0, json.dumps(payload), "")

        run.calls = calls
        return run

    def test_commit_parents_starting_commit_and_carries_every_touched_path(self):
        worktree, starting = self._build_repo()
        # Proves the assertion below means something: if a global identity did
        # exist here, a driver that supplied none would still commit fine.
        self.assertEqual(
            self._git(worktree, "config", "--global", "user.email").returncode, 1,
            "the fixture's HOME already configures a git identity",
        )
        touched = sorted([TRACKED, UNTRACKED])
        packet = self._packet(starting_commit=starting)
        self.assertEqual(self._worktree(packet), worktree)

        # No push remote is resolvable from the coordinator checkout, so the PR
        # is skipped and the commit -- which precedes it -- is all that runs.
        code, report = self._drive(packet, self._runner(worktree, touched))
        self.assertEqual(code, 0, json.dumps(report.get("pr"), indent=2))

        tip = self._git_ok(worktree, "rev-parse", BRANCH)
        self.assertNotEqual(tip, starting, "the branch still points at starting_commit")
        self.assertEqual(
            self._git_ok(worktree, "rev-parse", BRANCH + "^"), starting,
            "the commit does not sit directly on starting_commit",
        )
        self.assertEqual(report["pr"]["commit"]["sha"], tip)

        diff = self._git_ok(worktree, "diff", "--name-only", starting, BRANCH).splitlines()
        # Every touched path has to be on the branch. The commit may carry more
        # than the gate saw, but only the receipt capture: M-10c's spec row puts
        # the receipt and the transcript in the worktree precisely so this
        # commit picks them up. Asserting equality here pinned a set that the
        # next specified change necessarily grows -- the same over-specification
        # M-9's PR_STEP_NAMES fixture had -- and no worker could reconcile it,
        # because templates/dispatch/tests/** is protected.
        for path in touched:
            self.assertIn(path, diff, "the branch does not carry what the gate saw")
        # The capture is admitted by NAME, not by directory. Permitting anything
        # under docs/evidence/receipts/ let a driver report the transcript as
        # withheld and commit the secret beside it in a third file, and the whole
        # suite still passed -- which defeats the withholding path entirely.
        # M-10c's spec row names exactly two files; only those two are admitted.
        captured = {
            "docs/evidence/receipts/T-DRIVER/receipt.json",
            "docs/evidence/receipts/T-DRIVER/worker-stdout.txt",
        }
        extra = [p for p in diff if p not in touched and p not in captured]
        self.assertEqual(
            extra, [],
            f"the commit carries paths that are neither touched nor the capture: {extra}",
        )

        # Nothing left behind: a leftover dirty worktree means the next reader
        # cannot tell what was handed onward from what was not.
        self.assertEqual(self._git_ok(worktree, "status", "--porcelain"), "")

        message = self._git_ok(worktree, "log", "-1", "--format=%B", BRANCH)
        self.assertIn("T-DRIVER", message, f"the message does not name the packet: {message!r}")
        self.assertIn(
            starting[:7], message, f"the message does not name starting_commit: {message!r}",
        )

    def test_the_coordinator_checkout_is_untouched(self):
        worktree, starting = self._build_repo()
        # The coordinator checkout in this fixture is a real repo of its own,
        # with its own dirt: REQ-005 says the driver commits none of it.
        self._git_ok(self.repo_root, "init", "-b", "main")
        (self.repo_root / "coordinator-only.txt").write_text("dirty\n", encoding="utf-8")
        before = self._git(self.repo_root, "rev-parse", "HEAD").stdout

        code, report = self._drive(
            self._packet(starting_commit=starting),
            self._runner(worktree, sorted([TRACKED, UNTRACKED])),
        )
        self.assertEqual(code, 0)
        # The ban is only meaningful if the commit it excludes actually ran.
        self.assertIn("commit", report["pr"], "report['pr'] has no commit record")

        self.assertEqual(self._git(self.repo_root, "rev-parse", "HEAD").stdout, before)
        self.assertEqual(
            self._git_ok(self.repo_root, "status", "--porcelain"), "?? coordinator-only.txt",
        )


if __name__ == "__main__":
    unittest.main()
