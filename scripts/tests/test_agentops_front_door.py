"""The `agentops` front door, estate status roll-up and dispatch run --dry-run."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "bin/agentops"
FIXTURES = Path(__file__).resolve().parent / "fixtures/estate_status/live-2026-10-14"
sys.path.insert(0, str(ROOT / "scripts"))
import estate_status as estate  # noqa: E402


def agentops(*args, **kw):
    return subprocess.run([str(BIN), *args], text=True, capture_output=True, **kw)


@pytest.mark.parametrize("args", [(), ("--help",), ("-h",), ("help",)])
def test_help_is_grouped_stdout_exit_zero(args):
    r = agentops(*args)
    assert r.returncode == 0 and r.stderr == ""
    assert "Start here:" in r.stdout and "estate status" in r.stdout and "Examples:" in r.stdout


def test_version_is_short_commit():
    r = agentops("--version")
    assert r.returncode == 0 and r.stdout.startswith("agentops ")


def test_topics_describe_each_topic():
    out = agentops("topics", "--all").stdout
    assert "handoff" in out and "check-protected-paths" in out and "Fail when" in out


def test_unknown_topic_suggests_and_exits_2():
    r = agentops("hadnoff")
    assert r.returncode == 2 and "did you mean handoff" in r.stderr


def test_families_list_members_and_keep_spellings():
    assert "estate status" in agentops("estate").stdout
    assert "dispatch run" in agentops("dispatch").stdout
    r = agentops("dispatch", "rn")
    assert r.returncode == 2 and "did you mean dispatch run" in r.stderr
    for spelling in (("estate", "status"), ("handoff",), ("dispatch", "run"), ("cli-contract",)):
        out = agentops(*spelling, "--help").stdout
        assert "usage: agentops " + " ".join(spelling) in out, spelling
    assert "agentops handoff" in agentops("help", "handoff").stdout
    assert agentops("dispatch-run", "--help").returncode == 0


def replayed():
    return estate.build_report(estate.Probe(replay=FIXTURES), list(estate.ENVIRONMENTS), fetch=False)


def test_overall_rolls_up_gates_with_next_commands():
    roll = replayed()["overall"]
    assert roll["verdict"] == "blocked"
    assert sum(roll["counts"].values()) == len(roll["environments"]) == 5
    for row in roll["environments"]:
        assert ("next" in row) == (row["state"] != "clear")
        for cmd in row.get("next", []):
            assert cmd.startswith("agentops estate status --env " + row["id"])


def test_markdown_leads_with_verdict_and_never_cuts_json():
    text = estate.render_markdown(replayed(), elapsed=1.5)
    assert text.startswith("Estate: ✗ blocked · ") and "1.5s" in text
    assert estate._cell({"a": 1, "b": "x" * 300}, 40).count("{") == 0
    assert estate._cell(list(range(100)), 30).endswith("more")


def test_exit_code_flag(tmp_path):
    base = ["estate", "status", "--replay", str(FIXTURES)]
    assert agentops(*base).returncode == 0
    assert agentops(*base, "--exit-code").returncode == 1
    saved = agentops(*base, "--json").stdout
    (tmp_path / "r.json").write_text(saved)
    assert agentops("estate", "status", "--from", str(tmp_path / "r.json"), "--exit-code").returncode == 1
    old = json.loads(saved)
    del old["overall"]  # a report saved before the roll-up existed still renders
    (tmp_path / "old.json").write_text(json.dumps(old))
    assert agentops("estate", "status", "--from", str(tmp_path / "old.json")).stdout.startswith("Estate:")


def test_dispatch_run_dry_run_starts_nothing(tmp_path):
    tree = tmp_path / "t"
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "codex").write_text('#!/bin/sh\necho "usage --model -s --output-last-message"\n')
    (fake / "codex").chmod(0o755)
    status = tmp_path / "s.json"
    r = agentops("dispatch", "run", "--dry-run", "--worker", "codex", "--model", "gpt-6-luna",
                 "--worktree", str(tree), "--status-file", str(status), "do it",
                 env=dict(os.environ, PATH=f"{fake}:{os.environ['PATH']}"))
    assert r.returncode == 0 and "command:" in r.stdout and "--model gpt-6-luna" in r.stdout
    assert not status.exists()


@pytest.mark.parametrize("topic", [name for name, _ in __import__("agentops_front").START_HERE])
def test_start_here_usage_is_spelled_as_typed(topic):
    r = agentops(*topic.split(), "--help")
    assert r.returncode == 0 and r.stdout.startswith(f"usage: agentops {topic}")


def test_replay_markdown_is_byte_identical():
    for extra in ([], ["--all"]):
        base = ["estate", "status", "--replay", str(FIXTURES), *extra]
        first, second = agentops(*base), agentops(*base)
        assert first.returncode == second.returncode == 0
        assert first.stdout == second.stdout
        assert not re.search(r"\d\.\ds\b", first.stdout.splitlines()[0])  # no elapsed time in a replay


def test_default_status_is_short_and_json_carries_operator_schema():
    short = agentops("estate", "status", "--replay", str(FIXTURES)).stdout.splitlines()
    assert len(short) <= 24 and short[-1] == "full report: agentops estate status --all"
    assert any(line.startswith("next: ") for line in short)
    full = agentops("estate", "status", "--replay", str(FIXTURES), "--all").stdout
    assert "# Estate status" in full
    doc = json.loads(agentops("estate", "status", "--replay", str(FIXTURES), "--json").stdout)
    assert doc["schema"] == "agentops.estate-status/v1" and doc["schema_version"] == "estate-status/v1"


def test_saved_report_without_gates_reemits_as_unknown(tmp_path):
    saved = json.loads(agentops("estate", "status", "--replay", str(FIXTURES), "--json").stdout)
    del saved["overall"]
    for env in saved["environments"]:
        env.pop("gate")
    (tmp_path / "r.json").write_text(json.dumps(saved))
    for extra in ([], ["--json"]):
        r = agentops("estate", "status", "--from", str(tmp_path / "r.json"), *extra)
        assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["overall"]["verdict"] == "unknown"
