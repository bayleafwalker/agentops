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
   If a later step then fails (a rewrite, a commit hook), that shard content
   stays staged in the index rather than committed; nothing is lost and the
   next run commits it.
9. when the default branch is protected (the push is refused with a
   protected-branch message, or the checkout is named with ``--protected``),
   land the commit through a pull request instead -- see "Protected default
   branches" below.

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

Protected default branches
--------------------------

Forgejo and GitHub refuse a direct push to a protected branch. The shard commit
then stays on the local default branch (as before) and goes in by pull request:

a. if an open ``audit/shards-*`` PR's head is an ancestor of it, carry that
   PR as it is (newer commits are not pushed onto it while its checks run;
   they go in next); otherwise push it, without force, to
   ``audit/shards-<today>`` (fast-forwarding that branch if it exists, else
   with a ``-<sha>`` suffix), and close an open shard PR it replaces;
b. open the PR if none is open (Forgejo ``fj pr create``, GitHub
   ``gh pr create``; platform and owner/repo come from the remote URL);
c. verify that ``<default>...HEAD`` touches only shard files and only appends
   to them (the ``check_append_only_shards.py`` logic); otherwise stop with
   ``needs-operator``;
d. wait up to ``--ci-wait`` seconds for the checks on the PR head; if they are
   still running, leave the PR open (``pr-open``) and let the next run carry
   on; merge only when every check succeeded (or was skipped);
