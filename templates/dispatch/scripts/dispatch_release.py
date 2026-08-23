#!/usr/bin/env python3
"""L-1 hand-off driver: one packet, prepare -> run -> gate -> receipt -> PR, stop.

The driver chains the ``hybrid_dispatch.py`` stages for exactly one frozen task
packet and then, when the gate disposition is ``candidate``, opens a pull
request whose body is the receipt. It never merges. It never runs ``git``
against the coordinator checkout: every ``git`` invocation is pinned to the
packet's disposable worktree, and the PR step happens here in the driver —
outside the worker sandbox, whose ``network_policy: disabled`` and
``allowed_command_ids`` make ``gh pr create`` impossible from inside.

Step order is fixed in ``STEPS`` and is not configurable at the call site.
Any step that exits non-zero stops the sequence, writes an auditctl
``workflow.escalation`` event, and makes the driver exit non-zero.

One deliberate exception to "non-zero stops": ``gate`` exits 2 when it reached a
verdict of ``coordinator_review_required`` (a complete, parseable receipt with a
disposition). That is a *verdict*, not a failure — the packet contract says the
PR step is skipped with a recorded reason when the disposition is not
``candidate``, which requires ``receipt`` to run after such a gate. A gate exit
without a parseable disposition is a failure like any other.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
HYBRID_DISPATCH = HERE / "hybrid_dispatch.py"

#: Fixed stage order. The PR step is not a hybrid_dispatch stage; it is the
#: driver's own and runs only after ``receipt`` has been written to disk.
STEPS: tuple[str, ...] = ("prepare", "run", "gate", "receipt")

#: Gate exit codes that carry a verdict rather than a failure. hybrid_dispatch
#: returns 2 from ``gate`` for ``coordinator_review_required``.
GATE_VERDICT_EXITS = frozenset({0, 2})

ESCALATION_TYPE = "workflow.escalation"
DRIVER_ACTOR = "dispatch-release"


class DriverError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_receipt(stdout: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


Runner = Callable[[list[str], Path | None], subprocess.CompletedProcess]


def _default_runner(cmd: list[str], cwd: Path | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, text=True, capture_output=True, check=False, stdin=subprocess.DEVNULL,
    )


def worktree_path(packet: dict[str, Any]) -> Path:
    return Path(packet["worktree"]["root"]) / packet["repo_id"] / packet["task_id"]


def write_escalation(
    packet: dict[str, Any],
    step: str,
    exit_code: int,
    detail: str,
    runner: Runner,
    auditctl_bin: str,
) -> dict[str, Any]:
    """Record a workflow.escalation event. Degrades quietly without auditctl."""
    metadata = {
        "task_id": packet["task_id"],
        "repo_id": packet["repo_id"],
        "step": step,
        "exit_code": exit_code,
        "starting_commit": packet["starting_commit"],
        "driver": DRIVER_ACTOR,
    }
    record = {
        "type": ESCALATION_TYPE,
        "actor": DRIVER_ACTOR,
        "summary": f"{packet['task_id']}: step {step} exited {exit_code}; sequence stopped",
        "detail": detail[-4000:],
        "metadata": metadata,
        "recorded_at": _now(),
    }
    if shutil.which(auditctl_bin) is None and not Path(auditctl_bin).exists():
        record["sink"] = "unavailable"
        return record
    cmd = [
        auditctl_bin, "add",
        "--type", ESCALATION_TYPE,
        "--source", DRIVER_ACTOR,
        "--actor", DRIVER_ACTOR,
        "--summary", record["summary"],
        "--detail", record["detail"],
        "--ref", f"sha:{packet['starting_commit']}",
        "--metadata", json.dumps(metadata, sort_keys=True),
    ]
    completed = runner(cmd, None)
    record["sink"] = "auditctl" if completed.returncode == 0 else "auditctl_failed"
    if completed.returncode != 0:
        record["sink_error"] = (completed.stderr or completed.stdout).strip()[-1000:]
    return record


def hybrid_cmd(
    step: str,
    packet_path: Path,
    repo_root: Path,
    python_bin: str,
    passthrough: list[str],
) -> list[str]:
    return [
        python_bin, str(HYBRID_DISPATCH),
        "--repo-root", str(repo_root),
        "--packet", str(packet_path),
        *passthrough,
        step,
    ]


def pr_command(
    packet: dict[str, Any], receipt_path: Path, base: str, title: str, gh_bin: str,
) -> list[str]:
    """The single ``gh pr create`` invocation. Body is the receipt file."""
    return [
        gh_bin, "pr", "create",
        "--head", packet["worktree"]["branch"],
        "--base", base,
        "--title", title,
        "--body-file", str(receipt_path),
    ]


def drive(
    packet_path: Path,
    repo_root: Path,
    *,
    dry_run: bool,
    base_branch: str,
    python_bin: str = sys.executable,
    gh_bin: str = "gh",
    auditctl_bin: str = "auditctl",
    passthrough: list[str] | None = None,
    runner: Runner = _default_runner,
    report_path: Path | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run the fixed sequence. Returns (exit_code, report)."""
    packet = _load_json(packet_path)
    worktree = worktree_path(packet)
    passthrough = list(passthrough or [])
    report: dict[str, Any] = {
        "schema_version": "agentops-dispatch-release/v1",
        "task_id": packet["task_id"],
        "starting_commit": packet["starting_commit"],
        "coordinator_repo_root": str(repo_root),
        "worktree": str(worktree),
        "dry_run": dry_run,
        "started_at": _now(),
        "steps": [],
        "disposition": None,
        "receipt_path": None,
        "pr": None,
        "escalation": None,
    }

    def finish(code: int) -> tuple[int, dict[str, Any]]:
        report["finished_at"] = _now()
        report["exit_code"] = code
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return code, report

    receipt_path = worktree.parent / f"{packet['task_id']}.receipt.json"
    report["receipt_path"] = str(receipt_path)
    gate_receipt: dict[str, Any] | None = None

    for step in STEPS:
        cmd = hybrid_cmd(step, packet_path, repo_root, python_bin, passthrough)
        started = _now()
        completed = runner(cmd, None)
        parsed = _parse_receipt(completed.stdout)
        entry: dict[str, Any] = {
            "step": step,
            "command": cmd,
            "started_at": started,
            "finished_at": _now(),
            "exit_code": completed.returncode,
            "stderr": (completed.stderr or "").strip()[-2000:],
        }
        if step == "gate":
            disposition = parsed.get("disposition") if parsed else None
            entry["disposition"] = disposition
            verdict = completed.returncode in GATE_VERDICT_EXITS and disposition is not None
            failed = not verdict
            if not failed:
                gate_receipt = parsed
                report["disposition"] = disposition
        else:
            failed = completed.returncode != 0
        entry["failed"] = failed
        report["steps"].append(entry)
        if failed:
            detail = (completed.stderr or "").strip() or (completed.stdout or "").strip()
            report["escalation"] = write_escalation(
                packet, step, completed.returncode, detail, runner, auditctl_bin,
            )
            return finish(completed.returncode or 1)
        if step == "receipt":
            # Written before the PR step, and it IS the PR body.
            final = parsed if parsed is not None else {"raw_stdout": completed.stdout}
            final = dict(final)
            final["gate"] = gate_receipt
            final["driver_steps"] = [
                {k: v for k, v in s.items() if k != "command"} for s in report["steps"]
            ]
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")

    if not receipt_path.exists():
        report["escalation"] = write_escalation(
            packet, "receipt", 1, "receipt file was not written", runner, auditctl_bin,
        )
        return finish(1)

    title = f"[hybrid] {packet['task_id']} @ {packet['starting_commit'][:12]}"
    cmd = pr_command(packet, receipt_path, base_branch, title, gh_bin)
    pr: dict[str, Any] = {"command": cmd, "body_file": str(receipt_path), "opened": False}
    if report["disposition"] != "candidate":
        pr["skipped"] = True
        pr["reason"] = (
            f"gate disposition is {report['disposition']!r}, not 'candidate'; "
            "the coordinator must review before any PR is opened"
        )
    elif dry_run:
        pr["skipped"] = True
        pr["reason"] = "dry-run: would open this PR with the receipt as body"
    else:
        # Runs in the worktree so gh resolves the repository from there, never
        # from the coordinator checkout. It is the only network step and the
        # only step that is not a hybrid_dispatch stage.
        completed = runner(cmd, worktree)
        pr["exit_code"] = completed.returncode
        pr["stdout"] = (completed.stdout or "").strip()
        pr["stderr"] = (completed.stderr or "").strip()[-2000:]
        pr["opened"] = completed.returncode == 0
        if completed.returncode != 0:
            report["pr"] = pr
            report["escalation"] = write_escalation(
                packet, "pr", completed.returncode, pr["stderr"], runner, auditctl_bin,
            )
            return finish(completed.returncode)
        pr["url"] = pr["stdout"].splitlines()[-1] if pr["stdout"] else None
    report["pr"] = pr
    return finish(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="main", help="PR base branch (never pushed to).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run every step except gh pr create; report what it would open.")
    parser.add_argument("--gh-bin", default=os.environ.get("GH_BIN", "gh"))
    parser.add_argument("--auditctl-bin", default=os.environ.get("AUDITCTL_BIN", "auditctl"))
    parser.add_argument("--report", type=Path, help="Write the driver report JSON here too.")
    args, passthrough = parser.parse_known_args(argv)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    code, report = drive(
        args.packet.resolve(),
        args.repo_root.resolve(),
        dry_run=args.dry_run,
        base_branch=args.base,
        gh_bin=args.gh_bin,
        auditctl_bin=args.auditctl_bin,
        passthrough=passthrough,
        report_path=args.report,
    )
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
