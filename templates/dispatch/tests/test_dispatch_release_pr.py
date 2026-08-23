"""Coordinator-authored oracle for spec row M-8 — the driver's PR step opens a PR.

The PR step has never once worked: ``gh pr create`` runs in the packet's
disposable worktree and ``prepare_workspace`` deliberately removes ``origin``
there, so ``gh`` exits 1 with ``no git remotes found``. M-8 puts the remote back
in the driver, after the worker is done, in the PR step only: add ``origin``,
push the packet branch, then ``gh pr create --head``.

Written against the M-8 spec only: the driver runs no ``git`` at all today, so
every test here fails.
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

#: The URL the coordinator's ``origin`` resolves to. Offered two ways so the
#: oracle does not dictate *how* the driver reads it: the fake runner answers a
#: read-only ``git`` query with it, and the coordinator checkout carries it in a
#: real ``.git/config``. Either route is a read-only resolution.
RESOLVED_URL = "git@example.invalid:coordinator/repo.git"

#: What ``push_remote=`` supplies. Deliberately unlike RESOLVED_URL so "used
#: verbatim" cannot pass by accident.
EXPLICIT_URL = "https://example.invalid/explicit/repo.git"

#: The packet branch, and a base branch whose name shares nothing with it —
#: a substring check for "the base branch was pushed" has to be able to fail.
BRANCH = "hybrid/t-driver"
BASE_BRANCH = "trunk-never-pushed"

#: The three things the PR step does, in order. ``report["pr"]`` names one of
#: these when the step fails, so a reader of a failed report can tell "the
#: remote would not add" from "the push was rejected" from "gh refused".
PR_STEP_NAMES = ("remote-add", "push", "pr-create")

#: git subcommands and flags that write. None of them may run against the
#: coordinator checkout: resolution is read-only.
MUTATING_GIT = frozenset({"add", "push", "commit", "merge", "checkout", "init", "set-url"})


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_pr_subject", SCRIPTS / "dispatch_release.py")


def _is_remote_query(cmd: list[str]) -> bool:
    """A read-only "where does origin point" question, in any of its spellings."""
    if MUTATING_GIT & set(cmd):
        return False
    return (
        "get-url" in cmd
        or "remote" in cmd
        or any("remote.origin.url" in arg for arg in cmd)
    )


class FakeRunner:
    """Scripted stand-in for subprocess: records every command and its cwd.

    ``resolve_url`` is what a read-only origin query answers with; ``None``
    makes every such query fail the way it does in a checkout with no remote.
    ``exits`` is keyed by stage name, by ``gh``, and by the PR step names in
    ``PR_STEP_NAMES``, so a fixture can fail exactly one of the three.
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
        if _is_remote_query(cmd):
            if self.resolve_url is None:
                return subprocess.CompletedProcess(
                    cmd, 2, "", "error: No such remote 'origin'",
                )
            return subprocess.CompletedProcess(cmd, 0, self.resolve_url + "\n", "")
        name = "remote-add" if "add" in cmd else "push" if "push" in cmd else "git"
        code = self.exits.get(name, 0)
        return subprocess.CompletedProcess(cmd, code, "", "boom" if code else "")

    def steps(self) -> list[str]:
        return [
            c[-1] for c, _ in self.calls
            if c[0] not in (self.auditctl_bin, "gh", "git")
        ]

    def audit_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == self.auditctl_bin]

    def gh_calls(self) -> list[list[str]]:
        return [c for c, _ in self.calls if c[0] == "gh"]

    def git_calls(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.calls if c[0] == "git"]

    def remote_adds(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "remote" in c and "add" in c]

    def pushes(self) -> list[tuple[list[str], Path | None]]:
        return [(c, cwd) for c, cwd in self.git_calls() if "push" in c]

    def index_of(self, predicate) -> int:
        for i, (cmd, cwd) in enumerate(self.calls):
            if predicate(cmd, cwd):
                return i
        return -1


