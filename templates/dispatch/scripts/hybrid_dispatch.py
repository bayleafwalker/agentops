#!/usr/bin/env python3
"""Coordinator-side driver for the AgentOps supervised hybrid dispatch mode.

The coordinator (a Claude or Codex harness session) owns every step here. The
OpenCode worker only ever sees the frozen packet, a disposable worktree, and a
session permission overlay derived from that packet.

Subcommands
-----------
validate   Structural check of a packet against the repository dispatch manifest.
overlay    Emit the session-only OpenCode permission overlay for a packet.
prepare    Create the disposable exact-commit worktree and run gates cold.
run        Dispatch one bounded worker loop for the packet.
gate       Run the post-dispatch deterministic gates and capture the diff.
receipt    Emit a disposition receipt for the packet.

Nothing here touches git history on the main worktree, sprintctl, or any
deployment surface: those authorities stay with the coordinator and the human.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

POLICY_RELATIVE = Path("templates/dispatch/hybrid/hybrid-dispatch.v1.json")
WORKER_CONFIG_RELATIVE = Path("templates/dispatch/hybrid/opencode.hybrid.json")
PACKET_SCHEMA_VERSION = "agentops-task/v1"
AGENTOPS_ROOT = Path(
    os.environ.get("AGENTOPS_ROOT", "/projects/dev/agentops")
).resolve()

REQUIRED_PACKET_FIELDS = (
    "schema_version",
    "task_id",
    "repo_id",
    "sprint_item",
    "route",
    "starting_commit",
    "purpose",
    "readable_context_paths",
    "writable_patch_paths",
    "protected_paths",
    "required_outcomes",
    "non_goals",
    "allowed_command_ids",
    "limits",
    "network_policy",
    "worktree",
)

WORKER_DENIED_PERMISSIONS = ("external_directory", "webfetch", "websearch", "task")


class PacketError(RuntimeError):
    """A packet is unfit for dispatch. Always a task_defect, never a retry."""


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PacketError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PacketError(f"invalid JSON in {path}: {exc}") from exc


def load_policy(agentops_root: Path = AGENTOPS_ROOT) -> dict[str, Any]:
    """Load the canonical hybrid dispatch policy.

    A deployed host may pin an immutable copy; ``AGENTOPS_HYBRID_POLICY`` selects
    it so the host never silently follows a mutable source checkout.
    """
    override = os.environ.get("AGENTOPS_HYBRID_POLICY")
    path = Path(override) if override else agentops_root / POLICY_RELATIVE
    policy = _load_json(path)
    if policy.get("schema_version") != "agentops-hybrid-dispatch/v1":
        raise PacketError(f"{path}: unexpected policy schema_version")
    return policy


def load_worker_config_path(agentops_root: Path = AGENTOPS_ROOT) -> Path:
    """Resolve the checked-in OpenCode worker agent config.

    ``AGENTOPS_HYBRID_WORKER_CONFIG`` lets a deployed host pin an immutable copy
    alongside its pinned policy.
    """
    override = os.environ.get("AGENTOPS_HYBRID_WORKER_CONFIG")
    if override:
        return Path(override)
    return agentops_root / WORKER_CONFIG_RELATIVE


def load_manifest(repo_root: Path) -> dict[str, Any]:
    candidates = sorted(repo_root.glob("*.dispatch.json"))
    if not candidates:
        raise PacketError(f"{repo_root}: no *.dispatch.json manifest")
    if len(candidates) > 1:
        names = ", ".join(p.name for p in candidates)
        raise PacketError(f"{repo_root}: ambiguous dispatch manifests ({names})")
    return _load_json(candidates[0])


def _matches_any(path: str, patterns: list[str]) -> bool:
    """True when ``path`` is covered by any glob or directory-prefix pattern.

    Manifest scope roots are written as directory prefixes (``docs/``) while
    packets use globs (``docs/**``); both forms must resolve here.
    """
    for pattern in patterns:
        if pattern.endswith("/"):
            if path == pattern.rstrip("/") or path.startswith(pattern):
                return True
            continue
        if fnmatch.fnmatch(path, pattern):
            return True
        prefix = pattern[: -len("/**")] if pattern.endswith("/**") else None
        if prefix is not None and (path == prefix or path.startswith(prefix + "/")):
            return True
        if path == pattern:
            return True
    return False


def _pattern_escapes_repo(pattern: str) -> bool:
    if pattern.startswith("/") or pattern.startswith("~"):
        return True
    return any(part == ".." for part in Path(pattern).parts)


def validate_packet(
    packet: dict[str, Any],
    manifest: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    """Return the ordered list of pre-gates this packet satisfies structurally.

    Raises PacketError on the first unfitness. A contradictory packet stops as a
    task defect rather than being softened into a retry.
    """
    missing = [field for field in REQUIRED_PACKET_FIELDS if field not in packet]
    if missing:
        raise PacketError(f"packet is missing required fields: {', '.join(missing)}")
    if packet["schema_version"] != PACKET_SCHEMA_VERSION:
        raise PacketError(
            f"packet schema_version must be {PACKET_SCHEMA_VERSION}, "
            f"got {packet['schema_version']!r}"
        )

    hybrid = manifest.get("hybrid")
    if not hybrid:
        raise PacketError(
            f"repository {manifest.get('repo_id')!r} has no hybrid block in its "
            "dispatch manifest; it is not hybrid-eligible"
        )
    if not hybrid.get("enabled", False):
        raise PacketError(
            f"repository {manifest.get('repo_id')!r} has hybrid dispatch disabled"
        )

    route = packet["route"]
    if route not in policy["routes"]:
        raise PacketError(f"unknown route {route!r}")
    if policy["routes"][route].get("mode") != "supervised_hybrid":
        raise PacketError(f"route {route!r} is not a supervised_hybrid worker route")
    allowed_routes = hybrid.get("worker_routes", [])
    if route not in allowed_routes:
        raise PacketError(
            f"route {route!r} is not enabled for this repository "
            f"(allowed: {', '.join(allowed_routes) or 'none'})"
        )

    if packet["network_policy"] != "disabled":
        raise PacketError("network_policy must be 'disabled' for worker dispatch")

    commit = packet["starting_commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise PacketError("starting_commit must be a full lowercase 40-hex commit")

    item_ref = packet["sprint_item"].get("ref", "")
    if "#" not in item_ref:
        raise PacketError("sprint_item.ref must be a sprintctl repo#id reference")
    if not packet["sprint_item"].get("claim_actor"):
        raise PacketError("sprint_item.claim_actor is required; the coordinator holds the claim")

    scope_roots = manifest.get("scope", {}).get("allowed_path_roots", [])
    protected = list(hybrid.get("protected_paths", [])) + list(packet["protected_paths"])

    for pattern in packet["writable_patch_paths"]:
        if _pattern_escapes_repo(pattern):
            raise PacketError(f"writable path escapes the repository: {pattern}")
        if scope_roots and not _matches_any(pattern, scope_roots):
            raise PacketError(
                f"writable path {pattern} is outside manifest scope.allowed_path_roots"
            )
        if _matches_any(pattern, protected):
            raise PacketError(f"writable path {pattern} intersects a protected path")

    for pattern in packet["readable_context_paths"]:
        if _pattern_escapes_repo(pattern):
            raise PacketError(f"readable path escapes the repository: {pattern}")

    commands = hybrid.get("commands", {})
    for command_id in packet["allowed_command_ids"]:
        if command_id not in commands:
            raise PacketError(
                f"command id {command_id!r} is not registered in the repository "
                "hybrid.commands map"
            )

    limits = packet["limits"]
    ceiling = hybrid.get("max_timeout_seconds")
    if ceiling and limits["timeout_seconds"] > ceiling:
        raise PacketError(
            f"limits.timeout_seconds {limits['timeout_seconds']} exceeds the "
            f"repository ceiling {ceiling}"
        )

    max_attempts = policy["routes"][route].get("max_attempts", 1)
    if packet.get("attempt", 1) > max_attempts:
        raise PacketError(
            f"attempt {packet.get('attempt')} exceeds max_attempts {max_attempts} "
            f"for route {route!r}; reroute or escalate explicitly"
        )

    return list(policy["gates"]["pre"])


def build_overlay(
    packet: dict[str, Any],
    manifest: dict[str, Any],
    policy: dict[str, Any],
    base_config: dict[str, Any],
) -> dict[str, Any]:
    """Build the session-only OpenCode permission overlay for one packet.

    Noninteractive ``opencode run`` refuses permissions left at ``ask``, and
    ``--auto`` is far too broad for a frozen packet, so every permission is
    resolved here to an explicit allow or deny.
    """
    route = packet["route"]
    agent_name = policy["routes"][route]["agent"]
    base_agent = base_config["agent"][agent_name]
    commands = manifest["hybrid"]["commands"]

    bash: dict[str, str] = {}
    for command_id in packet["allowed_command_ids"]:
        bash[commands[command_id]] = "allow"
    bash["*"] = "deny"

    edit: dict[str, str] = {}
    for pattern in packet["writable_patch_paths"]:
        edit[pattern] = "allow"
    edit["*"] = "deny"

    overlay = {
        "$schema": base_config.get("$schema", "https://opencode.ai/config.json"),
        "model": base_agent["model"],
        "permission": {
            "*": "deny",
            "edit": edit,
            "bash": bash,
            "external_directory": "deny",
            "webfetch": "deny",
            "websearch": "deny",
        },
        "agent": {
            agent_name: {
                **base_agent,
                "permission": {
                    **base_agent.get("permission", {}),
                    "edit": edit,
                    "bash": bash,
                    "task": "deny",
                    "external_directory": "deny",
                    "webfetch": "deny",
                    "websearch": "deny",
                },
            }
        },
    }
    if agent_name == "ao-review":
        overlay["permission"]["edit"] = "deny"
        overlay["permission"]["bash"] = "deny"
        overlay["agent"][agent_name]["permission"]["edit"] = "deny"
        overlay["agent"][agent_name]["permission"]["bash"] = "deny"
    return overlay


def overlay_hash(overlay: dict[str, Any]) -> str:
    payload = json.dumps(overlay, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PacketError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def worktree_path(packet: dict[str, Any]) -> Path:
    return Path(packet["worktree"]["root"]) / packet["repo_id"] / packet["task_id"]


def prepare_worktree(repo_root: Path, packet: dict[str, Any]) -> Path:
    target = worktree_path(packet)
    if target.exists():
        raise PacketError(
            f"{target} already exists; never dispatch two workers into one worktree"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(
        repo_root,
        "worktree",
        "add",
        "-b",
        packet["worktree"]["branch"],
        str(target),
        packet["starting_commit"],
    )
    return target


def run_registered_commands(
    worktree: Path, packet: dict[str, Any], manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    commands = manifest["hybrid"]["commands"]
    results: list[dict[str, Any]] = []
    for command_id in packet["allowed_command_ids"]:
        command = commands[command_id]
        completed = subprocess.run(
            command,
            shell=True,
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=packet["limits"]["timeout_seconds"],
            check=False,
        )
        results.append(
            {
                "command_id": command_id,
                "command": command,
                "exit_code": completed.returncode,
                "stdout_tail": completed.stdout[-4000:],
                "stderr_tail": completed.stderr[-4000:],
            }
        )
    return results


def dispatch_worker(
    worktree: Path,
    packet_path: Path,
    packet: dict[str, Any],
    overlay: dict[str, Any],
    policy: dict[str, Any],
    opencode_bin: str,
) -> dict[str, Any]:
    """Run exactly one bounded worker loop and return its raw transcript record."""
    agent_name = policy["routes"][packet["route"]]["agent"]
    message = (
        "Implement only the attached frozen task packet. Stay inside the writable "
        "paths it declares, use only the registered commands, and stop with a "
        "structured blocker on any ambiguity, missing context, or scope conflict. "
        "Do not use git, do not change sprint state, and do not expand scope."
    )
    env = {
        **os.environ,
        "OPENCODE_CONFIG_CONTENT": json.dumps(overlay),
    }
    # OpenCode 1.18.5 treats positional arguments after --file as further file
    # values, so the message must precede it.
    argv = [
        opencode_bin,
        "run",
        message,
        "--agent",
        agent_name,
        "--file",
        str(packet_path),
        "--format",
        "json",
    ]
    completed = subprocess.run(
        argv,
        cwd=worktree,
        env=env,
        capture_output=True,
        text=True,
        timeout=packet["limits"]["timeout_seconds"],
        check=False,
    )
    return {
        "argv": [shlex.quote(a) for a in argv],
        "agent": agent_name,
        "model": policy["routes"][packet["route"]]["harness_model"],
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr_tail": completed.stderr[-4000:],
    }


def post_gates(
    worktree: Path, packet: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    """Run the deterministic post-dispatch gates. Worker claims are not evidence."""
    changed = [
        line.strip()
        for line in _git(worktree, "diff", "--name-only", packet["starting_commit"]).splitlines()
        if line.strip()
    ]
    untracked = [
        line.strip()
        for line in _git(worktree, "ls-files", "--others", "--exclude-standard").splitlines()
        if line.strip()
    ]
    touched = sorted(set(changed) | set(untracked))
    protected = list(manifest["hybrid"].get("protected_paths", [])) + list(
        packet["protected_paths"]
    )
    out_of_scope = [p for p in touched if not _matches_any(p, packet["writable_patch_paths"])]
    protected_hits = [p for p in touched if _matches_any(p, protected)]
    command_results = run_registered_commands(worktree, packet, manifest)

    gates = {
        "diff-nonempty": bool(touched),
        "diff-scope-respected": not out_of_scope,
        "protected-paths-untouched": not protected_hits,
        "worktree-clean": True,
        "registered-commands-green": all(r["exit_code"] == 0 for r in command_results),
    }
    return {
        "gates": gates,
        "passed": all(gates.values()),
        "touched_paths": touched,
        "out_of_scope_paths": out_of_scope,
        "protected_path_hits": protected_hits,
        "command_results": command_results,
        "diff": _git(worktree, "diff", packet["starting_commit"]),
    }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _receipt(packet: dict[str, Any], policy: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "recorded_at": _now(),
        "task_id": packet["task_id"],
        "repo_id": packet["repo_id"],
        "sprint_item": packet["sprint_item"],
        "route": packet["route"],
        "attempt": packet.get("attempt", 1),
        "harness_model": policy["routes"][packet["route"]]["harness_model"],
        "qualification": policy["qualification"],
        "acceptance_authority": policy["acceptance_authority"],
        **extra,
    }


def _emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--agentops-root", type=Path, default=AGENTOPS_ROOT)
    parser.add_argument("--opencode-bin", default=os.environ.get("OPENCODE_BIN", "opencode"))
    parser.add_argument(
        "command",
        choices=["validate", "overlay", "prepare", "run", "gate", "receipt"],
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    packet_path = args.packet.resolve()

    try:
        packet = _load_json(packet_path)
        manifest = load_manifest(repo_root)
        policy = load_policy(args.agentops_root.resolve())
        pre_gates = validate_packet(packet, manifest, policy)

        if args.command == "validate":
            _emit({"packet": packet["task_id"], "status": "fit", "pre_gates": pre_gates})
            return 0

        base_config = _load_json(load_worker_config_path(args.agentops_root.resolve()))
        overlay = build_overlay(packet, manifest, policy, base_config)

        if args.command == "overlay":
            _emit({"overlay": overlay, "overlay_sha256": overlay_hash(overlay)})
            return 0

        if args.command == "prepare":
            worktree = prepare_worktree(repo_root, packet)
            cold = run_registered_commands(worktree, packet, manifest)
            green = all(r["exit_code"] == 0 for r in cold)
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="prepare",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    cold_command_results=cold,
                    eligible_for_dispatch=green,
                )
            )
            return 0 if green else 2

        worktree = worktree_path(packet)
        if not worktree.exists():
            raise PacketError(f"{worktree} does not exist; run 'prepare' first")

        if args.command == "run":
            transcript = dispatch_worker(
                worktree, packet_path, packet, overlay, policy, args.opencode_bin
            )
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="run",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    worker=transcript,
                )
            )
            return 0

        if args.command == "gate":
            evidence = post_gates(worktree, packet, manifest)
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="gate",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    evidence=evidence,
                    disposition=(
                        "candidate" if evidence["passed"] else "coordinator_review_required"
                    ),
                )
            )
            return 0 if evidence["passed"] else 2

        # receipt
        _emit(
            _receipt(
                packet,
                policy,
                stage="receipt",
                worktree=str(worktree),
                overlay_sha256=overlay_hash(overlay),
                dispositions_available=policy["dispositions"],
                note=(
                    "The coordinator records the disposition and the human accepts, "
                    "merges, and changes sprint state."
                ),
            )
        )
        return 0
    except PacketError as exc:
        print(f"hybrid-dispatch: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
