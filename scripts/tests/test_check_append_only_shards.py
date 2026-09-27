"""The append-only guard must discriminate, not merely pass.

A guard that returns 0 for everything looks identical to a guard that works, so
every case here pairs a violation with a positive control in the same repository.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

try:
    import pytest
except ImportError as exc:  # pragma: no cover - depends on the host interpreter
    # These are pytest-style tests (fixtures/parametrize). The registered
    # full-suite command is `python -m unittest discover`, which cannot run
    # them and must stay cold-green on a host without pytest: report a skip
    # instead of an import error. Run them with `python -m pytest`.
    import unittest

    raise unittest.SkipTest(f"pytest-style module needs pytest: {exc}") from exc

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "check_append_only_shards.py"

_spec = importlib.util.spec_from_file_location("check_append_only_shards", SCRIPT)
guard = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(guard)

SHARD = "_artifacts/demo/audit/events-2026-08-29.ndjson"
LINE_ONE = '{"id":"ad:1","summary":"first"}'
LINE_TWO = '{"id":"ad:2","summary":"second"}'


def _run(repo: Path, *args: str) -> str:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return ""


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _run(root, "init", "-q", "-b", "main")
    _run(root, "config", "user.email", "t@example.invalid")
    _run(root, "config", "user.name", "t")
    shard = root / SHARD
    shard.parent.mkdir(parents=True)
    shard.write_text(LINE_ONE + "\n")
    _run(root, "add", "-A")
    _run(root, "commit", "-qm", "base")
    monkeypatch.chdir(root)
    return root


def _commit(repo: Path, message: str) -> None:
    _run(repo, "add", "-A")
    _run(repo, "commit", "-qm", message)


def test_appending_a_line_is_allowed(repo: Path) -> None:
    (repo / SHARD).write_text(LINE_ONE + "\n" + LINE_TWO + "\n")
    _commit(repo, "append")

    assert guard.check("HEAD~1", "HEAD") == []


def test_a_brand_new_shard_is_allowed(repo: Path) -> None:
    new = repo / "_artifacts/other/audit/events-2026-08-30.ndjson"
    new.parent.mkdir(parents=True)
    new.write_text(LINE_TWO + "\n")
    _commit(repo, "new shard")

    assert guard.check("HEAD~1", "HEAD") == []


def test_rewriting_an_existing_line_is_refused(repo: Path) -> None:
    (repo / SHARD).write_text('{"id":"ad:1","summary":"REWRITTEN"}\n')
    _commit(repo, "rewrite")

    violations = guard.check("HEAD~1", "HEAD")
    assert len(violations) == 1
    assert "line 1 rewritten" in violations[0]


def test_truncating_a_shard_is_refused(repo: Path) -> None:
    (repo / SHARD).write_text(LINE_ONE + "\n" + LINE_TWO + "\n")
    _commit(repo, "append")
    (repo / SHARD).write_text(LINE_ONE + "\n")
    _commit(repo, "truncate")

    violations = guard.check("HEAD~1", "HEAD")
    assert len(violations) == 1
    assert "truncated" in violations[0]


def test_deleting_a_shard_is_refused(repo: Path) -> None:
    (repo / SHARD).unlink()
    _commit(repo, "delete")

    violations = guard.check("HEAD~1", "HEAD")
    assert len(violations) == 1
    assert "deleted" in violations[0]


def test_non_shard_paths_are_ignored(repo: Path) -> None:
    """The guard must not police ordinary files, only audit shards."""
    notes = repo / "_artifacts/demo/session-notes/note.json"
    notes.parent.mkdir(parents=True)
    notes.write_text("{}\n")
    _commit(repo, "add note")
    notes.write_text('{"changed": true}\n')
    _commit(repo, "rewrite note")

    assert guard.check("HEAD~1", "HEAD") == []


def test_exit_code_signals_the_violation(repo: Path) -> None:
    (repo / SHARD).write_text('{"id":"ad:1","summary":"REWRITTEN"}\n')
    _commit(repo, "rewrite")

    assert guard.main(["--base", "HEAD~1", "--head", "HEAD"]) == 1
    # Positive control: the same invocation over an untouched range passes.
    assert guard.main(["--base", "HEAD", "--head", "HEAD"]) == 0


def test_a_branch_behind_base_is_not_a_deletion(repo: Path) -> None:
    # main gains a shard and a line after the branch forks; the branch touches
    # neither. Two-dot against main's tip saw both as "deleted" by the branch.
    _run(repo, "checkout", "-q", "-b", "topic")
    (repo / "notes.md").write_text("docs only\n")
    _commit(repo, "topic change")
    _run(repo, "checkout", "-q", "main")
    (repo / SHARD).write_text(LINE_ONE + "\n" + LINE_TWO + "\n")
    newer = repo / "_artifacts/demo/audit/events-2026-08-30.ndjson"
    newer.write_text(LINE_ONE + "\n")
    _commit(repo, "main appends")

    assert guard.check("main", "topic") == []


def test_a_branch_behind_base_still_cannot_rewrite(repo: Path) -> None:
    # The merge-base comparison must not excuse a rewrite of a line that
    # existed when the branch forked.
    _run(repo, "checkout", "-q", "-b", "topic")
    (repo / SHARD).write_text('{"id":"ad:1","summary":"REWRITTEN"}\n')
    _commit(repo, "topic rewrites")
    _run(repo, "checkout", "-q", "main")
    (repo / "notes.md").write_text("main moves on\n")
    _commit(repo, "main moves")

    violations = guard.check("main", "topic")
    assert len(violations) == 1 and "line 1 rewritten" in violations[0]
