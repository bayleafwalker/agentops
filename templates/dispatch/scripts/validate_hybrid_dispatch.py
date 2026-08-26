#!/usr/bin/env python3
"""Validate the hybrid dispatch policy, worker config, and repository hybrid blocks.

Deterministic and offline. Provider availability is a separate live concern:
use ``--live`` only to confirm that the installed OpenCode catalog still lists
the policy's concrete model ids. Availability is never qualification.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

POLICY_RELATIVE = Path("templates/dispatch/hybrid/hybrid-dispatch.v1.json")
WORKER_CONFIG_RELATIVE = Path("templates/dispatch/hybrid/opencode.hybrid.json")
DENIED = ("external_directory", "webfetch", "websearch", "task")
FINALIZER_TOOLS = (
    "read", "glob", "grep", "list", "todowrite", "todoread", "edit", "write",
    "patch", "bash", "task", "external_directory", "webfetch", "websearch",
)


#: Formats this validator asserts on manifests. ``manifest.schema.json`` has
#: declared ``"format": "uuid"`` on ``authority_repo_uuid`` since it was written,
#: but ``format`` is an annotation by default, so until 2026-08-26 the checker
#: would certify a non-UUID -- the schema made a claim it did not keep. V6-I made
#: the format checkable; this is the caller that opts in.
ASSERTED_FORMATS = ("uuid",)


def _load_schema_check():
    """``schema_check``, loaded by path exactly once.

    Loaded at import rather than per call: re-executing the module on every
    lookup is wasteful, and it also hands out a *different* function object each
    time, so nothing downstream could assert that the checker in use is the
    registered one.
    """
    spec = importlib.util.spec_from_file_location(
        "_schema_check_for_validate_hybrid_dispatch",
        Path(__file__).resolve().parent / "schema_check.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_SCHEMA_CHECK = _load_schema_check()


def _format_checker(name: str):
    """The checker ``schema_check`` registers for ``name``, never a second copy.

    Restating the pattern here is how two functions answering the same question
    drift apart -- the defect this repo has already had to undo once, and the
    reason ``churn_metrics`` imports ``MUTATION_TOOLS`` rather than listing it.
    An unknown name raises here for the same reason it raises there: certifying
    what was never checked is the thing being fixed.
    """
    try:
        return _SCHEMA_CHECK.FORMAT_CHECKERS[name]
    except KeyError:
        raise ValueError(
            f"no checker registered for asserted format {name!r}"
        ) from None


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
    qualification = policy["qualification"]
    if qualification == "none":
        pass
    elif isinstance(qualification, dict) and qualification.get("mode") == "named_pilot":
        required = {"pilot_id", "repositories", "routes", "models", "evidence_document", "default", "admission"}
        missing = required - qualification.keys()
        if missing:
            raise ValueError(f"named pilot is missing fields: {', '.join(sorted(missing))}")
        if qualification["default"] != "unqualified":
            raise ValueError("a named pilot must leave the default unqualified")
        if not all(isinstance(qualification[key], list) and qualification[key] for key in ("repositories", "routes", "models")):
            raise ValueError("a named pilot must bound repositories, routes, and models")
        for route in qualification["routes"]:
            configured = policy["routes"].get(route)
            if not configured or configured.get("harness_model") not in qualification["models"]:
                raise ValueError(f"named pilot route {route!r} is not bound to a pilot model")
    else:
        raise ValueError("qualification must be 'none' or a bounded named_pilot")

    for authority in ("git", "sprintctl", "deployment or cluster mutation"):
        if authority not in policy["worker"]["denied_authority"]:
            raise ValueError(f"worker must be denied {authority}")

    agents = worker_config["agent"]
    for name, route in policy["routes"].items():
        repository_scope = route.get("repository_scope")
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
                raise ValueError(f"{name}: project repository scope is invalid")
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

    review = agents.get("ao-review", {}).get("permission", {})
    if review.get("edit") != "deny" or review.get("bash") != "deny":
        raise ValueError("benchmark-only ao-review must be read-only")

    finalizer = agents.get("ao-finalizer")
    if not isinstance(finalizer, dict):
        raise ValueError("ao-finalizer must be configured")
    if finalizer.get("mode") != "primary":
        raise ValueError("ao-finalizer must be a primary agent")
    finalizer_permission = finalizer.get("permission")
    if not isinstance(finalizer_permission, dict):
        raise ValueError("ao-finalizer permission map is missing")
    if finalizer_permission.get("*") != "deny":
        raise ValueError("ao-finalizer must deny the wildcard tool surface")
    if finalizer.get("tools") not in (None, {}):
        raise ValueError("ao-finalizer must not declare tools")
    if finalizer.get("mcp") not in (None, {}):
        raise ValueError("ao-finalizer must not declare MCP tools")
    for tool in FINALIZER_TOOLS:
        if finalizer_permission.get(tool) != "deny":
            raise ValueError(f"ao-finalizer: {tool} must be denied")
    if any(value != "deny" for value in finalizer_permission.values()):
        raise ValueError("ao-finalizer must deny every explicit tool and MCP permission")

    base = worker_config["permission"]
    if "*" in base:
        raise ValueError(
            "the checked-in base config must resolve every permission explicitly, "
            "not leave a wildcard fallback -- noninteractive opencode run refuses "
            "permissions left at 'ask', and a blanket '*': 'deny' withholds tools "
            "from the model entirely (see build_overlay's docstring)"
        )
    bash = base.get("bash")
    if not isinstance(bash, dict) or bash.get("*") != "deny":
        raise ValueError(
            "the checked-in base config must deny bash by default -- unlike edit/"
            "write, bash has no containment equivalent to a disposable worktree "
            "plus post-hoc scope gates, so it must never be pre-authorized outside "
            "a packet-specific allowed_command_ids overlay"
        )
    for key in ("external_directory", "webfetch", "websearch"):
        if base.get(key) != "deny":
            raise ValueError(f"base config: {key} must be denied")


def validate_manifest_identity(manifest: dict[str, Any], path: Path) -> None:
    """Assert the formats the manifest schema declares but cannot enforce alone.

    ``authority_repo_uuid`` stays **optional** -- ten of eighteen manifests carry
    none, and requiring one is a separate and larger claim about authority
    identity across repositories. What changes is that a *present* value must be
    what the schema says it is. Measured before turning this on: eight manifests
    carry the field and all eight were already valid, so this rejects nothing
    that exists and constrains only what is written next.
    """
    value = manifest.get("authority_repo_uuid")
    if value is None:
        return
    if not isinstance(value, str) or not _format_checker("uuid")(value):
        raise ValueError(
            f"{path}: authority_repo_uuid must match the schema's "
            f'"format": "uuid", got {value!r}'
        )


def validate_manifest_hybrid(manifest: dict[str, Any], policy: dict[str, Any], path: Path) -> bool:
    validate_manifest_identity(manifest, path)
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
    # L-3 (D-8): self_candidate is a manifest-level grant, so it must be a
    # literal boolean on an enabled class carrying its provenance -- a flip
    # without a ruling is unreviewable.
    #
    # The class is no longer required to *be* a worker route. It must instead
    # name the routes its ruling was written about (permitted_routes), each of
    # which must be an enabled worker route here. That is the decoupling: a
    # route says who executes and is chosen per task; a class says what may be
    # minted without human review and is granted deliberately. Requiring the two
    # to share a name welded a transient binding to a durable authority.
    classes = (manifest.get("routing") or {}).get("action_classes") or {}
    for name, entry in classes.items():
        flag = entry.get("self_candidate", False)
        if not isinstance(flag, bool):
            raise ValueError(f"{path}: action class {name} self_candidate must be a boolean")
        if flag:
            if not entry.get("enabled", False):
                raise ValueError(f"{path}: action class {name} is self_candidate but not enabled")
            permitted = entry.get("permitted_routes")
            if not isinstance(permitted, list) or not permitted:
                raise ValueError(
                    f"{path}: action class {name} is self_candidate but declares no "
                    "permitted_routes; the grant must say which routes it covers"
                )
            for route in permitted:
                if route not in worker_routes:
                    raise ValueError(
                        f"{path}: action class {name} permits route {route}, which is "
                        "not an enabled hybrid worker route here"
                    )
            if not str(entry.get("self_candidate_ruling", "")).strip():
                raise ValueError(
                    f"{path}: action class {name} is self_candidate without a self_candidate_ruling"
                )
    soft_tokens = hybrid.get("soft_token_ceiling")
    hard_tokens = hybrid.get("hard_token_ceiling")
    if not isinstance(soft_tokens, int) or not isinstance(hard_tokens, int):
        raise ValueError(f"{path}: hybrid token ceilings must be explicit integers")
    if soft_tokens <= 0 or hard_tokens <= soft_tokens:
        raise ValueError(
            f"{path}: hybrid.hard_token_ceiling must exceed a positive soft_token_ceiling"
        )
    return True


def qualification_state(policy: dict[str, Any], repo_id: str, route: str) -> str:
    """Return the exact qualification label that must be retained in receipts."""
    qualification = policy["qualification"]
    if qualification == "none":
        return "unqualified"
    if (
        repo_id in qualification["repositories"]
        and route in qualification["routes"]
        and policy["routes"][route]["harness_model"] in qualification["models"]
    ):
        return f"named_pilot:{qualification['pilot_id']}"
    return qualification["default"]


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
        + ("; models available" if args.live else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