e. merge pinned to the exact head commit: Forgejo through ``credctl merge
   --style fast-forward-only``, GitHub through ``gh pr merge
   --match-head-commit`` with a merge style the repository allows; then
   fetch and fast-forward the local checkout (after a rebase or squash merge,
   move onto the merged commit, whose tree is the PR head's). A fast-forward
   refused because the base moved is left for the next run (``base-moved``).

A refused merge, a failed check, a push the forge refuses, or a PR diff that is
not shard appends is reported as ``needs-operator`` with the PR URL. Branch
protection is never bypassed.

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
import time
import urllib.error
import urllib.request
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
#: A shard whose last line has stayed unterminated this long (seconds) is not
#: an append in flight but a crashed writer; it needs a person.
STALE_PARTIAL_AGE = 2 * 3600
STALE_PARTIAL = "stale-partial-line"

#: Head branches of shard PRs: ``audit/shards-<YYYY-MM-DD>[-<sha>]``.
PR_BRANCH_PREFIX = "audit/shards-"
#: A push refused because the target branch is protected (Forgejo's pre-receive
#: message, GitHub's GH006 protected-branch and GH013 ruleset rejections).
PROTECTED_RE = re.compile(r"protected branch|GH006|GH013|protected_branch", re.IGNORECASE)
NEEDS_OPERATOR = "needs-operator"
#: A shard PR whose checks have not finished after this long (seconds) is
#: stuck, not slow; it needs a person.
PR_STALE_AGE = 24 * 3600
NO_CHECKS_AGE = 3600
CI_POLL = 20
TOOL_TIMEOUT = 120

#: The append-only comparison CI runs, reused for the PR diff.
_CHECKER = Path(__file__).with_name("check_append_only_shards.py")


class Skip(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


@dataclass
class Result:
    repo: str
    action: str  # pushed | merged | pr-open | noop | skipped | error | would-commit
    reason: str = ""
    commit: str = ""
    shards: list[str] = field(default_factory=list)
    detail: str = ""
    pr_url: str = ""
    #: opened | updated | open | merged | "" (no PR involved)
    pr_state: str = ""

    @property
    def attention(self) -> bool:
        if self.reason in {STALE_PARTIAL, "pr-stale"}:
            return True
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


def process(path: Path, *, remote: str, retries: int, dry_run: bool,
            protected: bool = False, ci_wait: float = 0) -> Result | None:
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
        # Three dots: only what the local commits changed, not upstream-only
        # shard changes this checkout has not pulled yet.
        unpushed = bool(_shard_paths_in(repo, f"{upstream}...HEAD"))
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
            commit_and_push(repo, result, upstream=upstream, default=default, retries=retries,
                            protected=protected, ci_wait=ci_wait)
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
                    retries: int, protected: bool = False, ci_wait: float = 0) -> None:
    for attempt in range(retries + 1):
        sync(repo, upstream)
        changed, _ = repo.pending_shards()
        ready, partial = check_append_only(repo, upstream, changed)
        result.shards = ready
        result.detail = ""
        if partial:
            result.detail = f"waiting on a partial last line: {', '.join(partial)}"
            now = dt.datetime.now().timestamp()
            if any(now - (repo.path / p).stat().st_mtime > STALE_PARTIAL_AGE for p in partial):
                result.reason = STALE_PARTIAL
        if ready:
            repo.run("add", "--", *ready)
            repo.run("commit", "--quiet", "-m", MESSAGE.format(date=through_date(ready)),
                     "--only", "--", *ready)
        if not repo.commits(f"{upstream}..HEAD"):
            result.action = "noop"
            return
        head = repo.out("rev-parse", "HEAD")
        if protected:
            land_via_pr(repo, result, upstream=upstream, default=default, ci_wait=ci_wait)
            return
        push = repo.run("push", "--quiet", repo.remote, f"HEAD:refs/heads/{default}", check=False)
        if push.returncode == 0:
            result.action, result.commit = "pushed", head
            if attempt:
                note = f"after {attempt} retry(ies)"
                result.detail = f"{result.detail}; {note}" if result.detail else note
            return
        err = (push.stderr or push.stdout).strip()
        if PROTECTED_RE.search(err):
            land_via_pr(repo, result, upstream=upstream, default=default, ci_wait=ci_wait)
            return
        # Only a lost race is retried; "[remote rejected]" (a hook or branch
        # protection) is not a race and is reported at once.
        rejected = "non-fast-forward" in err or "fetch first" in err or "[rejected]" in err
        if not rejected or attempt == retries:
            result.commit = head
            raise Skip("push-failed", err)
        # Lost a race: the next pass fetches, undoes the local shard commit
        # (reset --soft), fast-forwards and commits again.


# --- protected default branch: land the shard commit through a PR -------------


@dataclass
class PR:
    number: int
    url: str
    branch: str
    head: str
    created: str = ""


def _tool(repo: Repo, *cmd: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(list(cmd), cwd=repo.path, env=repo.env, capture_output=True,
                              text=True, check=False, timeout=TOOL_TIMEOUT)
    except FileNotFoundError:
        raise Skip(NEEDS_OPERATOR, f"{cmd[0]} is not on PATH") from None


def _tool_out(proc: subprocess.CompletedProcess) -> str:
    return (proc.stderr.strip() + " " + proc.stdout.strip()).strip()[:2000]


class Forge:
    """The forge behind a remote URL: ``github`` (gh) or ``forgejo`` (fj, credctl).

    Forgejo has no machine-readable ``fj`` output, so reads go to its REST API
    (anonymously, or with ``$FORGEJO_TOKEN`` when set); writes go through
    ``fj`` and ``credctl`` with the user's own credentials.
    """

    def __init__(self, platform: str, host: str, slug: str) -> None:
        self.platform, self.host, self.slug = platform, host, slug
        self.web = f"https://{host}"

    @classmethod
    def from_url(cls, url: str) -> "Forge | None":
        m = re.match(r"^(?:https?|ssh|git)://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+?)(?:\.git)?/?$", url) \
            or re.match(r"^(?:[^@/]+@)?([^/:]+):(?!\d+/)(.+?)(?:\.git)?/?$", url)
        if not m or m.group(2).count("/") != 1:
            return None
        host, slug = m.group(1).lower(), m.group(2)
        return cls("github" if host == "github.com" else "forgejo", host, slug)

    # -- reads --

    def _api(self, path: str):
        req = urllib.request.Request(f"{self.web}/api/v1/repos/{self.slug}/{path}",
                                     headers={"Accept": "application/json"})
        token = os.environ.get("FORGEJO_TOKEN")
        if token:
            req.add_header("Authorization", f"token {token}")
        try:
            with urllib.request.urlopen(req, timeout=TOOL_TIMEOUT) as resp:
                return json.load(resp)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise Skip(NEEDS_OPERATOR, f"cannot read {self.web} API {path}: {exc}") from None

    def open_prs(self, repo: Repo, base: str) -> list[PR]:
        if self.platform == "github":
            proc = _tool(repo, "gh", "pr", "list", "--repo", self.slug, "--state", "open",
                         "--base", base, "--json", "number,url,headRefName,headRefOid,createdAt")
            if proc.returncode != 0:
                raise Skip(NEEDS_OPERATOR, f"gh pr list: {_tool_out(proc)}")
            try:
                return [PR(r["number"], r["url"], r["headRefName"], r["headRefOid"],
                           r.get("createdAt", "")) for r in json.loads(proc.stdout or "[]")]
            except (ValueError, KeyError, TypeError) as exc:
                raise Skip(NEEDS_OPERATOR, f"gh pr list: unexpected output: {exc!r}") from None
        prs: list[PR] = []
        for page in range(1, 21):
            rows = self._api(f"pulls?state=open&limit=50&page={page}")
            try:
                prs += [PR(r["number"], r["html_url"], r["head"]["ref"], r["head"]["sha"],
                           r.get("created_at", ""))
                        for r in rows if (r.get("base") or {}).get("ref") == base]
            except (KeyError, TypeError, AttributeError) as exc:
                raise Skip(NEEDS_OPERATOR, f"Forgejo pulls: unexpected response: {exc!r}") from None
            if len(rows) < 50:
                break
        return prs

    def checks(self, repo: Repo, pr: PR) -> tuple[str, str]:
        """Return ("success" | "pending" | "failure", detail) for the PR head."""
        if self.platform == "github":
            proc = _tool(repo, "gh", "pr", "checks", str(pr.number), "--repo", self.slug,
                         "--json", "name,bucket")
            # Exit 8 means "checks pending"; 1 with "no checks reported" means none yet.
            if proc.returncode not in (0, 8) and "no checks reported" not in proc.stderr:
                raise Skip(NEEDS_OPERATOR, f"gh pr checks: {_tool_out(proc)}")
            try:
                rows = [(r["name"], r["bucket"]) for r in json.loads(proc.stdout or "[]")]
            except (ValueError, KeyError, TypeError):
                rows = []
            ok, running = {"pass", "skipping"}, {"pending"}
        else:
            data = self._api(f"commits/{pr.head}/status")
            try:
                rows = [(st.get("context", "?"), st.get("status") or st.get("state") or "")
                        for st in data.get("statuses") or []]
            except (AttributeError, TypeError) as exc:
                raise Skip(NEEDS_OPERATOR, f"Forgejo status: unexpected response: {exc!r}") from None
            ok, running = {"success", "skipped"}, {"pending", "running", "queued", "waiting", ""}
        if not rows:
            # Checks register a few seconds after a push; none after an hour
            # means the repository has no CI for this PR, which needs a person.
            if _pr_age(pr) > NO_CHECKS_AGE:
                return "failure", "no checks reported for this PR"
            return "pending", "no checks reported yet"
        bad = [f"{n}={st}" for n, st in rows if st not in ok and st not in running]
        if bad:
            return "failure", ", ".join(bad)
        waiting = [n for n, st in rows if st in running]
        if waiting:
            return "pending", f"waiting on {', '.join(waiting)}"
        return "success", f"{len(rows)} check(s) passed"

    # -- writes --

    def create_pr(self, repo: Repo, base: str, branch: str, title: str, body: str) -> None:
        if self.platform == "github":
            cmd = ["gh", "pr", "create", "--repo", self.slug, "--base", base, "--head", branch,
                   "--title", title, "--body", body]
        else:
            cmd = ["fj", "pr", "create", "--repo", self.slug, "--base", base, "--head", branch,
                   "--body", body, title]
        proc = _tool(repo, *cmd)
        if proc.returncode != 0:
            raise Skip(NEEDS_OPERATOR, f"{cmd[0]} pr create: {_tool_out(proc)}")

    def close(self, repo: Repo, pr: PR, message: str) -> bool:
        if self.platform == "github":
            cmd = ["gh", "pr", "close", str(pr.number), "--repo", self.slug, "--comment", message]
        else:
            cmd = ["fj", "pr", "close", f"{self.slug}#{pr.number}", "--with-msg", message]
        return _tool(repo, *cmd).returncode == 0

    def merge(self, repo: Repo, pr: PR) -> tuple[bool, str]:
        if self.platform == "github":
            proc = _tool(repo, "gh", "repo", "view", self.slug, "--json",
                         "rebaseMergeAllowed,squashMergeAllowed,mergeCommitAllowed")
            try:
                allowed = json.loads(proc.stdout)
            except ValueError:
                return False, f"gh repo view: {_tool_out(proc)}"
            style = next((flag for key, flag in (("rebaseMergeAllowed", "--rebase"),
                                                  ("squashMergeAllowed", "--squash"),
                                                  ("mergeCommitAllowed", "--merge"))
                          if allowed.get(key)), None)
            if style is None:
                return False, "the repository allows no merge style"
            proc = _tool(repo, "gh", "pr", "merge", str(pr.number), "--repo", self.slug,
                         "--match-head-commit", pr.head, style)
            return proc.returncode == 0, _tool_out(proc)
        proc = _tool(repo, "credctl", "merge", "--repository", f"forgejo:{self.slug}",
                     "--pr", str(pr.number), "--head-sha", pr.head,
                     "--style", "fast-forward-only", "--forgejo-url", self.web)
        try:
            merged = proc.returncode == 0 and json.loads(proc.stdout).get("merged") is True
        except ValueError:
            merged = False
        return merged, _tool_out(proc)


def forge_for(repo: Repo) -> Forge | None:
    return Forge.from_url(repo.out("remote", "get-url", repo.remote))


def _load_checker():
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_append_only_shards", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def verify_pr_diff(repo: Repo, upstream: str, head: str) -> None:
    """Refuse (needs-operator) unless ``upstream...head`` is shard appends only."""
    base = repo.out("merge-base", upstream, head)
    out = repo.out("diff", "--no-renames", "--name-status", f"{base}..{head}")
    rows = [line.split("\t") for line in out.splitlines() if line]
    other = [rest[-1] for status, *rest in rows if status[0] not in "AM" or not is_shard(rest[-1])]
    if not rows:
        raise Skip(NEEDS_OPERATOR, "the PR diff is empty")
    if other:
        raise Skip(NEEDS_OPERATOR, f"the PR changes non-shard paths or deletes: {', '.join(other)}")
    try:
        violations = _load_checker().check(base, head, cwd=str(repo.path))
    except RuntimeError as exc:
        raise Skip(NEEDS_OPERATOR, f"append-only check: {exc}") from None
    if violations:
        raise Skip(NEEDS_OPERATOR, "the PR rewrites shards: " + "; ".join(violations))


def _is_ancestor(repo: Repo, old: str, new: str) -> bool:
    return repo.run("merge-base", "--is-ancestor", old, new, check=False).returncode == 0


def _pr_age(pr: PR) -> float:
    try:
        created = dt.datetime.fromisoformat(pr.created.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return (dt.datetime.now(dt.timezone.utc) - created).total_seconds()


def land_via_pr(repo: Repo, result: Result, *, upstream: str, default: str,
                ci_wait: float) -> None:
    """Land the local shard commit(s) on a protected ``default`` through a PR.

    An open shard PR whose head is an ancestor of HEAD is carried to a merge
    as it is: newer local commits are not pushed onto it while its checks run
    (each push would restart CI, and on a busy repo it would never finish);
    they go in by the next run, on the same branch when it fast-forwards.
    """
    head = repo.out("rev-parse", "HEAD")
    result.commit = head
    forge = forge_for(repo)
    if forge is None:
        raise Skip(NEEDS_OPERATOR, f"{default} is protected and the remote is not a GitHub or "
                                   "Forgejo URL")
    prs = [p for p in forge.open_prs(repo, default) if p.branch.startswith(PR_BRANCH_PREFIX)]
    for p in prs:  # make each PR head known locally for the ancestry test
        repo.run("fetch", "--quiet", repo.remote, f"refs/heads/{p.branch}", check=False)
    pr = next((p for p in prs if _is_ancestor(repo, p.head, head)), None)
    if pr:
        target = pr.head
        result.pr_url, result.pr_state = pr.url, "open"
        if target != head:
            result.detail = _join(result.detail, f"{len(repo.commits(f'{target}..{head}'))} "
                                                 "newer local commit(s) wait for the next PR")
    else:
        target = head
        branch = PR_BRANCH_PREFIX + dt.datetime.now(dt.timezone.utc).date().isoformat()
        taken = repo.run("ls-remote", "--heads", repo.remote, f"refs/heads/{branch}",
                         check=False).stdout.split()
        if taken:
            repo.run("fetch", "--quiet", repo.remote, f"refs/heads/{branch}", check=False)
            if not _is_ancestor(repo, taken[0], head):
                branch = f"{branch}-{head[:7]}"
        push = repo.run("push", "--quiet", repo.remote, f"HEAD:refs/heads/{branch}", check=False)
        if push.returncode != 0:
            raise Skip(NEEDS_OPERATOR, f"push to {branch}: {(push.stderr or push.stdout).strip()}")
        subject = repo.out("log", "-1", "--format=%s", "HEAD")
        forge.create_pr(repo, default, branch, subject,
                        "Audit shards committed by agentops scripts/commit_audit_shards.py. "
                        f"{default} is protected, so they land by pull request. Shard files "
                        "only: append-only NDJSON, no code.")
        pr = next((p for p in forge.open_prs(repo, default) if p.branch == branch), None)
        if pr is None:
            raise Skip(NEEDS_OPERATOR, f"created a PR from {branch} but cannot find it open")
        result.pr_url, result.pr_state = pr.url, "opened"

    verify_pr_diff(repo, upstream, target)
    for old in prs:
        if old.number != pr.number and not forge.close(
                repo, old, f"Superseded by {pr.url} (the base moved; no force-push)."):
            result.detail = _join(result.detail, f"could not close superseded {old.url}")

    deadline = time.monotonic() + ci_wait
    while True:
        current = next((p for p in forge.open_prs(repo, default) if p.number == pr.number), None)
        if current is None:
            raise Skip(NEEDS_OPERATOR, "the PR is no longer open")
        if current.head != target:
            state, detail = "pending", f"PR head is {current.head[:12]}, expected {target[:12]}"
        else:
            state, detail = forge.checks(repo, current)
        if state == "success":
            break
        if state == "failure":
            raise Skip(NEEDS_OPERATOR, f"checks failed: {detail}")
        if time.monotonic() >= deadline:
            result.action, result.reason = "pr-open", "ci-pending"
            if _pr_age(pr) > PR_STALE_AGE:
                result.reason = "pr-stale"
            result.detail = _join(result.detail, detail)
            return
        time.sleep(min(CI_POLL, max(0.0, deadline - time.monotonic())))

    merged, output = forge.merge(repo, current)
    repo.run("fetch", "--quiet", repo.remote)
    landed = _is_ancestor(repo, target, upstream) or \
        repo.out("rev-parse", f"{upstream}^{{tree}}") == repo.out("rev-parse", f"{target}^{{tree}}")
    if not landed:
        if not merged and not _is_ancestor(repo, upstream, target):
            # The base moved during the wait and a fast-forward-only merge was
            # refused: the next run rebuilds on the new base and replaces the PR.
            result.action, result.reason = "pr-open", "base-moved"
            result.detail = _join(result.detail, f"merge refused: {output}")
            return
        if not merged:
            raise Skip(NEEDS_OPERATOR, f"merge refused: {output}")
        # Merged, but rewritten onto a base that moved meanwhile (a GitHub
        # rebase or squash): the next run's sync settles the checkout.
        result.pr_state, result.action, result.reason = "merged", "merged", ""
        result.detail = _join(result.detail, "merged onto a moved base; the next run "
                                             "fast-forwards the checkout")
        return
    if not _is_ancestor(repo, target, upstream):
        # Rebase or squash merge: the same tree under a new commit. Move onto
        # it; any newer local shard commits stay staged for the next run.
        repo.run("reset", "--quiet", "--soft", upstream)
    sync(repo, upstream)
    result.pr_state = "merged"
    result.action, result.reason = "merged", ""
    result.commit = repo.out("rev-parse", upstream)


def _join(a: str, b: str) -> str:
    return f"{a}; {b}" if a else b


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
    parser.add_argument("--protected", action="append", default=[], metavar="NAME",
                        help="checkout whose default branch is protected: land shards by PR "
                             "without trying a direct push first (repeatable; a protected-branch "
                             "rejection is detected without it)")
    parser.add_argument("--ci-wait", type=float, default=300,
                        help="seconds to wait for a shard PR's checks before leaving it for "
                             "the next run (default 300)")
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
            res = process(path, remote=args.remote, retries=args.retries, dry_run=args.dry_run,
                          protected=path.name in args.protected, ci_wait=args.ci_wait)
        except Skip as skip:
            res = Result(repo=path.name, action="error", reason=skip.reason, detail=skip.detail)
        except OSError as exc:
            res = Result(repo=path.name, action="error", reason="os-error", detail=str(exc))
        except subprocess.TimeoutExpired as exc:
            res = Result(repo=path.name, action="error", reason="timeout", detail=str(exc))
        except Exception as exc:  # one odd forge response must not end the whole run
            res = Result(repo=path.name, action="error", reason="unexpected", detail=repr(exc))
        if res is not None:
            results.append(res)
            print(json.dumps(asdict(res), sort_keys=True), flush=True)

    attention = [r for r in results if r.attention]
    summary = {
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "dry_run": args.dry_run,
        "attention": [r.repo for r in attention],
        "prs": [{"repo": r.repo, "url": r.pr_url, "state": r.pr_state,
                 "action": r.action, "reason": r.reason}
                for r in results if r.pr_url or r.pr_state],
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
