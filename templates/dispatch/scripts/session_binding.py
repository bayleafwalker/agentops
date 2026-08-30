#!/usr/bin/env python3
"""Produce the session-scoped half of the resolved-context invariant.

``docs/contracts/session-resolved-context.md`` splits that invariant by lifetime.
The *write-scoped* half -- path attribution, resolved per write -- is instantiated by
auditctl's ``AuditContext``. The *session-scoped* half -- identity, role, harness,
environment, and the pinned revisions and digests they resolve against, resolved once
at session creation and immutable -- has had a name (``SessionBinding``) and no
producer. This is the producer.

What it is not
--------------
It is deliberately **not** ``session-capsule/v1``. Two handovers have recorded the
capsule schema as this producer's schema; reading it settles that it is not. The
capsule is *end*-of-session exhaust -- git diff, verification results, an end kind --
and it answers "what did this session do". A binding answers "what is this session,
and what entitled it", is written at the start, and never changes. Building the
capsule would have been the third instance this week of verifying the thing next to
the thing.

The question it exists to answer
--------------------------------
The contract's open finding 2 states it exactly: not "do these values agree", which a
coherent redirect already satisfies, but **"who set this, and what entitled them to"**.
So the binding records every settings source in effect by path *and content digest*.
A shared-scope process that changes what a session may do changes one of those files,
and the digest is what makes the change visible afterwards, from the record, without
re-deriving anything.

Resolution is borrowed, never re-derived
----------------------------------------
The environment record is resolved through ``resolve_environment_record`` -- the same
function ``render_environment_context`` and ``project_release`` use, hostname
normalization included. Re-deriving it here in a few lines of shell is precisely the
defect the contract exists to end: "two independent resolutions that happen to agree
are not one resolution".

Immutability is enforced, not asserted
--------------------------------------
``SessionStart`` fires again on resume, clear and compact. The first write for a
runtime session id wins; a later one is compared field by field against it. Equal, it
is a no-op and the source is recorded. Different, it is a **contradiction** and the
run fails closed with the differing fields named, per obligation 2 of the contract.
Nothing is silently preferred.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import auditctl_resolve  # noqa: E402
from resolve_environment_record import (  # noqa: E402
    EnvironmentResolutionError,
    resolve_environment_record,
)

SCHEMA_VERSION = "session-binding/v0"

#: Settings layers a Claude Code session resolves against, in precedence order. Each is
#: recorded whether or not it exists: "this file was absent" is as much a part of what
#: entitled the session as its contents, and a layer that appears later is a change.
SETTINGS_LAYERS = (
    ("managed", Path("/etc/claude-code/managed-settings.json")),
    ("user", Path.home() / ".claude" / "settings.json"),
    ("project", None),  # <cwd>/.claude/settings.json
    ("local", None),  # <cwd>/.claude/settings.local.json
)


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _settings_sources(cwd: Path) -> list[dict]:
    sources = []
    for scope, fixed in SETTINGS_LAYERS:
        if fixed is not None:
            path = fixed
        elif scope == "project":
            path = cwd / ".claude" / "settings.json"
        else:
            path = cwd / ".claude" / "settings.local.json"
        present = path.is_file()
        sources.append({
            "scope": scope,
            "path": str(path),
            "present": present,
            "sha256": _digest(path) if present else None,
        })
    return sources


def _environment(records_dir: Path, hostname: str) -> dict:
    """Resolve this host's environment record, or say plainly that it did not."""
    try:
        path = resolve_environment_record(records_dir, hostname=hostname)
    except EnvironmentResolutionError as exc:
        return {"record": None, "resolution_source": "unresolved", "detail": str(exc)}
    except OSError as exc:
        return {"record": None, "resolution_source": "unreadable", "detail": str(exc)}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"record": None, "resolution_source": "unparseable", "detail": str(exc)}
    return {
        "record": {
            "id": record.get("id"),
            "environment_class": record.get("environment_class"),
            "revision": record.get("revision"),
            "path": str(path),
            "sha256": _digest(path),
        },
        "resolution_source": "hostname-match",
        "detail": None,
    }


def _project(cwd: Path) -> dict:
    """The project binding for the workspace this session started in.

    Walks up from the session's cwd because a session routinely starts in a
    subdirectory. It records the file it found, not the directory it was launched
    from: the latter is write-scoped and belongs to `AuditContext`.
    """
    for candidate in [cwd, *cwd.parents]:
        path = candidate / "project.toml"
        if not path.is_file():
            continue
        try:
            import tomllib
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # a malformed binding is a finding, not a crash
            return {"project_id": None, "path": str(path), "sha256": _digest(path),
                    "resolution_source": "unparseable", "detail": str(exc)}
        return {
            "project_id": data.get("project_id"),
            "display_name": data.get("display_name"),
            "home_repo": data.get("home_repo"),
            "path": str(path),
            "sha256": _digest(path),
            "resolution_source": "ancestor-walk",
            "detail": None,
        }
    return {"project_id": None, "path": None, "sha256": None,
            "resolution_source": "undeclared", "detail": None}


