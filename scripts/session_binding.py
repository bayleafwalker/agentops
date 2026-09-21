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

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def _native_instruction_root(cwd: Path) -> tuple[Path, str]:
    """The directory the native root-to-CWD instruction walk starts from.

    A session binding has no operator-supplied ``--root`` the way the retired
    ``instruction_doctor.py`` did, so one is derived: the directory holding
    the workspace's ``project.toml`` (the same ancestor walk ``_project``
    already does) when one is declared, else the enclosing Git worktree, else
    ``cwd`` itself -- a walk of one directory, which is still an honest
    observation and not a guess.
    """
    for candidate in [cwd, *cwd.parents]:
        if (candidate / "project.toml").is_file():
            return candidate, "project-root"
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2, check=False,
        )
        top = result.stdout.strip()
        if result.returncode == 0 and top:
            return Path(top), "git-toplevel"
    except (OSError, subprocess.SubprocessError):
        pass
    return cwd, "cwd"


def _instructions(cwd: Path) -> dict:
    """The observed native instruction chain: root-to-CWD ``AGENTS.md``/``CLAUDE.md``.

    TS-3 (``docs/plans/2026-09-17-target-state.md``): role and skills are
    *observed*, not compiled. This is the observation half of the retired
    ``instruction_doctor.py`` (39cf66a) -- the native root-to-CWD source walk,
    recorded as path plus content digest -- and stops there. It deliberately
    does **not** port that doctor's other half: comparing the walk against a
    v2 dispatch manifest's source catalog, gates.json or a skill lock. That
    comparison is the *compiled* profile TS-3 says this estate does not keep.

    ``skills`` is empty here at ``SessionStart``: the hook fires before any skill is
    loaded in the turn, so which skills a session will use is not yet determinable at
    binding time. It is appended to afterward by ``record_skill``/``--record-skill``,
    called from a ``PostToolUse`` hook keyed on the ``Skill`` tool (#2481), which is
    the seam that has the digest at invocation time. A session whose hook is not
    registered simply keeps an empty list here, which is still not read as "no skills
    were used".
    """
    root, root_source = _native_instruction_root(cwd)
    root = root.resolve()
    directories = [root]
    current = root
    try:
        relative_parts = cwd.resolve().relative_to(root).parts
    except ValueError:
        relative_parts = ()  # cwd is not under root (e.g. a one-directory walk)
    for part in relative_parts:
        current = current / part
        directories.append(current)
    sources = []
    for directory in directories:
        for name in ("AGENTS.md", "CLAUDE.md"):
            path = directory / name
            if path.is_file() and not path.is_symlink():
                sources.append({
                    "path": str(path),
                    "name": name,
                    "sha256": _digest(path),
                })
    return {
        "root": str(root),
        "root_source": root_source,
        "sources": sources,
        "skills": [],
    }


def _resolve_skill(name: str, cwd: Path) -> dict:
    """Locate a skill's ``SKILL.md`` the way the harness would have loaded it.

    A ``plugin:skill`` name has no filesystem form here to resolve against, so it is
    left unresolved rather than guessed at. Otherwise the first existing of the cwd's
    own skills directory, the native instruction root's, and the user's is taken --
    the same three places a session's instructions are rooted in.
    """
    if ":" in name:
        return {"name": name, "path": None, "sha256": None, "resolution": "unresolved"}
    root, _ = _native_instruction_root(cwd)
    candidates = (
        (cwd.resolve() / ".claude" / "skills" / name / "SKILL.md", "cwd"),
        (root.resolve() / ".claude" / "skills" / name / "SKILL.md", "root"),
        (Path.home() / ".claude" / "skills" / name / "SKILL.md", "user"),
    )
    for path, resolution in candidates:
        if path.is_file():
            return {"name": name, "path": str(path), "sha256": _digest(path),
                     "resolution": resolution}
    return {"name": name, "path": None, "sha256": None, "resolution": "unresolved"}


def record_skill(bindings_dir: Path, session_id: str, name: str, *, cwd: Path,
                  loaded_at: str | None = None) -> dict | None:
    """Append an observed skill digest to a binding already on disk.

    Called from a ``PostToolUse`` hook on the ``Skill`` tool (#2481) -- the seam
    decided for this because the acceptance needs the digest at invocation time, and a
    ``Stop``-time reconstruction would have to parse the harness transcript instead.
    Idempotent on ``(path, sha256)``: recording an unchanged skill a second time adds
    no second entry, so a hook that fires more than once for the same load is safe.
    Unresolved names carry ``path: null, sha256: null`` by construction, so the name
    is folded into that comparison for them too -- otherwise every unresolved skill
    would collide on the same null pair and only the first name would ever appear.
    Never raises -- a hook must not cost the session -- so a missing or unreadable
    binding is reported to stderr and answered with ``None``.
    """
    path = bindings_dir / f"{session_id}.json"
    try:
        binding = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"session_binding: cannot record skill for session {session_id}: {exc}",
              file=sys.stderr)
        return None

    entry = _resolve_skill(name, cwd)
    entry["loaded_at"] = loaded_at or _now()

    skills = binding.setdefault("instructions", {}).setdefault("skills", [])
    key = (entry["path"], entry["sha256"])
    duplicate_key = key if key != (None, None) else (entry["name"], *key)

    def _key(existing: dict) -> tuple:
        existing_key = (existing.get("path"), existing.get("sha256"))
        return existing_key if existing_key != (None, None) \
            else (existing.get("name"), *existing_key)

    if not any(_key(existing) == duplicate_key for existing in skills):
        skills.append(entry)

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic: a whole binding or none
    return binding


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
        "instructions": _instructions(cwd),
    }


#: Fields whose value is a property of the *session*, not of the moment it was written.
#: A second SessionStart -- resume, clear, compact -- must agree on every one of these.
IMMUTABLE_FIELDS = ("runtime_session_id", "harness", "actor", "host", "environment",
                    "workspace", "entitlement")
#: Recorded, deliberately not compared. See `created_at_entry` in `build`.
#: `instructions` is an observation of the entry, not a property of the session: an
#: AGENTS.md/CLAUDE.md edit between resumes is legitimate, and a binding written before
#: the field existed has none -- comparing it would fail every resume closed.
PER_ENTRY_FIELDS = ("binding_id", "resolved_at", "created_at_entry", "instructions")


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
    parser.add_argument("--record-skill", action="store_true",
                        help="PostToolUse mode: append an observed skill digest to "
                             "an existing binding, from a payload keyed on the "
                             "Skill tool")
    args = parser.parse_args(argv)

    if args.record_skill:
        try:
            event = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError as exc:
            print(f"session_binding: unreadable PostToolUse payload: {exc}",
                  file=sys.stderr)
            return 0  # a hook must not cost the session
        if event.get("tool_name") != "Skill":
            return 0
        session_id = (event.get("session_id") or "").strip()
        skill_name = (event.get("tool_input") or {}).get("skill")
        if not session_id or not skill_name:
            return 0
        cwd = Path(event.get("cwd") or os.getcwd())
        record_skill(args.bindings_dir, session_id, skill_name, cwd=cwd)
        return 0

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
