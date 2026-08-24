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

#: A hybrid packet PR declares itself with this prefix. It buys exactly one
#: exemption, checked below, and nothing else.
PACKET_MARKER = "[hybrid]"

#: The one protected path every packet freeze must touch. Commit 1 of a freeze
#: branch registers the packet oracle's command id under ``hybrid.commands``,
#: so without an exemption this gate fails EVERY hybrid packet PR -- and a gate
#: that is red on every legitimate PR is one people learn to merge over, which
#: is how it would come to miss the case it was built for (PR #74). The
#: exemption is therefore as narrow as it can be made: this file only, purely
#: additive keys under ``hybrid.commands`` only, and only when the title says
#: the PR is a packet.
REGISTRATION_PATH = "agentops.dispatch.json"


def protected_patterns(manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(manifest["hybrid"]["protected_paths"])


def changed_paths(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def _blob(ref: str, path: str) -> str | None:
    """The file's content at ``ref``, or None when it is not there."""
    out = subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True,
    )
    return out.stdout if out.returncode == 0 else None


def registration_only(base: str, head: str, path: str = REGISTRATION_PATH) -> bool:
    """True when the only change to the manifest is new ``hybrid.commands`` keys.

    Anything else in the document -- a changed route, a flipped
    ``self_candidate``, a removed command, a re-pointed command id -- is a
    policy change and must be declared, so any of those makes this False and
    the gate fails as before.
    """
    before, after = _blob(base, path), _blob(head, path)
    if before is None or after is None:
        return False
    try:
        b, a = json.loads(before), json.loads(after)
    except json.JSONDecodeError:
        return False
    b_cmds = (b.get("hybrid") or {}).pop("commands", None)
    a_cmds = (a.get("hybrid") or {}).pop("commands", None)
    if b != a or not isinstance(b_cmds, dict) or not isinstance(a_cmds, dict):
        return False
    # Purely additive: every command that existed still exists, unchanged.
    return all(a_cmds.get(k) == v for k, v in b_cmds.items())


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
    title = args.title.strip()
    if (
        title.lower().startswith(PACKET_MARKER)
        and hits == [REGISTRATION_PATH]
        and registration_only(args.base, args.head)
    ):
        print(
            f"{REGISTRATION_PATH}: new hybrid.commands key(s) only, under a "
            f"{PACKET_MARKER!r} title -- the packet registration seam; allowed"
        )
        return 0

    declared = title.lower().startswith(MARKER)
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
