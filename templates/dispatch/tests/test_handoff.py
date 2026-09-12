"""Oracle for handoff/v1 (context-economy plan, phase 3).

Three properties carry the design; the rest of `handoff.py` is rendering.

1. **The schema means something.** A handoff that omits `next_action`, carries a
   `diff_sha256` that is not a digest, or grows a field nobody declared must be
   rejected *before* it is written, not discovered by a successor.
2. **Exactly one successor.** `ack` is the single-active-successor guard. A
   second ack must refuse, must name the live successor, and must leave the file
   byte-identical -- a guard that refuses but half-writes is not a guard.
3. **A stale tree is refused.** `diff_sha256` exists so a successor can prove the
   working tree is the one the predecessor left. If validation passed on a moved
   tree the field would be decoration. Digest v2 extends that to the *contents*
   of untracked files, which v1 could not see; both definitions are pinned here,
   because `validate` must compute the one the file declares or every handoff
   written before v2 would start refusing.
4. **One guard, two hosts.** Once the file is scp'd to the successor's machine
   there are two copies. The ack off-origin must go through the origin's copy,
   so a remote refusal leaves the local file untouched and a remote acceptance
   updates both. Tested against an injected transport: a second machine is not
   available in CI and the guard branches only on the transport's exit status.

The subject is `templates/dispatch/scripts/handoff.py`. Real git repositories are
built in tmp_path rather than mocked: the digest is defined in terms of `git diff
HEAD` and `git status --porcelain`, and a fake that returns fixed strings would
prove nothing about that definition.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


handoff = _load_module("handoff_subject", SCRIPTS / "handoff.py")


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=test@example.invalid",
         "-c", "user.name=test", *args],
        capture_output=True, text=True, check=True)
    return proc.stdout


def _make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    (path / "file.txt").write_text("one\n")
    _git(path, "add", "file.txt")
    _git(path, "commit", "-q", "-m", "initial")
    return path


class TestSchema(unittest.TestCase):
    """The declared schema is enforced, and enforced eagerly."""

    def setUp(self) -> None:
        self.valid = {
            "schema_version": "handoff/v1",
            "handoff_id": "2026-09-12-example.v1",
            "version": 1,
            "created_at": "2026-09-12T00:00:00Z",
            "predecessor": {
                "harness": "claude-code",
                "session_id": "sess-1",
                "transcript_path": "/tmp/t.jsonl",
                "model": "claude-opus-5",
                "context_used_pct": 61.0,
            },
            "objective": "finish the thing",
            "constraints": ["do not push"],
            "decisions": [{"what": "json canonical", "why": "ack needs a parser"}],
            "rejected": [{"what": "prose canonical", "why": "no rename-safe parser"}],
            "state": {
                "repos": [{
                    "path": "/projects/dev/agentops",
                    "head": "0" * 40,
                    "branch": "main",
                    "dirty": False,
                    "diff_sha256": "a" * 64,
                    "unpushed": 0,
                }],
                "running": [],
            },
            "unresolved": [],
            "evidence": [{"kind": "artifact", "ref": "docs/plan.md"}],
            "sprintctl_bundle_ref": None,
            "next_action": "run the tests",
            "successor": {"session_id": None, "acknowledged_at": None},
        }

    def test_valid_instance_has_no_violations(self) -> None:
        self.assertEqual(handoff.schema_errors(self.valid), [])

    def test_schema_itself_is_auditable_by_the_repository_checker(self) -> None:
        # schema_check raises UnsupportedKeyword on any construct it cannot
        # enforce, so a clean run over a deliberately broken instance proves the
        # whole schema -- every $defs branch included -- was audited, not just
        # the parts this instance reaches.
        self.assertNotEqual(handoff.schema_errors({}), [])

    def test_missing_next_action_is_rejected(self) -> None:
        del self.valid["next_action"]
        self.assertTrue(any("next_action" in e for e in handoff.schema_errors(self.valid)))

    def test_empty_next_action_is_rejected(self) -> None:
        self.valid["next_action"] = ""
        self.assertNotEqual(handoff.schema_errors(self.valid), [])

    def test_diff_sha256_must_be_a_digest(self) -> None:
        self.valid["state"]["repos"][0]["diff_sha256"] = "not-a-digest"
        self.assertNotEqual(handoff.schema_errors(self.valid), [])

    def test_undeclared_field_is_rejected(self) -> None:
        self.valid["notes"] = "smuggled"
        self.assertNotEqual(handoff.schema_errors(self.valid), [])

    def test_evidence_kind_is_closed(self) -> None:
        self.valid["evidence"] = [{"kind": "slack", "ref": "x"}]
        self.assertNotEqual(handoff.schema_errors(self.valid), [])

    def test_digest_version_is_optional_and_must_be_an_integer(self) -> None:
        self.assertEqual(handoff.schema_errors(self.valid), [])   # absent: v1
        self.valid["state"]["digest_version"] = 2
        self.assertEqual(handoff.schema_errors(self.valid), [])
        self.valid["state"]["digest_version"] = "2"
        self.assertNotEqual(handoff.schema_errors(self.valid), [])

    def test_origin_fields_are_optional_and_nullable(self) -> None:
        self.valid["origin_host"] = "workstation"
        self.valid["origin_path"] = "/projects/dev/agentops/x.json"
        self.assertEqual(handoff.schema_errors(self.valid), [])
        self.valid["origin_host"] = None
        self.valid["origin_path"] = None
        self.assertEqual(handoff.schema_errors(self.valid), [])
        self.valid["origin_host"] = ""
        self.assertNotEqual(handoff.schema_errors(self.valid), [])

    def test_successor_may_be_set(self) -> None:
        self.valid["successor"] = {
            "session_id": "sess-2", "acknowledged_at": "2026-09-12T01:00:00Z"}
        self.assertEqual(handoff.schema_errors(self.valid), [])


class TestCreateAndValidate(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = _make_repo(self.tmp / "repo")
        self.out = self.tmp / "handoffs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _create(self, slug: str = "example") -> Path:
        rc = handoff.main([
            "create", "--slug", slug, "--repo", str(self.repo),
            "--objective", "finish the thing",
            "--next-action", "run the tests",
            "--constraint", "do not push",
            "--no-sprintctl", "--out-dir", str(self.out),
            "--date", "2026-09-12",
        ])
        self.assertEqual(rc, 0)
        return next(self.out.glob(f"*-{slug}.v1.json"))

    def test_create_writes_json_and_rendered_markdown(self) -> None:
        path = self._create()
        self.assertTrue(path.with_suffix(".md").exists())
        data = json.loads(path.read_text())
        self.assertEqual(data["handoff_id"], "2026-09-12-example.v1")
        self.assertIsNone(data["successor"]["session_id"])
        self.assertEqual(handoff.schema_errors(data), [])

    def test_second_create_bumps_the_version_rather_than_overwriting(self) -> None:
        first = self._create()
        handoff.main([
            "create", "--slug", "example", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        second = self.out / "2026-09-12-example.v2.json"
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(json.loads(second.read_text())["version"], 2)

    def test_empty_next_action_is_refused_before_anything_is_written(self) -> None:
        rc = handoff.main([
            "create", "--slug", "empty", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "   ", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        self.assertEqual(rc, 1)
        self.assertEqual(list(self.out.glob("*empty*")), [])

    def test_validate_accepts_an_untouched_tree(self) -> None:
        path = self._create()
        self.assertEqual(handoff.validate_handoff(json.loads(path.read_text())), [])

    def test_validate_refuses_a_stale_diff(self) -> None:
        path = self._create()
        (self.repo / "file.txt").write_text("two\n")  # the tree moves
        problems = handoff.validate_handoff(json.loads(path.read_text()))
        self.assertTrue(problems)
        self.assertTrue(any("stale diff_sha256" in p for p in problems), problems)
        self.assertEqual(handoff.main(["validate", str(path)]), 1)

    def test_an_untracked_file_alone_makes_the_diff_stale(self) -> None:
        # `git diff HEAD` says nothing about an untracked file; the porcelain
        # half is what catches it, and dropping it would let a successor inherit
        # a file it was never told about while validation still passed.
        path = self._create()
        (self.repo / "scratch.txt").write_text("untracked\n")
        problems = handoff.validate_handoff(json.loads(path.read_text()))
        self.assertTrue(any("stale diff_sha256" in p for p in problems), problems)

    def test_validate_refuses_a_missing_repo_path(self) -> None:
        path = self._create()
        data = json.loads(path.read_text())
        data["state"]["repos"][0]["path"] = str(self.tmp / "gone")
        self.assertTrue(any("does not exist" in p
                            for p in handoff.validate_handoff(data)))

    def test_validate_refuses_an_unresolvable_head(self) -> None:
        path = self._create()
        data = json.loads(path.read_text())
        data["state"]["repos"][0]["head"] = "b" * 40
        self.assertTrue(any("does not resolve" in p
                            for p in handoff.validate_handoff(data)))

    def test_no_tree_check_still_enforces_schema_and_paths(self) -> None:
        path = self._create()
        (self.repo / "file.txt").write_text("two\n")
        self.assertEqual(
            handoff.validate_handoff(json.loads(path.read_text()),
                                     check_tree=False), [])

    def test_dirty_tree_is_recorded_and_recomputes_stably(self) -> None:
        (self.repo / "file.txt").write_text("dirty\n")
        path = self._create("dirty")
        data = json.loads(path.read_text())
        self.assertTrue(data["state"]["repos"][0]["dirty"])
        self.assertEqual(handoff.validate_handoff(data), [])

    def test_draft_file_supplies_fields(self) -> None:
        draft = self.tmp / "draft.json"
        draft.write_text(json.dumps({
            "slug": "drafted",
            "objective": "from the draft",
            "next_action": "do the drafted thing",
            "constraints": ["a", "b"],
            "decisions": [{"what": "w", "why": "y"}],
        }))
        rc = handoff.main([
            "create", "--repo", str(self.repo), "--draft", str(draft),
            "--no-sprintctl", "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        self.assertEqual(rc, 0)
        data = json.loads((self.out / "2026-09-12-drafted.v1.json").read_text())
        self.assertEqual(data["objective"], "from the draft")
        self.assertEqual(data["constraints"], ["a", "b"])

    def test_prompt_carries_constraints_next_action_and_the_readonly_rule(self) -> None:
        path = self._create()
        text = handoff.render_prompt(json.loads(path.read_text()), path)
        self.assertIn("do not push", text)
        self.assertIn("run the tests", text)
        self.assertIn("READ-ONLY", text)
        self.assertIn("ack", text)


class TestAckGuard(unittest.TestCase):
    """Exactly one successor, and a refusal that changes nothing."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = _make_repo(self.tmp / "repo")
        self.out = self.tmp / "handoffs"
        handoff.main([
            "create", "--slug", "acked", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        self.path = self.out / "2026-09-12-acked.v1.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_ack_sets_the_successor(self) -> None:
        handoff.ack(self.path, "sess-first")
        data = json.loads(self.path.read_text())
        self.assertEqual(data["successor"]["session_id"], "sess-first")
        self.assertIsNotNone(data["successor"]["acknowledged_at"])
        self.assertEqual(handoff.schema_errors(data), [])

    def test_second_ack_is_refused_and_names_the_live_successor(self) -> None:
        handoff.ack(self.path, "sess-first")
        with self.assertRaises(handoff.HandoffError) as caught:
            handoff.ack(self.path, "sess-second")
        self.assertIn("sess-first", str(caught.exception))

    def test_a_refused_ack_leaves_the_file_byte_identical(self) -> None:
        handoff.ack(self.path, "sess-first")
        before = self.path.read_bytes()
        with self.assertRaises(handoff.HandoffError):
            handoff.ack(self.path, "sess-second")
        self.assertEqual(self.path.read_bytes(), before)

    def test_cli_ack_exits_nonzero_on_the_second_claim(self) -> None:
        self.assertEqual(
            handoff.main(["ack", str(self.path), "--session-id", "sess-first"]), 0)
        self.assertEqual(
            handoff.main(["ack", str(self.path), "--session-id", "sess-second"]), 1)

    def test_ack_leaves_no_temp_file_behind(self) -> None:
        handoff.ack(self.path, "sess-first")
        self.assertEqual(list(self.out.glob(".*tmp")), [])

    def test_ack_refreshes_the_rendered_markdown(self) -> None:
        handoff.ack(self.path, "sess-first")
        self.assertIn("sess-first", self.path.with_suffix(".md").read_text())

    def test_write_atomic_replaces_rather_than_truncating(self) -> None:
        # The guard reads this file to decide whether a second successor may
        # start; a truncated read is indistinguishable from an unacked handoff.
        # os.replace guarantees a reader sees either the old file or the new one.
        target = self.tmp / "atomic.json"
        target.write_text('{"a": 1}')
        handoff.write_atomic(target, '{"a": 2}')
        self.assertEqual(json.loads(target.read_text()), {"a": 2})
        self.assertEqual([p for p in self.tmp.iterdir() if p.name.startswith(".")], [])


class TestDigestDefinition(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _make_repo(Path(self._tmp.name) / "repo")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_digest_is_stable_across_calls(self) -> None:
        self.assertEqual(handoff.diff_sha256(self.repo),
                         handoff.diff_sha256(self.repo))

    def test_digest_changes_with_an_uncommitted_edit(self) -> None:
        before = handoff.diff_sha256(self.repo)
        (self.repo / "file.txt").write_text("changed\n")
        self.assertNotEqual(before, handoff.diff_sha256(self.repo))

    def test_v1_matches_the_documented_definition(self) -> None:
        import hashlib
        (self.repo / "file.txt").write_text("changed\n")
        (self.repo / "new.txt").write_text("new\n")
        expected = hashlib.sha256()
        expected.update(_git(self.repo, "diff", "HEAD").encode())
        expected.update(_git(self.repo, "status", "--porcelain").encode())
        self.assertEqual(handoff.diff_sha256(self.repo, 1), expected.hexdigest())

    def test_v2_matches_the_documented_definition(self) -> None:
        import hashlib
        (self.repo / "file.txt").write_text("changed\n")
        (self.repo / "b.txt").write_text("bee\n")
        (self.repo / "a.txt").write_text("ay\n")
        expected = hashlib.sha256()
        expected.update(_git(self.repo, "diff", "HEAD").encode())
        expected.update(_git(self.repo, "status", "--porcelain").encode())
        for name in ("a.txt", "b.txt"):   # sorted by path bytes
            content = hashlib.sha256((self.repo / name).read_bytes()).hexdigest()
            expected.update(b"\0" + name.encode() + b"\0" + content.encode())
        self.assertEqual(handoff.diff_sha256(self.repo, 2), expected.hexdigest())

    def test_v1_is_blind_to_an_untracked_content_change(self) -> None:
        # The defect v2 exists to fix, asserted rather than described: `git
        # status --porcelain` names the path and never its bytes.
        (self.repo / "notes.txt").write_text("first\n")
        before = handoff.diff_sha256(self.repo, 1)
        (self.repo / "notes.txt").write_text("second\n")
        self.assertEqual(before, handoff.diff_sha256(self.repo, 1))

    def test_v2_detects_an_untracked_content_change(self) -> None:
        (self.repo / "notes.txt").write_text("first\n")
        before = handoff.diff_sha256(self.repo, 2)
        (self.repo / "notes.txt").write_text("second\n")
        self.assertNotEqual(before, handoff.diff_sha256(self.repo, 2))

    def test_v2_still_detects_a_tracked_edit_and_a_new_untracked_file(self) -> None:
        base = handoff.diff_sha256(self.repo, 2)
        (self.repo / "file.txt").write_text("changed\n")
        edited = handoff.diff_sha256(self.repo, 2)
        self.assertNotEqual(base, edited)
        (self.repo / "new.txt").write_text("new\n")
        self.assertNotEqual(edited, handoff.diff_sha256(self.repo, 2))

    def test_v2_is_stable_across_calls(self) -> None:
        (self.repo / "notes.txt").write_text("first\n")
        self.assertEqual(handoff.diff_sha256(self.repo, 2),
                         handoff.diff_sha256(self.repo, 2))

    def test_v2_hashes_a_binary_untracked_file_without_error(self) -> None:
        # Bytes, not text: a decode step here would raise on the first PNG a
        # session left in the tree, and the digest would be unusable exactly
        # when a successor most needs it.
        blob = bytes(range(256)) + b"\x00\xff\xfe" * 32
        (self.repo / "image.bin").write_bytes(blob)
        first = handoff.diff_sha256(self.repo, 2)
        self.assertRegex(first, r"^[0-9a-f]{64}$")
        (self.repo / "image.bin").write_bytes(blob + b"\x01")
        self.assertNotEqual(first, handoff.diff_sha256(self.repo, 2))

    def test_v2_ignores_gitignored_files(self) -> None:
        (self.repo / ".gitignore").write_text("junk/\n")
        _git(self.repo, "add", ".gitignore")
        _git(self.repo, "commit", "-q", "-m", "ignore junk")
        before = handoff.diff_sha256(self.repo, 2)
        (self.repo / "junk").mkdir()
        (self.repo / "junk" / "x.tmp").write_text("noise\n")
        self.assertEqual(before, handoff.diff_sha256(self.repo, 2))

    def test_an_unknown_digest_version_is_refused_not_guessed(self) -> None:
        with self.assertRaises(handoff.HandoffError):
            handoff.diff_sha256(self.repo, 99)


class TestDigestVersionCompatibility(unittest.TestCase):
    """The version field exists so old handoffs keep validating."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = _make_repo(self.tmp / "repo")
        self.out = self.tmp / "handoffs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _create(self, slug: str) -> Path:
        handoff.main([
            "create", "--slug", slug, "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        return self.out / f"2026-09-12-{slug}.v1.json"

    def test_create_writes_version_2(self) -> None:
        data = json.loads(self._create("fresh").read_text())
        self.assertEqual(data["state"]["digest_version"], 2)

    def test_a_v1_handoff_without_the_field_still_validates(self) -> None:
        # Exactly the shape of the four evidence handoffs already committed
        # under docs/dispatch/handoffs: no state.digest_version at all.
        path = self._create("legacy")
        data = json.loads(path.read_text())
        del data["state"]["digest_version"]
        data["state"]["repos"][0]["diff_sha256"] = handoff.diff_sha256(self.repo, 1)
        path.write_text(json.dumps(data, indent=2) + "\n")
        self.assertEqual(handoff.validate_handoff(json.loads(path.read_text())), [])

    def test_the_committed_evidence_handoffs_declare_no_digest_version(self) -> None:
        # If a later change starts stamping the field into these, the
        # compatibility path above stops being exercised by anything real.
        committed = sorted(
            (ROOT / "docs/dispatch/handoffs").glob("*.v*.json"))
        self.assertTrue(committed, "no committed handoffs to check")
        for path in committed:
            if path.name.endswith("sprintctl-bundle.json"):
                continue
            with self.subTest(path.name):
                data = json.loads(path.read_text())
                self.assertNotIn("digest_version", data["state"])
                self.assertEqual(handoff.schema_errors(data), [])

    def test_a_v2_handoff_is_refused_when_an_untracked_file_changes(self) -> None:
        (self.repo / "scratch.txt").write_text("before\n")
        path = self._create("guarded")
        self.assertEqual(handoff.validate_handoff(json.loads(path.read_text())), [])
        (self.repo / "scratch.txt").write_text("after\n")
        problems = handoff.validate_handoff(json.loads(path.read_text()))
        self.assertTrue(any("stale diff_sha256" in p for p in problems), problems)


class _RecordingTransport:
    """Stands in for ssh. Records calls, returns a scripted exit status."""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, list[str]]] = []

    def run(self, host: str, argv: list[str]):
        self.calls.append((host, argv))
        returncode, stdout, stderr = self.results.pop(0)
        return subprocess.CompletedProcess(
            [host, *argv], returncode, stdout, stderr)


class TestTwoHostAck(unittest.TestCase):
    """One guard when the file lives on two hosts.

    The handoff is scp'd to the successor's host, so the guard would become two
    files and two independent claims. `ack` off-origin must take the
    authoritative ack on the origin first and touch the local copy only if that
    succeeded.
    """

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = _make_repo(self.tmp / "repo")
        self.out = self.tmp / "handoffs"
        handoff.main([
            "create", "--slug", "crosshost", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
            "--origin-host", "workstation",
        ])
        self.path = self.out / "2026-09-12-crosshost.v1.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_records_the_origin_host_and_path(self) -> None:
        data = json.loads(self.path.read_text())
        self.assertEqual(data["origin_host"], "workstation")
        self.assertEqual(data["origin_path"], str(self.path.resolve()))
        self.assertEqual(handoff.schema_errors(data), [])

    def test_on_the_origin_host_no_transport_is_used(self) -> None:
        transport = _RecordingTransport()
        handoff.ack(self.path, "sess-local",
                    transport=transport, hostname="workstation")
        self.assertEqual(transport.calls, [])
        self.assertEqual(
            json.loads(self.path.read_text())["successor"]["session_id"],
            "sess-local")

    def test_a_remote_refusal_leaves_the_local_file_untouched(self) -> None:
        before = self.path.read_bytes()
        transport = _RecordingTransport(
            (1, "", "handoff: already has a live successor: sess-other"))
        with self.assertRaises(handoff.HandoffError) as caught:
            handoff.ack(self.path, "sess-second",
                        transport=transport, hostname="devbox")
        self.assertIn("sess-other", str(caught.exception))
        self.assertIn("workstation", str(caught.exception))
        self.assertEqual(self.path.read_bytes(), before)

    def test_a_remote_acceptance_updates_both_copies(self) -> None:
        transport = _RecordingTransport((0, "acknowledged\n", ""))
        handoff.ack(self.path, "sess-first",
                    transport=transport, hostname="devbox")
        host, argv = transport.calls[0]
        self.assertEqual(host, "workstation")          # the origin's copy
        self.assertEqual(argv[:3], ["agentops", "handoff", "ack"])
        self.assertIn(str(self.path.resolve()), argv)  # the origin's path
        self.assertIn("sess-first", argv)
        local = json.loads(self.path.read_text())      # and then the local one
        self.assertEqual(local["successor"]["session_id"], "sess-first")
        self.assertIsNotNone(local["successor"]["acknowledged_at"])
        self.assertEqual(handoff.schema_errors(local), [])

    def test_a_missing_agentops_on_the_origin_falls_back_to_python3(self) -> None:
        transport = _RecordingTransport(
            (127, "", "bash: agentops: command not found"),
            (0, "acknowledged\n", ""))
        handoff.ack(self.path, "sess-first",
                    transport=transport, hostname="devbox")
        self.assertEqual(len(transport.calls), 2)
        _, argv = transport.calls[1]
        self.assertEqual(argv[0], "python3")
        self.assertTrue(argv[1].endswith("handoff.py"))
        self.assertEqual(
            json.loads(self.path.read_text())["successor"]["session_id"],
            "sess-first")

    def test_a_locally_acked_handoff_refuses_before_reaching_the_origin(self) -> None:
        handoff.ack(self.path, "sess-first",
                    transport=_RecordingTransport((0, "", "")),
                    hostname="devbox")
        transport = _RecordingTransport()
        with self.assertRaises(handoff.HandoffError):
            handoff.ack(self.path, "sess-second",
                        transport=transport, hostname="devbox")
        self.assertEqual(transport.calls, [])

    def test_a_handoff_without_an_origin_acks_locally_anywhere(self) -> None:
        # Handoffs written before the two-host guard existed have no origin_host
        # and must keep working, on any host, without an ssh attempt.
        data = json.loads(self.path.read_text())
        data.pop("origin_host")
        data.pop("origin_path")
        self.path.write_text(json.dumps(data, indent=2) + "\n")
        transport = _RecordingTransport()
        handoff.ack(self.path, "sess-first",
                    transport=transport, hostname="somewhere-else")
        self.assertEqual(transport.calls, [])
        self.assertEqual(
            json.loads(self.path.read_text())["successor"]["session_id"],
            "sess-first")

    def test_local_hostname_is_overridable_by_the_environment(self) -> None:
        import os
        previous = os.environ.get("AGENTOPS_HOSTNAME")
        os.environ["AGENTOPS_HOSTNAME"] = "pretend-host"
        try:
            self.assertEqual(handoff.local_hostname(), "pretend-host")
        finally:
            if previous is None:
                del os.environ["AGENTOPS_HOSTNAME"]
            else:
                os.environ["AGENTOPS_HOSTNAME"] = previous


if __name__ == "__main__":
    unittest.main()
