"""Tests for the quote verifier (agentops#2437, context-economy Phase 1 arm b).

Synthetic fixtures only: small in-memory JSONL transcripts built with
tmp_path, following test_measure.py's helpers. No test reads
/home/agent/.claude/projects or any committed scorecard's host-specific
numbers -- the decomposition math and the adjusted-attribution view must
hold for any corpus, not just this host's.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "verify.py"

_spec = importlib.util.spec_from_file_location("context_economy_verify", SCRIPT)
verify = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(verify)


def _line(**kwargs) -> str:
    return json.dumps(kwargs)


def _assistant_tool_use(tool_id: str, name: str, command: str = "") -> str:
    inp = {"command": command} if name == "Bash" else {}
    return _line(
        type="assistant",
        timestamp="2026-09-01T00:00:00.000Z",
        message={"content": [{"type": "tool_use", "id": tool_id, "name": name, "input": inp}]},
    )


def _tool_result(tool_id: str, text: str) -> str:
    return _line(
        type="user",
        timestamp="2026-09-01T00:00:01.000Z",
        message={"content": [{"type": "tool_result", "tool_use_id": tool_id, "content": text}]},
    )


def _write_transcript(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _sessions_with_mixed_bash_classes(tmp_path: Path) -> list[dict]:
    """One session with a Bash file-read (cat), a Bash git call, a Bash
    'other' command, and one Read-tool call, plus some message text."""
    root = tmp_path / "transcripts"
    f = root / "sess1.jsonl"
    _write_transcript(f, [
        _line(type="assistant", timestamp="2026-09-01T00:00:00.000Z",
              message={"content": [{"type": "text", "text": "z" * 1000}]}),
        _assistant_tool_use("t1", "Bash", "cat foo.py"),
        _tool_result("t1", "a" * 300),  # file-read class, 300 bash bytes
        _assistant_tool_use("t2", "Bash", "git status"),
        _tool_result("t2", "b" * 200),  # git class, 200 bash bytes
        _assistant_tool_use("t3", "Bash", "echo hello"),
        _tool_result("t3", "c" * 100),  # other class, 100 bash bytes
        _assistant_tool_use("t4", "Read"),
        _tool_result("t4", "d" * 50),  # 50 read bytes
    ])
    return [verify.measure.scan_file(str(f), str(root))]


def test_decompose_bash_sums_by_class(tmp_path: Path):
    sessions = _sessions_with_mixed_bash_classes(tmp_path)
    by_class = verify.decompose_bash(sessions)
    assert by_class == {"file-read": 300, "git": 200, "other": 100}


def test_bash_numerator_decomposition_sums_to_bash_numerator(tmp_path: Path):
    sessions = _sessions_with_mixed_bash_classes(tmp_path)
    attribution = verify.build_attribution(sessions)
    total_bash = sum(row["chars"] for row in attribution["bash_numerator_decomposition"].values())
    assert total_bash == attribution["bash_numerator_chars"] == 600

    total_share_of_bash = sum(
        row["share_of_bash_numerator"] for row in attribution["bash_numerator_decomposition"].values()
    )
    assert total_share_of_bash == pytest.approx(1.0)


def test_decomposition_shares_are_of_bash_and_of_context(tmp_path: Path):
    sessions = _sessions_with_mixed_bash_classes(tmp_path)
    attribution = verify.build_attribution(sessions)
    denom = attribution["denominator_chars"]
    file_read_row = attribution["bash_numerator_decomposition"]["file-read"]
    assert file_read_row["chars"] == 300
    assert file_read_row["share_of_bash_numerator"] == pytest.approx(300 / 600)
    assert file_read_row["share_of_context"] == pytest.approx(300 / denom)


def test_adjusted_view_moves_bash_file_read_class_to_read(tmp_path: Path):
    sessions = _sessions_with_mixed_bash_classes(tmp_path)
    attribution = verify.build_attribution(sessions)
    adjusted = attribution["adjusted"]
    # 300 bash file-read chars move from bash to read.
    assert adjusted["bash_file_read_chars"] == 300
    assert adjusted["adjusted_bash_chars"] == 600 - 300
    assert adjusted["adjusted_read_chars"] == 50 + 300
    denom = attribution["denominator_chars"]
    assert adjusted["adjusted_bash_share"] == pytest.approx((600 - 300) / denom)
    assert adjusted["adjusted_file_read_share"] == pytest.approx((50 + 300) / denom)
    # Attribution is conservative: total bash+read bytes are unchanged, only
    # relabeled between the two shares.
    original_bash_read = attribution["bash_numerator_chars"] + 50
    adjusted_bash_read = adjusted["adjusted_bash_chars"] + adjusted["adjusted_read_chars"]
    assert adjusted_bash_read == original_bash_read


def test_adjusted_view_is_noop_when_no_bash_file_reads(tmp_path: Path):
    root = tmp_path / "transcripts"
    f = root / "sess1.jsonl"
    _write_transcript(f, [
        _line(type="assistant", timestamp="2026-09-01T00:00:00.000Z",
              message={"content": [{"type": "text", "text": "z" * 100}]}),
        _assistant_tool_use("t1", "Bash", "git status"),
        _tool_result("t1", "b" * 200),
    ])
    sessions = [verify.measure.scan_file(str(f), str(root))]
    attribution = verify.build_attribution(sessions)
    adjusted = attribution["adjusted"]
    assert adjusted["bash_file_read_chars"] == 0
    assert adjusted["adjusted_bash_chars"] == attribution["bash_numerator_chars"]
    assert adjusted["adjusted_read_chars"] == 0
    assert "file-read" not in attribution["bash_numerator_decomposition"]


def test_build_scorecard_carries_both_snapshots_and_phase1_reference(tmp_path: Path):
    sessions = _sessions_with_mixed_bash_classes(tmp_path)
    scorecard = verify.build_scorecard(sessions, str(tmp_path / "transcripts"), days=30)
    assert scorecard["study"] == "context-economy-phase1-bash-attribution"
    assert scorecard["phase1_reference_snapshot"] == verify.PHASE1_REFERENCE_SNAPSHOT
    assert scorecard["this_run_snapshot"]["denominator_chars"] == scorecard["denominator_chars"]
    assert scorecard["this_run_snapshot"]["bash_numerator_chars"] == scorecard["bash_numerator_chars"] == 600
    assert "snapshots_are_two_live_reads_of_the_same_corpus" in scorecard["caveats"]
    assert "bash_numerator_decomposition_answers_the_file_read_label_question" in scorecard["caveats"]
    # The phase1_reference_snapshot values must never be recomputed from this
    # (synthetic, unrelated) corpus.
    assert scorecard["phase1_reference_snapshot"]["denominator_chars"] == 1877174
    assert scorecard["phase1_reference_snapshot"]["bash_numerator_chars"] == 1095814


def test_classes_used_in_decomposition_are_from_classes_module(tmp_path: Path):
    """The decomposition must key off classes.cls(), not a private copy."""
    sessions = _sessions_with_mixed_bash_classes(tmp_path)
    by_class = verify.decompose_bash(sessions)
    for name in by_class:
        assert name in {n for n, _ in verify.classes.CLASSES} | {'other'}


def test_help_flag_exits_cleanly():
    parser = verify.build_argparser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_main_writes_scorecard_to_out(tmp_path: Path):
    root = tmp_path / "transcripts"
    f = root / "sess1.jsonl"
    _write_transcript(f, [
        _line(type="assistant", timestamp="2026-09-01T00:00:00.000Z",
              message={"content": [{"type": "text", "text": "z" * 100}]}),
        _assistant_tool_use("t1", "Bash", "cat foo.py"),
        _tool_result("t1", "a" * 40),
    ])
    out = tmp_path / "out" / "scorecard.json"
    rc = verify.main(["--root", str(root), "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text())
    assert data["bash_numerator_chars"] == 40
    assert data["bash_numerator_decomposition"]["file-read"]["chars"] == 40
