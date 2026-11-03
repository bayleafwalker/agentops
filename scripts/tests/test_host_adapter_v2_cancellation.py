"""Cancellation request intent is local, durable and never an outcome."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha  # noqa: E402


@pytest.fixture
def state(tmp_path):
    s = ha.State(tmp_path)
    s.ingest("repo", [{"message_id": "msg_A", "inbox_seq": 1, "body": {"text": "synthetic"}}], 1, fixture_v2=True)
    s.update("repo", "msg_A", state=ha.S_RUN_REGISTERED, run_id="run_A", model_id="provider/model")
    s.prepare_v2_launch_binding("repo", "msg_A", directory="/work/run", title="test",
                                permissions=[{"action": "*", "resource": "*", "effect": "deny"}],
                                server_version="2.0.32")
    s.update("repo", "msg_A", state=ha.S_LAUNCHED, session_id="ses_A")
    s.prepare_v2_prompt("repo", "msg_A")
    s.begin_v2_submission("repo", "msg_A")
    yield s
    s.close()


def test_cancellation_actions_are_distinct_one_time_and_restart_safe(state, tmp_path):
    intent = state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    assert state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested") == intent
    assert state.begin_v2_cancellation_action("repo", "msg_A", action="delete") == intent
    with pytest.raises(ha.PromptIntentError):
        state.begin_v2_cancellation_action("repo", "msg_A", action="delete")
    state.close()
    reopened = ha.State(tmp_path)
    try:
        assert reopened.load_v2_cancellation("repo", "msg_A") == {
            "intent": intent, "delete_state": "unknown", "interrupt_state": "not_requested"}
        assert reopened.begin_v2_cancellation_action("repo", "msg_A", action="interrupt") == intent
        with pytest.raises(ha.PromptIntentError):
            reopened.begin_v2_cancellation_action("repo", "msg_A", action="interrupt")
        assert reopened.get("repo", "msg_A")["outcome"] is None
    finally:
        reopened.close()


def test_cancellation_refuses_changed_reason_or_binding(state):
    state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_cancellation("repo", "msg_A", reason="timeout")
    state.update("repo", "msg_A", session_id="ses_other")
    with pytest.raises(ha.PromptIntentError):
        state.load_v2_cancellation("repo", "msg_A")


def test_partial_cancellation_state_is_refused(state):
    state.update("repo", "msg_A", v2_delete_state="unknown")
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")


def test_action_update_failure_rolls_back(state):
    state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    state.db.execute("""CREATE TRIGGER reject_delete BEFORE UPDATE OF v2_delete_state ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        state.begin_v2_cancellation_action("repo", "msg_A", action="delete")
    assert state.load_v2_cancellation("repo", "msg_A")["delete_state"] == "not_requested"


def test_no_cancel_intent_before_prompt_uncertainty(state):
    state.update("repo", "msg_A", prompt_admission="intent")
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    assert state.get("repo", "msg_A")["v2_cancel_intent"] is None


def test_partial_cancel_with_prompt_intent_cannot_begin_submission(state):
    state.update("repo", "msg_A", prompt_admission="intent", v2_delete_state="unknown")
    with pytest.raises(ha.PromptIntentError):
        state.begin_v2_submission("repo", "msg_A")
    assert state.get("repo", "msg_A")["prompt_admission"] == "intent"


@pytest.mark.parametrize("field,value", [("session_id", "ses_other"), ("prompt_id", "msg_" + "0" * 32),
                                        ("v2_launch_binding_sha256", "0" * 64)])
def test_changed_binding_cannot_authorize_cancellation_action(state, field, value):
    state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    state.update("repo", "msg_A", **{field: value})
    with pytest.raises(ha.PromptIntentError):
        state.begin_v2_cancellation_action("repo", "msg_A", action="interrupt")
    with pytest.raises(ha.PromptIntentError):
        state.load_v2_cancellation("repo", "msg_A")


def test_admission_reconciliation_preserves_cancellation_intent(state):
    intent = state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    prompt = state.load_v2_prompt("repo", "msg_A")
    row = state.get("repo", "msg_A")
    state.record_v2_admission("repo", "msg_A", {"status": "observed", "id": prompt["id"],
        "session_id": row["session_id"], "sha256": prompt["sha256"], "sources": ["message"],
        "server_version": "2.0.32", "prompt_binding_sha256": row["prompt_binding_sha256"]})
    assert state.load_v2_cancellation("repo", "msg_A")["intent"] == intent
    assert state.load_v2_prompt("repo", "msg_A")["admission"] == "admitted"


def test_initial_cancellation_failure_rolls_back(state):
    state.db.execute("""CREATE TRIGGER reject_cancel BEFORE UPDATE OF v2_cancel_intent ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        state.prepare_v2_cancellation("repo", "msg_A", reason="cancel-requested")
    row = state.get("repo", "msg_A")
    assert all(row[k] is None for k in ("v2_cancel_intent", "v2_cancel_intent_sha256", "v2_delete_state", "v2_interrupt_state"))


def test_v1_row_remains_untouched(tmp_path):
    s = ha.State(tmp_path)
    try:
        s.ingest("repo", [{"message_id": "legacy", "inbox_seq": 1}], 1)
        s.update("repo", "legacy", state=ha.S_LAUNCHED, run_id="run_old", session_id="ses_old", prompt_sent=1)
        before = dict(s.get("repo", "legacy"))
        with pytest.raises(ha.PromptIntentError):
            s.prepare_v2_cancellation("repo", "legacy", reason="cancel-requested")
        assert dict(s.get("repo", "legacy")) == before
    finally:
        s.close()


def test_prior_schema_migration_preserves_legacy_row(tmp_path):
    s = ha.State(tmp_path)
    s.ingest("repo", [{"message_id": "legacy", "inbox_seq": 1}], 1)
    s.update("repo", "legacy", state=ha.S_LAUNCHED, run_id="run_old", session_id="ses_old", prompt_sent=1)
    before = dict(s.get("repo", "legacy"))
    s.close()
    db = sqlite3.connect(tmp_path / "adapter.sqlite3")
    for field in ("v2_cancel_intent", "v2_cancel_intent_sha256", "v2_delete_state", "v2_interrupt_state"):
        db.execute(f"ALTER TABLE messages DROP COLUMN {field}")
    db.close()
    reopened = ha.State(tmp_path)
    try:
        assert dict(reopened.get("repo", "legacy")) == before
    finally:
        reopened.close()
