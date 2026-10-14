"""Oracle for the Claude Code observation hooks.

The hooks sit on the user's critical path (every session start, every prompt), so the
properties are: they never fail the session, they register once per host, and
`attended` is reported at most once per five minutes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import claude_agent_hooks as hooks  # noqa: E402

ROOT = SCRIPTS.parent


class Owner:
    def __init__(self, fail: bool = False) -> None:
        self.registered, self.observed, self.fail = [], [], fail

    def agent_register(self, repo, **kw):
        if self.fail:
            raise RuntimeError("down")
        self.registered.append((repo, kw))

    def agent_observe(self, repo, **kw):
        if self.fail:
            raise RuntimeError("down")
        self.observed.append((repo, kw))


def test_session_start_registers_once_per_host_with_a_persisted_instance(tmp_path):
    o = Owner()
    hooks.session_start(o, tmp_path, "2.1.299", ["agentops"])
    hooks.session_start(o, tmp_path, "2.1.299", ["agentops"])
    assert len(o.registered) == 1
    repo, kw = o.registered[0]
    decl = kw["declaration"]
    assert decl["harness"] == {"name": "claude-code", "version": "2.1.299"}
    assert decl["interactivity"] == "interactive" and decl["host_class"] == "workstation"
    saved = json.loads(next(tmp_path.glob("claude-code.*.json")).read_text())
    assert saved["instance_id"] == kw["instance_id"] and kw["instance_id"].startswith("ins_")
    hooks.session_start(o, tmp_path, "2.1.300", ["agentops"])  # a new version is a new declaration revision
    assert len(o.registered) == 2 and o.registered[1][1]["instance_id"] == kw["instance_id"]


def test_prompt_submit_reports_observed_and_attended_for_900s_and_is_rate_limited(tmp_path):
    o = Owner()
    hooks.session_start(o, tmp_path, "v", ["agentops"])
    t0 = time.time()
    assert hooks.prompt_submit(o, tmp_path, ["agentops"], now=t0) is True
    assert [(kw["fact"], kw["valid_for_seconds"]) for _, kw in o.observed] == [("observed", 900), ("attended", 900)]
    assert hooks.prompt_submit(o, tmp_path, ["agentops"], now=t0 + 299) is False
    assert len(o.observed) == 2
    assert hooks.prompt_submit(o, tmp_path, ["agentops"], now=t0 + 301) is True
    assert len(o.observed) == 4


def test_prompt_submit_without_registration_does_nothing(tmp_path):
    o = Owner()
    assert hooks.prompt_submit(o, tmp_path, ["agentops"]) is False and o.observed == []


def test_owner_failure_still_consumes_the_rate_limit_stamp(tmp_path):
    hooks.session_start(Owner(), tmp_path, "v", ["agentops"])
    t0 = time.time()
    with pytest.raises(RuntimeError):
        hooks.prompt_submit(Owner(fail=True), tmp_path, ["agentops"], now=t0)
    assert hooks.prompt_submit(Owner(), tmp_path, ["agentops"], now=t0 + 10) is False


@pytest.mark.parametrize("script,arg", [("agent-directory-session-start.sh", None),
                                        ("agent-directory-prompt-submit.sh", None)])
def test_wrapper_scripts_fail_open_with_exit_zero_and_no_output(tmp_path, script, arg):
    env = dict(os.environ, AGENTOPS_VUORO_PROFILE=str(tmp_path / "missing.json"),
               AGENTOPS_AGENT_INSTANCES_DIR=str(tmp_path / "inst"))
    p = subprocess.run(["bash", str(ROOT / "hooks" / script)], input="{}", capture_output=True, text=True,
                       env=env, timeout=10)
    assert (p.returncode, p.stdout, p.stderr) == (0, "", "")
    assert not (tmp_path / "inst").exists()


def test_main_with_an_unreachable_owner_exits_zero_within_the_deadline(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text("{not json")  # vuoro_client absent or profile invalid: either way fail open
    env = dict(os.environ, AGENTOPS_VUORO_PROFILE=str(profile), AGENTOPS_AGENT_INSTANCES_DIR=str(tmp_path / "i"))
    t = time.time()
    p = subprocess.run([sys.executable, str(SCRIPTS / "claude_agent_hooks.py"), "session-start"],
                       input="{}", capture_output=True, text=True, env=env, timeout=10)
    assert p.returncode == 0 and p.stdout == "" and time.time() - t < 5


def test_concurrent_session_starts_converge_on_one_instance_id(tmp_path, monkeypatch):
    first = hooks.ha.new_ulid("ins")
    other = hooks.ha.new_ulid("ins")
    path, _ = hooks._paths(tmp_path)

    def racing_mint(prefix):
        # another SessionStart wins the race after this one decided to mint
        path.write_text(json.dumps({"instance_id": other, "registered_version": None, "registered_repos": []}))
        return first

    monkeypatch.setattr(hooks.ha, "new_ulid", racing_mint)
    record, created = hooks.load_or_mint(tmp_path)
    assert record["instance_id"] == other and created is False
    assert json.loads(path.read_text())["instance_id"] == other
    assert [p.name for p in tmp_path.iterdir()] == [path.name]  # no stray tmp files


def test_the_deadline_also_covers_a_stdin_that_never_closes(tmp_path):
    env = dict(os.environ, AGENTOPS_VUORO_PROFILE=str(tmp_path / "missing.json"),
               AGENTOPS_AGENT_INSTANCES_DIR=str(tmp_path / "i"))
    t = time.time()
    p = subprocess.Popen([sys.executable, str(SCRIPTS / "claude_agent_hooks.py"), "prompt-submit"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        rc = p.wait(timeout=8)
    finally:
        p.kill()
    assert rc == 0 and time.time() - t < 6
