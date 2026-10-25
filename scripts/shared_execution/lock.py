"""Integrity check for a self-contained vendored execution engine."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def source_digest(package_dir: str | Path) -> str:
    """Digest sorted Python source names and exact bytes, excluding runtime files."""
    root = Path(package_dir)
    digest = hashlib.sha256()
    sources = sorted(root.glob("*.py"))
    if not sources:
        raise ValueError(f"no shared execution source files in {root}")
    for source in sources:
        digest.update(source.name.encode())
        digest.update(b"\0")
        digest.update(source.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def verify_dispatch_lock(lock_path: str | Path) -> dict[str, Any]:
    """Fail closed if a vendored engine differs from its adjacent dispatch lock."""
    path = Path(lock_path)
    lock = json.loads(path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != "dispatch-lock/v1":
        raise ValueError("unsupported dispatch lock schema")
    relative = lock.get("vendored_path")
    if not isinstance(relative, str) or not relative:
        raise ValueError("dispatch lock has no vendored_path")
    repository_root = next((parent for parent in path.parents if (parent / relative).is_dir()), None)
    if repository_root is None:
        raise ValueError("vendored execution package is missing")
    package = repository_root / relative
    # A lock cannot redirect verification outside the repository containing it.
    repository_root = repository_root.resolve()
    resolved_package = package.resolve()
    if resolved_package != repository_root and repository_root not in resolved_package.parents:
        raise ValueError("vendored_path escapes repository root")
    expected = lock.get("source_digest")
    if not isinstance(expected, str) or source_digest(resolved_package) != expected:
        raise ValueError("vendored shared execution source digest mismatch")
    return lock
