"""Follow-up tests for #2562 repair (NUL-safe paths, merge diffs, PR-action ancestry, floor).

Kept apart from the frozen oracle in test_dispatch_publish_check.py.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dispatch_publish_check import ConfirmTests, PublishCheckCase  # noqa: E402


class PreflightFloorTests(PublishCheckCase):
    def test_floor_applies_alongside_a_manifest(self) -> None:
        c = self.repos.commit("c", "src/ok.py", "sub/dir/x.dispatch.json", ".claude/x.js")
        self.assertEqual(self.preflight(c, c)["protected_hits"], [".claude/x.js", "sub/dir/x.dispatch.json"])


class PreflightPathEdgeTests(PublishCheckCase):
    def test_non_ascii_protected_path_is_a_hit(self) -> None:
        c = self.repos.commit("c", ".claude/\u00e4.md")
        self.assertEqual(self.preflight(c, c)["protected_hits"], [".claude/\u00e4.md"])

    def test_nested_dispatch_json_is_a_hit(self) -> None:
        c = self.repos.commit("c", "a/b/c.dispatch.json")
        self.assertEqual(self.preflight(c, c)["protected_hits"], ["a/b/c.dispatch.json"])

    def test_protected_change_inside_a_merge_commit_is_a_hit(self) -> None:
        r = self.repos
        r.git("checkout", "-q", "-b", "side")
        s = r.commit("side", "src/side.py")
        r.git("checkout", "-q", "-")
        r.commit("main-side", "src/m.py")
        r.git("merge", "-q", "--no-ff", "--no-commit", "side")
        r.write(".claude/evil.js", "x\n")
        r.git("add", "-A")
        r.git("commit", "-q", "-m", "merge")
        tip = r.git("rev-parse", "HEAD")
        self.assertIn(".claude/evil.js", self.preflight(tip, tip)["protected_hits"])


class ConfirmPrActionTests(ConfirmTests):
    def test_a_pr_action_is_not_confirmed_when_main_was_also_pushed(self) -> None:
        c = self.repos.commit("c", "src/c.py")
        branch = f"dispatch/publish-{c[:12]}"
        self.repos.git("push", "-q", "origin", f"{c}:refs/heads/{branch}")
        self.assertTrue(self.confirm(c, "pr-opened")["confirmed"])
        self.repos.git("push", "-q", "origin", f"{c}:refs/heads/main")
        for action in ("pr-opened", "needs-hand-pass-pr"):
            self.assertFalse(self.confirm(c, action)["confirmed"])


if __name__ == "__main__":
    unittest.main()
