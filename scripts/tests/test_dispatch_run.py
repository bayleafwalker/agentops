import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import time
import textwrap
import pytest

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


def invoke(tmp_path, tree, fakebin, *, output="finished", final="finished", err="", code="0", extra=(), entry=None, prompt="outcome", sleep="", env_extra=None):
    status = tmp_path / "records" / "result.json"
    argv_file = tmp_path / "argv.txt"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", TMPDIR=str(tmp_path), FAKE_OUTPUT=output, FAKE_FINAL=final,
               FAKE_ERR=err, FAKE_EXIT=code, FAKE_SLEEP=sleep, ARGV_FILE=str(argv_file))
    if env_extra:
        env.update(env_extra)
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
    _, record = invoke(tmp_path, tree, fakebin, output=output, final=output)
    serialized = json.dumps(record)
    assert "quoted-secret" not in serialized
    assert '"token": "[REDACTED]"' in record["final_message_tail"]
    assert "private-material" not in serialized


def test_record_redacts_authorization_and_quoted_values(tmp_path):
    tree, fakebin = setup(tmp_path)
    output = 'Authorization: Basic basic-secret\nAuthorization: Bearer bearer-secret\ntoken="several secret words"\n{"token":"escaped \\\"secret\\\" value"}'
    _, record = invoke(tmp_path, tree, fakebin, output=output, final=output)
    serialized = json.dumps(record)
    for secret in ("basic-secret", "bearer-secret", "several secret words", "escaped", "secret\\\" value"):
        assert secret not in serialized


def test_record_redacts_token_authorization_and_password_remainder(tmp_path):
    tree, fakebin = setup(tmp_path)
    _, record = invoke(tmp_path, tree, fakebin,
                       output="Authorization: token ghx_abc\npassword: hunter2 more words")
    serialized = json.dumps(record)
    assert "ghx_abc" not in serialized
    assert "hunter2" not in serialized and "more words" not in serialized


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


def test_all_markdown_marker_forms(tmp_path):
    tree, fakebin = setup(tmp_path)
    for final in ("**DISPATCH_OUTCOME:** ESCALATED", "**DISPATCH_OUTCOME**: ESCALATED",
                  "- DISPATCH_OUTCOME: **ESCALATED**"):
        _, record = invoke(tmp_path, tree, fakebin, final=final)
        assert record["outcome"] == "escalated", final


def test_hash_and_underscore_marker_forms(tmp_path):
    tree, fakebin = setup(tmp_path)
    for final in ("__DISPATCH_OUTCOME__: ESCALATED", "DISPATCH_OUTCOME: _ESCALATED_",
                  "## DISPATCH_OUTCOME: ESCALATED"):
        _, record = invoke(tmp_path, tree, fakebin, final=final)
        assert record["outcome"] == "escalated", final


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


def test_opencode_model_value_follows_model_flag(tmp_path):
    # Regression: argv was `run --model --format json MODEL`, so --model consumed "--format".
    tree, fakebin = setup(tmp_path)
    argv_file = tmp_path / "argv"
    opencode = fakebin / "opencode"
    opencode.write_text("#!/bin/sh\nif [ \"$1\" = run ] && [ \"$2\" = --help ]; then\n"
                        "printf '%s\\n' 'opencode run --model --format'\nexit 0\nfi\n"
                        f"printf '%s\\n' \"$@\" > '{argv_file}'\n"
                        "printf '%s\\n' '{\"type\":\"text\",\"part\":{\"text\":\"ok\"}}'\n")
    opencode.chmod(0o755)
    status = tmp_path / "opencode.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "opencode", "--model", "provider/model",
                             "--data-boundary-attested", "--worktree", str(tree), "--status-file", str(status), "prompt"],
                            env=env, text=True, capture_output=True)
    argv = argv_file.read_text().splitlines()
    assert result.returncode == 0
    assert argv[argv.index("--model") + 1] == "provider/model"
    assert argv[argv.index("--format") + 1] == "json"
    assert argv[-2:] == ["--", "prompt"]


