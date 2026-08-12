#!/usr/bin/env python3
"""Validate the OpenCode admission-check config and, optionally, a result.

This is an offline sanity check, not a promotion gate: nothing here signs,
seals, or consumes anything, because the admission check itself no longer
produces anything that needs that (there is no one-shot ledger, no signed
record, no independent-review gate). Ongoing trust in a provider/model for
a role is a separate, rolling mechanism (agentops#2143 -- role-scoped
continuous fitness/routing evidence over hundreds of real runs), not this
check.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).parents[3]
DEFAULT_CORPUS = ROOT / "templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json"
DEFAULT_MANIFEST = ROOT / "agentops.dispatch.json"
EXPECTED_MODEL = "opencode-go/deepseek-v4-flash"
EXPECTED_PROVIDER = "opencode-go"
EXPECTED_MODEL_ID = "deepseek-v4-flash"
EXPECTED_WORKER = "agentworker"
MAX_USAGE_MULTIPLIER = 2
MAX_COST_USD = 3.0
SOFT_TOKEN_CEILING = 500_000
HARD_TOKEN_CEILING = 1_000_000
MAX_STRING_LENGTH = 256
MAX_FIELD_NAME_LENGTH = 96
SECRET_LIKE = (
    re.compile(r"-----BEGIN [A-Z0-9 ]+-----"),
    re.compile(r"^(?:https?|ssh)://"),
    re.compile(r"(?i)(?:api[_ -]?key|bearer|secret|password|token)\s*[:=]"),
    re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$"),
)
SENSITIVE_KEYS = frozenset({
    "prompt", "prompts", "transcript", "transcripts", "output", "outputs",
    "stdout", "stderr", "response", "responses", "raw", "path", "paths", "cwd", "command", "argv",
    "credential", "credentials", "secret", "secrets", "api_key", "apiKey",
    "claim_token", "claimToken", "environment", "env", "worktree", "worktree_path",
    "absolute_path", "raw_transcript", "raw_output",
})


class QualificationError(ValueError):
    """A missing or contradictory requirement fails the check closed."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"{path}: top-level value must be an object")
    return value


def _keys(value: dict[str, Any], required: set[str], optional: set[str], field: str) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required - optional)
    if missing:
        raise QualificationError(f"{field} is missing fields: {', '.join(missing)}")
    if extra:
        raise QualificationError(f"{field} has unexpected fields: {', '.join(extra)}")


def _non_blank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{field} must be a non-blank string")
    return value


