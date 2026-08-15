#!/usr/bin/env python3
"""Validate repository dispatch and state-protocol contracts without dependencies."""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import re
from typing import Any
from uuid import UUID


CLASSIFICATIONS = {
    "formally-checked",
    "exhaustively-checked-within-bound",
    "property-tested",
    "concurrency-tested",
    "example-tested",
    "documented-only",
    "unknown",
}

RISK_SKILLS = {"verify-state-protocols", "reconcile-project-contracts"}


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
    if value.get("schema_version") != "test-context/v1":
        raise ValueError(f"{path}: schema_version must be test-context/v1")
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
    if value.get("schema_version") != "verification-result/v1":
        raise ValueError(f"{path}: schema_version must be verification-result/v1")
    _non_empty_list(value["claims"], "claims", path)
    for claim in value["claims"]:
        _require(claim, ("property", "result"), path)
        if claim["result"] not in CLASSIFICATIONS:
            raise ValueError(f"{path}: invalid evidence classification {claim['result']!r}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    return value


def validate(path: Path) -> dict[str, Any]:
    value = load_json(path)
    version = value.get("schema_version")
    if version == "test-context/v1":
        validate_context(value, path)
    elif version == "verification-result/v1":
        validate_result(value, path)
    else:
        raise ValueError(f"{path}: unknown schema_version {version!r}")
    return value


def _string_list(value: Any, field: str, path: Path, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "an array" if allow_empty else "a non-empty array"
        raise ValueError(f"{path}: {field} must be {qualifier}")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"{path}: {field} entries must be non-empty strings")
    return value


def validate_manifest(value: dict[str, Any], path: Path, root: Path) -> list[dict[str, Any]]:
    _require(value, ("schema_version", "repo_id", "adoption_level", "routing", "skills", "verification", "hooks"), path)
    if value["schema_version"] not in {1, 2}:
        raise ValueError(f"{path}: schema_version must be 1 or 2")
    if value["schema_version"] == 2:
        instruction_set = value.get("instruction_set")
        if not isinstance(instruction_set, dict):
            raise ValueError(f"{path}: schema_version 2 requires instruction_set")
        if instruction_set.get("schema_version") != 1:
            raise ValueError(f"{path}: instruction_set.schema_version must be 1")
        if instruction_set.get("discovery") != "native" or not isinstance(
            instruction_set.get("sources"), list
        ):
            raise ValueError(
                f"{path}: instruction_set must declare native discovery and sources"
            )
        source_ids: set[str] = set()
        for source in instruction_set["sources"]:
            if not isinstance(source, dict):
                raise ValueError(f"{path}: instruction source must be an object")
            _require(source, ("id", "path", "kind", "digest", "source_rev"), path)
            if source["id"] in source_ids:
                raise ValueError(f"{path}: duplicate instruction source id {source['id']!r}")
            source_ids.add(source["id"])
            if source["kind"] not in {"AGENTS.md", "CLAUDE.md", "overlay", "generated", "other"}:
                raise ValueError(f"{path}: invalid instruction source kind")
            source_path = Path(source["path"])
            if source_path.is_absolute() or ".." in source_path.parts:
                raise ValueError(f"{path}: instruction source path must be relative")
            digest = source["digest"]
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError(f"{path}: instruction source digest must be sha256")
            if not isinstance(source["source_rev"], str) or not source["source_rev"]:
                raise ValueError(f"{path}: instruction source source_rev is required")
    elif "instruction_set" in value:
        raise ValueError(f"{path}: instruction_set requires schema_version 2")
    authority_repo_uuid = value.get("authority_repo_uuid")
    if authority_repo_uuid is not None:
        try:
            canonical_authority_repo_uuid = str(UUID(str(authority_repo_uuid)))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}: authority_repo_uuid must be a UUID") from exc
        if authority_repo_uuid != canonical_authority_repo_uuid:
            raise ValueError(f"{path}: authority_repo_uuid must be a canonical UUID")
    if value["adoption_level"] not in {"guidance-only", "observable", "dispatchable"}:
        raise ValueError(f"{path}: invalid adoption_level")

    routing = value["routing"]
    if not isinstance(routing, dict) or not isinstance(routing.get("action_classes"), dict):
        raise ValueError(f"{path}: routing.action_classes must be an object")
    selected = _string_list(value["skills"].get("selected"), "skills.selected", path)
    overlays = _string_list(value["skills"].get("overlays", []), "skills.overlays", path, allow_empty=True)
    for overlay in overlays:
        if not (root / overlay).is_file():
            raise ValueError(f"{path}: overlay does not exist: {overlay}")

    verification = value["verification"]
    if not isinstance(verification, dict):
        raise ValueError(f"{path}: verification must be an object")
    _string_list(verification.get("command_families"), "verification.command_families", path)

    surfaces = value.get("risk_surfaces", [])
    if not isinstance(surfaces, list):
        raise ValueError(f"{path}: risk_surfaces must be an array")
    ids: set[str] = set()
    for surface in surfaces:
        if not isinstance(surface, dict):
            raise ValueError(f"{path}: risk surface must be an object")
        _require(surface, ("id", "paths", "skills"), path)
        if surface["id"] in ids:
            raise ValueError(f"{path}: duplicate risk surface id {surface['id']!r}")
        ids.add(surface["id"])
        _string_list(surface["paths"], f"risk_surfaces.{surface['id']}.paths", path)
        risk_skills = _string_list(surface["skills"], f"risk_surfaces.{surface['id']}.skills", path)
        if any(skill not in RISK_SKILLS for skill in risk_skills):
            raise ValueError(f"{path}: risk surface {surface['id']} has invalid skills")
        if any(skill not in selected for skill in risk_skills):
            raise ValueError(f"{path}: risk surface {surface['id']} uses an unselected skill")
        depth = surface.get("default_depth")
        if depth is not None and (not isinstance(depth, int) or depth not in range(4)):
            raise ValueError(f"{path}: risk surface {surface['id']} default_depth must be 0..3")
        if "context_ids" in surface:
            _string_list(surface["context_ids"], f"risk_surfaces.{surface['id']}.context_ids", path)
    return surfaces


