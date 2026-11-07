#!/usr/bin/env python3
"""Checkout freshness report: `agentops checkout-freshness [--fetch] [--json] [--strict]`.

For each key repository of the estate this reports, without changing anything:

* the current branch (or ``detached``);
* local ``main`` ahead/behind its upstream (``main@{upstream}``, falling back to
  ``origin/main`` when main has none configured);
* when that remote-tracking ref was last fetched (its reflog, else ``FETCH_HEAD``
  mtime);
* tracked files with changes, untracked files, and the worktree count.

Run it at session start, before planning reads: ``--fetch`` first runs ``git fetch``
for the upstream remote, which only updates remote-tracking refs. No command it runs
touches a working tree, index or local branch. It is advisory, not a hook.

Exit status is 0 unless ``--strict`` is given, in which case it is 1 when any
available repository's main is behind its upstream or its checkout is dirty.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

DEV = Path("/projects/dev")
DEFAULT_REPOS = ("agentops", "sprintctl", "vuoro", "vuoro-cloud", "sovite", "cred-broker",
                 "appservice", "gitops-nixos")
SCHEMA = "checkout-freshness/v1"
GIT_TIMEOUT = 60
FETCH_TIMEOUT = 120


def git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0"}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          timeout=timeout, env=env, check=False)


def out(repo: Path, *args: str) -> str | None:
    try:
        result = git(repo, *args)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def iso(ts: float | int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def upstream_of_main(repo: Path) -> tuple[str | None, str]:
    """(`remote/branch`, how it was chosen)."""
    configured = out(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "main@{upstream}")
    if configured:
        return configured, "main@{upstream}"
    if out(repo, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"):
        return "origin/main", "fallback origin/main"
    return None, "no upstream"


def last_fetch(repo: Path, upstream: str) -> tuple[str | None, str]:
    """Most recent evidence of a fetch: the remote-tracking ref's reflog (moves only when
    the ref changed) or FETCH_HEAD's mtime (written by every fetch), whichever is newer."""
    candidates: list[tuple[float, str]] = []
    stamp = out(repo, "reflog", "show", "-n1", "--format=%ct", f"refs/remotes/{upstream}", "--")
    if stamp and stamp.isdigit():
        candidates.append((int(stamp), "reflog"))
    git_dir = out(repo, "rev-parse", "--absolute-git-dir")
    common = out(repo, "rev-parse", "--path-format=absolute", "--git-common-dir") or git_dir
    for directory in dict.fromkeys(filter(None, (common, git_dir))):
        fetch_head = Path(directory) / "FETCH_HEAD"
        if fetch_head.exists():
            candidates.append((fetch_head.stat().st_mtime, "FETCH_HEAD"))
    if not candidates:
        return None, "never fetched"
    when, source = max(candidates)
    return iso(when), source


