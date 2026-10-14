"""The CI check that closes the gap between the gate and acceptance.

The dispatch gate asserts ``protected-paths-untouched`` over the WORKER's
commit; acceptance happens over the merged pull request. Commit 6b7265a reached
main inside PR #74 -- a change to a protected path, under a title about
something else, while that PR's own gate table read
``protected-paths-untouched: true``. Accurate about the commit, misleading
about the PR.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load("check_protected_paths_subject", SCRIPTS / "check_protected_paths.py")


class ProtectedPathCheckTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t.invalid")
        self._git("config", "user.name", "t")
        (self.repo / "agentops.dispatch.json").write_text(
            json.dumps({"hybrid": {"protected_paths": [
                "hybrid/scripts/hybrid_dispatch.py",
                "hybrid/state/**",
                "docs/**",
            ], "hand_pass_actors": ["operator"]}}),
            encoding="utf-8",
        )
        for rel in ("hybrid/scripts/hybrid_dispatch.py",
                    "hybrid/scripts/dispatch_release.py",
                    "docs/x.md"):
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("base\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "base")
        self.base = self._git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True,
        ).stdout

    def _touch_and_commit(self, rel: str) -> None:
        (self.repo / rel).write_text("changed\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", f"touch {rel}")

    def _hp(self, rest: str = "x", n: int = 40) -> str:
        return f"hand-pass@{self._git('rev-parse', 'HEAD').strip()[:n]}: {rest}"

    def _run(self, title: str, sender: str | None = "operator") -> int:
        import os
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            argv = [
                "--base", self.base, "--head", "HEAD", "--title", title,
                "--manifest", "agentops.dispatch.json",
            ]
            if sender is not None:
                argv += ["--sender", sender]
            return checker.main(argv)
        finally:
            os.chdir(cwd)

    def test_a_protected_path_without_the_marker_fails(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(
            self._run("feat(dispatch): a bounded PR body for the driver"), 1,
            "a protected path changed under an unrelated title was allowed",
        )

    def test_a_protected_path_with_the_marker_passes(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run(self._hp("narrow the provider registry")), 0)

    def test_a_bot_sender_cannot_hand_pass_its_own_pr(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(
            self._run(self._hp("self-declared"), sender="agent-app[bot]"), 1,
            "a sender outside hybrid.hand_pass_actors was allowed to hand-pass",
        )

    def test_a_plain_hand_pass_title_without_a_sha_fails(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run("hand-pass: no sha", sender="operator"), 1)

    def test_a_sha_that_is_not_the_head_fails_even_for_the_operator(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        stale = self.base  # reviewed an earlier commit; the head moved on
        self.assertEqual(self._run(f"hand-pass@{stale}: stale", sender="operator"), 1)

    def test_a_short_matching_prefix_fails(self):
        # 7 hex is 28 bits: an agent can grind a later commit onto it.
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        for n in (6, 7, 12, 39):
            self.assertEqual(
                self._run(self._hp(n=n), sender="operator"), 1,
                f"a {n}-hex prefix of the head sha was accepted as a hand-pass",
            )

    def test_the_full_matching_sha_passes(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run(self._hp(n=40), sender="operator"), 0)

    def test_a_full_sha_differing_in_the_last_digit_fails(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        head = self._git("rev-parse", "HEAD").strip()
        wrong = head[:39] + ("0" if head[39] != "0" else "1")
        self.assertEqual(self._run(f"hand-pass@{wrong}: near miss", sender="operator"), 1)

    def test_a_missing_sender_cannot_hand_pass(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run(self._hp("no sender"), sender=None), 1)
        self.assertEqual(self._run(self._hp("empty sender"), sender=""), 1)

    def test_an_operator_sender_without_the_marker_still_fails(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run("feat: unmarked", sender="operator"), 1)

    def test_no_actor_list_means_nobody_can_hand_pass(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        (self.repo / "agentops.dispatch.json").write_text(
            json.dumps({"hybrid": {"protected_paths": ["hybrid/scripts/hybrid_dispatch.py"]}}),
            encoding="utf-8",
        )
        self.assertEqual(self._run(self._hp(), sender="operator"), 1)

    def test_the_marker_is_matched_case_insensitively_and_only_as_a_prefix(self):
        self._touch_and_commit("hybrid/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run(self._hp("shout").upper().replace("HAND-PASS@", "Hand-Pass@")), 0)
        self.assertEqual(
            self._run("feat: mentions " + self._hp()), 1,
            "the marker was honoured somewhere other than the start of the title",
        )

    def test_an_unprotected_path_passes_either_way(self):
        self._touch_and_commit("hybrid/scripts/dispatch_release.py")
        self.assertEqual(self._run("feat: the driver"), 0)

    def test_a_glob_protected_path_is_caught(self):
        # docs/** is protected by glob, not by exact name.
        self._touch_and_commit("docs/x.md")
        self.assertEqual(
            self._run("docs: evidence"), 1,
            "a glob-protected path was not matched; the checker is not using "
            "its _matches_any",
        )
