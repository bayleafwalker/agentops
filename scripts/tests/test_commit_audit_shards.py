"""commit_audit_shards.py against real temporary git repos (bare remote + checkout).

Each test builds ``<tmp>/remote.git`` and a checkout at ``<tmp>/root/work`` (the
scanned root is ``<tmp>/root``), plus an ``other`` clone outside the root that
plays the second machine. Global and system git config are isolated so the
host's hooks (gitleaks via core.hooksPath) and credentials never run here.
"""
from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "commit_audit_shards.py"
_spec = importlib.util.spec_from_file_location("commit_audit_shards", SCRIPT)
cas = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules[_spec.name] = cas  # dataclasses resolves annotations through it
_spec.loader.exec_module(cas)

SHARD = "_artifacts/demo/audit/events-2026-09-26.ndjson"
SHARD2 = "_artifacts/demo/audit/events-2026-09-27.ndjson"


def git(cwd: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {args}: {proc.stderr}")
    return proc.stdout.strip()


def write(repo: Path, rel: str, text: str, append: bool = False) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a" if append else "w") as fh:
        fh.write(text)


def commit_all(repo: Path, msg: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def env(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Test\n\temail = test@example.invalid\n"
        "[init]\n\tdefaultBranch = main\n[core]\n\thooksPath = /dev/null\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(remote), str(seed))
    write(seed, "README.md", "seed\n")
    write(seed, SHARD, '{"n":1}\n')
    commit_all(seed, "seed")
    git(seed, "push", "-q", "origin", "main")
    root = tmp_path / "root"
    root.mkdir()
    work = root / "work"
    git(tmp_path, "clone", "-q", str(remote), str(work))
    other = tmp_path / "other"
    git(tmp_path, "clone", "-q", str(remote), str(other))
    return {"tmp": tmp_path, "remote": remote, "root": root, "work": work, "other": other}


def run(env, *extra: str) -> tuple[int, list[dict], dict]:
    summary = env["tmp"] / "summary.json"
    rc = cas.main(["--root", str(env["root"]), "--summary", str(summary), *extra])
    data = json.loads(summary.read_text())
    return rc, data["results"], data


def remote_head(env) -> str:
    return git(env["remote"], "rev-parse", "main")


def remote_files(env, rev: str = "main") -> list[str]:
    return git(env["remote"], "diff-tree", "--no-commit-id", "--name-only", "-r", rev).splitlines()


def other_pushes(env, rel: str = "code.py", text: str = "x = 1\n") -> str:
    other = env["other"]
    git(other, "pull", "-q", "--ff-only")
    write(other, rel, text, append=True)
    sha = commit_all(other, f"feat: touch {rel}")
    git(other, "push", "-q", "origin", "main")
    return sha


# --- behaviour ---------------------------------------------------------------


def test_happy_path_commits_and_pushes_untracked_shard(env):
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 0
    assert [r["action"] for r in results] == ["pushed"]
    assert results[0]["shards"] == [SHARD2]
    assert results[0]["commit"] == remote_head(env)
    assert git(env["remote"], "log", "-1", "--format=%s", "main") == \
        "chore(audit): append audit shards through 2026-09-27"
    assert remote_files(env) == [SHARD2]
    assert git(env["work"], "status", "--porcelain") == ""


def test_behind_remote_fast_forwards_then_commits(env):
    upstream = other_pushes(env)
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "pushed"
    assert git(env["remote"], "rev-parse", "main~1") == upstream
    assert git(env["work"], "rev-parse", "HEAD") == remote_head(env)


def test_untracked_and_modified_shards_in_one_commit(env):
    write(env["work"], SHARD, '{"n":1.5}\n', append=True)
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 0
    assert sorted(remote_files(env)) == sorted([SHARD, SHARD2])
    assert git(env["remote"], "show", f"main:{SHARD}") == '{"n":1}\n{"n":1.5}'


def test_non_shard_changes_are_untouched(env):
    work = env["work"]
    write(work, "staged.txt", "staged\n")
    git(work, "add", "staged.txt")
    write(work, "README.md", "dirty\n", append=True)
    write(work, "scratch.txt", "untracked\n")
    write(work, SHARD2, '{"n":2}\n')
    before = git(work, "status", "--porcelain")
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "pushed"
    assert remote_files(env) == [SHARD2]
    after = git(work, "status", "--porcelain")
    assert after == "\n".join(l for l in before.splitlines() if SHARD2 not in l and "_artifacts" not in l)
    assert git(work, "diff", "--cached", "--name-only") == "staged.txt"
    assert (work / "README.md").read_text() == "seed\ndirty\n"


def test_feature_branch_is_skipped_and_reported(env):
    work = env["work"]
    git(work, "switch", "-q", "-c", "feature")
    write(work, SHARD2, '{"n":2}\n')
    head = remote_head(env)
    rc, results, data = run(env)
    assert rc == 1
    assert results[0]["action"] == "skipped" and results[0]["reason"] == "not-default-branch"
    assert data["attention"] == ["work"]
    assert remote_head(env) == head
    assert git(work, "log", "-1", "--format=%s") == "seed"


def test_unpushed_non_shard_commit_is_skipped(env):
    work = env["work"]
    write(work, "wip.py", "wip\n")
    commit_all(work, "wip")
    write(work, SHARD2, '{"n":2}\n')
    head = remote_head(env)
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "unpushed-work"
    assert remote_head(env) == head
    assert git(work, "log", "-1", "--format=%s") == "wip"
    assert "?? _artifacts/" in git(work, "status", "--porcelain")


def _race(monkeypatch, env, times: int = 1) -> list[str]:
    """Push from the other clone right before each of the first ``times`` pushes."""
    pushed: list[str] = []
    original = cas.Repo.run

    def racing(self, *args, check=True):
        if args and args[0] == "push" and len(pushed) < times:
            pushed.append(other_pushes(env, "race.txt", f"{len(pushed)}\n"))
        return original(self, *args, check=check)

    monkeypatch.setattr(cas.Repo, "run", racing)
    return pushed


def test_push_race_fetches_fast_forwards_and_retries(env, monkeypatch):
    raced = _race(monkeypatch, env, times=2)
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "pushed"
    assert results[0]["detail"] == "after 2 retry(ies)"
    assert git(env["remote"], "rev-parse", "main~1") == raced[-1]
    assert remote_files(env) == [SHARD2]
    # linear history, no merge commits
    assert git(env["remote"], "rev-list", "--merges", "main") == ""


def test_nothing_to_do_makes_no_commit(env):
    head = remote_head(env)
    rc, results, data = run(env)
    assert rc == 0 and results == [] and data["attention"] == []
    assert remote_head(env) == head
    rc, results, _ = run(env)
    assert rc == 0 and results == []


def test_second_run_is_idempotent(env):
    write(env["work"], SHARD2, '{"n":2}\n')
    run(env)
    head = remote_head(env)
    rc, results, _ = run(env)
    assert rc == 0 and results == [] and remote_head(env) == head


def test_pull_after_commit_leaves_no_untracked_twin(env):
    work = env["work"]
    write(work, SHARD2, '{"n":2}\n')
    run(env)
    assert "??" not in git(work, "status", "--porcelain")
    # The other machine pulls the shard commit and pushes on top of it...
    other_pushes(env)
    # ...and the hook checkout pulls cleanly: nothing untracked shadows the shard.
    git(work, "pull", "-q", "--ff-only")
    assert git(work, "rev-parse", "HEAD") == remote_head(env)


def test_committing_elsewhere_does_break_pull(env):
    """The constraint the routine exists for: a twin committed elsewhere blocks pull."""
    work, other = env["work"], env["other"]
    write(work, SHARD2, '{"n":2}\n')
    write(other, SHARD2, '{"n":2}\n')
    commit_all(other, "chore(audit): elsewhere")
    git(other, "push", "-q", "origin", "main")
    proc = subprocess.run(["git", "pull", "--ff-only"], cwd=work, capture_output=True, text=True)
    assert proc.returncode != 0 and "untracked working tree files" in proc.stderr


def test_unpushed_shard_only_commit_is_pushed(env):
    work = env["work"]
    write(work, SHARD2, '{"n":2}\n')
    sha = commit_all(work, "chore(audit): by hand")
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "pushed"
    assert remote_head(env) == sha


def test_unpushed_shard_only_commit_behind_remote_is_recommitted(env):
    work = env["work"]
    write(work, SHARD2, '{"n":2}\n')
    commit_all(work, "chore(audit): by hand")
    upstream = other_pushes(env)
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "pushed"
    assert git(env["remote"], "rev-parse", "main~1") == upstream
    assert remote_files(env) == [SHARD2]


# --- forced failures of the guards ------------------------------------------


def test_rewritten_shard_is_refused(env):
    work = env["work"]
    write(work, SHARD, '{"n":"edited"}\n')
    head = remote_head(env)
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "shard-rewritten"
    assert remote_head(env) == head
    assert git(work, "log", "-1", "--format=%s") == "seed"


def test_merge_in_progress_is_a_transient_skip(env):
    work = env["work"]
    (work / ".git" / "MERGE_HEAD").write_text(git(work, "rev-parse", "HEAD") + "\n")
    write(work, SHARD2, '{"n":2}\n')
    head = remote_head(env)
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["reason"] == "operation-in-progress"
    assert remote_head(env) == head


def test_rebase_in_progress_is_skipped(env):
    work = env["work"]
    (work / ".git" / "rebase-merge").mkdir()
    write(work, SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert results[0]["reason"] == "operation-in-progress"


def test_held_lock_skips(env):
    work = env["work"]
    write(work, SHARD2, '{"n":2}\n')
    head = remote_head(env)
    with open(work / ".git" / cas.LOCK_NAME, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        rc, results, _ = run(env)
    assert rc == 0 and results[0]["reason"] == "locked"
    assert remote_head(env) == head


def test_cannot_fast_forward_is_reported(env):
    work = env["work"]
    other_pushes(env, "README.md", "remote\n")
    write(work, "README.md", "local\n", append=True)  # conflicts with the ff
    write(work, SHARD2, '{"n":2}\n')
    head = remote_head(env)
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "cannot-fast-forward"
    assert remote_head(env) == head
    assert (work / "README.md").read_text() == "seed\nlocal\n"


def test_race_beyond_retries_fails_without_force(env, monkeypatch):
    raced = _race(monkeypatch, env, times=5)
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env, "--retries", "1")
    assert rc == 1 and results[0]["reason"] == "push-failed"
    assert remote_head(env) == raced[-1]  # the other side's work was not overwritten
    assert SHARD2 not in git(env["remote"], "ls-tree", "-r", "--name-only", "main")


def test_unreachable_remote_is_reported(env):
    work = env["work"]
    git(work, "remote", "set-url", "origin", str(env["tmp"] / "missing.git"))
    write(work, SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["action"] == "error"


def test_partial_line_waits_for_next_run(env):
    write(env["work"], SHARD2, '{"n":2')
    head = remote_head(env)
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "noop"
    assert remote_head(env) == head


def test_deleted_shard_is_never_committed(env):
    work = env["work"]
    (work / SHARD).unlink()
    write(work, SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "pushed"
    assert remote_files(env) == [SHARD2]
    assert SHARD in git(env["remote"], "ls-tree", "-r", "--name-only", "main")
    assert "deleted shards left alone" in results[0]["detail"]


def test_dry_run_changes_nothing(env):
    write(env["work"], SHARD2, '{"n":2}\n')
    head = remote_head(env)
    rc, results, _ = run(env, "--dry-run")
    assert rc == 0 and results[0]["action"] == "would-commit"
    assert remote_head(env) == head
    assert git(env["work"], "log", "-1", "--format=%s") == "seed"


# --- review follow-ups -------------------------------------------------------


def test_race_keeps_other_staged_and_unstaged_changes(env, monkeypatch):
    work = env["work"]
    write(work, "staged.txt", "staged\n")
    git(work, "add", "staged.txt")
    write(work, "README.md", "dirty\n", append=True)
    _race(monkeypatch, env, times=1)
    write(work, SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 0 and results[0]["action"] == "pushed"
    assert remote_files(env) == [SHARD2]
    assert git(work, "diff", "--cached", "--name-only") == "staged.txt"
    assert (work / "README.md").read_text() == "seed\ndirty\n"


def test_divergent_same_shard_skip_restores_local_commit(env):
    work = env["work"]
    write(work, SHARD, '{"local":1}\n', append=True)
    local = commit_all(work, "chore(audit): by hand")
    other_pushes(env, SHARD, '{"remote":1}\n')
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "cannot-fast-forward"
    assert git(work, "rev-parse", "HEAD") == local  # the skip mutated nothing
    assert git(work, "status", "--porcelain") == ""


def test_unpushed_commit_rewriting_a_shard_is_refused(env):
    work = env["work"]
    write(work, SHARD, '{"n":"edited"}\n')
    commit_all(work, "chore(audit): rewrite")
    head = remote_head(env)
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "shard-rewritten"
    assert remote_head(env) == head


def test_shard_commit_under_wip_commit_is_reported(env):
    work = env["work"]
    write(work, SHARD2, '{"n":2}\n')
    commit_all(work, "chore(audit): by hand")
    write(work, "wip.py", "wip\n")
    commit_all(work, "wip")
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "unpushed-work"


def test_remote_hook_rejection_is_not_retried(env, monkeypatch):
    hook = env["remote"] / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho denied >&2\nexit 1\n")
    hook.chmod(0o755)
    git(env["remote"], "config", "core.hooksPath", str(hook.parent))  # global is /dev/null
    pushes = []
    original = cas.Repo.run

    def counting(self, *args, check=True):
        if args and args[0] == "push":
            pushes.append(args)
        return original(self, *args, check=check)

    monkeypatch.setattr(cas.Repo, "run", counting)
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "push-failed"
    assert len(pushes) == 1


def test_timeout_is_reported_not_fatal(env, monkeypatch):
    write(env["work"], SHARD2, '{"n":2}\n')

    def slow(self, *args, check=True):
        raise subprocess.TimeoutExpired(["git", *args], 1)

    monkeypatch.setattr(cas.Repo, "run", slow)
    rc, results, _ = run(env)
    assert rc == 1 and results[0]["reason"] == "timeout"


def test_upstream_only_shard_change_is_not_a_candidate(env):
    work = env["work"]
    other_pushes(env, SHARD2, '{"remote":1}\n')
    git(work, "fetch", "-q")  # origin/main ahead, local not pulled
    write(work, "README.md", "dirty\n", append=True)
    before = git(work, "rev-parse", "HEAD")
    rc, results, _ = run(env)
    assert rc == 0 and results == []
    assert git(work, "rev-parse", "HEAD") == before  # not fast-forwarded behind the operator's back


def test_stale_partial_line_needs_attention(env):
    import os
    import time
    path = env["work"] / SHARD2
    write(env["work"], SHARD2, '{"n":2')
    old = time.time() - 3 * 3600
    os.utime(path, (old, old))
    rc, results, data = run(env)
    assert rc == 1 and results[0]["reason"] == "stale-partial-line"
    assert data["attention"] == ["work"]


# --- protected default branch: landing through a PR ---------------------------
#
# The bare remote gets a pre-receive hook that refuses main with Forgejo's
# message. fj, gh and credctl are PATH stubs (one script, dispatching on its
# name) sharing a JSON state file with the fake Forgejo API: open PRs, the CI
# state of every head and whether a merge is refused. A merge fast-forwards the
# bare remote's main with update-ref, the way the forge would.

STUB = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
state_path, remote = os.environ["FAKE_FORGE"], os.environ["FAKE_REMOTE"]
tool, args = os.path.basename(sys.argv[0]), sys.argv[1:]
with open(os.environ["FAKE_FORGE_LOG"], "a") as log:
    log.write(json.dumps([tool, *args]) + "\n")
state = json.load(open(state_path))
def save(): json.dump(state, open(state_path, "w"))
def opt(name): return args[args.index(name) + 1]
def ref(branch):
    return subprocess.run(["git", "-C", remote, "rev-parse", "refs/heads/" + branch],
                          capture_output=True, text=True).stdout.strip()
def find(num): return next(p for p in state["prs"] if p["number"] == int(num))
def do_merge(pr, sha):
    if state.get("merge") == "refuse" or ref(pr["branch"]) != sha:
        return False
    main = ref("main")
    if subprocess.run(["git", "-C", remote, "merge-base", "--is-ancestor", main, sha]).returncode:
        return False
    subprocess.run(["git", "-C", remote, "update-ref", "refs/heads/main", sha, main], check=True)
    pr["state"] = "merged"; save(); return True
if args[:2] == ["pr", "create"]:
    num = len(state["prs"]) + 1
    state["prs"].append({"number": num, "branch": opt("--head"), "base": opt("--base"),
                         "state": "open", "created": state.get("created", "2026-09-27T00:00:00Z"),
                         "url": f"https://forge.test/owner/work/pulls/{num}"})
    save(); print(state["prs"][-1]["url"]); sys.exit(0)
if args[:2] == ["pr", "close"]:
    find(args[2].split("#")[-1])["state"] = "closed"; save(); sys.exit(0)
if tool == "credctl" and args[0] == "merge":
    ok = do_merge(find(opt("--pr")), opt("--head-sha"))
    print(json.dumps({"merged": ok, "reason": "" if ok else "refused"}))
    sys.exit(0 if ok else 4)
if tool == "gh":
    if args[:2] == ["pr", "list"]:
        print(json.dumps([{"number": p["number"], "url": p["url"], "headRefName": p["branch"],
                           "headRefOid": ref(p["branch"]), "createdAt": p["created"]}
                          for p in state["prs"] if p["state"] == "open"])); sys.exit(0)
    if args[:2] == ["pr", "checks"]:
        bucket = {"success": "pass", "pending": "pending", "failure": "fail"}[state["ci"]]
        print(json.dumps([{"name": "test", "bucket": bucket}])); sys.exit(0)
    if args[:2] == ["repo", "view"]:
        print(json.dumps({"rebaseMergeAllowed": True})); sys.exit(0)
    if args[:2] == ["pr", "merge"]:
        sys.exit(0 if do_merge(find(args[2]), opt("--match-head-commit")) else 1)
sys.exit(f"stub: unhandled {tool} {args}")
'''


@pytest.fixture
def forge(env, monkeypatch):
    tmp = env["tmp"]
    hooks = tmp / "remote-hooks"
    hooks.mkdir()
    (hooks / "pre-receive").write_text(
        "#!/bin/sh\nwhile read old new ref; do\n"
        "  if [ \"$ref\" = refs/heads/main ]; then\n"
        "    echo 'remote: Forgejo: Not allowed to push to protected branch main' >&2\n"
        "    exit 1\n  fi\ndone\n")
    (hooks / "pre-receive").chmod(0o755)
    git(env["remote"], "config", "core.hooksPath", str(hooks))
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "stub").write_text(STUB)
    (bindir / "stub").chmod(0o755)
    for name in ("fj", "gh", "credctl"):
        (bindir / name).symlink_to(bindir / "stub")
    state = tmp / "forge.json"
    state.write_text(json.dumps({"prs": [], "ci": "pending"}))
    log = tmp / "forge.log"
    log.write_text("")
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_FORGE", str(state))
    monkeypatch.setenv("FAKE_REMOTE", str(env["remote"]))
    monkeypatch.setenv("FAKE_FORGE_LOG", str(log))

    def branch_head(branch):
        return git(env["remote"], "rev-parse", f"refs/heads/{branch}", check=False)

    def api(self, path):
        data = json.loads(state.read_text())
        if path.startswith("pulls?"):
            return [{"number": p["number"], "html_url": p["url"], "created_at": p["created"],
                     "head": {"ref": p["branch"], "sha": branch_head(p["branch"])},
                     "base": {"ref": p["base"]}}
                    for p in data["prs"] if p["state"] == "open"]
        assert path.startswith("commits/") and path.endswith("/status")
        return {"statuses": [{"context": "ci / test", "status": data["ci"]},
                             {"context": "ci / image", "status": "skipped"}]}

    platform = {"name": "forgejo"}
    monkeypatch.setattr(cas.Forge, "_api", api)
    monkeypatch.setattr(cas, "forge_for",
                        lambda repo: cas.Forge(platform["name"], "forge.test", "owner/work"))

    class F:
        def set(self, **kw):
            data = json.loads(state.read_text())
            data.update(kw)
            state.write_text(json.dumps(data))

        def prs(self):
            return json.loads(state.read_text())["prs"]

        def calls(self, tool=None):
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            return [r for r in rows if tool is None or r[0] == tool]

        branch = staticmethod(branch_head)

        def github(self):
            platform["name"] = "github"

    return F()


TODAY_BRANCH = "audit/shards-" + __import__("datetime").datetime.now(
    __import__("datetime").timezone.utc).date().isoformat()


def local_ahead(env) -> list[str]:
    return git(env["work"], "rev-list", "origin/main..HEAD").split()


def test_protected_rejection_pushes_branch_and_opens_pr(env, forge):
    write(env["work"], SHARD2, '{"n":2}\n')
    main_before = remote_head(env)
    rc, results, summary = run(env, "--ci-wait", "0")
    res = results[0]
    assert rc == 0, res  # CI still running is not an attention state
    assert (res["action"], res["reason"], res["pr_state"]) == ("pr-open", "ci-pending", "opened")
    assert res["pr_url"] == "https://forge.test/owner/work/pulls/1"
    head = git(env["work"], "rev-parse", "HEAD")
    assert forge.branch(TODAY_BRANCH) == head == res["commit"]
    assert remote_head(env) == main_before  # nothing bypassed protection
    create = forge.calls("fj")[0]
    assert create[:6] == ["fj", "pr", "create", "--repo", "owner/work", "--base"]
    assert "--head" in create and TODAY_BRANCH in create
    assert forge.calls("credctl") == []
    assert summary["prs"] == [{"repo": "work", "url": res["pr_url"], "state": "opened",
                               "action": "pr-open", "reason": "ci-pending"}]


def test_protected_ci_pending_leaves_pr_then_green_merges_and_fast_forwards(env, forge):
    write(env["work"], SHARD2, '{"n":2}\n')
    run(env, "--ci-wait", "0")
    rc, results, _ = run(env, "--ci-wait", "0")  # still pending: left alone, not reopened
    assert rc == 0 and results[0]["action"] == "pr-open" and results[0]["pr_state"] == "open"
    assert len([c for c in forge.calls("fj") if c[1:3] == ["pr", "create"]]) == 1
    forge.set(ci="success")
    head = git(env["work"], "rev-parse", "HEAD")
    rc, results, _ = run(env, "--ci-wait", "0")
    res = results[0]
    assert rc == 0, res
    assert (res["action"], res["pr_state"], res["commit"]) == ("merged", "merged", head)
    assert forge.calls("credctl") == [[
        "credctl", "merge", "--repository", "forgejo:owner/work", "--pr", "1",
        "--head-sha", head, "--style", "fast-forward-only", "--forgejo-url", "https://forge.test"]]
    assert remote_head(env) == head
    assert local_ahead(env) == [] and git(env["work"], "status", "--porcelain") == ""
    assert run(env)[1] == []  # nothing left pending


def test_protected_existing_pr_branch_is_reused_fast_forward(env, forge):
    write(env["work"], SHARD2, '{"n":2}\n')
    run(env, "--ci-wait", "0")
    first = forge.branch(TODAY_BRANCH)
    write(env["work"], SHARD2, '{"n":3}\n', append=True)
    forge.set(ci="success")
    rc, results, _ = run(env, "--ci-wait", "0")
    res = results[0]
    assert rc == 0 and res["action"] == "merged", res
    head = git(env["work"], "rev-parse", "HEAD")
    assert git(env["work"], "rev-parse", "HEAD~1") == first  # stacked, not rewritten
    assert forge.branch(TODAY_BRANCH) == head == remote_head(env)
    assert len(forge.prs()) == 1 and forge.prs()[0]["state"] == "merged"


def test_protected_base_moved_opens_new_branch_and_closes_old_pr(env, forge):
    write(env["work"], SHARD2, '{"n":2}\n')
    run(env, "--ci-wait", "0")
    old = forge.branch(TODAY_BRANCH)
    # main moves under the open PR (a merge of other work, landed as the forge would)
    git(env["remote"], "config", "core.hooksPath", "/dev/null")
    other_pushes(env)
    git(env["remote"], "config", "core.hooksPath", str(env["tmp"] / "remote-hooks"))
    rc, results, _ = run(env, "--ci-wait", "0")
    res = results[0]
    head = git(env["work"], "rev-parse", "HEAD")
    assert rc == 0 and res["pr_state"] == "opened", res
    assert forge.branch(TODAY_BRANCH) == old  # never force-pushed
    assert forge.branch(f"{TODAY_BRANCH}-{head[:7]}") == head
    assert [p["state"] for p in forge.prs()] == ["closed", "open"]


def test_protected_non_shard_diff_needs_operator(env, forge, monkeypatch):
    # Forced failure: disable the earlier guard (unpushed non-shard work is
    # normally refused by sync) so the PR diff guard is what has to catch it.
    monkeypatch.setattr(cas.Repo, "shard_only", lambda self, commit: True)
    write(env["work"], "code.py", "x = 1\n")
    write(env["work"], SHARD2, '{"n":2}\n')
    commit_all(env["work"], "wip")
    forge.set(ci="success")
    rc, results, summary = run(env, "--ci-wait", "0")
    res = results[0]
    assert rc == 1 and res["reason"] == "needs-operator", res
    assert "code.py" in res["detail"] and res["pr_url"]
    assert forge.calls("credctl") == []
    assert summary["attention"] == ["work"]


def test_protected_rewritten_shard_in_pr_needs_operator(env, forge, monkeypatch):
    # Forced failure: skip the local prefix check so only the PR guard stands.
    monkeypatch.setattr(cas, "check_append_only", lambda repo, upstream, paths: (paths, []))
    write(env["work"], SHARD, '{"n":"rewritten"}\n')
    forge.set(ci="success")
    rc, results, _ = run(env, "--ci-wait", "0")
    res = results[0]
    assert rc == 1 and res["reason"] == "needs-operator", res
    assert "rewritten" in res["detail"] or "line 1" in res["detail"]
    assert forge.calls("credctl") == []


def test_protected_merge_refused_needs_operator(env, forge):
    write(env["work"], SHARD2, '{"n":2}\n')
    forge.set(ci="success", merge="refuse")
    main_before = remote_head(env)
    rc, results, _ = run(env, "--ci-wait", "0")
    res = results[0]
    assert rc == 1 and res["reason"] == "needs-operator", res
    assert res["pr_url"] == "https://forge.test/owner/work/pulls/1"
    assert "merge refused" in res["detail"]
    assert remote_head(env) == main_before and len(local_ahead(env)) == 1


def test_protected_ci_failure_needs_operator(env, forge):
    write(env["work"], SHARD2, '{"n":2}\n')
    forge.set(ci="failure")
    rc, results, _ = run(env, "--ci-wait", "0")
    assert rc == 1 and results[0]["reason"] == "needs-operator"
    assert "ci / test=failure" in results[0]["detail"]
    assert forge.calls("credctl") == []


def test_protected_pr_pending_for_a_day_needs_attention(env, forge):
    forge.set(created="2026-01-01T00:00:00Z")
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env, "--ci-wait", "0")
    assert rc == 1 and results[0]["reason"] == "pr-stale"


def test_configured_protected_skips_the_direct_push(env, forge, monkeypatch):
    pushes = []
    original = cas.Repo.run

    def counting(self, *args, check=True):
        if args and args[0] == "push":
            pushes.append(args[-1])
        return original(self, *args, check=check)

    monkeypatch.setattr(cas.Repo, "run", counting)
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env, "--ci-wait", "0", "--protected", "work")
    assert rc == 0 and results[0]["action"] == "pr-open"
    assert pushes == [f"HEAD:refs/heads/{TODAY_BRANCH}"]


def test_protected_github_merges_with_match_head_commit(env, forge):
    forge.github()
    forge.set(ci="success")
    write(env["work"], SHARD2, '{"n":2}\n')
    rc, results, _ = run(env, "--ci-wait", "0")
    res = results[0]
    head = git(env["work"], "rev-parse", "HEAD")
    assert rc == 0 and res["action"] == "merged", res
    gh = [c for c in forge.calls("gh") if c[1:3] in (["pr", "create"], ["pr", "merge"])]
    assert gh[0][:5] == ["gh", "pr", "create", "--repo", "owner/work"]
    assert gh[1] == ["gh", "pr", "merge", "1", "--repo", "owner/work",
                     "--match-head-commit", head, "--rebase"]
    assert remote_head(env) == head and local_ahead(env) == []


@pytest.mark.parametrize("url,expected", [
    ("https://git.apps.kotona.app/bayleaf/cred-broker.git",
     ("forgejo", "git.apps.kotona.app", "bayleaf/cred-broker")),
    ("ssh://git@git.apps.kotona.app:2222/bayleaf/cred-broker.git",
     ("forgejo", "git.apps.kotona.app", "bayleaf/cred-broker")),
    ("git@github.com:bayleafwalker/agentops.git", ("github", "github.com", "bayleafwalker/agentops")),
    ("https://github.com/bayleafwalker/agentops", ("github", "github.com", "bayleafwalker/agentops")),
])
def test_forge_from_remote_url(url, expected):
    forge = cas.Forge.from_url(url)
    assert (forge.platform, forge.host, forge.slug) == expected


def test_forge_from_local_path_is_none():
    assert cas.Forge.from_url("/tmp/remote.git") is None
