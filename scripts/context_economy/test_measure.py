"""Tests for the context-economy measure instrument (relocated from outctl@94840d7).

These build small synthetic transcript fixtures on disk (never real transcripts,
which are not reproducible) and assert the classification math: what counts
towards Bash share vs. file-read share of context, and how the two are
combined into a scorecard.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "measure.py"

_spec = importlib.util.spec_from_file_location("context_economy_measure", SCRIPT)
measure = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(measure)


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


def _assistant_text(text: str) -> str:
    return _line(
        type="assistant",
        timestamp="2026-09-01T00:00:02.000Z",
        message={"content": [{"type": "text", "text": text}]},
    )


def _write_transcript(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def test_bash_bytes_are_attributed_to_bash_share(tmp_path: Path):
    """A Bash tool_result's bytes must land in `bash`, not `read`."""
    root = tmp_path / "transcripts"
    f = root / "sess1.jsonl"
    _write_transcript(f, [
        _assistant_text("hello"),  # 5 text chars
        _assistant_tool_use("t1", "Bash", "ls"),
        _tool_result("t1", "x" * 100),  # 100 bash bytes
    ])
    s = measure.scan_file(str(f), str(root))
    assert s["bash"] == 100
    assert s["read"] == 0
    assert s["text"] > 0


def test_read_bytes_are_attributed_to_read_share(tmp_path: Path):
    """A Read tool_result's bytes must land in `read`, not `bash`."""
    root = tmp_path / "transcripts"
    f = root / "sess1.jsonl"
    _write_transcript(f, [
        _assistant_tool_use("t1", "Read"),
        _tool_result("t1", "y" * 250),  # 250 read bytes
    ])
    s = measure.scan_file(str(f), str(root))
    assert s["read"] == 250
    assert s["bash"] == 0


def test_aggregate_sums_across_sessions_and_shares_are_of_context(tmp_path: Path):
    root = tmp_path / "transcripts"
    f1 = root / "a.jsonl"
    f2 = root / "b.jsonl"
    # session 1: 100 bash bytes, 0 read, 100 text chars -> context = 200
    _write_transcript(f1, [
        _assistant_text("z" * 100),
        _assistant_tool_use("t1", "Bash", "ls"),
        _tool_result("t1", "x" * 100),
    ])
    # session 2: 0 bash, 300 read bytes, 100 text chars -> context = 400
    _write_transcript(f2, [
        _assistant_text("z" * 100),
        _assistant_tool_use("t1", "Read"),
        _tool_result("t1", "y" * 300),
    ])
    sessions = [measure.scan_file(str(f1), str(root)), measure.scan_file(str(f2), str(root))]
    agg = measure.aggregate(sessions)
    # context_chars = text_chars (incl. tool_use input JSON) + tool_result bytes (bash+read here)
    assert agg["bash_chars"] == 100
    assert agg["read_chars"] == 300
    expected_context = sum(s["text"] for s in sessions) + sum(s["tools"] for s in sessions)
    assert agg["context_chars"] == expected_context
    assert agg["context_chars"] >= 100 + 300  # at least the tool_result bytes themselves
    scorecard = measure.build_scorecard(sessions, str(root), days=None)
    assert scorecard["bash_share"]["numerator_chars"] == 100
    assert scorecard["bash_share"]["denominator_chars"] == agg["context_chars"]
    assert scorecard["file_read_share"]["numerator_chars"] == 300
    assert scorecard["bash_share"]["value"] == pytest.approx(100 / agg["context_chars"])
    assert scorecard["file_read_share"]["value"] == pytest.approx(300 / agg["context_chars"])


def test_scorecard_gate_pass_fail_thresholds(tmp_path: Path):
    root = tmp_path / "transcripts"
    f = root / "sess1.jsonl"
    # bash share well under 28%, read share well under 45%
    _write_transcript(f, [
        _assistant_text("z" * 1000),
        _assistant_tool_use("t1", "Bash", "ls"),
        _tool_result("t1", "x" * 10),
    ])
    sessions = [measure.scan_file(str(f), str(root))]
    scorecard = measure.build_scorecard(sessions, str(root), days=None)
    assert scorecard["bash_share"]["pass"] is True
    assert scorecard["bash_share"]["gate_threshold"] == pytest.approx(0.28)
    assert scorecard["file_read_share"]["gate_threshold"] == pytest.approx(0.45)

    root2 = tmp_path / "transcripts2"
    f2 = root2 / "sess1.jsonl"
    # bash share well over 28% -> gate fails
    _write_transcript(f2, [
        _assistant_text("z" * 10),
        _assistant_tool_use("t1", "Bash", "ls"),
        _tool_result("t1", "x" * 1000),
    ])
    sessions2 = [measure.scan_file(str(f2), str(root2))]
    scorecard2 = measure.build_scorecard(sessions2, str(root2), days=None)
    assert scorecard2["bash_share"]["pass"] is False


def test_date_range_and_transcript_count(tmp_path: Path):
    root = tmp_path / "transcripts"
    f1 = root / "a.jsonl"
    f2 = root / "b.jsonl"
    lines1 = [_line(type="assistant", timestamp="2026-08-20T00:00:00.000Z", message={"content": [{"type": "text", "text": "hi"}]})]
    lines2 = [_line(type="assistant", timestamp="2026-09-10T00:00:00.000Z", message={"content": [{"type": "text", "text": "hi"}]})]
    _write_transcript(f1, lines1)
    _write_transcript(f2, lines2)
    sessions = [measure.scan_file(str(f1), str(root)), measure.scan_file(str(f2), str(root))]
    agg = measure.aggregate(sessions)
    assert agg["n_sessions"] == 2
    assert agg["date_min"] == "2026-08-20"
    assert agg["date_max"] == "2026-09-10"


def test_subagent_transcripts_are_included_in_all_shares(tmp_path: Path):
    """Sessions under a /subagents/ path are still scanned; `sub` flags them
    but scan_root/aggregate include them in the totals, matching the
    outctl study's 'ALL' grouping used for the scorecard."""
    root = tmp_path / "transcripts"
    top = root / "a.jsonl"
    sub = root / "subagents" / "s1.jsonl"
    _write_transcript(top, [_assistant_text("hi")])
    _write_transcript(sub, [_assistant_text("ho")])
    s_top = measure.scan_file(str(top), str(root))
    s_sub = measure.scan_file(str(sub), str(root))
    assert s_top["sub"] is False
    assert s_sub["sub"] is True


def test_find_transcripts_days_filter(tmp_path: Path, monkeypatch):
    import os
    import time

    root = tmp_path / "transcripts"
    root.mkdir()
    recent = root / "recent.jsonl"
    old = root / "old.jsonl"
    recent.write_text("\n")
    old.write_text("\n")
    old_time = time.time() - 40 * 86400
    os.utime(old, (old_time, old_time))
    found = measure.find_transcripts(str(root), days=30)
    assert str(recent) in found
    assert str(old) not in found


def test_help_flag_exits_cleanly():
    parser = measure.build_argparser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0
