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
        r"(?i)((?:authorization\s*:\s*)\w+\s+)\S+",
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"(?im)((?:api[_-]?key|access[_-]?key|secret|password|token|authorization)\s*:\s*)(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\n]*)",
        r"(?i)((?:api[_-]?key|access[_-]?key|secret|password|token|authorization)\s*=\s*)(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;]+)",
        r"(?i)([\"'](?:api[_-]?key|access[_-]?key|secret|password|token|authorization)[\"']\s*:\s*[\"'])((?:\\.|[^\"\\])*)([\"'])",
        r"(?ims)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|vuo_[A-Za-z0-9_-]{20,})\b",
        r"\bAKIA[0-9A-Z]{16}\b", r"\b(?:sk|sk-ant|sk-proj)-[A-Za-z0-9_-]{20,}\b",
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
    )
    for pattern in patterns:
        text = re.sub(pattern, lambda m: ((m.group(1) if m.lastindex else "") + "[REDACTED]" + (m.group(3) if m.lastindex and m.lastindex >= 3 else "")), text)
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
    parts = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(event, dict) and event.get("type") == "text":
            part = event.get("part") or {}
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
    # OpenCode's JSON text events do not identify assistant-message boundaries;
    # treat their ordered text parts as one final response.
    return "\n".join(parts)


def escalation(final: str) -> tuple[bool, str | None]:
    cleaned = [re.sub(r"[*`]", "", line).strip().lstrip("#").strip() for line in final.splitlines()]
    cleaned = [re.sub(r"^_+|_+$", "", re.sub(r"^_*(DISPATCH_OUTCOME|ESCALATION_REASON)_*\s*:", r"\1:", line, flags=re.I)) for line in cleaned]
    cleaned = [re.sub(r":\s*_+([^_\s]+)_*", r": \1", line) for line in cleaned]
    marker = any(re.fullmatch(r"[-+> ]*DISPATCH_OUTCOME\s*:\s*ESCALATED[.,;:!? ]*", line, re.I) for line in cleaned)
    reason = next((m.group(1).strip(" .,;:!?") for line in cleaned
                   if (m := re.fullmatch(r"[-+> ]*ESCALATION_REASON\s*:\s*(.+?)\s*[.,;:!? ]*", line, re.I))), None)
    return marker, reason


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

    finalized = False
    def finish(outcome: str, code: int, final: str = "", reason: str | None = None) -> bool:
        nonlocal finalized
        if finalized:
            return False
        record.update(outcome=outcome, exit_code=code, final_message_tail=safe_tail(final),
                      escalation_reason=safe_tail(reason, 1000) if outcome == "escalated" and reason else None,
                      ended_at=now())
        blocked = {signal.SIGTERM, signal.SIGINT, signal.SIGHUP}
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        try:
            write_record(status_path, record)
            finalized = True
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
        return True

    def kill_group() -> None:
        if proc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass

    def bounded_drain() -> tuple[str, str]:
        if not proc:
            return "", ""
        try:
            return proc.communicate(timeout=0.25)
        except subprocess.TimeoutExpired as exc:
            stdout = exc.output or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            for pipe in (proc.stdout, proc.stderr):
                if pipe:
                    pipe.close()
            return stdout, stderr

    def on_term(signum, frame):
        kill_group()
        partial_out, partial_err = bounded_drain()
        partial = "\n".join(part for part in (partial_out, partial_err) if part)
        finish("failed", 128 + signum, "worker killed by signal" + ("\n" + partial if partial else ""))
        raise SystemExit(128 + signum)

    previous_handlers = {sig: signal.signal(sig, on_term) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        if args.worker == "codex":
            fd, temp_path = tempfile.mkstemp(prefix="agentops-dispatch-final-")
            os.close(fd)
            command += [args.model, "--output-last-message", temp_path, "--", args.prompt]
        else:
            command += [args.model, "--", args.prompt]
        proc = subprocess.Popen(command, cwd=worktree, text=True, errors="replace", stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            proc.wait(timeout=args.timeout)
            code = proc.returncode
            stdout, stderr = bounded_drain()
            kill_group()
        except subprocess.TimeoutExpired:
            stdout, stderr = bounded_drain()
            kill_group()
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
        marker, reason = escalation(final)
        if marker:
            finish("escalated", code, final, reason)
            result_code = 0
        elif code == 0:
            finish("done", code, final)
            result_code = 0
        else:
            finish("failed", code, final)
            result_code = code
        print(safe_tail(transcript), end="\n" if transcript else "")
        print(f"agentops dispatch run: {record['outcome']}; status: {status_path}", file=sys.stderr)
        return result_code or (1 if record["outcome"] == "failed" else 0)
    except OSError as exc:
        kill_group()
        partial_out, partial_err = bounded_drain()
        partial = "\n".join(part for part in (partial_out, partial_err) if part)
        finish("failed", 127, f"{type(exc).__name__}: {exc}" + ("\n" + partial if partial else ""))
        return 127
    except Exception as exc:
        kill_group()
        partial_out, partial_err = bounded_drain()
        partial = "\n".join(part for part in (partial_out, partial_err) if part)
        finish("failed", 1, f"{type(exc).__name__}: {exc}" + ("\n" + partial if partial else ""))
        print(f"agentops dispatch run: unexpected error: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


if __name__ == "__main__":
    raise SystemExit(main())
