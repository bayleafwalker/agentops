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


def validate_envrc(path: Path, profile: str) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path}: cannot read .envrc: {exc}"]
    errors: list[str] = []
    if not re.search(r"export\s+SPRINTCTL_BACKEND=served\b", text):
        errors.append(f"{path}: missing `export SPRINTCTL_BACKEND=served`")
    expected = f"export SPRINTCTL_VUORO_PROFILE={profile}"
    if expected not in text:
        errors.append(f"{path}: missing exact profile binding `{expected}`")
    for pattern in DIRECT_PATTERNS:
        if pattern.search(text):
            errors.append(f"{path}: contains prohibited direct-backend wiring matching {pattern.pattern!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="directory containing the eight repositories")
    parser.add_argument("--profile", required=True, help="absolute profile path selected by every .envrc")
    args = parser.parse_args()
    errors: list[str] = []
    for repository in REPOSITORIES:
        errors.extend(validate_envrc(args.root / repository / ".envrc", args.profile))
    if errors:
        print("Vuoro workstation cutover is not complete:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"ok: all {len(REPOSITORIES)} profiles select served Sprintctl via {args.profile}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