class PrStepTests(unittest.TestCase):
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

    def _with_origin(self) -> None:
        """Give the coordinator checkout a real origin URL on disk.

        The spec fixes the *result* of resolution, not its mechanism, so the
        URL is readable both by running git (the fake runner answers) and by
        reading config (this file). A driver that resolves either way passes.
        """
        config = self.repo_root / ".git" / "config"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(
            '[remote "origin"]\n\turl = ' + RESOLVED_URL + "\n"
            "\tfetch = +refs/heads/*:refs/remotes/origin/*\n",
            encoding="utf-8",
        )

    def _packet(self, **extra: Any) -> Path:
        packet = {
            "task_id": "T-DRIVER",
            "repo_id": "repo-x",
            "starting_commit": "0" * 40,
            "worktree": {"root": str(self.tmp / "wt"), "branch": BRANCH},
        }
        packet.update(extra)
        path = self.tmp / "packet.json"
        path.write_text(json.dumps(packet), encoding="utf-8")
        return path

    def _worktree(self, packet_path: Path) -> Path:
        return driver.worktree_path(json.loads(packet_path.read_text(encoding="utf-8")))

    def _runner(self, **kw) -> FakeRunner:
        return FakeRunner(str(self.auditctl), **kw)

    def _require_push_remote(self) -> None:
        """Without the keyword, passing it raises TypeError and the fixture
        errors instead of failing on the absent behaviour."""
        self.assertIn(
            "push_remote", inspect.signature(driver.drive).parameters,
            "drive() has no push_remote keyword",
        )

    def _drive(self, packet_path: Path, runner: FakeRunner, **kw):
        if "push_remote" in kw:
            self._require_push_remote()
        kw.setdefault("dry_run", False)
        kw.setdefault("base_branch", BASE_BRANCH)
        return driver.drive(
            packet_path, self.repo_root, runner=runner, auditctl_bin=str(self.auditctl), **kw,
        )

    def _assert_pushed_ref_is_the_packet_branch(self, push: list[str]) -> None:
        """A bare ``git push`` pushes whatever the branch is tracking; the
        driver has to name the packet's own ref and nothing else."""
        self.assertTrue(
            any(arg == BRANCH or arg.endswith(":" + BRANCH) for arg in push),
            f"push names no refspec for {BRANCH}: {push}",
        )
        self.assertNotIn(BASE_BRANCH, " ".join(push), f"the base branch was pushed: {push}")

    # The keyword itself: the call site has to be able to say where to push
    # without the driver reading the coordinator checkout at all.
    def test_push_remote_is_keyword_only_and_optional(self):
        params = inspect.signature(driver.drive).parameters
        self.assertIn("push_remote", params)
        self.assertEqual(params["push_remote"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(params["push_remote"].default)

    # 1. The three things, in order, all in the worktree. Order is the whole
    # row: gh cannot resolve a repository from a worktree with no remote, and a
    # push of a branch the remote has never seen is what --head needs.
    def test_candidate_adds_origin_then_pushes_then_opens_the_pr(self):
        self._with_origin()
        packet = self._packet()
        runner = self._runner()
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        worktree = self._worktree(packet)

        adds = runner.remote_adds()
        self.assertEqual(len(adds), 1, "the PR step adds origin exactly once")
        add_cmd, add_cwd = adds[0]
        self.assertIn("origin", add_cmd, f"the remote is named origin: {add_cmd}")
        self.assertIn(RESOLVED_URL, add_cmd, f"the remote points at origin's URL: {add_cmd}")
        self.assertEqual(add_cwd, worktree, "the remote is added to the worktree, not the checkout")

        pushes = runner.pushes()
        self.assertEqual(len(pushes), 1, "the PR step pushes exactly once")
        self.assertEqual(pushes[0][1], worktree)

        gh = [(c, cwd) for c, cwd in runner.calls if c[0] == "gh"]
        self.assertEqual(len(gh), 1)
        self.assertEqual(gh[0][0][:3], ["gh", "pr", "create"])
        self.assertEqual(gh[0][0][gh[0][0].index("--head") + 1], BRANCH)
        self.assertEqual(gh[0][1], worktree)

        i_add = runner.index_of(lambda c, _: c[0] == "git" and "remote" in c and "add" in c)
        i_push = runner.index_of(lambda c, _: c[0] == "git" and "push" in c)
        i_gh = runner.index_of(lambda c, _: c[0] == "gh")
        self.assertLess(i_add, i_push, "the push needs the remote to exist first")
        self.assertLess(i_push, i_gh, "gh pr create --head needs the branch on the remote")

    # 2. REQ-002 restated for the mechanism M-8 introduces: the driver pushes
    # the packet's branch and never the branch it is asking to merge into.
    def test_push_names_the_packet_branch_and_never_the_base(self):
        self._with_origin()
        runner = self._runner()
        code, _ = self._drive(self._packet(), runner)
        self.assertEqual(code, 0)
        pushes = runner.pushes()
        self.assertTrue(pushes, "the PR step pushes the packet branch")
        for push, _cwd in pushes:
            self._assert_pushed_ref_is_the_packet_branch(push)

    # 3. Three dispatches were finished by hand because the report said the PR
    # step failed without saying where it had pushed. The record is the fix.
    def test_report_pr_records_the_remote_and_the_branch_pushed(self):
        self._with_origin()
        runner = self._runner()
        _, report = self._drive(self._packet(), runner)
        pr = report["pr"]
        self.assertIn("push", pr, "report['pr'] has no push record")
        self.assertEqual(pr["push"]["remote"], RESOLVED_URL)
        self.assertEqual(pr["push"]["branch"], BRANCH)
        self.assertTrue(pr["opened"])

    # 4. A failed remote-add or push is the hand-off failing, and is escalated
    # exactly like a failed gh pr create — and gh is never reached, because a
    # PR against an unpushed branch is the bug this row exists to remove.
    def test_failed_remote_add_or_push_escalates_once_and_never_reaches_gh(self):
        for failing in ("remote-add", "push"):
            with self.subTest(failing=failing):
                self._with_origin()
                runner = self._runner(exits={failing: 128})
                code, report = self._drive(self._packet(), runner)
                self.assertNotEqual(code, 0)
                self.assertEqual(runner.gh_calls(), [])
                audit = runner.audit_calls()
                self.assertEqual(len(audit), 1, "the failure escalates exactly once")
                self.assertEqual(audit[0][1:4], ["add", "--type", "workflow.escalation"])
                self.assertEqual(report["escalation"]["metadata"]["step"], "pr")
                self.assertEqual(report["pr"]["failed_step"], failing)
                self.assertFalse(report["pr"]["opened"])

    # 5. An explicit remote is used as given: the caller, not the driver's
    # resolution, decides where a packet branch lands.
    def test_explicit_push_remote_is_used_verbatim(self):
        self._with_origin()  # present, and must be ignored in favour of the argument
        runner = self._runner()
        _, report = self._drive(self._packet(), runner, push_remote=EXPLICIT_URL)
        adds = runner.remote_adds()
        self.assertEqual(len(adds), 1)
        self.assertIn(EXPLICIT_URL, adds[0][0])
        self.assertNotIn(RESOLVED_URL, " ".join(adds[0][0]))
        self.assertEqual(report["pr"]["push"]["remote"], EXPLICIT_URL)

    # 6. A driver that cannot find a remote must not turn a green packet into a
    # failed one: it skips the PR with a reason, exactly as dry-run does.
    def test_unresolvable_remote_skips_the_pr_and_still_exits_zero(self):
        runner = self._runner(resolve_url=None)  # and no .git in the coordinator checkout
        code, report = self._drive(self._packet(), runner)
        self.assertEqual(code, 0)
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.remote_adds(), [])
        self.assertEqual(runner.gh_calls(), [], "with nowhere to push there is no PR to open")
        self.assertIn("skipped", report["pr"], "report['pr'] does not record the skip")
        self.assertTrue(report["pr"]["skipped"])
        self.assertIn("remote", report["pr"]["reason"].lower())
        self.assertFalse(report["pr"]["opened"])
        self.assertIsNone(report["stop"])

    # 7. A dry run is a rehearsal: no network call and no change to the
    # worktree's remotes, but it still reports the gh it would have run. The
    # remote is handed in explicitly so the fixture bans using a URL the driver
    # already has, not merely one it declined to look up.
    def test_dry_run_adds_no_remote_pushes_nothing_and_opens_nothing(self):
        self._with_origin()
        runner = self._runner()
        code, report = self._drive(
            self._packet(), runner, dry_run=True, push_remote=EXPLICIT_URL,
        )
        self.assertEqual(code, 0)
        self.assertEqual(runner.remote_adds(), [], "a dry run must not touch the worktree remotes")
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.gh_calls(), [])
        self.assertTrue(report["pr"]["skipped"])
        self.assertIn("dry-run", report["pr"]["reason"])
        self.assertEqual(report["pr"]["command"][:3], ["gh", "pr", "create"])
        self.assertEqual(
            report["pr"]["command"][report["pr"]["command"].index("--head") + 1], BRANCH,
        )

    # 8a. A non-candidate disposition is work the driver cannot vouch for. The
    # push is part of the hand-off, so it must not happen either -- not even
    # with a remote handed in. Attempt 2 in the packet is what makes this a skip
    # rather than the gate-red-twice stop.
    def test_non_candidate_disposition_reaches_neither_push_nor_gh(self):
        self._with_origin()
        runner = self._runner(
            exits={"gate": 2}, disposition="coordinator_review_required",
        )
        code, report = self._drive(
            self._packet(attempt=2), runner, push_remote=EXPLICIT_URL,
        )
        self.assertEqual(code, 0)
        self.assertTrue(report["pr"]["skipped"])
        self.assertEqual(runner.remote_adds(), [])
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.gh_calls(), [])

    # 8b. Every L-2 stop condition still means the driver hands nothing onward.
    # A pushed branch is visible on the remote, so it is a hand-off too.
    def test_every_stop_condition_reaches_neither_push_nor_gh(self):
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
                self._with_origin()
                packet = self._packet(**extra)
                runner = self._runner(gate_extra=gate_extra)
                code, report = self._drive(packet, runner, push_remote=EXPLICIT_URL)
                self.assertEqual(report["stop"]["condition"], condition)
                self.assertNotEqual(code, 0)
                self.assertEqual(runner.remote_adds(), [])
                self.assertEqual(runner.pushes(), [])
                self.assertEqual(runner.gh_calls(), [])

    def test_gate_red_twice_reaches_neither_push_nor_gh(self):
        self._with_origin()
        packet = self._packet()
        for _ in range(2):
            runner = self._runner(exits={"gate": 2}, disposition="coordinator_review_required")
            code, report = self._drive(packet, runner, push_remote=EXPLICIT_URL)
        self.assertEqual(report["stop"]["condition"], "gate-red-twice")
        self.assertNotEqual(code, 0)
        self.assertEqual(runner.remote_adds(), [])
        self.assertEqual(runner.pushes(), [])
        self.assertEqual(runner.gh_calls(), [])

    # Resolution is read-only with respect to the coordinator: the driver may
    # ask origin where it points, and may do nothing else there.
    def test_resolution_never_writes_to_the_coordinator_checkout(self):
        self._with_origin()
        packet = self._packet()
        runner = self._runner()
        code, report = self._drive(packet, runner)
        self.assertEqual(code, 0)
        # Resolution has to have happened for the ban below to mean anything.
        self.assertIn("push", report["pr"], "report['pr'] has no push record")
        self.assertEqual(report["pr"]["push"]["remote"], RESOLVED_URL)
        worktree = self._worktree(packet)
        for cmd, cwd in runner.git_calls():
            if cwd == worktree:
                continue
            self.assertFalse(
                MUTATING_GIT & set(cmd), f"git writes outside the worktree: {cmd} (cwd={cwd})",
            )


if __name__ == "__main__":
    unittest.main()
