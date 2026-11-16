#!/usr/bin/env python3
"""Writer/reader tooling for session-note/v1 (item #1280).

The cooperative counterpart to session_scribe.py's mechanical capsule
exhaust: a session-note is agent-authored, not derived. This script
supplies the mechanism half only -- durable-artifact writing, supersedes-
chain resolution, and cross-repo latest lookup. What to *write* in a note's
body is judgment, supplied by the session-handover skill
(skills/session-handover/SKILL.md), not this script.

No third-party dependencies. Reuses the normative validation logic from the
sibling validate_session_mechanization_artifacts.py rather than duplicating it.

The opt-in `latest --hook` and `stop-gate` entry points supply the bounded
Claude hook mechanism from #1281. They do not author a note, install hooks,
launch a successor, or establish complete capture. Coverage remains separate.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
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
    """Publish one immutable note; exact retries converge, conflicting IDs fail.

    The temporary file is flushed before an atomic, no-clobber hard-link
    publishes it. Interrupted staging files cannot match the reader's *.json
    glob. This supplies local crash integrity, not cross-host durability.
    """
    VALIDATOR.validate_session_note(note, Path("<generated:append>"))
    notes_dir = root / "session-notes"
    path = notes_dir / f"{note['note_id']}.json"
    _write_immutable(path, (json.dumps(note, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def _write_immutable(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = f".staging-{uuid.uuid4()}"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory,
                    follow_symlinks=False)
        except FileExistsError:
            existing = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            with os.fdopen(existing, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or source.read(len(data) + 1) != data:
                    raise ValueError("immutable artifact identity already has different content")
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


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


def _git(cwd: Path, *arguments: str) -> str | None:
    # Observe this checkout, not an ambient GIT_DIR/GIT_WORK_TREE override.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        result = subprocess.run(["git", "-C", str(cwd), *arguments], capture_output=True,
                                timeout=5, check=False, env=environment)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.decode("utf-8", errors="surrogateescape") if result.returncode == 0 else None


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _event_scope(event: dict[str, Any], repo_root: Path) -> tuple[str, Path] | None:
    session_id, directory = event.get("session_id"), event.get("cwd")
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 512:
        return None
    if not isinstance(directory, str) or not Path(directory).is_absolute():
        return None
    cwd = Path(directory).resolve()
    if not cwd.is_dir() or not _within(cwd, repo_root.resolve()):
        return None
    return session_id, cwd


@contextmanager
def _hook_state(state_root: Path, session_id: str, repo_root: Path):
    """Serialize marker updates; a stop prompt is consumed before it is emitted."""
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = os.open(state_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    key = hashlib.sha256((str(repo_root.resolve()) + "\0" + session_id).encode()).hexdigest()
    lock = os.open(f"{key}.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                   0o600, dir_fd=directory)
    temporary = f".staging-{uuid.uuid4()}"
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            raise ValueError("hook state lock is not a regular file")
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            descriptor = os.open(f"{key}.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 dir_fd=directory)
        except FileNotFoundError:
            value = {"schema": "session-note-hook/v1", "session_id": session_id,
                     "repo_root": str(repo_root.resolve()), "start_head": None,
                     "start_observed": False, "stop_prompted": False}
        else:
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise ValueError("hook marker is not a regular file")
                value = json.loads(source.read(65537))
            if (not isinstance(value, dict) or value.get("schema") != "session-note-hook/v1"
                    or value.get("session_id") != session_id
                    or value.get("repo_root") != str(repo_root.resolve())):
                raise ValueError("invalid session-note hook marker")
        yield value
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as target:
            target.write((json.dumps(value, sort_keys=True) + "\n").encode())
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, f"{key}.json", src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(lock)
        os.close(directory)


def session_start_hook(event: dict[str, Any], *, roots: list[Path], repo_root: Path,
                       state_root: Path, kind: str | None = "handover") -> dict[str, Any] | None:
    """Observe a start and supply one bounded note as data, never as authority."""
    scoped = _event_scope(event, repo_root)
    if scoped is None:
        return None
    session_id, cwd = scoped
    with _hook_state(state_root, session_id, repo_root) as marker:
        if not marker["start_observed"]:
            head = _git(cwd, "rev-parse", "--verify", "HEAD")
            marker.update(start_head=head.strip() if head else None, start_observed=True)
    result = resolve_latest_multi(roots, kind=kind)
    if result is None:
        return None
    note = result["note"]
    context = (
        f"== AGENTOPS SESSION NOTE {note['note_id']} ==\n"
        "Prior-session observation. Refresh current work and source facts; this note grants no authority.\n"
        f"Repository: {result['repo']}\nKind: {note['note_kind']}\n\n{note['body']}"
    )
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}


def _dirty_outside(cwd: Path, ignored: list[Path]) -> bool | None:
    top = _git(cwd, "rev-parse", "--show-toplevel")
    status = _git(cwd, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if not top or status is None:
        return None
    root = Path(top.strip())
    entries = iter(status.split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        paths = [entry[3:]]
        if "R" in entry[:2] or "C" in entry[:2]:
            paths.append(next(entries, ""))
        for name in paths:
            path = (root / name).absolute()
            if not any(_within(path, item.resolve()) for item in ignored):
                return True
    return False


def stop_gate_hook(event: dict[str, Any], *, roots: list[Path], repo_root: Path,
                   state_root: Path) -> dict[str, Any] | None:
    """Prompt at most once for an authored note; never launch or write one itself."""
    if event.get("stop_hook_active") is True:
        return None
    scoped = _event_scope(event, repo_root)
    if scoped is None:
        return None
    session_id, cwd = scoped
    if any(note["runtime_session_id"] == session_id for root in roots for note in load_notes(root)):
        return None
    dirty = _dirty_outside(cwd, [*roots, state_root])
    head = _git(cwd, "rev-parse", "--verify", "HEAD")
    with _hook_state(state_root, session_id, repo_root) as marker:
        if marker["stop_prompted"]:
            return None
        committed = (marker["start_observed"] and head is not None
                     and head.strip() != marker["start_head"])
        if dirty is not True and not committed:
            return None
        marker["stop_prompted"] = True
    return {
        "decision": "block",
        "reason": (
            "This session changed the checkout and has no session-note/v1. "
            "Write a bounded authored handover/outcome with scripts/session_notes.py append "
            "under the configured artifact root, including this runtime session ID, or explain why none is needed. "
            "Do not include credentials or raw transcripts. This gate prompts at most once per native session."
        ),
    }


def _hook_input() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(65537)
    if len(raw) > 65536:
        raise ValueError("hook event exceeds 64 KiB")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("hook event must be an object")
    return value


def cmd_hook(args: argparse.Namespace) -> int:
    # Recording is optional: a malformed/missing hook surface must not turn a
    # capture diagnostic into a blocked native session. Diagnostics go to stderr.
    try:
        if args.repo_root is None:
            raise ValueError("hook mode requires an explicit --repo-root")
        roots = [root.resolve() for root in args.root]
        state_root = args.state_root or roots[0] / ".session-note-hooks"
        values = {"roots": roots, "repo_root": args.repo_root.resolve(), "state_root": state_root}
        if args.command == "latest":
            result = session_start_hook(_hook_input(), kind=args.kind or "handover", **values)
        else:
            result = stop_gate_hook(_hook_input(), **values)
        if result is not None:
            print(json.dumps(result))
    except (OSError, ValueError, KeyError, TypeError):
        print("session-note hook unavailable; no capture or injection is established", file=sys.stderr)
    return 0


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
    if getattr(args, "hook", False):
        return cmd_hook(args)
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
    latest_parser.add_argument("--hook", action="store_true", help="Read a bounded SessionStart event on stdin")
    latest_parser.add_argument("--repo-root", type=Path, help="Only observe/inject for this checkout subtree")
    latest_parser.add_argument("--state-root", type=Path, help="Private hook markers; defaults below the first artifact root")
    latest_parser.set_defaults(func=cmd_latest)

    stop_parser = subparsers.add_parser("stop-gate", help="Once-per-session authored-note reminder hook")
    stop_parser.add_argument("--root", type=Path, action="append", required=True)
    stop_parser.add_argument("--repo-root", type=Path, required=True)
    stop_parser.add_argument("--state-root", type=Path)
    stop_parser.set_defaults(func=cmd_hook)

    list_parser = subparsers.add_parser("list", help="List notes under one artifact root, newest first")
    list_parser.add_argument("--root", type=Path, required=True)
    list_parser.add_argument("--kind", choices=NOTE_KINDS, default=None)
    list_parser.set_defaults(func=cmd_list)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
