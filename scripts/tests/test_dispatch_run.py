import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPT = Path(__file__).parents[1] / "dispatch_run.py"


def setup(tmp_path, help_text="usage: fake exec --model MODEL -s workspace-write --output-last-message FILE"):
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
                      "printf '%s\\n' \"$*\" > \"$ARGV_FILE\"\n"
                      "if [ -n \"${FAKE_SLEEP:-}\" ]; then sleep \"$FAKE_SLEEP\"; fi\n"
                      "shift 2\nwhile [ $# -gt 0 ]; do\n"
                      "  if [ \"$1\" = --output-last-message ]; then printf '%s' \"$FAKE_FINAL\" > \"$2\"; shift 2; continue; fi\n"
                      "  if [ \"$1\" = -- ]; then shift; break; fi\n  shift\ndone\n"
                      "printf '%s\\n' \"$FAKE_OUTPUT\"\n"
                      "printf '%s\\n' \"$FAKE_ERR\" >&2\nexit \"${FAKE_EXIT:-0}\"\n")
    worker.chmod(0o755)
    return tree, fakebin


def invoke(tmp_path, tree, fakebin, *, output="finished", final="finished", err="", code="0", extra=(), entry=None, prompt="outcome", sleep=""):
    status = tmp_path / "records" / "result.json"
    argv_file = tmp_path / "argv.txt"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", TMPDIR=str(tmp_path), FAKE_OUTPUT=output, FAKE_FINAL=final,
               FAKE_ERR=err, FAKE_EXIT=code, FAKE_SLEEP=sleep, ARGV_FILE=str(argv_file))
    command = ([sys.executable, str(SCRIPT)] if entry is None else [str(entry)]) + ["--worker", "codex", "--model", "gpt-6-luna",
               "--worktree", str(tree), "--status-file", str(status), *extra, prompt]
    if entry:
        command = [str(entry), "dispatch", "run", *command[1:]]
    result = subprocess.run(command,
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
                           output="ordinary log", final="DISPATCH_OUTCOME: ESCALATED\nESCALATION_REASON: missing requirement", code="7")
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


def test_record_redacts_json_quoted_keys_and_pem_before_truncating(tmp_path):
    tree, fakebin = setup(tmp_path)
    output = '{"token": "quoted-secret", "other": "ok"}\n-----BEGIN RSA PRIVATE KEY-----\nprivate-material\n-----END RSA PRIVATE KEY-----'
    _, record = invoke(tmp_path, tree, fakebin, output=output)
    serialized = json.dumps(record)
    assert "quoted-secret" not in serialized
    assert "private-material" not in serialized


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


def test_actual_argv_prompt_separator_and_leading_dash(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, _ = invoke(tmp_path, tree, fakebin, extra=("--timeout", "3"), final="done", prompt="-do this")
    assert result.returncode == 0
    argv = (tmp_path / "argv.txt").read_text()
    assert "--output-last-message" in argv and "--" in argv and "-do this" in argv
    assert not list(tmp_path.glob("agentops-dispatch-final-*"))


def test_markdown_marker_and_reason_only_when_escalated(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin, final="**DISPATCH_OUTCOME: ESCALATED**.\n- `ESCALATION_REASON: need owner.`", code="8")
    assert result.returncode == 0
    assert record["outcome"] == "escalated"
    assert record["escalation_reason"] == "need owner"
    _, record = invoke(tmp_path, tree, fakebin, final="ESCALATION_REASON: irrelevant")
    assert record["escalation_reason"] is None


def test_echoed_prompt_and_stderr_marker_do_not_escalate(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin, output="DISPATCH_OUTCOME: ESCALATED", final="finished",
                            err="DISPATCH_OUTCOME: ESCALATED")
    assert result.returncode == 0
    assert record["outcome"] == "done"


def test_dispatch_entry_strips_run(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin, entry=Path(__file__).parents[2] / "bin" / "agentops")
    assert result.returncode == 0
    assert record["outcome"] == "done"


def test_missing_cli_fails_validation(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "missing.json"
    env = dict(os.environ, PATH="/run/current-system/sw/bin:/usr/bin:/bin")
    result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "m",
                             "--worktree", str(tree), "--status-file", str(status), "prompt"],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 2
    assert "not found on PATH" in result.stderr
    assert not status.exists()


def test_attested_opencode_success_uses_final_json_text(tmp_path):
    tree, fakebin = setup(tmp_path)
    opencode = fakebin / "opencode"
    opencode.write_text("#!/bin/sh\nif [ \"$1\" = run ] && [ \"$2\" = --help ]; then\n"
                        "printf '%s\\n' 'opencode run --model --format'\nexit 0\nfi\n"
                        "printf '%s\\n' '{\"type\":\"text\",\"part\":{\"text\":\"DISPATCH_OUTCOME: ESCALATED\\nESCALATION_REASON: blocked\"}}'\n")
    opencode.chmod(0o755)
    status = tmp_path / "opencode.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "opencode", "--model", "provider/model",
                             "--data-boundary-attested", "--worktree", str(tree), "--status-file", str(status), "prompt"],
                            env=env, text=True, capture_output=True)
    record = json.loads(status.read_text())
    assert result.returncode == 0
    assert record["outcome"] == "escalated"
    assert record["escalation_reason"] == "blocked"


def test_timeout_kills_worker_and_records_marker(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin, extra=("--timeout", "0.05"), sleep="2")
    assert result.returncode == 124
    assert record["outcome"] == "failed"
    assert record["exit_code"] == 124
    assert "DISPATCH_TIMEOUT" in record["final_message_tail"]


def test_sigterm_finalizes_running_record_as_failed(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "term.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", TMPDIR=str(tmp_path), FAKE_SLEEP="10",
               FAKE_OUTPUT="", FAKE_FINAL="", FAKE_ERR="", FAKE_EXIT="0", ARGV_FILE=str(tmp_path / "argv"))
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "gpt-6-luna",
                             "--worktree", str(tree), "--status-file", str(status), "prompt"],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    import time
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if status.exists() and json.loads(status.read_text())["outcome"] == "running":
            break
        time.sleep(0.01)
    proc.terminate()
    assert proc.wait(timeout=5) == 143
    record = json.loads(status.read_text())
    assert record["outcome"] == "failed"
    assert record["exit_code"] == 143
    assert "killed" in record["final_message_tail"]
