#!/usr/bin/env python3
"""Report dispatch run branches; retire only merged branches without a worktree."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()


def worktrees(repo: str) -> dict[str, dict]:
    result = {}
    for block in git(repo, "worktree", "list", "--porcelain").split("\n\n"):
        fields = dict(line.partition(" ")[::2] for line in block.splitlines())
        branch = fields.get("branch", "").removeprefix("refs/heads/")
        if branch:
            path = Path(fields["worktree"])
            result[branch] = {"path": str(path), "age_seconds": max(0, int(time.time() - path.stat().st_mtime)) if path.exists() else None}
    return result


def inspect(repo: str, apply: bool = False, remove_paths: list[str] | None = None) -> dict:
    # A failed fetch cannot license retirement against stale origin/main.
    git(repo, "fetch", "--quiet", "origin", "refs/heads/main:refs/remotes/origin/main")
    held = worktrees(repo)
    errors = []
    removed = []
    for path_arg in remove_paths or []:
        path = Path(path_arg)
        if not apply:
            raise ValueError("--remove-worktree requires --apply")
        if path.parent != Path("/projects/dev/_wt") or not path.name.startswith("dispatch-") or path.resolve() != path:
            raise ValueError("only an explicit /projects/dev/_wt/dispatch-* worktree may be removed")
        if not any(row["path"] == str(path) and branch.startswith("dispatch/run-") for branch, row in held.items()):
            raise ValueError("requested path is not this repository's dispatch run worktree")
        try:
            git(repo, "worktree", "remove", str(path))  # No force: preserve dirty work.
            removed.append(str(path))
        except subprocess.CalledProcessError as error:
            errors.append(error.stderr.strip())
    held = worktrees(repo)
    rows = []
    for line in git(repo, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads/dispatch/").splitlines():
        ref, tip = line.split()
        branch = ref.removeprefix("refs/heads/")
        if not re.fullmatch(r"dispatch/run-[A-Za-z0-9_-]+", branch):
            continue
        ancestry = subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", tip, "origin/main"], capture_output=True, text=True)
        if ancestry.returncode not in (0, 1):
            raise ValueError(ancestry.stderr.strip() or "could not check branch ancestry")
        merged = ancestry.returncode == 0
        row = {"branch": branch, "tip": tip, "merged": merged, "worktree": held.get(branch), "deleted": False}
        if apply and merged and branch not in worktrees(repo):
            try:
                # Expected old value refuses a concurrent branch advance.
                git(repo, "update-ref", "-d", ref, tip)
                row["deleted"] = True
            except subprocess.CalledProcessError as error:
                row["error"] = error.stderr.strip()
        rows.append(row)
    return {"repo": repo, "applied": apply, "branches": rows, "removed_worktrees": removed, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--remove-worktree", action="append", default=[])
    args = parser.parse_args()
    try:
        result = inspect(args.repo, args.apply, args.remove_worktree)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({"error": str(error)}))
        return 1
    print(json.dumps(result))
    return int(bool(result["errors"] or any(row.get("error") for row in result["branches"])))


if __name__ == "__main__":
    raise SystemExit(main())