def build(event: dict, *, records_dir: Path, hostname: str | None = None) -> dict:
    session_id = (event.get("session_id") or "").strip()
    if not session_id:
        raise ValueError("SessionStart payload carries no session_id")
    cwd = Path(event.get("cwd") or os.getcwd())
    host = hostname or socket.gethostname()
    return {
        "schema_version": SCHEMA_VERSION,
        "binding_id": str(uuid.uuid4()),
        "runtime_session_id": session_id,
        "resolved_at": _now(),
        "harness": {"name": "claude"},
        # The entry that created the binding, recorded once. `source` is a property of
        # an *entry* (startup, resume, clear, compact), not of the session, so it is
        # excluded from the immutable comparison below -- the first version of this put
        # it inside `harness` and every resume then read as a contradiction, which is a
        # fail-closed rule earning its way to being routed around.
        "created_at_entry": {"source": str(event.get("source") or "unknown")},
        "actor": {
            "os_user": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
            "uid": os.getuid(),
        },
        "host": {"hostname": host},
        "environment": _environment(records_dir, host),
        "workspace": {"cwd": str(cwd), "project": _project(cwd)},
        "entitlement": {
            "settings_sources": _settings_sources(cwd),
            "resolution_source": "declared-layers",
        },
    }


#: Fields whose value is a property of the *session*, not of the moment it was written.
#: A second SessionStart -- resume, clear, compact -- must agree on every one of these.
IMMUTABLE_FIELDS = ("runtime_session_id", "harness", "actor", "host", "environment",
                    "workspace", "entitlement")
#: Recorded, deliberately not compared. See `created_at_entry` in `build`.
PER_ENTRY_FIELDS = ("binding_id", "resolved_at", "created_at_entry")


def contradictions(existing: dict, candidate: dict) -> list[str]:
    return [
        field for field in IMMUTABLE_FIELDS
        if existing.get(field) != candidate.get(field)
    ]


def publish(binding: dict, *, quiet: bool = False) -> None:
    """Record the binding as an observation. Never fatal: telemetry is not the run."""
    auditctl = auditctl_resolve.resolve(quiet_when_absent=quiet)
    if auditctl is None:
        return
    metadata = json.dumps({
        "binding_id": binding["binding_id"],
        "runtime_session_id": binding["runtime_session_id"],
        "environment_id": (binding["environment"]["record"] or {}).get("id"),
        "environment_resolution": binding["environment"]["resolution_source"],
        "project_id": binding["workspace"]["project"].get("project_id"),
        "settings_sources": [
            {"scope": s["scope"], "present": s["present"], "sha256": s["sha256"]}
            for s in binding["entitlement"]["settings_sources"]
        ],
    })
    summary = (
        f"session bound in {Path(binding['workspace']['cwd']).name}: "
        f"env {(binding['environment']['record'] or {}).get('id') or 'unresolved'}, "
        f"{sum(1 for s in binding['entitlement']['settings_sources'] if s['present'])}"
        " settings layers"
    )
    subprocess.run(
        [auditctl, "add", "--type", "session.binding", "--source", "claude-hook",
         "--actor", "claude-hook", "--summary", summary, "--metadata", metadata],
        capture_output=True, check=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bindings-dir", type=Path,
                        default=Path(os.environ.get(
                            "AGENTOPS_SESSION_BINDING_DIR",
                            "/projects/dev/.claude/state/session-bindings")))
    parser.add_argument("--records-dir", type=Path,
                        default=Path(__file__).resolve().parents[1]
                        / "environment-record")
    parser.add_argument("--hostname", help="override the detected hostname (for testing)")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args(argv)

    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError as exc:
        print(f"session_binding: unreadable SessionStart payload: {exc}", file=sys.stderr)
        return 0  # a hook must not cost the session its start

    try:
        binding = build(event, records_dir=args.records_dir, hostname=args.hostname)
    except ValueError as exc:
        print(f"session_binding: {exc}", file=sys.stderr)
        return 0

    args.bindings_dir.mkdir(parents=True, exist_ok=True)
    path = args.bindings_dir / f"{binding['runtime_session_id']}.json"

    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
        differing = contradictions(existing, binding)
        if differing:
            # Fail closed and say which fields. The contract forbids silently
            # preferring one of two incompatible resolutions; that preference is
            # exactly what wrote correct indexes and misplaced shards in August.
            print(
                "session_binding: contradiction on re-entry to session "
                f"{binding['runtime_session_id']}: {', '.join(differing)} differ from "
                f"the binding resolved at {existing.get('resolved_at')}",
                file=sys.stderr,
            )
            return 1
        return 0  # already bound, and it agrees

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic: a whole binding or none
    if not args.no_publish:
        publish(binding, quiet=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
