#!/usr/bin/env python3
"""Structured session handoff: create, validate, prompt, ack (handoff/v1).

Phase 3 of outctl's context-economy plan. The prose convention
(`docs/dispatch/handover-*.md`, and the session-handover skill) stays; this adds
the machine half the prose cannot do: a successor that can *prove* the tree is
the one the predecessor left, and a guard that permits exactly one live
successor.

Canonical form is JSON. The rendered `.md` beside it is for humans and is never
read back -- the ack guard, the validator and the SessionStart injection all read
the JSON. That is the owner decision recorded in the plan; a prose file cannot be
rename-acked without a parser nobody wants to own.

`diff_sha256` has three definitions, distinguished by `state.digest_version`:

    v1 (default when the field is absent): sha256 over the bytes of
       `git diff HEAD` followed immediately by the bytes of
       `git status --porcelain`, both run in the repo path, no separator.
    v2: v1's two inputs, then, for each untracked non-ignored file
       (`git ls-files --others --exclude-standard`, sorted by path bytes),
       the record `NUL <path bytes> NUL <content sha256 hex>`.
    v3 (what `create` writes): v2's diff computation, unchanged -- the bump
       marks a different thing, that `state.tracker_watermark` (below) is
       only ever populated by a `create` that writes v3, so its absence
       unambiguously means "written before the live-tracker re-check
       existed" and `validate` skips that re-check rather than refusing
       every handoff written before it.

v1 is blind to *content* changes in untracked files: `git status --porcelain`
names an untracked path but never its bytes, so editing an untracked file left
the digest unmoved (phase-4 acceptance finding). v2 closes that. Old handoffs
keep validating under v1 (or v2) because the file declares which definition it
used; `validate` computes the definition the file declares, never the newest
one.

Either way a successor that recomputes the digest is asserting "the working tree
is the one described here", not merely "HEAD matches". That is a claim about
the git basis only -- it says nothing about whether the tracker items this
handoff names are still in the state it recorded. `state.tracker_watermark`
closes that gap: at `create`, each item id named in the sprintctl bundle or in
`next_action` is looked up live and its status/status_revision recorded; at
`validate`, the same items are looked up again and a handoff is refused if an
item is now done or its status_revision has moved. An absent or failing
sprintctl skips the lookup at both ends -- same meaning as `--no-tree-check`,
skip not fail -- so this build never blocks on a tracker that is not there.

No third-party dependencies (PyYAML is used only if a draft is YAML and only if
it happens to be importable; JSON drafts never need it). Schema validation reuses
the repository's own hand-rolled subset checker, `schema_check.py`, rather than
introducing jsonschema.

Subcommands
    create    gather repo state, embed the sprintctl bundle by reference, write
              docs/dispatch/handoffs/<date>-<slug>.v<N>.json plus a rendered .md
    validate  schema, repo paths exist, head resolves, diff_sha256 matches *now*,
              next_action non-empty, evidence refs of kind `artifact` exist (and
              match their recorded sha256, if any), and live tracker state for
              every watermarked item still matches what `create` recorded.
              Nonzero exit and a plain message on a stale diff, a missing or
              mismatched evidence ref, or a moved tracker item -- those
              refusals are the point of the fields
    prompt    render the successor's first prompt on stdout
    ack       set successor.session_id atomically; refuse if already set, naming
              the live successor. The single-active-successor guard

Two hosts, one guard. When the handoff is carried to another host (scp to the
successor's box -- workstation and devbox-vm share no filesystem mount), the
guard would otherwise become two files and two independent claims. So `create`
stamps `origin_host`/`origin_path`, and `ack` on any other host performs the
authoritative atomic ack on the origin's copy over ssh *first*, updating the
local copy only if that succeeded. The predecessor keeps the copy that decides.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parent
SCHEMA_PATH = REPO_ROOT / "schemas" / "handoff.schema.json"
HANDOFF_DIR = REPO_ROOT / "docs" / "dispatch" / "handoffs"
SCHEMA_VERSION = "handoff/v1"

_SPEC = importlib.util.spec_from_file_location(
    "handoff_schema_check", _HERE / "schema_check.py")
assert _SPEC and _SPEC.loader
SCHEMA_CHECK = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(SCHEMA_CHECK)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class HandoffError(Exception):
    """A refusal with a message meant for a human, not a traceback."""


# --------------------------------------------------------------------------
# repo state


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise HandoffError(
            f"git {' '.join(args)} failed in {repo}: {proc.stderr.strip()}")
    return proc.stdout


def _git_bytes(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True)
    if proc.returncode != 0:
        raise HandoffError(
            f"git {' '.join(args)} failed in {repo}: "
            f"{proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout


def _is_excluded(repo: Path, raw: bytes, exclude: frozenset[str]) -> bool:
    """Is this repo-relative path one of the handoff's own output files?"""
    return os.fsdecode(raw) in exclude


def untracked_records(repo: Path,
                      exclude: frozenset[str] = frozenset()) -> list[bytes]:
    """`NUL <path> NUL <sha256 of contents>` per untracked non-ignored file.

    Sorted by raw path bytes, so the sequence is a function of the tree and not
    of the locale or of git's output order. Contents are hashed as *bytes*: an
    untracked PNG must hash as cleanly as an untracked .md. A path git lists but
    that cannot be read (a dangling symlink, a file removed between the listing
    and the read) records the literal marker `unreadable` instead of a digest --
    that state is itself part of what the successor is asserting about.
    """
    listing = _git_bytes(repo, "ls-files", "--others", "--exclude-standard", "-z")
    records = []
    for raw in sorted(p for p in listing.split(b"\0") if p):
        if _is_excluded(repo, raw, exclude):
            continue
        target = repo / os.fsdecode(raw)
        try:
            content = hashlib.sha256(target.read_bytes()).hexdigest().encode()
        except OSError:
            content = b"unreadable"
        records.append(b"\0" + raw + b"\0" + content)
    return records


DIGEST_VERSION_DEFAULT = 1   # what a handoff without state.digest_version means
DIGEST_VERSION_CURRENT = 3   # what `create` writes