def _finite_number(value: Any, field: str, *, positive: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or (positive and value <= 0):
        raise QualificationError(f"{field} must be finite numeric evidence")
    return float(value)


def _reject_sensitive(value: Any, path: str = "result") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in SENSITIVE_KEYS:
                raise QualificationError(f"{path}.{key} is not allowed in a plain run-report")
            if isinstance(key, str) and (key.startswith("/") or "/projects/" in key):
                raise QualificationError(f"{path} contains an absolute workspace path in a field name")
            _reject_sensitive(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if value.startswith("/") or "/projects/" in value:
            raise QualificationError(f"{path} must not contain an absolute workspace path")
        if any(pattern.search(value) for pattern in SECRET_LIKE):
            raise QualificationError(f"{path} contains secret-like or externally addressable text")


def _validate_bounded_strings(value: Any, path: str = "result") -> None:
    """Keep every retained string structurally bounded and control-free."""
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > MAX_FIELD_NAME_LENGTH:
                raise QualificationError(f"{path} contains an overlong field name")
            _validate_bounded_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_bounded_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH or any(ord(char) < 0x20 and char not in "\t" for char in value):
            raise QualificationError(f"{path} contains an unbounded or control-bearing string")


def validate_config(corpus: dict[str, Any], manifest: dict[str, Any]) -> None:
    _keys(corpus, {"schema_version", "corpus_id", "route", "budgets", "containment"}, set(), "corpus")
    if corpus["schema_version"] != "opencode-admission-check/v1":
        raise QualificationError("corpus schema_version is not opencode-admission-check/v1")
    _non_blank(corpus["corpus_id"], "corpus.corpus_id")

    route = corpus["route"]
    if not isinstance(route, dict):
        raise QualificationError("corpus.route must be an object")
    _keys(route, {"harness", "agent", "profile_id", "provider_model", "provider", "model", "model_override"}, set(), "corpus.route")
    if route["harness"] != "opencode" or route["agent"] != "ao-mechanical-bulk":
        raise QualificationError("corpus route is not the OpenCode mechanical-bulk route")
    if route["provider_model"] != EXPECTED_MODEL or route["provider"] != EXPECTED_PROVIDER or route["model"] != EXPECTED_MODEL_ID:
        raise QualificationError("corpus route must name the exact provider/model")
    if route["model_override"] is not False:
        raise QualificationError("admission check forbids a model override")

    budgets = corpus["budgets"]
    if not isinstance(budgets, dict):
        raise QualificationError("corpus.budgets must be an object")
    _keys(budgets, {"max_cost_usd", "soft_token_ceiling", "hard_token_ceiling", "usage_multiplier_ceiling"}, set(), "corpus.budgets")
    if budgets != {"max_cost_usd": MAX_COST_USD, "soft_token_ceiling": SOFT_TOKEN_CEILING, "hard_token_ceiling": HARD_TOKEN_CEILING, "usage_multiplier_ceiling": MAX_USAGE_MULTIPLIER}:
        raise QualificationError("admission budget does not match the reviewed bounded limits")

    containment = corpus["containment"]
    if not isinstance(containment, dict):
        raise QualificationError("corpus.containment must be an object")
    _keys(containment, {"worker_identity", "exact_groups"}, set(), "corpus.containment")
    if containment["worker_identity"] != EXPECTED_WORKER or containment["exact_groups"] != ["agentworker", "agentdispatch"]:
        raise QualificationError("containment identity or group set is not the exact reviewed set")

    hybrid = manifest.get("hybrid")
    if not isinstance(hybrid, dict) or hybrid.get("enabled") is not True:
        raise QualificationError("repository has not explicitly opted into hybrid dispatch")
    if "mechanical_bulk" not in hybrid.get("worker_routes", []):
        raise QualificationError("repository has not opted into the mechanical_bulk route")


def validate_result(result: dict[str, Any], corpus: dict[str, Any]) -> None:
    """Sanity- and privacy-check a plain run-report; nothing is promoted."""
    _reject_sensitive(result)
    _validate_bounded_strings(result)
    _keys(result, {
        "schema_version", "started_at", "finished_at", "provider", "model", "agent",
        "routable", "export_cross_check", "cost_sane", "usage_baseline", "usage_observed",
        "usage_multiplier", "cost_usd", "tokens", "completion_events", "containment", "pass",
    }, {"run_report"}, "result")
    if result["schema_version"] != "opencode-admission-check-result/v1":
        raise QualificationError("result schema_version is unsupported")
    route = corpus["route"]
    if result["provider"] != route["provider"] or result["model"] != route["model"] or result["agent"] != route["agent"]:
        raise QualificationError("result does not match the reviewed route")
    if result["routable"] is not True:
        raise QualificationError("result must prove the route was actually reachable")
    export = result["export_cross_check"]
    if not isinstance(export, dict) or export.get("providerID") != route["provider"] or export.get("modelID") != route["model"] or export.get("finish") != "stop":
        raise QualificationError("result export cross-check is not exact")
    baseline = _finite_number(result["usage_baseline"], "result.usage_baseline", positive=True)
    observed = _finite_number(result["usage_observed"], "result.usage_observed")
    if observed < 0 or observed > MAX_USAGE_MULTIPLIER * baseline:
        raise QualificationError("result usage exceeds the two-times baseline constraint")
    cost = _finite_number(result["cost_usd"], "result.cost_usd")
    if cost < 0 or cost > corpus["budgets"]["max_cost_usd"]:
        raise QualificationError("result cost exceeds the bounded budget")
    if not isinstance(result["tokens"], int) or isinstance(result["tokens"], bool) or result["tokens"] < 0 or result["tokens"] > corpus["budgets"]["hard_token_ceiling"]:
        raise QualificationError("result token usage is malformed or exceeds the hard ceiling")
    if not isinstance(result["completion_events"], int) or isinstance(result["completion_events"], bool) or result["completion_events"] < 1:
        raise QualificationError("result must record at least one clean completion event")
    containment = result["containment"]
    if not isinstance(containment, dict) or containment.get("status") != "pass" or containment.get("worker_identity") != corpus["containment"]["worker_identity"] or containment.get("exact_groups") != corpus["containment"]["exact_groups"]:
        raise QualificationError("result lacks a passing containment probe matching the reviewed identity")
    if result["pass"] is not True:
        raise QualificationError("result reports a failed check")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--result", type=Path, help="also validate a run-report result JSON file")
    args = parser.parse_args(argv)
    try:
        corpus = _load(args.corpus)
        manifest = _load(args.manifest)
        validate_config(corpus, manifest)
        if args.result is not None:
            validate_result(_load(args.result), corpus)
    except QualificationError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 2
    print(json.dumps({"valid": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
