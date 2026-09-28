"""Oracle for agentops#2545: tell an inactive repository from a capture failure.

Item 2545 (scope moved from #2533, which delivered ``scripts/audit_freshness.py``
but not the capture-gap repair): for each stale audit store, *distinguish an
inactive repository from a capture failure by comparing against git activity*,
fix capture for every active repository, and run ``audit_freshness.py`` on a
schedule the estate controls. Acceptance: ``audit_freshness.py`` reports every
active repository fresh within 48h, and the scheduled run exits 1 on a
deliberately stale fixture store.

The #2533 contract (``test_audit_freshness.py``) stays in force unchanged: without
the new flag every stale or absent store is an alert. This oracle adds one
opt-in mode, exercised as a black box:

    python scripts/audit_freshness.py --root DIR [--now ISO8601Z]
                                      --window-seconds N --git-activity

With ``--git-activity``, each audit store ``_artifacts/<scope>/audit`` is paired
with the git work tree ``<root>/<scope>`` (in these fixtures the store sits
inside that work tree, so resolving it by path or by ``git rev-parse
--show-toplevel`` from the store gives the same repository). The repository is
*active* when its newest commit is no older than ``--window-seconds`` measured
from ``--now`` (not from the wall clock), and *inactive* otherwise. Then:

* stale store + active repository -> a **capture failure**: an alert (exit 1),
  with an output line naming the scope and containing the word ``capture``;
* stale store + inactive repository -> **inactive**, not an alert: an output
  line naming the scope contains the word ``inactive``, and on its own it
  leaves the exit status 0;
* stale store with no git repository to compare against -> still an alert
  (exit 1): the deliberately stale fixture store the scheduled run must catch.
  Silence without evidence of inactivity stays a failed invariant (#2533, Q6);
* the per-store gauge ``agentops_audit_last_authoritative_event_age_seconds``
  is still printed for every store, inactive ones included.

Activity must come from git history, not file-system times: every fixture
repository here was created seconds ago, so a directory or file mtime would
call all of them active.

``--root DIR --window-seconds 172800 --git-activity`` is the argument set the
scheduled run is expected to use (48h, as in the acceptance text), so the
fixture-store check below is the scheduled run's behaviour on a stale store.
That the schedule itself exists, and that the live estate reports every active
repository fresh, are environment facts outside this suite (see the item's
oracle note).

Every check fails at this revision because ``audit_freshness.py`` has no
``--git-activity`` mode (argparse exits 2 on the unknown flag).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

UTC = timezone.utc
SCRIPT = Path(__file__).resolve().parents[1] / "audit_freshness.py"
METRIC = "agentops_audit_last_authoritative_event_age_seconds"
WINDOW = 172800  # 48h: the acceptance window
# Fixed and well in the past, so an implementation that measures activity from the
# wall clock instead of --now calls every fixture repository inactive and fails.
NOW = datetime(2025, 3, 1, 12, 0, 0, tzinfo=UTC)


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def event(ts: datetime) -> str:
    stamp = iso(ts)
    return json.dumps(
        {
            "id": f"ad:{stamp}",
            "ts": stamp,
            "created_at": stamp,
            "type": "dispatch.exit",
            "source": "claude-hook",
            "summary": "oracle fixture event",
            "payload": {},
        },
        sort_keys=True,
    )


@pytest.fixture
def git_env(tmp_path, monkeypatch):
    """Hermetic git: no host hooks (gitleaks via core.hooksPath), no signing, no system config."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[init]\n\tdefaultBranch = main\n[core]\n\thooksPath = /dev/null\n"
        "[commit]\n\tgpgsign = false\n"
        "[user]\n\tname = Oracle Fixture\n\temail = oracle@example.invalid\n"
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "estate"
    root.mkdir()
    # Keep git from discovering any repository above the fixture root.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    return root


def make_repo(root: Path, scope: str, last_commit: datetime) -> Path:
    """A git work tree ``<root>/<scope>`` whose newest commit is ``last_commit``."""
    repo = root / scope
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text(f"{scope}\n")
    (repo / ".gitignore").write_text("_artifacts/*/audit*/\n")
    subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=repo, check=True)
    stamp = iso(last_commit)
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True, env=env)
    return repo


def write_store(base: Path, scope: str, newest: datetime) -> Path:
    """Shard ``<base>/_artifacts/<scope>/audit/events-<day>.ndjson`` whose newest event is ``newest``."""
    path = base / "_artifacts" / scope / "audit" / f"events-{newest:%Y-%m-%d}.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(event(newest - timedelta(hours=2)) + "\n" + event(newest) + "\n")
    return path


def run(root: Path, *, activity: bool = True) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(SCRIPT), "--root", str(root), "--now", iso(NOW),
            "--window-seconds", str(WINDOW)]
    if activity:
        argv.append("--git-activity")
    return subprocess.run(argv, capture_output=True, text=True, timeout=120)


