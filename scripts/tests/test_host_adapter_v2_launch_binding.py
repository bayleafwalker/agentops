"""Dormant launch binding is frozen before any future server write."""
import json
import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha  # noqa: E402

RULES = [{"action": "*", "resource": "*", "effect": "deny"},
         {"action": "shell", "resource": "sprintctl run context *", "effect": "allow"}]
ARGS = {"directory": "/work/run", "title": "vuoro-msg:msg_A", "permissions": RULES, "server_version": "2.0.32"}


@pytest.fixture
def state(tmp_path):
    s = ha.State(tmp_path)
    s.ingest("repo", [{"message_id": "msg_A", "inbox_seq": 1, "body": {"text": "synthetic"}}], 1)
    s.update("repo", "msg_A", state=ha.S_RUN_REGISTERED, run_id="run_A", model_id="provider/model")
    yield s
    s.close()


def test_binding_is_stable_and_survives_restart(state, tmp_path):
    binding = state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    assert state.prepare_v2_launch_binding("repo", "msg_A", **ARGS) == binding
    assert state.load_v2_launch_binding("repo", "msg_A") == binding
    state.close()
    reopened = ha.State(tmp_path)
    try:
        assert reopened.load_v2_launch_binding("repo", "msg_A") == binding
        reopened.update("repo", "msg_A", state=ha.S_LAUNCHED, session_id="ses_A")
        assert reopened.load_v2_launch_binding("repo", "msg_A") == binding
    finally:
        reopened.close()


@pytest.mark.parametrize("field,value", [("directory", "/other"), ("title", "other"),
                                        ("permissions", list(reversed(RULES))), ("server_version", "2.0.33")])
def test_changed_binding_is_refused(state, field, value):
    state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_launch_binding("repo", "msg_A", **{**ARGS, field: value})
    assert state.load_v2_launch_binding("repo", "msg_A")["directory"] == "/work/run"


@pytest.mark.parametrize("field,value", [("state", ha.S_LAUNCHED), ("run_id", None),
                                        ("model_id", "invalid"), ("session_id", "ses_A"),
                                        ("harness_api", "opencode-v1"), ("prompt_sent", 1)])
def test_requires_unlaunched_registered_v2_attempt(state, field, value):
    state.update("repo", "msg_A", **{field: value})
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    assert state.get("repo", "msg_A")["v2_launch_binding"] is None


def test_partial_corrupt_and_changed_run_are_refused(state):
    state.update("repo", "msg_A", harness_api="opencode-v2")
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    state.update("repo", "msg_A", harness_api=None)
    state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    state.update("repo", "msg_A", run_id="run_other")
    with pytest.raises(ha.PromptIntentError):
        state.load_v2_launch_binding("repo", "msg_A")
    state.update("repo", "msg_A", run_id="run_A", v2_launch_binding_sha256="0" * 64)
    with pytest.raises(ha.PromptIntentError):
        state.load_v2_launch_binding("repo", "msg_A")


@pytest.mark.parametrize("field", ["prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256",
                                   "prompt_admission", "prompt_admission_evidence"])
def test_partial_prompt_state_cannot_be_rebound(state, field):
    state.update("repo", "msg_A", **{field: "partial"})
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    assert state.get("repo", "msg_A")["v2_launch_binding"] is None


def test_load_rejects_structurally_invalid_model_even_if_rehashed(state):
    binding = state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    binding["model_id"] = "invalid"
    raw = ha.canonical(binding)
    state.update("repo", "msg_A", model_id="invalid", v2_launch_binding=raw,
                 v2_launch_binding_sha256=hashlib.sha256(raw.encode()).hexdigest())
    with pytest.raises(ha.PromptIntentError):
        state.load_v2_launch_binding("repo", "msg_A")


def test_transaction_failure_leaves_no_partial_binding(state):
    state.db.execute("""CREATE TRIGGER reject_binding BEFORE UPDATE OF v2_launch_binding ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        state.prepare_v2_launch_binding("repo", "msg_A", **ARGS)
    row = state.get("repo", "msg_A")
    assert row["harness_api"] is None and row["v2_launch_binding"] is None and row["v2_launch_binding_sha256"] is None
