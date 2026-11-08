#!/usr/bin/env python3
"""Run a native worker in a worktree and persist a coordinator-readable result."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_tail(text: str, limit: int = 4000) -> str:
    patterns = (
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"(?i)((?:api[_-]?key|access[_-]?key|secret|password|token|authorization)\s*[:=]\s*)[\"']?[^\s,;\"']+",
        r"(?i)([\"'](?:api[_-]?key|access[_-]?key|secret|password|token|authorization)[\"']\s*:\s*[\"'])[^\"']+",
        r"(?ims)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|vuo_[A-Za-z0-9_-]{20,})\b",
        r"\bAKIA[0-9A-Z]{16}\b", r"\b(?:sk|sk-ant|sk-proj)-[A-Za-z0-9_-]{20,}\b",
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    )
    for pattern in patterns:
        text = re.sub(pattern, lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", text)
    return text[-limit:]


def git(cwd: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worktree", required=True, type=Path)
    p.add_argument("--model", required=True, help="explicit provider model ID (caller validates against model-routing.json)")
    p.add_argument("--status-file", required=True, type=Path)
    p.add_argument("--worker", required=True, choices=("codex", "opencode"))
    p.add_argument("--timeout", type=float, default=3600, help="worker timeout in seconds (default: 3600)")
    p.add_argument("--data-boundary-attested", action="store_true", help="attest OpenCode input meets external-provider boundary")
    p.add_argument("prompt", help="bounded worker outcome and acceptance criteria")
    return p


def validate_cli(worker: str, executable: str) -> tuple[list[str], str | None]:
    try:
        result = subprocess.run([executable, "exec" if worker == "codex" else "run", "--help"], text=True, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"cannot validate {worker} CLI flags: {exc}"
    help_text = result.stdout + result.stderr
    if result.returncode != 0:
        return [], f"cannot validate {worker} CLI flags (help exited {result.returncode})"
    tokens = set(re.findall(r"(?<![\w-])--?[A-Za-z][\w-]*", help_text))
    required = {"--model"}
    command = [executable, "exec", "-s", "workspace-write", "--model"] if worker == "codex" else [executable, "run", "--model", "--format", "json"]
    if worker == "codex":
        required |= {"-s", "--output-last-message"}
    else:
        required.add("--format")
    missing = sorted(required - tokens)
    if missing:
        return [], f"{worker} CLI does not advertise required flags: {', '.join(missing)}"
    return command, None


def write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def opencode_final(stdout: str) -> str:
    final = ""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if event.get("type") == "text":
            part = event.get("part") or {}
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                final += part["text"]
    return final


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        argv = argv[1:]
    args = parser().parse_args(argv)
    if args.timeout <= 0:
        parser().error("--timeout must be positive")
    worktree, status_path = args.worktree.resolve(), args.status_file.resolve()
    if args.worker == "opencode" and not args.data_boundary_attested:
        parser().error("OpenCode requires --data-boundary-attested after checking the external-provider data boundary")
    if not worktree.is_dir() or not git(worktree, "rev-parse", "--show-toplevel"):
        parser().error(f"--worktree is not a readable git worktree: {worktree}")
    executable = shutil.which(args.worker)
    command, problem = validate_cli(args.worker, executable) if executable else ([], f"{args.worker} CLI not found on PATH")
    if problem:
        print(f"agentops dispatch run: {problem}", file=sys.stderr)
        return 2
    started = now()
    record = {"schema": "agentops-dispatch-run/v1", "outcome": "running", "exit_code": None,
              "branch": git(worktree, "branch", "--show-current"), "head_sha": git(worktree, "rev-parse", "HEAD"),
              "dirty": bool(git(worktree, "status", "--porcelain")), "final_message_tail": "",
              "escalation_reason": None, "started_at": started, "ended_at": None, "model": args.model, "worker": args.worker}
    write_record(status_path, record)
    temp_path = None
    proc = None

    def finish(outcome: str, code: int, output: str = "", final: str = "", reason: str | None = None) -> None:
        record.update(outcome=outcome, exit_code=code, final_message_tail=safe_tail(output),
                      escalation_reason=safe_tail(reason, 1000) if outcome == "escalated" and reason else None,
                      ended_at=now())
        write_record(status_path, record)

    def on_term(signum, frame):
        if proc and proc.poll() is None:
            proc.kill()
        finish("failed", 128 + signum, "worker killed by signal")
        raise SystemExit(128 + signum)

    previous_term = signal.signal(signal.SIGTERM, on_term)
    try:
        if args.worker == "codex":
            fd, temp_path = tempfile.mkstemp(prefix="agentops-dispatch-final-")
            os.close(fd)
            command += [args.model, "--output-last-message", temp_path, "--", args.prompt]
        else:
            command += [args.model, "--", args.prompt]
        proc = subprocess.Popen(command, cwd=worktree, text=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = proc.communicate(timeout=args.timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            code = 124
            stdout += "\nDISPATCH_TIMEOUT: worker exceeded --timeout\n"
        transcript = (stdout or "") + ("\n" + stderr if stderr else "")
        if code < 0:
            code = 128 + abs(code)
        if args.worker == "codex" and temp_path and os.path.exists(temp_path):
            final = Path(temp_path).read_text(encoding="utf-8", errors="replace")
        elif args.worker == "opencode":
            final = opencode_final(stdout or "")
        else:
            final = ""
        marker = re.search(r"(?im)^\s*[-*+`*_>\s]*DISPATCH_OUTCOME\s*:\s*ESCALATED\s*[*_`.,;:!?]*\s*$", final)
        reason_match = re.search(r"(?im)^\s*[-*+`*_>\s]*ESCALATION_REASON\s*:\s*(.+?)\s*[*_`.,;:!?]*\s*$", final)
        if marker:
            finish("escalated", code, transcript, final, reason_match.group(1).strip(" *_`.,;:!?") if reason_match else None)
            result_code = 0
        elif code == 0:
            finish("done", code, transcript)
            result_code = 0
        else:
            finish("failed", code, transcript)
            result_code = code
        print(safe_tail(transcript), end="\n" if transcript else "")
        print(f"agentops dispatch run: {record['outcome']}; status: {status_path}", file=sys.stderr)
        return result_code or (1 if record["outcome"] == "failed" else 0)
    except OSError as exc:
        finish("failed", 127, str(exc))
        return 127
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    raise SystemExit(main())
