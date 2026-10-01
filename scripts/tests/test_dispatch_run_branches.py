"""Retirement must fail closed and preserve checked-out or unpublished work."""
import sys
from pathlib import Path
from unittest.mock import patch

from test_dispatch_publish_check import PublishCheckCase

sys.path.insert(0, str(Path(__file__).parents[1]))
from dispatch_run_branches import inspect


class RunBranchTests(PublishCheckCase):
    def inspect(self, apply=False):
        return inspect(str(self.repos.work), apply)

    def test_merged_free_branch_is_deleted(self):
        self.repos.git("branch", "dispatch/run-old")
        row = self.inspect(True)["branches"][0]
        self.assertTrue(row["deleted"])
        self.assertNotIn("dispatch/run-old", self.repos.git("branch", "--list"))

    def test_merged_checked_out_branch_is_preserved(self):
        path = self.repos.root / "active"
        self.repos.git("worktree", "add", "-b", "dispatch/run-active", str(path))
        row = self.inspect(True)["branches"][0]
        self.assertFalse(row["deleted"])
        self.assertEqual(row["worktree"]["path"], str(path))
        self.assertGreaterEqual(row["worktree"]["age_seconds"], 0)

    def test_unmerged_branch_is_reported_and_preserved(self):
        tip = self.repos.commit("unpublished", "src/new.py")
        self.repos.git("branch", "dispatch/run-unpublished", tip)
        row = self.inspect(True)["branches"][0]
        self.assertFalse(row["merged"])
        self.assertFalse(row["deleted"])
        self.assertEqual(self.repos.git("rev-parse", row["branch"]), tip)

    def test_dry_run_changes_nothing(self):
        self.repos.git("branch", "dispatch/run-old")
        self.assertFalse(self.inspect()["branches"][0]["deleted"])
        self.assertEqual(self.repos.git("rev-parse", "dispatch/run-old"), self.repos.base)

    def test_concurrent_advance_cannot_delete_new_commits(self):
        import dispatch_run_branches as module
        self.repos.git("branch", "dispatch/run-old")
        tip = self.repos.commit("new work", "src/new.py")
        original = module.git
        def git(repo, *args):
            if args[:2] == ("update-ref", "-d"):
                self.repos.git("update-ref", "refs/heads/dispatch/run-old", tip)
            return original(repo, *args)
        with patch.object(module, "git", side_effect=git):
            row = self.inspect(True)["branches"][0]
        self.assertFalse(row["deleted"])
        self.assertIn("error", row)
        self.assertEqual(self.repos.git("rev-parse", "dispatch/run-old"), tip)

    def test_worktree_removal_cannot_be_implicit_or_outside_run_root(self):
        with self.assertRaisesRegex(ValueError, "requires --apply"):
            inspect(str(self.repos.work), False, ["/tmp/active"])
        with self.assertRaisesRegex(ValueError, "explicit"):
            inspect(str(self.repos.work), True, [str(self.repos.work)])