def status_counts(repo: Path) -> tuple[int | None, int | None]:
    # Not via out(): stripping would eat the leading space of a " M path" entry.
    try:
        result = git(repo, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if result.returncode != 0:
        return None, None
    porcelain = result.stdout
    tracked = untracked = 0
    entries = porcelain.split("\0")
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry:
            continue
        code = entry[:2]
        if code == "??":
            untracked += 1
        elif code != "!!":
            tracked += 1
            if code[0] in "RC":
                index += 1  # rename/copy carries the source path as the next entry
    return tracked, untracked


def inspect(name: str, repo: Path, fetch: bool) -> dict:
    report: dict = {"repo": name, "path": str(repo)}
    if not repo.is_dir() or out(repo, "rev-parse", "--is-inside-work-tree") != "true":
        report["available"] = False
        report["reason"] = "not a git checkout" if repo.is_dir() else "path does not exist"
        return report
    report["available"] = True
    branch = out(repo, "symbolic-ref", "--quiet", "--short", "HEAD")
    report["branch"] = branch or "detached"
    upstream, chosen = upstream_of_main(repo)
    report["upstream"] = upstream
    report["upstream_source"] = chosen
    if fetch and upstream:
        remote = upstream.split("/", 1)[0]
        try:
            result = git(repo, "fetch", "--quiet", remote,
                         timeout=FETCH_TIMEOUT)
            report["fetch"] = "ok" if result.returncode == 0 else (
                "failed: " + (result.stderr.strip().splitlines() or ["unknown error"])[-1])
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["fetch"] = f"failed: {type(exc).__name__}"
    has_main = out(repo, "rev-parse", "--verify", "--quiet", "refs/heads/main") is not None
    if has_main and upstream:
        counts = out(repo, "rev-list", "--left-right", "--count", f"main...{upstream}")
        if counts:
            ahead, behind = (int(n) for n in counts.split())
            report["main_ahead"], report["main_behind"] = ahead, behind
        report["last_fetch"], report["last_fetch_source"] = last_fetch(repo, upstream)
    else:
        report["main_ahead"] = report["main_behind"] = None
        report["last_fetch"], report["last_fetch_source"] = None, (
            "no local main" if not has_main else "no upstream")
    report["dirty_tracked"], report["untracked"] = status_counts(repo)
    worktrees = out(repo, "worktree", "list", "--porcelain")
    report["worktrees"] = (sum(1 for line in worktrees.splitlines() if line.startswith("worktree "))
                           if worktrees is not None else None)
    return report


def stale(report: dict) -> bool:
    if not report.get("available"):
        return False
    return bool(report.get("main_behind")) or bool(report.get("dirty_tracked"))


def render_markdown(reports: list[dict]) -> str:
    lines = ["# Checkout freshness", "",
             "| Repo | Branch | main vs upstream | Last fetch | Dirty | Untracked | Worktrees |",
             "|---|---|---|---|---|---|---|"]
    notes = []
    for r in reports:
        if not r.get("available"):
            lines.append(f"| {r['repo']} | not available ({r['reason']}) | - | - | - | - | - |")
            continue
        if r.get("main_ahead") is None:
            position = r["last_fetch_source"]
        else:
            position = f"+{r['main_ahead']}/-{r['main_behind']} {r['upstream']}"
            if r["upstream_source"] != "main@{upstream}":
                position += " (fallback)"
        fetched = r.get("last_fetch") or r.get("last_fetch_source") or "-"
        lines.append(f"| {r['repo']} | {r['branch']} | {position} | {fetched} | "
                     f"{r['dirty_tracked']} | {r['untracked']} | {r['worktrees']} |")
        if r.get("fetch", "ok") != "ok":
            notes.append(f"- {r['repo']}: fetch {r['fetch']}")
    behind = [r["repo"] for r in reports if r.get("main_behind")]
    dirty = [r["repo"] for r in reports if r.get("dirty_tracked")]
    lines += ["", f"Behind upstream: {', '.join(behind) or 'none'}. "
                  f"Dirty tracked: {', '.join(dirty) or 'none'}."]
    if notes:
        lines += ["", *notes]
    return "\n".join(lines) + "\n"


def resolve_repos(values: list[str] | None, base: Path) -> list[tuple[str, Path]]:
    repos = []
    for value in values or DEFAULT_REPOS:
        name, sep, path = value.partition("=")
        if sep:
            repos.append((name, Path(path).expanduser()))
        else:
            candidate = Path(value).expanduser()
            repos.append((candidate.name, candidate) if candidate.is_absolute()
                         else (value, base / value))
    return repos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentops checkout-freshness",
        description="Read-only report of local checkout freshness: branch, main ahead/behind "
                    "its upstream, last fetch, dirty/untracked counts and worktrees.")
    parser.add_argument("repos", nargs="*", metavar="REPO",
                        help="repo name under --base, an absolute path, or NAME=PATH "
                             f"(default: {', '.join(DEFAULT_REPOS)})")
    parser.add_argument("--base", type=Path, default=DEV,
                        help=f"directory holding the repos (default: {DEV})")
    parser.add_argument("--fetch", action="store_true",
                        help="git fetch each repo's upstream remote first "
                             "(updates remote-tracking refs only)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if any repo's main is behind upstream or its checkout is dirty")
    args = parser.parse_args(argv)

    reports = [inspect(name, path, args.fetch) for name, path in resolve_repos(args.repos, args.base)]
    if args.json:
        json.dump({"schema": SCHEMA, "repos": reports}, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(reports))
    return 1 if args.strict and any(stale(r) for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
