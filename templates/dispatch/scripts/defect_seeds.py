"""Defect-seeded acceptance cases: prove an oracle detects what a packet claims.

The ``acceptance-properties-discriminating`` pre-gate is structural only: it
requires each acceptance property to name a ``fails_when``, and never checks
that the oracle actually goes red when that condition holds. A packet can
therefore declare a falsifying condition its oracle cannot detect, and nothing
notices.

A seed closes that. It is the reference overlay's complement: the reference
must turn the oracle GREEN, a seed must turn it RED. If a seeded defect leaves
the oracle green, the oracle does not test what the packet claims.

Ordering, patching and running belong to the coordinator. This module decides
only what a seed declaration MEANS and whether evidence satisfies it. No git,
no subprocess, no file I/O.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

#: Same shape as an acceptance property id: both name a requirement in evidence
#: a human will read later.
SEED_ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9._-]*\Z")


def _patch_escapes_repo(patch: str) -> bool:
    if patch.startswith("/") or patch.startswith("~"):
        return True
    return any(part == ".." for part in Path(patch).parts)


def parse_seeds(packet: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalise ``oracle.defect_seeds`` into a list of seed declarations.

    Each seed is returned as exactly ``{"id", "patch", "expect_red",
    "description"}`` with ``description`` defaulting to ``""``. A packet that
    declares no seeds returns ``[]`` and is not an error.

    Raises ValueError when a declaration is present but unusable: not a list, a
    non-object entry, a missing or malformed id, a duplicate id, a missing
    patch, an absolute patch path or one escaping the repository, an empty
    ``expect_red``, or an ``expect_red`` naming a command that is not in
    ``oracle.starts_red``. The packet is never mutated.
    """
    oracle = packet.get("oracle") or {}
    declaration = oracle.get("defect_seeds")
    if declaration is None:
        return []
    if not isinstance(declaration, list):
        raise ValueError("oracle.defect_seeds must be a list of seed declarations")

    starts_red = oracle.get("starts_red") or []
    seen: set[str] = set()
    parsed: list[dict[str, Any]] = []
    for entry in declaration:
        if not isinstance(entry, dict):
            raise ValueError("each defect seed must be an object")

        seed_id = entry.get("id")
        if not isinstance(seed_id, str) or not SEED_ID_RE.fullmatch(seed_id):
            raise ValueError(
                "each defect seed must declare an id that starts with a letter "
                "and uses only letters, digits, '.', '_' or '-'"
            )
        if seed_id in seen:
            raise ValueError(f"duplicate defect seed id: {seed_id!r}")
        seen.add(seed_id)

        patch = entry.get("patch")
        if not isinstance(patch, str) or not patch:
            raise ValueError(f"defect seed {seed_id!r} must declare a patch path")
        if _patch_escapes_repo(patch):
            raise ValueError(
                f"defect seed {seed_id!r} patch must be a repo-relative path "
                "that stays inside the repository"
            )

        expect_red = entry.get("expect_red")
        if not isinstance(expect_red, list) or not expect_red:
            raise ValueError(
                f"defect seed {seed_id!r} must declare a non-empty expect_red"
            )
        outside = [command_id for command_id in expect_red if command_id not in starts_red]
        if outside:
            raise ValueError(
                f"defect seed {seed_id!r} expects red from commands the oracle "
                f"does not start red: {', '.join(sorted(outside))}"
            )

        parsed.append(
            {
                "id": seed_id,
                "patch": patch,
                "expect_red": list(expect_red),
                "description": entry.get("description", ""),
            }
        )
    return parsed


def seed_falsified(seed: dict[str, Any], results: Iterable[dict[str, Any]]) -> bool:
    """Whether this seed did its job: every expected command ran and was red.

    ``results`` is any iterable of ``{"command_id", "exit_code"}`` and is
    drained once. A command with no result is never counted as red -- silence
    is not evidence -- and a result for an unexpected command is ignored.
    """
    expected = set(seed["expect_red"])
    red: set[str] = set()
    for result in results:
        command_id = result.get("command_id")
        if command_id not in expected:
            continue
        exit_code = result.get("exit_code")
        if exit_code is None or exit_code == 0:
            return False
        red.add(command_id)
    return red == expected


def unfalsified(
    packet: dict[str, Any], outcomes: dict[str, Iterable[dict[str, Any]]]
) -> list[str]:
    """The seed ids that did not falsify, in packet order.

    ``outcomes`` maps a seed id to that seed's results. A seed with no outcome
    at all counts as unfalsified -- silence is not evidence.
    """
    return [
        seed["id"]
        for seed in parse_seeds(packet)
        if not seed_falsified(seed, outcomes.get(seed["id"]) or [])
    ]