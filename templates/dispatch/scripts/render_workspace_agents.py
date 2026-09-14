#!/usr/bin/env python3
"""Render the workspace `AGENTS.md` from its versioned agentops source.

`/projects/dev` is not a git repository -- its `.git` holds only an empty
`info/`. So `/projects/dev/AGENTS.md`, which every session is told to read, was
guidance that no repository carried: an edit made there survived exactly as long
as the workstation did, and could not reach devbox-vm or a rebuilt host.

This renderer makes the file an artifact of agentops rather than a source. The
content lives in `templates/workspace/AGENTS.agentops.md`, which is versioned,
reviewed and replicated by the same push that carries the rest of the repo; the
rendered file carries a header naming its source and that source's digest, so a
reader can tell at a glance that editing it in place is pointless.

`--check` is the honest half. Without it, drift is invisible again the moment
someone edits the rendered file, which is precisely the failure this replaces.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = REPO_ROOT / "templates" / "workspace" / "AGENTS.agentops.md"
DEFAULT_TARGET = Path("/projects/dev/AGENTS.md")

TOOL = "agentops-workspace-agents/v1"
HEADER_OPEN = "<!-- agentops-render: DO NOT HAND-EDIT"

# Matches the whole `source_git_sha:` header line (with its trailing
# newline), so it can be dropped before comparing two renders for content
# drift -- a history-only change (e.g. a rebase) must not read as drift.
_SOURCE_GIT_SHA_LINE = re.compile(r"^ {5}source_git_sha: .*\n", re.MULTILINE)


def lookup_source_git_sha(source: Path, repo_root: Path = REPO_ROOT) -> str | None:
    """Return the short sha of the last commit that touched `source`.

    Returns None (never raises) when git is unavailable or `source` is not
    inside a git checkout -- this is I/O, kept out of `render()` so tests can
    inject a sha instead of depending on the ambient git state.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%h", "--", str(source)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def strip_source_git_sha(rendered: str) -> str:
    """Return `rendered` with its `source_git_sha:` header line removed."""
    return _SOURCE_GIT_SHA_LINE.sub("", rendered)


def extract_source_git_sha(rendered: str) -> str | None:
    """Return the `source_git_sha:` value recorded in `rendered`, if any."""
    match = _SOURCE_GIT_SHA_LINE.search(rendered)
    if not match:
        return None
    return match.group(0).strip().split(": ", 1)[1]


def render(source: Path, source_git_sha: str | None = None) -> str:
    """Return the full rendered document for `source`.

    `source_git_sha` is injected rather than looked up here so this function
    stays pure; callers that want it populated pass the result of
    `lookup_source_git_sha`.
    """
    body = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    try:
        origin = source.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        origin = source.resolve().as_posix()
    sha_line = f"     source_git_sha: {source_git_sha}\n" if source_git_sha else ""
    header = (
        f"{HEADER_OPEN}\n"
        f"     source: agentops/{origin}\n"
        f"     source_sha256: {digest}\n"
        f"{sha_line}"
        f"     tool: {TOOL}\n"
        f"     Edits here are discarded on the next render. Change the source,\n"
        f"     then re-run: python {Path(__file__).name} --apply\n"
        f"-->\n"
    )
    return header + body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="write the rendered file")
    group.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if the target is missing or has drifted from the source",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"FAILED: source not found: {args.source}", file=sys.stderr)
        return 2

    current_sha = lookup_source_git_sha(args.source)
    expected = render(args.source, source_git_sha=current_sha)

    if args.check:
        if not args.target.is_file():
            print(f"FAILED: {args.target} does not exist; run --apply", file=sys.stderr)
            return 1
        actual = args.target.read_text(encoding="utf-8")
        # Compare content only -- a history-only source_git_sha change (e.g. a
        # rebase) is not drift, so it is excluded from the comparison.
        if strip_source_git_sha(actual) != strip_source_git_sha(expected):
            recorded_sha = extract_source_git_sha(actual)
            print(
                f"FAILED: {args.target} has drifted from {args.source}.\n"
                "The rendered file is not a source -- re-apply the render, and if the\n"
                "drift is content worth keeping, move it into the source first.\n"
                f"stale: rendered from {recorded_sha or 'unknown'}, "
                f"source now at {current_sha or 'unknown'}",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {args.target} matches {args.source}")
        return 0

    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(expected, encoding="utf-8")
    print(f"wrote {args.target} ({len(expected)} bytes) from {args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
