#!/usr/bin/env python3
"""Resolve the environment-record/v1 file that describes the current host.

Identity is derived from the host's own hostname (normalized to the
environment-record/v1 `id` token pattern), matched against the `id` field of
records in the environment-record directory. This reuses the identity
convention already established by `vuoro-client-profile/v1`'s
`source_environment_id`, rather than inventing a new one.

Files whose stem contains `.example` are treated as templates, not live
records, and are never returned by resolution -- they exist to document the
schema, not to be selected automatically.
"""

from __future__ import annotations

import argparse
import re
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_vuoro_profiles import ProfileError, validate_environment  # noqa: E402


TOKEN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class EnvironmentResolutionError(ValueError):
    """Raised when a host's environment record cannot be resolved unambiguously."""


def normalize_hostname(hostname: str) -> str:
    """Normalize a raw hostname into an environment-record/v1 `id` token.

    Hostnames observed on this project's hosts are PascalCase (e.g. the
    `hostname` field sprintctl records for claims is `WorkstationLinux`)
    while environment-record ids are kebab-case (`workstation-linux`), so a
    case-boundary split runs before lower-casing -- a plain `.lower()` would
    silently fail to match any record.
    """
    split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", hostname.strip())
    token = re.sub(r"[^a-zA-Z0-9._-]", "-", split).lower()
    token = re.sub(r"-{2,}", "-", token).strip("-")
    if not token or not TOKEN.fullmatch(token):
        raise EnvironmentResolutionError(
            f"hostname {hostname!r} does not normalize to a valid environment id"
        )
    return token


def _candidate_records(records_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in records_dir.glob("*.json")
        if ".example" not in path.stem and ".schema" not in path.stem
    )


def resolve_environment_record(
    records_dir: Path, *, hostname: str | None = None
) -> Path:
    """Find the unique live environment record whose `id` matches this host."""
    target_id = normalize_hostname(hostname or socket.gethostname())
    matches: list[Path] = []
    for path in _candidate_records(records_dir):
        try:
            record = validate_environment(path)
        except ProfileError:
            continue
        if record["id"] == target_id:
            matches.append(path)
    if not matches:
        raise EnvironmentResolutionError(
            f"no environment record with id {target_id!r} found under {records_dir}"
        )
    if len(matches) > 1:
        names = ", ".join(str(path) for path in matches)
        raise EnvironmentResolutionError(
            f"ambiguous environment records for id {target_id!r}: {names}"
        )
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records-dir", required=True, type=Path)
    parser.add_argument(
        "--hostname", help="override the detected hostname (for testing)"
    )
    args = parser.parse_args()
    try:
        resolved = resolve_environment_record(
            args.records_dir, hostname=args.hostname
        )
    except EnvironmentResolutionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(resolved)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
