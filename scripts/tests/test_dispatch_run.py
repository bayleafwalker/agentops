import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).parents[1] / "dispatch_run.py"


def setup(tmp_path, help_text="usage: fake exec --model MODEL -s workspace-write"):
    tree = tmp_path / "tree"
    tree.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tree, check=True)
    subprocess.run(["git", "checkout", "-qb", "worker-branch"], cwd=tree, check=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.com",
                    "commit", "--allow-empty", "-qm", "base"], cwd=tree, check=True)
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    worker = fakebin / "codex"
    worker.write_text("#!/bin/sh\nif [ \"$1\" = exec ] && [ \"$2\" = --help ]; then\n"
                      f"  printf '%s\\n' '{help_text}'\n  exit 0\nfi\n"
                      "printf '%s\\n' \"$FAKE_OUTPUT\"\nexit \"${FAKE_EXIT:-0}\"\n")
    worker.chmod(0o755)
    return tree, fakebin


def invoke(tmp_path, tree, fakebin, *, output="finished", code="0", extra=()):
    status = tmp_path / "records" / "result.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_OUTPUT=output, FAKE_EXIT=code)
    result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "gpt-6-luna",
                             "--worktree", str(tree), "--status-file", str(status), *extra, "outcome"],
                           text=True, capture_output=True, env=env)
    return result, json.loads(status.read_text()) if status.exists() else None


def test_done_writes_record(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin)
    assert result.returncode == 0
    assert record["outcome"] == "done"
    assert record["model"] == "gpt-6-luna"
    assert record["branch"] == "worker-branch"
    assert record["exit_code"] == 0


def test_escalation_marker_never_means_done(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin,
                           output="DISPATCH_OUTCOME: ESCALATED\nESCALATION_REASON: missing requirement")
    assert result.returncode == 0
    assert record["outcome"] == "escalated"
    assert record["escalation_reason"] == "missing requirement"


def test_failure_preserves_exit_code(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin, output="worker error", code="7")
    assert result.returncode == 7
    assert record["outcome"] == "failed"
    assert record["exit_code"] == 7


def test_record_redacts_common_secret_forms(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin,
                           output="password=hunter2 api_key=abc123 Bearer tokenvalue",
                           code="0")
    assert result.returncode == 0
    assert "hunter2" not in json.dumps(record)
    assert "abc123" not in json.dumps(record)
    assert "tokenvalue" not in json.dumps(record)


def test_bad_cli_flags_fail_before_worker_run(tmp_path):
    tree, fakebin = setup(tmp_path, help_text="usage: fake exec --model MODEL --full-auto")
    result, record = invoke(tmp_path, tree, fakebin)
    assert result.returncode == 2
    assert "does not advertise required flags" in result.stderr
    assert record is None


def test_opencode_requires_attestation_before_launch(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "status.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "opencode", "--model",
                             "opencode-go/deepseek-v4.1-flash", "--worktree", str(tree),
                             "--status-file", str(status), "outcome"], text=True, capture_output=True, env=env)
    assert result.returncode == 2
    assert "requires --data-boundary-attested" in result.stderr
    assert not status.exists()
