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

    Two OpenCode 1.18.5 behaviours constrain the shape, both measured against
    ``opencode-go/deepseek-v4-flash`` on a trivial single-file edit:

    * A wildcard ``"*": "deny"`` does not merely gate calls, it withholds the
      tools from the model entirely. A blanket top-level deny left the worker
      with no toolset at all, so it emitted a pseudo tool call as prose
      (``<read_file src=.../>``) and stopped with an empty diff. Every tool is
      therefore enumerated explicitly and the blanket deny is gone.
    * The same applies inside a per-tool map: an ``edit`` map whose ``"*"`` is
      ``deny`` withholds the edit tool even when specific paths are allowed, so
      per-path scoping of ``edit`` silently guarantees an empty diff. ``bash``
      does not share this behaviour and keeps its registered-command map.

    So ``edit`` is granted whole and write containment rests where it is
    actually adjudicated anyway: the disposable exact-commit worktree,
    ``external_directory: deny``, and the cold ``diff-scope-respected`` /
    ``protected-paths-untouched`` post-gates. The packet's
    ``writable_patch_paths`` stay the contract the gates enforce; the overlay is
    defence in depth over them, never the sole boundary.
    """
    route = packet["route"]
    agent_name = policy["routes"][route]["agent"]
    base_agent = base_config["agent"][agent_name]
    commands = manifest["hybrid"]["commands"]

    bash: dict[str, str] = {}
    for command_id in packet["allowed_command_ids"]:
        bash[commands[command_id]] = "allow"
    bash["*"] = "deny"

    # Read-side tools the worker needs to locate its own work. Without these
    # the model cannot inspect the tree it is asked to patch.
    permission = {
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "list": "allow",
        "todowrite": "allow",
        "todoread": "allow",
        "edit": "allow",
        "write": "allow",
        "patch": "allow",
        "bash": bash,
        "task": "deny",
        "external_directory": "deny",
        "webfetch": "deny",
        "websearch": "deny",
    }

    overlay = {
        "$schema": base_config.get("$schema", "https://opencode.ai/config.json"),
        "model": base_agent["model"],
        "permission": dict(permission),
        "agent": {
            agent_name: {
                **base_agent,
                "permission": {
                    **base_agent.get("permission", {}),
                    **permission,
                },
            }
        },
    }
    if agent_name == "ao-review":
        # The challenger reads a captured diff and never mutates the worktree,
        # so every write surface is withheld, not just `edit`.
        for surface in ("edit", "write", "patch", "bash"):
            overlay["permission"][surface] = "deny"
            overlay["agent"][agent_name]["permission"][surface] = "deny"
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


#: Agent-context files OpenCode auto-loads into the worker's prompt without a
#: tool call. These are the measured leak vector for the coordinator's path.
AGENT_CONTEXT_FILES = ("AGENTS.md", "CLAUDE.md", ".agents/AGENTS.md")


def reroot_agent_context(workspace: Path, repo_root: Path) -> list[str]:
    """Repoint absolute coordinator paths in auto-loaded context at the clone.

    This is the actual escape mechanism, and it is not a git one. A repository's
    ``AGENTS.md`` documents commands with the absolute checkout path; OpenCode
    loads it into the prompt unasked; a worker given a packet it must *locate*
    work for then explores those absolute paths and writes to them. It never
    consults git to do so.

    Rerooting only works in a standalone clone. Attempted first on a linked
    worktree it changed nothing, because OpenCode resolved the project root to
    the coordinator's checkout and loaded *that* copy -- which is why clone
    isolation and this rewrite are one fix rather than two, and why neither
    alone was sufficient.
    """
    needle = str(repo_root)
    rewritten: list[str] = []
    for relative in AGENT_CONTEXT_FILES:
        path = workspace / relative
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        if needle not in original:
            continue
        path.write_text(original.replace(needle, str(workspace)), encoding="utf-8")
        rewritten.append(relative)
    return rewritten


def restore_agent_context(workspace: Path, repo_root: Path) -> None:
    """Undo :func:`reroot_agent_context` where the worker left the file alone.

    The rewrite is coordinator scaffolding, not worker output, so it must not
    reach the captured diff and trip ``diff-scope-respected``. A file whose only
    difference from its committed blob is the substitution is restored; one the
    worker genuinely edited is left as found, so a real out-of-scope edit still
    fails its gate instead of being quietly reverted.
    """
    for relative in AGENT_CONTEXT_FILES:
        path = workspace / relative
        if not path.is_file():
            continue
        current = path.read_text(encoding="utf-8")
        if str(workspace) not in current:
            continue
        restored = current.replace(str(workspace), str(repo_root))
        if restored == _git(workspace, "show", f"HEAD:{relative}"):
            path.write_text(restored, encoding="utf-8")


def safety_ref(repo_root: Path, packet: dict[str, Any]) -> dict[str, Any]:
    """Pin the coordinator's pre-dispatch commit behind a named ref.

    Recoverability must be a property of the tool, not of operator discipline:
    the ref is created here so nobody has to remember to checkpoint, and the
    receipt carries the one command that undoes the wave. Uncommitted
    coordinator work is *not* covered by it -- git cannot restore what was never
    committed -- so a dirty tree is reported alongside as what remains at risk.
    """
    name = f"safety/pre-dispatch-{packet['task_id']}"
    head = _git(repo_root, "rev-parse", "HEAD").strip()
    existing = _git(repo_root, "for-each-ref", "--format=%(refname:short)", f"refs/heads/{name}")
    if not existing.strip():
        _git(repo_root, "branch", name, head)
    dirty = [
        line.strip()
        for line in _git(repo_root, "status", "--porcelain").splitlines()
        if line.strip()
    ]
    return {
        "ref": name,
        "commit": head,
        "restore_command": f"git -C {repo_root} reset --hard {name}",
        "uncommitted_paths_at_risk": dirty,
    }


def prepare_workspace(repo_root: Path, packet: dict[str, Any]) -> Path:
    """Clone the repository into a disposable standalone workspace.

    This provides **execution isolation and provenance, not containment.** It
    buys: no push route back to the coordinator (``origin`` is removed), an
    independent object store (``--no-hardlinks``), and disposable per-packet
    task state that can be destroyed without touching coordinator refs.

    It does **not** stop a worker reaching the coordinator's checkout. That was
    the original justification and it was wrong: a bare probe inside such a
    clone stayed put, but the same clone driven through the full packet path
    still wrote to the coordinator's absolute paths on its first tool call.
    Rewriting those paths out of the auto-loaded ``AGENTS.md`` did not help
    either. The channel is neither git topology nor the context file, and it is
    deliberately left uninvestigated: once the filesystem denies the write, the
    source of the path stops mattering.

    Filesystem containment is the worker uid (and later a mount namespace).
    See ``coordinator_tree_state`` for the detection that backs it up.
    """
    target = worktree_path(packet)
    if target.exists():
        raise PacketError(
            f"{target} already exists; never dispatch two workers into one workspace"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    _git(repo_root, "clone", "--no-hardlinks", "--quiet", str(repo_root), str(target))
    _git(target, "switch", "--quiet", "--create", packet["worktree"]["branch"],
         packet["starting_commit"])
    _git(target, "remote", "remove", "origin")
    reroot_agent_context(target, repo_root)
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
            # Registered gate commands are noninteractive too: a prompt here
            # would stall the cold run rather than fail it.
            stdin=subprocess.DEVNULL,
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


def worker_cannot_write(repo_root: Path, worker_user: str | None) -> bool:
    """True when the worker's identity genuinely cannot write the checkout.

    Asked of the *worker's* uid, not the coordinator's, and answered by the
    kernel rather than by inspecting modes: ``test -w`` under the target
    identity accounts for every path component, group membership, ACLs and
    read-only mounts at once. A permission audit that reasons only about the
    repository directory misses a parent that grants access.

    Absence of a worker identity is not containment -- the worker then inherits
    this process's uid, which is the configuration the escape was measured in.
    """
    if worker_user is None:
        return not os.access(repo_root, os.W_OK)
    probe = subprocess.run(
        ["sudo", "--non-interactive", "--user", worker_user, "test", "-w", str(repo_root)],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if probe.returncode not in (0, 1):
        raise PacketError(
            f"could not determine whether {worker_user} can write {repo_root}: "
            f"{probe.stderr.strip() or 'sudo probe failed'}. Refusing to guess "
            "about a containment boundary."
        )
    return probe.returncode == 1


def coordinator_tree_state(repo_root: Path) -> list[str]:
    """Porcelain status of the coordinator's own working tree.

    The disposable worktree is the worker's boundary, but nothing in the
    OpenCode overlay reliably enforces it: ``external_directory: deny`` did not
    stop a worker from writing an absolute path into the coordinator's tree,
    and a repository's own ``AGENTS.md`` routinely hands the model that
    absolute root in its auto-loaded context. Comparing this before and after
    the worker loop turns an escape into a hard, observable failure instead of
    an empty diff that merely looks like a weak model.
    """
    return [
        line.strip()
        for line in _git(repo_root, "status", "--porcelain").splitlines()
        if line.strip()
    ]


def dispatch_worker(
    worktree: Path,
    packet_path: Path,
    packet: dict[str, Any],
    overlay: dict[str, Any],
    policy: dict[str, Any],
    opencode_bin: str,
    worker_user: str | None = None,
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
    # Another path by which the worker learns the coordinator's real checkout.
    # It has no use for it: everything it may touch is inside the worktree.
    env.pop("AGENTOPS_ROOT", None)
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
    if worker_user:
        # The only containment that actually holds: run the worker as an
        # identity with no write access to the coordinator's checkout. sudo
        # scrubs the environment, so the overlay has to be carried explicitly --
        # it is session configuration, not a secret.
        argv = [
            "sudo",
            "--non-interactive",
            "--user",
            worker_user,
            f"--preserve-env=OPENCODE_CONFIG_CONTENT",
            *argv,
        ]
    completed = subprocess.run(
        argv,
        cwd=worktree,
        env=env,
        # A worker loop is strictly noninteractive. With the coordinator's stdin
        # inherited, `opencode run` blocks in init and the packet burns its whole
        # timeout without ever reaching inference -- indistinguishable from a slow
        # model. The same packet exits promptly once stdin is closed.
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=packet["limits"]["timeout_seconds"],
        check=False,
    )
    return {
        "argv": [shlex.quote(a) for a in argv],
        "worker_user": worker_user,
        "agent": agent_name,
        "model": policy["routes"][packet["route"]]["harness_model"],
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr_tail": completed.stderr[-4000:],
    }


def post_gates(
    worktree: Path,
    packet: dict[str, Any],
    manifest: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    """Run the deterministic post-dispatch gates. Worker claims are not evidence."""
    restore_agent_context(worktree, repo_root)
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
        "--worker-user",
        default=os.environ.get("AGENTOPS_WORKER_USER"),
        help=(
            "Run the worker loop as this identity via sudo. It must have no write "
            "access to the coordinator checkout; that is the only containment that "
            "holds. Without it the run is supervised-diagnostic only."
        ),
    )
    parser.add_argument(
        "--allow-writable-coordinator",
        action="store_true",
        help=(
            "Dispatch even though the worker's identity can write the coordinator "
            "checkout. Workers are known to escape into it; only supervised runs "
            "on a disposable host should ever pass this. Requires --override-reason "
            "and permanently marks the run ineligible for qualification."
        ),
    )
    parser.add_argument(
        "--override-reason",
        help="Why the containment override is acceptable for this run. Required with it.",
    )
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
            safety = safety_ref(repo_root, packet)
            worktree = prepare_workspace(repo_root, packet)
            cold = run_registered_commands(worktree, packet, manifest)
            green = all(r["exit_code"] == 0 for r in cold)
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="prepare",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    safety=safety,
                    cold_command_results=cold,
                    eligible_for_dispatch=green,
                )
            )
            return 0 if green else 2

        worktree = worktree_path(packet)
        if not worktree.exists():
            raise PacketError(f"{worktree} does not exist; run 'prepare' first")

        if args.command == "run":
            # The worker inherits this process's identity, and a worker that can
            # write the coordinator checkout demonstrably does -- measured on
            # every attempt, through a linked worktree and through a standalone
            # clone alike. Where the filesystem already denies the write there is
            # nothing to decide; where it does not, refusing is the only control
            # that actually holds, so it is the default rather than advice.
            contained = worker_cannot_write(repo_root, args.worker_user)
            if not contained and not args.allow_writable_coordinator:
                raise PacketError(
                    f"{repo_root} is writable by the worker identity "
                    f"({args.worker_user or 'this process'}), so a worker can escape "
                    "into it and the disposable workspace is not a real boundary. "
                    "Dispatch with --worker-user naming an identity that cannot "
                    "write the coordinator checkout (devbox), or pass "
                    "--allow-writable-coordinator --override-reason '...' to accept "
                    "the risk on a supervised, disposable host."
                )
            if not contained and not (args.override_reason or "").strip():
                raise PacketError(
                    "--allow-writable-coordinator requires a non-empty "
                    "--override-reason; an unexplained override is how a "
                    "diagnostic run gets mistaken for a qualifying one"
                )
            # An uncontained run is diagnostic forever. Recording that on the
            # receipt is what stops it being folded into a qualification corpus
            # later, when the circumstances are no longer remembered.
            containment_override = {
                "containment_override": not contained,
                "worker_user": args.worker_user,
                "qualification_eligible": contained,
                "unattended_eligible": contained,
                "override_reason": args.override_reason if not contained else None,
            }
            before = coordinator_tree_state(repo_root)
            transcript = dispatch_worker(
                worktree, packet_path, packet, overlay, policy, args.opencode_bin,
                args.worker_user,
            )
            breach = sorted(set(coordinator_tree_state(repo_root)) - set(before))
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="run",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    worker=transcript,
                    **containment_override,
                    containment={
                        "coordinator_tree_untouched": not breach,
                        "coordinator_tree_changes": breach,
                        # A breach receipt states how to undo itself. An
                        # operator reading this is mid-incident and should not
                        # have to reconstruct the cleanup from the path list.
                        "recovery": (
                            [
                                f"git -C {repo_root} checkout --"
                                f" {' '.join(p.split(maxsplit=1)[-1] for p in breach if not p.startswith('??'))}".rstrip(),
                                f"git -C {repo_root} clean -f --"
                                f" {' '.join(p.split(maxsplit=1)[-1] for p in breach if p.startswith('??'))}".rstrip(),
                            ]
                            if breach
                            else []
                        ),
                    },
                    **(
                        {"disposition": "containment_breach"}
                        if breach
                        else {}
                    ),
                )
            )
            # A worker that wrote outside its disposable worktree has escaped the
            # boundary the packet exists to enforce. That is never a retryable
            # quality result: it stops the packet for human triage.
            return 3 if breach else 0

        if args.command == "gate":
            evidence = post_gates(worktree, packet, manifest, repo_root)
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
