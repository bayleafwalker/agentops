#!/usr/bin/env python3
"""Mechanical primitives for the fresh post-session reconciler (item #1108).

This is the *latency-optimization* half of Tier 2 in
`docs/plans/agentops/session-mechanization-plan.md`: a fresh session,
triggered right after one session ends, that reconciles that session's
capsule immediately instead of waiting for the canonical periodic scribe.
The scribe remains the correctness path — if the reconciler never runs,
nothing is lost.

The reconciler shares the scribe's durable cursor
(`<root>/session-scribe/cursor.json`), so a capsule consumed by either
path is invisible to the other. All cursor math, capsule validation, and
proposal writing is delegated to `session_scribe.py`; this script adds
the single-capsule scope rules and idempotence guards the immediate path
needs (a re-triggered reconciler must be a clean no-op, never a duplicate
proposal).

Judgment (classifying the capsule into one of the six reconciliation
outcomes) is supplied by a fresh dispatched session following
`templates/dispatch/skills/session-reconciler/SKILL.md`, not by this
script.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_SCRIBE_PATH = Path(__file__).with_name("session_scribe.py")
_SPEC = importlib.util.spec_from_file_location("session_scribe", _SCRIBE_PATH)
assert _SPEC and _SPEC.loader
SCRIBE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(SCRIBE)

VALIDATOR = SCRIBE.VALIDATOR


def _load_proposals(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    result = []
    for path in sorted(root.glob("reconciliation-proposals/*.json")):
        value = VALIDATOR.load_json(path)
        VALIDATOR.validate_reconciliation_proposal(value, path)
        result.append((path, value))
    return result


def proposals_referencing(root: Path, capsule_id: str) -> list[dict[str, Any]]:
    """Proposals whose source capsules point at this capsule's artifact file."""
    needle = f"session-capsules/{capsule_id}.json"
    matches = []
    for path, proposal in _load_proposals(root):
        refs = [entry["capsule_ref"]["source"] for entry in proposal["source_capsules"]]
        if any(source.endswith(needle) for source in refs):
            matches.append(
                {
                    "proposal_id": proposal["proposal_id"],
                    "dedup_key": proposal["dedup_key"],
                    "classification": proposal["classification"],
                    "lifecycle_state": proposal["lifecycle"]["state"],
                    "path": str(path),
                }
            )
    return matches


def _find_capsule(root: Path, capsule_id: str) -> tuple[Path, dict[str, Any]] | None:
    for path, capsule in SCRIBE.load_capsules(root):
        if capsule["capsule_id"] == capsule_id:
            return path, capsule
    return None


def _consumed(root: Path, capsule_id: str) -> bool:
    cursor = SCRIBE.load_cursor(root)
    return capsule_id in set(cursor.get("consumed_capsule_ids", []))


def cmd_context(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    capsule_id = args.capsule_id

    if _consumed(root, capsule_id):
        print(
            json.dumps(
                {
                    "status": "already-consumed",
                    "capsule_id": capsule_id,
                    "note": "cursor already covers this capsule (scribe or a prior reconciler); nothing to do",
                    "existing_proposals": proposals_referencing(root, capsule_id),
                },
                indent=2,
            )
        )
        return 0

    found = _find_capsule(root, capsule_id)
    if found is None:
        print(f"context: capsule {capsule_id!r} not found under {root}/session-capsules", file=sys.stderr)
        return 1
    path, capsule = found

    target = capsule.get("target")
    siblings = []
    if target:
        cursor = SCRIBE.load_cursor(root)
        for _, other in SCRIBE.unconsumed(root, cursor):
            other_target = other.get("target")
            if other["capsule_id"] != capsule_id and other_target and other_target["ref"] == target["ref"]:
                siblings.append(
                    {
                        "capsule_id": other["capsule_id"],
                        "runtime_session_id": other["runtime_session_id"],
                        "ended_at": other["ended_at"],
                    }
                )

    out = {
        "status": "ready",
        "capsule_id": capsule_id,
        "capsule_path": str(path),
        "capsule_ref": SCRIBE.build_capsule_ref(root, path, args.project),
        "runtime_session_id": capsule["runtime_session_id"],
        "actor": capsule["actor"],
        "harness": capsule["harness"],
        "target": target,
        "claim": capsule.get("claim"),
        "starting_watermark": capsule["starting_watermark"],
        "end": capsule["end"],
        "git": capsule["git"],
        "verification": capsule["verification"],
        "related_unconsumed_same_target": siblings,
        "existing_proposals": proposals_referencing(root, capsule_id),
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    capsule_id = args.capsule_id

    if _consumed(root, capsule_id):
        print(f"emit: capsule {capsule_id} already consumed; nothing written (idempotent no-op)")
        return 0
    if _find_capsule(root, capsule_id) is None:
        print(f"emit: capsule {capsule_id!r} not found under {root}/session-capsules", file=sys.stderr)
        return 1

    proposal = VALIDATOR.load_json(args.proposal)
    sources = proposal.get("source_capsules", [])
    needle = f"session-capsules/{capsule_id}.json"
    if len(sources) != 1 or not sources[0].get("capsule_ref", {}).get("source", "").endswith(needle):
        print(
            "emit: the reconciler is single-capsule scoped — source_capsules must reference "
            f"exactly the capsule being reconciled ({capsule_id}); grouping belongs to the scribe",
            file=sys.stderr,
        )
        return 1

    return SCRIBE.cmd_emit(argparse.Namespace(root=root, proposal=args.proposal, consumes=[capsule_id]))


def cmd_no_change(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    if _consumed(root, args.capsule_id):
        print(f"no-change: capsule {args.capsule_id} already consumed; nothing written (idempotent no-op)")
        return 0
    return SCRIBE.cmd_no_change(
        argparse.Namespace(
            root=root,
            project=args.project,
            capsule_id=args.capsule_id,
            confidence=args.confidence,
            rationale=args.rationale,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    context_parser = subparsers.add_parser(
        "context", help="Assemble the reconciliation context packet for one capsule"
    )
    context_parser.add_argument("--root", type=Path, required=True, help="Artifact root, e.g. _artifacts/<repo>")
    context_parser.add_argument("--project", required=True, help="Portable repo scope identifier, e.g. agentops")
    context_parser.add_argument("--capsule-id", required=True)
    context_parser.set_defaults(func=cmd_context)

    emit_parser = subparsers.add_parser(
        "emit", help="Validate and persist an agent-authored single-capsule proposal"
    )
    emit_parser.add_argument("--root", type=Path, required=True)
    emit_parser.add_argument("--proposal", type=Path, required=True, help="Path to the authored proposal JSON")
    emit_parser.add_argument("--capsule-id", required=True)
    emit_parser.set_defaults(func=cmd_emit)

    no_change_parser = subparsers.add_parser(
        "no-change", help="Record an incidental-no-change outcome for the capsule"
    )
    no_change_parser.add_argument("--root", type=Path, required=True)
    no_change_parser.add_argument("--project", required=True)
    no_change_parser.add_argument("--capsule-id", required=True)
    no_change_parser.add_argument("--confidence", choices=("high", "medium", "low"), required=True)
    no_change_parser.add_argument("--rationale", required=True)
    no_change_parser.set_defaults(func=cmd_no_change)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
