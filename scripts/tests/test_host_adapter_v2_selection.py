"""Synthetic v2 selection never upgrades an existing legacy inbox record."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha  # noqa: E402

MESSAGE = {"message_id": "msg_A", "inbox_seq": 1, "body": {"text": "synthetic"}}
ARGS = {"harness_id": "opencode", "harness_build": "2.0.32", "model_id": "provider/model",
        "recipe_id": "inbox-continue-v1", "observed_profile": {"sandbox": "synthetic"},
        "idempotency_key": "inbox.msg_A"}


@pytest.fixture
def state(tmp_path):
    s = ha.State(tmp_path)
    yield s
    s.close()


@pytest.mark.parametrize("phase", [ha.S_RECEIVED, ha.S_DECIDED, ha.S_RUN_REGISTERED])
def test_existing_legacy_records_are_never_upgraded(state, phase):
    state.ingest("repo", [MESSAGE], 1)
    state.update("repo", "msg_A", state=phase)
    state.ingest("repo", [MESSAGE], 1, fixture_v2=True)
    assert state.get("repo", "msg_A")["execution_selection"] is None
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_registration_intent("repo", "msg_A", ARGS)


def test_selection_insert_and_cursor_roll_back_together(state):
    state.db.execute("""CREATE TRIGGER reject_selection BEFORE INSERT ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        state.ingest("repo", [MESSAGE], 1, fixture_v2=True)
    assert state.get("repo", "msg_A") is None and state.cursor("repo") == 0


def test_registration_intent_is_immutable_and_survives_restart(state, tmp_path):
    state.ingest("repo", [MESSAGE], 1, fixture_v2=True)
    state.update("repo", "msg_A", state=ha.S_DECIDED, decision="accepted")
    snapshot = state.prepare_v2_registration_intent("repo", "msg_A", ARGS)
    assert state.prepare_v2_registration_intent("repo", "msg_A", ARGS) == snapshot
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_registration_intent("repo", "msg_A", {**ARGS, "model_id": "provider/other"})
    state.close()
    reopened = ha.State(tmp_path)
    try:
        assert reopened.load_v2_registration_intent("repo", "msg_A") == snapshot
        reopened.update("repo", "msg_A", state=ha.S_RUN_REGISTERED, run_id="run_A", model_id="provider/other")
        with pytest.raises(ha.PromptIntentError, match="registered model"):
            reopened.load_v2_registration_intent("repo", "msg_A")
    finally:
        reopened.close()


@pytest.mark.parametrize("change", [{"harness_build": "1.19.0"}, {"model_id": "missing"},
                                   {"idempotency_key": "different"}, {"harness_id": "other"}])
def test_unqualified_registration_is_not_frozen(state, change):
    state.ingest("repo", [MESSAGE], 1, fixture_v2=True)
    state.update("repo", "msg_A", state=ha.S_DECIDED, decision="accepted")
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_registration_intent("repo", "msg_A", {**ARGS, **change})
    assert state.get("repo", "msg_A")["v2_registration_intent"] is None


def test_malformed_or_partial_selection_and_intent_are_refused(state):
    state.ingest("repo", [MESSAGE], 1, fixture_v2=True)
    state.update("repo", "msg_A", state=ha.S_DECIDED, decision="accepted", execution_selection="{}")
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_registration_intent("repo", "msg_A", ARGS)
    state.update("repo", "msg_A", execution_selection=ha.canonical({"schema": "adapter-execution-selection/v1",
                 "api": "opencode-v2", "source": "synthetic-fixture"}), v2_registration_intent="{}")
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_registration_intent("repo", "msg_A", ARGS)
    with pytest.raises(ha.PromptIntentError):
        state.load_v2_registration_intent("repo", "msg_A")


def test_registration_intent_write_failure_rolls_back(state):
    state.ingest("repo", [MESSAGE], 1, fixture_v2=True)
    state.update("repo", "msg_A", state=ha.S_DECIDED, decision="accepted")
    state.db.execute("""CREATE TRIGGER reject_registration BEFORE UPDATE OF v2_registration_intent ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        state.prepare_v2_registration_intent("repo", "msg_A", ARGS)
    row = state.get("repo", "msg_A")
    assert row["v2_registration_intent"] is None and row["v2_registration_intent_sha256"] is None


@pytest.mark.parametrize("field", ["run_id", "model_id", "session_id", "harness_api", "v2_launch_binding",
                                   "v2_launch_binding_sha256", "prompt_id", "prompt_nonce", "prompt_sha256",
                                   "prompt_binding_sha256", "prompt_admission", "prompt_admission_evidence",
                                   "prompt_launch_binding_sha256"])
def test_downstream_partial_state_cannot_be_registered(state, field):
    state.ingest("repo", [MESSAGE], 1, fixture_v2=True)
    state.update("repo", "msg_A", state=ha.S_DECIDED, decision="accepted", **{field: "partial"})
    with pytest.raises(ha.PromptIntentError):
        state.prepare_v2_registration_intent("repo", "msg_A", ARGS)
    assert state.get("repo", "msg_A")["v2_registration_intent"] is None


def test_registration_predecessor_must_match_envelope(state):
    state.ingest("repo", [{**MESSAGE, "context": {"predecessor_run_id": "run_old"}}], 1, fixture_v2=True)
    state.update("repo", "msg_A", state=ha.S_DECIDED, decision="accepted")
    with pytest.raises(ha.PromptIntentError, match="predecessor"):
        state.prepare_v2_registration_intent("repo", "msg_A", ARGS)
    snapshot = state.prepare_v2_registration_intent("repo", "msg_A", {**ARGS, "predecessor_run_id": "run_old"})
    assert snapshot["arguments"]["predecessor_run_id"] == "run_old"
