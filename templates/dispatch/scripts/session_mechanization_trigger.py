#!/usr/bin/env python3
"""Trigger wiring for the session-mechanization Tier-2 paths (item #1172).

Owns scheduling only, never judgment. `reconcile-tick` dispatches one fresh,
non-interactive Claude session per unconsumed capsule found by
`session_scribe.py plan` (the Tier-2 latency optimization, following
`skills/session-reconciler/SKILL.md`). `scribe-tick` dispatches one fresh
session per configured artifact root on a schedule (the correctness path,
following `skills/session-scribe/SKILL.md`). Both skills only ever write
`reconciliation-proposal/v1` artifacts or a no-change record -- neither
mutates sprintctl state, so a bad tick produces at most a bad proposal for
a human to reject, never a bad sprint transition.

Idempotence is layered:
- within one artifact root, `session_scribe.py`'s durable cursor plus each
  skill's own already-consumed check make a capsule immune to
  double-processing even if dispatched twice;
- across overlapping trigger runs for the *same* root, a flock in this
  script serializes ticks so two crons never race the same cursor file.

Every dispatch attempt is appended to `status.ndjson` (one line per attempt)
so `status` can answer "did the last tick actually fire, and how stale is
the backlog" without re-deriving it from Claude Code logs.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIBE_SCRIPT = Path(__file__).with_name("session_scribe.py")
STATE_DIR = Path("~/.local/state/actionq/session-mechanization-trigger").expanduser()
STATUS_LOG = STATE_DIR / "status.ndjson"
LOCK_DIR = STATE_DIR / "locks"

RECONCILER_SKILL = "templates/dispatch/skills/session-reconciler/SKILL.md"
SCRIBE_SKILL = "templates/dispatch/skills/session-scribe/SKILL.md"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log_status(entry: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"logged_at": _now_iso(), **entry}
    with STATUS_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


class _LockHeld(Exception):
    pass


def _acquire_lock(name: str):
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_DIR / f"{name}.lock", "w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise _LockHeld(name)
    return handle


def _run_skill_session(*, skill: str, instruction: str, add_dirs: list[Path]) -> subprocess.CompletedProcess:
    prompt = (
        f"Follow {skill} exactly, start to finish, and nothing outside its "
        f"'Do Not' boundaries. {instruction} "
        "Report which outcome you recorded (or that you deferred to the "
        "scribe) at the end."
    )
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    for d in add_dirs:
        cmd.extend(["--add-dir", str(d)])
    cmd.extend(["--allowedTools", "Bash,Read,Write,Glob,Grep"])
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )


def _plan(root: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIBE_SCRIPT), "plan", "--root", str(root)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def cmd_reconcile_tick(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        lock = _acquire_lock(f"cursor-{args.project}")
    except _LockHeld:
        _log_status({"trigger": "reconcile", "project": args.project, "outcome": "skipped-locked"})
        print(f"reconcile-tick: a run for {args.project} is already in progress, skipping", file=sys.stderr)
        return 0

    try:
        plan = _plan(root)
        capsule_ids = [c["capsule_id"] for group in plan["groups"] for c in group["capsules"]]
        if not capsule_ids:
            _log_status({"trigger": "reconcile", "project": args.project, "outcome": "no-op", "unconsumed_count": 0})
            print(f"reconcile-tick: nothing unconsumed for {args.project}")
            return 0

        exit_code = 0
        for capsule_id in capsule_ids:
            instruction = f"--root {root} --project {args.project} --capsule-id {capsule_id}."
            result = _run_skill_session(
                skill=RECONCILER_SKILL,
                instruction=instruction,
                add_dirs=[REPO_ROOT, root],
            )
            ok = result.returncode == 0
            _log_status(
                {
                    "trigger": "reconcile",
                    "project": args.project,
                    "capsule_id": capsule_id,
                    "outcome": "dispatched-ok" if ok else "dispatched-failed",
                    "returncode": result.returncode,
                }
            )
            if not ok:
                exit_code = 1
                print(result.stderr[-4000:], file=sys.stderr)
        return exit_code
    finally:
        lock.close()


def cmd_scribe_tick(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    try:
        lock = _acquire_lock(f"cursor-{args.project}")  # same key as reconcile-tick: they share one cursor
    except _LockHeld:
        _log_status({"trigger": "scribe", "project": args.project, "outcome": "skipped-locked"})
        print(f"scribe-tick: a run for {args.project} is already in progress, skipping", file=sys.stderr)
        return 0

    try:
        plan = _plan(root)
        if plan["unconsumed_count"] == 0:
            _log_status({"trigger": "scribe", "project": args.project, "outcome": "no-op", "unconsumed_count": 0})
            print(f"scribe-tick: nothing unconsumed for {args.project}")
            return 0

        instruction = f"--root {root} --project {args.project}."
        result = _run_skill_session(
            skill=SCRIBE_SKILL,
            instruction=instruction,
            add_dirs=[REPO_ROOT, root],
        )
        ok = result.returncode == 0
        _log_status(
            {
                "trigger": "scribe",
                "project": args.project,
                "outcome": "dispatched-ok" if ok else "dispatched-failed",
                "returncode": result.returncode,
                "unconsumed_count_before": plan["unconsumed_count"],
            }
        )
        if not ok:
            print(result.stderr[-4000:], file=sys.stderr)
            return 1
        return 0
    finally:
        lock.close()


def cmd_status(args: argparse.Namespace) -> int:
    backlog = {}
    for root in args.root:
        result = subprocess.run(
            [sys.executable, str(SCRIBE_SCRIPT), "status", "--root", str(root.resolve())],
            capture_output=True,
            text=True,
            check=True,
        )
        backlog[str(root)] = json.loads(result.stdout)

    recent_triggers = []
    if STATUS_LOG.exists():
        lines = STATUS_LOG.read_text(encoding="utf-8").strip().splitlines()
        recent_triggers = [json.loads(line) for line in lines[-args.tail:]]

    print(json.dumps({"backlog": backlog, "recent_triggers": recent_triggers}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    reconcile_parser = subparsers.add_parser("reconcile-tick", help="Dispatch the immediate reconciler for every unconsumed capsule")
    reconcile_parser.add_argument("--root", type=Path, required=True)
    reconcile_parser.add_argument("--project", required=True)
    reconcile_parser.set_defaults(func=cmd_reconcile_tick)

    scribe_parser = subparsers.add_parser("scribe-tick", help="Dispatch the periodic scribe once for one artifact root")
    scribe_parser.add_argument("--root", type=Path, required=True)
    scribe_parser.add_argument("--project", required=True)
    scribe_parser.set_defaults(func=cmd_scribe_tick)

    status_parser = subparsers.add_parser("status", help="Print backlog age per root plus recent trigger attempts")
    status_parser.add_argument("--root", type=Path, action="append", required=True)
    status_parser.add_argument("--tail", type=int, default=20)
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
