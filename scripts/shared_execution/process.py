"""V2.1 detached-child supervision mechanics.

This module owns process-group launch, timeout and cleanup. It deliberately
does not interpret logs, provider quotas, acceptance results, or project task
receipts.
"""

from __future__ import annotations

import os
from pathlib import Path
import json
import signal
import subprocess
import time
from typing import Any, TextIO

from .runtime import atomic, identity


def run_child(command: list[str], output: TextIO, *, spec: dict[str, Any],
              attempt_dir: str | Path, env: dict[str, str], started_at: float) -> int:
    """Run one child in its own process group using the V2.1 supervision loop."""
    root = Path(attempt_dir)
    child = subprocess.Popen(command, cwd=spec["cwd"], env=env,
                             stdin=subprocess.DEVNULL, stdout=output,
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
