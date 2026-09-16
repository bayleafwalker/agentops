"""Pure evaluators over text read at one commit (DOSSIER-front-page-design.md §6.2-§6.3)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

RUNGS = {"D0": 0, "D1": 1, "D2": 2, "D3": 3, "D4": 4}
PLACEHOLDER = re.compile(r"replace|placeholder|changeme|todo", re.IGNORECASE)
DIGEST = re.compile(r"vuoro-service@(sha256:[0-9a-f]{64})")
Scope = dict[str, frozenset[str]]


@dataclass(frozen=True)
class Row:
    passed: bool
    value: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Move:
    vocabulary: str
    member: str
    cls: str
    boundary: str
    boundary_at: str
    detail: str | None = None


def service_rows(deployment: str | None, ks: str | None) -> dict[str, Row]:
    if deployment is None:
        return {}
    digest = DIGEST.search(deployment)
    replicas = re.search(r"^\s*replicas:\s*(\d+)", deployment, re.MULTILINE)
    suspended = bool(ks and re.search(r"^\s*suspend:\s*true\b", ks, re.MULTILINE))
    reachable = (replicas is None or int(replicas.group(1)) > 0) and not suspended
    return {"vuoro-shared": Row(reachable, digest.group(1) if digest else None)}


def lock_rows(pins: dict) -> dict[str, Row]:
    if "adapters" in pins:  # vuoro-composition/v1 named each lock by its domain
        entries = [{**a, "lock_id": f"{a['domain']}-adapter"} for a in pins["adapters"]]
    else:
        entries = pins["release_locks"]
    return {e["lock_id"]: Row(True, e["source_revision"], e.get("distribution_version")) for e in entries}


def record_classes(validation: str) -> set[str]:
    declared = re.search(r"^RECORD_CLASSES\s*=\s*\(([^)]*)\)", validation, re.MULTILINE)
    if declared:
        return set(re.findall(r"[\"']([^\"']+)[\"']", declared.group(1)))
    # Before RECORD_CLASSES existed the validator admitted exactly one literal class.
    return set(re.findall(r"record_class must be (\w+)", validation))


def configured(value) -> bool:
    return isinstance(value, str) and value.strip() != "" and not PLACEHOLDER.search(value)


def audience_configured(value) -> bool:
    # An all-caps token (SOME_AUDIENCE_TO_FILL) is a placeholder's shape, never a real audience.
    return configured(value) and not re.fullmatch(r"[A-Z0-9_]+", value)


def authorized(policy: dict, provider: str | None, capability: str, repository: str, wide_scope: Scope | None = None) -> bool:
    settings = policy.get("providers", {}).get(provider)
    if not settings:
        return False
    if provider != "forgejo":
        return all(configured(v) for v in settings.values() if isinstance(v, str))
    per_repository = settings.get("repository_audiences")
    if per_repository is not None:
        return audience_configured(per_repository.get(capability, {}).get(repository))
    # A provider-wide audience names the repositories registered when its value was set, not later ones.
    in_scope = wide_scope is None or repository in wide_scope.get(capability, frozenset())
    return in_scope and audience_configured(settings.get("audiences", {}).get(capability))


def broker_rows(policy: dict | None, wide_scope: Scope | None = None) -> dict[str, dict[str, Row]]:
    if policy is None:
        return {"credbroker.capability_rule": {}, "credbroker.repository": {}, "credbroker.binding": {}}
    rules = policy.get("policy", {})
    providers = {r["repository_id"]: r.get("provider") for r in policy.get("repositories", [])}
    active = {h["host_id"]: h.get("active", True) for h in rules.get("hosts", [])}
    # A binding names a repository, or a non-repository target (kubernetes.edit) whose provider is its capability's prefix.
    subject = lambda b: b.get("repository_id") or b["target"]  # noqa: E731
    usable = lambda b, c: active.get(b["host_id"], False) and authorized(  # noqa: E731
        policy, providers.get(b["repository_id"]) if "repository_id" in b else c.split(".")[0], c, subject(b), wide_scope)
    return {
        "credbroker.capability_rule": {k: Row(True, json.dumps(v, sort_keys=True)) for k, v in rules.get("capabilities", {}).items()},
        "credbroker.repository": {r: Row(True) for r in providers},
        "credbroker.binding": {
            f"{b['host_id']}|{subject(b)}|{c}": Row(usable(b, c)) for b in rules.get("bindings", []) for c in b.get("capabilities", [])
        },
    }


def durability_rows(cockpit_pvc: bool | None, policy: dict | None, broker_pvc: bool) -> dict[str, Row]:
    """cockpit_pvc None: the owning component's manifest is gone, so the store is no member at all (RETIRED, never D0)."""
    receipts = bool(policy and policy.get("receipt_path")) and broker_pvc
    cockpit = {} if cockpit_pvc is None else {"cockpit.reconciliation-state": Row(True, "D2" if cockpit_pvc else "D0")}
    return cockpit | {"credbroker.receipts": Row(True, "D2" if receipts else "D0")}


def policy_revision(policy: dict) -> str:
    """cred-broker's own algorithm (config.py:241, policy.py:58-59): sha256 over the canonical `policy` object only."""
    return "sha256:" + hashlib.sha256(json.dumps(policy["policy"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def orphan_authorities(requested: dict[str, int], served: set[str]) -> dict[str, int]:
    return {a: n for a, n in sorted(requested.items()) if a not in served}


def classify(vocabulary: str, before: dict[str, Row], after: dict[str, Row]) -> list[tuple[str, str]]:
    moves = []
    for member in sorted(before.keys() | after.keys()):
        b, a = before.get(member), after.get(member)
        if vocabulary == "durability.store":
            if b and a and b.value != a.value:
                moves.append((member, "DURABILITY-UP" if RUNGS[a.value] > RUNGS[b.value] else "DURABILITY-DOWN"))
            elif b and a is None:
                moves.append((member, "RETIRED"))
        elif b is None:
            moves += [(member, "GAINED")] if a.passed else []
        elif a is None:
            moves += [(member, "FORECLOSED")] if b.passed else []
        else:
            if b.passed != a.passed:
                moves.append((member, "GAINED" if a.passed else "REGRESSED"))
            if b.value != a.value and (a.passed or b.passed):
                moves.append((member, "CONTRACT-CHANGE"))
    return moves
