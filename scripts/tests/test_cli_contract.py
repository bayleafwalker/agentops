"""Tests for the operator interface conformance checker (scripts/cli_contract.py)."""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cli_contract  # noqa: E402

GOOD = textwrap.dedent('''
    import json, sys
    HELP = "demo: one purpose line\\n\\nStart here:\\n  status  what needs you\\n\\nExamples:\\n  demo status\\n"
    a = sys.argv[1:]
    if not a or a == ["--help"]:
        print(HELP); sys.exit(0)
    if a == ["--version"]:
        print("demo 1.2.3"); sys.exit(0)
    if a == ["status", "--help"]:
        print("usage: demo status [--json]"); sys.exit(0)
    if a == ["status"]:
        print("context: demo\\nNothing needs you.\\nnext: demo status --json"); sys.exit(0)
    if a == ["status", "--json"]:
        print(json.dumps({"schema": "demo.status/v1"})); sys.exit(0)
    if a[0].startswith("-"):
        print("error: unknown option", file=sys.stderr); sys.exit(2)
    print(f"error: no such command {a[0]!r}; did you mean status?", file=sys.stderr); sys.exit(2)
''')

BROKEN_SUBHELP = GOOD.replace(
    'print("usage: demo status [--json]"); sys.exit(0)',
    'raise ValueError("max() iterable argument is empty")',
)


def _tool(tmp_path: Path, body: str) -> list[str]:
    script = tmp_path / "demo.py"
    script.write_text(body)
    return [sys.executable, str(script)]


def _run(capsys, cmd: list[str]) -> tuple[int, dict[str, str]]:
    code = cli_contract.main(["--json", "--command", "status", "--status", "status", "--", *cmd])
    doc = json.loads(capsys.readouterr().out)
    assert doc["schema"] == cli_contract.SCHEMA
    return code, {c["id"]: c["result"] for c in doc["checks"]}


@pytest.mark.parametrize("name", ["commit", "apply", "seed", "status", "ls", "handoff", "a"])
def test_misspelling_never_equals_the_real_command(name):
    assert cli_contract.typo_of(name) != name


def test_conforming_tool_passes_every_check(tmp_path, capsys):
    code, results = _run(capsys, _tool(tmp_path, GOOD))
    assert code == 0, results
    assert set(results.values()) == {"pass"}


def test_crashing_subcommand_help_fails(tmp_path, capsys):
    code, results = _run(capsys, _tool(tmp_path, BROKEN_SUBHELP))
    assert code == 1
    assert results["help.subcommand"] == "fail"


def test_status_json_must_exit_zero(tmp_path, capsys):
    body = GOOD.replace(
        'print(json.dumps({"schema": "demo.status/v1"})); sys.exit(0)',
        'print(json.dumps({"schema": "demo.status/v1"})); sys.exit(1)',
    )
    _, results = _run(capsys, _tool(tmp_path, body))
    assert results["status.json"] == "fail"


def test_examples_needs_a_heading_not_a_substring(tmp_path, capsys):
    body = GOOD.replace("Examples:\\n  demo status", "for example run demo status")
    _, results = _run(capsys, _tool(tmp_path, body))
    assert results["help.examples"] == "fail"
