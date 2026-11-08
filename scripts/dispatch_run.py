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
import time


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
    command = [executable, "exec", "-s", "workspace-write", "--model"] if worker == "codex" else [executable, "run", "--format", "json", "--model"]
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


def read_tail(path: Path, limit: int = 8 * 1024 * 1024) -> str:
    """Read only the end of a worker output file, where its final message lives."""
    with path.open("rb") as stream:
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        data = stream.read(limit)
    return data.decode("utf-8", errors="replace")


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
    # Keep termination signals deferred from the initial running record through
    # spawn and completion. This closes the windows where a signal used to
    # leave a running record behind or arrive before Popen registered its PID.
    blocked = {signal.SIGTERM, signal.SIGINT, signal.SIGHUP}
    old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
    pending_signal = None
    finalized = False
    def on_term(signum, frame):
        nonlocal pending_signal
        if pending_signal is None:
            pending_signal = signum

    previous_handlers = {sig: signal.signal(sig, on_term) for sig in blocked}
    signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
    temp_dir = None
    temp_path = None
    stdout_path = None
    stderr_path = None
    proc = None

    def finish(outcome: str, code: int, final: str = "", reason: str | None = None) -> bool:
        nonlocal finalized
        if finalized:
            return False
        record.update(outcome=outcome, exit_code=code, final_message_tail=safe_tail(final),
                      escalation_reason=safe_tail(reason, 1000) if outcome == "escalated" and reason else None,
                      ended_at=now())
        old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, blocked)
        try:
            write_record(status_path, record)
            finalized = True
        finally:
            # Discard signals queued during the atomic terminal commit. Its
            # outcome is already authoritative and must agree with our exit.
            for sig in blocked:
                try:
                    signal.sigtimedwait({sig}, 0)
                except (AttributeError, OSError):
                    pass
            signal.pthread_sigmask(signal.SIG_SETMASK, old_mask)
        return True

    def kill_group(sig=signal.SIGKILL) -> None:
        if proc:
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                pass
            except PermissionError:
                pass

    def bounded_drain() -> tuple[str, str]:
        if not stdout_path or not stderr_path:
            return "", ""
        return read_tail(stdout_path), read_tail(stderr_path)

    def terminate_group() -> None:
        kill_group(signal.SIGTERM)
        if proc:
            try:
                proc.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                pass
        # The group may contain descendants after the leader has exited.
        kill_group(signal.SIGKILL)
        if proc:
            proc.wait()

    try:
        write_record(status_path, record)
        if pending_signal is not None:
            raise InterruptedError
        temp_dir = tempfile.TemporaryDirectory(prefix="agentops-dispatch-")
        private_dir = Path(temp_dir.name)
        stdout_path, stderr_path = private_dir / "stdout", private_dir / "stderr"
        stdout_path.touch(mode=0o600)
        stderr_path.touch(mode=0o600)
        if args.worker == "codex":
            temp_path = str(private_dir / "final-message")
            fd = os.open(temp_path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
            command += [args.model, "--output-last-message", temp_path, "--", args.prompt]
        else:
            command += [args.model, "--", args.prompt]
        with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
            if pending_signal is not None:
                raise InterruptedError
            proc = subprocess.Popen(command, cwd=worktree, stdin=subprocess.DEVNULL,
                                    stdout=stdout_file, stderr=stderr_file, start_new_session=True,
                                    close_fds=True)
        if pending_signal is not None:
            raise InterruptedError
        try:
            deadline = time.monotonic() + args.timeout
            while proc.poll() is None and pending_signal is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, args.timeout)
                try:
                    proc.wait(timeout=min(0.05, remaining))
                except subprocess.TimeoutExpired:
                    continue
            if pending_signal is not None:
                raise InterruptedError
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
            final = read_tail(Path(temp_path))
        elif args.worker == "opencode":
            final = opencode_final(stdout or "")
        else:
            final = ""
        marker, reason = escalation(final)
        if pending_signal is not None:
            raise InterruptedError
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
    except InterruptedError:
        sig = pending_signal or signal.SIGTERM
        terminate_group()
        partial_out, partial_err = bounded_drain()
        partial = "\n".join(part for part in (partial_out, partial_err) if part)
        finish("failed", 128 + sig, "worker killed by signal" + ("\n" + partial if partial else ""))
        return 128 + sig
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
        if temp_dir:
            temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
