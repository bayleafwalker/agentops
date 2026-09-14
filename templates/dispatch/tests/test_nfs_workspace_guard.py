"""nfs-workspace-guard.sh denies edits and git mutations against the legacy
TrueNAS NFS workspace mirror, /mnt/truenas/storage_layer/sealed/projects/<rest>.

A Claude session committed into that stale mirror on 2026-09-14, mistaking it
for the canonical /projects/dev checkout it resembles. This test pipes hook
event JSON into the script on stdin -- exactly how PreToolUse invokes it --
and asserts on the emitted permissionDecision, the same contract
bounded-read-guard.sh and forge-sandbox-guard.sh use.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "templates" / "dispatch" / "hooks" / "nfs-workspace-guard.sh"

PREFIX = "/mnt/truenas/storage_layer/sealed/projects"


def run_hook(event: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    import os

    full_env["PATH"] = os.environ.get("PATH", full_env["PATH"])
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=full_env,
        timeout=10,
    )


def assert_denied(result: subprocess.CompletedProcess) -> dict:
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny"
    assert "nfs-workspace-guard.sh" in hso["permissionDecisionReason"]
    return out


def assert_allowed(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


def test_edit_under_prefix_is_denied():
    result = run_hook({
        "tool_name": "Edit",
        "tool_input": {"file_path": f"{PREFIX}/dev/foo/bar.py"},
    })
    out = assert_denied(result)
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "/projects/dev/foo/bar.py" in reason


def test_edit_on_canonical_path_is_allowed():
    result = run_hook({
        "tool_name": "Edit",
        "tool_input": {"file_path": "/projects/dev/foo/bar.py"},
    })
    assert_allowed(result)


def test_write_under_prefix_is_denied():
    result = run_hook({
        "tool_name": "Write",
        "tool_input": {"file_path": f"{PREFIX}/dev/foo/new.py"},
    })
    assert_denied(result)


def test_multiedit_under_prefix_is_denied():
    result = run_hook({
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": f"{PREFIX}/dev/foo/bar.py", "edits": []},
    })
    assert_denied(result)


def test_notebookedit_under_prefix_is_denied():
    result = run_hook({
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": f"{PREFIX}/dev/foo/nb.ipynb"},
    })
    assert_denied(result)


def test_symlink_into_prefix_is_denied(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(f"{PREFIX}/dev", target_is_directory=True)
    result = run_hook({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(link / "foo.py")},
    })
    assert_denied(result)


def test_git_dash_c_commit_under_prefix_is_denied():
    result = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"git -C {PREFIX}/dev/foo commit -m x"},
    })
    assert_denied(result)


def test_cd_then_git_push_under_prefix_is_denied():
    result = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"cd {PREFIX}/dev/foo && git push"},
    })
    assert_denied(result)


def test_cwd_under_prefix_plain_git_commit_is_denied():
    result = run_hook({
        "tool_name": "Bash",
        "cwd": f"{PREFIX}/dev/foo",
        "tool_input": {"command": "git commit -m x"},
    })
    assert_denied(result)


def test_git_dash_c_status_under_prefix_is_allowed():
    result = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"git -C {PREFIX}/dev/foo status"},
    })
    assert_allowed(result)


@pytest.mark.parametrize("subcmd", ["log", "diff", "show", "fetch", "ls-remote"])
def test_other_read_only_git_under_prefix_is_allowed(subcmd):
    result = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": f"git -C {PREFIX}/dev/foo {subcmd}"},
    })
    assert_allowed(result)


@pytest.mark.parametrize(
    "command",
    [
        "git -C {p}/dev/foo merge main",
        "git -C {p}/dev/foo rebase main",
        "git -C {p}/dev/foo cherry-pick abc123",
        "git -C {p}/dev/foo am patch.diff",
        "git -C {p}/dev/foo reset --hard HEAD~1",
        "git -C {p}/dev/foo checkout -b new-branch",
        "git -C {p}/dev/foo switch -c new-branch",
        "git -C {p}/dev/foo tag v1.0",
        "git -C {p}/dev/foo stash",
    ],
)
def test_other_mutating_git_subcommands_under_prefix_are_denied(command):
    result = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": command.format(p=PREFIX)},
    })
    assert_denied(result)


def test_git_commit_outside_prefix_is_allowed():
    result = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git -C /projects/dev/agentops commit -m x"},
    })
    assert_allowed(result)


def test_override_env_allows_edit_under_prefix():
    result = run_hook(
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": f"{PREFIX}/dev/foo/bar.py"},
        },
        env={"AGENTOPS_ALLOW_NFS_WORKSPACE_WRITES": "1"},
    )
    assert_allowed(result)


def test_override_env_allows_git_commit_under_prefix():
    result = run_hook(
        {
            "tool_name": "Bash",
            "tool_input": {"command": f"git -C {PREFIX}/dev/foo commit -m x"},
        },
        env={"AGENTOPS_ALLOW_NFS_WORKSPACE_WRITES": "1"},
    )
    assert_allowed(result)


def test_malformed_json_is_allowed():
    result = subprocess.run(
        [str(HOOK)],
        input="not json",
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert_allowed(result)


def test_non_bash_non_edit_tool_is_allowed():
    result = run_hook({
        "tool_name": "Read",
        "tool_input": {"file_path": f"{PREFIX}/dev/foo/bar.py"},
    })
    assert_allowed(result)
