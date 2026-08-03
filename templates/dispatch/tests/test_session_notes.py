from __future__ import annotations

import argparse
import copy
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / "scripts" / "session_notes.py"
SPEC = importlib.util.spec_from_file_location("session_notes", SCRIPT)
assert SPEC and SPEC.loader
NOTES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NOTES)

EXAMPLES_DIR = Path(__file__).parents[1] / "session-mechanization"
BASE_NOTE = json.loads((EXAMPLES_DIR / "session-note.example.json").read_text(encoding="utf-8"))


def _make_note(note_id: str, created_at: str, *, kind: str = "handover", supersedes=None, repo: str = "agentops", target_refs=None) -> dict:
    note = copy.deepcopy(BASE_NOTE)
    note["note_id"] = note_id
    note["created_at"] = created_at
    note["note_kind"] = kind
    note["supersedes"] = supersedes
    note["repo"] = {"project": repo}
    note["target_refs"] = target_refs if target_refs is not None else []
    return note


def _write_note(root: Path, note: dict) -> Path:
    notes_dir = root / "session-notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / f"{note['note_id']}.json"
    path.write_text(json.dumps(note), encoding="utf-8")
    return path


NOTE_A = "0f1e2d3c-4b5a-4978-8b6c-1a2b3c4d5e6f"
NOTE_B = "1a2b3c4d-5e6f-4788-9a0b-1c2d3e4f5061"
NOTE_C = "2b3c4d5e-6f70-4819-9a0b-2c3d4e5f6071"
NOTE_D = "3c4d5e6f-7081-492a-9b0c-3d4e5f607182"


class NewNoteTests(unittest.TestCase):
    def test_new_note_builds_a_schema_valid_artifact(self) -> None:
        note = NOTES.new_note(repo="agentops", kind="handover", body="test body")
        NOTES.VALIDATOR.validate_session_note(note, Path("<generated:test>"))
        self.assertEqual(note["schema_version"], "session-note/v1")
        self.assertEqual(note["repo"], {"project": "agentops"})
        self.assertEqual(note["note_kind"], "handover")
        self.assertIsNone(note["supersedes"])
        self.assertFalse(note["privacy"]["raw_transcript_captured"])

    def test_new_note_rejects_unknown_kind_before_writing(self) -> None:
        with self.assertRaises(ValueError):
            NOTES.new_note(repo="agentops", kind="not-a-real-kind", body="x")


class AppendAndLoadTests(unittest.TestCase):
    def test_append_writes_validating_artifact_under_session_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            note = NOTES.new_note(repo="agentops", kind="summary", body="did the thing")
            path = NOTES.append(root, note)
            self.assertTrue(path.is_file())
            self.assertEqual(path.parent.name, "session-notes")
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["note_id"], note["note_id"])

    def test_load_notes_validates_every_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_note(root, _make_note(NOTE_A, "2026-07-23T14:00:00Z"))
            _write_note(root, _make_note(NOTE_B, "2026-07-23T15:00:00Z"))
            notes = NOTES.load_notes(root)
            self.assertEqual({n["note_id"] for n in notes}, {NOTE_A, NOTE_B})

    def test_load_notes_empty_root_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(NOTES.load_notes(Path(tmp)), [])


class ResolveLatestTests(unittest.TestCase):
    def test_single_note_is_its_own_latest(self) -> None:
        notes = [_make_note(NOTE_A, "2026-07-23T14:00:00Z")]
        latest = NOTES.resolve_latest(notes)
        self.assertEqual(latest["note_id"], NOTE_A)

    def test_supersede_chain_resolves_to_the_head_not_the_newest_raw_timestamp(self) -> None:
        # B supersedes A. B is the head even though we also add a later-timestamped
        # non-head note C is not present here -- this isolates plain chain-walking.
        notes = [
            _make_note(NOTE_A, "2026-07-23T14:00:00Z"),
            _make_note(NOTE_B, "2026-07-23T15:00:00Z", supersedes=NOTE_A),
        ]
        latest = NOTES.resolve_latest(notes)
        self.assertEqual(latest["note_id"], NOTE_B)

    def test_two_concurrent_heads_tiebreak_on_newest_created_at(self) -> None:
        # A and B are both heads (neither supersedes the other) -- concurrent /clear
        # sessions in the same repo. Newest created_at wins.
        notes = [
            _make_note(NOTE_A, "2026-07-23T14:00:00Z"),
            _make_note(NOTE_B, "2026-07-23T16:00:00Z"),
        ]
        latest = NOTES.resolve_latest(notes)
        self.assertEqual(latest["note_id"], NOTE_B)

    def test_two_concurrent_heads_equal_timestamp_tiebreaks_on_note_id(self) -> None:
        notes = [
            _make_note(NOTE_B, "2026-07-23T14:00:00Z"),
            _make_note(NOTE_A, "2026-07-23T14:00:00Z"),
        ]
        latest = NOTES.resolve_latest(notes)
        # NOTE_B > NOTE_A lexicographically
        self.assertEqual(latest["note_id"], NOTE_B)

    def test_dangling_supersedes_ref_does_not_raise(self) -> None:
        missing = "9" * 8 + "-" + "9" * 4 + "-" + "9" * 4 + "-" + "9" * 4 + "-" + "9" * 12
        notes = [_make_note(NOTE_A, "2026-07-23T14:00:00Z", supersedes=missing)]
        latest = NOTES.resolve_latest(notes)
        self.assertEqual(latest["note_id"], NOTE_A)

    def test_cycle_does_not_infinite_loop_and_returns_deterministic_result(self) -> None:
        # A supersedes B and B supersedes A: neither is an uncontested head.
        # Must not hang or raise; must fall back to newest by (created_at, note_id).
        notes = [
            _make_note(NOTE_A, "2026-07-23T14:00:00Z", supersedes=NOTE_B),
            _make_note(NOTE_B, "2026-07-23T15:00:00Z", supersedes=NOTE_A),
        ]
        latest = NOTES.resolve_latest(notes)
        self.assertEqual(latest["note_id"], NOTE_B)

    def test_kind_filter_excludes_non_matching_notes(self) -> None:
        notes = [
            _make_note(NOTE_A, "2026-07-23T14:00:00Z", kind="handover"),
            _make_note(NOTE_B, "2026-07-23T16:00:00Z", kind="outcome"),
        ]
        latest = NOTES.resolve_latest(notes, kind="handover")
        self.assertEqual(latest["note_id"], NOTE_A)

    def test_no_notes_resolves_to_none(self) -> None:
        self.assertIsNone(NOTES.resolve_latest([]))

    def test_no_matching_kind_resolves_to_none(self) -> None:
        notes = [_make_note(NOTE_A, "2026-07-23T14:00:00Z", kind="handover")]
        self.assertIsNone(NOTES.resolve_latest(notes, kind="outcome"))


