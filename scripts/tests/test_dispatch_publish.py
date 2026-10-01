"""Exercise publication effects with real local Git remotes, without an LLM relay."""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from test_dispatch_publish_check import PublishCheckCase

sys.path.insert(0, str(Path(__file__).parents[1]))
import dispatch_publish as publisher
import dispatch_publish_check as checker


class NativePublisherTests(PublishCheckCase):
    def setUp(self):
        super().setUp()
        self.repos.git("switch", "-c", "dispatch/run-test123")

    def publish(self, tip, expected):
        return publisher.publish(str(self.repos.work), tip, "dispatch/run-test123", expected, ["1"])

    def test_expected_tip_is_pushed_and_confirmed(self):
        tip = self.repos.commit("verified", "src/ok.py")
        report = self.publish(tip, [tip])
        self.assertTrue(report["published"])
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], tip)

    def test_unexpected_commit_refuses_effect_even_with_forged_agent_summary(self):
        rogue = self.repos.commit("unverified", "src/rogue.py")
        tip = self.repos.commit("verified", "src/ok.py")
        with self.assertRaisesRegex(ValueError, "unaccounted"):
            self.publish(tip, [tip])
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)
        self.assertNotEqual(rogue, self.repos.base)

    def test_protected_paths_cannot_push_main(self):
        tip = self.repos.commit("protected", ".claude/new.js")
        with self.assertRaisesRegex(ValueError, "GitHub origin"):
            self.publish(tip, [tip])
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)

    def test_shared_main_cannot_publish(self):
        self.repos.git("switch", "main")
        with self.assertRaisesRegex(ValueError, "named run branch"):
            self.publish(self.repos.base, [])

    def test_net_zero_range_without_expected_unpublished_commits_is_skipped(self):
        tip = self.repos.commit("empty reverted history")
        self.repos.git("update-ref", f"refs/dispatch/verified/{self.repos.base}-{tip}", tip)
        report = self.publish(tip, [])
        self.assertEqual(report["action"], "net-zero")
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)

    def test_pr_confirmation_fetches_unknown_remote_main_before_ancestry(self):
        tip = self.repos.commit("verified", "src/ok.py")
        self.repos.git("push", "origin", f"{tip}:refs/heads/dispatch/publish-{tip[:12]}")
        other = self.repos.root / "other"
        self.repos.run(self.repos.root, "clone", "-q", str(self.repos.origin), str(other))
        self.repos.configure(other)
        self.repos.run(other, "fetch", "origin", f"refs/heads/dispatch/publish-{tip[:12]}")
        self.repos.run(other, "reset", "--hard", tip)
        self.repos.run(other, "commit", "-q", "--allow-empty", "-m", "new remote child")
        self.repos.run(other, "push", "origin", "HEAD:refs/heads/main")
        report = checker.confirm(str(self.repos.work), tip, "pr-opened")
        self.assertFalse(report["confirmed"])
        self.assertIn("already on remote main", report["error"])

    def test_pr_confirmation_fails_closed_on_main_lookup_error(self):
        tip = self.repos.commit("verified")
        with patch.object(checker, "remote_ref", side_effect=[(tip, None), (None, "lookup failed")]):
            self.assertFalse(checker.confirm(str(self.repos.work), tip, "pr-opened")["confirmed"])

    def test_branch_name_uses_resolved_full_tip(self):
        tip = self.repos.commit("verified")
        self.assertEqual(checker.preflight(str(self.repos.work), tip[:7], [tip])["publish_branch"], "dispatch/publish-" + tip[:12])

    def test_protected_hand_back_uses_full_tip_branch_and_keeps_main_unchanged(self):
        tip = self.repos.commit("protected", ".claude/new.js")
        original_run = subprocess.run
        gh_calls = []
        def run(args, **kwargs):
            if args[0] != "gh":
                return original_run(args, **kwargs)
            gh_calls.append(args)
            stdout = "[]" if args[1:3] == ["pr", "list"] else "https://github.com/bayleafwalker/demo/pull/1"
            return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")
        with patch.object(publisher, "github_identity", return_value="bayleafwalker/demo"), patch.object(subprocess, "run", side_effect=run):
            report = self.publish(tip[:7], [tip])
        self.assertEqual(report["action"], "needs-hand-pass-pr")
        self.assertFalse(report["published"])
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/dispatch/publish-" + tip[:12])[0], tip)
        self.assertIn("dispatch/publish-" + tip[:12], gh_calls[-1])
        self.assertIn("--body-file", gh_calls[-1])
        self.assertEqual(gh_calls[0][gh_calls[0].index("--base") + 1], "main")

    def test_multiple_push_destinations_are_refused_before_effects(self):
        self.repos.git("config", "--add", "remote.origin.pushurl", str(self.repos.origin))
        self.repos.git("config", "--add", "remote.origin.pushurl", "https://example.invalid/appservice.git")
        tip = self.repos.commit("verified", "src/ok.py")
        with self.assertRaisesRegex(ValueError, "exactly one push destination"):
            self.publish(tip, [tip])
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)

    def test_pr_confirmation_fails_closed_when_missing_main_cannot_be_fetched(self):
        tip = self.repos.commit("verified")
        original_git = checker.git
        def git(repo, *args, **kwargs):
            if args[0] == "cat-file":
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="missing")
            if args[0] == "fetch":
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="fetch denied")
            return original_git(repo, *args, **kwargs)
        with patch.object(checker, "remote_ref", side_effect=[(tip, None), ("f" * 40, None)]), patch.object(checker, "git", side_effect=git):
            report = checker.confirm(str(self.repos.work), tip, "pr-opened")
        self.assertFalse(report["confirmed"])
        self.assertIn("fetch denied", report["error"])
