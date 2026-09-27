#!/usr/bin/env python3
"""Commit and push auditctl audit shards in every checkout under a root.

TS-6 (docs/plans/2026-09-17-target-state.md) makes committed shards the
authoritative evidence until the S4 import. Shards used to be committed by a
Stop hook ("chore(audit): append today's shard"), which never fires in headless
runs; from 2026-08-30 they were committed by hand, and days went uncommitted.
This routine replaces both. It runs unattended from a systemd user timer
(gitops-nixos, ``audit-shards-commit.timer``).

The commit has to happen *inside the checkout the hooks write into*. A shard
committed from another clone or worktree and pushed leaves the original checkout
holding the same path untracked, and its next ``git pull --ff-only`` aborts with
"untracked working tree files would be overwritten" -- even when the content is
identical. So this walks the real checkouts and commits there, touching nothing
but shard paths.

Per checkout (a direct child of ``--root`` with pending shard changes, or with
local shard-only commits that have not been pushed):

1. take a non-blocking per-repo ``flock``; skip if another run holds it;
2. skip if a merge, rebase, cherry-pick, revert or bisect is in progress;
3. skip (and report) unless the checkout is on the default branch and tracks
   ``origin/<default>``: shards are never committed onto a feature branch;
4. ``git fetch``; skip (and report) if the local branch carries unpushed
   commits that touch anything other than shard files -- somebody's work in
   progress is never pushed by a timer;
5. fast-forward if behind (``merge --ff-only``); skip (and report) if it cannot;
6. refuse any shard whose committed content is not a prefix of the working
   copy (a rewrite, which CI's ``check_append_only_shards.py`` would reject
   anyway) and any shard not ending in a newline (a write in flight);
7. ``git add`` + ``git commit --only -- <shard paths>``, so other staged and
   unstaged changes stay exactly as they were;
8. ``git push`` (never ``--force``). On a non-fast-forward rejection it undoes
   its own unpushed commit with ``reset --soft`` (index and working tree are
   left alone), fetches, fast-forwards and commits again, up to ``--retries``.

It never force-pushes, never deletes a file, never changes shard content, and
does nothing at all when nothing is pending.

Output: one JSON object per repo on stdout (the journal) and a summary at
``$XDG_STATE_HOME/agentops/audit-shards/last-run.json``. Exit 0 when every
checkout is committed, clean or only transiently skipped (lock held, merge in
progress); exit 1 when any checkout was left with shards it could not commit
(``attention``), so the failed unit surfaces through the host's failed-unit
notification; exit 2 on a usage error. There is no operator-action inbox yet
(docs/plans/2026-09-27-telemetry-audit-and-operator-actions.md, B2); the
summary file and the failed unit stand in for it.

Usage::

    commit_audit_shards.py                     # every checkout under /projects/dev
    commit_audit_shards.py --root /projects/dev --only agentops --dry-run
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

#: Same definition as scripts/check_append_only_shards.py.
SHARD_GLOB = "*_artifacts/*/audit/*.ndjson"
#: git pathspec for the same set (``**/`` also matches at the repository root).
SHARD_PATHSPEC = ":(glob)**/_artifacts/*/audit/*.ndjson"
MESSAGE = "chore(audit): append audit shards through {date}"
LOCK_NAME = "agentops-commit-audit-shards.lock"
IN_PROGRESS = (
    "MERGE_HEAD", "rebase-merge", "rebase-apply",
    "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG",
)
DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
GIT_TIMEOUT = 300

#: Skips that clear on their own; they do not fail the run.
TRANSIENT = {"locked", "operation-in-progress"}


class Skip(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class Result:
    repo: str
    action: str  # committed | pushed | noop | skipped | error | would-commit
    reason: str = ""
    commit: str = ""
    shards: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def attention(self) -> bool:
        return self.action in {"skipped", "error"} and self.reason not in TRANSIENT


def is_shard(path: str) -> bool:
    return fnmatch.fnmatch(path, SHARD_GLOB)


class Repo:
    def __init__(self, path: Path, remote: str = "origin") -> None:
        self.path = path
        self.remote = remote
        self.env = dict(os.environ)
        # Unattended: never wait on a prompt.
        self.env["GIT_TERMINAL_PROMPT"] = "0"
        self.env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["git", *args], cwd=self.path, env=self.env, capture_output=True,
            text=True, check=False, timeout=GIT_TIMEOUT,
        )
        if check and proc.returncode != 0:
            raise Skip("git-error", f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()}")
        return proc

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def git_dir(self) -> Path:
        return Path(self.path, self.out("rev-parse", "--git-dir")).resolve()

    def pending_shards(self) -> tuple[list[str], list[str]]:
        """Return (changed-or-untracked shard paths, deleted shard paths)."""
        proc = self.run("status", "--porcelain=v1", "-z", "--untracked-files=all",
                        "--", SHARD_PATHSPEC)
        changed, deleted = [], []
        entries = iter(proc.stdout.split("\0"))
        for entry in entries:
            if len(entry) < 4:
                continue
            code, path = entry[:2], entry[3:]
            if code[0] in "RC":
                next(entries, None)  # -z puts the rename source in its own field
            if not is_shard(path):
                continue
            (deleted if "D" in code else changed).append(path)
        return sorted(changed), sorted(deleted)

    def commits(self, rev_range: str) -> list[str]:
        out = self.out("rev-list", rev_range)
        return out.split() if out else []

    def shard_only(self, commit: str) -> bool:
        out = self.out("diff-tree", "--no-commit-id", "--name-status", "-r", "--root", commit)
        rows = [line.split("\t") for line in out.splitlines() if line]
        return bool(rows) and all(
            status[0] in "AM" and len(rest) == 1 and is_shard(rest[0])
            for status, *rest in rows
        )


def default_branch(repo: Repo) -> str:
    proc = repo.run("symbolic-ref", "--quiet", "--short",
                    f"refs/remotes/{repo.remote}/HEAD", check=False)
    name = proc.stdout.strip()
    if proc.returncode == 0 and name.startswith(repo.remote + "/"):
        return name[len(repo.remote) + 1:]
    return "main"


def _blob(repo: Repo, rev: str, path: str) -> bytes | None:
    proc = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=repo.path, env=repo.env,
                          capture_output=True, check=False, timeout=GIT_TIMEOUT)
    return proc.stdout if proc.returncode == 0 else None


def check_append_only(repo: Repo, upstream: str, paths: list[str]) -> tuple[list[str], list[str]]:
    """Return (paths safe to commit, paths waiting on a partial line).

    Every comparison is against ``upstream``, not HEAD, so a local shard-only
    commit that rewrote a shard is caught before it is pushed, not by CI after.
    """
    for path in _shard_paths_in(repo, f"{upstream}..HEAD"):
        base, head = _blob(repo, upstream, path), _blob(repo, "HEAD", path)
        if base is not None and (head is None or not head.startswith(base)):
            raise Skip("shard-rewritten", f"{path}: an unpushed commit rewrites it")
    ready, partial = [], []
    for path in paths:
        data = (repo.path / path).read_bytes()
        if data and not data.endswith(b"\n"):
            partial.append(path)  # an append in flight; the next run takes it
            continue
        base = _blob(repo, upstream, path)
        if base is not None and not data.startswith(base):
            raise Skip("shard-rewritten",
                       f"{path}: committed content is not a prefix of the working copy")
        ready.append(path)
    return ready, partial


def _shard_paths_in(repo: Repo, rev_range: str) -> list[str]:
    out = repo.out("diff", "--name-only", rev_range)
    return [p for p in out.splitlines() if p and is_shard(p)]


def through_date(paths: list[str]) -> str:
    dates = [m.group(1) for p in paths if (m := DATE_RE.search(Path(p).name))]
    return max(dates) if dates else dt.datetime.now(dt.timezone.utc).date().isoformat()


def sync(repo: Repo, upstream: str) -> None:
    """Fetch, refuse unpushed work, and fast-forward to ``upstream``.

    Local shard-only commits that are not on the remote (a previous push that
    lost a race, or a hand commit) are undone with ``reset --soft``: the index
    and working tree keep their content, and the shards are committed again on
    top of the remote tip.
    """
    repo.run("fetch", "--quiet", repo.remote)
    ahead = repo.commits(f"{upstream}..HEAD")
    foreign = [c for c in ahead if not repo.shard_only(c)]
    if foreign:
        raise Skip("unpushed-work",
                   f"{len(foreign)} unpushed commit(s) touch non-shard files, e.g. {foreign[0][:12]}")
    orig = None
    if ahead and repo.commits(f"HEAD..{upstream}"):
        orig = repo.out("rev-parse", "HEAD")
        base = repo.out("merge-base", "HEAD", upstream)
        repo.run("reset", "--quiet", "--soft", base)
    if repo.commits(f"HEAD..{upstream}"):
        proc = repo.run("merge", "--ff-only", "--quiet", upstream, check=False)
        if proc.returncode != 0:
            if orig:
                # A skip leaves the checkout as it found it: put the local
                # shard commit(s) back.
                repo.run("reset", "--quiet", "--soft", orig)
            raise Skip("cannot-fast-forward", (proc.stderr or proc.stdout).strip())


def process(path: Path, *, remote: str, retries: int, dry_run: bool) -> Result | None:
    repo = Repo(path, remote)
    name = path.name
    if repo.run("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
        return None
    changed, deleted = repo.pending_shards()
    branch = repo.run("symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip()
    default = default_branch(repo)
    upstream = f"{remote}/{default}"
    unpushed = False
    if branch == default and repo.run("rev-parse", "--verify", "--quiet", upstream,
                                      check=False).returncode == 0:
        # Any unpushed commit carrying shards makes the repo a candidate; sync()
        # then refuses (and reports) it if other work rides along.
        unpushed = bool(_shard_paths_in(repo, f"{upstream}..HEAD"))
    if not changed and not unpushed:
        return None  # nothing pending: not even listed

    result = Result(repo=name, action="skipped", shards=changed)
    # A dry run writes nothing, not even the lock file.
    lock_path = os.devnull if dry_run else repo.git_dir() / LOCK_NAME
    with open(lock_path, "w") as lock:
        try:
            if not dry_run:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            result.reason = "locked"
            return result
        try:
            gd = repo.git_dir()
            busy = [m for m in IN_PROGRESS if (gd / m).exists()]
            if busy:
                raise Skip("operation-in-progress", ", ".join(busy))
            if branch != default:
                raise Skip("not-default-branch",
                           f"on {branch or 'detached HEAD'}, default is {default}")
            tracking = repo.run("rev-parse", "--abbrev-ref", "--symbolic-full-name",
                                "@{upstream}", check=False).stdout.strip()
            if tracking != upstream:
                raise Skip("no-upstream", f"{default} tracks {tracking or 'nothing'}, expected {upstream}")
            if dry_run:
                result.action, result.reason = "would-commit", ""
                if deleted:
                    result.detail = f"deleted shards left alone: {', '.join(deleted)}"
                return result
            commit_and_push(repo, result, upstream=upstream, default=default, retries=retries)
            if deleted:
                result.detail = (result.detail + "; " if result.detail else "") + \
                    f"deleted shards left alone: {', '.join(deleted)}"
        except Skip as skip:
            result.action = "error" if skip.reason == "git-error" else "skipped"
            result.reason, result.detail = skip.reason, skip.detail
        except subprocess.TimeoutExpired as exc:
            result.action, result.reason, result.detail = "error", "timeout", str(exc)
        return result


def commit_and_push(repo: Repo, result: Result, *, upstream: str, default: str,
                    retries: int) -> None:
    for attempt in range(retries + 1):
        sync(repo, upstream)
        changed, _ = repo.pending_shards()
        ready, partial = check_append_only(repo, upstream, changed)
        result.shards = ready
        if partial:
            result.detail = f"waiting on a partial last line: {', '.join(partial)}"
        if ready:
            repo.run("add", "--", *ready)
            repo.run("commit", "--quiet", "-m", MESSAGE.format(date=through_date(ready)),
                     "--only", "--", *ready)
        if not repo.commits(f"{upstream}..HEAD"):
            result.action, result.reason = "noop", ""
            return
        head = repo.out("rev-parse", "HEAD")
        push = repo.run("push", "--quiet", repo.remote, f"HEAD:refs/heads/{default}", check=False)
        if push.returncode == 0:
            result.action, result.commit = "pushed", head
            if attempt:
                result.detail = f"after {attempt} retry(ies)"
            return
        err = (push.stderr or push.stdout).strip()
        # Only a lost race is retried; "[remote rejected]" (a hook or branch
        # protection) is not a race and is reported at once.
        rejected = "non-fast-forward" in err or "fetch first" in err or "[rejected]" in err
        if not rejected or attempt == retries:
            result.commit = head
            raise Skip("push-failed", err)
        # Lost a race: the next pass fetches, undoes the local shard commit
        # (reset --soft), fast-forwards and commits again.


def discover(root: Path, only: list[str]) -> list[Path]:
    dirs = sorted(p for p in root.iterdir() if p.is_dir() and (p / ".git").exists())
    if only:
        dirs = [p for p in dirs if p.name in only]
    return dirs


def state_file() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "agentops" / "audit-shards" / "last-run.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Commit and push auditctl audit shards in each checkout under a root.")
    parser.add_argument("--root", default=os.environ.get("AUDIT_SHARDS_ROOT", "/projects/dev"),
                        help="directory whose child git checkouts are scanned (default /projects/dev)")
    parser.add_argument("--only", action="append", default=[], metavar="NAME",
                        help="limit to this checkout name (repeatable)")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--retries", type=int, default=3,
                        help="push retries after a non-fast-forward rejection (default 3)")
    parser.add_argument("--summary", type=Path, default=None,
                        help="summary JSON path (default $XDG_STATE_HOME/agentops/audit-shards/last-run.json)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be committed; no fetch, commit or push")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"commit-audit-shards: root {root} is not a directory", file=sys.stderr)
        return 2

    results: list[Result] = []
    for path in discover(root, args.only):
        try:
            res = process(path, remote=args.remote, retries=args.retries, dry_run=args.dry_run)
        except Skip as skip:
            res = Result(repo=path.name, action="error", reason=skip.reason, detail=skip.detail)
        except OSError as exc:
            res = Result(repo=path.name, action="error", reason="os-error", detail=str(exc))
        except subprocess.TimeoutExpired as exc:
            res = Result(repo=path.name, action="error", reason="timeout", detail=str(exc))
        if res is not None:
            results.append(res)
            print(json.dumps(asdict(res), sort_keys=True), flush=True)

    attention = [r for r in results if r.attention]
    summary = {
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "dry_run": args.dry_run,
        "attention": [r.repo for r in attention],
        "results": [asdict(r) for r in results],
    }
    target = args.summary or state_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        tmp.replace(target)
    except OSError as exc:
        print(f"commit-audit-shards: cannot write summary {target}: {exc}", file=sys.stderr)
    for r in attention:
        print(f"commit-audit-shards: ATTENTION {r.repo}: {r.reason}: {r.detail}", file=sys.stderr)
    if not results:
        print("commit-audit-shards: nothing to do", file=sys.stderr)
    return 1 if attention else 0


if __name__ == "__main__":
    sys.exit(main())
