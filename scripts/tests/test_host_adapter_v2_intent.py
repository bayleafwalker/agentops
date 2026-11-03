"""V2 prompt preparation is durable and dormant until its caller is qualified."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha  # noqa: E402


@pytest.fixture
def prepared_state(tmp_path):
    state = ha.State(tmp_path)
    envelope = {"message_id": "msg_A", "inbox_seq": 1, "body": {"text": "synthetic"}}
    state.ingest("repo", [envelope], 1)
    state.update("repo", "msg_A", state=ha.S_LAUNCHED, run_id="run_A", session_id="ses_A",
                 model_id="opencode-go/model", harness_api="opencode-v2")
    yield state
    state.close()


def test_prompt_intent_is_atomic_stable_and_survives_restart(prepared_state, tmp_path):
    first = prepared_state.prepare_v2_prompt("repo", "msg_A")
    second = prepared_state.prepare_v2_prompt("repo", "msg_A")
    assert first == second
    assert first["id"].startswith("msg_")
    assert first["admission"] == "intent"
    assert hashlib.sha256(first["text"].encode()).hexdigest() == first["sha256"]
    prepared_state.close()
    reopened = ha.State(tmp_path)
    try:
        assert reopened.prepare_v2_prompt("repo", "msg_A") == first
    finally:
        reopened.close()
    # The fixture closes the original state once more.


@pytest.mark.parametrize("field,value", [
    ("harness_api", None), ("harness_api", "opencode-v1"),
    ("state", ha.S_RECEIVED), ("session_id", None), ("run_id", None),
    ("model_id", None), ("model_id", "invalid-model"), ("model_id", "provider/ model"),
    ("prompt_sent", 1), ("closed", 1),
])
def test_requires_explicit_launched_v2_binding(prepared_state, field, value):
    prepared_state.update("repo", "msg_A", **{field: value})
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    row = prepared_state.get("repo", "msg_A")
    assert all(row[key] is None for key in ("prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256", "prompt_admission"))


def test_partial_and_changed_intent_is_refused(prepared_state):
    prepared_state.update("repo", "msg_A", prompt_id="msg_" + "a" * 32)
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")


def test_changed_binding_or_prompt_digest_is_refused(prepared_state):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.update("repo", "msg_A", session_id="ses_other")
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.update("repo", "msg_A", session_id="ses_A", prompt_sha256="0" * 64)
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")


def test_replacing_prompt_id_with_another_valid_id_is_refused(prepared_state):
    intent = prepared_state.prepare_v2_prompt("repo", "msg_A")
    replacement = "msg_" + ("0" * 32 if intent["id"] != "msg_" + "0" * 32 else "1" * 32)
    prepared_state.update("repo", "msg_A", prompt_id=replacement)
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")


def test_changed_envelope_and_nonintent_admission_are_refused(prepared_state):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    original = prepared_state.get("repo", "msg_A")["envelope"]
    envelope = {"message_id": "msg_A", "inbox_seq": 1, "body": {"text": "changed"}}
    prepared_state.db.execute("UPDATE messages SET envelope=? WHERE repo_id=? AND message_id=?",
                              (json.dumps(envelope), "repo", "msg_A"))
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.db.execute("UPDATE messages SET envelope=? WHERE repo_id=? AND message_id=?",
                              (original, "repo", "msg_A"))
    prepared_state.update("repo", "msg_A", prompt_admission="admitted")
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")


def test_replacing_nonce_with_another_valid_nonce_is_refused(prepared_state):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    original = prepared_state.get("repo", "msg_A")["prompt_nonce"]
    replacement = "0" * 32 if original != "0" * 32 else "1" * 32
    prepared_state.update("repo", "msg_A", prompt_nonce=replacement)
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")


def test_failure_before_persist_rolls_back_all_intent_fields(prepared_state, monkeypatch):
    def fail(*args):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(ha, "build_prompt", fail)
    with pytest.raises(RuntimeError, match="injected"):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    row = prepared_state.get("repo", "msg_A")
    assert all(row[key] is None for key in ("prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256", "prompt_admission"))


def test_database_rejection_does_not_leave_partial_intent(prepared_state):
    prepared_state.db.execute("""CREATE TRIGGER reject_intent BEFORE UPDATE OF prompt_id ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected rejection"):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    row = prepared_state.get("repo", "msg_A")
    assert all(row[key] is None for key in ("prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256", "prompt_admission"))


def test_existing_legacy_rows_migrate_without_inventing_intent(tmp_path):
    db = sqlite3.connect(tmp_path / "adapter.sqlite3")
    db.executescript("""
        CREATE TABLE messages (repo_id TEXT NOT NULL, message_id TEXT NOT NULL, inbox_seq INTEGER NOT NULL,
          envelope TEXT NOT NULL, state TEXT NOT NULL, decision TEXT, reason_code TEXT, reason_text TEXT,
          run_id TEXT, session_id TEXT, prompt_sent INTEGER NOT NULL DEFAULT 0,
          abort_requested INTEGER NOT NULL DEFAULT 0, outcome TEXT, summary TEXT, evidence TEXT, detail TEXT,
          ambiguous_sent INTEGER NOT NULL DEFAULT 0, abort_sent INTEGER NOT NULL DEFAULT 0,
          idle_polls INTEGER NOT NULL DEFAULT 0, closed INTEGER NOT NULL DEFAULT 0, last_error TEXT,
          created_at REAL NOT NULL, updated_at REAL NOT NULL, PRIMARY KEY(repo_id,message_id));
        INSERT INTO messages(repo_id,message_id,inbox_seq,envelope,state,run_id,session_id,prompt_sent,created_at,updated_at)
          VALUES('repo','old',1,'{}','launched','run_old','ses_old',1,1,1);
    """)
    db.close()
    state = ha.State(tmp_path)
    try:
        row = state.get("repo", "old")
        assert row["prompt_sent"] == 1 and row["run_id"] == "run_old"
        assert all(row[key] is None for key in ("harness_api", "prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256", "prompt_admission"))
        with pytest.raises(ha.PromptIntentError):
            state.prepare_v2_prompt("repo", "old")
    finally:
        state.close()
    read_only = ha.State(tmp_path, read_only=True)
    try:
        assert ha._status_rows(read_only)[0]["message_id"] == "old"
    finally:
        read_only.close()
