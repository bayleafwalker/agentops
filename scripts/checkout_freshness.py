#!/usr/bin/env python3
"""Checkout freshness report: `agentops checkout-freshness [--fetch] [--json] [--strict]`.

For each key repository of the estate this reports, without changing anything:

* the current branch (or ``detached``);
* local ``main`` ahead/behind its upstream (``main@{upstream}``, falling back to
  ``origin/main`` when main has none configured);
* when that remote-tracking ref was last fetched (the newer of its newest reflog
  entry and the ``FETCH_HEAD`` mtime);
* tracked paths with changes, untracked entries (``--untracked-files=normal``: a wholly
  untracked directory counts once), and the worktree count.

A git query that times out is reported as ``timeout``; any other missing value as ``unknown``.

Run it at session start, before planning reads: ``--fetch`` first runs ``git fetch``
for the upstream remote (``--no-auto-gc --recurse-submodules=no``, ssh in BatchMode),
which only updates remote-tracking refs and ``FETCH_HEAD``. No command it runs
touches a working tree, index or local branch. It is advisory, not a hook.

Exit status is 0 unless ``--strict`` is given, in which case it is 1 when any
available repository's main is behind its upstream or its checkout is dirty.
"""

from __future__ import annotations

import argparse
import json
import os
import re
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


def git(repo: Path, *args: str, timeout: int = GIT_TIMEOUT,
        extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_OPTIONAL_LOCKS": "0",
           **(extra_env or {})}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          timeout=timeout, env=env, check=False)


class GitTimeout(Exception):
    """A read-only git query exceeded GIT_TIMEOUT; rendered as "timeout"."""