def test_timeout_kills_worker_and_records_marker(tmp_path):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin, extra=("--timeout", "0.05"), sleep="2")
    assert result.returncode == 124
    assert record["outcome"] == "failed"
    assert record["exit_code"] == 124
    assert record["final_message_tail"] == ""


def test_timeout_drains_output_after_term_grace(tmp_path):
    tree, fakebin = setup(tmp_path)
    worker = fakebin / "codex"
    worker.write_text("#!/usr/bin/env python3\nimport os,signal,sys,time\n"
                      "if sys.argv[1:] == ['exec','--help']:\n print('exec --model -s --output-last-message'); raise SystemExit(0)\n"
                      "path=sys.argv[sys.argv.index('--output-last-message')+1]\n"
                      "def term(*_):\n print('printed during grace',flush=True); open(path,'w').write('final during grace'); raise SystemExit(0)\n"
                      "signal.signal(signal.SIGTERM,term)\ntime.sleep(20)\n")
    worker.chmod(0o755)
    result, record = invoke(tmp_path, tree, fakebin, extra=("--timeout", "0.1", "--kill-grace", "0.5"))
    assert result.returncode == 124
    assert "printed during grace" in result.stdout
    assert record["exit_code"] == 124
    assert record["final_message_tail"] == "final during grace"


@pytest.mark.parametrize(("option", "value"), [
    ("--timeout", "nan"), ("--timeout", "inf"), ("--timeout", "-1"),
    ("--kill-grace", "nan"), ("--kill-grace", "inf"), ("--kill-grace", "-1"),
    ("--kill-grace", "301"),
])
def test_rejects_invalid_time_values(tmp_path, option, value):
    tree, fakebin = setup(tmp_path)
    result, record = invoke(tmp_path, tree, fakebin, extra=(option, value))
    assert result.returncode == 2
    assert f"{option} must be" in result.stderr
    assert record is None


def test_timeout_kills_process_group_with_grandchild(tmp_path):
    tree, fakebin = setup(tmp_path)
    pidfile = tmp_path / "timed-out-worker.pid"
    worker = fakebin / "codex"
    worker.write_text(worker.read_text().replace('if [ -n "${FAKE_SLEEP:-}" ]; then sleep "$FAKE_SLEEP"; fi',
                                                 'echo $$ > "$CHILD_PID"; sleep 30'))
    worker.chmod(0o755)
    start = time.monotonic()
    result, record = invoke(tmp_path, tree, fakebin, extra=("--timeout", "1"), sleep="yes",
                            env_extra={"CHILD_PID": str(pidfile)})
    assert time.monotonic() - start < 4
    assert result.returncode == 124
    assert record["outcome"] == "failed" and record["exit_code"] == 124
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_exited_worker_with_pipe_holding_grandchild_is_done_and_killed(tmp_path):
    tree, fakebin = setup(tmp_path)
    pidfile = tmp_path / "grandchild.pid"
    worker = fakebin / "codex"
    worker.write_text(worker.read_text().replace('printf \'%s\\n\' "$FAKE_OUTPUT"',
        'sleep 30 & echo $! > "$PIDFILE"; printf \'%s\\n\' "$FAKE_OUTPUT"'))
    worker.chmod(0o755)
    status = tmp_path / "records" / "result.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", TMPDIR=str(tmp_path),
               FAKE_OUTPUT="final worker output", FAKE_FINAL="final message", FAKE_ERR="", FAKE_EXIT="0",
               ARGV_FILE=str(tmp_path / "argv"), PIDFILE=str(pidfile))
    started = time.monotonic()
    result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "m",
                             "--worktree", str(tree), "--status-file", str(status), "--timeout", "4", "prompt"],
                            text=True, capture_output=True, env=env, timeout=5)
    record = json.loads(status.read_text())
    assert time.monotonic() - started < 2
    assert result.returncode == 0 and record["outcome"] == "done"
    assert record["final_message_tail"] == "final message"
    assert "final worker output" in result.stdout
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_final_message_excludes_prompt_and_transcript(tmp_path):
    tree, fakebin = setup(tmp_path)
    _, record = invoke(tmp_path, tree, fakebin, prompt="sensitive echoed prompt", output="sensitive echoed prompt", final="answer")
    assert record["final_message_tail"] == "answer"
    assert "sensitive echoed prompt" not in json.dumps(record)


