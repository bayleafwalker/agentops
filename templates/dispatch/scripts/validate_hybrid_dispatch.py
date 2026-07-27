#!/usr/bin/env python3
"""Validate the hybrid dispatch policy, worker config, and repository hybrid blocks.

Deterministic and offline. Provider availability is a separate live concern:
use ``--live`` only to confirm that the installed OpenCode catalog still lists
the policy's concrete model ids. Availability is never qualification.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

POLICY_RELATIVE = Path("templates/dispatch/hybrid/hybrid-dispatch.v1.json")
WORKER_CONFIG_RELATIVE = Path("templates/dispatch/hybrid/opencode.hybrid.json")
DENIED = ("external_directory", "webfetch", "websearch", "task")


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_policy(policy: dict[str, Any], worker_config: dict[str, Any]) -> None:
    if policy["schema_version"] != "agentops-hybrid-dispatch/v1":
        raise ValueError("unexpected policy schema_version")
    if policy["default_mode"] != "supervised_hybrid":
        raise ValueError("supervised_hybrid must be the default mode")
    if policy["workflow_precedence"] != ["supervised_hybrid", "frontier_only"]:
        raise ValueError("workflow precedence must be supervised_hybrid then frontier_only")
    if policy["acceptance_authority"] != "human":
        raise ValueError("acceptance authority must remain human")
    if policy["sprintctl_authority"] != "coordinator_only":
        raise ValueError("sprintctl authority must remain coordinator-only")
    if policy["free_remote_models"] != "forbidden_for_repository_context":
        raise ValueError("free remote models must stay forbidden for repository context")
    if policy["network_policy_default"] != "disabled":
        raise ValueError("worker network policy must default to disabled")
    if policy["qualification"] != "none":
        raise ValueError(
            "no route is qualified; availability and a passing smoke run do not "
            "promote a model/task-class pair"
        )

    for authority in ("git", "sprintctl", "deployment or cluster mutation"):
        if authority not in policy["worker"]["denied_authority"]:
            raise ValueError(f"worker must be denied {authority}")

    agents = worker_config["agent"]
    for name, route in policy["routes"].items():
        agent = route.get("agent")
        if agent is None:
            if "modes" not in route:
                raise ValueError(f"{name}: coordinator route must declare modes")
            continue
        if agent not in agents:
            raise ValueError(f"{name}: missing OpenCode agent {agent}")
        if agents[agent]["mode"] != "primary":
            raise ValueError(f"{name}: CLI dispatch agent must be primary")
        if agents[agent]["model"] != route["harness_model"]:
            raise ValueError(f"{name}: agent model does not match the routing policy")
        permission = agents[agent]["permission"]
        for key in DENIED:
            if permission.get(key) != "deny":
                raise ValueError(f"{agent}: {key} must be denied")

    review = agents["ao-review"]["permission"]
    if review.get("edit") != "deny" or review.get("bash") != "deny":
        raise ValueError("ao-review must be read-only")

    base = worker_config["permission"]
    if base["*"] != "ask":
        raise ValueError("the checked-in base config must not pre-authorize anything")
    for key in ("external_directory", "webfetch", "websearch"):
        if base.get(key) != "deny":
            raise ValueError(f"base config: {key} must be denied")


def validate_manifest_hybrid(manifest: dict[str, Any], policy: dict[str, Any], path: Path) -> bool:
    hybrid = manifest.get("hybrid")
    if hybrid is None:
        return False
    for field in ("enabled", "worker_routes", "commands", "protected_paths"):
        if field not in hybrid:
            raise ValueError(f"{path}: hybrid block missing {field}")
    worker_routes = hybrid["worker_routes"]
    if not isinstance(worker_routes, list) or not worker_routes:
        raise ValueError(f"{path}: hybrid.worker_routes must be a non-empty array")
    for route in worker_routes:
        if route not in policy["routes"]:
            raise ValueError(f"{path}: unknown worker route {route}")
        if policy["routes"][route].get("mode") != "supervised_hybrid":
            raise ValueError(f"{path}: {route} is not a worker route")
    if not hybrid["commands"]:
        raise ValueError(f"{path}: hybrid.commands must register at least one command")
    if not hybrid["protected_paths"]:
        raise ValueError(
            f"{path}: hybrid.protected_paths must be explicit; an empty list would "
            "let a worker edit any in-scope path"
        )
    scope_roots = manifest.get("scope", {}).get("allowed_path_roots", [])
    if hybrid["enabled"] and not scope_roots:
        raise ValueError(
            f"{path}: hybrid dispatch requires scope.allowed_path_roots to bound "
            "writable packet paths"
        )
    return True


def live_check(policy: dict[str, Any]) -> None:
    models = {
        route["harness_model"]
        for route in policy["routes"].values()
        if "harness_model" in route
    }
    providers = {model.split("/", 1)[0] for model in models}
    for provider in sorted(providers):
        listed = subprocess.run(
            ["opencode", "models", provider],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0:
            raise ValueError(f"opencode models {provider} failed: {listed.stderr.strip()}")
        available = set(listed.stdout.split())
        for model in sorted(m for m in models if m.startswith(provider + "/")):
            if model not in available:
                raise ValueError(f"unavailable model {model}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agentops-root", type=Path, default=Path("/projects/dev/agentops"))
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        default=[],
        help="Repository dispatch manifest to check for a well-formed hybrid block.",
    )
    parser.add_argument("--live", action="store_true", help="Also check OpenCode model availability.")
    args = parser.parse_args()

    root = args.agentops_root.resolve()
    policy = _load(root / POLICY_RELATIVE)
    worker_config = _load(root / WORKER_CONFIG_RELATIVE)
    validate_policy(policy, worker_config)

    checked = 0
    for manifest_path in args.manifest:
        if validate_manifest_hybrid(_load(manifest_path), policy, manifest_path):
            checked += 1

    if args.live:
        live_check(policy)

    print(
        f"hybrid dispatch policy valid; {checked} manifest hybrid block(s) checked"
        + ("; models available (unqualified)" if args.live else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
