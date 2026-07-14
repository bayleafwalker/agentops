#!/usr/bin/env python3
"""Mechanical primitives for the canonical periodic scribe (item #1107).

This script is the *mechanism* half of the scribe described in
`docs/plans/agentops/session-mechanization-plan.md`: durable-cursor
bookkeeping, deterministic capsule discovery/grouping, and schema-validated
artifact writing. It never classifies work — that is the *judgment* half,
supplied by a fresh dispatched session following
`templates/dispatch/skills/session-scribe/SKILL.md`.

No third-party dependencies. Reuses the normative validation logic from the
sibling `validate_session_mechanization_artifacts.py` rather than duplicating
it.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_VALIDATOR_PATH = Path(__file__).with_name("validate_session_mechanization_artifacts.py")
_SPEC = importlib.util.spec_from_file_location("session_mechanization_validator", _VALIDATOR_PATH)
assert _SPEC and _SPEC.loader
VALIDATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(VALIDATOR)

CURSOR_SCHEMA_VERSION = "session-scribe-cursor/v1"
_PENDING_LIFECYCLE = {
    "state": "pending",
    "decided_at": None,
    "decided_by": None,
    "rejection_reason": None,
    "superseded_by": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value: str) -> datetime:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(text)


def cursor_path(root: Path) -> Path:
    return root / "session-scribe" / "cursor.json"


def load_cursor(root: Path) -> dict[str, Any]:
    path = cursor_path(root)
    if not path.exists():
        return {
            "schema_version": CURSOR_SCHEMA_VERSION,
            "consumed_capsule_ids": [],
            "last_advanced_at": None,
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    value.setdefault("consumed_capsule_ids", [])
    return value


def save_cursor(root: Path, cursor: dict[str, Any]) -> None:
    path = cursor_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cursor, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def discover_capsules(root: Path) -> list[Path]:
    return sorted(root.glob("session-capsules/*.json"))


def load_capsules(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    result = []
    for path in discover_capsules(root):
        value = VALIDATOR.load_json(path)
        VALIDATOR.validate_session_capsule(value, path)
        result.append((path, value))
    return result


def _sort_key(entry: tuple[Path, dict[str, Any]]) -> tuple[str, str]:
    _, capsule = entry
    return (capsule["ended_at"], capsule["capsule_id"])


def unconsumed(root: Path, cursor: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    consumed = set(cursor.get("consumed_capsule_ids", []))
    entries = [entry for entry in load_capsules(root) if entry[1]["capsule_id"] not in consumed]
    return sorted(entries, key=_sort_key)


def group_by_target(entries: list[tuple[Path, dict[str, Any]]]) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    groups: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path, capsule in entries:
        target = capsule.get("target")
        key = target["ref"] if target else f"capsule:{capsule['capsule_id']}"
        groups.setdefault(key, []).append((path, capsule))
    return groups


def build_capsule_ref(root: Path, path: Path, project: str) -> dict[str, str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rel = path.relative_to(root)
    return {
        "kind": "artifact",
        "source": f"{project}:_artifacts/{project}/{rel.as_posix()}",
        "revision": f"sha256:{digest}",
    }


def _write_proposal(root: Path, proposal: dict[str, Any]) -> Path:
    out_dir = root / "reconciliation-proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{proposal['proposal_id']}.json"
    with out_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(proposal, indent=2, sort_keys=True) + "\n")
    return out_path


def _advance(root: Path, capsule_ids: list[str]) -> None:
    cursor = load_cursor(root)
    consumed = set(cursor.get("consumed_capsule_ids", []))
    consumed.update(capsule_ids)
    cursor["consumed_capsule_ids"] = sorted(consumed)
    cursor["last_advanced_at"] = _now_iso()
    save_cursor(root, cursor)


def cmd_plan(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    cursor = load_cursor(root)
    entries = unconsumed(root, cursor)
    groups = group_by_target(entries)
    out = {
        "cursor_last_advanced_at": cursor.get("last_advanced_at"),
        "unconsumed_count": len(entries),
        "groups": [
            {
                "group_key": key,
                "capsules": [
                    {
                        "capsule_id": capsule["capsule_id"],
                        "runtime_session_id": capsule["runtime_session_id"],
                        "target": capsule.get("target"),
                        "ended_at": capsule["ended_at"],
                        "path": str(path),
                    }
                    for path, capsule in members
                ],
            }
            for key, members in sorted(groups.items())
        ],
    }
    print(json.dumps(out, indent=2))
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    proposal = VALIDATOR.load_json(args.proposal)
    proposal.setdefault("schema_version", "reconciliation-proposal/v1")
    proposal.setdefault("proposal_id", str(uuid.uuid4()))
    proposal.setdefault("created_at", _now_iso())
    proposal.setdefault("lifecycle", dict(_PENDING_LIFECYCLE))
    VALIDATOR.validate_reconciliation_proposal(proposal, args.proposal)

    known = {capsule["capsule_id"] for _, capsule in load_capsules(root)}
    missing = [capsule_id for capsule_id in args.consumes if capsule_id not in known]
    if missing:
        print(f"emit: unknown capsule id(s) not found under {root}/session-capsules: {missing}", file=sys.stderr)
        return 1

    out_path = _write_proposal(root, proposal)
    _advance(root, args.consumes)
    print(f"wrote {out_path}")
    print(f"advanced cursor: {len(args.consumes)} capsule(s) consumed")
    return 0


def cmd_no_change(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    capsules = {capsule["capsule_id"]: (path, capsule) for path, capsule in load_capsules(root)}
    if args.capsule_id not in capsules:
        print(f"no-change: capsule {args.capsule_id!r} not found under {root}/session-capsules", file=sys.stderr)
        return 1
    path, capsule = capsules[args.capsule_id]

    proposal = {
        "schema_version": "reconciliation-proposal/v1",
        "proposal_id": str(uuid.uuid4()),
        "dedup_key": f"{args.project}:capsule:{args.capsule_id}:no-change",
        "created_at": _now_iso(),
        "source_capsules": [
            {
                "runtime_session_id": capsule["runtime_session_id"],
                "capsule_ref": build_capsule_ref(root, path, args.project),
            }
        ],
        "evidence_refs": [],
        "basis": {
            "observed_revision": f"capsule:{args.capsule_id}",
            "current_revision": f"capsule:{args.capsule_id}",
        },
        "target": None,
        "classification": "incidental-no-change",
        "proposed_commands": [],
        "confidence": {"level": args.confidence, "rationale": args.rationale},
        "lifecycle": dict(_PENDING_LIFECYCLE),
    }
    VALIDATOR.validate_reconciliation_proposal(proposal, Path("<generated:no-change>"))

    out_path = _write_proposal(root, proposal)
    _advance(root, [args.capsule_id])
    print(f"wrote {out_path}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    cursor = load_cursor(root)
    consumed = set(cursor.get("consumed_capsule_ids", []))
    capsules = load_capsules(root)
    now = datetime.now(timezone.utc)

    unreconciled = []
    for _, capsule in capsules:
        if capsule["capsule_id"] in consumed:
            continue
        age_seconds = (now - _parse_iso(capsule["ended_at"])).total_seconds()
        unreconciled.append(
            {
                "capsule_id": capsule["capsule_id"],
                "runtime_session_id": capsule["runtime_session_id"],
                "ended_at": capsule["ended_at"],
                "age_seconds": age_seconds,
            }
        )
    unreconciled.sort(key=lambda entry: entry["age_seconds"], reverse=True)

    summary = {
        "total_capsules": len(capsules),
        "reconciled_count": len(capsules) - len(unreconciled),
        "unreconciled_count": len(unreconciled),
        "oldest_unreconciled_age_seconds": unreconciled[0]["age_seconds"] if unreconciled else None,
        "unreconciled": unreconciled,
        "cursor_last_advanced_at": cursor.get("last_advanced_at"),
    }
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="List unconsumed session capsules, grouped by target ref")
    plan_parser.add_argument("--root", type=Path, required=True, help="Artifact root, e.g. _artifacts/<repo>")
    plan_parser.set_defaults(func=cmd_plan)

    emit_parser = subparsers.add_parser("emit", help="Validate and persist an agent-authored proposal")
    emit_parser.add_argument("--root", type=Path, required=True)
    emit_parser.add_argument("--proposal", type=Path, required=True, help="Path to the authored proposal JSON")
    emit_parser.add_argument("--consumes", nargs="+", required=True, metavar="CAPSULE_ID")
    emit_parser.set_defaults(func=cmd_emit)

    no_change_parser = subparsers.add_parser("no-change", help="Record an incidental-no-change outcome for one capsule")
    no_change_parser.add_argument("--root", type=Path, required=True)
    no_change_parser.add_argument("--project", required=True)
    no_change_parser.add_argument("--capsule-id", required=True)
    no_change_parser.add_argument("--confidence", choices=("high", "medium", "low"), required=True)
    no_change_parser.add_argument("--rationale", required=True)
    no_change_parser.set_defaults(func=cmd_no_change)

    status_parser = subparsers.add_parser("status", help="Print reconciliation-lag metrics")
    status_parser.add_argument("--root", type=Path, required=True)
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
