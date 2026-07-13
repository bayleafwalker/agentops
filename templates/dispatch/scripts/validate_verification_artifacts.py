#!/usr/bin/env python3
"""Validate the stable minimum contract for state-protocol JSON artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CLASSIFICATIONS = {
    "formally-checked",
    "exhaustively-checked-within-bound",
    "property-tested",
    "concurrency-tested",
    "example-tested",
    "documented-only",
    "unknown",
}


def _require(value: dict[str, Any], fields: tuple[str, ...], path: Path) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise ValueError(f"{path}: missing fields: {', '.join(missing)}")


def _non_empty_list(value: Any, field: str, path: Path) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path}: {field} must be a non-empty array")


def validate_context(value: dict[str, Any], path: Path) -> None:
    _require(
        value,
        (
            "id",
            "owner_repo",
            "subject",
            "contract_ref",
            "source_of_truth",
            "depth",
            "backends",
            "actors",
            "operations",
            "consistency",
            "invariants",
            "faults",
            "oracles",
            "implementation_anchors",
        ),
        path,
    )
    if value["depth"] not in range(4):
        raise ValueError(f"{path}: depth must be 0..3")
    for field in ("backends", "actors", "operations", "invariants", "oracles", "implementation_anchors"):
        _non_empty_list(value[field], field, path)
    _require(value["contract_ref"], ("doc_id", "revision"), path)
    _require(value["consistency"], ("target", "object"), path)


def validate_result(value: dict[str, Any], path: Path) -> None:
    _require(
        value,
        ("context_id", "contract_ref", "implementation_sha", "depth", "environment", "execution", "claims", "counterexamples"),
        path,
    )
    _non_empty_list(value["claims"], "claims", path)
    for claim in value["claims"]:
        _require(claim, ("property", "result"), path)
        if claim["result"] not in CLASSIFICATIONS:
            raise ValueError(f"{path}: invalid evidence classification {claim['result']!r}")


def validate(path: Path) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    version = value.get("schema_version")
    if version == "test-context/v1":
        validate_context(value, path)
    elif version == "verification-result/v1":
        validate_result(value, path)
    else:
        raise ValueError(f"{path}: unknown schema_version {version!r}")


def discover(root: Path) -> list[Path]:
    return sorted(
        set(root.glob("verification/contexts/*.json"))
        | set(root.glob("verification/results/*.json"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    paths = args.paths or discover(args.root)
    if not paths:
        print("no verification artifacts found")
        return 0
    for path in paths:
        validate(path)
        print(f"ok {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
