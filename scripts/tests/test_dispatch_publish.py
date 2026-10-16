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

    def test_delivered_verified_ref_is_pruned_without_deleting_unpublished_evidence(self):
        delivered = self.repos.commit("delivered", "src/old.py")
        old_ref = f"refs/dispatch/verified/{self.repos.base}-{delivered}"
        self.repos.git("update-ref", old_ref, delivered)
        self.repos.git("push", "origin", f"{delivered}:refs/heads/main")
        tip = self.repos.commit("verified", "src/new.py")
        new_ref = f"refs/dispatch/verified/{delivered}-{tip}"
        self.repos.git("update-ref", new_ref, tip)
        self.assertTrue(self.publish(tip, [tip])["published"])
        refs = self.repos.git("for-each-ref", "--format=%(refname)", "refs/dispatch/verified/")
        self.assertNotIn(old_ref, refs)
        self.assertIn(new_ref, refs)

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

    def run_main(self, *extra):
        tip = self.repos.commit("verified", "src/ok.py")
        argv = ["dispatch_publish.py", "--repo", str(self.repos.work), "--tip", tip,
                "--run-branch", "dispatch/run-test123", "--expected", tip, *extra]
        with patch.object(sys, "argv", argv), patch("builtins.print") as printed:
            code = publisher.main()
        return code, json.loads(printed.call_args[0][0])

    def test_authority_gate_refuses_before_any_effect(self):
        environment = Path(__file__).parents[2] / "environment-record/devbox-vm.vuoro-shared.json"
        with patch.object(publisher, "publish") as effect:
            code, report = self.run_main("--authority-environment", str(environment),
                                         "--run-id", "run_1", "--grant-id", "grant_1", "--attempt-id", "attempt_1")
        effect.assert_not_called()
        self.assertEqual(code, 1)
        self.assertEqual(report["action"], "publish-refused")
        self.assertEqual(report["authority"]["code"], "run-unverified")  # no served owner: fail closed
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)

    def test_authority_gate_refuses_record_without_authority(self):
        environment = Path(__file__).parents[2] / "environment-record/workstation-linux.vuoro-shared.json"
        with patch.object(publisher, "publish") as effect:
            code, report = self.run_main("--authority-environment", str(environment))
        effect.assert_not_called()
        self.assertEqual(code, 1)
        self.assertIn("environment-invalid", report["error"])

    def gated_target(self, tip, **over):
        target = {"operation": "push_branch", "repository": "agentops",
                  "branch": "dispatch/publish-batch/intent_01JZZZZZZZZZZZZZZZZZZZZZZZ", "commit_sha": tip}
        target.update(over)
        return target

    def test_gated_publication_pushes_only_the_attempt_branch_never_main(self):
        tip = self.repos.commit("verified", "src/ok.py")  # unprotected: ungated would push main
        target = self.gated_target(tip)
        report = publisher.publish(str(self.repos.work), tip, "dispatch/run-test123", [tip], ["1"], target)
        self.assertEqual(report["action"], "branch-pushed")
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)
        self.assertEqual(checker.remote_ref(str(self.repos.work), f"refs/heads/{target['branch']}")[0], tip)

    def test_gated_publication_refuses_a_tip_other_than_the_attempt_commit(self):
        tip = self.repos.commit("verified", "src/ok.py")
        with self.assertRaisesRegex(ValueError, "authorized target commit"):
            publisher.publish(str(self.repos.work), tip, "dispatch/run-test123", [tip], ["1"],
                              self.gated_target("f" * 40))
        self.assertEqual(checker.remote_ref(str(self.repos.work), "refs/heads/main")[0], self.repos.base)

    def test_gated_main_passes_the_allowed_target_to_publish(self):
        environment = Path(__file__).parents[2] / "environment-record/devbox-vm.vuoro-shared.json"
        allowed = {"branch": "dispatch/publish-x/intent_01JZZZZZZZZZZZZZZZZZZZZZZZ"}
        with patch.object(publisher, "authority_gate", return_value=(None, allowed)), \
                patch.object(publisher, "publish", return_value={"action": "branch-pushed"}) as effect:
            code, _ = self.run_main("--authority-environment", str(environment))
        self.assertEqual(code, 0)
        self.assertIs(effect.call_args[0][5], allowed)

    def test_ungated_publication_is_unchanged(self):
        code, report = self.run_main()
        self.assertEqual(code, 0)
        self.assertTrue(report["published"])