def out(repo: Path, *args: str) -> str | None:
    """Stripped stdout, or None when git fails. Raises GitTimeout on a timeout."""
    try:
        result = git(repo, *args)
    except subprocess.TimeoutExpired as exc:
        raise GitTimeout(" ".join(args)) from exc
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def iso(ts: float | int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def upstream_of_main(repo: Path) -> dict:
    """Upstream of local main: `main@{upstream}` (its full ref, display name and remote
    from `branch.main.remote`, which may be "." or contain a slash), else origin/main."""
    full = out(repo, "rev-parse", "--symbolic-full-name", "main@{upstream}")
    if full:
        return {"ref": full,
                "name": out(repo, "rev-parse", "--abbrev-ref", "main@{upstream}") or full,
                "remote": out(repo, "config", "--get", "branch.main.remote"),
                "source": "main@{upstream}"}
    if out(repo, "rev-parse", "--verify", "--quiet", "refs/remotes/origin/main"):
        return {"ref": "refs/remotes/origin/main", "name": "origin/main", "remote": "origin",
                "source": "fallback origin/main"}
    return {"ref": None, "name": None, "remote": None, "source": "no upstream"}


def reflog_time(repo: Path, ref: str) -> int | None:
    """Time of the ref's newest reflog entry (when the ref was last updated), not the
    commit time: `--date=unix --format=%gd` prints `<ref>@{<unix seconds>}`."""
    line = out(repo, "reflog", "show", "-n1", "--date=unix", "--format=%gd", ref, "--")
    match = re.search(r"@\{(\d+)\}$", line or "")
    return int(match.group(1)) if match else None


def last_fetch(repo: Path, ref: str) -> tuple[str | None, str]:
    """Most recent evidence of a fetch, whichever is newer: the newest reflog entry of
    the remote-tracking ref (written only when a fetch moved it) or the mtime of
    FETCH_HEAD (rewritten by every fetch of any remote)."""
    candidates: list[tuple[float, str]] = []
    stamp = reflog_time(repo, ref)
    if stamp is not None:
        candidates.append((stamp, "reflog"))
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
    """(changed tracked paths, untracked entries). Untracked uses git's `normal` mode: a
    wholly untracked directory counts once, as `git status` shows it."""
    # Not via out(): stripping would eat the leading space of a " M path" entry.
    try:
        result = git(repo, "status", "--porcelain=v1", "--untracked-files=normal", "-z")
    except subprocess.TimeoutExpired as exc:
        raise GitTimeout("status") from exc
    except OSError:
        return None, None
    if result.returncode != 0:
        return None, None
    tracked = untracked = 0
    entries = result.stdout.split("\0")
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


def run_fetch(repo: Path, remote: str | None) -> str:
    if not remote:
        return "skipped: no remote"
    if remote == ".":
        return "skipped: upstream is a local branch"
    env = {} if os.environ.get("GIT_SSH_COMMAND") else {"GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}
    try:
        result = git(repo, "fetch", "--quiet", "--no-auto-gc", "--recurse-submodules=no", remote,
                     timeout=FETCH_TIMEOUT, extra_env=env)
    except subprocess.TimeoutExpired:
        return "failed: timeout"
    except OSError as exc:
        return f"failed: {type(exc).__name__}"
    if result.returncode == 0:
        return "ok"
    return "failed: " + (result.stderr.strip().splitlines() or ["unknown error"])[-1]


def inspect(name: str, repo: Path, fetch: bool) -> dict:
    report: dict = {"repo": name, "path": str(repo)}
    try:
        inside = repo.is_dir() and out(repo, "rev-parse", "--is-inside-work-tree") == "true"
    except GitTimeout:
        report.update(available=False, reason="timeout/unknown")
        return report
    if not inside:
        report["available"] = False
        report["reason"] = "not a git checkout" if repo.is_dir() else "path does not exist"
        return report
    report["available"] = True
    report.update(branch=None, upstream=None, upstream_source=None, main_ahead=None,
                  main_behind=None, last_fetch=None, last_fetch_source=None,
                  dirty_tracked=None, untracked=None, worktrees=None)
    timeouts: list[str] = []

    def step(fn) -> None:
        try:
            fn()
        except GitTimeout as exc:
            timeouts.append(str(exc))

    def branch() -> None:
        report["branch"] = out(repo, "symbolic-ref", "--quiet", "--short", "HEAD") or "detached"

    upstream: dict = {"ref": None, "remote": None}

    def find_upstream() -> None:
        upstream.update(upstream_of_main(repo))
        report["upstream"], report["upstream_source"] = upstream["name"], upstream["source"]

    def position() -> None:
        has_main = out(repo, "rev-parse", "--verify", "--quiet", "refs/heads/main") is not None
        if not (has_main and upstream["ref"]):
            report["last_fetch_source"] = "no local main" if not has_main else "no upstream"
            return
        counts = out(repo, "rev-list", "--left-right", "--count", f"refs/heads/main...{upstream['ref']}")
        if counts:
            report["main_ahead"], report["main_behind"] = (int(n) for n in counts.split())
        report["last_fetch"], report["last_fetch_source"] = last_fetch(repo, upstream["ref"])

    def counts() -> None:
        report["dirty_tracked"], report["untracked"] = status_counts(repo)

    def worktrees() -> None:
        listing = out(repo, "worktree", "list", "--porcelain")
        if listing is not None:
            report["worktrees"] = sum(1 for line in listing.splitlines()
                                      if line.startswith("worktree "))

    step(branch)
    step(find_upstream)
    if fetch and upstream["ref"]:
        report["fetch"] = run_fetch(repo, upstream["remote"])
    step(position)
    step(counts)
    step(worktrees)
    if timeouts:
        report["timeouts"] = timeouts
    return report


def stale(report: dict) -> bool:
    if not report.get("available"):
        return False
    return bool(report.get("main_behind")) or bool(report.get("dirty_tracked"))


def cell(value, timed_out: bool = False) -> str:
    """None is 'timeout' only when a git step for this repo actually timed out."""
    if value is None:
        return "timeout" if timed_out else "unknown"
    return str(value)


def render_markdown(reports: list[dict]) -> str:
    lines = ["# Checkout freshness", "",
             "| Repo | Branch | main vs upstream | Last fetch | Dirty tracked "
             "| Untracked (files; untracked dirs count once) | Worktrees |",
             "|---|---|---|---|---|---|---|"]
    notes = []
    for r in reports:
        if not r.get("available"):
            lines.append(f"| {r['repo']} | not available ({r['reason']}) | - | - | - | - | - |")
            continue
        if r.get("main_ahead") is None:
            position = r.get("last_fetch_source") or ("timeout" if r.get("timeouts") else "unknown")
        else:
            position = f"+{r['main_ahead']}/-{r['main_behind']} {r['upstream']}"
            if r["upstream_source"] != "main@{upstream}":
                position += " (fallback)"
        fetched = r.get("last_fetch") or r.get("last_fetch_source") or ("timeout" if r.get("timeouts") else "unknown")
        t = bool(r.get("timeouts"))
        lines.append(f"| {r['repo']} | {cell(r['branch'], t)} | {position} | {fetched} | "
                     f"{cell(r['dirty_tracked'], t)} | {cell(r['untracked'], t)} | {cell(r['worktrees'], t)} |")
        if r.get("fetch", "ok") != "ok":
            notes.append(f"- {r['repo']}: fetch {r['fetch']}")
        if r.get("timeouts"):
            notes.append(f"- {r['repo']}: git timed out on {', '.join(r['timeouts'])}")
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
