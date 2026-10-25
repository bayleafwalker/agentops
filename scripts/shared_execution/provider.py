"""Fail-closed decision helpers for explicitly qualified provider failover.

This module consumes an operator-ordered binding snapshot. It is not a model
catalog, selector, eligibility authority, or automatic route discovery API.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any


POLICY_SCHEMA = "provider-failover/v1"
SUPPORTED_FAILURES = {"quota_exhausted", "transport_error"}


@dataclass(frozen=True)
class FailoverDecision:
    allowed: bool
    reason: str
    binding: dict[str, Any] | None = None
    usage_ref: str | None = None


def harness_command_digest(command_template: list[str] | tuple[str, ...]) -> str:
    """Hash the explicit harness command template a binding was qualified for."""
    if not command_template or not all(isinstance(item, str) for item in command_template):
        raise ValueError("worker command template must be a non-empty string list")
    encoded = json.dumps(list(command_template), ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_failover_policy(policy: Any) -> dict[str, Any]:
    """Validate shape only; the owner/adapter supplied the eligibility facts."""
    if policy is None:
        return {"schema_version": POLICY_SCHEMA, "enabled": False, "ordered_bindings": []}
    if not isinstance(policy, dict):
        raise ValueError("provider_failover must be an object")
    enabled = policy.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("provider_failover.enabled must be boolean")
    if not enabled:
        return dict(policy, schema_version=policy.get("schema_version", POLICY_SCHEMA),
                    enabled=False, ordered_bindings=policy.get("ordered_bindings", []))
    if policy.get("schema_version") != POLICY_SCHEMA:
        raise ValueError(f"provider_failover schema must be {POLICY_SCHEMA}")
    if not isinstance(policy.get("source_ref"), str) or not policy["source_ref"].strip():
        raise ValueError("enabled provider_failover needs a binding snapshot source_ref")
    for field in ("billing_snapshot_ref", "budget_enforcement_ref"):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            raise ValueError(f"enabled provider_failover needs {field}")
    if policy.get("allow_paid_overage") is not False:
        raise ValueError("paid overage is unsupported; allow_paid_overage must be false")
    bindings = policy.get("ordered_bindings")
    if not isinstance(bindings, list) or len(bindings) < 2:
        raise ValueError("enabled provider_failover needs an ordered current and fallback binding")
    ids: set[str] = set()
    required = ("binding_id", "provider_id", "model_id", "role_id", "harness_id",
                "eligibility_ref", "role_qualification_ref", "data_policy_ref",
                "billing_mode", "billing_ref",
                "harness_qualification_ref", "worker_command_sha256",
                "allowed_data_classes", "max_cost_per_attempt_usd")
    for index, binding in enumerate(bindings):
        if not isinstance(binding, dict):
            raise ValueError(f"binding {index} must be an object")
        for field in required:
            if field not in binding:
                raise ValueError(f"binding {index} is missing {field}")
            value = binding[field]
            if field not in {"allowed_data_classes", "max_cost_per_attempt_usd"} and (
                    not isinstance(value, str) or not value.strip()):
                raise ValueError(f"binding {index} {field} must be non-empty text")
        binding_id = binding["binding_id"]
        if binding_id in ids:
            raise ValueError(f"duplicate binding_id {binding_id}")
        ids.add(binding_id)
        classes = binding["allowed_data_classes"]
        if (not isinstance(classes, list) or not classes
                or not all(isinstance(item, str) and item.strip() for item in classes)):
            raise ValueError(f"binding {index} allowed_data_classes must be a non-empty string list")
        if binding["billing_mode"] not in {"subscription", "api"}:
            raise ValueError(f"binding {index} billing_mode must be explicit subscription or api")
        cost = binding["max_cost_per_attempt_usd"]
        if (not isinstance(cost, (int, float)) or isinstance(cost, bool)
                or not math.isfinite(cost) or cost <= 0):
            raise ValueError(f"binding {index} max_cost_per_attempt_usd must be finite and positive")
    return dict(policy)


def decide_failover(policy: Any, *, current_binding_id: str | None,
                    current_provider_id: str, current_model_id: str,
                    role_id: str | None, data_class: str | None, harness_id: str,
                    worker_command_sha256: str, failure_kind: str,
                    quota_reset_at: float | None, expected_attempt_ref: str | None,
                    usage: Any,
                    now: float) -> FailoverDecision:
    """Return the next ordered binding only when every explicit bound is known."""
    try:
        policy = validate_failover_policy(policy)
    except (TypeError, ValueError) as exc:
        return FailoverDecision(False, "invalid_policy:" + str(exc))
    if not policy.get("enabled"):
        return FailoverDecision(False, "disabled")
    if failure_kind not in SUPPORTED_FAILURES:
        return FailoverDecision(False, "failure_kind_not_qualified")
    if failure_kind == "quota_exhausted":
        if (not isinstance(quota_reset_at, (int, float)) or isinstance(quota_reset_at, bool)
                or not math.isfinite(quota_reset_at) or quota_reset_at <= now):
            return FailoverDecision(False, "quota_reset_unknown_or_elapsed")
    if not isinstance(usage, dict) or usage.get("state") != "known" or usage.get("complete") is not True:
        return FailoverDecision(False, "usage_unknown")
    if usage.get("observer") not in {"owner", "coordinator"}:
        return FailoverDecision(False, "usage_observer_untrusted")
    if usage.get("billing_snapshot_ref") != policy.get("billing_snapshot_ref"):
        return FailoverDecision(False, "usage_billing_snapshot_mismatch")
    for field in ("attempt_ref", "evidence_ref", "source_ref"):
        if not isinstance(usage.get(field), str) or not usage[field].strip():
            return FailoverDecision(False, "usage_evidence_missing")
    if not expected_attempt_ref or usage["attempt_ref"] != expected_attempt_ref:
        return FailoverDecision(False, "usage_attempt_mismatch")
    observed_cost = usage.get("attempt_cost_usd")
    remaining = usage.get("remaining_budget_usd")
    if any(not isinstance(value, (int, float)) or isinstance(value, bool)
           or not math.isfinite(value) or value < 0 for value in (observed_cost, remaining)):
        return FailoverDecision(False, "usage_cost_or_budget_unknown")

    bindings = policy["ordered_bindings"]
    index = next((i for i, binding in enumerate(bindings)
                  if binding["binding_id"] == current_binding_id), None)
    if index is None:
        return FailoverDecision(False, "current_binding_unresolved")
    current = bindings[index]
    if (current["provider_id"] != current_provider_id
            or current["model_id"] != current_model_id):
        return FailoverDecision(False, "current_binding_mismatch")
    if (not role_id or current["role_id"] != role_id
            or current["harness_id"] != harness_id
            or current["worker_command_sha256"] != worker_command_sha256):
        return FailoverDecision(False, "current_role_or_harness_unqualified")
    if not data_class or data_class not in current["allowed_data_classes"]:
        return FailoverDecision(False, "current_data_policy_unqualified")
    if observed_cost > current["max_cost_per_attempt_usd"]:
        return FailoverDecision(False, "observed_cost_exceeded_current_binding")

    candidate = bindings[index + 1] if index + 1 < len(bindings) else None
    if candidate is None:
        return FailoverDecision(False, "no_next_ordered_binding")
    if candidate["provider_id"] == current_provider_id:
        return FailoverDecision(False, "candidate_provider_unchanged")
    if (candidate["role_id"] != role_id or candidate["harness_id"] != harness_id
            or candidate["worker_command_sha256"] != worker_command_sha256):
        return FailoverDecision(False, "candidate_role_or_harness_unqualified")
    if data_class not in candidate["allowed_data_classes"]:
        return FailoverDecision(False, "candidate_data_policy_unqualified")
    candidate_cost = candidate["max_cost_per_attempt_usd"]
    if candidate_cost > current["max_cost_per_attempt_usd"]:
        return FailoverDecision(False, "candidate_cost_exceeds_current_ceiling")
    if candidate_cost > remaining:
        return FailoverDecision(False, "candidate_cost_exceeds_remaining_budget")
    return FailoverDecision(True, "binding_snapshot_constraints_passed",
                            dict(candidate), usage["evidence_ref"])