def test_non_utf8_worker_output_is_replaced(tmp_path):
    tree, fakebin = setup(tmp_path)
    worker = fakebin / "codex"
    worker.write_text(worker.read_text().replace("printf '%s\\n' \"$FAKE_OUTPUT\"", "printf '\\377\\n'"))
    worker.chmod(0o755)
    result, record = invoke(tmp_path, tree, fakebin)
    assert result.returncode == 0
    assert record["outcome"] == "done"


@pytest.mark.parametrize("worker", ["codex", "opencode"])
def test_large_worker_output_does_not_block_and_keeps_final_message(tmp_path, worker):
    tree, fakebin = setup(tmp_path)
    script = fakebin / worker
    if worker == "codex":
        source = script.read_text()
        source = source.replace('printf \'%s\\n\' "$FAKE_OUTPUT"',
                                "python3 -c 'import sys; print(\"x\" * 1200000); print(\"answer\")'")
        source = source.replace('printf \'%s\\n\' "$FAKE_ERR" >&2',
                                "python3 -c 'import sys; print(\"y\" * 1200000, file=sys.stderr)'")
        script.write_text(source)
        script.chmod(0o755)
        result, record = invoke(tmp_path, tree, fakebin, extra=("--timeout", "5"), final="final answer")
    else:
        script.write_text("#!/usr/bin/env python3\nimport sys\n"
                          "if sys.argv[1:] == ['run', '--help']:\n print('opencode run --model --format'); raise SystemExit(0)\n"
                          "print('z' * 1200000)\n"
                          "print('{\"type\":\"text\",\"part\":{\"text\":\"final answer\"}}')\n"
                          "print('e' * 1200000, file=sys.stderr)\n")
        script.chmod(0o755)
        status = tmp_path / "opencode-large.json"
        env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", TMPDIR=str(tmp_path))
        started = time.monotonic()
        result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "opencode", "--model", "provider/model",
                                 "--data-boundary-attested", "--worktree", str(tree), "--status-file", str(status),
                                 "--timeout", "5", "prompt"], env=env, text=True, capture_output=True, timeout=8)
        assert time.monotonic() - started < 5
        record = json.loads(status.read_text())
    assert result.returncode == 0
    assert record["outcome"] == "done"
    assert record["final_message_tail"] == "final answer"
    assert not list(tmp_path.glob("agentops-dispatch-*"))


def test_large_worker_output_timeout_records_124_and_cleans_temp_files(tmp_path):
    tree, fakebin = setup(tmp_path)
    worker = fakebin / "codex"
    source = worker.read_text().replace('printf \'%s\\n\' "$FAKE_OUTPUT"',
                                         "python3 -c 'print(\"x\" * 1200000)'\nsleep 2")
    worker.write_text(source)
    worker.chmod(0o755)
    result, record = invoke(tmp_path, tree, fakebin, extra=("--timeout", "0.2"), final="answer")
    assert result.returncode == 124
    assert record["outcome"] == "failed" and record["exit_code"] == 124
    assert not list(tmp_path.glob("agentops-dispatch-*"))


