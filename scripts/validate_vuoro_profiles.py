#!/usr/bin/env python3
"""Dependency-free validation for Vuoro environment records and client profiles.

The profiles deliberately contain an identity *reference* rather than bearer
material.  This validator is a cutover gate: it prevents a host profile from
quietly pointing at production or regressing to a PostgreSQL URL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


#: TS-10 interim fence: legacy direct-DSN writers are fenced by mechanism at
#: S5 (`docs/plans/2026-09-17-target-state.md`); until then this pattern set
#: is the check that no shared profile or `.envrc` selects a direct
#: PostgreSQL backend. Retire this constant and `dsn_fence_violations` when
#: S5 lands.
DIRECT_PATTERNS = (
    re.compile(r"\bSPRINTCTL_URL\b"),
    re.compile(r"sprintctl-cnpg-main-app"),
    re.compile(r"\bsprintctl-pg\b"),
    re.compile(r"SPRINTCTL_BACKEND\s*=\s*(?:\"|')?remote\b"),
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
)

TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
AUTHORITY = re.compile(r"^[a-z0-9][a-z0-9._-]*:[a-z0-9][a-z0-9._-]*$")
WORK_AUTHORITIES = {
    "work:read",
    "work:lifecycle",
    "work:evidence",
    "work:batch",
    "work:project-read",
    "work:project-write",
    "work:pilot-read",
}
WORKSTATION_OPERATOR_AUTHORITIES = WORK_AUTHORITIES | {"work:sprint"}
# Separately commissioned evidence producers, not operators: each profile id
# is bound to one source environment and exactly the evidence authorities.
NATIVE_EVIDENCE_PROFILE_ID = "workstation-mi1-native-vuoro-shared"
NATIVE_EVIDENCE_AUTHORITIES = {"work:read", "work:evidence"}
NATIVE_EVIDENCE_PROFILES = {
    NATIVE_EVIDENCE_PROFILE_ID: "workstation",
    # Agent directory/inbox identities (vuoro agent-coordination M2c).
    "workstation-inbox-native-vuoro-shared": "workstation",
    "devbox-inbox-native-vuoro-shared": "devbox",
}


class ProfileError(ValueError):
    pass


def _load(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"{path}: cannot load JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ProfileError(f"{path}: top-level value must be an object")
    return value


def _exact(value: dict[str, object], expected: set[str], path: Path) -> None:
    actual = set(value)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual))
        extra = ", ".join(sorted(actual - expected))
        detail = ", ".join(part for part in (f"missing {missing}" if missing else "", f"unknown {extra}" if extra else "") if part)
        raise ProfileError(f"{path}: invalid fields ({detail})")


def _token(value: object, field: str, path: Path) -> str:
    if not isinstance(value, str) or not TOKEN.fullmatch(value):
        raise ProfileError(f"{path}: {field} must be a lower-case token")
    return value


def _strings(value: object, field: str, path: Path, pattern: re.Pattern[str]) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and pattern.fullmatch(item) for item in value):
        raise ProfileError(f"{path}: {field} must be a non-empty array of valid values")
    if len(set(value)) != len(value):
        raise ProfileError(f"{path}: {field} must not contain duplicates")
    return value


ENVIRONMENT_REQUIRED = {"schema_version", "id", "environment_class", "revision", "roles", "constraints", "capabilities", "runbook_refs", "identity_bindings"}
ENVIRONMENT_OPTIONAL = {"authority", "tooling", "trust_roots", "credential_broker"}
#: Records with this role are a maintained runner composition: they must state
#: their bounded authority and pinned tooling (bounded-execution-environment.md).
RUNNER_ROLE = "unattended-agent-host"
OPERATION = re.compile(r"^[a-z0-9][a-z0-9._-]*\*?$")
TOOL_DIGEST = re.compile(r"^(sha256:[0-9a-f]{64}|git:[0-9a-f]{40}|nix:[0-9a-z]{32})$")
SHA256_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
TRUST_ROOT_KINDS = {"tls-ca-bundle", "vuoro-endpoint", "credential-broker"}
#: cred-broker `Capability` enum (cred-broker src/cred_broker/models.py).
BROKER_CAPABILITIES = {
    "repo.read", "repo.write", "repo.create", "repo.admin", "repo.delete",
    "pr.read", "pr.manage", "pr.merge", "release.read", "release.publish",
    "deploy.read", "deploy.nonprod", "deploy.prod", "kubernetes.edit",
}
MAX_EXECUTION_TTL_SECONDS = 86400


def operation_matches(pattern: str, operation: str) -> bool:
    """One trailing ``*`` matches any suffix; otherwise the match is exact."""
    if pattern.endswith("*"):
        return operation.startswith(pattern[:-1])
    return operation == pattern


def _patterns_overlap(a: str, b: str) -> bool:
    if a.endswith("*") and b.endswith("*"):
        return a[:-1].startswith(b[:-1]) or b[:-1].startswith(a[:-1])
    if a.endswith("*"):
        return operation_matches(a, b)
    if b.endswith("*"):
        return operation_matches(b, a)
    return a == b


def _exact_object(value: object, expected: set[str], field: str, path: Path, optional: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict) or not expected <= set(value) <= expected | optional:
        raise ProfileError(f"{path}: {field} must contain {sorted(expected)}")
    return value


def validate_authority(value: object, path: Path) -> dict:
    authority = _exact_object(value, {"standing_read", "scoped_execution", "explicit_approval"}, "authority", path)
    read = _exact_object(authority["standing_read"], {"operations"}, "authority.standing_read", path)
    read_ops = _strings(read["operations"], "authority.standing_read.operations", path, OPERATION)
    scoped = _exact_object(
        authority["scoped_execution"],
        {"repositories", "operations", "publication_operation", "max_ttl_seconds"},
        "authority.scoped_execution", path,
    )
    _strings(scoped["repositories"], "authority.scoped_execution.repositories", path, TOKEN)
    scoped_ops = _strings(scoped["operations"], "authority.scoped_execution.operations", path, OPERATION)
    publication = scoped["publication_operation"]
    if not isinstance(publication, str) or not OPERATION.fullmatch(publication) or publication.endswith("*"):
        raise ProfileError(f"{path}: authority.scoped_execution.publication_operation must name one operation")
    if not any(operation_matches(p, publication) for p in scoped_ops):
        raise ProfileError(f"{path}: publication_operation {publication} is not within scoped_execution.operations")
    ttl = scoped["max_ttl_seconds"]
    if not isinstance(ttl, int) or isinstance(ttl, bool) or not 1 <= ttl <= MAX_EXECUTION_TTL_SECONDS:
        raise ProfileError(f"{path}: authority.scoped_execution.max_ttl_seconds must be 1..{MAX_EXECUTION_TTL_SECONDS}")
    approvals = authority["explicit_approval"]
    if not isinstance(approvals, list) or not approvals:
        raise ProfileError(f"{path}: authority.explicit_approval must be a non-empty array")
    transitions: set[str] = set()
    for index, entry in enumerate(approvals):
        field = f"authority.explicit_approval[{index}]"
        entry = _exact_object(entry, {"transition", "operations"}, field, path)
        transitions.add(_token(entry["transition"], f"{field}.transition", path))
        for op in _strings(entry["operations"], f"{field}.operations", path, OPERATION):
            granted = [p for p in read_ops + scoped_ops if _patterns_overlap(p, op)]
            if granted:
                raise ProfileError(f"{path}: {field} operation {op} is also granted without approval by {granted}")
    if len(transitions) != len(approvals):
        raise ProfileError(f"{path}: authority.explicit_approval transitions must be unique")
    return authority


def _validate_tooling(value: object, path: Path) -> None:
    if not isinstance(value, list) or not value:
        raise ProfileError(f"{path}: tooling must be a non-empty array")
    names = set()
    for index, tool in enumerate(value):
        field = f"tooling[{index}]"
        tool = _exact_object(tool, {"name", "version", "source", "digest"}, field, path)
        names.add(_token(tool["name"], f"{field}.name", path))
        for key in ("version", "source"):
            if not isinstance(tool[key], str) or not tool[key]:
                raise ProfileError(f"{path}: {field}.{key} must be a non-empty string")
        if not isinstance(tool["digest"], str) or not TOOL_DIGEST.fullmatch(tool["digest"]):
            raise ProfileError(f"{path}: {field}.digest must be sha256:, git: or nix: pinned")
    if len(names) != len(value):
        raise ProfileError(f"{path}: tooling names must be unique")


def _validate_trust_roots(value: object, path: Path) -> None:
    if not isinstance(value, list) or not value:
        raise ProfileError(f"{path}: trust_roots must be a non-empty array")
    for index, root in enumerate(value):
        field = f"trust_roots[{index}]"
        root = _exact_object(root, {"id", "kind", "ref"}, field, path, optional={"digest"})
        _token(root["id"], f"{field}.id", path)
        if root["kind"] not in TRUST_ROOT_KINDS:
            raise ProfileError(f"{path}: {field}.kind must be one of {sorted(TRUST_ROOT_KINDS)}")
        if not isinstance(root["ref"], str) or not root["ref"]:
            raise ProfileError(f"{path}: {field}.ref must be a non-empty string")
        if "digest" in root and (not isinstance(root["digest"], str) or not SHA256_DIGEST.fullmatch(root["digest"])):
            raise ProfileError(f"{path}: {field}.digest must be sha256:<64 hex>")


def _validate_credential_broker(value: object, path: Path) -> None:
    broker = _exact_object(value, {"host_profile", "subject", "capabilities"}, "credential_broker", path)
    _token(broker["host_profile"], "credential_broker.host_profile", path)
    if not isinstance(broker["subject"], str) or not re.fullmatch(r"[a-z0-9_]+", broker["subject"]):
        raise ProfileError(f"{path}: credential_broker.subject must be a broker subject id")
    if not isinstance(broker["capabilities"], list):
        raise ProfileError(f"{path}: credential_broker.capabilities must be an array")
    for index, entry in enumerate(broker["capabilities"]):
        field = f"credential_broker.capabilities[{index}]"
        entry = _exact_object(entry, {"capability", "target", "bound"}, field, path)
        if entry["capability"] not in BROKER_CAPABILITIES:
            raise ProfileError(f"{path}: {field}.capability is not a cred-broker capability id")
        if not isinstance(entry["target"], str) or not entry["target"]:
            raise ProfileError(f"{path}: {field}.target must be a non-empty string")
        if not isinstance(entry["bound"], bool):
            raise ProfileError(f"{path}: {field}.bound must be a boolean")


def validate_environment(path: Path) -> dict[str, object]:
    value = _load(path)
    _exact({k: v for k, v in value.items() if k not in ENVIRONMENT_OPTIONAL}, ENVIRONMENT_REQUIRED, path)
    if value["schema_version"] != "environment-record/v1":
        raise ProfileError(f"{path}: schema_version must be environment-record/v1")
    _token(value["id"], "id", path)
    if value["environment_class"] not in {"local", "development", "production", "recovery"}:
        raise ProfileError(f"{path}: invalid environment_class")
    if not isinstance(value["revision"], int) or isinstance(value["revision"], bool) or value["revision"] < 1:
        raise ProfileError(f"{path}: revision must be a positive integer")
    for field in ("roles", "constraints", "capabilities"):
        _strings(value[field], field, path, TOKEN)
    if not isinstance(value["runbook_refs"], list) or not value["runbook_refs"] or not all(isinstance(item, str) and item for item in value["runbook_refs"]):
        raise ProfileError(f"{path}: runbook_refs must be a non-empty string array")
    bindings = value["identity_bindings"]
    if not isinstance(bindings, list) or not bindings:
        raise ProfileError(f"{path}: identity_bindings must be non-empty")
    if RUNNER_ROLE in value["roles"]:
        for key in ("authority", "tooling"):
            if key not in value:
                raise ProfileError(f"{path}: an {RUNNER_ROLE} record must declare {key}")
    if "authority" in value:
        validate_authority(value["authority"], path)
    if "tooling" in value:
        _validate_tooling(value["tooling"], path)
    if "trust_roots" in value:
        _validate_trust_roots(value["trust_roots"], path)
    if "credential_broker" in value:
        _validate_credential_broker(value["credential_broker"], path)
    return value


def validate_profile(path: Path, environment: dict[str, object]) -> dict[str, object]:
    value = _load(path)
    _exact(value, {"schema_version", "id", "revision", "source_environment_id", "target", "credential_ref", "required_authorities", "production_endpoint_denied"}, path)
    if value["schema_version"] != "vuoro-client-profile/v1":
        raise ProfileError(f"{path}: schema_version must be vuoro-client-profile/v1")
    _token(value["id"], "id", path)
    if not isinstance(value["revision"], int) or isinstance(value["revision"], bool) or value["revision"] < 1:
        raise ProfileError(f"{path}: revision must be a positive integer")
    if value["source_environment_id"] != environment["id"]:
        raise ProfileError(f"{path}: source_environment_id does not match {environment['id']}")
    target = value["target"]
    if not isinstance(target, dict) or set(target) != {"environment_id", "environment_class", "endpoint"}:
        raise ProfileError(f"{path}: target must contain only environment_id, environment_class, and endpoint")
    _token(target["environment_id"], "target.environment_id", path)
    endpoint = target["endpoint"]
    parsed = urlparse(endpoint) if isinstance(endpoint, str) else None
    if parsed is None or parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ProfileError(f"{path}: target.endpoint must be a credential-free HTTPS URL")
    if target["environment_class"] != "production" or target["environment_id"] != "vuoro-shared":
        raise ProfileError(f"{path}: only the primary vuoro-shared production target is allowed")
    credential_ref = value["credential_ref"]
    if not isinstance(credential_ref, str) or not re.fullmatch(r"file:(?:/|~/).+", credential_ref):
        raise ProfileError(f"{path}: credential_ref must be a local file reference, never a token or URL")
    authorities = set(_strings(value["required_authorities"], "required_authorities", path, AUTHORITY))
    expected_authorities = (
        WORKSTATION_OPERATOR_AUTHORITIES
        if environment["id"] == "workstation"
        else WORK_AUTHORITIES
    )
    if value["id"] in NATIVE_EVIDENCE_PROFILES:
        bound = NATIVE_EVIDENCE_PROFILES[value["id"]]
        if environment["id"] != bound:
            raise ProfileError(f"{path}: native evidence profile is bound to {bound}")
        expected_authorities = NATIVE_EVIDENCE_AUTHORITIES
    missing = expected_authorities - authorities
    extra = authorities - expected_authorities
    if missing or extra:
        raise ProfileError(f"{path}: authorities must exactly match the declared profile purpose; missing={sorted(missing)} extra={sorted(extra)}")
    if value["production_endpoint_denied"] is not False:
        raise ProfileError(f"{path}: production_endpoint_denied must be false for the primary authority")
    return value


def _executable_shell_text(text: str) -> str:
    """Return shell text with comments removed.

    The DSN fence audits the configuration an interactive shell can execute.
    A ``#`` inside a quoted value is data, not a comment, so a line-oriented
    ``startswith('#')`` filter is insufficient here.
    """
    lines: list[str] = []
    for line in text.splitlines():
        quote: str | None = None
        escaped = False
        kept: list[str] = []
        for character in line:
            if escaped:
                kept.append(character)
                escaped = False
                continue
            if character == "\\" and quote != "'":
                kept.append(character)
                escaped = True
                continue
            if character in {"'", '"'}:
                if quote is None:
                    quote = character
                elif quote == character:
                    quote = None
                kept.append(character)
                continue
            if character == "#" and quote is None:
                break
            kept.append(character)
        lines.append("".join(kept))
    return "\n".join(lines)


def dsn_fence_violations(path: Path) -> list[str]:
    """Errors when ``path`` selects a direct PostgreSQL backend (TS-10 interim fence).

    Scans a repo's ``.envrc`` or a shared profile file for ``SPRINTCTL_URL``, a
    direct ``postgres(ql)://`` DSN, or the cnpg/backend selectors that point at
    one, so a served-mode workstation cannot quietly regress to a direct
    writer. ``unset SPRINTCTL_URL`` is prescribed served-mode cleanup, not
    direct-backend wiring, and is excluded from the scan.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: cannot read: {exc}"]
    scannable = text if path.suffix == ".json" else _executable_shell_text(text)
    scan_text = "\n".join(
        line
        for line in scannable.splitlines()
        if not re.match(r"\s*unset\s+SPRINTCTL_URL\s*$", line)
    )
    errors: list[str] = []
    for pattern in DIRECT_PATTERNS:
        if pattern.search(scan_text):
            errors.append(f"{path}: contains prohibited direct-backend wiring matching {pattern.pattern!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path)
    parser.add_argument("--profile", action="append", type=Path, default=[])
    parser.add_argument(
        "--check-dsn-fence",
        dest="dsn_fence_paths",
        action="append",
        type=Path,
        default=[],
        help="a .envrc or shared profile file to scan for direct-backend DSN wiring (TS-10 interim fence); repeatable",
    )
    args = parser.parse_args()
    if not args.environment and not args.dsn_fence_paths:
        parser.error("at least one of --environment or --check-dsn-fence is required")
    errors: list[str] = []
    try:
        if args.environment:
            environment = validate_environment(args.environment)
            for profile_path in args.profile:
                profile = validate_profile(profile_path, environment)
                print(f"ok {profile_path} -> {profile['target']['environment_id']} as {profile['id']}")
            print(f"ok {args.environment}")
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for fence_path in args.dsn_fence_paths:
        violations = dsn_fence_violations(fence_path)
        errors.extend(violations)
        if not violations:
            print(f"ok {fence_path}: no direct-backend wiring")
    if errors:
        print("DSN fence violations:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
