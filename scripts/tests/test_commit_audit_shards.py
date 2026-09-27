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