def test_opencode_ignores_non_dict_json_lines(tmp_path):
    tree, fakebin = setup(tmp_path)
    opencode = fakebin / "opencode"
    opencode.write_text("#!/bin/sh\nif [ \"$1\" = run ] && [ \"$2\" = --help ]; then printf '%s\\n' 'opencode run --model --format'; exit 0; fi\nprintf '%s\\n' '[]' '{\"type\":\"text\",\"part\":{\"text\":\"reply\"}}'\n")
    opencode.chmod(0o755)
    status = tmp_path / "opencode.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    result = subprocess.run([sys.executable, str(SCRIPT), "--worker", "opencode", "--model", "provider/model",
                             "--data-boundary-attested", "--worktree", str(tree), "--status-file", str(status), "prompt"],
                            text=True, capture_output=True, env=env)
    assert result.returncode == 0
    assert json.loads(status.read_text())["final_message_tail"] == "reply"


def test_late_signal_does_not_overwrite_finalized_record(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "late.json"
    code = textwrap.dedent(f"""
        import importlib.util, os, signal
        from pathlib import Path
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        previous = lambda signum, frame: None
        signal.signal(signal.SIGTERM, previous)
        original = m.write_record
        count = [0]
        def write(path, record):
            count[0] += 1
            original(path, record)
            if count[0] == 2:
                os.kill(os.getpid(), signal.SIGTERM)
        m.write_record = write
        m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                '--status-file', {str(status)!r}, 'prompt'])
        assert signal.getsignal(signal.SIGTERM) is previous
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_FINAL="answer", FAKE_OUTPUT="", FAKE_ERR="", FAKE_EXIT="0", ARGV_FILE=str(tmp_path / "argv"))
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True)
    assert result.returncode == 0
    record = json.loads(status.read_text())
    assert record["outcome"] == "done"
    assert record["final_message_tail"] == "answer"


def test_terminal_record_is_single_atomic_replace_and_process_exit_matches(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "atomic.json"
    code = textwrap.dedent(f"""
        import importlib.util, os, signal
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        calls = []
        original = m.write_record
        def write(path, record):
            calls.append(record['outcome'])
            original(path, record)
            if record['outcome'] == 'done':
                os.kill(os.getpid(), signal.SIGTERM)
        m.write_record = write
        result = m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                         '--status-file', {str(status)!r}, 'prompt'])
        assert calls == ['running', 'done'], calls
        assert result == 0
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_FINAL="answer", FAKE_OUTPUT="", FAKE_ERR="", FAKE_EXIT="0",
               ARGV_FILE=str(tmp_path / "argv"))
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    record = json.loads(status.read_text())
    assert record["outcome"] == "done" and record["exit_code"] == result.returncode