def discover(root: Path) -> list[Path]:
    return sorted(
        set(root.glob("verification/contexts/*.json"))
        | set(root.glob("verification/results/*.json"))
    )


def discover_manifest(root: Path, explicit: Path | None) -> Path | None:
    if explicit is not None:
        return explicit
    manifests = sorted(root.glob("*.dispatch.json"))
    if len(manifests) > 1:
        raise ValueError(f"{root}: expected at most one *.dispatch.json manifest")
    return manifests[0] if manifests else None


def path_matches(path: str, patterns: list[str]) -> bool:
    normalized = path.removeprefix("./")
    for pattern in patterns:
        if fnmatch.fnmatchcase(normalized, pattern):
            return True
        if pattern.endswith("/**") and normalized.startswith(pattern[:-3].rstrip("/") + "/"):
            return True
    return False


def select_surfaces(surfaces: list[dict[str, Any]], changed_paths: list[str]) -> list[dict[str, Any]]:
    return [
        surface
        for surface in surfaces
        if any(path_matches(changed, surface["paths"]) for changed in changed_paths)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--require-results", action="store_true")
    parser.add_argument("--implementation-sha")
    args = parser.parse_args()
    root = args.root.resolve()
    paths = args.paths or discover(root)
    contexts: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for path in paths:
        value = validate(path)
        if value["schema_version"] == "test-context/v1":
            context_id = value["id"]
            if context_id in contexts:
                raise ValueError(f"{path}: duplicate context id {context_id!r}")
            contexts[context_id] = value
        else:
            results.append(value)
        print(f"ok {path}")

    manifest_path = discover_manifest(root, args.manifest)
    surfaces: list[dict[str, Any]] = []
    if manifest_path is not None:
        surfaces = validate_manifest(load_json(manifest_path), manifest_path, root)
        for surface in surfaces:
            for context_id in surface.get("context_ids", []):
                if context_id not in contexts:
                    raise ValueError(f"{manifest_path}: risk surface {surface['id']} references missing context {context_id!r}")
        print(f"ok {manifest_path}")

    selected = select_surfaces(surfaces, args.changed_path)
    for surface in selected:
        print(f"risk-surface {surface['id']} depth={surface.get('default_depth', 0)} required={str(surface.get('required_on_change', False)).lower()}")

    if args.require_results:
        required = [surface for surface in selected if surface.get("required_on_change", False)]
        for surface in required:
            context_ids = surface.get("context_ids", [])
            if not context_ids:
                raise ValueError(f"{manifest_path}: required risk surface {surface['id']} has no context_ids")
            matching = [result for result in results if result.get("context_id") in context_ids]
            if args.implementation_sha:
                matching = [result for result in matching if result.get("implementation_sha") == args.implementation_sha]
            if not matching:
                suffix = f" for {args.implementation_sha}" if args.implementation_sha else ""
                raise ValueError(f"{manifest_path}: required risk surface {surface['id']} has no verification result{suffix}")

    if not paths:
        print("no verification artifacts found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
