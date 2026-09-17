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
    "work:claim",
    "work:lifecycle",
    "work:evidence",
    "work:batch",
    "work:project-read",
    "work:project-write",
    "work:pilot-read",
}
WORKSTATION_OPERATOR_AUTHORITIES = WORK_AUTHORITIES | {"work:sprint"}


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


def validate_environment(path: Path) -> dict[str, object]:
    value = _load(path)
    _exact(value, {"schema_version", "id", "environment_class", "revision", "roles", "constraints", "capabilities", "runbook_refs", "identity_bindings"}, path)
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
    missing = expected_authorities - authorities
    extra = authorities - expected_authorities
    if missing or extra:
        raise ProfileError(f"{path}: authorities must exactly cover current served work operations; missing={sorted(missing)} extra={sorted(extra)}")
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
