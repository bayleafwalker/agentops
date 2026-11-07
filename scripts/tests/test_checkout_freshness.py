"""Tests for scripts/checkout_freshness.py (`agentops checkout-freshness`).

Each test builds a bare remote, a clone and a second writer clone under tmp_path; a
commit pushed from the writer makes the clone behind once it fetches.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "checkout_freshness.py"
SPEC = importlib.util.spec_from_file_location("checkout_freshness", SCRIPT)
assert SPEC and SPEC.loader
fresh = importlib.util.module_from_spec(SPEC)
sys.modules["checkout_freshness"] = fresh
SPEC.loader.exec_module(fresh)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.test",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}


def sh(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, **GIT_ENV}).stdout


@pytest.fixture
def estate(tmp_path, monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    remote = tmp_path / "remote.git"
    sh("init", "--bare", "-b", "main", str(remote))
    writer = tmp_path / "writer"
    sh("clone", str(remote), str(writer))
    (writer / "a.txt").write_text("one\n")
    sh("add", "a.txt", cwd=writer)
    sh("commit", "-m", "one", cwd=writer)
    sh("push", "origin", "main", cwd=writer)
    base = tmp_path / "dev"
    clone = base / "repo"
    sh("clone", str(remote), str(clone))
    (writer / "b.txt").write_text("two\n")
    sh("add", "b.txt", cwd=writer)
    sh("commit", "-m", "two", cwd=writer)
    sh("push", "origin", "main", cwd=writer)
    return base, clone


def snapshot(repo: Path) -> tuple[str, str, str]:
    return (sh("rev-parse", "HEAD", cwd=repo), sh("status", "--porcelain", cwd=repo),
            sh("rev-parse", "refs/heads/main", cwd=repo))


def test_clean_clone_before_fetch_is_current(estate):
    _, clone = estate
    report = fresh.inspect("repo", clone, fetch=False)
    assert report["available"] and report["branch"] == "main"
    assert report["upstream"] == "origin/main" and report["upstream_source"] == "main@{upstream}"
    assert (report["main_ahead"], report["main_behind"]) == (0, 0)
    assert (report["dirty_tracked"], report["untracked"], report["worktrees"]) == (0, 0, 1)
    # A clone leaves neither FETCH_HEAD nor (always) a remote-ref reflog.
    assert report["last_fetch"] is None or report["last_fetch_source"] == "reflog"


def test_fetch_makes_clone_behind_without_touching_worktree(estate):
    _, clone = estate
    before = snapshot(clone)
    report = fresh.inspect("repo", clone, fetch=True)
    assert report["fetch"] == "ok"
    assert (report["main_ahead"], report["main_behind"]) == (0, 1)
    assert report["last_fetch"] is not None
    assert report["last_fetch_source"] in {"reflog", "FETCH_HEAD"}
    assert snapshot(clone) == before
    assert not (clone / "b.txt").exists()


def test_dirty_untracked_and_worktrees(estate, tmp_path):
    _, clone = estate
    (clone / "a.txt").write_text("changed\n")
    (clone / "new.txt").write_text("x\n")
    (clone / "sub").mkdir()
    (clone / "sub" / "deep.txt").write_text("y\n")
    (clone / "sub" / "deeper.txt").write_text("z\n")  # a wholly untracked dir counts once
    sh("worktree", "add", str(tmp_path / "wt"), "-b", "side", cwd=clone)
    report = fresh.inspect("repo", clone, fetch=False)
    assert (report["dirty_tracked"], report["untracked"], report["worktrees"]) == (1, 2, 2)


def test_upstream_fallback_and_feature_branch(estate):
    _, clone = estate
    sh("checkout", "-q", "-b", "feature", cwd=clone)
    sh("branch", "--unset-upstream", "main", cwd=clone)
    report = fresh.inspect("repo", clone, fetch=False)
    assert report["branch"] == "feature"
    assert report["upstream"] == "origin/main"
    assert report["upstream_source"] == "fallback origin/main"


def test_non_origin_upstream_is_used(estate, tmp_path):
    _, clone = estate
    sh("remote", "rename", "origin", "github", cwd=clone)
    report = fresh.inspect("repo", clone, fetch=True)
    assert report["upstream"] == "github/main"
    assert report["main_behind"] == 1


def test_missing_repo_is_not_available(tmp_path):
    report = fresh.inspect("gone", tmp_path / "gone", fetch=False)
    assert report == {"repo": "gone", "path": str(tmp_path / "gone"), "available": False,
                      "reason": "path does not exist"}


def test_cli_json_markdown_and_strict(estate, capsys):
    base, _ = estate
    assert fresh.main(["--base", str(base), "repo", "missing", "--fetch", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "checkout-freshness/v1"
    assert [r["repo"] for r in payload["repos"]] == ["repo", "missing"]
    assert payload["repos"][0]["main_behind"] == 1
    assert fresh.main(["--base", str(base), "repo", "missing"]) == 0
    text = capsys.readouterr().out
    assert "| repo | main | +0/-1 origin/main |" in text
    assert "| missing | not available (path does not exist) |" in text
    assert "Behind upstream: repo." in text
    assert fresh.main(["--base", str(base), "repo", "--strict"]) == 1


def test_strict_passes_when_current(estate, capsys):
    base, clone = estate
    assert fresh.main(["--base", str(base), "repo", "--strict"]) == 0  # not fetched yet
    capsys.readouterr()
    assert fresh.main([f"named={clone}", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["repos"][0]["repo"] == "named"
    assert payload["repos"][0]["path"] == str(clone)


def test_last_fetch_is_reflog_entry_time_not_commit_time(estate, monkeypatch):
    _, clone = estate
    commit_time = int(subprocess.run(["git", "log", "-1", "--format=%ct", "origin/main"],
                                     cwd=clone, capture_output=True, text=True).stdout)
    fetched_at = 2_000_000_000  # 2033-05-18T03:33:20Z, well after any commit
    # The reflog entry a fetch writes is stamped with the committer date.
    monkeypatch.setenv("GIT_COMMITTER_DATE", f"@{fetched_at} +0000")
    sh("fetch", "origin", cwd=clone)  # moves origin/main, so a reflog entry is written
    monkeypatch.delenv("GIT_COMMITTER_DATE")
    git_dir = clone / ".git"
    if (git_dir / "FETCH_HEAD").exists():
        os.utime(git_dir / "FETCH_HEAD", (1_000_000_000, 1_000_000_000))  # older than the reflog
    assert fresh.reflog_time(clone, "refs/remotes/origin/main") == fetched_at
    assert fetched_at != commit_time
    when, source = fresh.last_fetch(clone, "refs/remotes/origin/main")
    assert (when, source) == ("2033-05-18T03:33:20Z", "reflog")


def test_local_branch_upstream_skips_fetch(estate):
    _, clone = estate
    sh("branch", "base", cwd=clone)
    sh("branch", "--set-upstream-to=base", "main", cwd=clone)
    report = fresh.inspect("repo", clone, fetch=True)
    assert report["upstream"] == "base"
    assert report["fetch"] == "skipped: upstream is a local branch"
    assert (report["main_ahead"], report["main_behind"]) == (0, 0)


def test_remote_name_with_slash(estate):
    _, clone = estate
    sh("remote", "rename", "origin", "team/upstream", cwd=clone)
    report = fresh.inspect("repo", clone, fetch=True)
    assert report["fetch"] == "ok"
    assert report["upstream"] == "team/upstream/main"
    assert report["main_behind"] == 1


def test_fetch_is_noninteractive_and_scoped(estate, monkeypatch):
    _, clone = estate
    calls = []
    real = fresh.git

    def spy(repo, *args, **kwargs):
        calls.append((args, kwargs.get("extra_env")))
        return real(repo, *args, **kwargs)

    monkeypatch.delenv("GIT_SSH_COMMAND", raising=False)
    monkeypatch.setattr(fresh, "git", spy)
    fresh.inspect("repo", clone, fetch=True)
    fetch_args, env = next((a, e) for a, e in calls if a[0] == "fetch")
    assert fetch_args == ("fetch", "--quiet", "--no-auto-gc", "--recurse-submodules=no", "origin")
    assert env == {"GIT_SSH_COMMAND": "ssh -o BatchMode=yes"}


def test_timeouts_render_as_unknown(estate, monkeypatch):
    _, clone = estate
    real = fresh.git

    def slow_status(repo, *args, **kwargs):
        if args and args[0] in {"status", "worktree"}:
            raise subprocess.TimeoutExpired(["git", *args], 1)
        return real(repo, *args, **kwargs)

    monkeypatch.setattr(fresh, "git", slow_status)
    report = fresh.inspect("repo", clone, fetch=False)
    assert report["dirty_tracked"] is None and report["worktrees"] is None
    assert report["timeouts"] == ["status", "worktree list --porcelain"]
    text = fresh.render_markdown([report])
    assert "| timeout/unknown | timeout/unknown | timeout/unknown |" in text
    assert "git timed out on status" in text
