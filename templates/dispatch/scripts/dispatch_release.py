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
import copy
import fnmatch
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

#: L-4: one cheap retry after a red gate, and no more. Named so a reader can
#: tell a bounded retry from a loop that happened to stop.
MAX_GATE_ATTEMPTS = 2

#: What a retry re-runs. ``prepare`` is what makes a dispatch expensive and the
#: worktree already exists with its cold gates no longer red, so re-running it
#: would buy nothing -- that is what makes the retry cheap.
RETRY_STEPS: tuple[str, ...] = ("run", "gate", "receipt")

#: Gate exit codes that carry a verdict rather than a failure. hybrid_dispatch
#: returns 2 from ``gate`` for ``coordinator_review_required``.
GATE_VERDICT_EXITS = frozenset({0, 2})

#: The L-2 stop-condition vocabulary, in the order the M-1 spec row lists them.
#: A fired condition exits non-zero, escalates once with ``stop_condition`` in
#: the metadata, and never reaches the PR step.
STOP_CONDITIONS: tuple[str, ...] = (
    "release-boundary",
    "command-not-allowed",
    "path-outside-writable",
    "gate-red-twice",
)

#: The three parts of the PR step, in the only order that works. A failed part
#: names itself in report["pr"]["failed_step"] so a reader of a failed report
#: can tell "the remote would not add" from "the push was rejected" from "gh
#: refused".
PR_STEP_NAMES: tuple[str, ...] = ("remote-add", "push", "pr-create")

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
    stop_condition: str | None = None,
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
    if stop_condition is not None:
        metadata["stop_condition"] = stop_condition
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
    # Same default as templates/dispatch/hooks/log-session-cost.sh: without it
    # every auditctl write fails with "AUDITCTL_ARTIFACTS_ROOT is required".
    os.environ.setdefault("AUDITCTL_ARTIFACTS_ROOT", "/projects/dev")
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


def _resolve_push_remote(
    repo_root: Path, push_remote: str | None, runner: Runner,
) -> str | None:
    """The URL the PR step pushes to. An explicit argument wins; otherwise the
    coordinator's origin is asked, read-only. None means no URL could be
    resolved, and the PR step skips rather than failing."""
    if push_remote is not None:
        return push_remote
    completed = runner(["git", "remote", "get-url", "origin"], repo_root)
    if completed.returncode != 0:
        return None
    return (completed.stdout or "").strip() or None


def _packet_command_ids(packet: dict[str, Any]) -> list[str]:
    """Every command id a packet references, from the oracle and acceptance rows."""
    ids: list[str] = []
    oracle = packet.get("oracle")
    if isinstance(oracle, dict):
        starts_red = oracle.get("starts_red")
        if isinstance(starts_red, str):
            ids.append(starts_red)
        elif isinstance(starts_red, list):
            ids.extend(cid for cid in starts_red if isinstance(cid, str))
    for prop in packet.get("acceptance_properties") or []:
        if isinstance(prop, dict):
            cid = prop.get("command_id")
            if isinstance(cid, str):
                ids.append(cid)
    return ids


def _preflight_stop(packet: dict[str, Any]) -> tuple[str, str] | None:
    """Stop conditions checked before any stage runs. Returns (condition, detail)."""
    if packet.get("release_boundary") is True:
        return ("release-boundary", "release_boundary is true in the packet")
    allowed = packet.get("allowed_command_ids")
    if allowed is not None:
        offending = [cid for cid in _packet_command_ids(packet) if cid not in allowed]
        if offending:
            return (
                "command-not-allowed",
                f"command ids outside allowed_command_ids: {', '.join(offending)}",
            )
    return None


def _gate_evidence(receipt: dict[str, Any] | None) -> dict[str, Any]:
    """The gate's evidence: nested under ``evidence`` in a real receipt, flat in a stub."""
    if isinstance(receipt, dict) and isinstance(receipt.get("evidence"), dict):
        return receipt["evidence"]
    return receipt if isinstance(receipt, dict) else {}


