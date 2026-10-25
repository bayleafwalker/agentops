"""V2.1 detached-child supervision mechanics.

This module owns process-group launch, timeout and cleanup. It deliberately
does not interpret logs, provider quotas, acceptance results, or project task
receipts.
"""

from __future__ import annotations

import os
import hashlib
import re
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
import json
import signal
import subprocess
import time
from typing import Any, TextIO

from .runtime import atomic, identity


MAX_STDIN_BYTES = 2 * 1024 * 1024


@contextmanager
def _child_stdin(spec: dict[str, Any], root: Path):
    """Snapshot bounded, digest-bound input before starting any child process."""
    if "stdin_artifact" not in spec:
        yield subprocess.DEVNULL
        return
    artifact = spec["stdin_artifact"]
    if not isinstance(artifact, dict) or set(artifact) != {"file", "sha256", "size_bytes"}:
        raise ValueError("stdin_artifact requires file, sha256 and size_bytes")
    name, expected, size = artifact["file"], artifact["sha256"], artifact["size_bytes"]
    if (not isinstance(name, str) or not name or name in {".", ".."}
            or Path(name).name != name or "/" in name or "\\" in name):
        raise ValueError("stdin artifact must name a direct attempt file")
    if not isinstance(expected, str) or re.fullmatch(r"[a-f0-9]{64}", expected) is None:
        raise ValueError("stdin artifact requires a SHA-256 digest")
    if type(size) is not int or not 0 <= size <= MAX_STDIN_BYTES:
        raise ValueError("stdin artifact size exceeds the bounded input contract")
    fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != size:
            raise ValueError("stdin artifact must be a regular file of the bound size")
        data = source.read(MAX_STDIN_BYTES + 1)
    if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("stdin artifact content binding mismatch")
    # Feed the verified snapshot, not a mutable source file or a large argv value.
    with tempfile.TemporaryFile() as snapshot:
        snapshot.write(data)
        snapshot.seek(0)
        yield snapshot


def run_child(command: list[str], output: TextIO, *, spec: dict[str, Any],
              attempt_dir: str | Path, env: dict[str, str], started_at: float) -> int:
    """Run one child in its own process group using the V2.1 supervision loop."""
    root = Path(attempt_dir)
    with _child_stdin(spec, root) as input_stream:
        child = subprocess.Popen(command, cwd=spec["cwd"], env=env,
                                 stdin=input_stream, stdout=output,
                                 stderr=subprocess.STDOUT, start_new_session=True)
    atomic(root / "child.json", {
        "pid": child.pid,
        "start": identity(child.pid),
        "pgid": child.pid,
    })
    while child.poll() is None:
        if time.time() - started_at > spec["timeout"]:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            # A terminated parent may leave grandchildren; end the owned group.
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return 124
        time.sleep(0.05)
    # A CLI exit cannot leave background writers alive after its receipt.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return child.returncode


def kill_recorded_group(receipt: dict[str, Any] | None) -> bool:
    """Kill the process group only while the recorded PID/start pair is live."""
    if not receipt or not receipt.get("start"):
        return False
    try:
        pid = int(receipt["pid"])
        pgid = int(receipt["pgid"])
    except (KeyError, TypeError, ValueError):
        return False
    if identity(pid) != str(receipt["start"]):
        return False
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return False
    return True


def stop_attempt(attempt_dir: str | Path, *, marker_key: str = "AGENTOPS_ATTEMPT_DIR") -> None:
    """Stop the exact V2.1 wrapper/child groups, including surviving descendants."""
    root = Path(attempt_dir)
    for name in ("child.json", "process.json"):
        info_path = root / name
        if not info_path.exists():
            continue
        info = json.loads(info_path.read_text())
        owned_group = bool(info and info.get("start")
                           and identity(int(info["pid"])) == info["start"])
        if info and not owned_group:
            marker = (marker_key + "=" + str(root)).encode()
            for process in Path("/proc").glob("[0-9]*"):
                try:
                    if marker in (process / "environ").read_bytes().split(b"\0") \
                            and os.getpgid(int(process.name)) == info["pgid"]:
                        owned_group = True
                        break
                except (OSError, ProcessLookupError):
                    continue
        if owned_group:
            try:
                os.killpg(info["pgid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
