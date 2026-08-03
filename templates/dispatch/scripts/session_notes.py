#!/usr/bin/env python3
"""Writer/reader tooling for session-note/v1 (item #1280).

The cooperative counterpart to session_scribe.py's mechanical capsule
exhaust: a session-note is agent-authored, not derived. This script
supplies the mechanism half only -- durable-artifact writing, supersedes-
chain resolution, and cross-repo latest lookup. What to *write* in a note's
body is judgment, supplied by the session-handover skill
(templates/dispatch/skills/session-handover/SKILL.md), not this script.

No third-party dependencies. Reuses the normative validation logic from the
sibling validate_session_mechanization_artifacts.py rather than duplicating it.

Hook wiring (`latest --hook`, `stop-gate`) and the `coverage` report command
are out of scope here -- see AgentOps #1281.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_VALIDATOR_PATH = Path(__file__).with_name("validate_session_mechanization_artifacts.py")
_SPEC = importlib.util.spec_from_file_location("session_mechanization_validator", _VALIDATOR_PATH)
assert _SPEC and _SPEC.loader
VALIDATOR = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(VALIDATOR)

NOTE_KINDS = ("handover", "summary", "outcome")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_note(
    *,
    repo: str,
    kind: str,
    body: str,
    target_refs: list[str] | None = None,
    supersedes: str | None = None,
    runtime_session_id: str | None = None,
    capsule_ref: dict[str, Any] | None = None,
    raw_transcript_captured: bool = False,
) -> dict[str, Any]:
    """Build a schema-valid session-note/v1 artifact. Raises before writing anything."""
    if kind not in NOTE_KINDS:
        raise ValueError(f"note_kind {kind!r} is not one of {NOTE_KINDS}")
    note = {
        "schema_version": "session-note/v1",
        "note_id": str(uuid.uuid4()),
        "origin_stream_id": str(uuid.uuid4()),
        "runtime_session_id": runtime_session_id,
        "repo": {"project": repo},
        "note_kind": kind,
        "target_refs": list(target_refs) if target_refs else [],
        "capsule_ref": capsule_ref,
        "created_at": _now_iso(),
        "supersedes": supersedes,
        "body": body,
        "privacy": {
            "raw_transcript_captured": raw_transcript_captured,
            "raw_transcript_ref": None,
            "retention_days": None,
        },
    }
    VALIDATOR.validate_session_note(note, Path("<generated:new_note>"))
    return note


def append(root: Path, note: dict[str, Any]) -> Path:
    """Validate and persist a note under root/session-notes/<note_id>.json."""
    VALIDATOR.validate_session_note(note, Path("<generated:append>"))
    notes_dir = root / "session-notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    path = notes_dir / f"{note['note_id']}.json"
    path.write_text(json.dumps(note, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_notes(root: Path) -> list[dict[str, Any]]:
    """Load and validate every note under root/session-notes/*.json."""
    notes = []
    for path in sorted(root.glob("session-notes/*.json")):
        value = VALIDATOR.load_json(path)
        VALIDATOR.validate_session_note(value, path)
        notes.append(value)
    return notes


def resolve_latest(notes: list[dict[str, Any]], *, kind: str | None = None) -> dict[str, Any] | None:
    """Resolve the current head of the supersedes chain.

    A head is a note no other note claims to supersede. Concurrent /clear
    sessions can produce more than one head; ties break on newest
    created_at, then note_id, for determinism. A dangling supersedes
    pointer (the ancestor is missing or off-machine) never affects whether
    *this* note is a head -- only incoming references do. A cycle leaves no
    note uncontested as a head; the resolver falls back to the newest note
    by the same tiebreak rather than raising or hanging.
    """
    candidates = [n for n in notes if kind is None or n["note_kind"] == kind]
    if not candidates:
        return None
    superseded_ids = {n["supersedes"] for n in candidates if n["supersedes"]}
    heads = [n for n in candidates if n["note_id"] not in superseded_ids]
    pool = heads if heads else candidates
    return max(pool, key=lambda n: (n["created_at"], n["note_id"]))


def resolve_latest_multi(roots: list[Path], *, kind: str | None = None) -> dict[str, Any] | None:
    """Resolve the latest note across several repos' artifact roots.

    Each root is resolved independently (a supersedes chain is local to one
    repo), then the per-root winners are compared. The reported repo comes
    from the winning note's own repo.project field, not from the caller --
    the note is already self-describing.
    """
    winners = []
    for root in roots:
        candidate = resolve_latest(load_notes(root), kind=kind)
        if candidate is not None:
            winners.append(candidate)
    if not winners:
        return None
    winner = max(winners, key=lambda n: (n["created_at"], n["note_id"]))
    return {"repo": winner["repo"]["project"], "note": winner}


def list_notes(notes: list[dict[str, Any]], *, kind: str | None = None) -> list[dict[str, Any]]:
    """List notes, newest first."""
    candidates = [n for n in notes if kind is None or n["note_kind"] == kind]
    return sorted(candidates, key=lambda n: (n["created_at"], n["note_id"]), reverse=True)


def cmd_append(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    note = new_note(
        repo=args.repo,
        kind=args.kind,
        body=args.body,
        target_refs=args.target_refs,
        supersedes=args.supersedes,
        runtime_session_id=args.runtime_session_id,
    )
    path = append(root, note)
    print(f"wrote {path}")
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    roots = [r.resolve() for r in args.root]
    result = resolve_latest_multi(roots, kind=args.kind)
    if result is None:
        print("no session note found", file=__import__("sys").stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    notes = list_notes(load_notes(root), kind=args.kind)
    print(json.dumps(notes, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    append_parser = subparsers.add_parser("append", help="Write a new session note")
    append_parser.add_argument("--root", type=Path, required=True, help="Artifact root, e.g. _artifacts/<repo>")
    append_parser.add_argument("--repo", required=True)
    append_parser.add_argument("--kind", choices=NOTE_KINDS, required=True)
    append_parser.add_argument("--body", required=True)
    append_parser.add_argument("--target-refs", nargs="*", default=None, metavar="REF")
    append_parser.add_argument("--supersedes", default=None, metavar="NOTE_ID")
    append_parser.add_argument("--runtime-session-id", default=None)
    append_parser.set_defaults(func=cmd_append)

    latest_parser = subparsers.add_parser("latest", help="Resolve the latest note across one or more artifact roots")
    latest_parser.add_argument("--root", type=Path, action="append", required=True, help="Repeat for cross-repo resolution")
    latest_parser.add_argument("--kind", choices=NOTE_KINDS, default=None)
    latest_parser.set_defaults(func=cmd_latest)

    list_parser = subparsers.add_parser("list", help="List notes under one artifact root, newest first")
    list_parser.add_argument("--root", type=Path, required=True)
    list_parser.add_argument("--kind", choices=NOTE_KINDS, default=None)
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
