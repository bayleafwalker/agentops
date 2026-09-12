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

`diff_sha256` is sha256 over the bytes of `git diff HEAD` followed immediately by
the bytes of `git status --porcelain`, both run in the repo path, no separator.
It covers uncommitted work *and* untracked/staged bookkeeping, so a successor
that recomputes it is asserting "the working tree is byte-identical to the one
described here", not merely "HEAD matches".

No third-party dependencies (PyYAML is used only if a draft is YAML and only if
it happens to be importable; JSON drafts never need it). Schema validation reuses
the repository's own hand-rolled subset checker, `schema_check.py`, rather than
introducing jsonschema.

Subcommands
    create    gather repo state, embed the sprintctl bundle by reference, write
              docs/dispatch/handoffs/<date>-<slug>.v<N>.json plus a rendered .md
    validate  schema, repo paths exist, head resolves, diff_sha256 matches *now*,
              next_action non-empty. Nonzero exit and a plain message on a stale
              diff -- that refusal is the point of the field
    prompt    render the successor's first prompt on stdout
    ack       set successor.session_id atomically; refuse if already set, naming
              the live successor. The single-active-successor guard
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parents[2]
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


def diff_sha256(repo: Path) -> str:
    """sha256 over `git diff HEAD` bytes then `git status --porcelain` bytes."""
    digest = hashlib.sha256()
    digest.update(_git(repo, "diff", "HEAD").encode())
    digest.update(_git(repo, "status", "--porcelain").encode())
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


def repo_state(path: Path) -> dict[str, Any]:
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
        "diff_sha256": diff_sha256(repo),
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

    Claude Code exposes `CLAUDE_PROJECT_DIR` to hooks and skills but *not* a
    session-id variable (checked against the hooks reference, 2026-09-12), so
    `$CLAUDE_SESSION_ID` is honoured when something in the environment sets it
    and the session-binding record written by the SessionStart hook is the
    fallback: it is keyed by exactly the id the harness reports.
    """
    if explicit:
        return explicit
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
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "handoff_id": f"{date}-{slug}.v{version}",
        "version": version,
        "created_at": _now_iso(),
        "predecessor": predecessor,
        "objective": objective,
        "constraints": constraints,
        "decisions": decisions,
        "rejected": rejected,
        "state": {"repos": repos, "running": running},
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
        "It recomputes diff_sha256 (sha256 of `git diff HEAD` then",
        "`git status --porcelain`) for each repo below and refuses if the tree",
        "has moved. If it refuses, STOP and report; do not adapt to the drift.",
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


def validate_handoff(handoff: dict[str, Any], *, check_tree: bool = True) -> list[str]:
    """Return refusal messages, empty when the handoff is usable right now."""
    problems = [f"schema: {e}" for e in schema_errors(handoff)]
    if problems:
        return problems
    if not handoff["next_action"].strip():
        problems.append("next_action is empty")
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
        now = diff_sha256(path)
        if now != repo["diff_sha256"]:
            problems.append(
                f"{path}: stale diff_sha256 — recorded {repo['diff_sha256'][:16]}, "
                f"working tree is now {now[:16]}. The tree is not the one the "
                f"predecessor left; refusing.")
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


def ack(path: Path, session_id: str) -> dict[str, Any]:
    handoff = read_handoff(path)
    live = handoff.get("successor", {}).get("session_id")
    if live:
        raise HandoffError(
            f"handoff {handoff.get('handoff_id', path.name)} already has a live "
            f"successor: {live} (acknowledged {handoff['successor'].get('acknowledged_at')}). "
            f"Refusing: exactly one successor may be active. Consult or stop that "
            f"session, or create a new handoff.")
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
    repos = [repo_state(Path(p)) for p in repo_paths]

    slug = args.slug or draft.get("slug")
    if not slug:
        raise HandoffError("--slug is required (or a draft `slug` key)")
    if not SLUG_RE.match(slug):
        raise HandoffError(
            f"slug {slug!r} must be lowercase alphanumeric with hyphens")

    out_dir = Path(args.out_dir) if args.out_dir else HANDOFF_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    version = next_version(out_dir, date, slug)
    stem = f"{date}-{slug}.v{version}"

    bundle_ref = None
    if not args.no_sprintctl:
        bundle_ref = sprintctl_bundle(
            Path(repos[0]["path"]), out_dir / f"{stem}.sprintctl-bundle.json")

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
    )

    problems = schema_errors(handoff)
    if problems:
        raise HandoffError(
            "refusing to write a handoff that does not satisfy the schema:\n  "
            + "\n  ".join(problems))

    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    write_atomic(json_path, json.dumps(handoff, indent=2) + "\n")
    write_atomic(md_path, render_markdown(handoff))
    print(json_path)
    print(md_path)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    handoff = read_handoff(args.file)
    problems = validate_handoff(handoff, check_tree=not args.no_tree_check)
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
    handoff = ack(Path(args.file), args.session_id)
    print(f"acknowledged {handoff['handoff_id']} as successor "
          f"{handoff['successor']['session_id']}")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    handoff = read_handoff(args.file)
    path = Path(args.file).with_suffix(".md")
    write_atomic(path, render_markdown(handoff))
    print(path)
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

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except HandoffError as exc:
        print(f"handoff: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
