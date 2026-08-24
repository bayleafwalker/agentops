#!/usr/bin/env python3
"""Fail when a pull request touches a protected path without declaring itself.

The dispatch gate asserts ``protected-paths-untouched`` over the WORKER's
commit. Acceptance happens over the merged pull request, and the coordinator
routinely adds commits to a packet branch after the gate has run. PR #74's gate
table therefore reported ``protected-paths-untouched: true`` while that same PR
modified ``hybrid_dispatch.py`` -- accurate about the commit, misleading about
the PR.

Widening the gate itself is the wrong fix: the coordinator's evidence and
oracle-reconciliation commits are legitimately outside the packet's writable
paths, so a whole-branch scope check would fail every packet. But
``protected-paths-untouched`` is a different invariant, and it should hold over
the whole PR for everyone, always -- unless the PR says out loud that it is a
hand-pass. Being forced to say so is the feature.

Glob semantics come from ``hybrid_dispatch._matches_any`` rather than being
reimplemented; M-11 existed because that matcher had already been written twice.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "_hybrid_dispatch_for_ci", HERE / "hybrid_dispatch.py"
)
_dispatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dispatch)  # type: ignore[union-attr]

MARKER = "hand-pass:"


def protected_patterns(manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(manifest["hybrid"]["protected_paths"])


def changed_paths(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--title", default="")
    parser.add_argument("--manifest", type=Path, default=Path("agentops.dispatch.json"))
    args = parser.parse_args(argv)

    patterns = protected_patterns(args.manifest)
    touched = changed_paths(args.base, args.head)
    hits = [p for p in touched if _dispatch._matches_any(p, patterns)]

    if not hits:
        print(f"no protected path touched ({len(touched)} file(s) changed)")
        return 0
    declared = args.title.strip().lower().startswith(MARKER)
    for path in hits:
        print(f"protected: {path}")
    if declared:
        print(f"\ndeclared hand-pass: the title begins {MARKER!r}; allowed")
        return 0
    print(
        f"\nThis pull request modifies {len(hits)} protected path(s) and does not "
        f"declare itself a hand-pass.\n"
        f"The dispatch gate only covers the worker's commit, so it cannot catch "
        f"this.\nIf the change is intended, prefix the PR title with {MARKER!r}."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
