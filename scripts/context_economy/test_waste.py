"""Tests for the Bash-result waste scanner (relocated from outctl@94840d7)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "waste.py"

_spec = importlib.util.spec_from_file_location("context_economy_waste", SCRIPT)
waste_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(waste_mod)


def _line(**kwargs) -> str:
    return json.dumps(kwargs)


def _bash_tool_use(tool_id: str, command: str) -> str:
    return _line(type="assistant", message={"content": [{"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}]})


def _bash_result(tool_id: str, text: str, is_error: bool = False) -> str:
    d = {"type": "tool_result", "tool_use_id": tool_id, "content": text}
    if is_error:
        d["is_error"] = True
    return _line(type="user", message={"content": [d]})


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def test_cls_matches_first_class():
    assert waste_mod.cls("cat foo.py") == "file-read"
    assert waste_mod.cls("git status") == "git"
    assert waste_mod.cls("echo hi") == "other"


def test_duplicate_bash_results_are_counted(tmp_path: Path):
    root = tmp_path / "transcripts"
    f = root / "sess.jsonl"
    dup_text = "x" * 300  # over the 200-byte dedup floor
    _write(f, [
        _bash_tool_use("t1", "cat a.txt"),
        _bash_result("t1", dup_text),
        _bash_tool_use("t2", "cat a.txt"),
        _bash_result("t2", dup_text),  # exact duplicate -> counted as waste
    ])
    G, per = waste_mod.scan_root(str(root))
    assert G["dup_n"] == 1
    assert G["dup_bytes"] == len(dup_text)
    assert G["tot"] == 2 * len(dup_text)
    assert G["n"] == 2


def test_small_duplicates_under_floor_are_not_counted(tmp_path: Path):
    root = tmp_path / "transcripts"
    f = root / "sess.jsonl"
    tiny = "ok"  # under the 200-byte floor
    _write(f, [
        _bash_tool_use("t1", "echo ok"),
        _bash_result("t1", tiny),
        _bash_tool_use("t2", "echo ok"),
        _bash_result("t2", tiny),
    ])
    G, per = waste_mod.scan_root(str(root))
    assert G["dup_n"] == 0
    assert G["dup_bytes"] == 0


def test_error_results_are_counted(tmp_path: Path):
    root = tmp_path / "transcripts"
    f = root / "sess.jsonl"
    _write(f, [
        _bash_tool_use("t1", "false"),
        _bash_result("t1", "command not found", is_error=True),
    ])
    G, per = waste_mod.scan_root(str(root))
    assert G["errn"] == 1
    assert G["errbytes"] == len("command not found")


def test_only_you_hint_is_counted(tmp_path: Path):
    root = tmp_path / "transcripts"
    f = root / "sess.jsonl"
    hint_text = "Only you see that command's output"
    _write(f, [
        _bash_tool_use("t1", "ls"),
        _bash_result("t1", hint_text),
    ])
    G, per = waste_mod.scan_root(str(root))
    assert G["hint"] == 1
    assert G["hintbytes"] == len(hint_text)
