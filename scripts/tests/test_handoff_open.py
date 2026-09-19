"""Oracle for `agentops handoff open` and `continue-entry` (backlog #2429).

Interactive continuation reads `docs/dispatch/handoffs/*.json` by hand today,
and on 2026-09-19 a session assembling `~/continue` by hand almost overwrote
another track's live entry. These two subcommands replace that by-hand step:

1. **`open`** must list exactly the unacked handoffs, collapsed to the newest
   version per track (falling back to slug for files with no `track`), with a
   launch cwd that uses the recorded `origin_cwd` and falls back to the first
   repo path for files that predate it.
2. **`continue-entry --into`** must be surgical: it changes only its own
   `<!-- handoff:<track> -->`...`<!-- /handoff:<track> -->` section of the
   operator's scratchpad, leaving operator prose and every other track's
   section byte-identical, and re-running it is a no-op on the bytes.

Real handoff files are built with `handoff.main(["create", ...])` rather than
hand-assembled dicts, so these tests exercise the same path `create` writes
through in production.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


handoff = _load_module("handoff_open_subject", SCRIPTS / "handoff.py")


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


class TestOpen(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = _make_repo(self.tmp / "repo")
        self.out = self.tmp / "handoffs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _create(self, slug: str, *, date: str = "2026-09-12",
               track: str | None = None, cwd: str | None = None) -> Path:
        args = [
            "create", "--slug", slug, "--repo", str(self.repo),
            "--objective", "o", "--next-action", f"do {slug}",
            "--no-sprintctl", "--out-dir", str(self.out), "--date", date,
        ]
        if track:
            args += ["--track", track]
        if cwd:
            args += ["--origin-cwd", cwd]
        rc = handoff.main(args)
        self.assertEqual(rc, 0)
        return sorted(
            self.out.glob(f"{date}-{slug}.v*.json"),
            key=lambda p: int(p.name.rsplit(".v", 1)[1][:-len(".json")]),
        )[-1]

    def test_open_lists_an_unacked_handoff(self) -> None:
        self._create("s6")
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["track"], "s6")
        self.assertEqual(rows[0]["next_action"], "do s6")

    def test_acked_handoffs_never_appear(self) -> None:
        path = self._create("s6")
        handoff.ack(path, "sess-1")
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(rows, [])

    def test_superseded_versions_never_appear_only_the_newest(self) -> None:
        self._create("weekly-lanes")
        second = self._create("weekly-lanes")  # same date+slug -> v2
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["handoff_id"], json.loads(second.read_text())["handoff_id"])
        self.assertTrue(rows[0]["handoff_id"].endswith(".v2"))

    def test_collapses_by_explicit_track_across_different_slugs(self) -> None:
        self._create("s6-a", track="s6", date="2026-09-12")
        self._create("s6-b", track="s6", date="2026-09-13")
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["track"], "s6")
        self.assertEqual(rows[0]["handoff_id"], "2026-09-13-s6-b.v1")

    def test_ack_on_one_version_still_lets_another_version_of_the_same_slug_stand(self) -> None:
        first = self._create("codex-acceptance")
        second = self._create("codex-acceptance")
        handoff.ack(first, "sess-1")
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["handoff_id"], json.loads(second.read_text())["handoff_id"])

    def test_cwd_uses_the_recorded_origin_cwd(self) -> None:
        self._create("s6", cwd="/somewhere/predecessor/was")
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(rows[0]["cwd"], "/somewhere/predecessor/was")

    def test_cwd_falls_back_to_the_first_repo_path_for_legacy_files(self) -> None:
        path = self._create("legacy")
        data = json.loads(path.read_text())
        data.pop("origin_cwd", None)
        data.pop("track", None)
        path.write_text(json.dumps(data, indent=2) + "\n")
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(rows[0]["cwd"], data["state"]["repos"][0]["path"])
        self.assertEqual(rows[0]["track"], "legacy")  # fallback to slug

    def test_launch_line_uses_the_recorded_cwd_and_the_file_path(self) -> None:
        path = self._create("s6", cwd="/wherever")
        rows = handoff.open_handoffs(self.out)
        line = handoff.launch_line(rows[0])
        self.assertTrue(line.startswith("cd /wherever && claude --bg --session-id "))
        self.assertIn(str(path), line)
        self.assertIn('"$(agentops handoff prompt', line)

    def test_launch_line_uuid_is_fresh_each_call(self) -> None:
        self._create("s6")
        rows = handoff.open_handoffs(self.out)
        first = handoff.launch_line(rows[0])
        second = handoff.launch_line(rows[0])
        self.assertNotEqual(first, second)

    def test_a_directory_that_does_not_exist_lists_nothing(self) -> None:
        rows = handoff.open_handoffs(self.out / "does-not-exist")
        self.assertEqual(rows, [])

    def test_bundle_and_markdown_siblings_are_not_mistaken_for_handoffs(self) -> None:
        self._create("s6")
        rows = handoff.open_handoffs(self.out)
        self.assertEqual(len(rows), 1)  # not double-counted via the .md sibling

    def test_cli_open_json_includes_every_row_with_a_launch_line(self) -> None:
        self._create("s6")
        self._create("weekly-lanes")
        out = self.tmp / "capture.json"
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = handoff.main(["open", "--json", "--dir", str(self.out)])
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertEqual({row["track"] for row in payload}, {"s6", "weekly-lanes"})
        for row in payload:
            self.assertIn("launch", row)
            self.assertTrue(row["launch"].startswith("cd "))


class TestContinueEntry(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = _make_repo(self.tmp / "repo")
        self.out = self.tmp / "handoffs"
        rc = handoff.main([
            "create", "--slug", "s6", "--repo", str(self.repo),
            "--objective", "close s6", "--next-action", "run the tests",
            "--no-sprintctl", "--out-dir", str(self.out), "--date", "2026-09-19",
            "--origin-cwd", "/projects/dev/agentops",
        ])
        self.assertEqual(rc, 0)
        self.path = next(self.out.glob("2026-09-19-s6.v*.json"))
        self.handoff = json.loads(self.path.read_text())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_section_is_delimited_by_the_track_markers(self) -> None:
        section = handoff.render_continue_entry(self.handoff, self.path)
        self.assertTrue(section.startswith("<!-- handoff:s6 -->\n"))
        self.assertTrue(section.rstrip("\n").endswith("<!-- /handoff:s6 -->"))
        self.assertIn("close s6", section)
        self.assertIn("run the tests", section)
        self.assertIn("cd /projects/dev/agentops && claude --bg --session-id", section)

    def test_into_appends_when_the_file_is_new(self) -> None:
        target = self.tmp / "continue"
        rc = handoff.main([
            "continue-entry", str(self.path), "--into", str(target)])
        self.assertEqual(rc, 0)
        text = target.read_text()
        self.assertIn("<!-- handoff:s6 -->", text)
        self.assertIn("<!-- /handoff:s6 -->", text)

    def test_into_creates_missing_parent_directories(self) -> None:
        target = self.tmp / "nested" / "dir" / "continue"
        handoff.main(["continue-entry", str(self.path), "--into", str(target)])
        self.assertTrue(target.exists())

    def test_into_changes_only_its_own_section_byte_exact(self) -> None:
        target = self.tmp / "continue"
        operator_prose = (
            "# Operator scratchpad\n\n"
            "Some hand-written notes at the top.\n\n"
        )
        other_track_a = (
            "<!-- handoff:s3-d14 -->\n"
            "### 2026-09-18-s3-d14.v2\n\n"
            "cd /somewhere && claude --bg --session-id "
            "11111111-1111-1111-1111-111111111111 "
            '"$(agentops handoff prompt /somewhere/x.json)"\n\n'
            "**Objective.** other track a\n"
            "<!-- /handoff:s3-d14 -->\n"
        )
        other_track_b = (
            "\n<!-- handoff:weekly-lanes -->\n"
            "### 2026-09-15-weekly-lanes.v1\n\n"
            "some other body text\nwith multiple lines\n"
            "<!-- /handoff:weekly-lanes -->\n"
        )
        trailer = "\n# trailing operator note\n"
        before = operator_prose + other_track_a + other_track_b + trailer
        target.write_text(before)

        rc = handoff.main([
            "continue-entry", str(self.path), "--into", str(target)])
        self.assertEqual(rc, 0)
        after = target.read_text()

        # everything outside the s6 section survives byte-exact
        self.assertIn(operator_prose, after)
        self.assertIn(other_track_a, after)
        self.assertIn(other_track_b, after)
        self.assertIn(trailer, after)
        # and the s6 section itself was inserted
        self.assertIn("<!-- handoff:s6 -->", after)
        self.assertIn("<!-- /handoff:s6 -->", after)
        # nothing else in the file was reordered or truncated
        self.assertEqual(
            after.replace(
                after[after.index("<!-- handoff:s6 -->"):
                     after.index("<!-- /handoff:s6 -->") + len("<!-- /handoff:s6 -->") + 1],
                ""),
            before)

    def test_into_replaces_only_its_prior_section_on_rerun(self) -> None:
        target = self.tmp / "continue"
        prose = "# scratchpad\n\n"
        other = "<!-- handoff:other -->\nkeep me\n<!-- /handoff:other -->\n"
        target.write_text(prose + other)

        handoff.main(["continue-entry", str(self.path), "--into", str(target)])
        first_pass = target.read_text()
        self.assertIn(prose, first_pass)
        self.assertIn(other, first_pass)

        # a second handoff run on the same track (e.g. an updated objective)
        updated = dict(self.handoff)
        updated["objective"] = "close s6, now with a new objective"
        stale_path = self.path.parent / "stale-s6.json"
        stale_path.write_text(json.dumps(updated, indent=2) + "\n")
        handoff.main(["continue-entry", str(stale_path), "--into", str(target)])
        second_pass = target.read_text()

        self.assertIn(prose, second_pass)
        self.assertIn(other, second_pass)
        self.assertIn("close s6, now with a new objective", second_pass)
        self.assertNotIn("close s6, now with a new objective, now with", second_pass)
        # exactly one s6 section remains
        self.assertEqual(second_pass.count("<!-- handoff:s6 -->"), 1)
        self.assertEqual(second_pass.count("<!-- /handoff:s6 -->"), 1)

    def test_into_is_idempotent_on_rerun_apart_from_the_fresh_uuid(self) -> None:
        target = self.tmp / "continue"
        target.write_text("# prose\n<!-- handoff:other -->\nx\n<!-- /handoff:other -->\n")
        handoff.main(["continue-entry", str(self.path), "--into", str(target)])
        first = target.read_bytes()
        handoff.main(["continue-entry", str(self.path), "--into", str(target)])
        second = target.read_bytes()
        # bytes differ only in the freshly-minted uuid inside the launch line;
        # strip that one line before comparing the rest byte-exact
        def _without_launch_line(data: bytes) -> bytes:
            return b"\n".join(
                line for line in data.split(b"\n")
                if not line.startswith(b"cd "))
        self.assertEqual(_without_launch_line(first), _without_launch_line(second))

    def test_without_into_prints_the_section_to_stdout(self) -> None:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = handoff.main(["continue-entry", str(self.path)])
        self.assertEqual(rc, 0)
        self.assertIn("<!-- handoff:s6 -->", buf.getvalue())
        self.assertIn("<!-- /handoff:s6 -->", buf.getvalue())


class TestTrackAndOriginCwdOnCreate(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo = _make_repo(self.tmp / "repo")
        self.out = self.tmp / "handoffs"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_track_defaults_to_the_slug(self) -> None:
        rc = handoff.main([
            "create", "--slug", "example", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        self.assertEqual(rc, 0)
        path = next(self.out.glob("*-example.v1.json"))
        data = json.loads(path.read_text())
        self.assertEqual(data["track"], "example")
        self.assertEqual(handoff.schema_errors(data), [])

    def test_explicit_track_overrides_the_slug(self) -> None:
        rc = handoff.main([
            "create", "--slug", "example-a", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
            "--track", "shared-track",
        ])
        self.assertEqual(rc, 0)
        path = next(self.out.glob("*-example-a.v1.json"))
        self.assertEqual(json.loads(path.read_text())["track"], "shared-track")

    def test_origin_cwd_defaults_to_the_process_cwd(self) -> None:
        import os
        rc = handoff.main([
            "create", "--slug", "example", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        self.assertEqual(rc, 0)
        path = next(self.out.glob("*-example.v1.json"))
        data = json.loads(path.read_text())
        self.assertEqual(data["origin_cwd"], str(Path.cwd()))

    def test_legacy_files_without_track_or_origin_cwd_still_validate(self) -> None:
        rc = handoff.main([
            "create", "--slug", "example", "--repo", str(self.repo),
            "--objective", "o", "--next-action", "n", "--no-sprintctl",
            "--out-dir", str(self.out), "--date", "2026-09-12",
        ])
        self.assertEqual(rc, 0)
        path = next(self.out.glob("*-example.v1.json"))
        data = json.loads(path.read_text())
        data.pop("track")
        data.pop("origin_cwd")
        self.assertEqual(handoff.schema_errors(data), [])

    def test_the_committed_evidence_handoffs_have_no_track_or_origin_cwd_and_still_validate(self) -> None:
        # Pinning backward compatibility against the real files committed in
        # docs/dispatch/handoffs/, same spirit as
        # TestDigestVersionCompatibility.test_the_committed_evidence_handoffs_declare_no_digest_version.
        handoffs_dir = ROOT / "docs" / "dispatch" / "handoffs"
        files = sorted(handoffs_dir.glob("*.json"))
        self.assertTrue(files)
        for path in files:
            data = json.loads(path.read_text())
            self.assertNotIn("track", data)
            self.assertNotIn("origin_cwd", data)
            self.assertEqual(handoff.schema_errors(data), [], path)


if __name__ == "__main__":
    unittest.main()
