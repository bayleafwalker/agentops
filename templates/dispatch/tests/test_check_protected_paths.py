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

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


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
                "templates/dispatch/scripts/hybrid_dispatch.py",
                "templates/dispatch/hybrid/**",
                "docs/**",
            ]}}),
            encoding="utf-8",
        )
        for rel in ("templates/dispatch/scripts/hybrid_dispatch.py",
                    "templates/dispatch/scripts/dispatch_release.py",
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

    def _run(self, title: str) -> int:
        import os
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return checker.main([
                "--base", self.base, "--head", "HEAD", "--title", title,
                "--manifest", "agentops.dispatch.json",
            ])
        finally:
            os.chdir(cwd)

    def test_a_protected_path_without_the_marker_fails(self):
        self._touch_and_commit("templates/dispatch/scripts/hybrid_dispatch.py")
        self.assertEqual(
            self._run("feat(dispatch): a bounded PR body for the driver"), 1,
            "a protected path changed under an unrelated title was allowed",
        )

    def test_a_protected_path_with_the_marker_passes(self):
        self._touch_and_commit("templates/dispatch/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run("hand-pass: narrow the provider registry"), 0)

    def test_the_marker_is_matched_case_insensitively_and_only_as_a_prefix(self):
        self._touch_and_commit("templates/dispatch/scripts/hybrid_dispatch.py")
        self.assertEqual(self._run("Hand-Pass: shout"), 0)
        self.assertEqual(
            self._run("feat: mentions hand-pass: in the middle"), 1,
            "the marker was honoured somewhere other than the start of the title",
        )

    def test_an_unprotected_path_passes_either_way(self):
        self._touch_and_commit("templates/dispatch/scripts/dispatch_release.py")
        self.assertEqual(self._run("feat: the driver"), 0)

    def test_a_glob_protected_path_is_caught(self):
        # docs/** is protected by glob, not by exact name.
        self._touch_and_commit("docs/x.md")
        self.assertEqual(
            self._run("docs: evidence"), 1,
            "a glob-protected path was not matched; the checker is not using "
            "hybrid_dispatch._matches_any",
        )
