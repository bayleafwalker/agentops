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
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE = REPO_ROOT / "templates" / "workspace" / "AGENTS.agentops.md"
DEFAULT_TARGET = Path("/projects/dev/AGENTS.md")

TOOL = "agentops-workspace-agents/v1"
HEADER_OPEN = "<!-- agentops-render: DO NOT HAND-EDIT"


def render(source: Path) -> str:
    """Return the full rendered document for `source`."""
    body = source.read_text(encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    try:
        origin = source.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        origin = source.resolve().as_posix()
    header = (
        f"{HEADER_OPEN}\n"
        f"     source: agentops/{origin}\n"
        f"     source_sha256: {digest}\n"
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

    expected = render(args.source)

    if args.check:
        if not args.target.is_file():
            print(f"FAILED: {args.target} does not exist; run --apply", file=sys.stderr)
            return 1
        actual = args.target.read_text(encoding="utf-8")
        if actual != expected:
            print(
                f"FAILED: {args.target} has drifted from {args.source}.\n"
                "The rendered file is not a source -- re-apply the render, and if the\n"
                "drift is content worth keeping, move it into the source first.",
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
