#!/usr/bin/env python3
"""Normative dependency-free validator for maintenance-envelope/v1."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any
from urllib.parse import urlsplit


CONTRACT_ID = "maintenance-envelope/v1"
TOP_FIELDS = {
    "contract_id", "envelope_id", "plan_ref", "issued_at", "window",
    "operator", "repositories", "command_registry_ref", "command_registry",
    "operations", "jit_fields", "jit_bindings", "start_gate", "steps",
    "abort", "recovery_policy", "audit_reconciliation",
}
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
GIT_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA_REF = re.compile(r"^sha256:[0-9a-f]{64}$")
ARTIFACT_REF = re.compile(r"^artifact:sha256:[0-9a-f]{64}$")
EVENT_REF = re.compile(r"^event:[1-9][0-9]*$")
JIT_NAMES = {"backup_name", "backup_uid", "drain_boundary_utc"}
JIT_SOURCES = {
    "backup_name": "backup-observation",
    "backup_uid": "backup-observation",
    "drain_boundary_utc": "clock-observation",
}
PHASE_ORDER = {"pre-migration": 0, "migration": 1, "post-migration": 2}
RECOVERY_KINDS = ["observation", "requested-command"]
RECOVERY_FORBIDDEN = {"grant", "claim", "approve", "publish", "reconcile", "advance", "bind-jit"}
ABORT_FORBIDDEN = {"delete-migration-ledger", "edit-released-migration", "unreviewed-commit", "recovery-request-authority"}
AUDIT_RECEIPTS = {"command", "effect", "review", "publication", "jit-binding", "start-gate", "abort", "reconciliation"}
AUDIT_OUTCOMES = {"accepted", "rejected", "duplicate", "expired", "aborted", "incomplete"}
AUDIT_REDACT = {"credentials", "claim-tokens", "capability-secrets"}
PLACEHOLDER = re.compile(r"(?:REPLACE_AT_ACTIVATION|\$\{|<[^>]+>)")
SENSITIVE = re.compile(r"(?:claim[_-]?token|credential|password|api[_-]?key|access[_-]?token)\s*[:=]", re.I)


class EnvelopeError(ValueError):
    """Invalid maintenance envelope."""


def _fail(path: Path, field: str, message: str) -> EnvelopeError:
    return EnvelopeError(f"{path}: {field} {message}")


def _object(value: Any, field: str, path: Path, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _fail(path, field, "must be an object")
    missing = required - set(value)
    extra = set(value) - required
    if missing:
        raise _fail(path, field, f"is missing fields: {sorted(missing)}")
    if extra:
        raise _fail(path, field, f"has unexpected fields: {sorted(extra)}")
    return value


def _text(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _fail(path, field, "must be a non-blank string")
    if PLACEHOLDER.search(value) or value in {"HEAD", "main", "latest"}:
        raise _fail(path, field, "must not contain a mutable ref or placeholder")
    if SENSITIVE.search(value):
        raise _fail(path, field, "must not contain authority credentials")
    return value


def _identifier(value: Any, field: str, path: Path) -> str:
    value = _text(value, field, path)
    if not IDENTIFIER.fullmatch(value):
        raise _fail(path, field, "must be an identifier")
    return value


def _datetime(value: Any, field: str, path: Path) -> datetime:
    text = _text(value, field, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise _fail(path, field, "must be an RFC 3339 date-time") from exc
    if parsed.tzinfo is None:
        raise _fail(path, field, "must include an explicit offset")
    return parsed


def _array(value: Any, field: str, path: Path, *, non_empty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (non_empty and not value):
        raise _fail(path, field, "must be a non-empty array" if non_empty else "must be an array")
    return value


def _sorted_unique(values: list[str], field: str, path: Path) -> None:
    if values != sorted(set(values)):
        raise _fail(path, field, "must be sorted and unique")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _relative_path(value: Any, field: str, path: Path) -> str:
    text = _text(value, field, path)
    parsed = PurePosixPath(text)
    if text.startswith("/") or "//" in text or any(part in {"", ".", ".."} for part in parsed.parts):
        raise _fail(path, field, "must be normalized, relative, and traversal-free")
    return text.rstrip("/")


def _immutable_ref(value: Any, field: str, path: Path, *, kinds: set[str] | None = None) -> dict[str, str]:
    ref = _object(value, field, path, {"kind", "source", "revision"})
    kind = _text(ref["kind"], f"{field}.kind", path)
    allowed = kinds or {"git-commit", "artifact", "verification-result", "sprint-event", "release"}
    if kind not in allowed:
        raise _fail(path, f"{field}.kind", f"must be one of {sorted(allowed)}")
    source = _text(ref["source"], f"{field}.source", path)
    revision = _text(ref["revision"], f"{field}.revision", path)
    valid = {
        "git-commit": bool(GIT_COMMIT.fullmatch(revision)),
        "artifact": bool(SHA_REF.fullmatch(revision)),
        "verification-result": bool(SHA_REF.fullmatch(revision)),
        "sprint-event": bool(EVENT_REF.fullmatch(revision)),
        "release": bool(GIT_COMMIT.fullmatch(revision) or SHA_REF.fullmatch(revision)),
    }[kind]
    if not valid:
        raise _fail(path, f"{field}.revision", f"is not an exact {kind} revision")
    return {"kind": kind, "source": source, "revision": revision}


def _repository_url(value: Any, field: str, path: Path) -> str:
    url = _text(value, field, path)
    if url.startswith("git@"):
        if not re.fullmatch(r"git@[A-Za-z0-9.-]+:[A-Za-z0-9._~/-]+(?:\.git)?", url):
            raise _fail(path, field, "must be a credential-free Git URL")
        return url
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise _fail(path, field, "must be a credential-free HTTPS or git@ Git URL")
    return url


def validate_envelope(
    value: Any,
    path: Path,
    *,
    evaluation_time: datetime | None = None,
    evaluation_step_id: str | None = None,
) -> dict[str, Any]:
    envelope = _object(value, "envelope", path, TOP_FIELDS)
    if envelope["contract_id"] != CONTRACT_ID:
        raise _fail(path, "contract_id", f"must be {CONTRACT_ID}")
    _identifier(envelope["envelope_id"], "envelope_id", path)
    if not isinstance(envelope["plan_ref"], str) or not ARTIFACT_REF.fullmatch(envelope["plan_ref"]):
        raise _fail(path, "plan_ref", "must be artifact:sha256:<lowercase digest>")

    issued = _datetime(envelope["issued_at"], "issued_at", path)
    window = _object(envelope["window"], "window", path, {"not_before", "expires_at"})
    not_before = _datetime(window["not_before"], "window.not_before", path)
    expires = _datetime(window["expires_at"], "window.expires_at", path)
    if issued > not_before:
        raise _fail(path, "issued_at", "must not be after window.not_before")
    if expires <= not_before:
        raise _fail(path, "window.expires_at", "must be after window.not_before")
    if expires - not_before > timedelta(hours=24):
        raise _fail(path, "window", "must not exceed 24 hours")
    if (evaluation_time is None) != (evaluation_step_id is None):
        raise _fail(path, "activation", "requires both evaluation time and step id")
    if evaluation_time is not None:
        if evaluation_time.tzinfo is None:
            raise _fail(path, "activation.at", "must include an explicit offset")
        if evaluation_time < not_before:
            raise _fail(path, "activation.at", "is before window.not_before")
        if evaluation_time >= expires:
            raise _fail(path, "activation.at", "is at or after window.expires_at")

    operator = _object(envelope["operator"], "operator", path, {"identity", "decision_ref"})
    _identifier(operator["identity"], "operator.identity", path)
    _immutable_ref(operator["decision_ref"], "operator.decision_ref", path)

    repositories: dict[str, dict[str, str]] = {}
    for index, raw in enumerate(_array(envelope["repositories"], "repositories", path, non_empty=True)):
        field = f"repositories[{index}]"
        repo = _object(raw, field, path, {"id", "url", "commit"})
        repo_id = _identifier(repo["id"], f"{field}.id", path)
        if repo_id in repositories:
            raise _fail(path, "repositories", f"contains duplicate id {repo_id}")
        commit = _text(repo["commit"], f"{field}.commit", path)
        if not GIT_COMMIT.fullmatch(commit):
            raise _fail(path, f"{field}.commit", "must be a full lowercase Git object id")
        repositories[repo_id] = {"id": repo_id, "url": _repository_url(repo["url"], f"{field}.url", path), "commit": commit}

    registry_raw = _array(envelope["command_registry"], "command_registry", path, non_empty=True)
    expected_registry_ref = "artifact:sha256:" + hashlib.sha256(_canonical_bytes(registry_raw)).hexdigest()
    if envelope["command_registry_ref"] != expected_registry_ref:
        raise _fail(path, "command_registry_ref", "must bind the canonical command registry bytes")
    registered_commands: dict[str, tuple[str, ...]] = {}
    for index, raw in enumerate(registry_raw):
        field = f"command_registry[{index}]"
        command = _object(raw, field, path, {"id", "argv"})
        command_id = _identifier(command["id"], f"{field}.id", path)
        if command_id in registered_commands:
            raise _fail(path, "command_registry", f"contains duplicate id {command_id}")
        argv = [_text(arg, f"{field}.argv[]", path) for arg in _array(command["argv"], f"{field}.argv", path, non_empty=True)]
        if len(argv) > 32 or any(len(arg) > 512 for arg in argv):
            raise _fail(path, f"{field}.argv", "must contain at most 32 bounded exact arguments")
        if any(any(character in arg for character in (";", "|", "`", "\n", "\r")) for arg in argv):
            raise _fail(path, f"{field}.argv", "must not contain shell control syntax")
        registered_commands[command_id] = tuple(argv)

    operations: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_array(envelope["operations"], "operations", path, non_empty=True)):
        field = f"operations[{index}]"
        op = _object(raw, field, path, {"id", "owner_repository", "command_id", "allowed_paths", "allowed_commands"})
        op_id = _identifier(op["id"], f"{field}.id", path)
        if op_id in operations:
            raise _fail(path, "operations", f"contains duplicate id {op_id}")
        owner = _identifier(op["owner_repository"], f"{field}.owner_repository", path)
        if owner not in repositories:
            raise _fail(path, f"{field}.owner_repository", "must name a bound repository")
        paths = [_relative_path(item, f"{field}.allowed_paths[]", path) for item in _array(op["allowed_paths"], f"{field}.allowed_paths", path, non_empty=True)]
        commands = [_identifier(item, f"{field}.allowed_commands[]", path) for item in _array(op["allowed_commands"], f"{field}.allowed_commands", path, non_empty=True)]
        _sorted_unique(paths, f"{field}.allowed_paths", path)
        _sorted_unique(commands, f"{field}.allowed_commands", path)
        primary_command = _identifier(op["command_id"], f"{field}.command_id", path)
        if primary_command not in registered_commands or any(command not in registered_commands for command in commands):
            raise _fail(path, field, "must reference only content-bound registered commands")
        if primary_command not in commands:
            raise _fail(path, f"{field}.command_id", "must be included in allowed_commands")
        operations[op_id] = {"owner": owner, "paths": paths, "commands": commands, "command_id": primary_command}

    steps_raw = _array(envelope["steps"], "steps", path, non_empty=True)
    step_ids = []
    for index, raw in enumerate(steps_raw):
        if not isinstance(raw, dict) or "id" not in raw:
            raise _fail(path, f"steps[{index}]", "must contain id")
        step_ids.append(_identifier(raw["id"], f"steps[{index}].id", path))
    if len(step_ids) != len(set(step_ids)):
        raise _fail(path, "steps", "must contain unique ids")

    jit = _array(envelope["jit_fields"], "jit_fields", path, non_empty=True)
    jit_names: set[str] = set()
    jit_definitions: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(jit):
        field = f"jit_fields[{index}]"
        item = _object(raw, field, path, {"name", "source", "pattern", "bind_before_step", "required"})
        name = _text(item["name"], f"{field}.name", path)
        if name not in JIT_NAMES or name in jit_names:
            raise _fail(path, f"{field}.name", "must be one of each fixed v1 JIT field")
        if item["source"] != JIT_SOURCES[name]:
            raise _fail(path, f"{field}.source", f"must be {JIT_SOURCES[name]}")
        pattern = _text(item["pattern"], f"{field}.pattern", path)
        if len(pattern) > 256 or not pattern.startswith("^") or not pattern.endswith("$") or ".*" in pattern or ".+" in pattern:
            raise _fail(path, f"{field}.pattern", "must be bounded and fully anchored without wildcard quantifiers")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise _fail(path, f"{field}.pattern", "must compile") from exc
        if item["bind_before_step"] not in step_ids:
            raise _fail(path, f"{field}.bind_before_step", "must name an exact step")
        if item["required"] is not True:
            raise _fail(path, f"{field}.required", "must be true")
        jit_names.add(name)
        jit_definitions[name] = item
    if jit_names != JIT_NAMES:
        raise _fail(path, "jit_fields", f"must contain exactly {sorted(JIT_NAMES)}")

    bindings = _array(envelope["jit_bindings"], "jit_bindings", path)
    bound_names: set[str] = set()
    for index, raw in enumerate(bindings):
        field = f"jit_bindings[{index}]"
        binding = _object(raw, field, path, {"name", "value", "observed_at", "evidence_ref", "receipt_ref"})
        name = _text(binding["name"], f"{field}.name", path)
        if name not in jit_definitions or name in bound_names:
            raise _fail(path, f"{field}.name", "must bind each fixed JIT field exactly once")
        value_text = _text(binding["value"], f"{field}.value", path)
        if not re.fullmatch(jit_definitions[name]["pattern"], value_text):
            raise _fail(path, f"{field}.value", "must match its frozen JIT pattern")
        observed = _datetime(binding["observed_at"], f"{field}.observed_at", path)
        if observed < not_before or observed >= expires:
            raise _fail(path, f"{field}.observed_at", "must fall inside the maintenance window")
        if evaluation_time is not None and observed > evaluation_time:
            raise _fail(path, f"{field}.observed_at", "must not be after activation evaluation")
        _immutable_ref(binding["evidence_ref"], f"{field}.evidence_ref", path, kinds={"verification-result", "artifact"})
        _immutable_ref(binding["receipt_ref"], f"{field}.receipt_ref", path, kinds={"artifact"})
        bound_names.add(name)
    start = _object(envelope["start_gate"], "start_gate", path, {"plan", "dependent_implementation_sessions", "active_normal_claims"})
    if start["plan"] != "plan-1":
        raise _fail(path, "start_gate.plan", "must be plan-1")
    for name in ("dependent_implementation_sessions", "active_normal_claims"):
        predicate = _object(start[name], f"start_gate.{name}", path, {"expected_count", "observed_at", "evidence_ref", "receipt_ref"})
        if predicate["expected_count"] != 0:
            raise _fail(path, f"start_gate.{name}", "must require evidenced count zero")
        observed = _datetime(predicate["observed_at"], f"start_gate.{name}.observed_at", path)
        if observed < not_before or observed >= expires:
            raise _fail(path, f"start_gate.{name}.observed_at", "must fall inside the maintenance window")
        if evaluation_time is not None:
            if observed > evaluation_time or evaluation_time - observed > timedelta(minutes=5):
                raise _fail(path, f"start_gate.{name}.observed_at", "must be fresh within five minutes before activation")
        _immutable_ref(predicate["evidence_ref"], f"start_gate.{name}.evidence_ref", path, kinds={"verification-result"})
        _immutable_ref(predicate["receipt_ref"], f"start_gate.{name}.receipt_ref", path, kinds={"artifact"})

    prior_ids: set[str] = set()
    repo_heads = {repo_id: repo["commit"] for repo_id, repo in repositories.items()}
    previous_phase = -1
    for index, raw in enumerate(steps_raw):
        field = f"steps[{index}]"
        step = _object(raw, field, path, {"id", "sequence", "repository_id", "base_commit", "commit", "operation_id", "depends_on", "paths", "commands", "reviews", "verification_refs", "publication_ref", "phase"})
        if isinstance(step["sequence"], bool) or step["sequence"] != index + 1:
            raise _fail(path, f"{field}.sequence", "must be contiguous and match array order")
        repo_id = _identifier(step["repository_id"], f"{field}.repository_id", path)
        if repo_id not in repositories:
            raise _fail(path, f"{field}.repository_id", "must name a bound repository")
        base = _text(step["base_commit"], f"{field}.base_commit", path)
        commit = _text(step["commit"], f"{field}.commit", path)
        if not GIT_COMMIT.fullmatch(base) or not GIT_COMMIT.fullmatch(commit) or base == commit:
            raise _fail(path, field, "must bind distinct full base and candidate commits")
        if base != repo_heads[repo_id]:
            raise _fail(path, f"{field}.base_commit", "must equal the exact preceding repository head")
        repo_heads[repo_id] = commit
        op_id = _identifier(step["operation_id"], f"{field}.operation_id", path)
        if op_id not in operations or operations[op_id]["owner"] != repo_id:
            raise _fail(path, f"{field}.operation_id", "must name an allowlisted operation owned by the step repository")
        deps = [_identifier(item, f"{field}.depends_on[]", path) for item in _array(step["depends_on"], f"{field}.depends_on", path)]
        _sorted_unique(deps, f"{field}.depends_on", path)
        if any(dep not in prior_ids for dep in deps):
            raise _fail(path, f"{field}.depends_on", "must reference only earlier steps")
        paths = [_relative_path(item, f"{field}.paths[]", path) for item in _array(step["paths"], f"{field}.paths", path, non_empty=True)]
        commands = [_identifier(item, f"{field}.commands[]", path) for item in _array(step["commands"], f"{field}.commands", path, non_empty=True)]
        _sorted_unique(paths, f"{field}.paths", path)
        _sorted_unique(commands, f"{field}.commands", path)
        allowed_paths = operations[op_id]["paths"]
        if any(not any(item == root or item.startswith(root + "/") for root in allowed_paths) for item in paths):
            raise _fail(path, f"{field}.paths", "must stay within the operation allowlist")
        if not set(commands) <= set(operations[op_id]["commands"]):
            raise _fail(path, f"{field}.commands", "must be a subset of the operation allowlist")
        reviews = _array(step["reviews"], f"{field}.reviews", path, non_empty=True)
        review_refs: set[tuple[str, str, str]] = set()
        for review_index, raw_review in enumerate(reviews):
            review_field = f"{field}.reviews[{review_index}]"
            review = _object(raw_review, review_field, path, {"reviewer", "author", "verdict", "ref"})
            reviewer = _identifier(review["reviewer"], f"{review_field}.reviewer", path)
            author = _identifier(review["author"], f"{review_field}.author", path)
            if reviewer == author or review["verdict"] != "pass":
                raise _fail(path, review_field, "must record an independent passing review")
            ref = _immutable_ref(review["ref"], f"{review_field}.ref", path, kinds={"verification-result"})
            key = (ref["kind"], ref["source"], ref["revision"])
            if key in review_refs:
                raise _fail(path, f"{field}.reviews", "must contain unique review refs")
            review_refs.add(key)
        for verify_index, verify in enumerate(_array(step["verification_refs"], f"{field}.verification_refs", path, non_empty=True)):
            _immutable_ref(verify, f"{field}.verification_refs[{verify_index}]", path, kinds={"verification-result", "artifact"})
        _immutable_ref(step["publication_ref"], f"{field}.publication_ref", path, kinds={"verification-result", "artifact"})
        phase = _text(step["phase"], f"{field}.phase", path)
        if phase not in PHASE_ORDER or PHASE_ORDER[phase] < previous_phase:
            raise _fail(path, f"{field}.phase", "must be known and non-decreasing")
        previous_phase = PHASE_ORDER[phase]
        prior_ids.add(step["id"])

    if evaluation_step_id is not None:
        if evaluation_step_id not in step_ids:
            raise _fail(path, "activation.step", "must name an exact step")
        evaluation_sequence = step_ids.index(evaluation_step_id) + 1
        for name, definition in jit_definitions.items():
            binding_sequence = step_ids.index(definition["bind_before_step"]) + 1
            if evaluation_sequence >= binding_sequence and name not in bound_names:
                raise _fail(
                    path,
                    "jit_bindings",
                    f"must bind {name} at and after step {definition['bind_before_step']}",
                )

    abort = _object(envelope["abort"], "abort", path, {"before_migration", "after_migration", "forbidden"})
    if abort["before_migration"] != "restore-reviewed-pre-migration-state":
        raise _fail(path, "abort.before_migration", "must restore reviewed pre-migration state")
    if abort["after_migration"] not in {"restore-uid-attested-backup", "reviewed-forward-fix"}:
        raise _fail(path, "abort.after_migration", "must use reviewed forward recovery")
    if set(_array(abort["forbidden"], "abort.forbidden", path)) != ABORT_FORBIDDEN:
        raise _fail(path, "abort.forbidden", f"must contain exactly {sorted(ABORT_FORBIDDEN)}")

    recovery = _object(envelope["recovery_policy"], "recovery_policy", path, {"record_kinds", "authority", "forbidden_uses"})
    if recovery["record_kinds"] != RECOVERY_KINDS or recovery["authority"] != "none":
        raise _fail(path, "recovery_policy", "must keep observation/requested-command records non-authoritative")
    forbidden_uses = _array(recovery["forbidden_uses"], "recovery_policy.forbidden_uses", path)
    _sorted_unique(forbidden_uses, "recovery_policy.forbidden_uses", path)
    if set(forbidden_uses) != RECOVERY_FORBIDDEN:
        raise _fail(path, "recovery_policy.forbidden_uses", f"must contain exactly {sorted(RECOVERY_FORBIDDEN)}")

    audit = _object(envelope["audit_reconciliation"], "audit_reconciliation", path, {"incident_correlation_required", "immutable_receipts", "required_outcomes", "redact", "retention", "export_required", "independent_review_required"})
    if audit["incident_correlation_required"] is not True or audit["export_required"] is not True or audit["independent_review_required"] is not True:
        raise _fail(path, "audit_reconciliation", "must require correlation, export, and independent review")
    for field, required in (("immutable_receipts", AUDIT_RECEIPTS), ("required_outcomes", AUDIT_OUTCOMES), ("redact", AUDIT_REDACT)):
        values = _array(audit[field], f"audit_reconciliation.{field}", path)
        _sorted_unique(values, f"audit_reconciliation.{field}", path)
        if set(values) != required:
            raise _fail(path, f"audit_reconciliation.{field}", f"must contain exactly {sorted(required)}")
    if audit["retention"] not in {"append-only-export", "content-addressed-export"}:
        raise _fail(path, "audit_reconciliation.retention", "must be an immutable export policy")
    return envelope


def validate_file(
    path: Path,
    *,
    evaluation_time: datetime | None = None,
    evaluation_step_id: str | None = None,
) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EnvelopeError(f"{path}: cannot read canonical JSON: {exc}") from exc
    validate_envelope(value, path, evaluation_time=evaluation_time, evaluation_step_id=evaluation_step_id)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--structural", action="store_true", help="validate frozen structure without asserting activation readiness")
    mode.add_argument("--at", help="activation evaluation time as RFC 3339; rejects early or expired envelopes")
    parser.add_argument("--step", help="exact step about to execute; required with --at")
    args = parser.parse_args(argv)
    try:
        evaluation_time = None
        if args.at is not None:
            if args.step is None:
                raise EnvelopeError("--step is required with --at")
            evaluation_time = _datetime(args.at, "--at", Path("<cli>"))
        elif args.step is not None:
            raise EnvelopeError("--step is allowed only with --at")
        results = [
            (path, validate_file(path, evaluation_time=evaluation_time, evaluation_step_id=args.step))
            for path in args.paths
        ]
    except EnvelopeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for path, digest in results:
        print(json.dumps({"contract_id": CONTRACT_ID, "path": str(path), "sha256": digest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
