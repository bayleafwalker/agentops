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
import grp
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

POLICY_RELATIVE = Path("templates/dispatch/hybrid/hybrid-dispatch.v1.json")
WORKER_CONFIG_RELATIVE = Path("templates/dispatch/hybrid/opencode.hybrid.json")
LEGACY_PACKET_SCHEMA_VERSION = "agentops-task/v1"
PACKET_SCHEMA_VERSION = "agentops-task/v2"
SUPPORTED_PACKET_SCHEMA_VERSIONS = (
    LEGACY_PACKET_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
)
GATE_SET_HASH_SCHEMA_VERSIONS = {
    LEGACY_PACKET_SCHEMA_VERSION: "agentops-hybrid-gate-set/v1",
    PACKET_SCHEMA_VERSION: "agentops-hybrid-gate-set/v2",
}
ACCEPTANCE_PROPERTY_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]*\Z")
AGENTOPS_ROOT = Path(
    os.environ.get("AGENTOPS_ROOT", "/projects/dev/agentops")
).resolve()

REQUIRED_PACKET_FIELDS = (
    "schema_version",
    "task_id",
    "repo_id",
    "sprint_item",
    "route",
    "task_class",
    "risk",
    "oracle",
    "starting_commit",
    "purpose",
    "readable_context_paths",
    "writable_patch_paths",
    "protected_paths",
    "required_outcomes",
    "acceptance_properties",
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
    packet_schema_version = packet["schema_version"]
    if packet_schema_version not in SUPPORTED_PACKET_SCHEMA_VERSIONS:
        raise PacketError(
            "packet schema_version must be one of "
            f"{', '.join(SUPPORTED_PACKET_SCHEMA_VERSIONS)}, got {packet_schema_version!r}"
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
    if manifest.get("repo_id") != packet["repo_id"]:
        raise PacketError(
            "packet.repo_id must match the repository dispatch manifest; a packet "
            "cannot self-label itself as an admitted pilot repository"
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
    repository_scope = policy["routes"][route].get("repository_scope")
    if repository_scope is not None:
        if (
            not isinstance(repository_scope, dict)
            or repository_scope.get("kind") != "project"
            or not isinstance(repository_scope.get("project_ref"), str)
            or not repository_scope.get("project_ref").strip()
            or not isinstance(repository_scope.get("repositories"), list)
            or not repository_scope["repositories"]
            or any(not isinstance(repo_id, str) or not repo_id.strip() for repo_id in repository_scope["repositories"])
        ):
            raise PacketError(f"route {route!r} has an invalid repository scope")
        if packet["repo_id"] not in repository_scope["repositories"]:
            raise PacketError(
                f"route {route!r} is scoped to a different project repository"
            )

    if packet.get("task_class") != "mechanical_implementation":
        raise PacketError("worker dispatch requires task_class mechanical_implementation")
    if packet.get("risk") != "low":
        raise PacketError("worker dispatch requires risk low")
    oracle = packet.get("oracle") or {}
    starts_red = oracle.get("starts_red") or []
    if not isinstance(starts_red, list) or any(not isinstance(c, str) for c in starts_red):
        raise PacketError("oracle.starts_red must be a list of command ids")
    unknown = [c for c in starts_red if c not in packet.get("allowed_command_ids", [])]
    if unknown:
        raise PacketError(
            f"oracle.starts_red names commands the packet cannot run: {', '.join(sorted(unknown))}"
        )
    if oracle.get("ownership") != "externally_defined" or oracle.get("worker_may_modify") is not False:
        raise PacketError(
            "worker dispatch requires an externally defined oracle that the worker cannot modify"
        )

    if packet["network_policy"] != "disabled":
        raise PacketError("network_policy must be 'disabled' for worker dispatch")

    commit = packet["starting_commit"]
    if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
        raise PacketError("starting_commit must be a full lowercase 40-hex commit")

    item_ref = packet["sprint_item"].get("ref", "")
    if "#" not in item_ref:
        raise PacketError("sprint_item.ref must be a sprintctl repo#id reference")
    item_repo, _, item_id = item_ref.partition("#")
    if item_repo != packet["repo_id"] or not item_id.isdigit() or int(item_id) < 1:
        raise PacketError("sprint_item.ref must name the packet repository and a positive item id")
    claim_id = packet["sprint_item"].get("claim_id")
    if isinstance(claim_id, bool) or not isinstance(claim_id, int) or claim_id < 1:
        raise PacketError("sprint_item.claim_id must be a positive integer")
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
    if not packet["allowed_command_ids"]:
        raise PacketError("allowed_command_ids must name at least one registered gate")
    for command_id in packet["allowed_command_ids"]:
        if command_id not in commands:
            raise PacketError(
                f"command id {command_id!r} is not registered in the repository "
                "hybrid.commands map"
            )
    acceptance_properties = packet.get("acceptance_properties") or []
    if not acceptance_properties:
        raise PacketError(
            "acceptance_properties must define at least one coordinator-authored falsifying condition"
        )
    requirement_ids: set[str] = set()
    for acceptance in acceptance_properties:
        command_id = acceptance.get("command_id")
        if command_id not in packet["allowed_command_ids"]:
            raise PacketError(
                f"acceptance property command {command_id!r} is not granted by allowed_command_ids"
            )
        if not acceptance.get("requirement") or not acceptance.get("fails_when"):
            raise PacketError(
                "each acceptance property must name its requirement and the incorrect behaviour it falsifies"
            )
        if packet_schema_version == PACKET_SCHEMA_VERSION:
            requirement_id = acceptance.get("id")
            if not isinstance(requirement_id, str) or not requirement_id:
                raise PacketError("each v2 acceptance property must declare a stable id")
            if not ACCEPTANCE_PROPERTY_ID_RE.fullmatch(requirement_id):
                raise PacketError(
                    "each v2 acceptance property id must start with a letter and use only letters, digits, '.', '_', or '-'"
                )
            if requirement_id in requirement_ids:
                raise PacketError(
                    f"acceptance property id {requirement_id!r} is duplicated within the packet"
                )
            requirement_ids.add(requirement_id)
        elif "id" in acceptance:
            raise PacketError("v1 acceptance properties cannot declare v2 stable ids")

    limits = packet["limits"]
    ceiling = hybrid.get("max_timeout_seconds")
    if ceiling and limits["timeout_seconds"] > ceiling:
        raise PacketError(
            f"limits.timeout_seconds {limits['timeout_seconds']} exceeds the "
            f"repository ceiling {ceiling}"
        )

    max_cost = limits.get("max_cost_usd")
    if isinstance(max_cost, bool) or not isinstance(max_cost, (int, float)) or max_cost <= 0:
        raise PacketError("limits.max_cost_usd must be a positive explicit packet cap")
    cost_ceiling = hybrid.get("max_cost_usd")
    if cost_ceiling and max_cost > cost_ceiling:
        raise PacketError(
            f"limits.max_cost_usd {limits['max_cost_usd']} exceeds the "
            f"repository ceiling {cost_ceiling}"
        )
    soft_tokens = limits.get("soft_token_ceiling")
    hard_tokens = limits.get("hard_token_ceiling")
    repo_soft_tokens = hybrid.get("soft_token_ceiling")
    repo_hard_tokens = hybrid.get("hard_token_ceiling")
    if not isinstance(soft_tokens, int) or not isinstance(hard_tokens, int):
        raise PacketError("limits must declare integer soft_token_ceiling and hard_token_ceiling")
    if soft_tokens <= 0 or hard_tokens <= soft_tokens:
        raise PacketError("hard_token_ceiling must exceed a positive soft_token_ceiling")
    if repo_soft_tokens and soft_tokens > repo_soft_tokens:
        raise PacketError("packet soft_token_ceiling exceeds the repository ceiling")
    if repo_hard_tokens and hard_tokens > repo_hard_tokens:
        raise PacketError("packet hard_token_ceiling exceeds the repository ceiling")

    churn = context_churn_limits(packet)
    required_churn = {
        "max_repeated_reads_per_path",
        "max_reasoning_steps_without_mutation",
        "max_identical_context_tokens",
        "handoff_when_candidate_ready",
    }
    if set(churn) != required_churn:
        raise PacketError("context_churn must declare the exact supported stall limits")
    for name, maximum in (
        ("max_repeated_reads_per_path", 12),
        ("max_reasoning_steps_without_mutation", 24),
    ):
        value = churn[name]
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise PacketError(f"context_churn.{name} must be between 1 and {maximum}")
    identical_tokens = churn["max_identical_context_tokens"]
    if isinstance(identical_tokens, bool) or not isinstance(identical_tokens, int) or identical_tokens < 1000:
        raise PacketError("context_churn.max_identical_context_tokens must be >= 1000")
    if churn["handoff_when_candidate_ready"] is not True:
        raise PacketError("context_churn.handoff_when_candidate_ready must be true")

    max_attempts = policy["routes"][route].get("max_attempts", 1)
    if packet.get("attempt", 1) > max_attempts:
        raise PacketError(
            f"attempt {packet.get('attempt')} exceeds max_attempts {max_attempts} "
            f"for route {route!r}; reroute or escalate explicitly"
        )

    return list(policy["gates"]["pre"])


def qualification_state(policy: dict[str, Any], packet: dict[str, Any]) -> str:
    """Label a packet narrowly; availability never widens pilot qualification."""
    qualification = policy["qualification"]
    if qualification == "none":
        return "unqualified"
    if (
        packet["repo_id"] in qualification["repositories"]
        and packet["route"] in qualification["routes"]
        and policy["routes"][packet["route"]]["harness_model"] in qualification["models"]
    ):
        return f"named_pilot:{qualification['pilot_id']}"
    return qualification["default"]


RESERVATION_STALE_AFTER_ENV = "SPRINTCTL_RESERVATION_STALE_AFTER_HOURS"
DEFAULT_RESERVATION_STALE_AFTER = timedelta(hours=4)


def reservation_stale_after() -> timedelta:
    """How idle a reservation may be and still authorize a dispatch.

    Mirrors sprintctl's own horizon and reads the same environment variable, so
    an operator who widens it there does not have to remember to widen it twice.
    """
    raw = os.environ.get(RESERVATION_STALE_AFTER_ENV)
    if raw:
        try:
            hours = float(raw)
        except ValueError:
            return DEFAULT_RESERVATION_STALE_AFTER
        if hours > 0:
            return timedelta(hours=hours)
    return DEFAULT_RESERVATION_STALE_AFTER


def verify_live_coordinator_claim(
    repo_root: Path, packet: dict[str, Any], sprintctl_bin: str,
) -> dict[str, Any]:
    """Read and validate the exact served reservation that authorizes this packet.

    The worker never receives this authority.  This coordinator-side check
    prevents a frozen packet from being dispatched after its authorization went
    stale, moved to a different actor, or ceased to cover the intended item.

    **Migrated from ``sprintctl claim`` (2026-08-23).**  That command no longer
    exists: sprintctl removed credential-bearing claims in favour of advisory
    reservations, so every packet on every host failed here regardless of its
    contents.  The unit tests did not catch it because they mocked the old
    payload shape, which is the failure mode of testing a CLI you never call.

    The two are not a rename.  A claim was a lease with an expiry; a reservation
    is explicitly "a coordination signal, not a lease" and carries no expiry at
    all.  The expiry check is therefore replaced by a **staleness** check on
    ``last_activity_at``, matching sprintctl's own 4-hour horizon: an
    authorization nobody has touched in that long is not evidence that anyone is
    still coordinating this work, and ``sprintctl reservation touch`` refreshes
    it deliberately rather than by accident.  ``sprint_item.claim_id`` and
    ``claim_actor`` keep their names so frozen packets stay readable; they now
    hold the reservation id and its actor.
    """
    item_ref = packet["sprint_item"]["ref"]
    _, _, item_text = item_ref.partition("#")
    item_id = int(item_text)
    expected_claim_id = packet["sprint_item"]["claim_id"]
    expected_actor = packet["sprint_item"]["claim_actor"]
    try:
        completed = subprocess.run(
            [sprintctl_bin, "reservation", "list", "--item-id", str(item_id),
             "--active-only", "--json"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise PacketError(f"cannot execute sprintctl reservation read: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise PacketError(f"served reservation read failed: {detail or completed.returncode}")
    try:
        reservations = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PacketError("served reservation read returned invalid JSON") from exc
    if not isinstance(reservations, list):
        raise PacketError("served reservation read returned a non-list payload")
    matching = [
        row for row in reservations
        if isinstance(row, dict) and row.get("id") == expected_claim_id
    ]
    if len(matching) != 1:
        raise PacketError(
            f"served reservation {expected_claim_id} is not active for item #{item_id}"
        )
    reservation = matching[0]
    if reservation.get("work_item_id") != item_id:
        raise PacketError(
            f"served reservation {expected_claim_id} does not cover item #{item_id}"
        )
    if reservation.get("actor") != expected_actor:
        raise PacketError(
            f"served reservation {expected_claim_id} is not held by {expected_actor!r}"
        )
    if reservation.get("state") != "active":
        raise PacketError(f"served reservation {expected_claim_id} is not active")
    last_activity_at = reservation.get("last_activity_at")
    if not isinstance(last_activity_at, str):
        raise PacketError(
            f"served reservation {expected_claim_id} has no last_activity_at"
        )
    try:
        touched = datetime.fromisoformat(last_activity_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PacketError(
            f"served reservation {expected_claim_id} has an invalid last_activity_at"
        ) from exc
    if touched.tzinfo is None:
        touched = touched.replace(tzinfo=timezone.utc)
    idle = datetime.now(timezone.utc) - touched
    if idle > reservation_stale_after():
        raise PacketError(
            f"served reservation {expected_claim_id} has been idle for "
            f"{idle.total_seconds() / 3600:.1f}h; touch it deliberately "
            f"(sprintctl reservation touch) or reserve the item again"
        )
    return {
        "claim_id": expected_claim_id,
        "work_item_id": item_id,
        "agent": expected_actor,
        "last_activity_at": last_activity_at,
        "idle_seconds": int(idle.total_seconds()),
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def build_overlay(
    packet: dict[str, Any],
    manifest: dict[str, Any],
    policy: dict[str, Any],
    base_config: dict[str, Any],
    model_override: str | None = None,
) -> dict[str, Any]:
    """Build the session-only OpenCode permission overlay for one packet.

    Noninteractive ``opencode run`` refuses permissions left at ``ask``, and
    ``--auto`` is far too broad for a frozen packet, so every permission is
    resolved here to an explicit allow or deny.

    The qualified OpenCode implementation profile constrains the shape. Its
    current devbox observation was measured against
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

    # OpenCode evaluates matching permission patterns in insertion order and
    # the last match wins.  Put the fallback first so an exact registered
    # command can override it; appending "*" last withholds the bash tool even
    # when an earlier command entry says allow.
    bash: dict[str, str] = {"*": "deny"}
    for command_id in packet["allowed_command_ids"]:
        bash[commands[command_id]] = "allow"

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

    model = model_override or base_agent["model"]
    overlay = {
        "$schema": base_config.get("$schema", "https://opencode.ai/config.json"),
        "model": model,
        # The session overlay replaces the worker's config, so the route's
        # declared provider registry has to travel or a model alias such as
        # local3090/worker-fast cannot resolve. It travels narrowed: the
        # credential is replaced with a placeholder and unknown keys are
        # dropped. See worker_provider_registry.
        "provider": worker_provider_registry(base_config),
        "permission": dict(permission),
        "agent": {
            agent_name: {
                **base_agent,
                "model": model,
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


#: The sudo flags that make a worker contained, defined once so the
#: qualification probe and production dispatch cannot drift apart. They did:
#: --set-home was added to dispatch and not to the probe, so every profile
#: probe measured the CLI under the coordinator's HOME while dispatch ran under
#: the worker's, and the qualification evidence stopped describing production.
CONTAINED_SUDO_FLAGS: tuple[str, ...] = ("--non-interactive", "--set-home")

#: What the worker's provider registry is allowed to carry, per provider and
#: inside ``options``. Deny-by-default: an unrecognised key is dropped, not
#: passed on, so adding a secret to the coordinator's config cannot leak by
#: omission.
_PROVIDER_KEYS: tuple[str, ...] = ("npm", "name", "models")
_PROVIDER_OPTION_KEYS: tuple[str, ...] = ("baseURL",)

#: openai-compatible clients will not construct without some apiKey string.
#: Forcing this one means a provider that needs a real credential fails loudly
#: at the worker instead of quietly succeeding with the coordinator's.
WORKER_PLACEHOLDER_API_KEY = "local-only"


def worker_provider_registry(base_config: dict[str, Any]) -> dict[str, Any]:
    """The provider registry a worker needs, with no credential in it.

    A model alias such as ``local3090/worker-fast`` cannot resolve unless the
    overlay carries the provider that defines it: ``OPENCODE_CONFIG_CONTENT``
    replaces the worker's configuration rather than merging with it, and the
    worker has no configuration of its own -- probed 2026-08-24, its home does
    not exist. So the registry has to travel.

    What must not travel is ``options.apiKey``. The same probe established that
    the worker authenticates with no credential file at all, which makes this
    the only credential-shaped value that ever crosses the boundary, and the
    worker's own declared contract is "no authority, credentials, network, or
    oracle ownership".
    """
    registry: dict[str, Any] = {}
    for name, provider in (base_config.get("provider") or {}).items():
        if not isinstance(provider, dict):
            continue
        kept = {k: provider[k] for k in _PROVIDER_KEYS if k in provider}
        options = provider.get("options")
        if isinstance(options, dict):
            kept_options = {
                k: options[k] for k in _PROVIDER_OPTION_KEYS if k in options
            }
            kept_options["apiKey"] = WORKER_PLACEHOLDER_API_KEY
            kept["options"] = kept_options
        registry[name] = kept
    return registry


def worker_argv(
    opencode_bin: str,
    agent_name: str,
    message: str,
    packet_path: Path,
    worker_user: str | None,
) -> list[str]:
    """The exact command one contained worker loop runs.

    Extracted so it can be asserted over without running anything. Note what
    ``--set-home`` does and does not do: the coordinator's opencode auth store
    and ssh directory are already unreadable by the worker on filesystem
    permissions, so this closes no leak. It points the worker's HOME at its own
    rather than at one it cannot read.
    """
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
    if not worker_user:
        return argv
    return [
        "sudo",
        *CONTAINED_SUDO_FLAGS,
        "--user",
        worker_user,
        "--preserve-env=OPENCODE_CONFIG_CONTENT",
        *argv,
    ]


def overlay_hash(overlay: dict[str, Any]) -> str:
    # Permission maps are ordered policy: OpenCode applies the last matching
    # rule.  Sorting keys would make behaviorally different overlays share a
    # digest, so preserve the insertion order used for dispatch.
    payload = json.dumps(overlay, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def context_churn_limits(packet: dict[str, Any]) -> dict[str, Any]:
    """Resolve additive v1 churn controls without breaking older packets."""
    return packet.get("context_churn") or {
        "max_repeated_reads_per_path": 4,
        # Every workspace the loop builds is a full clone of the repository, and
        # eight steps is not enough room to orient in one before writing.
        "max_reasoning_steps_without_mutation": 12,
        "max_identical_context_tokens": 250000,
        "handoff_when_candidate_ready": True,
    }


def gate_set_hash_schema_version(packet: dict[str, Any]) -> str:
    """Return the version needed to compare this receipt's gate-set hash."""
    try:
        return GATE_SET_HASH_SCHEMA_VERSIONS[packet["schema_version"]]
    except KeyError as exc:
        raise PacketError(f"unsupported packet schema_version {packet.get('schema_version')!r}") from exc


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


def worker_shared_gid(worker_user: str | None) -> int | None:
    """The gid of the one group the coordinator and the contained worker share.

    Setting the group-write bit is useless unless the group is one the worker is
    actually in, and the clone lands owned by the coordinator's *primary* group,
    which it is not. Measured on devbox 2026-08-23: workspace ``agent:agent``
    mode 775, worker in ``agentworker`` and ``agentdispatch`` -- so every write
    the worker attempted inside its own workspace failed ``PermissionDenied``
    while the mode looked correct.
    """
    if not worker_user:
        return None
    try:
        worker = pwd.getpwnam(worker_user)
    except KeyError:
        return None
    worker_gids = {worker.pw_gid}
    mine = set(os.getgroups())
    for group in grp.getgrall():
        if worker_user in group.gr_mem:
            worker_gids.add(group.gr_gid)
    shared = sorted(worker_gids & mine)
    return shared[0] if shared else None


def share_workspace_with_group(workspace: Path, worker_user: str | None = None) -> None:
    """Make the freshly cloned workspace writable by its owning group.

    The workspace root is setgid and group-shared precisely so the coordinator
    and the worker can both write it, but setgid only propagates group
    *ownership* -- the mode still comes from the creating process's umask. The
    clone is made by the coordinator at its own umask, so without this every
    file lands ``0644 coordinator:shared`` and the worker, which is in the
    group but is not the owner, can write none of it.

    That state is worth naming because it is silent and looks like something
    else: measured on devbox 2026-07-28, a correctly moded workspace root still
    left the contained worker unable to edit the clone it was dispatched into.
    Its first edit fails with EACCES inside its *own* workspace, which reads
    exactly like the containment boundary working -- and it is why the
    containment probe alone (``test -w`` on the coordinator checkout) is not
    sufficient evidence that a contained run can do anything.

    Inert where no worker split exists: the workspace is then owned by the
    coordinator's own group and nothing else is in it.
    """
    gid = worker_shared_gid(worker_user)
    for path in [workspace, *workspace.rglob("*")]:
        try:
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                continue
            # Group ownership first: the write bit means nothing on a group the
            # worker is not in, which is the state that produced a silent
            # 1.07M-token run where every edit was denied inside the worker's
            # own workspace.
            if gid is not None:
                os.chown(path, -1, gid)
            path.chmod(stat.S_IMODE(mode) | stat.S_IWGRP)
        except OSError:
            # A single unreadable or racing path is not worth failing the whole
            # prepare over; the worker's first write would surface it, and the
            # group-write round trip is asserted by check-worker-containment.sh.
            continue


def worker_can_write_workspace(workspace: Path, worker_user: str | None) -> tuple[bool, str]:
    """Prove the contained worker can actually write the workspace it is given.

    This is the check whose absence cost a whole run. On 2026-08-23 a worker went
    straight for the right three files, was denied on every one, spent 1.07M
    tokens probing why, and hit its token ceiling -- while prepare reported a
    green cold gate and run exited 0. Nothing in the receipt said "the worker
    could not write", because nothing had asked.

    The decisive check is static and needs no privileges: the workspace's group
    must be one the worker belongs to, and the group-write bit must be set.
    That is exactly the state that failed, and it is knowable by stat alone.

    The dynamic probe is a confirmation, not the check, because the coordinator
    may run only a narrow allowlist as the worker -- on devbox that is opencode
    and ``test``. A probe that cannot run is *skipped*, never treated as a
    denial: refusing to dispatch because we lack sudo rights to ask would fail
    the run for a reason that has nothing to do with the workspace.
    """
    if not worker_user:
        return True, "no worker user: writes happen as the coordinator"

    gid = worker_shared_gid(worker_user)
    try:
        info = workspace.lstat()
    except OSError as exc:
        return False, f"cannot stat {workspace}: {exc}"
    if gid is None:
        return False, (
            f"{worker_user} shares no group with this process, so no mode can make "
            f"{workspace} writable by it"
        )
    if info.st_gid != gid:
        return False, (
            f"{workspace} is group {info.st_gid}, not {gid}, which is the group "
            f"{worker_user} is in: the group-write bit would be inert"
        )
    if not stat.S_IMODE(info.st_mode) & stat.S_IWGRP:
        return False, f"{workspace} is not group-writable, so {worker_user} cannot write it"

    test_bin = shutil.which("test", path=os.defpath) or shutil.which("test")
    if test_bin is None:
        return True, f"{workspace} is group-writable by {worker_user} (probe unavailable)"
    try:
        completed = subprocess.run(
            ["sudo", "--non-interactive", "--user", worker_user, test_bin, "-w", str(workspace)],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return True, f"group ownership correct; probe could not run ({exc})"
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0 and _probe_was_refused(stderr):
        return True, f"group ownership correct; probe not permitted ({stderr[-160:]})"
    if completed.returncode != 0:
        return False, (
            f"{worker_user} cannot write {workspace} despite correct group and mode: "
            f"{stderr[-300:] or completed.returncode}"
        )
    return True, f"{worker_user} can write the workspace (probed)"


def _probe_was_refused(stderr: str) -> bool:
    """Tell "sudo would not let me ask" apart from "the answer is no"."""
    lowered = stderr.lower()
    return any(
        marker in lowered
        for marker in ("a password is required", "not allowed to execute", "may not run")
    )


def workspace_is_retry_reuse(packet: dict[str, Any]) -> bool:
    """True when an existing workspace is this packet's own, left by attempt N-1.

    Narrow on purpose: the packet must *declare* a retry, and the standing
    workspace must be a git work tree already on the branch this packet names.
    Anything else -- a stale directory, someone else's branch, a first attempt --
    is still the two-workers case and is still refused.
    """
    if int(packet.get("attempt", 1) or 1) <= 1:
        return False
    target = worktree_path(packet)
    if not (target / ".git").exists():
        return False
    try:
        branch = _git(target, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except Exception:  # noqa: BLE001 - an unreadable work tree is not a reusable one
        return False
    return branch == packet["worktree"]["branch"]


def prepare_workspace(
    repo_root: Path, packet: dict[str, Any], worker_user: str | None = None,
) -> Path:
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
        # The guard is about two workers at once. It also blocked the one thing
        # L-4 needs -- a packet coming back to its own workspace for a second
        # attempt -- which is what made V5-M2 the packet that could not unblock
        # its own retry. A declared retry, on the workspace already standing on
        # this packet's own branch, is the one case that is not a second worker.
        if not workspace_is_retry_reuse(packet):
            raise PacketError(
                f"{target} already exists; never dispatch two workers into one workspace"
            )
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        _git(repo_root, "clone", "--no-hardlinks", "--quiet", str(repo_root), str(target))
        _git(target, "switch", "--quiet", "--create", packet["worktree"]["branch"],
             packet["starting_commit"])
        _git(target, "remote", "remove", "origin")
    reroot_agent_context(target, repo_root)
    share_workspace_with_group(target, worker_user)
    writable, detail = worker_can_write_workspace(target, worker_user)
    if not writable:
        raise PacketError(f"prepared workspace is not writable by the worker: {detail}")
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


def check_oracle_attainable(
    repo_root: Path, packet: dict[str, Any], manifest: dict[str, Any],
) -> list[str]:
    """Freeze-time check that a declared-red oracle can actually be satisfied.

    ``validate`` asks whether acceptance properties *discriminate*. It never asks
    whether they can be *met*, and three of the five defects behind a seven-run
    packet were exactly that gap: an oracle that demanded a seam the packet did
    not state, an oracle scoped to three items when the packet covered one, and
    an oracle that did not exist at ``starting_commit`` at all.

    This is L-2(a), the cheap half: run each ``starts_red`` command at the
    starting commit in a throwaway checkout and require it to be **red for a
    reason other than absence**. Exit 127 is not a failing test, it is a missing
    one, and accepting it let a worker be judged by a gate that never ran.

    The other half -- proving the failure depends only on files the packet
    declares -- is ``check_oracle_reads`` (L-2(b), read-trace form) plus
    ``check_oracle_reference`` (L-2(b), reference-overlay form).
    """
    starts_red = (packet.get("oracle") or {}).get("starts_red") or []
    if not starts_red:
        return []
    commands = manifest["hybrid"]["commands"]
    faults: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-attainable-") as tmp:
        checkout = Path(tmp) / "at-starting-commit"
        try:
            _git(repo_root, "clone", "--no-hardlinks", "--quiet", str(repo_root), str(checkout))
            _git(checkout, "checkout", "--quiet", "--detach", packet["starting_commit"])
        except Exception as exc:  # noqa: BLE001 - reported, never raised past here
            return [f"could not check out {packet['starting_commit']} to test the oracle: {exc}"]
        for command_id in starts_red:
            command = commands.get(command_id)
            if command is None:
                faults.append(f"{command_id} is not a registered command")
                continue
            completed = subprocess.run(
                command, shell=True, cwd=checkout, stdin=subprocess.DEVNULL,
                capture_output=True, text=True, check=False,
                timeout=packet["limits"]["timeout_seconds"],
            )
            if completed.returncode == 127:
                faults.append(
                    f"{command_id} exits 127 at {packet['starting_commit'][:12]}: the oracle does "
                    "not exist in the workspace the worker will be given"
                )
            elif completed.returncode == 0:
                faults.append(
                    f"{command_id} already passes at {packet['starting_commit'][:12]}: an oracle "
                    "that cannot fail proves nothing about what the worker does to it"
                )
    return faults


#: Paths the read-trace ignores even though they are inside the checkout.
#: Everything here is either the version-control or interpreter machinery that
#: any command touches regardless of what it tests (``.git/``, bytecode caches,
#: a local virtualenv) or the test runner's own configuration discovery
#: (pyproject/pytest/tox/setup.cfg, conftest.py), which a runner reads before
#: it knows which test it is running. None of it is a seam the packet could
#: have declared, so flagging it would only teach packets to declare
#: ``pyproject.toml`` as context. The oracle's own test files -- the ones the
#: command names on its command line -- are exempted separately in
#: ``_oracle_named_paths``: that a test reads itself is not a dependency.
ORACLE_READ_TRACE_EXEMPT_PREFIXES = (".git/", "__pycache__/", ".venv/")
ORACLE_READ_TRACE_EXEMPT_FILES = (
    "pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini", "conftest.py",
)
#: strace's own file-syscall class. A hand-maintained list silently misses
#: whatever a platform names differently; the class is what strace keeps current.
ORACLE_READ_TRACE_SYSCALLS = "%file"
_STRACE_OPEN_RE = re.compile(
    r'^(?:\[pid\s+\d+\]\s*|\d+\s+)?(openat|open)\((?:([^,]*),\s*)?"([^"]*)",\s*([A-Z_|0-9]+)'
    r'[^)]*\)\s*=\s*(-?\d+)'
)


def _oracle_named_paths(checkout: Path, command: str) -> set[Path]:
    """Files or directories the command names on its own command line."""
    named: set[Path] = set()
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for token in tokens:
        # ``tests/test_x.py::TestCase::test_y`` names a file; strip the selector.
        candidate = (checkout / token.split("::", 1)[0])
        if candidate.exists():
            named.add(Path(os.path.realpath(candidate)))
    return named


def _is_exempt_read(rel: str, resolved: Path, named: set[Path]) -> bool:
    if rel in ORACLE_READ_TRACE_EXEMPT_FILES or rel.startswith(ORACLE_READ_TRACE_EXEMPT_PREFIXES):
        return True
    if "__pycache__" in Path(rel).parts:
        return True
    return any(resolved == n or n in resolved.parents for n in named)


def parse_strace_reads(trace_text: str, checkout: Path) -> set[str]:
    """Paths inside ``checkout`` that the traced command opened for reading.

    Only *successful* opens that are not write-only count: a failed ``openat``
    is a probe, not a read, and ``O_WRONLY`` is the oracle writing its own
    cache. Directories are dropped -- a runner walks the tree to find tests,
    and that walk is not a dependency on anything in it.
    """
    root = Path(os.path.realpath(checkout))
    reads: set[str] = set()
    for line in trace_text.splitlines():
        match = _STRACE_OPEN_RE.match(line)
        if match is None:
            continue
        syscall, dirfd, raw_path, flags, result = match.groups()
        if int(result) < 0 or "O_WRONLY" in flags.split("|"):
            continue
        # ``openat``'s first argument is a directory fd, and a relative path is
        # relative to *that*, not to the cwd. shutil.rmtree walks with such fds,
        # so tempfile.TemporaryDirectory cleanup emits
        # ``openat(3, "coordinator", ...)`` -- and resolving it against the
        # checkout invented a read of a path that does not exist there. Every
        # Python oracle in this repository uses TemporaryDirectory, so this
        # false-positived all of them and made oracle_reads_within_paths
        # unobtainable. AT_FDCWD is the one fd that does mean the cwd.
        if (
            not raw_path.startswith("/")
            and syscall == "openat"
            and (dirfd or "").strip() != "AT_FDCWD"
        ):
            continue
        resolved = Path(os.path.realpath(root / raw_path if not raw_path.startswith("/") else raw_path))
        if resolved == root or root not in resolved.parents or resolved.is_dir():
            continue
        reads.add(resolved.relative_to(root).as_posix())
    return reads


def trace_oracle_reads(
    checkout: Path,
    packet: dict[str, Any],
    commands: dict[str, str],
    strace_bin: str | None,
    allow_untraced: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    """L-2(b), read-trace half: every file a ``starts_red`` oracle reads at
    ``starting_commit`` must be inside the paths the packet declares.

    An oracle that reads a file the worker may neither see nor write is an
    oracle that demands an unstated seam, or covers work the packet does not
    contain -- two of the five defects behind the seven-run packet. The packet
    cannot be judged by a test whose inputs it cannot name.

    Fails closed without ``strace``: a check that silently did not run is
    indistinguishable from one that passed. ``allow_untraced`` records the gap
    on the report as ``"skipped:untraced"`` and never as ``True``.
    """
    starts_red = (packet.get("oracle") or {}).get("starts_red") or []
    report: dict[str, Any] = {
        "oracle_reads_within_paths": None,
        "read_trace": None,
        "reads_outside_declared_paths": {},
    }
    if not starts_red:
        return [], report
    if strace_bin is None:
        if allow_untraced:
            report["oracle_reads_within_paths"] = "skipped:untraced"
            report["read_trace"] = "skipped:untraced"
            return [], report
        return [
            "strace is not on PATH, so the oracle's reads cannot be traced; install "
            "strace or pass --allow-untraced-oracle to record the gap instead of "
            "closing it"
        ], report
    declared = list(packet.get("readable_context_paths") or []) + list(
        packet.get("writable_patch_paths") or []
    )
    faults: list[str] = []
    outside: dict[str, list[str]] = {}
    for command_id in starts_red:
        command = commands.get(command_id)
        if command is None:
            continue  # already a fault from check_oracle_attainable
        named = _oracle_named_paths(checkout, command)
        with tempfile.NamedTemporaryFile(prefix="agentops-oracle-trace-", suffix=".log", delete=False) as handle:
            trace_path = Path(handle.name)
        try:
            subprocess.run(
                [strace_bin, "-f", "-qq", "-e", f"trace={ORACLE_READ_TRACE_SYSCALLS}",
                 "-o", str(trace_path), "sh", "-c", command],
                cwd=checkout, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                check=False, timeout=packet["limits"]["timeout_seconds"],
            )
            trace_text = trace_path.read_text(encoding="utf-8", errors="replace")
        finally:
            trace_path.unlink(missing_ok=True)
        offenders = sorted(
            rel for rel in parse_strace_reads(trace_text, checkout)
            if not _is_exempt_read(rel, Path(os.path.realpath(checkout / rel)), named)
            and not _matches_any(rel, declared)
        )
        if offenders:
            outside[command_id] = offenders
            faults.append(
                f"{command_id} oracle reads outside declared paths at "
                f"{packet['starting_commit'][:12]}: {', '.join(offenders)}"
            )
    report["oracle_reads_within_paths"] = not outside
    report["read_trace"] = True
    report["reads_outside_declared_paths"] = outside
    return faults, report


def check_oracle_reads(
    repo_root: Path, packet: dict[str, Any], manifest: dict[str, Any],
    allow_untraced: bool = False,
) -> tuple[list[str], dict[str, Any]]:
    """``trace_oracle_reads`` against a throwaway checkout of ``starting_commit``."""
    starts_red = (packet.get("oracle") or {}).get("starts_red") or []
    if not starts_red:
        return [], {"oracle_reads_within_paths": None, "read_trace": None,
                    "reads_outside_declared_paths": {}}
    with tempfile.TemporaryDirectory(prefix="agentops-attainable-") as tmp:
        checkout = Path(tmp) / "at-starting-commit"
        try:
            _git(repo_root, "clone", "--no-hardlinks", "--quiet", str(repo_root), str(checkout))
            _git(checkout, "checkout", "--quiet", "--detach", packet["starting_commit"])
        except Exception as exc:  # noqa: BLE001 - reported, never raised past here
            return [f"could not check out {packet['starting_commit']} to trace the oracle: {exc}"], {}
        return trace_oracle_reads(
            checkout, packet, manifest["hybrid"]["commands"], shutil.which("strace"), allow_untraced,
        )


def overlay_reference_patch(
    checkout: Path,
    packet: dict[str, Any],
    commands: dict[str, str],
    patch_path: Path | None,
) -> tuple[list[str], dict[str, Any]]:
    """L-2(b), reference-overlay half: a change confined to
    ``writable_patch_paths`` must turn every ``starts_red`` oracle green.

    The read-trace half proves the oracle reads nothing undeclared; it cannot
    prove the oracle is *satisfiable* by the files the worker may write. An
    oracle that demands a seam outside ``writable_patch_paths`` (defect 3) or
    that covers more work than the packet holds (defect 4) passes the trace and
    still cannot be met. Applying a coordinator-supplied reference patch at
    ``starting_commit`` and requiring green closes that gap at freeze time.

    ``patch_path`` is the already-resolved location of the unified diff (it
    lives in the coordinator's tree, not at ``starting_commit``). Absent, the
    check is recorded as ``"skipped:no-reference"`` -- never ``True``.
    """
    starts_red = (packet.get("oracle") or {}).get("starts_red") or []
    report: dict[str, Any] = {
        "oracle_satisfiable_within_paths": None,
        "reference_patch": None,
        "red_after_reference": [],
    }
    if not starts_red:
        return [], report
    if patch_path is None:
        report["oracle_satisfiable_within_paths"] = "skipped:no-reference"
        return [], report
    report["reference_patch"] = (packet.get("oracle") or {}).get("reference_patch")
    if not patch_path.is_file():
        report["oracle_satisfiable_within_paths"] = False
        return [f"oracle.reference_patch {report['reference_patch']!r} is not a file"], report
    faults: list[str] = []
    check = subprocess.run(
        ["git", "apply", "--check", str(patch_path)], cwd=checkout,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
    )
    if check.returncode != 0:
        report["oracle_satisfiable_within_paths"] = False
        return [
            f"reference_patch does not apply at {packet['starting_commit'][:12]}: "
            f"{check.stderr.strip()[-400:]}"
        ], report
    numstat = subprocess.run(
        ["git", "apply", "--numstat", str(patch_path)], cwd=checkout,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
    )
    touched = sorted({
        line.split("\t", 2)[2].strip()
        for line in numstat.stdout.splitlines() if line.count("\t") >= 2
    })
    writable = list(packet.get("writable_patch_paths") or [])
    outside = [rel for rel in touched if not _matches_any(rel, writable)]
    if outside:
        report["oracle_satisfiable_within_paths"] = False
        return [
            "reference_patch touches files outside writable_patch_paths: "
            + ", ".join(outside)
            + " -- the oracle can only be met by writing where the worker may not"
        ], report
    applied = subprocess.run(
        ["git", "apply", str(patch_path)], cwd=checkout,
        stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False,
    )
    if applied.returncode != 0:
        report["oracle_satisfiable_within_paths"] = False
        return [f"reference_patch failed to apply: {applied.stderr.strip()[-400:]}"], report
    still_red: list[str] = []
    for command_id in starts_red:
        command = commands.get(command_id)
        if command is None:
            continue  # already a fault from check_oracle_attainable
        completed = subprocess.run(
            command, shell=True, cwd=checkout, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, check=False,
            timeout=packet["limits"]["timeout_seconds"],
        )
        if completed.returncode != 0:
            still_red.append(command_id)
            faults.append(
                f"{command_id} is still red (exit {completed.returncode}) after the reference "
                f"patch at {packet['starting_commit'][:12]}: the oracle demands something "
                "outside writable_patch_paths, or more than this packet holds"
            )
    report["oracle_satisfiable_within_paths"] = not still_red
    report["red_after_reference"] = still_red
    return faults, report


def resolve_reference_patch(repo_root: Path, packet: dict[str, Any]) -> Path | None:
    """Where the packet's reference patch lives, or None when it carries none."""
    rel = (packet.get("oracle") or {}).get("reference_patch")
    if not rel:
        return None
    if Path(rel).is_absolute() or _pattern_escapes_repo(rel):
        raise PacketError("oracle.reference_patch must be a repo-relative path that stays inside the repository")
    return repo_root / rel


def check_oracle_reference(
    repo_root: Path, packet: dict[str, Any], manifest: dict[str, Any],
) -> tuple[list[str], dict[str, Any]]:
    """``overlay_reference_patch`` against a throwaway checkout of ``starting_commit``."""
    starts_red = (packet.get("oracle") or {}).get("starts_red") or []
    empty = {"oracle_satisfiable_within_paths": None, "reference_patch": None, "red_after_reference": []}
    if not starts_red:
        return [], empty
    patch_path = resolve_reference_patch(repo_root, packet)
    if patch_path is None:
        print(
            "hybrid-dispatch: warning: packet carries no oracle.reference_patch, so "
            "oracle satisfiability within writable_patch_paths was not checked "
            "(skipped:no-reference)",
            file=sys.stderr,
        )
        return overlay_reference_patch(repo_root, packet, manifest["hybrid"]["commands"], None)
    with tempfile.TemporaryDirectory(prefix="agentops-reference-") as tmp:
        checkout = Path(tmp) / "at-starting-commit"
        try:
            _git(repo_root, "clone", "--no-hardlinks", "--quiet", str(repo_root), str(checkout))
            _git(checkout, "checkout", "--quiet", "--detach", packet["starting_commit"])
        except Exception as exc:  # noqa: BLE001 - reported, never raised past here
            return [f"could not check out {packet['starting_commit']} to overlay the reference: {exc}"], {}
        return overlay_reference_patch(checkout, packet, manifest["hybrid"]["commands"], patch_path)


def assess_cold_run(
    results: list[dict[str, Any]], packet: dict[str, Any]
) -> tuple[list[dict[str, Any]], bool, list[str]]:
    """Decide whether a cold run means the workspace is fit to dispatch into.

    "Every registered command is green" is the right rule for a packet whose
    gates already pass, and the wrong one for a packet whose oracle is a test
    written before the code -- which is what a coordinator-authored oracle
    usually is.  Such a packet was undispatchable by construction: prepare
    demanded green, and the point of the packet was that one command is red.

    ``oracle.starts_red`` resolves it *upward* rather than by exempting anything.
    A named command must be red here, and a command that is already green is a
    fault: an oracle that cannot fail at the starting commit is not evidence of
    anything the worker later does to it.  Everything else must still be green,
    so unrelated breakage is caught exactly as before.
    """
    expected_red = set((packet.get("oracle") or {}).get("starts_red") or [])
    faults: list[str] = []
    for result in results:
        command_id = result["command_id"]
        red = result["exit_code"] != 0
        # 127 is "command not found", which is not a gate failing -- it is a gate
        # that does not exist at this commit. Accepting it as a declared red let a
        # packet dispatch against an oracle its workspace did not contain, and the
        # worker was judged by a test that never ran.
        if result["exit_code"] == 127:
            result["expectation"] = "red" if command_id in expected_red else "green"
            faults.append(
                f"{command_id} exited 127 at the starting commit: the command does not "
                "exist there, so it cannot be an oracle for this packet"
            )
            continue
        if command_id in expected_red:
            result["expectation"] = "red"
            if not red:
                faults.append(
                    f"{command_id} was declared starts_red but passed at the starting "
                    f"commit; an oracle that cannot fail proves nothing"
                )
        else:
            result["expectation"] = "green"
            if red:
                faults.append(f"{command_id} failed at the starting commit")
    return results, not faults, faults


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


MUTATION_TOOLS = frozenset({"write", "edit", "patch", "multiedit", "apply"})


def churn_verdict(
    events: list[dict[str, Any]], limits: dict[str, Any]
) -> tuple[str, str] | None:
    """Decide whether a worker stream has stopped making progress.

    ``context_churn`` was declared in every packet and enforced nowhere: the
    schema calls it "harness-side when telemetry permits", and it never did. A
    worker that read 1.07M tokens without a single completed write ran to its
    token ceiling with the limit sitting unread in its own packet.

    The stream is what the harness can see, so the limits are counted in it:
    tool events since the last *completed* mutation, and reads of one path. A
    denied write does not reset the counter -- it is an attempt, not progress --
    and a run of them gets its own verdict, because "the worker cannot write
    here" is a different fact from "the worker is going in circles" and the
    operator needs to be told which.
    """
    max_steps = limits.get("max_reasoning_steps_without_mutation")
    max_reads = limits.get("max_repeated_reads_per_path")
    steps_since_mutation = 0
    failed_mutations = 0
    reads: dict[str, int] = {}
    for event in events:
        if event.get("type") != "tool_use":
            continue
        part = event.get("part") or {}
        tool = part.get("tool")
        state = part.get("state") or {}
        status = state.get("status")
        if tool in MUTATION_TOOLS:
            if status == "completed":
                steps_since_mutation = 0
                failed_mutations = 0
                continue
            failed_mutations += 1
            if failed_mutations >= 3:
                return (
                    "worker_cannot_write",
                    f"{failed_mutations} consecutive mutation attempts failed; the worker "
                    "is being denied inside its own workspace",
                )
        # A call that did not complete is the harness failing, not the worker
        # circling, and it must not spend the budget meant to catch circling.
        # V5-M9 died on this three times: the worker's bash was refused by its
        # own profile and a grep errored on ripgrep's record limit, and those
        # four failures exhausted the steps before a write was ever attempted.
        # A failed *mutation* is still counted above, because "the worker is
        # being denied inside its own workspace" is a different fact and the
        # operator needs to be told which.
        if status != "completed":
            continue
        steps_since_mutation += 1
        if max_steps and steps_since_mutation > max_steps:
            return (
                "churn_no_mutation",
                f"{steps_since_mutation} tool steps without a completed mutation "
                f"(limit {max_steps})",
            )
        if tool == "read" and max_reads:
            path = (state.get("input") or {}).get("filePath")
            if path:
                reads[path] = reads.get(path, 0) + 1
                if reads[path] > max_reads:
                    return (
                        "churn_repeated_reads",
                        f"{path} read {reads[path]} times (limit {max_reads})",
                    )
    return None


def dispatch_worker(
    worktree: Path,
    packet_path: Path,
    packet: dict[str, Any],
    overlay: dict[str, Any],
    policy: dict[str, Any],
    opencode_bin: str,
    worker_user: str | None = None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Run exactly one bounded worker loop and return its raw transcript record."""
    agent_name = policy["routes"][packet["route"]]["agent"]
    message = (
        "Implement only the attached frozen task packet. Stay inside the writable "
        "paths it declares, use only the registered commands, and stop with a "
        "structured blocker on any ambiguity, missing context, or scope conflict. "
        "Do not use git, do not change sprint state, and do not expand scope. "
        "Respect context_churn: stop repeated unchanged reads or mutation-free "
        "reasoning at its limits. Do not optimize for cheap cache writes alone. "
        "As soon as the candidate and focused registered gate are ready, return "
        "the structured handoff instead of continuing self-review."
    )
    env = {
        **os.environ,
        "OPENCODE_CONFIG_CONTENT": json.dumps(overlay),
    }
    # Another path by which the worker learns the coordinator's real checkout.
    # It has no use for it: everything it may touch is inside the worktree.
    env.pop("AGENTOPS_ROOT", None)
    # The qualified OpenCode implementation profile treats positional arguments
    # after --file as further file values, so the message must precede it. The
    # containment prefix lives in worker_argv, shared with the qualification
    # probe: the only containment that actually holds is running as an identity
    # with no write access to the coordinator's checkout, and sudo scrubs the
    # environment, so the overlay is carried explicitly -- it is session
    # configuration, not a secret.
    argv = worker_argv(opencode_bin, agent_name, message, packet_path, worker_user)
    # Streamed rather than captured whole, so context_churn can be enforced while
    # the worker is still running. Captured output can only ever explain a
    # ceiling after it has been paid.
    limits = context_churn_limits(packet)
    deadline = time.monotonic() + packet["limits"]["timeout_seconds"]
    process = subprocess.Popen(
        argv,
        cwd=worktree,
        env=env,
        # A worker loop is strictly noninteractive. With the coordinator's stdin
        # inherited, `opencode run` blocks in init and the packet burns its whole
        # timeout without ever reaching inference -- indistinguishable from a slow
        # model. The same packet exits promptly once stdin is closed.
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: list[str] = []
    events: list[dict[str, Any]] = []
    stop: tuple[str, str] | None = None
    session_id: str | None = None
    try:
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append(event)
            session_id = session_id or event.get("sessionID")
            stop = churn_verdict(events, limits)
            if stop is not None:
                break
            if time.monotonic() > deadline:
                stop = ("timeout", "worker exceeded limits.timeout_seconds")
                break
    finally:
        if stop is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
        stderr = process.stderr.read() if process.stderr else ""
        if stop is None:
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                process.kill()
                stop = ("timeout", "worker exceeded limits.timeout_seconds")
    return {
        "argv": [shlex.quote(a) for a in argv],
        "worker_user": worker_user,
        "agent": agent_name,
        "model": model_override or policy["routes"][packet["route"]]["harness_model"],
        "exit_code": process.returncode if stop is None else 4,
        "stdout": "".join(lines),
        "stderr_tail": (stderr or "")[-4000:],
        "session_id": session_id,
        "churn_stop": None if stop is None else {"reason": stop[0], "detail": stop[1]},
    }


def worker_spend(
    transcript_stdout: str,
    cap_usd: float | None,
    soft_token_ceiling: int | None = None,
    hard_token_ceiling: int | None = None,
) -> dict[str, Any]:
    """Total what the worker loop actually spent, from its own transcript.

    ``limits.max_cost_usd`` was declared in the packet schema, the manifest
    schema and every example packet, and read by nothing: unlike
    ``timeout_seconds`` it bounded no behaviour at all. That is tolerable while
    the worker holds a separately capped credential and load-bearing when it
    does not -- on devbox the worker's key shares the coordinator's usage plan,
    so a runaway worker degrades the coordinator, and this is the only spend
    control in the system.

    OpenCode reports ``cost`` and ``tokens`` per ``step-finish`` part, so the
    figure is the harness's own accounting rather than an estimate from token
    counts and a price table that would drift. It is necessarily **post hoc**:
    it cannot abort a run mid-flight, and a single packet can still overspend
    its cap once. What it does is make that visible on the receipt and stop the
    packet, so a wave does not repeat the overspend across every item in it.

    A route whose provider reports no cost yields 0.0, which is indistinguishable
    from a free model. ``cost_reported`` records which case it was, so a corpus
    is never read as "this route is free" when it is really "this route did not
    say".
    """
    cost = 0.0
    tokens = 0
    cost_reported = False
    for line in transcript_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            part = json.loads(line).get("part") or {}
        except json.JSONDecodeError:
            continue
        if part.get("type") != "step-finish":
            continue
        if "cost" in part and part["cost"] is not None:
            cost += float(part["cost"])
            cost_reported = True
        tokens += int((part.get("tokens") or {}).get("total", 0) or 0)

    return {
        "cost_usd": round(cost, 6),
        "tokens": tokens,
        "cost_reported": cost_reported,
        "cap_usd": cap_usd,
        "within_cap": cap_usd is None or cost <= cap_usd,
        "soft_token_ceiling": soft_token_ceiling,
        "hard_token_ceiling": hard_token_ceiling,
        "soft_token_ceiling_exceeded": (
            soft_token_ceiling is not None and tokens > soft_token_ceiling
        ),
        "within_hard_token_ceiling": (
            hard_token_ceiling is None or tokens <= hard_token_ceiling
        ),
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

    worktree_status = _git(worktree, "status", "--porcelain").splitlines()
    gates = {
        "diff-nonempty": bool(touched),
        "diff-scope-respected": not out_of_scope,
        "protected-paths-untouched": not protected_hits,
        "worktree-state-captured": True,
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
        "worktree_status": worktree_status,
    }


def self_candidate_class(packet: dict[str, Any], manifest: dict[str, Any]) -> str | None:
    """The action class that lets this packet mint a candidate without a review
    record, or None.

    L-3 (D-8): ``routing.action_classes[<route>].self_candidate`` is the only
    place that authority lives. The packet cannot claim it for itself, the
    policy does not grant it per route, and a class that has not been flipped
    in the manifest keeps the review-record requirement exactly as before.
    """
    classes = (manifest.get("routing") or {}).get("action_classes") or {}
    entry = classes.get(packet["route"]) or {}
    if entry.get("enabled", False) and entry.get("self_candidate", False) is True:
        return packet["route"]
    return None


def load_independent_review(path: Path, packet: dict[str, Any]) -> dict[str, Any]:
    """Validate the coordinator's independent review record for a packet.

    A green mechanical gate is evidence, not acceptance.  The record is a
    deliberately separate artifact authored after inspecting that evidence;
    requiring it here makes a candidate impossible to mint from the worker
    loop alone.
    """
    review = _load_json(path)
    if not isinstance(review, dict):
        raise PacketError("review record must be a JSON object")
    required = {"task_id", "reviewer", "context", "decision", "evidence_path"}
    if not required.issubset(review):
        raise PacketError("review record is missing required independent-review fields")
    if review["task_id"] != packet["task_id"]:
        raise PacketError("review record task_id does not match packet")
    if review["context"] != "independent":
        raise PacketError("review record must be authored in an independent context")
    if review["decision"] != "candidate":
        raise PacketError("review record decision must be candidate")
    if review["reviewer"] == packet["sprint_item"]["claim_actor"]:
        raise PacketError("reviewer must differ from the coordinator claim actor")
    evidence_path = Path(str(review["evidence_path"]))
    if not evidence_path.is_file():
        raise PacketError("review record evidence_path does not exist")
    return review


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _receipt(packet: dict[str, Any], policy: dict[str, Any], **extra: Any) -> dict[str, Any]:
    packet_bytes = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()
    gate_bytes = json.dumps(
        {
            "allowed_command_ids": packet["allowed_command_ids"],
            "acceptance_properties": packet["acceptance_properties"],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    packet_hash = hashlib.sha256(packet_bytes).hexdigest()
    return {
        "schema_version": "agentops-hybrid-receipt/v1",
        "recorded_at": _now(),
        "execution_id": f"{packet['task_id']}:{packet_hash[:16]}:attempt-{packet.get('attempt', 1)}",
        "task_id": packet["task_id"],
        "repo_id": packet["repo_id"],
        "sprint_item": packet["sprint_item"],
        "route": packet["route"],
        "attempt": packet.get("attempt", 1),
        "inputs": {
            "packet_hash": f"sha256:{packet_hash}",
            "repository_commit": packet["starting_commit"],
            "packet_schema_version": packet["schema_version"],
            "gate_set_hash_schema_version": gate_set_hash_schema_version(packet),
            "gate_set_hash": f"sha256:{hashlib.sha256(gate_bytes).hexdigest()}",
        },
        "harness_model": policy["routes"][packet["route"]]["harness_model"],
        "qualification": qualification_state(policy, packet),
        "qualification_policy": policy["qualification"],
        "acceptance_authority": policy["acceptance_authority"],
        "context_churn": context_churn_limits(packet),
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
        "--sprintctl-bin", default=os.environ.get("SPRINTCTL_BIN", "sprintctl"),
        help="Coordinator-side sprintctl executable used for served claim verification.",
    )
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
        "--review-record",
        type=Path,
        help="Independent coordinator-review JSON required before gate may emit candidate.",
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
        "--worker-model",
        help=(
            "Run the loop on this model instead of the route's, for diagnostics "
            "that are about the harness rather than the model -- containment "
            "smokes above all, where the question is whether the worker can edit "
            "its clone and not reach the coordinator. Needed because provider "
            "access follows the identity: a contained worker has its own auth "
            "store, so the route's model may not be reachable as the worker even "
            "though it is as the coordinator. Permanently marks the run "
            "ineligible for qualification: a route assessed on a different model "
            "measured nothing about that route."
        ),
    )
    parser.add_argument(
        "--allow-untraced-oracle",
        action="store_true",
        help=(
            "validate only: when strace is not on PATH, record the oracle read-trace "
            "as skipped instead of failing closed. The report then says "
            "'skipped:untraced', never true."
        ),
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
            # L-2(a): a packet is not fit merely because it is well formed. An
            # oracle that cannot fail, or is not there at all, passes every
            # structural check and still cannot judge the worker.
            faults = check_oracle_attainable(repo_root, packet, manifest)
            # L-2(b), read-trace half: an attainable oracle may still depend on
            # files the packet never declared. Only traced when (a) is clean;
            # there is no point tracing a test that does not exist.
            read_report: dict[str, Any] = {}
            if not faults:
                faults, read_report = check_oracle_reads(
                    repo_root, packet, manifest, args.allow_untraced_oracle,
                )
            # L-2(b), reference-overlay half: a change confined to
            # writable_patch_paths must make the oracle green. Only run when
            # the trace is clean; optional until the handoff doc makes it
            # mandatory per class, but never reported true when absent.
            ref_report: dict[str, Any] = {}
            if not faults:
                faults, ref_report = check_oracle_reference(repo_root, packet, manifest)
            if faults:
                _emit({
                    "packet": packet["task_id"],
                    "status": "unfit",
                    "pre_gates": pre_gates,
                    "oracle_faults": faults,
                    **read_report,
                    **ref_report,
                })
                return 2
            _emit({"packet": packet["task_id"], "status": "fit", "pre_gates": pre_gates,
                   "oracle_attainable": True, **read_report, **ref_report})
            return 0

        base_config = _load_json(load_worker_config_path(args.agentops_root.resolve()))
        overlay = build_overlay(packet, manifest, policy, base_config, args.worker_model)

        if args.command == "overlay":
            _emit({"overlay": overlay, "overlay_sha256": overlay_hash(overlay)})
            return 0

        if args.command == "prepare":
            claim_evidence = verify_live_coordinator_claim(repo_root, packet, args.sprintctl_bin)
            safety = safety_ref(repo_root, packet)
            reused = workspace_is_retry_reuse(packet)
            worktree = prepare_workspace(repo_root, packet, args.worker_user)
            cold = run_registered_commands(worktree, packet, manifest)
            if reused:
                # A reused workspace holds the previous attempt's edits, so its
                # cold gates no longer have the colours the packet declared --
                # assessing them would fail every retry on the work the retry
                # exists to finish. The commands still run and are still
                # recorded; only the verdict is withheld, and the receipt says
                # so, because a reader cannot otherwise tell a skipped
                # assessment from a green one.
                green, cold_faults = True, []
                cold_gate_assessment = "skipped:workspace-reused"
            else:
                cold, green, cold_faults = assess_cold_run(cold, packet)
                cold_gate_assessment = "assessed"
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="prepare",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    coordinator_claim=claim_evidence,
                    safety=safety,
                    cold_command_results=cold,
                    cold_faults=cold_faults,
                    workspace_reused=reused,
                    cold_gate_assessment=cold_gate_assessment,
                    eligible_for_dispatch=green,
                )
            )
            return 0 if green else 2

        worktree = worktree_path(packet)
        if not worktree.exists():
            raise PacketError(f"{worktree} does not exist; run 'prepare' first")

        if args.command == "run":
            claim_evidence = verify_live_coordinator_claim(repo_root, packet, args.sprintctl_bin)
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
            # A run on a model the route does not name measures the harness, not
            # the route, so it is disqualified on the same footing and for the
            # same reason: the receipt has to carry it, because the
            # circumstances will not be remembered when the corpus is read.
            route_model = policy["routes"][packet["route"]]["harness_model"]
            on_route_model = args.worker_model in (None, route_model)
            containment_override = {
                "containment_override": not contained,
                "worker_user": args.worker_user,
                "worker_model": args.worker_model or route_model,
                "route_model": route_model,
                "model_override": not on_route_model,
                "qualification_eligible": contained and on_route_model,
                "unattended_eligible": contained and on_route_model,
                "override_reason": args.override_reason if not contained else None,
            }
            before = coordinator_tree_state(repo_root)
            transcript = dispatch_worker(
                worktree, packet_path, packet, overlay, policy, args.opencode_bin,
                args.worker_user, args.worker_model,
            )
            breach = sorted(set(coordinator_tree_state(repo_root)) - set(before))
            spend = worker_spend(
                transcript["stdout"],
                packet["limits"].get("max_cost_usd"),
                packet["limits"].get("soft_token_ceiling"),
                packet["limits"].get("hard_token_ceiling"),
            )
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="run",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    coordinator_claim=claim_evidence,
                    worker=transcript,
                    spend=spend,
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
                        else (
                            {}
                            if spend["within_cap"] and spend["within_hard_token_ceiling"]
                            else {"disposition": "budget_exceeded"}
                        )
                    ),
                )
            )
            # A worker that wrote outside its disposable worktree has escaped the
            # boundary the packet exists to enforce. That is never a retryable
            # quality result: it stops the packet for human triage.
            if breach:
                return 3
            # Overspend cannot be prevented after the fact, only stopped from
            # repeating. Exiting non-zero is what keeps a wave from running the
            # same overspend across every remaining packet.
            return 4 if not spend["within_cap"] or not spend["within_hard_token_ceiling"] else 0

        if args.command == "gate":
            claim_evidence = verify_live_coordinator_claim(repo_root, packet, args.sprintctl_bin)
            evidence = post_gates(worktree, packet, manifest, repo_root)
            review = None
            if evidence["passed"] and args.review_record is not None:
                review = load_independent_review(args.review_record, packet)
            # L-3: a self_candidate class needs no record when every evidence
            # gate is green. Any red gate, or any other class, is unchanged.
            self_class = self_candidate_class(packet, manifest)
            if evidence["passed"] and review is None and self_class is not None:
                review = {"mode": "self_candidate", "class": self_class, "basis": "manifest"}
            disposition = (
                "candidate" if evidence["passed"] and review is not None
                else "coordinator_review_required"
            )
            _emit(
                _receipt(
                    packet,
                    policy,
                    stage="gate",
                    worktree=str(worktree),
                    overlay_sha256=overlay_hash(overlay),
                    coordinator_claim=claim_evidence,
                    evidence=evidence,
                    independent_review=review,
                    disposition=disposition,
                )
            )
            return 0 if disposition == "candidate" else 2

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
