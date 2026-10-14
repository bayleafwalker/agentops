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

Glob semantics are ``hybrid_dispatch._matches_any``'s, copied verbatim into
``_matches_any`` below so this gate survives hybrid_dispatch.py's deletion
(S2 item 6). Change the matcher here, not in a new reimplementation.

The ``hand-pass@<sha>:`` title (sha the FULL 40-hex head sha being checked) is
honoured only when the GitHub actor who triggered the run (``--sender``) is
listed in ``hybrid.hand_pass_actors`` of the BASE manifest. The workflow runs
this script and reads that manifest from the base commit, so a PR cannot add
itself to the list. An agent token that titles its own PR therefore still
fails. The sha binds the authorisation to the commit the operator reviewed:
after the final push the operator edits the title to ``hand-pass@<sha>: ...``;
a later push changes the head and the token no longer matches. The full sha is
required because a short prefix (7 hex = 28 bits) can be ground by an agent so
that a later commit carries the prefix the operator signed.

There is no other exemption. The former ``[hybrid]`` title seam (purely
additive ``hybrid.commands`` keys) let an agent PR register shell commands the
dispatcher runs without operator sign-off, so a packet registration is now a
hand-pass like any other protected-path change.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path


def _matches_any(path: str, patterns: list[str]) -> bool:
    """True when ``path`` is covered by any glob or directory-prefix pattern.

    Manifest scope roots are written as directory prefixes (``docs/``) while
    packets use globs (``docs/**``); both forms must resolve here.
    """
    for pattern in patterns:
        if pattern.endswith("/"):
            if path == pattern.rstrip("/") or path.startswith(pattern):
                return True
            continue
        if fnmatch.fnmatch(path, pattern):
            return True
        prefix = pattern[: -len("/**")] if pattern.endswith("/**") else None
        if prefix is not None and (path == prefix or path.startswith(prefix + "/")):
            return True
        if path == pattern:
            return True
    return False


#: ``hand-pass@<40 hex>:`` at the start of the title. The hex must equal the
#: full head sha being checked, so an authorisation covers the commit the
#: operator reviewed and not whatever head a later push produces. Prefixes are
#: refused: a short one can be brute-forced onto a later commit.
HAND_PASS_RE = re.compile(r"^hand-pass@([0-9a-f]{40}):", re.IGNORECASE)

#: Hybrid packet PRs are titled with this prefix. It buys no exemption; it is
#: recognised only to explain why a packet's command registration still fails.
PACKET_MARKER = "[hybrid]"


def protected_patterns(manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(manifest["hybrid"]["protected_paths"])


def hand_pass_actors(manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list((manifest.get("hybrid") or {}).get("hand_pass_actors") or [])


def changed_paths(base: str, head: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", f"{base}...{head}"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--title", default="")
    parser.add_argument("--sender", default="",
                        help="login of the actor that triggered this run")
    parser.add_argument("--manifest", type=Path, default=Path("agentops.dispatch.json"))
    args = parser.parse_args(argv)

    patterns = protected_patterns(args.manifest)
    touched = changed_paths(args.base, args.head)
    hits = [p for p in touched if _matches_any(p, patterns)]

    if not hits:
        print(f"no protected path touched ({len(touched)} file(s) changed)")
        return 0
    title = args.title.strip()

    token = HAND_PASS_RE.match(title)
    marked = title.lower().startswith("hand-pass")
    head_sha = subprocess.run(
        ["git", "rev-parse", "--verify", f"{args.head}^{{commit}}"],
        capture_output=True, text=True,
    ).stdout.strip().lower()
    sha_ok = bool(token and head_sha and head_sha == token.group(1).lower())
    sender = args.sender.strip()
    actors = hand_pass_actors(args.manifest)
    for path in hits:
        print(f"protected: {path}")
    if sha_ok and sender and sender in actors:
        print(f"\ndeclared hand-pass by {sender} for {head_sha}; allowed")
        return 0
    if sha_ok:
        print(
            f"\nhand-pass declared by {sender or '<unknown sender>'}; needs the "
            f"operator to open, edit or reopen the PR on this head"
        )
        return 1
    if marked:
        print(
            f"\nhand-pass title does not name this head: expected a title "
            f"beginning 'hand-pass@{head_sha or '<full 40-hex head sha>'}:'. "
            f"Only the full 40-hex sha is accepted, not a prefix. The operator "
            f"edits the title after the final push."
        )
        return 1
    if title.lower().startswith(PACKET_MARKER):
        print(
            f"\nA {PACKET_MARKER!r} title buys no exemption: new hybrid.commands "
            f"entries are commands the dispatcher runs, so registering them needs "
            f"an operator hand-pass like any other protected-path change."
        )
    print(
        f"\nThis pull request modifies {len(hits)} protected path(s) and does not "
        f"declare itself a hand-pass.\n"
        f"The dispatch gate only covers the worker's commit, so it cannot catch "
        f"this.\nIf the change is intended, the operator edits the PR title to begin\n"
        f"'hand-pass@<full 40-hex head sha>:' after the final push "
        f"(gh pr view <n> --json headRefOid -q .headRefOid)."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
