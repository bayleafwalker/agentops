"""Allowlist enforcement against `schemas/harness-evidence-attributes.schema.json`.

The schema, not a copy of its key list, is the source of truth: `load_schema()`
reads the file itself at call time, and `filter_attributes()` derives its
allowed key sets from whatever that file currently contains. A caller that
wants the allowlist without paying to reload it can pass a schema it already
loaded back in.

Two of the schema's properties (`durations`, `rate_limit`) are themselves
`additionalProperties: false` objects, so an unknown key nested one level
down -- `rate_limit.raw_header`, say -- is exactly as forbidden as an unknown
top-level key, and is dropped and counted the same way rather than smuggled
through because its parent key was allowed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "harness-evidence-attributes.schema.json"
SCHEMA_VERSION = "harness-evidence-attributes/v1"


def load_schema() -> dict[str, Any]:
    """Read and parse the allowlist schema fresh from disk."""
    return json.loads(SCHEMA_PATH.read_text())


def allowed_top_level_keys(schema: dict[str, Any] | None = None) -> frozenset[str]:
    schema = schema if schema is not None else load_schema()
    return frozenset(schema.get("properties", {}).keys())


def allowed_nested_keys(field: str, schema: dict[str, Any] | None = None) -> frozenset[str]:
    """Allowed sub-keys of an object-valued top-level field, or empty if it has none."""
    schema = schema if schema is not None else load_schema()
    sub = schema.get("properties", {}).get(field, {})
    return frozenset(sub.get("properties", {}).keys())


class FilterResult:
    """The kept attribute map plus what was dropped, for evidence and testing."""

    def __init__(self, attributes: dict[str, Any], dropped_keys: list[str]) -> None:
        self.attributes = attributes
        self.dropped_keys = dropped_keys

    @property
    def dropped_count(self) -> int:
        return len(self.dropped_keys)


def candidate_from_payload(raw: dict[str, Any], control_keys: frozenset[str]) -> dict[str, Any]:
    """Strip a caller's control/linking keys and stamp `schema_version`.

    Shared by `spans` and `metrics`: both take a payload whose real
    attribute keys are meant to pass through `filter_attributes`, plus a
    handful of keys (`transcript_path`, `subagents`, `windows`, ...) that
    exist only to drive this library's own linking logic and must never be
    offered to the allowlist filter as candidate attributes.
    """
    candidate = {k: v for k, v in raw.items() if k not in control_keys}
    candidate.setdefault("schema_version", SCHEMA_VERSION)
    return candidate


def filter_attributes(candidate: dict[str, Any], schema: dict[str, Any] | None = None) -> FilterResult:
    """Keep only keys the allowlist schema permits; drop and count the rest.

    A top-level key absent from `schema["properties"]` is dropped outright.
    A top-level key that is present but whose value is a dict is recursed
    into exactly one level, against that field's own nested
    `additionalProperties: false` schema (`durations`, `rate_limit` today);
    an unknown nested key is dropped and counted as `"<field>.<subkey>"`. A
    nested field with no declared sub-schema (i.e. not one of `durations` /
    `rate_limit`) is kept whole rather than partially filtered, since this
    library has no per-field policy for it beyond top-level allow/deny.
    """
    schema = schema if schema is not None else load_schema()
    top = allowed_top_level_keys(schema)
    kept: dict[str, Any] = {}
    dropped_keys: list[str] = []
    for key, value in candidate.items():
        if key not in top:
            dropped_keys.append(key)
            continue
        nested_allowed = allowed_nested_keys(key, schema)
        if nested_allowed and isinstance(value, dict):
            nested_kept = {}
            for nested_key, nested_value in value.items():
                if nested_key in nested_allowed:
                    nested_kept[nested_key] = nested_value
                else:
                    dropped_keys.append(f"{key}.{nested_key}")
            if nested_kept:
                kept[key] = nested_kept
        else:
            kept[key] = value
    return FilterResult(kept, dropped_keys)
