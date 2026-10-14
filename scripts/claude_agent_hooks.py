#!/usr/bin/env python3
"""Claude Code observation hooks for the agent directory (roadmap M2b, baseline 2.2).

    session-start    register this workstation's Claude Code instance, once per host
    prompt-submit    report `observed` and `attended` (valid 900 s), at most once per 5 minutes

Both fail open: any error, a missing profile or the 3 s alarm ends in exit 0 and
no output, so a hook can never block a session. A submitted prompt is explicit
evidence that a human is present; nothing here ever asserts absence.

The instance id (`ins_<ULID>`) is minted once and kept under
`~/.config/vuoro/agent-instances/` (`AGENTOPS_AGENT_INSTANCES_DIR` overrides).
Config: `AGENTOPS_VUORO_PROFILE`, `AGENTOPS_AGENT_REPO_IDS` (comma list, default "agentops").
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import host_adapter as ha  # noqa: E402

VALID_FOR = 900
RATE_LIMIT_SECONDS = 300
DEADLINE_SECONDS = 3
DEFAULT_PROFILE = "/projects/dev/agentops/environment-record/profiles/workstation-vuoro-shared.json"


def instances_dir() -> Path:
    return Path(os.environ.get("AGENTOPS_AGENT_INSTANCES_DIR", str(Path.home() / ".config/vuoro/agent-instances")))


def _paths(base: Path) -> tuple[Path, Path]:
    host = socket.gethostname().split(".")[0] or "host"
    return base / f"claude-code.{host}.json", base / f"claude-code.{host}.stamp"


def repo_ids() -> list[str]:
    return [r for r in os.environ.get("AGENTOPS_AGENT_REPO_IDS", "agentops").split(",") if r.strip()]


def claude_version() -> str:
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=1.5).stdout
        return (out.split() or ["unknown"])[0][:64]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def load_or_mint(base: Path) -> tuple[dict, bool]:
    """The persisted instance file; minted (and written) on first use. Returns (record, created)."""
    path, _ = _paths(base)
    try:
        record = json.loads(path.read_text())
        if str(record.get("instance_id", "")).startswith("ins_"):
            return record, False
    except (OSError, ValueError):
        pass
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = {"instance_id": ha.new_ulid("ins"), "registered_version": None, "registered_repos": []}
    _write(path, record)
    return record, True


def _write(path: Path, record: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record))
    os.replace(tmp, path)


def declaration(version: str) -> dict:
    return {"schema": "agent-declaration/v1", "harness": {"name": "claude-code", "version": version},
            "adapter": None, "host_class": "workstation", "interactivity": "interactive",
            "accepted_kinds": [], "channels": []}


def session_start(owner: ha.OwnerPort, base: Path, version: str, repos: list[str]) -> None:
    record, _ = load_or_mint(base)
    if record.get("registered_version") == version and set(repos) <= set(record.get("registered_repos", [])):
        return  # already registered on this host for this version
    for repo in repos:
        owner.agent_register(repo, instance_id=record["instance_id"], declaration=declaration(version),
                             idempotency_key=f"reg.{record['instance_id']}.{version}")
    record.update(registered_version=version, registered_repos=sorted(set(repos)))
    _write(_paths(base)[0], record)


def prompt_submit(owner: ha.OwnerPort, base: Path, repos: list[str], now: float | None = None) -> bool:
    """Returns True when observations were attempted. Stamps first: failures are rate limited too."""
    now = time.time() if now is None else now
    path, stamp = _paths(base)
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError):
        return False  # SessionStart has not registered this host
    try:
        if now - stamp.stat().st_mtime < RATE_LIMIT_SECONDS:
            return False
    except OSError:
        pass
    stamp.write_text(str(int(now)))
    os.utime(stamp, (now, now))
    for repo in repos:
        for fact in ("observed", "attended"):
            owner.agent_observe(repo, instance_id=record["instance_id"], fact=fact, valid_for_seconds=VALID_FOR,
                                idempotency_key=f"obs.{record['instance_id']}.{fact}.{int(now)}")
    return True


def _on_alarm(signum, frame):  # noqa: ANN001
    raise TimeoutError("hook deadline")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    owner = None
    try:
        sys.stdin.read()  # hook event payload; not needed
    except Exception:  # noqa: BLE001
        pass
    try:
        if not argv or argv[0] not in ("session-start", "prompt-submit"):
            return 0
        signal.signal(signal.SIGALRM, _on_alarm)
        signal.alarm(DEADLINE_SECONDS)
        profile = os.environ.get("AGENTOPS_VUORO_PROFILE", DEFAULT_PROFILE)
        if not Path(profile).is_file():
            return 0
        owner = ha.VuoroOwner(profile)
        if argv[0] == "session-start":
            session_start(owner, instances_dir(), claude_version(), repo_ids())
        else:
            prompt_submit(owner, instances_dir(), repo_ids())
    except BaseException:  # noqa: BLE001 - fail open, including the alarm
        pass
    finally:
        signal.alarm(0)
        if owner is not None:
            try:
                owner.close()
            except BaseException:  # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