def diff_sha256(repo: Path, digest_version: int = DIGEST_VERSION_CURRENT,
                exclude: frozenset[str] = frozenset()) -> str:
    """The recorded working-tree digest, under the definition asked for.

    v1: `git diff HEAD` bytes then `git status --porcelain` bytes.
    v2: v1, then one `NUL <path> NUL <content sha256>` record per untracked
        non-ignored file, sorted by path bytes.

    `exclude` holds repo-relative paths the handoff writes about *itself* (its
    own .json, .md and sprintctl bundle). A handoff stored inside a repo it
    records would otherwise never validate: `create` computes the digest before
    writing those files, so the tree it recorded stops existing the moment it
    is written. `status --porcelain` lines naming them are dropped for the same
    reason.
    """
    if digest_version not in (1, 2, 3):
        raise HandoffError(
            f"unknown state.digest_version {digest_version!r}: this build "
            f"understands 1, 2 and 3. A newer handoff needs a newer agentops.")
    digest = hashlib.sha256()
    digest.update(_git(repo, "diff", "HEAD").encode())
    porcelain = _git(repo, "status", "--porcelain")
    if exclude:
        porcelain = "".join(
            line + "\n" for line in porcelain.splitlines()
            if line[3:].strip('"') not in exclude)
    digest.update(porcelain.encode())
    if digest_version >= 2:
        for record in untracked_records(repo, exclude):
            digest.update(record)
    return digest.hexdigest()


def _unpushed(repo: Path) -> int:
    """Commits on HEAD not on its upstream. No upstream means every commit is
    unpushed in the sense that matters to a successor, but counting the whole
    history would be noise, so an unconfigured upstream reports the count
    against no remote-tracking branch at all: 0 is wrong and a full count is
    wrong, so it falls back to commits not contained in any remote ref."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "@{upstream}..HEAD"],
        capture_output=True, text=True)
    if proc.returncode == 0:
        return int(proc.stdout.strip() or 0)
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--count", "HEAD", "--not",
         "--remotes"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        return 0
    return int(proc.stdout.strip() or 0)


def self_paths(repo: Path, outputs: list[Path]) -> frozenset[str]:
    """`outputs` that live inside `repo`, as repo-relative paths."""
    repo = Path(repo).expanduser().resolve()
    rel = set()
    for out in outputs:
        try:
            rel.add(str(Path(out).resolve().relative_to(repo)))
        except ValueError:
            continue
    return frozenset(rel)


def repo_state(path: Path,
               digest_version: int = DIGEST_VERSION_CURRENT,
               exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    repo = Path(path).expanduser().resolve()
    if not repo.is_dir():
        raise HandoffError(f"repo path does not exist: {repo}")
    head = _git(repo, "rev-parse", "HEAD").strip()
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    porcelain = _git(repo, "status", "--porcelain")
    return {
        "path": str(repo),
        "head": head,
        "branch": None if branch == "HEAD" else branch,
        "dirty": bool(porcelain.strip()),
        "diff_sha256": diff_sha256(repo, digest_version, exclude),
        "unpushed": _unpushed(repo),
    }


# --------------------------------------------------------------------------
# sprintctl bundle, by reference only


def sprintctl_bundle(repo: Path, out_path: Path) -> dict[str, Any] | None:
    """Write sprintctl's handoff bundle beside the handoff and return a ref.

    sprintctl is sprint memory; this file is session memory. Embedding the
    bundle inline would make the handoff grow without bound and would duplicate
    a record sprintctl already owns, so only a path plus digest is carried.
    An absent or failing sprintctl is not an error: the handoff is still valid
    without a sprint bundle.
    """
    proc = subprocess.run(
        ["sprintctl", "handoff", "--format", "json"],
        cwd=str(repo), capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        bundle = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    payload = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload)
    return {
        "path": str(out_path),
        "sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "generated_at": bundle.get("generated_at"),
    }


# --------------------------------------------------------------------------
# tracker watermark: live sprintctl item state, re-checked at validate

# Deliberately narrow: this finds the item ids a handoff *names*, it does not
# parse a dispatch loop's claims or build a general extractor -- two prior
# attempts at this item did that and were dropped for it. `next_action` names
# an item either as `item <id>` or `#<id>`; both forms are already in real use
# (see docs/assessments/2026-09-19-backlog-reconciliation.items.json).
_ITEM_ID_RE = re.compile(r"\bitem\s+#?(\d+)\b|#(\d+)\b", re.IGNORECASE)


def _item_ids_in_text(text: str) -> list[str]:
    ids = []
    for match in _ITEM_ID_RE.finditer(text or ""):
        ids.append(match.group(1) or match.group(2))
    return ids


def _item_ids_in_bundle(bundle: dict[str, Any] | None) -> list[str]:
    """Item ids the sprintctl bundle itself names, best effort.

    The bundle is sprintctl's own JSON, carried by this file only as a path
    plus digest (`sprintctl_bundle`, above); its shape is sprintctl's to
    change. This reads the two shapes sprintctl is known to emit -- a
    top-level `items` list and/or a single `item` object, each keyed by `id`
    -- and ignores everything else rather than guessing at a schema this file
    does not own.
    """
    ids: list[str] = []
    if not isinstance(bundle, dict):
        return ids
    for item in bundle.get("items") or []:
        if isinstance(item, dict) and item.get("id") is not None:
            ids.append(str(item["id"]))
        elif isinstance(item, (str, int)):
            ids.append(str(item))
    single = bundle.get("item")
    if isinstance(single, dict) and single.get("id") is not None:
        ids.append(str(single["id"]))
    return ids


def _referenced_item_ids(next_action: str,
                         bundle: dict[str, Any] | None) -> list[str]:
    """Every item id named in `next_action` or the sprintctl bundle, deduped."""
    seen: set[str] = set()
    out: list[str] = []
    for item_id in [*_item_ids_in_text(next_action), *_item_ids_in_bundle(bundle)]:
        if item_id not in seen:
            seen.add(item_id)
            out.append(item_id)
    return out


def sprintctl_item_show(repo: Path, item_id: str) -> dict[str, Any] | None:
    """Live `sprintctl item show` state for one item, or None.

    None means "could not ask" -- sprintctl missing, offline, erroring or
    answering with something other than JSON -- and is not itself a refusal:
    exactly `sprintctl_bundle`'s meaning for an absent or failing sprintctl.
    A module-level function so tests inject a fake by monkeypatching
    `handoff.sprintctl_item_show`, the same shape as `SSHTransport` standing
    in for `ssh` -- no test may depend on a live sprintctl.
    """
    try:
        proc = subprocess.run(
            ["sprintctl", "item", "show", "--id", str(item_id), "--json"],
            cwd=str(repo), capture_output=True, text=True)
    except OSError:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        record = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    return record if isinstance(record, dict) else None


def tracker_watermark(repo: Path, next_action: str,
                      bundle: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The live status/status_revision of every item this handoff names.

    Recorded once, at `create` time, so `validate` has something to compare
    live state against later. An item sprintctl cannot be asked about right
    now (absent or failing sprintctl) is simply left out -- not recorded as
    unknown, not a refusal -- so a handoff created without sprintctl carries
    an empty watermark rather than a partially-guessed one.
    """
    watermark = []
    for item_id in _referenced_item_ids(next_action, bundle):
        record = sprintctl_item_show(repo, item_id)
        if record is None:
            continue
        watermark.append({
            "item_id": item_id,
            "status": record.get("status"),
            "status_revision": record.get("status_revision"),
        })
    return watermark