def test_script_mode_ignores_signal_after_terminal_commit_until_exit(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "post-commit.json"
    code = textwrap.dedent(f"""
        import importlib.util, os, signal, sys, tempfile
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        real = tempfile.TemporaryDirectory
        class CleanupSignal:
            def __init__(self, *args, **kwargs): self.inner = real(*args, **kwargs)
            @property
            def name(self): return self.inner.name
            def cleanup(self):
                os.kill(os.getpid(), signal.SIGINT)
                self.inner.cleanup()
        m.tempfile.TemporaryDirectory = CleanupSignal
        sys.argv = [{str(SCRIPT)!r}, '--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                    '--status-file', {str(status)!r}, 'prompt']
        raise SystemExit(m.main())
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_FINAL="answer", FAKE_OUTPUT="", FAKE_ERR="",
               FAKE_EXIT="0", ARGV_FILE=str(tmp_path / "argv"))
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True)
    record = json.loads(status.read_text())
    assert result.returncode == 0, result.stderr
    assert record["outcome"] == "done" and record["exit_code"] == 0


@pytest.mark.parametrize("when", ["before_spawn", "after_spawn"])
def test_signal_at_popen_boundary_terminates_worker_and_matches_record(tmp_path, when):
    tree, fakebin = setup(tmp_path)
    worker = fakebin / "codex"
    worker.write_text(worker.read_text().replace('printf \'%s\\n\' "$*" > "$ARGV_FILE"',
                                                  'echo $$ > "$WORKER_PID"; printf \'%s\\n\' "$*" > "$ARGV_FILE"'))
    worker.chmod(0o755)
    status, pidfile = tmp_path / "spawn-race.json", tmp_path / "worker.pid"
    code = textwrap.dedent(f"""
        import importlib.util, os, signal
        from pathlib import Path
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        real = m.subprocess.Popen
        fired = [False]
        def spawn(*args, **kwargs):
            if args and args[0] and args[0][0].endswith('/codex') and '--output-last-message' in args[0] and not fired[0]:
                fired[0] = True
                if {when!r} == 'before_spawn': os.kill(os.getpid(), signal.SIGTERM)
                child = real(*args, **kwargs)
                Path({str(pidfile)!r}).write_text(str(child.pid))
                if {when!r} == 'after_spawn':
                    os.kill(os.getpid(), signal.SIGTERM)
                    os.kill(os.getpid(), signal.SIGINT)
                return child
            return real(*args, **kwargs)
        m.subprocess.Popen = spawn
        raise SystemExit(m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                                '--status-file', {str(status)!r}, 'prompt']))
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_SLEEP="20", FAKE_FINAL="", FAKE_OUTPUT="", FAKE_ERR="",
               FAKE_EXIT="0", ARGV_FILE=str(tmp_path / "argv"), WORKER_PID=str(pidfile))
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True, timeout=4)
    record = json.loads(status.read_text())
    assert result.returncode == 143
    assert record["outcome"] == "failed" and record["exit_code"] == result.returncode
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_worker_launch_closes_inherited_descriptors(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "fds.json"
    code = textwrap.dedent(f"""
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        real = m.subprocess.Popen
        captured = []
        def inspect(command, *args, **kwargs):
            if command and command[0].endswith('/codex') and '--output-last-message' in command:
                captured.append(kwargs.get('close_fds'))
            return real(command, *args, **kwargs)
        with patch.object(m.subprocess, 'Popen', side_effect=inspect):
            result = m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                             '--status-file', {str(status)!r}, 'prompt'])
        assert result == 0 and captured == [True], captured
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_FINAL="ok", FAKE_OUTPUT="", FAKE_ERR="", FAKE_EXIT="0",
               ARGV_FILE=str(tmp_path / "argv"))
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_signals_finalize_running_record_as_failed(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "term.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", TMPDIR=str(tmp_path), FAKE_SLEEP="10",
               FAKE_OUTPUT="", FAKE_FINAL="", FAKE_ERR="", FAKE_EXIT="0", ARGV_FILE=str(tmp_path / "argv"))
    for sig, expected in ((signal.SIGINT, 130), (signal.SIGHUP, 129), (signal.SIGTERM, 143)):
        status.unlink(missing_ok=True)
        proc = subprocess.Popen([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "gpt-6-luna",
                                 "--worktree", str(tree), "--status-file", str(status), "prompt"],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if status.exists() and json.loads(status.read_text())["outcome"] == "running":
                break
            time.sleep(0.01)
        os.kill(proc.pid, sig)
        assert proc.wait(timeout=5) == expected
        record = json.loads(status.read_text())
        assert record["outcome"] == "failed"
        assert record["exit_code"] == expected
        assert "killed" in record["final_message_tail"]


def test_popen_value_error_finalizes_instead_of_leaving_running(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "nul.json"
    code = textwrap.dedent(f"""
        import importlib.util
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        real_popen = m.subprocess.Popen
        def fail_worker(command, *args, **kwargs):
            if command[0] == 'git':
                return real_popen(command, *args, **kwargs)
            raise ValueError('embedded null byte')
        with patch.object(m, 'validate_cli', return_value=(["codex"], None)), \\
             patch.object(m.subprocess, 'Popen', side_effect=fail_worker):
            raise SystemExit(m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                                     '--status-file', {str(status)!r}, 'prompt\\0bad']))
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True)
    record = json.loads(status.read_text())
    assert result.returncode == 1
    assert record["outcome"] == "failed"
    assert "ValueError" in record["final_message_tail"]


