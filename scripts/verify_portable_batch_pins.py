#!/usr/bin/env python3
"""Verify portable feature batch draft pins using local Git objects only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SCRIPT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = (
    SCRIPT_ROOT
    / "docs/plans/agentops/portable-feature-batch-pins.v1.json"
)
OWNER_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PinError(ValueError):
    """Invalid manifest or repository mapping."""


def parse_repo_mapping(value: str) -> tuple[str, str]:
    owner, separator, path = value.partition("=")
    if not separator or not OWNER_NAME.fullmatch(owner) or not path:
        raise argparse.ArgumentTypeError(
            "repository mapping must be OWNER=PATH with a lowercase owner name"
        )
    return owner, path


def load_manifest(path: Path) -> list[dict[str, str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PinError(f"cannot read manifest: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise PinError("manifest must be an object with schema_version 1")
    rows = value.get("owners")
    if not isinstance(rows, list) or not rows:
        raise PinError("manifest owners must be a non-empty array")

    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PinError(f"manifest owners[{index}] must be an object")
        owner = row.get("owner")
        branch = row.get("branch")
        commit = row.get("commit")
        draft_path = row.get("draft_path")
        draft_sha256 = row.get("draft_sha256")
        if not isinstance(owner, str) or not OWNER_NAME.fullmatch(owner):
            raise PinError(f"manifest owners[{index}].owner is invalid")
        if owner in seen:
            raise PinError(f"duplicate owner in manifest: {owner}")
        seen.add(owner)
        if (
            not isinstance(branch, str)
            or not branch
            or branch.startswith("-")
            or ".." in branch
            or branch.startswith("/")
            or branch.endswith("/")
        ):
            raise PinError(f"manifest owners[{index}].branch is invalid")
        if not isinstance(commit, str) or not OBJECT_ID.fullmatch(commit):
            raise PinError(f"manifest owners[{index}].commit is invalid")
        if (
            not isinstance(draft_path, str)
            or not draft_path
            or draft_path.startswith("/")
            or ".." in Path(draft_path).parts
        ):
            raise PinError(f"manifest owners[{index}].draft_path is invalid")
        if not isinstance(draft_sha256, str) or not SHA256.fullmatch(draft_sha256):
            raise PinError(f"manifest owners[{index}].draft_sha256 is invalid")
        normalized.append(
            {
                "owner": owner,
                "branch": branch,
                "commit": commit,
                "draft_path": draft_path,
                "draft_sha256": draft_sha256,
            }
        )
    return normalized


def git(repo: str, *args: str) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        ["git", "-C", repo, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )


def state_for_repo(
    row: dict[str, str], repo_path: str | None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "owner": row["owner"],
        "branch": row["branch"],
        "expected_commit": row["commit"],
        "draft_path": row["draft_path"],
        "expected_draft_sha256": row["draft_sha256"],
        "repo_path": repo_path,
        "checks": {
            "commit_object": "missing",
            "branch_tip": "missing",
            "draft_path": "missing",
            "draft_sha256": "missing",
        },
        "actual_branch_tip": None,
        "actual_draft_sha256": None,
        "errors": [],
    }
    if repo_path is None:
        result["errors"].append("no --repo mapping supplied")
        return result

    commit_check = git(repo_path, "cat-file", "-e", f"{row['commit']}^{{commit}}")
    if commit_check.returncode == 0:
        result["checks"]["commit_object"] = "passed"
    else:
        result["errors"].append(
            "pinned commit object is unavailable in the local object database"
        )

    ref = f"refs/heads/{row['branch']}"
    tip_check = git(repo_path, "rev-parse", "--verify", ref)
    if tip_check.returncode == 0:
        tip = tip_check.stdout.decode("ascii", errors="replace").strip()
        result["actual_branch_tip"] = tip
        result["checks"]["branch_tip"] = (
            "passed" if tip == row["commit"] else "stale"
        )
        if tip != row["commit"]:
            result["errors"].append("local branch tip differs from pinned commit")
    else:
        result["errors"].append("local branch ref is unavailable")

    blob = git(
        repo_path,
        "cat-file",
        "blob",
        f"{row['commit']}:{row['draft_path']}",
    )
    if blob.returncode == 0:
        actual_hash = hashlib.sha256(blob.stdout).hexdigest()
        result["actual_draft_sha256"] = actual_hash
        result["checks"]["draft_path"] = "passed"
        result["checks"]["draft_sha256"] = (
            "passed" if actual_hash == row["draft_sha256"] else "stale"
        )
        if actual_hash != row["draft_sha256"]:
            result["errors"].append("draft blob SHA256 differs from manifest")
    else:
        result["errors"].append(
            "required draft path is unavailable at the pinned commit"
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"pin manifest (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        type=parse_repo_mapping,
        metavar="OWNER=PATH",
        help="local repository path for an owner; repeat for each owner",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rows = load_manifest(args.manifest)
    except PinError as exc:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "manifest": str(args.manifest),
                    "status": "error",
                    "error": str(exc),
                    "owners": [],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    repo_map: dict[str, str] = {}
    mapping_errors: list[str] = []
    for owner, path in args.repo:
        if owner in repo_map:
            mapping_errors.append(f"duplicate --repo mapping for {owner}")
        else:
            repo_map[owner] = path
    known = {row["owner"] for row in rows}
    for owner in sorted(set(repo_map) - known):
        mapping_errors.append(f"--repo mapping names unknown owner {owner}")

    owners = [state_for_repo(row, repo_map.get(row["owner"])) for row in rows]
    success = not mapping_errors and all(
        all(state == "passed" for state in owner["checks"].values())
        for owner in owners
    )
    report = {
        "schema_version": 1,
        "manifest": str(args.manifest),
        "status": "passed" if success else "failed",
        "mapping_errors": mapping_errors,
        "owners": owners,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
