#!/usr/bin/env python3
"""Verify and atomically materialize immutable skill-lock/v1 bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any


class SkillLockError(ValueError):
    pass


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    for child in sorted(item for item in path.rglob("*") if item.is_file() and not item.is_symlink()):
        digest.update(child.relative_to(path).as_posix().encode() + b"\0")
        digest.update(child.read_bytes())
    return digest.hexdigest()


def inspect(lock: dict[str, Any], source_root: Path) -> dict[str, Any]:
    if lock.get("schema_version") != "skill-lock/v1" or not isinstance(lock.get("selected"), list):
        raise SkillLockError("invalid skill lock")
    missing_mandatory: list[str] = []
    missing_optional: list[str] = []
    tampered: list[str] = []
    observed: list[tuple[str, str]] = []
    for selected in lock["selected"]:
        path = source_root / selected["path"]
        if path.is_symlink() or not path.is_dir():
            (missing_mandatory if selected["mandatory"] else missing_optional).append(selected["id"])
            continue
        if any(child.is_symlink() for child in path.rglob("*")):
            tampered.append(selected["id"])
            continue
        actual = tree_digest(path)
        observed.append((selected["id"], actual))
        if actual != selected["digest"]:
            tampered.append(selected["id"])
    calculated_tree = hashlib.sha256(json.dumps(sorted(observed), separators=(",", ":")).encode()).hexdigest()
    if not missing_mandatory and not missing_optional and calculated_tree != lock.get("tree_digest"):
        tampered.append("<tree>")
    handling = "fatal" if tampered else ("repair-only" if missing_mandatory else ("degraded" if missing_optional else "none"))
    return {"handling": handling, "managed_eligible": handling == "none", "missing_mandatory": missing_mandatory, "missing_optional": missing_optional, "tampered": tampered, "tree_digest": calculated_tree}


def materialize(lock: dict[str, Any], source_root: Path, target_root: Path, provider: str) -> dict[str, Any]:
    report = inspect(lock, source_root)
    if report["handling"] != "none":
        raise SkillLockError(f"skill lock is not materializable: {report['handling']}")
    expected_target = lock.get("provider_materialization_targets", {}).get(provider)
    if not isinstance(expected_target, str):
        raise SkillLockError(f"provider target is not locked: {provider}")
    target = target_root / expected_target
    if target.exists():
        raise SkillLockError("target already exists; rollback or select a new immutable target")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        for selected in lock["selected"]:
            shutil.copytree(source_root / selected["path"], staging / selected["id"])
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    receipt = {"schema_version": "skill-materialization-receipt/v1", "provider": provider, "target": expected_target, "tree_digest": lock["tree_digest"], "skills": [item["id"] for item in lock["selected"]]}
    return receipt


def rollback(receipt: dict[str, Any], target_root: Path, expected_tree_digest: str) -> None:
    if receipt.get("schema_version") != "skill-materialization-receipt/v1" or receipt.get("tree_digest") != expected_tree_digest:
        raise SkillLockError("rollback receipt mismatch")
    target = target_root / receipt["target"]
    if target.exists():
        shutil.rmtree(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    args = parser.parse_args(argv)
    report = inspect(json.loads(args.lock.read_text()), args.source_root)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["handling"] == "none" else 1


if __name__ == "__main__":
    raise SystemExit(main())