class ListNotesTests(unittest.TestCase):
    def test_list_sorts_newest_first(self) -> None:
        notes = [
            _make_note(NOTE_A, "2026-07-23T14:00:00Z"),
            _make_note(NOTE_B, "2026-07-23T16:00:00Z"),
            _make_note(NOTE_C, "2026-07-23T15:00:00Z"),
        ]
        listed = NOTES.list_notes(notes)
        self.assertEqual([n["note_id"] for n in listed], [NOTE_B, NOTE_C, NOTE_A])

    def test_list_filters_by_kind(self) -> None:
        notes = [
            _make_note(NOTE_A, "2026-07-23T14:00:00Z", kind="handover"),
            _make_note(NOTE_B, "2026-07-23T15:00:00Z", kind="outcome"),
        ]
        listed = NOTES.list_notes(notes, kind="outcome")
        self.assertEqual([n["note_id"] for n in listed], [NOTE_B])


class ResolveLatestMultiTests(unittest.TestCase):
    """resolve_latest_multi takes bare artifact roots (no caller-supplied labels):
    each note is already self-describing via its own repo.project field, so the
    reported repo attribution is derived from the winning note, not from the caller.
    """

    def test_picks_newest_across_two_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a), Path(tmp_b)
            _write_note(root_a, _make_note(NOTE_A, "2026-07-23T14:00:00Z", repo="agentops"))
            _write_note(root_b, _make_note(NOTE_B, "2026-07-23T18:00:00Z", repo="vuoro"))
            result = NOTES.resolve_latest_multi([root_a, root_b])
            self.assertEqual(result["note"]["note_id"], NOTE_B)
            self.assertEqual(result["repo"], "vuoro")

    def test_older_repo_is_ignored_when_newer_repo_has_a_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a), Path(tmp_b)
            _write_note(root_a, _make_note(NOTE_A, "2026-07-23T18:00:00Z", repo="agentops"))
            _write_note(root_b, _make_note(NOTE_B, "2026-07-23T14:00:00Z", repo="vuoro"))
            result = NOTES.resolve_latest_multi([root_a, root_b])
            self.assertEqual(result["repo"], "agentops")

    def test_empty_repo_root_among_roots_is_skipped_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a), Path(tmp_b)
            _write_note(root_b, _make_note(NOTE_B, "2026-07-23T14:00:00Z", repo="vuoro"))
            result = NOTES.resolve_latest_multi([root_a, root_b])
            self.assertEqual(result["repo"], "vuoro")

    def test_no_notes_anywhere_resolves_to_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            result = NOTES.resolve_latest_multi([Path(tmp_a), Path(tmp_b)])
            self.assertIsNone(result)


class AppendCommandTests(unittest.TestCase):
    def test_cmd_append_writes_and_prints_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = NOTES.cmd_append(
                    argparse.Namespace(
                        root=root,
                        repo="agentops",
                        kind="handover",
                        body="cli round trip",
                        target_refs=None,
                        supersedes=None,
                        runtime_session_id=None,
                    )
                )
            self.assertEqual(rc, 0)
            written = list((root / "session-notes").glob("*.json"))
            self.assertEqual(len(written), 1)
            self.assertIn(str(written[0]), buf.getvalue())


class LatestCommandTests(unittest.TestCase):
    def test_cmd_latest_prints_json_note_when_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_note(root, _make_note(NOTE_A, "2026-07-23T14:00:00Z"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = NOTES.cmd_latest(argparse.Namespace(root=[root], kind=None))
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["note"]["note_id"], NOTE_A)

    def test_cmd_latest_exits_nonzero_when_nothing_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = NOTES.cmd_latest(argparse.Namespace(root=[Path(tmp)], kind=None))
            self.assertEqual(rc, 1)


class ListCommandTests(unittest.TestCase):
    def test_cmd_list_prints_json_array_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_note(root, _make_note(NOTE_A, "2026-07-23T14:00:00Z"))
            _write_note(root, _make_note(NOTE_B, "2026-07-23T16:00:00Z"))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = NOTES.cmd_list(argparse.Namespace(root=root, kind=None))
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual([n["note_id"] for n in out], [NOTE_B, NOTE_A])


if __name__ == "__main__":
    unittest.main()