def _path_allowed(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _post_gate_stop(packet: dict[str, Any], evidence: dict[str, Any]) -> tuple[str, str] | None:
    """Stop conditions checked after the gate and before the PR step."""
    allowed = packet.get("allowed_command_ids")
    if allowed is not None:
        results = evidence.get("command_results") or []
        offending = [
            r.get("command_id") for r in results
            if isinstance(r, dict) and r.get("command_id") not in allowed
        ]
        if offending:
            return (
                "command-not-allowed",
                f"command ids outside allowed_command_ids: {', '.join(offending)}",
            )
    writable = packet.get("writable_patch_paths")
    if writable is not None:
        touched = evidence.get("touched_paths") or []
        offending = [p for p in touched if not _path_allowed(p, writable)]
        if offending:
            return (
                "path-outside-writable",
                f"touched paths outside writable_patch_paths: {', '.join(offending)}",
            )
    return None


def _gate_is_red(completed: subprocess.CompletedProcess, parsed: dict[str, Any] | None) -> bool:
    """A gate is red on a non-zero exit, a non-candidate disposition, or passed=false."""
    if completed.returncode != 0:
        return True
    if not isinstance(parsed, dict):
        return True
    if parsed.get("disposition") != "candidate":
        return True
    return _gate_evidence(parsed).get("passed") is False


def _record_red_gate(attempts_path: Path, starting_commit: str) -> int:
    """Increment the red-gate count for a starting_commit; returns the new count."""
    ledger: dict[str, Any] = {}
    if attempts_path.exists():
        ledger = _load_json(attempts_path)
    count = int(ledger.get(starting_commit, 0)) + 1
    ledger[starting_commit] = count
    attempts_path.parent.mkdir(parents=True, exist_ok=True)
    attempts_path.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    return count


def build_retry_packet(
    packet: dict[str, Any], attempt: int, stdout_tail: str, stderr_tail: str,
) -> dict[str, Any]:
    """The frozen packet plus the red gate's own output, and nothing else.

    The tails go into ``purpose`` as well as into ``retry_context``: the purpose
    is what the worker's prompt actually renders, so a retry that only sets a
    sibling key re-runs the same dispatch and calls it a retry. Nothing else
    moves -- a retry that quietly widened the sandbox would not be one.
    """
    retried = copy.deepcopy(packet)
    retried["attempt"] = attempt
    retried["retry_context"] = {
        "attempt": attempt,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
    retried["purpose"] = (
        str(packet.get("purpose", ""))
        + f"\n\nretry_context: attempt {attempt}. The previous attempt's gate was red. "
        "The gate's own output follows; it says what is still failing. Fix that, "
        "inside the same writable paths.\n"
        f"stdout_tail:\n{stdout_tail}\n"
        f"stderr_tail:\n{stderr_tail}"
    )
    return retried


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
    attempts_path: Path | None = None,
    push_remote: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """Run the fixed sequence. Returns (exit_code, report)."""
    packet = _load_json(packet_path)
    worktree = worktree_path(packet)
    passthrough = list(passthrough or [])
    if attempts_path is None:
        attempts_path = worktree.parent / f"{packet['task_id']}.attempts.json"
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
        "stop": None,
        "retry": None,
    }

    def finish(code: int) -> tuple[int, dict[str, Any]]:
        report["finished_at"] = _now()
        report["exit_code"] = code
        if report_path is not None:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        return code, report

    def stop(condition: str, detail: str) -> tuple[int, dict[str, Any]]:
        report["stop"] = {"condition": condition, "detail": detail}
        report["escalation"] = write_escalation(
            packet, "stop", 1, detail, runner, auditctl_bin, stop_condition=condition,
        )
        return finish(1)

    receipt_path = worktree.parent / f"{packet['task_id']}.receipt.json"
    report["receipt_path"] = str(receipt_path)
    gate_receipt: dict[str, Any] | None = None
    preflight = _preflight_stop(packet)
    if preflight is not None:
        return stop(*preflight)

    attempt = int(packet.get("attempt", 1))
    current_packet_path = packet_path
    current_packet = packet
    steps: tuple[str, ...] = STEPS

    while True:
      gate_red = False
      red_stdout = ""
      red_stderr = ""
      for step in steps:
        cmd = hybrid_cmd(step, current_packet_path, repo_root, python_bin, passthrough)
        started = _now()
        completed = runner(cmd, None)
        parsed = _parse_receipt(completed.stdout)
        entry: dict[str, Any] = {
            "step": step,
            "attempt": attempt,
            "command": cmd,
            "started_at": started,
            "finished_at": _now(),
            "exit_code": completed.returncode,
            "stderr": (completed.stderr or "").strip()[-2000:],
        }
        # Each stage emits its receipt on stdout, and that receipt is the only
        # record of what the stage actually observed -- the worker's exit code,
        # its spend, the gate's per-command results. Keeping only stderr made a
        # run that finished cleanly and changed nothing indistinguishable from a
        # run that never reached the model: diagnosing it cost a second dispatch.
        if parsed is not None:
            entry["receipt"] = parsed
        elif completed.stdout:
            entry["stdout_tail"] = completed.stdout.strip()[-4000:]
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
        if step == "gate":
            evidence = _gate_evidence(parsed)
            post_gate = _post_gate_stop(packet, evidence)
            if post_gate is not None:
                return stop(*post_gate)
            if _gate_is_red(completed, parsed):
                count = _record_red_gate(attempts_path, packet["starting_commit"])
                if count >= MAX_GATE_ATTEMPTS:
                    return stop(
                        "gate-red-twice",
                        f"second red gate on starting_commit {packet['starting_commit']}",
                    )
                gate_red = True
                # The retry has to carry what the gate actually said, not a
                # summary of it: the raw stdout is the gate's receipt and the
                # stderr is the command output the receipt points at.
                red_stdout = (completed.stdout or "").strip()[-4000:]
                red_stderr = (completed.stderr or "").strip()[-4000:]
        if step == "receipt":
            # Written before the PR step, and it IS the PR body.
            final = parsed if parsed is not None else {"raw_stdout": completed.stdout}
            final = dict(final)
            final["attempt"] = attempt
            final["gate"] = gate_receipt
            final["driver_steps"] = [
                {k: v for k, v in s.items() if k != "command"} for s in report["steps"]
            ]
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_text(json.dumps(final, indent=2) + "\n", encoding="utf-8")

      # L-4: exactly one cheap retry, and only for a red gate. A stage that
      # exited non-zero never produced a verdict to feed back, and a post-gate
      # stop means the packet is wrong rather than the worker -- neither is
      # answerable by running the worker again.
      if not gate_red or attempt >= MAX_GATE_ATTEMPTS:
          break
      attempt += 1
      current_packet = build_retry_packet(current_packet, attempt, red_stdout, red_stderr)
      current_packet_path = worktree.parent / f"{packet['task_id']}.attempt-{attempt}.json"
      current_packet_path.parent.mkdir(parents=True, exist_ok=True)
      current_packet_path.write_text(
          json.dumps(current_packet, indent=2) + "\n", encoding="utf-8",
      )
      report["retry"] = {
          "attempt": attempt,
          "packet_path": str(current_packet_path),
          "reason": "gate was red on the previous attempt; retried with its output",
      }
      steps = RETRY_STEPS

    if not receipt_path.exists():
        report["escalation"] = write_escalation(
            packet, "receipt", 1, "receipt file was not written", runner, auditctl_bin,
        )
        return finish(1)

    title = f"[hybrid] {packet['task_id']} @ {packet['starting_commit'][:12]}"
    cmd = pr_command(packet, receipt_path, base_branch, title, gh_bin)
    pr: dict[str, Any] = {"command": cmd, "body_file": str(receipt_path), "opened": False}

    def pr_failed(step_name: str, exit_code: int, stderr: str) -> tuple[int, dict[str, Any]]:
        pr["failed_step"] = step_name
        pr["exit_code"] = exit_code
        pr["stderr"] = stderr
        report["pr"] = pr
        report["escalation"] = write_escalation(
            packet, "pr", exit_code, stderr, runner, auditctl_bin,
        )
        return finish(exit_code)

    if report["disposition"] != "candidate":
        pr["skipped"] = True
        pr["reason"] = (
            f"gate disposition is {report['disposition']!r}, not 'candidate'; "
            "the coordinator must review before any PR is opened"
        )
    elif gate_red:
        pr["skipped"] = True
        pr["reason"] = (
            "gate is red (first red gate recorded); "
            "the coordinator must review before any PR is opened"
        )
    elif dry_run:
        pr["skipped"] = True
        pr["reason"] = "dry-run: would open this PR with the receipt as body"
    else:
        # The remote comes back here, in the driver, after the worker is done:
        # prepare_workspace deliberately removes origin from the worker's clone,
        # so the PR step has to re-add it. Resolution is read-only against the
        # coordinator checkout; every mutating git command below is pinned to
        # the packet's worktree.
        remote = _resolve_push_remote(repo_root, push_remote, runner)
        if remote is None:
            pr["skipped"] = True
            pr["reason"] = (
                "could not resolve a push remote from the coordinator's origin; "
                "no PR was opened"
            )
        else:
            branch = packet["worktree"]["branch"]
            add_cmd = ["git", "remote", "add", "origin", remote]
            completed = runner(add_cmd, worktree)
            if completed.returncode != 0:
                return pr_failed(
                    PR_STEP_NAMES[0], completed.returncode,
                    (completed.stderr or "").strip()[-2000:],
                )
            push_cmd = ["git", "push", "origin", f"{branch}:{branch}"]
            completed = runner(push_cmd, worktree)
            if completed.returncode != 0:
                return pr_failed(
                    PR_STEP_NAMES[1], completed.returncode,
                    (completed.stderr or "").strip()[-2000:],
                )
            pr["push"] = {"remote": remote, "branch": branch}
            # Runs in the worktree so gh resolves the repository from there,
            # never from the coordinator checkout. It is the only network step
            # and the only step that is not a hybrid_dispatch stage.
            completed = runner(cmd, worktree)
            pr["exit_code"] = completed.returncode
            pr["stdout"] = (completed.stdout or "").strip()
            pr["stderr"] = (completed.stderr or "").strip()[-2000:]
            pr["opened"] = completed.returncode == 0
            if completed.returncode != 0:
                return pr_failed(PR_STEP_NAMES[2], completed.returncode, pr["stderr"])
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
