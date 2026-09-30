"""Deterministic publication preflight and post-publish confirmation (#2562).

vuoro-dispatch-build used to leave the publication rules to the publish agent's
prompt: which commits in ``origin/main..TIP`` are expected or covered by a
recorded ``refs/dispatch/verified/<b>-<t>`` range, and which changed paths hit
``hybrid.protected_paths``. In run wf_bd22b93c-f7e the agent ignored the
protected-path rule and pushed main; in wf_290f8453-ea5 it "checked" protected
paths with ``[ -f "*.dispatch.json" ]``, a literal glob that is never true.

``scripts/dispatch_publish_check.py`` computes those facts in code. Contract
(the workflow runs it through an exact-command clerical agent and parses its
stdout as JSON):

    dispatch_publish_check.py preflight --repo R --tip T [--expected SHA ...]
        exit 0 and a JSON object on stdout with at least:
          tip              full SHA of T
          range            full SHAs of git rev-list origin/main..T
          expected         commits of range that are expected SHAs
          covered          commits of range covered by a valid verified ref
          unexpected       commits of range neither expected nor covered
          missing_expected expected SHAs (full) that are not ancestors of T
          invalid_refs     refs/dispatch/verified/* refs that cover nothing
                           because the ref value is not <t> or <b> is not an
                           ancestor of <t>
          protected_hits   sorted paths changed in origin/main..T matching
                           hybrid.protected_paths of the root *.dispatch.json
                           (glob semantics of check_protected_paths._matches_any)
          origin_url       git remote get-url origin
        A verified ref refs/dispatch/verified/<b>-<t> covers commit X only when
        the ref points at <t>, <b> is an ancestor of <t>, <t> is an ancestor of
        T, and X is listed by git rev-list <b>..<t>. SHAs may be given
        abbreviated; every SHA in the output is the full 40-hex form.
        A tip that does not resolve exits non-zero.

    dispatch_publish_check.py confirm --repo R --tip T --action A
        exit 0 and a JSON object with a boolean ``confirmed``, checked against
        the origin remote itself (not the local remote-tracking ref):
          pushed, already-on-origin      origin's main contains T
          pr-opened, needs-hand-pass-pr  origin has refs/heads/dispatch/publish-<first 12 hex of T> at T
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "dispatch_publish_check.py"

MANIFEST = {
    "hybrid": {
        "protected_paths": [
            "*.dispatch.json",
            ".claude/**",
            "schemas/",
            "model-routing.json",
        ]
    }
}


class _Repos:
    """A bare origin with main at a base commit, and a working clone."""

    def __init__(self, root: Path, manifest: dict | None = MANIFEST) -> None:
        self.root = root
        self.hooks = root / "no-hooks"
        self.hooks.mkdir()
        self.origin = root / "origin.git"
        self.run(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.work = root / "work"
        self.run(root, "clone", "-q", str(self.origin), str(self.work))
        self.configure(self.work)
        if manifest is not None:
            self.write("demo.dispatch.json", json.dumps(manifest))
        self.write("README.md", "base\n")
        self.write(".claude/workflows/old.js", "// on origin already\n")
        self.base = self.commit("base")
        self.git("push", "-q", "origin", "HEAD:refs/heads/main")
        self.git("fetch", "-q", "origin")

    def configure(self, repo: Path) -> None:
        for key, value in (
            ("user.email", "t@t.invalid"),
            ("user.name", "t"),
            ("commit.gpgsign", "false"),
            ("tag.gpgsign", "false"),
            ("core.hooksPath", str(self.hooks)),
        ):
            self.run(repo, "config", key, value)

    def run(self, cwd: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()

    def git(self, *args: str) -> str:
        return self.run(self.work, *args)

    def write(self, rel: str, text: str) -> None:
        path = self.work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str, *changes: str) -> str:
        for rel in changes:
            self.write(rel, f"{message}\n")
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")


def _script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class PublishCheckCase(unittest.TestCase):
    manifest: dict | None = MANIFEST

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repos = _Repos(Path(self._tmp.name), self.manifest)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def preflight(self, tip: str, *expected: str) -> dict:
        args = ["preflight", "--repo", str(self.repos.work), "--tip", tip]
        for sha in expected:
            args += ["--expected", sha]
        result = _script(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def confirm(self, tip: str, action: str) -> dict:
        result = _script("confirm", "--repo", str(self.repos.work), "--tip", tip, "--action", action)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIsInstance(report.get("confirmed"), bool, report)
        return report

    def assertSameSet(self, actual, expected) -> None:
        self.assertIsInstance(actual, list)
        self.assertEqual(sorted(actual), sorted(expected))


class PreflightCommitClassificationTests(PublishCheckCase):
    def test_script_exists(self) -> None:
        self.assertTrue(SCRIPT.is_file(), f"{SCRIPT} is the deterministic publication preflight")

    def test_expected_commits_are_classified_and_reported_in_full(self) -> None:
        b = self.repos.commit("b", "src/b.py")
        c = self.repos.commit("c", "src/c.py")
        # Abbreviated inputs, as the workflow receives SHAs from agents.
        report = self.preflight(c[:10], b[:10], c[:12])
        self.assertEqual(report["tip"], c)
        self.assertSameSet(report["range"], [b, c])
        self.assertSameSet(report["expected"], [b, c])
        self.assertSameSet(report["covered"], [])
        self.assertSameSet(report["unexpected"], [])
        self.assertSameSet(report["missing_expected"], [])
        self.assertSameSet(report["protected_hits"], [])

    def test_a_commit_neither_expected_nor_covered_is_unexpected(self) -> None:
        b = self.repos.commit("b", "src/b.py")
        c = self.repos.commit("c", "src/c.py")
        report = self.preflight(c, c)
        self.assertSameSet(report["expected"], [c])
        self.assertSameSet(report["unexpected"], [b])

    def test_a_valid_verified_ref_covers_its_range(self) -> None:
        b = self.repos.commit("b", "src/b.py")
        c = self.repos.commit("c", "src/c.py")
        base = self.repos.base
        # The workflow names refs with the SHAs agents reported, which may be abbreviated.
        self.repos.git("update-ref", f"refs/dispatch/verified/{base[:8]}-{b[:8]}", b)
        report = self.preflight(c, c)
        self.assertSameSet(report["covered"], [b])
        self.assertSameSet(report["unexpected"], [])
        self.assertSameSet(report["invalid_refs"], [])

    def test_a_ref_whose_value_is_not_its_named_tip_covers_nothing(self) -> None:
        # Event 3950 finding 3: the <b>-<t> in a ref name is not evidence on its own.
        b = self.repos.commit("b", "src/b.py")
        c = self.repos.commit("c", "src/c.py")
        forged = f"refs/dispatch/verified/{self.repos.base}-{b}"
        self.repos.git("update-ref", forged, c)
        report = self.preflight(c, c)
        self.assertSameSet(report["covered"], [])
        self.assertSameSet(report["unexpected"], [b])
        self.assertIn(forged, report["invalid_refs"])

    def test_a_ref_whose_base_is_not_an_ancestor_of_its_tip_covers_nothing(self) -> None:
        base = self.repos.base
        self.repos.git("checkout", "-q", "-b", "side", base)
        side = self.repos.commit("side", "src/side.py")
        self.repos.git("checkout", "-q", "main")
        b = self.repos.commit("b", "src/b.py")
        c = self.repos.commit("c", "src/c.py")
        # git rev-list side..b lists b, so only the ancestry check keeps this ref from covering it.
        bogus = f"refs/dispatch/verified/{side}-{b}"
        self.repos.git("update-ref", bogus, b)
        report = self.preflight(c, c)
        self.assertSameSet(report["covered"], [])
        self.assertSameSet(report["unexpected"], [b])
        self.assertIn(bogus, report["invalid_refs"])

    def test_a_ref_whose_tip_is_not_an_ancestor_of_the_publication_tip_covers_nothing(self) -> None:
        b = self.repos.commit("b", "src/b.py")
        self.repos.git("checkout", "-q", "-b", "side")
        d = self.repos.commit("d", "src/d.py")
        self.repos.git("checkout", "-q", "main")
        c = self.repos.commit("c", "src/c.py")
        # base..d lists b and d; d is not in TIP's history, so the range does not vouch for b here.
        self.repos.git("update-ref", f"refs/dispatch/verified/{self.repos.base}-{d}", d)
        report = self.preflight(c, c)
        self.assertSameSet(report["covered"], [])
        self.assertSameSet(report["unexpected"], [b])

    def test_an_expected_sha_outside_the_tip_history_is_missing(self) -> None:
        self.repos.git("checkout", "-q", "-b", "side")
        d = self.repos.commit("d", "src/d.py")
        self.repos.git("checkout", "-q", "main")
        c = self.repos.commit("c", "src/c.py")
        report = self.preflight(c, c, d[:10])
        self.assertSameSet(report["missing_expected"], [d])
        self.assertSameSet(report["unexpected"], [])

    def test_work_already_on_origin_has_an_empty_range(self) -> None:
        b = self.repos.commit("b", "src/b.py")
        self.repos.git("push", "-q", "origin", "HEAD:refs/heads/main")
        report = self.preflight(b, b)
        self.assertSameSet(report["range"], [])
        self.assertSameSet(report["unexpected"], [])
        self.assertSameSet(report["missing_expected"], [])
        self.assertSameSet(report["protected_hits"], [])

    def test_a_tip_that_does_not_resolve_is_an_error(self) -> None:
        self.assertTrue(SCRIPT.is_file(), SCRIPT)
        result = _script("preflight", "--repo", str(self.repos.work), "--tip", "0123456789abcdef0123", "--expected", "0123456789abcdef0123")
        self.assertNotEqual(result.returncode, 0)

    def test_origin_url_is_read_from_git(self) -> None:
        # Event 3950 finding 4: origin is computed in code, not self-reported by the publish agent.
        c = self.repos.commit("c", "src/c.py")
        report = self.preflight(c, c)
        self.assertEqual(report["origin_url"], self.repos.git("remote", "get-url", "origin"))
        self.assertEqual(report["origin_url"], str(self.repos.origin))


class PreflightProtectedPathTests(PublishCheckCase):
    def test_protected_hits_use_the_root_manifest_globs(self) -> None:
        # Event 4049 finding 1: "*.dispatch.json" is a glob to match, not a file name to test.
        self.repos.write("demo.dispatch.json", json.dumps({**MANIFEST, "notes": ["edited"]}))
        a = self.repos.commit("manifest")
        b = self.repos.commit("workflow", ".claude/workflows/new.js", "src/app.py")
        c = self.repos.commit("schema", "schemas/item.json", "docs/readme.md")
        report = self.preflight(c, a, b, c)
        self.assertEqual(report["protected_hits"], sorted([".claude/workflows/new.js", "demo.dispatch.json", "schemas/item.json"]))

    def test_paths_already_on_origin_are_not_hits(self) -> None:
        # .claude/workflows/old.js and demo.dispatch.json were added by the base commit on origin/main.
        c = self.repos.commit("plain", "src/c.py")
        report = self.preflight(c, c)
        self.assertEqual(report["protected_hits"], [])

    def test_an_exact_protected_path_and_a_deletion_are_hits(self) -> None:
        b = self.repos.commit("routing", "model-routing.json")
        self.repos.git("rm", "-q", ".claude/workflows/old.js")
        c = self.repos.commit("delete")
        report = self.preflight(c, b, c)
        self.assertEqual(report["protected_hits"], sorted([".claude/workflows/old.js", "model-routing.json"]))


class PreflightWithoutManifestTests(PublishCheckCase):
    manifest = None

    def test_a_repo_without_a_manifest_still_gets_the_protection_floor(self) -> None:
        c = self.repos.commit("c", ".claude/workflows/x.js", "src/ok.py")
        report = self.preflight(c, c)
        self.assertEqual(report["protected_hits"], [".claude/workflows/x.js"])
        self.assertSameSet(report["expected"], [c])


class ConfirmTests(PublishCheckCase):
    def _second_clone(self) -> Path:
        other = self.repos.root / "other"
        self.repos.run(self.repos.root, "clone", "-q", str(self.repos.origin), str(other))
        self.repos.configure(other)
        return other

    def test_a_push_is_confirmed_only_when_origin_main_contains_the_tip(self) -> None:
        c = self.repos.commit("c", "src/c.py")
        self.assertFalse(self.confirm(c, "pushed")["confirmed"])
        self.repos.git("push", "-q", "origin", f"{c}:refs/heads/main")
        self.assertTrue(self.confirm(c, "pushed")["confirmed"])
        self.assertTrue(self.confirm(c, "already-on-origin")["confirmed"])

    def test_confirmation_reads_the_remote_not_the_local_tracking_ref(self) -> None:
        c = self.repos.commit("c", "src/c.py")
        # A publish agent cannot fake a push by moving the local remote-tracking ref.
        self.repos.git("update-ref", "refs/remotes/origin/main", c)
        self.assertFalse(self.confirm(c, "pushed")["confirmed"])
        # And a real push is seen even when the local tracking ref is stale.
        self.repos.git("push", "-q", "origin", f"{c}:refs/heads/main")
        self.repos.git("update-ref", "refs/remotes/origin/main", self.repos.base)
        self.assertTrue(self.confirm(c, "pushed")["confirmed"])

    def test_a_pr_hand_back_is_confirmed_by_the_publish_branch_at_the_tip(self) -> None:
        b = self.repos.commit("b", "src/b.py")
        c = self.repos.commit("c", "src/c.py")
        branch = f"dispatch/publish-{c[:12]}"
        for action in ("pr-opened", "needs-hand-pass-pr"):
            with self.subTest(action=action, branch="missing"):
                self.assertFalse(self.confirm(c, action)["confirmed"])
        self.repos.git("push", "-q", "origin", f"{b}:refs/heads/{branch}")
        for action in ("pr-opened", "needs-hand-pass-pr"):
            with self.subTest(action=action, branch="elsewhere"):
                self.assertFalse(self.confirm(c, action)["confirmed"])
        self.repos.git("push", "-q", "--force", "origin", f"{c}:refs/heads/{branch}")
        # Delete the local tracking ref so only the remote can answer.
        self.repos.git("update-ref", "-d", f"refs/remotes/origin/{branch}")
        for action in ("pr-opened", "needs-hand-pass-pr"):
            with self.subTest(action=action, branch="at-tip"):
                self.assertTrue(self.confirm(c, action)["confirmed"])
        # A push of main is not a PR hand-back.
        self.assertFalse(self.confirm(c, "pushed")["confirmed"])

    def test_a_push_made_from_another_clone_is_confirmed(self) -> None:
        c = self.repos.commit("c", "src/c.py")
        other = self._second_clone()
        self.repos.run(other, "fetch", "-q", str(self.repos.work), "main:refs/heads/incoming")
        self.repos.run(other, "push", "-q", "origin", "incoming:refs/heads/main")
        self.assertTrue(self.confirm(c, "pushed")["confirmed"])


if __name__ == "__main__":
    unittest.main()
