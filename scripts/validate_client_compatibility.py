#!/usr/bin/env python3
"""Validate redacted client evidence offline; never infer vendor compatibility."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

SURFACES = {
    "claude_ui": {"ui_oauth"}, "claude_api": {"api_bearer"},
    "claude_code": {"local_cli_oauth"}, "chatgpt_ui": {"ui_oauth"},
    "codex_local": {"local_cli", "local_app"}, "codex_cloud": {"hosted"},
}
STAGES = {"discover", "consent", "call", "refresh", "reconnect"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def fields(value: object, names: set[str]) -> dict:
    require(isinstance(value, dict) and set(value) == names, "unexpected or missing fields")
    return value


def stamp(value: object) -> datetime:
    require(isinstance(value, str), "timestamp must be aware UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("timestamp must be aware UTC") from None
    require(parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0,
            "timestamp must be aware UTC")
    return parsed


def digest(value: object) -> None:
    require(isinstance(value, str) and bool(HEX.fullmatch(value)), "invalid SHA-256")


def pairs(items: list[tuple]) -> dict:
    require(len({key for key, _ in items}) == len(items), "duplicate JSON field")
    return dict(items)


def load(path: Path) -> dict:
    require(path.stat().st_size <= 1_048_576, "input exceeds 1 MiB")
    blob = path.read_bytes()
    require(len(blob) <= 1_048_576, "input exceeds 1 MiB")
    return json.loads(blob, object_pairs_hook=pairs)


def receipt(reference: object, root: Path) -> dict:
    ref = fields(reference, {"path", "sha256"})
    digest(ref["sha256"])
    require(isinstance(ref["path"], str), "receipt path must be relative")
    rel = Path(ref["path"])
    require(not rel.is_absolute() and ".." not in rel.parts, "receipt path must be relative")
    path = (root / rel).resolve()
    require(path.is_relative_to(root.resolve()), "receipt escapes evidence root")
    require(path.stat().st_size <= 1_048_576, "receipt exceeds 1 MiB")
    blob = path.read_bytes()
    require(len(blob) <= 1_048_576, "receipt exceeds 1 MiB")
    require(hashlib.sha256(blob).hexdigest() == ref["sha256"], "receipt digest changed")
    row = fields(json.loads(blob, object_pairs_hook=pairs), {"schema", "kind", "surface", "mode", "version", "stage",
                             "recorded_at", "source_observed_at", "endpoint", "outcome", "tools", "tool",
                             "request_sha256", "response_sha256", "error_code", "auth_method",
                             "workspace_id", "repo_id", "consent_scopes"})
    require(row["schema"] == "client-observation/v1", "unsupported receipt schema")
    require(row["kind"] in {"client_trace", "connection_health", "configuration", "protocol_conformance"},
            "invalid observation kind")
    require(row["surface"] in SURFACES and row["mode"] in SURFACES[row["surface"]], "invalid client mode")
    require(row["version"] is None or (isinstance(row["version"], str) and bool(NAME.fullmatch(row["version"]))), "invalid version")
    require(row["stage"] in STAGES and row["outcome"] in {"pass", "refused"}, "invalid receipt stage/outcome")
    recorded = stamp(row["recorded_at"])
    if row["source_observed_at"] is not None:
        require(stamp(row["source_observed_at"]) <= recorded, "source event is newer than receipt assembly")
    require(isinstance(row["tools"], list) and all(isinstance(x, str) and NAME.fullmatch(x) for x in row["tools"])
            and len(row["tools"]) == len(set(row["tools"])), "invalid tool inventory")
    for key in ("tool", "error_code"):
        require(row[key] is None or (isinstance(row[key], str) and bool(NAME.fullmatch(row[key]))), "invalid redacted identifier")
    require(row["auth_method"] in {None, "oauth", "api_bearer"}, "invalid auth method")
    for key in ("workspace_id", "repo_id"):
        require(row[key] is None or (isinstance(row[key], str) and bool(NAME.fullmatch(row[key]))), "invalid scope identifier")
    require(isinstance(row["consent_scopes"], list) and all(isinstance(x, str) and NAME.fullmatch(x) for x in row["consent_scopes"])
            and len(row["consent_scopes"]) == len(set(row["consent_scopes"])), "invalid consent scopes")
    for key in ("request_sha256", "response_sha256"):
        if row[key] is not None:
            digest(row[key])
    return row


def validate(matrix: object, root: Path) -> dict:
    doc = fields(matrix, {"schema", "as_of", "endpoint", "clients"})
    require(doc["schema"] == "client-compatibility/v1", "unsupported matrix schema")
    cutoff = stamp(doc["as_of"])
    require(doc["endpoint"] == "https://api.vuoro.cloud/mcp", "unexpected Cloud MCP endpoint")
    require(isinstance(doc["clients"], list), "clients must be an array")
    seen: set[tuple[str, str]] = set()
    result = []
    for entry in doc["clients"]:
        client = fields(entry, {"surface", "mode", "version", "stages"})
        surface = client["surface"]
        require(surface in SURFACES, "invalid surface")
        require(client["mode"] in SURFACES[surface], "invalid client mode")
        pair = (surface, client["mode"])
        require(pair not in seen, "duplicate surface mode")
        seen.add(pair)
        require(client["version"] is None or (isinstance(client["version"], str) and bool(NAME.fullmatch(client["version"]))), "invalid version")
        stages = fields(client["stages"], STAGES)
        reported = []
        unknown = []
        for stage, value in stages.items():
            observation = fields(value, {"status", "reason", "receipt"})
            status = observation["status"]
            require(status in {"pass", "refused", "unavailable", "untested"}, "invalid status")
            # Reasons are bounded categories, never arbitrary logs/credentials.
            require(isinstance(observation["reason"], str) and bool(NAME.fullmatch(observation["reason"])), "invalid reason category")
            if status in {"unavailable", "untested"}:
                require(observation["receipt"] is None, "unknown status must not imply observed evidence")
                unknown.append(stage)
                continue
            row = receipt(observation["receipt"], root)
            require(row["kind"] == "client_trace", "configuration, health or protocol evidence cannot qualify a real client stage")
            for key, expected in (("surface", surface), ("mode", client["mode"]), ("version", client["version"]),
                                  ("stage", stage), ("endpoint", doc["endpoint"]), ("outcome", status)):
                require(row[key] == expected, f"receipt {key} mismatch")
            require(stamp(row["recorded_at"]) <= cutoff, "receipt is newer than matrix")
            require(row["request_sha256"] is not None and row["response_sha256"] is not None, "self-reported exchange fingerprints required")
            if status == "refused":
                require(row["error_code"] is not None, "refusal needs observed code")
            else:
                require(row["error_code"] is None, "pass cannot carry refusal")
            if stage == "discover" and status == "pass":
                require(bool(row["tools"]), "discovery needs actual visible tools")
            if stage == "call":
                require(row["tool"] is not None, "call needs actual tool name")
            if stage in {"consent", "refresh"} and status == "pass":
                require(row["auth_method"] == "oauth", "OAuth stage needs observed authentication")
            if stage == "consent" and status == "pass":
                require(bool(row["consent_scopes"]), "consent needs observed scopes")
            reported.append({"stage": stage, "outcome": status, "version_known": client["version"] is not None,
                             "assurance": "structurally_valid_self_report",
                             "exchange_fingerprints": "self_reported_not_byte_verified",
                             "recorded_at": row["recorded_at"], "source_observed_at": row["source_observed_at"],
                             "unknown_bindings": [key for key in ("auth_method", "workspace_id", "repo_id") if row[key] is None]})
        result.append({"surface": surface, "mode": client["mode"], "observations": reported, "unknown_stages": sorted(unknown)})
    require(seen == {(surface, mode) for surface, modes in SURFACES.items() for mode in modes},
            "every product surface and mode must be explicit")
    return {"schema": "client-compatibility-validation/v1", "valid": True, "as_of": doc["as_of"],
            "clients": result, "authority": "receipt bytes and reported structure validated; client provenance and exchange bytes unverified",
            "writes": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = validate(load(args.matrix), args.evidence_root)
    except (ValueError, OSError, TypeError, KeyError):
        # Raw payloads/paths/errors can contain credentials: output a fixed refusal.
        print("invalid client compatibility evidence", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