def test_write_record_fsyncs_file_and_parent(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("dispatch_run", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real_fsync(fd))[1])
    path = tmp_path / "nested" / "record.json"
    module.write_record(path, {"outcome": "done"})
    assert json.loads(path.read_text())["outcome"] == "done"
    assert len(calls) == 2


def test_terminal_record_failure_uses_fallback_and_exits_nonzero(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "terminal.json"
    code = textwrap.dedent(f"""
        import importlib.util
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        real = m.write_record
        def failing(path, record):
            if str(path) == {str(status)!r} and record['outcome'] != 'running': raise OSError('disk full')
            return real(path, record)
        m.write_record = failing
        raise SystemExit(m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                                '--status-file', {str(status)!r}, 'prompt']))
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_FINAL="answer", FAKE_OUTPUT="", FAKE_ERR="",
               FAKE_EXIT="0", ARGV_FILE=str(tmp_path / "argv"))
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True)
    assert result.returncode == 1
    assert "terminal record write failed" in result.stderr
    fallback = json.loads(Path(str(status) + ".fallback.json").read_text())
    assert fallback["outcome"] == "failed" and fallback["exit_code"] == 1


def test_terminal_write_failure_during_signal_keeps_signal_code_and_fallback(tmp_path):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / "signal-write-failure.json"
    code = textwrap.dedent(f"""
        import importlib.util, os, signal, threading
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        real = m.write_record
        def failing(path, record):
            if str(path) == {str(status)!r} and record['outcome'] != 'running': raise OSError('disk full')
            return real(path, record)
        m.write_record = failing
        threading.Timer(.2, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
        raise SystemExit(m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                                '--status-file', {str(status)!r}, 'prompt']))
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_SLEEP="20", FAKE_FINAL="", FAKE_OUTPUT="",
               FAKE_ERR="", ARGV_FILE=str(tmp_path / "argv"))
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True, timeout=4)
    assert result.returncode == 143
    assert result.stderr.count("terminal record write failed") == 1
    assert "Traceback" not in result.stderr
    fallback = json.loads(Path(str(status) + ".fallback.json").read_text())
    assert fallback["outcome"] == "failed" and fallback["exit_code"] == 143


@pytest.mark.parametrize(("error", "expected"), [("OSError", 127), ("RuntimeError", 1)])
def test_terminal_write_failure_in_error_handler_is_reported_once(tmp_path, error, expected):
    tree, fakebin = setup(tmp_path)
    status = tmp_path / f"{error}.json"
    code = textwrap.dedent(f"""
        import importlib.util
        spec = importlib.util.spec_from_file_location('dispatch_run', {str(SCRIPT)!r})
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        real_write = m.write_record
        def failing_write(path, record):
            if str(path) == {str(status)!r} and record['outcome'] != 'running': raise OSError('disk full')
            return real_write(path, record)
        real_popen = m.subprocess.Popen
        def fail_worker(command, *args, **kwargs):
            if command and '--output-last-message' in command: raise {error}('worker launch failed')
            return real_popen(command, *args, **kwargs)
        m.write_record = failing_write
        m.subprocess.Popen = fail_worker
        raise SystemExit(m.main(['--worker', 'codex', '--model', 'm', '--worktree', {str(tree)!r},
                                '--status-file', {str(status)!r}, 'prompt']))
    """)
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    result = subprocess.run([sys.executable, "-c", code], env=env, text=True, capture_output=True)
    assert result.returncode == expected
    assert result.stderr.count("terminal record write failed") == 1
    assert "Traceback" not in result.stderr and "unexpected error" not in result.stderr
    fallback = json.loads(Path(str(status) + ".fallback.json").read_text())
    assert fallback["outcome"] == "failed" and fallback["exit_code"] == expected


