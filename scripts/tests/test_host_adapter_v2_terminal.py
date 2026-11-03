"""Terminal evidence is an observation, not owner settlement."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha  # noqa: E402

OBS = {"status": "terminal-observed", "outcome": "succeeded", "terminal_id": "msg_terminal",
       "interval_sha256": "a" * 64, "correlation": "single-input-two-snapshot", "atomicity": "not-established"}


def observation(s):
    prompt = s.load_v2_prompt("repo", "msg_A")
    return {**OBS, "session_id": "ses_A", "prompt_id": prompt["id"], "text_sha256": prompt["sha256"]}


@pytest.fixture
def state(tmp_path):
    s = ha.State(tmp_path)
    s.ingest("repo", [{"message_id": "msg_A", "inbox_seq": 1, "body": {"text": "synthetic"}}], 1, fixture_v2=True)
    s.update("repo", "msg_A", state=ha.S_DECIDED, decision="accepted")
    s.prepare_v2_registration_intent("repo", "msg_A", {"harness_id": "opencode", "harness_build": "2.0.32",
        "model_id": "provider/model", "recipe_id": "fixture", "observed_profile": {}, "idempotency_key": "inbox.msg_A"})
    s.update("repo", "msg_A", state=ha.S_RUN_REGISTERED, run_id="run_A", model_id="provider/model")
    s.prepare_v2_launch_binding("repo", "msg_A", directory="/work/run", title="test",
        permissions=[{"action": "*", "resource": "*", "effect": "deny"}], server_version="2.0.32")
    s.update("repo", "msg_A", state=ha.S_LAUNCHED, session_id="ses_A")
    s.prepare_v2_prompt("repo", "msg_A")
    prompt = s.begin_v2_submission("repo", "msg_A")
    row = s.get("repo", "msg_A")
    s.record_v2_admission("repo", "msg_A", {"status": "observed", "id": prompt["id"],
        "session_id": row["session_id"], "sha256": prompt["sha256"], "sources": ["message"],
        "server_version": "2.0.32", "prompt_binding_sha256": row["prompt_binding_sha256"]})
    yield s
    s.close()


def test_terminal_observation_replays_and_survives_restart(state, tmp_path):
    evidence = state.record_v2_terminal("repo", "msg_A", observation(state))
    assert state.record_v2_terminal("repo", "msg_A", observation(state)) == evidence
    with pytest.raises(ha.PromptIntentError, match="conflict"):
        state.record_v2_terminal("repo", "msg_A", {**observation(state), "outcome": "failed"})
    state.close()
    reopened = ha.State(tmp_path)
    try:
        assert reopened.load_v2_terminal("repo", "msg_A") == evidence
        assert reopened.get("repo", "msg_A")["outcome"] is None
    finally:
        reopened.close()


@pytest.mark.parametrize("field,value", [("status", "unknown"), ("outcome", "other"), ("terminal_id", "bad"),
                                        ("interval_sha256", "bad"), ("correlation", "claimed"),
                                        ("atomicity", "established")])
def test_malformed_observation_is_refused(state, field, value):
    with pytest.raises(ha.PromptIntentError):
        state.record_v2_terminal("repo", "msg_A", {**observation(state), field: value})
    assert state.get("repo", "msg_A")["v2_terminal_evidence"] is None


def test_unknown_admission_and_binding_drift_are_refused(state):
    obs = observation(state)
    state.update("repo", "msg_A", prompt_admission="unknown", prompt_admission_evidence=None)
    with pytest.raises(ha.PromptIntentError):
        state.record_v2_terminal("repo", "msg_A", obs)
    state.update("repo", "msg_A", session_id="ses_other")
    with pytest.raises(ha.PromptIntentError):
        state.record_v2_terminal("repo", "msg_A", obs)


def test_terminal_record_coexists_with_valid_cancel_intent(state):
    state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    evidence = state.record_v2_terminal("repo", "msg_A", observation(state))
    assert evidence["outcome"] == "succeeded" and state.load_v2_terminal("repo", "msg_A") == evidence
    assert state.load_v2_cancellation("repo", "msg_A")["intent"]["reason"] == "cancel-requested"
    with pytest.raises(ha.PromptIntentError, match="terminal evidence"):
        state.begin_v2_cancellation_action("repo", "msg_A", action="interrupt")


@pytest.mark.parametrize("field,value", [("session_id", "ses_other"), ("prompt_id", "msg_other"),
                                        ("text_sha256", "0" * 64)])
def test_cross_wired_terminal_observation_is_refused(state, field, value):
    with pytest.raises(ha.PromptIntentError, match="binding mismatch"):
        state.record_v2_terminal("repo", "msg_A", {**observation(state), field: value})
    assert state.get("repo", "msg_A")["v2_terminal_evidence"] is None


def test_no_new_cancellation_after_terminal_or_partial_evidence(state):
    state.record_v2_terminal("repo", "msg_A", observation(state))
    with pytest.raises(ha.PromptIntentError, match="terminal evidence"):
        state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    state.update("repo", "msg_A", v2_terminal_evidence=None)
    with pytest.raises(ha.PromptIntentError, match="terminal evidence"):
        state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")


def test_partial_and_failed_terminal_write_are_refused(state):
    state.db.execute("""CREATE TRIGGER reject_terminal BEFORE UPDATE OF v2_terminal_evidence ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        state.record_v2_terminal("repo", "msg_A", observation(state))
    assert state.get("repo", "msg_A")["v2_terminal_evidence"] is None
    state.db.execute("DROP TRIGGER reject_terminal")
    state.update("repo", "msg_A", v2_terminal_evidence_sha256="0" * 64)
    with pytest.raises(ha.PromptIntentError):
        state.record_v2_terminal("repo", "msg_A", observation(state))


def test_terminal_cannot_use_input_identity_or_invalid_clock(state):
    prompt = state.load_v2_prompt("repo", "msg_A")
    with pytest.raises(ha.PromptIntentError, match="identity"):
        state.record_v2_terminal("repo", "msg_A", {**observation(state), "terminal_id": prompt["id"]})
    state.clock = lambda: float("nan")
    with pytest.raises(ha.PromptIntentError, match="clock"):
        state.record_v2_terminal("repo", "msg_A", observation(state))
    assert state.get("repo", "msg_A")["v2_terminal_evidence"] is None


def test_terminal_columns_migrate_without_changing_legacy_row(tmp_path):
    s = ha.State(tmp_path)
    s.ingest("repo", [{"message_id": "legacy", "inbox_seq": 1}], 1)
    s.update("repo", "legacy", state=ha.S_LAUNCHED, run_id="run_old", session_id="ses_old", prompt_sent=1)
    before = dict(s.get("repo", "legacy"))
    s.close()
    db = sqlite3.connect(tmp_path / "adapter.sqlite3")
    db.execute("ALTER TABLE messages DROP COLUMN v2_terminal_evidence")
    db.execute("ALTER TABLE messages DROP COLUMN v2_terminal_evidence_sha256")
    db.close()
    reopened = ha.State(tmp_path)
    try:
        assert dict(reopened.get("repo", "legacy")) == before
        with pytest.raises(ha.PromptIntentError):
            reopened.record_v2_terminal("repo", "legacy", {**OBS, "session_id": "ses_old", "prompt_id": "msg_old", "text_sha256": "0" * 64})
    finally:
        reopened.close()
