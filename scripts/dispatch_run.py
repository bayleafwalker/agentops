#!/usr/bin/env python3
"""Run a native worker in a worktree and persist a coordinator-readable result.

The caller should launch this foreground command as a harness background task.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_tail(text: str, limit: int = 4000) -> str:
    text = text[-limit:]
    # Keep useful completion context while removing common credential forms.
    patterns = (
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"(?i)((?:api[_-]?key|access[_-]?key|secret|password|token|authorization)\s*[:=]\s*)[^\s,;]+",
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|vuo_[A-Za-z0-9_-]{20,})\b",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\b(?:sk|sk-ant|sk-proj)-[A-Za-z0-9_-]{20,}\b",
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    )
    for pattern in patterns:
        text = re.sub(pattern, lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", text)
    return text


def git(cwd: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worktree", required=True, type=Path)
    p.add_argument("--model", required=True, help="explicit provider model ID")
    p.add_argument("--status-file", required=True, type=Path)
    p.add_argument("--worker", required=True, choices=("codex", "opencode"))
    p.add_argument("--data-boundary-attested", action="store_true",
                   help="attest OpenCode input meets model-routing.md external-provider boundary")
    p.add_argument("prompt", help="bounded worker outcome and acceptance criteria")
    return p


def validate_cli(worker: str, executable: str) -> tuple[list[str], str | None]:
    base = [executable, "exec", "--help"] if worker == "codex" else [executable, "run", "--help"]
    try:
        result = subprocess.run(base, text=True, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], f"cannot validate {worker} CLI flags: {exc}"
    help_text = result.stdout + result.stderr
    if result.returncode != 0:
        return [], f"cannot validate {worker} CLI flags (help exited {result.returncode})"
    if worker == "codex":
        required = ("--model", "-s", "workspace-write")
        command = [executable, "exec", "-s", "workspace-write", "--model"]
    else:
        required = ("--model",)
        command = [executable, "run", "--model"]
    missing = [flag for flag in required if flag not in help_text]
    if missing:
        return [], f"{worker} CLI does not advertise required flags: {', '.join(missing)}"
    return command, None


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["run"]:
        argv = argv[1:]
    args = parser().parse_args(argv)
    worktree = args.worktree.resolve()
    status_path = args.status_file.resolve()
    start = now()
    if args.worker == "opencode" and not args.data_boundary_attested:
        parser().error("OpenCode requires --data-boundary-attested after checking the external-provider data boundary")
    if not worktree.is_dir() or not git(worktree, "rev-parse", "--show-toplevel"):
        parser().error(f"--worktree is not a readable git worktree: {worktree}")

    executable = shutil.which(args.worker)
    command, problem = validate_cli(args.worker, executable) if executable else ([], f"{args.worker} CLI not found on PATH")
    if problem:
        print(f"agentops dispatch run: {problem}", file=sys.stderr)
        return 2
    command += [args.model]
    if args.worker == "opencode":
        command += [args.prompt]
    else:
        command += [args.prompt]

    output = ""
    exit_code = 127
    try:
        result = subprocess.run(command, cwd=worktree, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        output, exit_code = result.stdout or "", result.returncode
    except OSError as exc:
        output = str(exc)

    tail = safe_tail(output)
    match = re.search(r"(?im)^\s*DISPATCH_OUTCOME:\s*ESCALATED\s*$", output)
    reason_match = re.search(r"(?im)^\s*ESCALATION_REASON:\s*(.+)$", output)
    escalated = bool(match)
    outcome = "escalated" if escalated else ("done" if exit_code == 0 else "failed")
    record = {
        "schema": "agentops-dispatch-run/v1", "outcome": outcome,
        "exit_code": exit_code, "branch": git(worktree, "branch", "--show-current"),
        "head_sha": git(worktree, "rev-parse", "HEAD"),
        "dirty": bool(git(worktree, "status", "--porcelain")),
        "final_message_tail": tail,
        "escalation_reason": safe_tail(reason_match.group(1), 1000) if reason_match else None,
        "started_at": start, "ended_at": now(), "model": args.model,
        "worker": args.worker,
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{status_path.name}.", dir=status_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(tmp_name, status_path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    print(tail, end="" if tail.endswith("\n") or not tail else "\n")
    print(f"agentops dispatch run: {outcome}; status: {status_path}", file=sys.stderr)
    return 0 if outcome in ("done", "escalated") else exit_code or 1


if __name__ == "__main__":
    raise SystemExit(main())
