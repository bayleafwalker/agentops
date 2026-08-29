#!/usr/bin/env python3
"""Fail when a committed audit shard is rewritten rather than appended to.

Rooting ``AUDITCTL_ARTIFACTS_ROOT`` at a repository makes audit shards durable:
git replicates them wherever the code goes, which is the whole point of the
change. It also makes them *mutable*, which is the one property they had before
and lose by moving. An NDJSON shard is an append-only log; a rebase, an amend or
a force-push can silently rewrite history whose entire value is that it cannot be
rewritten. Durability and immutability are not the same property, and git only
supplies the first.

This is the guard for the second. For every ``*.ndjson`` under a
``_artifacts/**/audit/`` path that differs between two revisions, the older
content must be a **line-wise prefix** of the newer one. Appending is fine and
expected. Editing an existing line, reordering, or deleting one is not.

Deliberately not a content check: it says nothing about hash chains, schemas or
ids. It answers one question -- was anything that was already written changed --
and that question is answerable from git alone, on any host, without auditctl
installed.

Usage::

    check_append_only_shards.py --base origin/main --head HEAD
    check_append_only_shards.py            # defaults to @{upstream}..HEAD

Exit 0 when every shard is append-only (including when none changed), 1 when a
shard was rewritten, 2 on a usage or git error.
"""
from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys

#: Shards live at ``<root>/_artifacts/<scope>/audit/<name>.ndjson``. The leading
#: ``**`` keeps this true whether the root is the repository or a subdirectory of
#: it, which is exactly the migration this guard exists to make safe.
SHARD_GLOB = "*_artifacts/*/audit/*.ndjson"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def _changed_shards(base: str, head: str) -> list[str]:
    out = _git("diff", "--name-only", f"{base}..{head}")
    return [
        path
        for path in out.splitlines()
        if path and fnmatch.fnmatch(path, SHARD_GLOB)
    ]


def _lines_at(revision: str, path: str) -> list[str] | None:
    """Return the file's lines at ``revision``, or None when it does not exist."""
    result = subprocess.run(
        ["git", "show", f"{revision}:{path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.splitlines()


def check(base: str, head: str) -> list[str]:
    """Return a list of violation messages; empty means append-only."""
    violations: list[str] = []
    for path in _changed_shards(base, head):
        before = _lines_at(base, path)
        if before is None:
            # A new shard. Nothing was rewritten because nothing was there.
            continue
        after = _lines_at(head, path)
        if after is None:
            violations.append(f"{path}: shard deleted ({len(before)} line(s) lost)")
            continue
        if len(after) < len(before):
            violations.append(
                f"{path}: truncated, {len(before)} line(s) -> {len(after)}"
            )
            continue
        for index, (old, new) in enumerate(zip(before, after), start=1):
            if old != new:
                violations.append(
                    f"{path}: line {index} rewritten\n"
                    f"    was: {old[:120]}\n"
                    f"    now: {new[:120]}"
                )
                break
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="revision to compare from (default @{upstream})")
    parser.add_argument("--head", default="HEAD", help="revision to compare to")
    args = parser.parse_args(argv)

    base = args.base
    if base is None:
        try:
            base = _git("rev-parse", "--abbrev-ref", "@{upstream}").strip()
        except RuntimeError:
            print(
                "no upstream to compare against; pass --base explicitly",
                file=sys.stderr,
            )
            return 2

    try:
        violations = check(base, args.head)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not violations:
        return 0

    print(
        f"audit shards are append-only, and {len(violations)} were rewritten "
        f"between {base} and {args.head}:",
        file=sys.stderr,
    )
    for violation in violations:
        print(f"  {violation}", file=sys.stderr)
    print(
        "\nA shard records what happened. Appending is expected; changing a line "
        "that was already written is not.\nIf this is a deliberate retraction, "
        "append a correcting event rather than editing the original --\n"
        "that is what the ledger retirement of 2026-08-26 did, and why those "
        "events are still auditable.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