# --------------------------------------------------------------------------
# drafts and flags


def load_draft(path: Path) -> dict[str, Any]:
    text = Path(path).read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # noqa: PLC0415  -- optional, never required
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise HandoffError(
                f"{path} is not JSON and PyYAML is not importable; write the "
                "draft as JSON") from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise HandoffError(f"{path}: draft must be a mapping at the top level")
    return data


def _pairs(values: list[str] | None, field: str) -> list[dict[str, str]]:
    """`--decision 'what::why'` -> [{'what': ..., 'why': ...}]."""
    out = []
    for raw in values or []:
        what, sep, why = raw.partition("::")
        if not sep:
            raise HandoffError(
                f"--{field} expects 'what::why', got {raw!r}")
        out.append({"what": what.strip(), "why": why.strip()})
    return out


def _evidence(values: list[str] | None) -> list[dict[str, str]]:
    out = []
    for raw in values or []:
        kind, sep, ref = raw.partition(":")
        if not sep:
            raise HandoffError(f"--evidence expects 'kind:ref', got {raw!r}")
        out.append({"kind": kind.strip(), "ref": ref.strip()})
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_session_id(explicit: str | None) -> str | None:
    """The predecessor's own session id, best effort.

    Precedence: an explicit `--session-id` (or draft `session_id`) always
    wins. Next, `$HANDOFF_SESSION_ID` — the env var a dispatcher or `claude
    -p` invocation sets to pin the predecessor's own id, so a caller that
    dispatched (and therefore knows) another session's id cannot have it
    silently overridden by whatever `$CLAUDE_SESSION_ID` or the newest
    session-binding record happen to say. An empty string is treated as
    unset. Claude Code exposes `CLAUDE_PROJECT_DIR` to hooks and skills but
    *not* a session-id variable (checked against the hooks reference,
    2026-09-12), so `$CLAUDE_SESSION_ID` is honoured next when something in
    the environment sets it, and the session-binding record written by the
    SessionStart hook is the final fallback: it is keyed by exactly the id
    the harness reports.
    """
    if explicit:
        return explicit
    env = os.environ.get("HANDOFF_SESSION_ID")
    if env:
        return env
    env = os.environ.get("CLAUDE_SESSION_ID")
    if env:
        return env
    bindings = Path(os.environ.get(
        "AGENTOPS_SESSION_BINDINGS_DIR",
        "/projects/dev/.claude/state/session-bindings"))
    if bindings.is_dir():
        records = sorted(bindings.glob("*.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if records:
            return records[0].stem
    return None


# --------------------------------------------------------------------------
# build / render


def next_version(directory: Path, date: str, slug: str) -> int:
    existing = list(directory.glob(f"{date}-{slug}.v*.json"))
    versions = []
    for path in existing:
        match = re.search(r"\.v([0-9]+)\.json$", path.name)
        if match:
            versions.append(int(match.group(1)))
    return max(versions, default=0) + 1


def build(
    *,
    slug: str,
    version: int,
    date: str,
    objective: str,
    next_action: str,
    repos: list[dict[str, Any]],
    constraints: list[str],
    decisions: list[dict[str, str]],
    rejected: list[dict[str, str]],
    unresolved: list[str],
    evidence: list[dict[str, str]],
    running: list[str],
    predecessor: dict[str, Any],
    bundle_ref: dict[str, Any] | None,
    digest_version: int = DIGEST_VERSION_CURRENT,
    tracker_watermark: list[dict[str, Any]] | None = None,
    origin_host: str | None = None,
    origin_path: str | None = None,
    origin_cwd: str | None = None,
    track: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_id": f"{date}-{slug}.v{version}",
        "version": version,
        "created_at": _now_iso(),
        "origin_host": origin_host,
        "origin_path": origin_path,
        "origin_cwd": origin_cwd,
        "track": track or slug,
        "predecessor": predecessor,
        "objective": objective,
        "constraints": constraints,
        "decisions": decisions,
        "rejected": rejected,
        "state": {
            "repos": repos,
            "running": running,
            "digest_version": digest_version,
            "tracker_watermark": tracker_watermark or [],
        },
        "unresolved": unresolved,
        "evidence": evidence,
        "sprintctl_bundle_ref": bundle_ref,
        "next_action": next_action,
        "successor": {"session_id": None, "acknowledged_at": None},
    }


def render_markdown(handoff: dict[str, Any]) -> str:
    pred = handoff["predecessor"]
    lines = [
        f"# Handoff {handoff['handoff_id']}",
        "",
        "<!-- Rendered from the canonical JSON beside this file. Do not hand-edit:",
        "     `agentops handoff validate` and `ack` read the JSON, never this. -->",
        "",
        f"**Objective.** {handoff['objective']}",
        "",
        f"**Next action.** {handoff['next_action']}",
        "",
        "## Predecessor",
        "",
        f"- harness: {pred['harness']}",
        f"- session: {pred['session_id'] or 'unknown'}",
        f"- model: {pred['model'] or 'unknown'}",
        f"- context used: {pred['context_used_pct'] if pred['context_used_pct'] is not None else 'unknown'}%",
        f"- transcript: {pred['transcript_path'] or 'unknown'}",
        (f"- origin: `{handoff['origin_host']}:{handoff.get('origin_path') or '?'}`"
         " (authoritative copy; an ack from another host goes through it)"
         if handoff.get("origin_host") else "- origin: (not recorded)"),
        "",
        "Read-only after transfer: once a successor acks, the predecessor makes no",
        "edits and takes no external actions. It stays consultable.",
        "",
        "## Constraints",
        "",
    ]
    lines += [f"- {c}" for c in handoff["constraints"]] or ["- (none recorded)"]
    lines += ["", "## Decisions", ""]
    lines += [f"- **{d['what']}** — {d['why']}" for d in handoff["decisions"]] or ["- (none recorded)"]
    lines += ["", "## Rejected", ""]
    lines += [f"- **{r['what']}** — {r['why']}" for r in handoff["rejected"]] or ["- (none recorded)"]
    lines += ["", "## Repo state", "",
              f"Digest definition: v"
              f"{handoff['state'].get('digest_version', DIGEST_VERSION_DEFAULT)}"
              " (see the handoffs README).",
              "",
              "| path | branch | head | dirty | unpushed | diff_sha256 |",
              "|---|---|---|---|---|---|"]
    for repo in handoff["state"]["repos"]:
        lines.append(
            f"| `{repo['path']}` | {repo['branch'] or '(detached)'} | "
            f"`{repo['head'][:12]}` | {'yes' if repo['dirty'] else 'no'} | "
            f"{repo['unpushed']} | `{repo['diff_sha256'][:16]}…` |")
    if handoff["state"]["running"]:
        lines += ["", "**Running:**", ""]
        lines += [f"- {item}" for item in handoff["state"]["running"]]
    lines += ["", "## Unresolved", ""]
    lines += [f"- {u}" for u in handoff["unresolved"]] or ["- (none recorded)"]
    lines += ["", "## Evidence", ""]
    lines += [f"- {e['kind']}: `{e['ref']}`" for e in handoff["evidence"]] or ["- (none recorded)"]
    ref = handoff["sprintctl_bundle_ref"]
    lines += ["", "## sprintctl bundle", "",
              (f"- `{ref['path']}` (sha256 `{ref['sha256'][:16]}…`)" if ref
               else "- none (sprintctl unavailable or produced no bundle)")]
    lines += ["", "## Successor", "",
              f"- session: {handoff['successor']['session_id'] or '(unacknowledged)'}",
              f"- acknowledged: {handoff['successor']['acknowledged_at'] or '—'}",
              ""]
    return "\n".join(lines)


def render_prompt(handoff: dict[str, Any], path: Path) -> str:
    repos = handoff["state"]["repos"]
    lines = [
        f"You are the successor session for handoff {handoff['handoff_id']}.",
        f"The canonical handoff is {path}. Load it first; it, not this prompt,",
        "is the record.",
        "",
        f"OBJECTIVE: {handoff['objective']}",
        "",
        "CONSTRAINTS — restate these back before you act, in your own words, so",
        "it is on the record that you have them:",
    ]
    lines += [f"  {i}. {c}" for i, c in enumerate(handoff["constraints"], 1)] or \
             ["  (none recorded)"]
    lines += [
        "",
        "DECISIONS ALREADY MADE (do not relitigate):",
    ]
    lines += [f"  - {d['what']} — {d['why']}" for d in handoff["decisions"]] or ["  (none)"]
    lines += ["", "ALREADY REJECTED (do not retry without new evidence):"]
    lines += [f"  - {r['what']} — {r['why']}" for r in handoff["rejected"]] or ["  (none)"]
    lines += [
        "",
        "VERIFY REPO STATE before any change. Run:",
        f"  agentops handoff validate {path}",
        "It recomputes diff_sha256 under the definition this handoff declares",
        f"(v{handoff['state'].get('digest_version', DIGEST_VERSION_DEFAULT)}: "
        "`git diff HEAD`, `git status --porcelain`, and under v2 the sha256 of",
        "each untracked file's contents) for each repo below and refuses if the",
        "tree has moved. If it refuses, STOP and report; do not adapt to the drift.",
    ]
    for repo in repos:
        lines.append(
            f"  - {repo['path']} @ {repo['head'][:12]} "
            f"({repo['branch'] or 'detached'}, "
            f"{'dirty' if repo['dirty'] else 'clean'}, "
            f"{repo['unpushed']} unpushed)")
    if handoff["state"]["running"]:
        lines += ["", "RUNNING (inherited; do not restart blindly):"]
        lines += [f"  - {item}" for item in handoff["state"]["running"]]
    if handoff["unresolved"]:
        lines += ["", "UNRESOLVED:"]
        lines += [f"  - {u}" for u in handoff["unresolved"]]
    if handoff["evidence"]:
        lines += ["", "EVIDENCE (read only what you need):"]
        lines += [f"  - {e['kind']}: {e['ref']}" for e in handoff["evidence"]]
    ref = handoff["sprintctl_bundle_ref"]
    if ref:
        lines += ["", f"SPRINT BUNDLE: {ref['path']} (sprint memory, by reference)"]
    lines += [
        "",
        "THEN EXECUTE, exactly this and nothing beyond it without saying so first:",
        f"  {handoff['next_action']}",
        "",
        "ACKNOWLEDGE FIRST. Your first action is:",
        f"  agentops handoff ack {path} --session-id <your session id>",
        "If it refuses, another successor is already live — stop and report its id.",
        "",
        "The predecessor is READ-ONLY after this transfer: it makes no edits and",
        "takes no external actions. It remains consultable for 'why did you reject",
        "X', but you own the work now. Do not assume its session is reachable —",
        "everything you need is in the handoff file.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# validation


def schema_errors(handoff: Any) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text())
    return SCHEMA_CHECK.validate(handoff, schema)


def handoff_outputs(file: Path | str | None) -> list[Path]:
    """A handoff's own files: `<stem>.json`, `.md` and its sprintctl bundle.

    Excluded from the tree digest, because they land inside a repo the handoff
    records. Without this a handoff kept in `agentops/docs/dispatch/handoffs/`
    could never validate: writing it changes the tree it just recorded.
    """
    if file is None:
        return []
    path = Path(file).expanduser().resolve()
    stem = path.name[:-len(".json")] if path.name.endswith(".json") else path.stem
    return [path.parent / f"{stem}{suffix}"
            for suffix in (".json", ".md", ".sprintctl-bundle.json")]


_EVIDENCE_REF_SHA_RE = re.compile(r"^(?P<ref>.+)#sha256=(?P<sha>[0-9a-f]{64})$")


def _evidence_problems(handoff: dict[str, Any]) -> list[str]:
    """Refuse a handoff whose `evidence[]` outranks reality.

    Only `kind: artifact` refs name a file or path -- the other three kinds
    (`session`, `auditctl`, `sprintctl`) name things this file has no business
    stat'ing. A ref may carry its recorded content hash as a `#sha256=<hex>`
    suffix; when it does, a mismatch is refused exactly like a missing file
    is, not merely warned about -- that is the defect this item names: a
    handoff citing a plan path that did not exist was discovered by an
    operator, not by validate.
    """
    problems = []
    for entry in handoff.get("evidence") or []:
        if entry.get("kind") != "artifact":
            continue
        raw_ref = entry.get("ref", "")
        match = _EVIDENCE_REF_SHA_RE.match(raw_ref)
        ref, expected_sha = (match.group("ref"), match.group("sha")) if match else (raw_ref, None)
        path = Path(ref)
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.is_file():
            problems.append(
                f"evidence: artifact {raw_ref!r} does not exist ({path}); refusing")
            continue
        if expected_sha:
            actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_sha != expected_sha:
                problems.append(
                    f"evidence: artifact {raw_ref!r} sha256 mismatch — recorded "
                    f"{expected_sha}, file is now {actual_sha}; refusing")
    return problems


def _tracker_problems(handoff: dict[str, Any]) -> list[str]:
    """Refuse a handoff whose watermarked tracker items have moved.

    `state.tracker_watermark` is absent on every handoff written before this
    check existed -- mandatory for new, flagged for old, exactly like
    `state.digest_version`'s own rollout -- so absence skips this entirely
    rather than refusing every handoff ever written. An empty watermark (no
    item ids were named) also has nothing to check: that is the "no item refs
    ... validates unchanged" case, not a special case here. sprintctl being
    absent or failing skips the item it could not ask about, same meaning as
    everywhere else sprintctl is optional in this file; not gated behind
    `--no-tree-check`, which is about the git basis only.
    """
    watermark = handoff["state"].get("tracker_watermark")
    if not watermark:
        return []
    repos = handoff["state"].get("repos") or []
    if not repos:
        return []
    repo = Path(repos[0]["path"])
    if not repo.is_dir():
        return []
    problems = []
    for recorded in watermark:
        item_id = recorded["item_id"]
        live = sprintctl_item_show(repo, item_id)
        if live is None:
            continue
        live_status = live.get("status")
        live_revision = live.get("status_revision")
        recorded_revision = recorded.get("status_revision")
        if live_status == "done":
            problems.append(
                f"tracker: item {item_id} is done (recorded status_revision "
                f"{recorded_revision!r}, current {live_revision!r}); this "
                "handoff's tracker claim is stale, refusing")
        elif live_revision != recorded_revision:
            problems.append(
                f"tracker: item {item_id} status_revision has moved (recorded "
                f"{recorded_revision!r}, current {live_revision!r}); live "
                "tracker state has changed since this handoff was created, "
                "refusing")
    return problems


def validate_handoff(handoff: dict[str, Any], *, check_tree: bool = True,
                     file: Path | str | None = None) -> list[str]:
    """Return refusal messages, empty when the handoff is usable right now."""
    self_outputs = handoff_outputs(file)
    problems = [f"schema: {e}" for e in schema_errors(handoff)]
    if problems:
        return problems
    if not handoff["next_action"].strip():
        problems.append("next_action is empty")
    # The file declares which digest definition it was written under; recompute
    # that one. Recomputing the newest definition against a v1 handoff would
    # refuse every handoff written before v2 existed, which is exactly the
    # breakage the version field exists to avoid.
    digest_version = handoff["state"].get(
        "digest_version", DIGEST_VERSION_DEFAULT)
    for repo in handoff["state"]["repos"]:
        path = Path(repo["path"])
        if not path.is_dir():
            problems.append(f"repo path does not exist: {path}")
            continue
        rev = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--verify", repo["head"] + "^{commit}"],
            capture_output=True, text=True)
        if rev.returncode != 0:
            problems.append(
                f"{path}: head {repo['head'][:12]} does not resolve in this repo")
            continue
        if not check_tree:
            continue
        try:
            now = diff_sha256(path, digest_version,
                              self_paths(path, self_outputs))
        except HandoffError as exc:
            problems.append(f"{path}: {exc}")
            continue
        if now != repo["diff_sha256"]:
            problems.append(
                f"{path}: stale diff_sha256 (v{digest_version}) — recorded "
                f"{repo['diff_sha256'][:16]}, "
                f"working tree is now {now[:16]}. The tree is not the one the "
                f"predecessor left; refusing.")
    # Live tracker precedence: the git basis matching is not enough, a handoff
    # must not be able to outrank tracker state it cites. Neither check below
    # is gated by `check_tree` -- that flag is about the diff comparison only.
    problems += _evidence_problems(handoff)
    problems += _tracker_problems(handoff)
    return problems


# --------------------------------------------------------------------------
# atomic ack


def read_handoff(path: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError as exc:
        raise HandoffError(f"no such handoff: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HandoffError(f"{path} is not valid JSON: {exc}") from exc


def write_atomic(path: Path, payload: str) -> None:
    """Write via a sibling temp file plus os.replace.

    A partially written handoff is worse than no handoff: the ack guard reads
    this file to decide whether a second successor may start, and a truncated
    read would be indistinguishable from an unacked handoff.
    """
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(payload)
    os.replace(tmp, path)


class SSHTransport:
    """`ssh <host> <argv...>`, the only transport used in production.

    Injectable so the two-host guard is testable without a second machine: the
    tests substitute a recorder that returns a chosen exit status, which is the
    only thing the guard branches on.
    """

    def __init__(self, ssh: str = "ssh", timeout: int = 60) -> None:
        self.ssh = ssh
        self.timeout = timeout

    def run(self, host: str, argv: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.ssh, host, *argv],
            capture_output=True, text=True, timeout=self.timeout)


def local_hostname() -> str:
    """This host's name, overridable so tests can pretend to be elsewhere."""
    return os.environ.get("AGENTOPS_HOSTNAME") or socket.gethostname()


def _remote_ack_argv(origin_path: str, session_id: str,
                     *, fallback: bool) -> list[str]:
    """The command run on the origin host to take the authoritative ack.

    `agentops` first because that is what the origin is documented to install;
    the `python3 <script>` form is the fallback for an origin where the wrapper
    is not on a non-interactive PATH (ssh runs a non-login shell). The script
    path is this file's own path, which holds because both hosts check out the
    same repository at the same location -- if that stops being true the origin
    needs an explicit `origin_script` and this is where it would go.
    """
    tail = ["handoff", "ack", origin_path, "--session-id", session_id]
    if fallback:
        return ["python3", str(_HERE / "handoff.py"), *tail[1:]]
    return ["agentops", *tail]


def remote_ack(origin_host: str, origin_path: str, session_id: str,
               transport: Any) -> subprocess.CompletedProcess:
    """Take the ack on the origin host. Returns the *successful* result."""
    result = transport.run(
        origin_host, _remote_ack_argv(origin_path, session_id, fallback=False))
    if result.returncode == 127:  # no `agentops` on the origin's ssh PATH
        result = transport.run(
            origin_host,
            _remote_ack_argv(origin_path, session_id, fallback=True))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise HandoffError(
            f"origin host {origin_host} refused the ack of {origin_path} "
            f"(exit {result.returncode}): {detail or 'no output'}. The origin "
            f"copy is the authoritative one; the local copy is unchanged.")
    return result


def ack(path: Path, session_id: str, *,
        transport: Any | None = None,
        hostname: str | None = None) -> dict[str, Any]:
    """Claim a handoff as its single successor.

    On the origin host this is the local atomic ack. On any other host the
    authoritative ack is taken on the origin first, over the injected transport,
    and the local copy is updated only once that succeeded -- so a handoff that
    was scp'd to two successor hosts still admits exactly one claim, because
    both of them are claiming the same file on the predecessor's machine.
    """
    handoff = read_handoff(path)
    live = handoff.get("successor", {}).get("session_id")
    if live:
        raise HandoffError(
            f"handoff {handoff.get('handoff_id', path.name)} already has a live "
            f"successor: {live} (acknowledged {handoff['successor'].get('acknowledged_at')}). "
            f"Refusing: exactly one successor may be active. Consult or stop that "
            f"session, or create a new handoff.")

    origin_host = handoff.get("origin_host")
    origin_path = handoff.get("origin_path")
    here = hostname or local_hostname()
    if origin_host and origin_path and origin_host != here:
        # Authoritative first, local second. If this raises, nothing below runs
        # and the local file is byte-identical to what it was.
        remote_ack(origin_host, origin_path, session_id,
                   transport or SSHTransport())

    handoff["successor"] = {
        "session_id": session_id,
        "acknowledged_at": _now_iso(),
    }
    write_atomic(path, json.dumps(handoff, indent=2) + "\n")
    md = path.with_suffix(".md")
    if md.exists():
        write_atomic(md, render_markdown(handoff))
    return handoff


# --------------------------------------------------------------------------
# commands


def cmd_create(args: argparse.Namespace) -> int:
    draft: dict[str, Any] = load_draft(args.draft) if args.draft else {}

    def pick(name: str, flag: Any, default: Any) -> Any:
        if flag not in (None, [], ()):
            return flag
        return draft.get(name, default)

    objective = pick("objective", args.objective, None)
    next_action = pick("next_action", args.next_action, None)
    if not objective:
        raise HandoffError("objective is required (--objective or draft key)")
    if not next_action or not str(next_action).strip():
        raise HandoffError("next_action is required and must be non-empty")

    repo_paths = [Path(p) for p in (args.repo or draft.get("repos") or [Path.cwd()])]
    slug = args.slug or draft.get("slug")
    if not slug:
        raise HandoffError("--slug is required (or a draft `slug` key)")
    if not SLUG_RE.match(slug):
        raise HandoffError(
            f"slug {slug!r} must be lowercase alphanumeric with hyphens")

    out_dir = Path(args.out_dir) if args.out_dir else (
        Path(os.environ["AGENTOPS_HANDOFF_DIR"])
        if os.environ.get("AGENTOPS_HANDOFF_DIR") else HANDOFF_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    version = next_version(out_dir, date, slug)
    stem = f"{date}-{slug}.v{version}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"

    # State is recorded with this handoff's own outputs excluded: they do not
    # exist yet here, and they land inside a recorded repo a moment later.
    outputs = [json_path, md_path, out_dir / f"{stem}.sprintctl-bundle.json"]
    repos = [
        repo_state(Path(p), DIGEST_VERSION_CURRENT,
                   self_paths(Path(p), outputs))
        for p in repo_paths
    ]

    bundle_ref = None
    bundle_json = None
    if not args.no_sprintctl:
        bundle_ref = sprintctl_bundle(
            Path(repos[0]["path"]), out_dir / f"{stem}.sprintctl-bundle.json")
        if bundle_ref:
            try:
                bundle_json = json.loads(
                    (out_dir / f"{stem}.sprintctl-bundle.json").read_text())
            except (OSError, json.JSONDecodeError):
                bundle_json = None

    watermark = tracker_watermark(
        Path(repos[0]["path"]), str(next_action).strip(), bundle_json)

    predecessor = {
        "harness": args.harness or draft.get("harness") or "claude-code",
        "session_id": resolve_session_id(args.session_id or draft.get("session_id")),
        "transcript_path": args.transcript_path or draft.get("transcript_path"),
        "model": args.model or draft.get("model"),
        "context_used_pct": (args.context_used_pct
                             if args.context_used_pct is not None
                             else draft.get("context_used_pct")),
    }

    handoff = build(
        slug=slug, version=version, date=date,
        objective=objective, next_action=str(next_action).strip(),
        repos=repos,
        constraints=list(pick("constraints", args.constraint, []) or []),
        decisions=(_pairs(args.decision, "decision")
                   or list(draft.get("decisions", []))),
        rejected=(_pairs(args.rejected, "rejected")
                  or list(draft.get("rejected", []))),
        unresolved=list(pick("unresolved", args.unresolved, []) or []),
        evidence=(_evidence(args.evidence) or list(draft.get("evidence", []))),
        running=list(pick("running", args.running, []) or []),
        predecessor=predecessor,
        bundle_ref=bundle_ref,
        digest_version=DIGEST_VERSION_CURRENT,
        tracker_watermark=watermark,
        # Stamped now, while this host still is the origin. After an scp the
        # copy on the successor's host has no other way to know where the
        # authoritative file lives.
        origin_host=(args.origin_host or draft.get("origin_host")
                     or local_hostname()),
        origin_path=str(json_path.resolve()),
        origin_cwd=(args.origin_cwd or draft.get("origin_cwd")
                    or str(Path.cwd())),
        track=(args.track or draft.get("track") or slug),
    )

    problems = schema_errors(handoff)
    if problems:
        raise HandoffError(
            "refusing to write a handoff that does not satisfy the schema:\n  "
            + "\n  ".join(problems))

    write_atomic(json_path, json.dumps(handoff, indent=2) + "\n")
    write_atomic(md_path, render_markdown(handoff))
    print(json_path)
    print(md_path)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    handoff = read_handoff(args.file)
    problems = validate_handoff(handoff, check_tree=not args.no_tree_check,
                                file=args.file)
    if problems:
        print(f"handoff {args.file}: REFUSED", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"handoff {handoff['handoff_id']}: valid, "
          f"{len(handoff['state']['repos'])} repo(s) match the recorded tree")
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    handoff = read_handoff(args.file)
    print(render_prompt(handoff, Path(args.file).resolve()))
    return 0


def cmd_ack(args: argparse.Namespace) -> int:
    path = Path(args.file)
    handoff = ack(path, args.session_id)
    origin = handoff.get("origin_host")
    where = ("" if not origin or origin == local_hostname()
             else f" (authoritative ack taken on {origin})")
    print(f"acknowledged {handoff['handoff_id']} as successor "
          f"{handoff['successor']['session_id']}{where}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    handoff = read_handoff(args.file)
    path = Path(args.file).with_suffix(".md")
    write_atomic(path, render_markdown(handoff))
    print(path)
    return 0


# --------------------------------------------------------------------------
# open: the unacked-handoffs list

HANDOFF_FILENAME_RE = re.compile(
    r"^(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})-(?P<slug>[a-z0-9][a-z0-9-]*)"
    r"\.v(?P<version>[0-9]+)\.json$")


def _slug_from_handoff_id(handoff_id: str) -> str:
    """The slug component of `<date>-<slug>.v<N>`, or the id itself if it
    does not match -- callers use this only as a fallback key, never to
    reject a file."""
    match = re.match(
        r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-(?P<slug>[a-z0-9][a-z0-9-]*)"
        r"\.v[0-9]+$", handoff_id)
    return match.group("slug") if match else handoff_id


def track_of(handoff: dict[str, Any]) -> str:
    """`track` when the file recorded one, else the slug parsed from its id.

    Files written before `track` existed carry no such field; falling back to
    the slug is what lets `open` collapse their versions too.
    """
    return handoff.get("track") or _slug_from_handoff_id(handoff["handoff_id"])


def launch_cwd(handoff: dict[str, Any]) -> str:
    """The recorded predecessor cwd, or the first repo path for old files
    that predate `origin_cwd`."""
    cwd = handoff.get("origin_cwd")
    if cwd:
        return cwd
    repos = handoff.get("state", {}).get("repos") or []
    return repos[0]["path"] if repos else "?"


def open_handoffs(directory: Path) -> list[dict[str, Any]]:
    """Unacked handoffs under `directory`, newest per track.

    "Newest" is the latest `handoff_id` date, then `created_at` (ISO 8601, so
    lexical order is chronological), then `version`. A file that is not valid
    JSON is skipped rather than aborting the whole listing -- one damaged file
    should not hide every other track's live handoff.

    Version is the LAST key, not the first. Version numbers are allocated per
    SLUG, not per track, so two different slugs in one track carry independent
    counters and comparing them is meaningless. Ordering by version first meant
    a brand-new `<track>/<new-slug>.v1` lost to a stale `<track>/<old-slug>.v4`
    from earlier the same day, and `open` advertised the superseded one --
    observed 2026-09-22, the same failure as acking-v2-not-retiring-v1 arriving
    from the other direction. Version still decides within a slug, because two
    versions of one slug share a date and are often written inside the same
    second, so `created_at` alone cannot separate them.

    The newest version of a track decides the whole track, acked or not. This
    used to skip acked files *before* grouping, which meant acking v2 did not
    retire v1: the track kept listing its superseded predecessor, and a
    successor reading `open` was sent backwards to a next-action that a later
    version had already replaced. Observed 2026-09-22 on the
    sprint559-echain-and-lane-fixes track, whose acked v2 left v1 open with a
    stale instruction to redo work that was done.
    """
    best: dict[str, tuple[tuple[int, str, str], dict[str, Any], Path]] = {}
    if not directory.is_dir():
        return []
    for path in sorted(directory.glob("*.json")):
        if not HANDOFF_FILENAME_RE.match(path.name):
            continue
        try:
            handoff = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        track = track_of(handoff)
        version = handoff.get("version", 0)
        date = handoff.get("handoff_id", "")[:10]
        created_at = handoff.get("created_at") or ""
        key = (date, created_at, version)
        current = best.get(track)
        if current is None or key > current[0]:
            best[track] = (key, handoff, path)
    rows = []
    for track, (_key, handoff, path) in best.items():
        successor = handoff.get("successor") or {}
        if successor.get("session_id"):
            continue
        rows.append({
            "track": track,
            "handoff_id": handoff["handoff_id"],
            "file": str(path),
            "date": handoff["handoff_id"][:10],
            "repos": [{"path": r["path"], "dirty": r["dirty"]}
                     for r in handoff.get("state", {}).get("repos", [])],
            "cwd": launch_cwd(handoff),
            "next_action": handoff.get("next_action", ""),
        })
    rows.sort(key=lambda r: (r["date"], r["track"]))
    return rows


def launch_line(row: dict[str, Any]) -> str:
    """`cd <cwd> && claude --bg --session-id <fresh uuid> "$(agentops handoff
    prompt <file>)"`. The uuid is minted fresh every render; nothing reads it
    back, so nothing depends on its value."""
    return (f'cd {row["cwd"]} && claude --bg --session-id {uuid.uuid4()} '
           f'"$(agentops handoff prompt {row["file"]})"')


def cmd_open(args: argparse.Namespace) -> int:
    directory = Path(args.dir) if args.dir else (
        Path(os.environ["AGENTOPS_HANDOFF_DIR"])
        if os.environ.get("AGENTOPS_HANDOFF_DIR") else HANDOFF_DIR)
    rows = open_handoffs(directory)
    if args.json:
        payload = [dict(row, launch=launch_line(row)) for row in rows]
        print(json.dumps(payload, indent=2))
        return 0
    if not rows:
        print("no unacked handoffs")
        return 0
    for row in rows:
        print(f"== {row['track']} ({row['date']}) -- {row['handoff_id']} ==")
        print(f"  cwd: {row['cwd']}")
        for repo in row["repos"]:
            print(f"  repo: {repo['path']} ({'dirty' if repo['dirty'] else 'clean'})")
        print(f"  next: {row['next_action']}")
        print(f"  launch: {launch_line(row)}")
        print()
    return 0


# --------------------------------------------------------------------------
# continue-entry: the operator-scratchpad section

def render_continue_entry(handoff: dict[str, Any], file: Path) -> str:
    """This handoff's delimited section for the operator's `~/continue`.

    Bounded by `<!-- handoff:<track> -->` / `<!-- /handoff:<track> -->` so
    `upsert_continue_section` can replace exactly this span and nothing else.
    """
    track = track_of(handoff)
    row = {
        "cwd": launch_cwd(handoff),
        "file": str(file),
    }
    lines = [
        f"<!-- handoff:{track} -->",
        f"### {handoff['handoff_id']}",
        "",
        launch_line(row),
        "",
        f"**Objective.** {handoff['objective']}",
        f"**Next action.** {handoff['next_action']}",
        "",
        "Repos:",
    ]
    repos = handoff.get("state", {}).get("repos") or []
    lines += [f"- `{repo['path']}` ({'dirty' if repo['dirty'] else 'clean'})"
             for repo in repos] or ["- (none recorded)"]
    lines += ["", f"<!-- /handoff:{track} -->"]
    return "\n".join(lines) + "\n"


def upsert_continue_section(path: Path, track: str, section: str) -> None:
    """Replace exactly `<!-- handoff:<track> -->`..`<!-- /handoff:<track> -->`
    in `path` with `section`, appending it if the marker pair is absent.
    Every other byte of `path` -- operator prose, other tracks' sections -- is
    left untouched. Written atomically; creates `path` (and its parent) if it
    does not exist yet. Re-running with the same `section` is a no-op change
    to the file's bytes.
    """
    if not section.endswith("\n"):
        section += "\n"
    text = path.read_text() if path.exists() else ""
    pattern = re.compile(
        re.escape(f"<!-- handoff:{track} -->") + r".*?"
        + re.escape(f"<!-- /handoff:{track} -->") + r"\n?",
        re.DOTALL)
    if pattern.search(text):
        new_text = pattern.sub(lambda _m: section, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        new_text = text + section
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, new_text)


def cmd_continue_entry(args: argparse.Namespace) -> int:
    handoff = read_handoff(args.file)
    section = render_continue_entry(handoff, Path(args.file).resolve())
    if args.into:
        into_path = Path(args.into).expanduser()
        upsert_continue_section(into_path, track_of(handoff), section)
        print(into_path)
    else:
        print(section, end="")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentops handoff", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Write a new handoff and its rendering")
    create.add_argument("--slug", help="short kebab-case name for the handoff")
    create.add_argument("--repo", action="append", metavar="PATH",
                        help="repeat per repository; defaults to the cwd")
    create.add_argument("--draft", type=Path,
                        help="YAML or JSON draft supplying any field")
    create.add_argument("--objective")
    create.add_argument("--next-action", dest="next_action")
    create.add_argument("--constraint", action="append", dest="constraint")
    create.add_argument("--decision", action="append", metavar="WHAT::WHY")
    create.add_argument("--rejected", action="append", metavar="WHAT::WHY")
    create.add_argument("--unresolved", action="append")
    create.add_argument("--evidence", action="append", metavar="KIND:REF")
    create.add_argument("--running", action="append")
    create.add_argument("--harness")
    create.add_argument("--session-id", dest="session_id")
    create.add_argument("--transcript-path", dest="transcript_path")
    create.add_argument("--model")
    create.add_argument("--context-used-pct", dest="context_used_pct", type=float)
    create.add_argument("--origin-host", dest="origin_host",
                        help="host that keeps the authoritative copy; defaults "
                             "to this host's name. A successor on any other "
                             "host acks through it over ssh")
    create.add_argument("--origin-cwd", dest="origin_cwd",
                        help="predecessor's working directory; defaults to "
                             "the process cwd. `handoff open` uses this as "
                             "the launch cwd")
    create.add_argument("--track",
                        help="identifies this continuation thread across "
                             "create calls, independent of slug or date; "
                             "defaults to the slug. `handoff open` collapses "
                             "to the newest version per track")
    create.add_argument("--out-dir", dest="out_dir")
    create.add_argument("--date", help="override the date component (testing)")
    create.add_argument("--no-sprintctl", action="store_true",
                        help="skip the sprintctl bundle entirely")
    create.set_defaults(func=cmd_create)

    validate = sub.add_parser("validate", help="Refuse a handoff that no longer describes reality")
    validate.add_argument("file", type=Path)
    validate.add_argument("--no-tree-check", action="store_true",
                          help="schema and paths only; skips the diff_sha256 comparison")
    validate.set_defaults(func=cmd_validate)

    prompt = sub.add_parser("prompt", help="Render the successor's first prompt")
    prompt.add_argument("file", type=Path)
    prompt.set_defaults(func=cmd_prompt)

    ack_parser = sub.add_parser("ack", help="Claim a handoff as its single successor")
    ack_parser.add_argument("file", type=Path)
    ack_parser.add_argument("--session-id", dest="session_id", required=True)
    ack_parser.set_defaults(func=cmd_ack)

    render = sub.add_parser("render", help="Regenerate the .md beside a handoff")
    render.add_argument("file", type=Path)
    render.set_defaults(func=cmd_render)

    open_parser = sub.add_parser(
        "open", help="List unacked handoffs, newest version per track")
    open_parser.add_argument("--json", action="store_true",
                             help="emit the rows as JSON, launch line included")
    open_parser.add_argument("--dir", help="override the handoffs directory (testing)")
    open_parser.set_defaults(func=cmd_open)

    continue_entry = sub.add_parser(
        "continue-entry",
        help="Render this handoff's entry for the operator's scratchpad")
    continue_entry.add_argument("file", type=Path)
    continue_entry.add_argument(
        "--into", help="upsert only this track's section into PATH; "
                       "every other byte of PATH is left untouched")
    continue_entry.set_defaults(func=cmd_continue_entry)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HandoffError as exc:
        print(f"handoff: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