def test_second_signal_skips_kill_grace(tmp_path):
    tree, fakebin = setup(tmp_path)
    worker = fakebin / "codex"
    ready = tmp_path / "ignoring-term-ready"
    worker.write_text(worker.read_text().replace('if [ -n "${FAKE_SLEEP:-}" ]; then sleep "$FAKE_SLEEP"; fi',
                                                 f'trap \'\' TERM\ntouch "{ready}"\nsleep 20'))
    worker.chmod(0o755)
    status = tmp_path / "twice.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}", FAKE_SLEEP="20", FAKE_FINAL="", FAKE_OUTPUT="",
               FAKE_ERR="", FAKE_EXIT="0", ARGV_FILE=str(tmp_path / "argv"))
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "m",
                             "--kill-grace", "2", "--worktree", str(tree), "--status-file", str(status), "prompt"],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and not ready.exists():
        time.sleep(.01)
    assert ready.exists(), "worker did not install its TERM ignore trap"
    os.kill(proc.pid, signal.SIGTERM)
    time.sleep(.1)
    os.kill(proc.pid, signal.SIGINT)
    assert proc.wait(timeout=1) == 143
    record = json.loads(status.read_text())
    assert record["exit_code"] == 143


def test_signal_waits_for_term_exiting_grandchild_before_kill(tmp_path):
    tree, fakebin = setup(tmp_path)
    worker = fakebin / "codex"
    marker = tmp_path / "term-seen"
    ready = tmp_path / "child-ready"
    worker.write_text("#!/usr/bin/env python3\nimport os,signal,subprocess,sys,time\n"
                      "if sys.argv[1:] == ['exec','--help']:\n print('exec --model -s --output-last-message'); raise SystemExit(0)\n"
                      f"child=subprocess.Popen([sys.executable,'-c',\"import signal,time; signal.signal(signal.SIGTERM, lambda *_: open({str(marker)!r},'w').write('term')); open({str(ready)!r},'w').write('ready'); time.sleep(20)\"])\n"
                      "time.sleep(20)\n")
    worker.chmod(0o755)
    status = tmp_path / "term-child.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "m", "--kill-grace", "2",
                             "--worktree", str(tree), "--status-file", str(status), "prompt"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and (not status.exists() or json.loads(status.read_text())["outcome"] != "running" or not ready.exists()):
        time.sleep(.01)
    os.kill(proc.pid, signal.SIGTERM)
    assert proc.wait(timeout=4) == 143
    assert marker.exists()


def test_signal_kills_term_ignoring_grandchild_after_grace(tmp_path):
    tree, fakebin = setup(tmp_path)
    worker = fakebin / "codex"
    pidfile = tmp_path / "ignoring.pid"
    worker.write_text("#!/usr/bin/env python3\nimport os,signal,subprocess,sys,time\n"
                      "if sys.argv[1:] == ['exec','--help']:\n print('exec --model -s --output-last-message'); raise SystemExit(0)\n"
                      f"child=subprocess.Popen([sys.executable,'-c',\"import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); open({str(pidfile)!r},'w').write(str(os.getpid())); time.sleep(20)\"])\n"
                      "time.sleep(20)\n")
    worker.chmod(0o755)
    status = tmp_path / "ignore-child.json"
    env = dict(os.environ, PATH=f"{fakebin}:{os.environ['PATH']}")
    proc = subprocess.Popen([sys.executable, str(SCRIPT), "--worker", "codex", "--model", "m", "--kill-grace", ".25",
                             "--worktree", str(tree), "--status-file", str(status), "prompt"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and (not status.exists() or json.loads(status.read_text())["outcome"] != "running" or not pidfile.exists()):
        time.sleep(.01)
    start = time.monotonic()
    os.kill(proc.pid, signal.SIGTERM)
    assert proc.wait(timeout=3) == 143
    assert time.monotonic() - start >= .20
    pid = int(pidfile.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
