#!/usr/bin/env python3
"""Verify that every shared workstation profile selected served Sprintctl mode."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DIRECT_PATTERNS = (
    re.compile(r"\bSPRINTCTL_URL\b"),
    re.compile(r"sprintctl-cnpg-main-app"),
    re.compile(r"\bsprintctl-pg\b"),
    re.compile(r"SPRINTCTL_BACKEND\s*=\s*(?:\"|')?remote\b"),
    re.compile(r"postgres(?:ql)?://", re.IGNORECASE),
)
REPOSITORIES = (
    "_orchestration",
    "actionq",
    "agentops",
    "aligned-equity",
    "box",
    "homelab-analytics",
    "scribectl",
    "sprintctl",
)


def _executable_shell_text(text: str) -> str:
    """Return shell text with comments removed.

    The cutover gate audits the configuration that an interactive shell can
    execute.  A ``#`` inside a quoted value is data, not a comment, so a
    line-oriented ``startswith('#')`` filter is insufficient here.
    """
    lines: list[str] = []
    for line in text.splitlines():
        quote: str | None = None
        escaped = False
        kept: list[str] = []
        for character in line:
            if escaped:
                kept.append(character)
                escaped = False
                continue
            if character == "\\" and quote != "'":
                kept.append(character)
                escaped = True
                continue
            if character in {"'", '"'}:
                if quote is None:
                    quote = character
                elif quote == character:
                    quote = None
                kept.append(character)
                continue
            if character == "#" and quote is None:
                break
            kept.append(character)
        lines.append("".join(kept))
    return "\n".join(lines)


def validate_envrc(path: Path, profile: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: cannot read .envrc: {exc}"]
    errors: list[str] = []
    executable_text = _executable_shell_text(text)
    if not re.search(r"export\s+SPRINTCTL_BACKEND=served\b", executable_text):
        errors.append(f"{path}: missing `export SPRINTCTL_BACKEND=served`")
    expected = f"export SPRINTCTL_VUORO_PROFILE={profile}"
    if expected not in executable_text:
        errors.append(f"{path}: missing exact profile binding `{expected}`")
    # `unset SPRINTCTL_URL` is prescribed served-mode cleanup, not direct
    # backend wiring.  It may appear in a normal executable selection block.
    scan_text = "\n".join(
        line
        for line in executable_text.splitlines()
        if not re.match(r"\s*unset\s+SPRINTCTL_URL\s*$", line)
    )
    for pattern in DIRECT_PATTERNS:
        if pattern.search(scan_text):
            errors.append(f"{path}: contains prohibited direct-backend wiring matching {pattern.pattern!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="directory containing the eight repositories")
    parser.add_argument("--profile", type=Path, required=True, help="profile JSON file selected by every .envrc")
    parser.add_argument(
        "--repository",
        dest="repositories",
        action="append",
        choices=REPOSITORIES,
        help="repository to validate; repeat to validate a deliberate subset (default: all)",
    )
    args = parser.parse_args()
    profile = args.profile.expanduser().resolve()
    if not profile.is_file():
        parser.error(f"--profile must be an existing profile JSON file, got: {args.profile}")
    repositories = args.repositories or REPOSITORIES
    errors: list[str] = []
    for repository in repositories:
        errors.extend(validate_envrc(args.root / repository / ".envrc", profile))
    if errors:
        print("Vuoro workstation cutover is not complete:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"ok: all {len(repositories)} selected profiles select served Sprintctl via {profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