def gauges(stdout: str) -> dict[str, float]:
    pat = re.compile(rf"^{re.escape(METRIC)}\{{(?P<labels>[^}}]*)\}}\s+(?P<val>-?\d+(?:\.\d+)?)\s*$")
    out: dict[str, float] = {}
    for line in stdout.splitlines():
        m = pat.match(line.strip())
        if m:
            rm = re.search(r'repo="([^"]+)"', m.group("labels"))
            if rm:
                out[rm.group(1)] = float(m.group("val"))
    return out


def lines_naming(proc: subprocess.CompletedProcess, scope: str) -> list[str]:
    """Non-gauge output lines (stdout or stderr) that name ``scope`` as a whole word."""
    word = re.compile(rf"(?<![\w-]){re.escape(scope)}(?![\w-])")
    return [
        line for line in (proc.stdout + "\n" + proc.stderr).splitlines()
        if word.search(line) and not line.strip().startswith(METRIC)
    ]


def detail(proc: subprocess.CompletedProcess) -> str:
    return f"exit={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


def test_active_repo_with_stale_store_is_a_capture_failure(git_env):
    # busy committed an hour ago; its store went quiet five days ago.
    repo = make_repo(git_env, "busy", NOW - timedelta(hours=1))
    write_store(repo, "busy", NOW - timedelta(days=5))

    proc = run(git_env)

    assert proc.returncode == 1, detail(proc)
    named = lines_naming(proc, "busy")
    assert any("capture" in line.lower() for line in named), (
        "an active repository with a stale store must be reported as a capture failure\n"
        + detail(proc))
    assert "busy" in gauges(proc.stdout), detail(proc)


def test_inactive_repo_with_stale_store_is_reported_inactive_not_an_alert(git_env):
    # quiet's last commit is 40 days old and its store is 30 days old: nothing to capture.
    repo = make_repo(git_env, "quiet", NOW - timedelta(days=40))
    write_store(repo, "quiet", NOW - timedelta(days=30))

    proc = run(git_env)

    assert proc.returncode == 0, (
        "a stale store whose repository had no commits within the window is inactive, "
        "not a capture failure\n" + detail(proc))
    named = lines_naming(proc, "quiet")
    assert any("inactive" in line.lower() for line in named), detail(proc)
    assert gauges(proc.stdout).get("quiet", 0) >= 29 * 86400, (
        "the gauge is still emitted for an inactive store\n" + detail(proc))


def test_activity_is_read_from_git_history_not_mtime(git_env):
    # Both repositories were created seconds ago; only their commit dates differ.
    busy = make_repo(git_env, "busy", NOW - timedelta(hours=3))
    quiet = make_repo(git_env, "quiet", NOW - timedelta(days=40))
    write_store(busy, "busy", NOW - timedelta(days=4))
    write_store(quiet, "quiet", NOW - timedelta(days=30))

    proc = run(git_env)

    assert proc.returncode == 1, detail(proc)
    assert any("capture" in line.lower() for line in lines_naming(proc, "busy")), detail(proc)
    assert any("inactive" in line.lower() for line in lines_naming(proc, "quiet")), detail(proc)


def test_fresh_active_repo_and_inactive_repo_exit_zero(git_env):
    fresh = make_repo(git_env, "fresh", NOW - timedelta(hours=1))
    quiet = make_repo(git_env, "quiet", NOW - timedelta(days=40))
    write_store(fresh, "fresh", NOW - timedelta(minutes=10))
    write_store(quiet, "quiet", NOW - timedelta(days=30))

    proc = run(git_env)

    assert proc.returncode == 0, detail(proc)
    g = gauges(proc.stdout)
    assert set(g) == {"fresh", "quiet"}, detail(proc)
    assert g["fresh"] < WINDOW, detail(proc)
    assert not any("capture" in line.lower() for line in lines_naming(proc, "fresh")), detail(proc)


def test_scheduled_run_exits_1_on_deliberately_stale_fixture_store(git_env):
    # The scheduled run's argument set against a stale store with no repository to
    # excuse it, next to a healthy active repository: the stale fixture store must alert.
    fresh = make_repo(git_env, "fresh", NOW - timedelta(hours=1))
    write_store(fresh, "fresh", NOW - timedelta(minutes=10))
    write_store(git_env, "stale-fixture", NOW - timedelta(days=5))

    proc = run(git_env)

    assert proc.returncode == 1, (
        "a stale store with no git activity to compare against must still alert\n"
        + detail(proc))
    assert lines_naming(proc, "stale-fixture"), detail(proc)
    assert not any("inactive" in line.lower() for line in lines_naming(proc, "stale-fixture")), (
        "a store with no repository is not evidence of inactivity\n" + detail(proc))


def test_activity_window_boundary_follows_window_seconds(git_env):
    # Newest commit 47h before --now is inside the 48h window (active); 49h is outside.
    inside = make_repo(git_env, "inside", NOW - timedelta(hours=47))
    outside = make_repo(git_env, "outside", NOW - timedelta(hours=49))
    write_store(inside, "inside", NOW - timedelta(days=3))
    write_store(outside, "outside", NOW - timedelta(days=3))

    proc = run(git_env)

    assert proc.returncode == 1, detail(proc)
    assert any("capture" in line.lower() for line in lines_naming(proc, "inside")), detail(proc)
    assert any("inactive" in line.lower() for line in lines_naming(proc, "outside")), detail(proc)
