#!/usr/bin/env python3
"""Dependency-free validation for harness implementation profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


SCHEMA_VERSION = "harness-profile/v1"
PROFILE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SEMANTIC_ADAPTER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
VERSION = re.compile(r"^\d+\.\d+\.\d+$")
WORKER_IDENTITY = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")
STATES = {"preflight_observed", "qualified", "superseded"}
REQUIRED_RECEIPT_FIELDS = {
    "semantic_adapter", "profile_id", "cli_version", "executable_fingerprint",
    "channel_revision", "profile_digest", "config_digest", "overlay_digest",
    "provider_model", "worker_identity", "capability_probe_results",
    "lifecycle_probe_results",
}
REQUIRED_LIFECYCLE_PROBES = {
    "json-events", "stable-session-identity", "session-continuation",
    "contained-identity", "no-tools-finalizer",
}
REQUIRED_PREQUALIFICATION_EVIDENCE = {
    "contained-identity", "provider-qualification",
}


def _error(path: Path, field: str, message: str) -> ValueError:
    return ValueError(f"{path}: {field} {message}")


def _object(value: Any, field: str, path: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _error(path, field, "must be an object")
    return value


def _keys(value: dict[str, Any], field: str, path: Path, required: set[str]) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required)
    if missing:
        raise _error(path, field, f"is missing fields: {', '.join(missing)}")
    if extra:
        raise _error(path, field, f"has unexpected fields: {', '.join(extra)}")


def _text(value: Any, field: str, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _error(path, field, "must be a non-blank string")
    return value


def _unique_texts(value: Any, field: str, path: Path, *, non_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or (non_empty and not value):
        raise _error(path, field, "must be a non-empty array" if non_empty else "must be an array")
    result = [_text(item, f"{field}[{index}]", path) for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise _error(path, field, "must not contain duplicates")
    return result


def validate_profile(value: dict[str, Any], path: Path) -> None:
    _keys(value, "profile", path, {
        "schema_version", "profile_id", "semantic_adapter", "host_class", "implementation",
        "worker_identity", "invocation", "policy", "lifecycle", "required_probes", "receipt_fields",
        "qualification",
    })
    if value["schema_version"] != SCHEMA_VERSION:
        raise _error(path, "schema_version", f"must be {SCHEMA_VERSION}")
    if not PROFILE_ID.fullmatch(_text(value["profile_id"], "profile_id", path)):
        raise _error(path, "profile_id", "must be a portable identifier")
    if not SEMANTIC_ADAPTER.fullmatch(_text(value["semantic_adapter"], "semantic_adapter", path)):
        raise _error(path, "semantic_adapter", "must be a semantic adapter identifier")
    _text(value["host_class"], "host_class", path)
    if not WORKER_IDENTITY.fullmatch(_text(value["worker_identity"], "worker_identity", path)):
        raise _error(path, "worker_identity", "must be a safe local username")

    implementation = _object(value["implementation"], "implementation", path)
    _keys(implementation, "implementation", path, {"channel", "package", "cli_version"})
    _text(implementation["channel"], "implementation.channel", path)
    _text(implementation["package"], "implementation.package", path)
    if not VERSION.fullmatch(_text(implementation["cli_version"], "implementation.cli_version", path)):
        raise _error(path, "implementation.cli_version", "must be a semantic version")

    invocation = _object(value["invocation"], "invocation", path)
    _keys(invocation, "invocation", path, {"command", "message_before_file", "stdin"})
    _unique_texts(invocation["command"], "invocation.command", path)
    if not isinstance(invocation["message_before_file"], bool):
        raise _error(path, "invocation.message_before_file", "must be boolean")
    if invocation["stdin"] != "closed":
        raise _error(path, "invocation.stdin", "must be closed")

    policy = _object(value["policy"], "policy", path)
    _keys(policy, "policy", path, {"config_file", "overlay_transport"})
    _text(policy["config_file"], "policy.config_file", path)
    if policy["overlay_transport"] != "OPENCODE_CONFIG_CONTENT":
        raise _error(path, "policy.overlay_transport", "must be OPENCODE_CONFIG_CONTENT")

    lifecycle = _object(value["lifecycle"], "lifecycle", path)
    _keys(lifecycle, "lifecycle", path, {
        "event_format", "event_stream", "session_id_field", "continuation",
        "contained_identity", "finalizer",
    })
    if lifecycle["event_format"] != "json":
        raise _error(path, "lifecycle.event_format", "must be json")
    if lifecycle["event_stream"] != "stdout":
        raise _error(path, "lifecycle.event_stream", "must be stdout")
    if lifecycle["session_id_field"] != "properties.sessionID":
        raise _error(path, "lifecycle.session_id_field", "must be properties.sessionID")

    continuation = _object(lifecycle["continuation"], "lifecycle.continuation", path)
    _keys(continuation, "lifecycle.continuation", path, {
        "mode", "session_flag", "continue_flag", "fork",
    })
    if continuation != {
        "mode": "same-session",
        "session_flag": "--session",
        "continue_flag": "--continue",
        "fork": False,
    }:
        raise _error(path, "lifecycle.continuation", "must use same-session continuation without forking")

    contained = _object(lifecycle["contained_identity"], "lifecycle.contained_identity", path)
    _keys(contained, "lifecycle.contained_identity", path, {
        "worker_user", "enforced_by", "probe",
    })
    if contained["worker_user"] != value["worker_identity"]:
        raise _error(path, "lifecycle.contained_identity.worker_user", "must match worker_identity")
    if contained["enforced_by"] != "filesystem-and-uid":
        raise _error(path, "lifecycle.contained_identity.enforced_by", "must be filesystem-and-uid")
    if contained["probe"] != "contained-identity":
        raise _error(path, "lifecycle.contained_identity.probe", "must name contained-identity")

    finalizer = _object(lifecycle["finalizer"], "lifecycle.finalizer", path)
    _keys(finalizer, "lifecycle.finalizer", path, {"agent", "tools", "same_session"})
    if finalizer["agent"] != "ao-finalizer":
        raise _error(path, "lifecycle.finalizer.agent", "must be ao-finalizer")
    if finalizer["tools"] != []:
        raise _error(path, "lifecycle.finalizer.tools", "must be empty")
    if finalizer["same_session"] is not True:
        raise _error(path, "lifecycle.finalizer.same_session", "must be true")

    required_probes = set(_unique_texts(value["required_probes"], "required_probes", path))
    missing_lifecycle = sorted(REQUIRED_LIFECYCLE_PROBES - required_probes)
    if missing_lifecycle:
        raise _error(path, "required_probes", f"is missing lifecycle evidence: {', '.join(missing_lifecycle)}")
    receipt_fields = set(_unique_texts(value["receipt_fields"], "receipt_fields", path))
    missing_receipt = sorted(REQUIRED_RECEIPT_FIELDS - receipt_fields)
    if missing_receipt:
        raise _error(path, "receipt_fields", f"is missing required evidence: {', '.join(missing_receipt)}")

    qualification = _object(value["qualification"], "qualification", path)
    _keys(qualification, "qualification", path, {"state", "blocking_probes"})
    if qualification["state"] not in STATES:
        raise _error(path, "qualification.state", f"must be one of: {', '.join(sorted(STATES))}")
    blocking = _unique_texts(qualification["blocking_probes"], "qualification.blocking_probes", path, non_empty=False)
    if qualification["state"] == "qualified" and blocking:
        raise _error(path, "qualification.blocking_probes", "must be empty when qualified")
    if qualification["state"] != "qualified" and not blocking:
        raise _error(path, "qualification.blocking_probes", "must name an outstanding probe")
    if qualification["state"] == "preflight_observed":
        missing_evidence = sorted(REQUIRED_PREQUALIFICATION_EVIDENCE - set(blocking))
        if missing_evidence:
            raise _error(
                path,
                "qualification.blocking_probes",
                f"must name outstanding contained/provider evidence: {', '.join(missing_evidence)}",
            )


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return _object(value, "profile", path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).parents[1] / "harness-profiles")
    args = parser.parse_args()
    paths = args.paths or sorted(args.root.glob("*.json"))
    paths = [path for path in paths if path.name != "harness-profile.schema.json"]
    if not paths:
        parser.error("no harness profile files found")
    profile_ids: set[str] = set()
    for path in paths:
        profile = load(path)
        validate_profile(profile, path)
        if profile["profile_id"] in profile_ids:
            raise ValueError(f"{path}: duplicate profile_id {profile['profile_id']!r}")
        profile_ids.add(profile["profile_id"])
    print(f"validated {len(paths)} harness profile(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
