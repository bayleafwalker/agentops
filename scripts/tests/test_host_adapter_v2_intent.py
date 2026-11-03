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
    state.update("repo", "msg_A", state=ha.S_RUN_REGISTERED, run_id="run_A", model_id="opencode-go/model")
    state.prepare_v2_launch_binding("repo", "msg_A", directory="/work/run", title="test",
                                    permissions=[{"action": "*", "resource": "*", "effect": "deny"}],
                                    server_version="2.0.32")
    state.update("repo", "msg_A", state=ha.S_LAUNCHED, session_id="ses_A")
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


def test_begin_is_one_time_and_unknown_survives_restart(prepared_state, tmp_path):
    with pytest.raises(ha.PromptIntentError, match="missing"):
        prepared_state.load_v2_prompt("repo", "msg_A")
    with pytest.raises(ha.PromptIntentError, match="missing"):
        prepared_state.begin_v2_submission("repo", "msg_A")
    intent = prepared_state.prepare_v2_prompt("repo", "msg_A")
    started = prepared_state.begin_v2_submission("repo", "msg_A")
    assert started == {**intent, "admission": "unknown"}
    with pytest.raises(ha.PromptIntentError):
        prepared_state.begin_v2_submission("repo", "msg_A")
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.close()
    reopened = ha.State(tmp_path)
    try:
        assert reopened.load_v2_prompt("repo", "msg_A") == started
        with pytest.raises(ha.PromptIntentError):
            reopened.begin_v2_submission("repo", "msg_A")
    finally:
        reopened.close()


def test_failed_begin_rolls_back_before_authorizing_submission(prepared_state):
    intent = prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.db.execute("""CREATE TRIGGER reject_begin BEFORE UPDATE OF prompt_admission ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected rejection"):
        prepared_state.begin_v2_submission("repo", "msg_A")
    assert prepared_state.load_v2_prompt("repo", "msg_A") == intent


def observation(state, sources=None):
    prompt = state.load_v2_prompt("repo", "msg_A")
    row = state.get("repo", "msg_A")
    return {"status": "observed", "id": prompt["id"], "session_id": row["session_id"],
            "sha256": prompt["sha256"], "sources": sources or ["inbox"], "server_version": "2.0.32",
            "prompt_binding_sha256": row["prompt_binding_sha256"]}


def test_admission_checkpoint_merges_sources_and_survives_restart(prepared_state, tmp_path):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    started = prepared_state.begin_v2_submission("repo", "msg_A")
    evidence = prepared_state.record_v2_admission("repo", "msg_A", observation(prepared_state))
    assert evidence["sources"] == ["inbox"]
    assert prepared_state.record_v2_admission("repo", "msg_A", observation(prepared_state)) == evidence
    merged = prepared_state.record_v2_admission("repo", "msg_A", observation(prepared_state, ["message"]))
    assert merged["sources"] == ["inbox", "message"] and merged["first_observed_at"] == evidence["first_observed_at"]
    prepared_state.close()
    reopened = ha.State(tmp_path)
    try:
        assert reopened.load_v2_prompt("repo", "msg_A") == {**started, "admission": "admitted"}
        with pytest.raises(ha.PromptIntentError):
            reopened.begin_v2_submission("repo", "msg_A")
    finally:
        reopened.close()


@pytest.mark.parametrize("field,value", [("status", "unknown"), ("id", "msg_other"),
                                        ("session_id", "ses_other"), ("sha256", "0" * 64),
                                        ("prompt_binding_sha256", "0" * 64),
                                        ("server_version", "2.0.33"), ("sources", [])])
def test_admission_rejects_unverified_or_changed_observations(prepared_state, field, value):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.begin_v2_submission("repo", "msg_A")
    item = observation(prepared_state)
    item[field] = value
    with pytest.raises(ha.PromptIntentError):
        prepared_state.record_v2_admission("repo", "msg_A", item)
    assert prepared_state.load_v2_prompt("repo", "msg_A")["admission"] == "unknown"


def test_admission_checkpoint_rejects_corruption_and_rolls_back(prepared_state):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.begin_v2_submission("repo", "msg_A")
    item = observation(prepared_state)
    prepared_state.db.execute("""CREATE TRIGGER reject_admission BEFORE UPDATE OF prompt_admission_evidence ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        prepared_state.record_v2_admission("repo", "msg_A", item)
    assert prepared_state.load_v2_prompt("repo", "msg_A")["admission"] == "unknown"
    prepared_state.db.execute("DROP TRIGGER reject_admission")
    prepared_state.record_v2_admission("repo", "msg_A", item)
    prepared_state.update("repo", "msg_A", prompt_admission_evidence="{}")
    with pytest.raises(ha.PromptIntentError, match="evidence"):
        prepared_state.load_v2_prompt("repo", "msg_A")


def test_admission_rejects_nonfinite_timestamps(prepared_state):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.begin_v2_submission("repo", "msg_A")
    item = observation(prepared_state)
    old_clock = prepared_state.clock
    prepared_state.clock = lambda: float("nan")
    with pytest.raises(ha.PromptIntentError, match="clock"):
        prepared_state.record_v2_admission("repo", "msg_A", item)
    prepared_state.clock = old_clock
    evidence = prepared_state.record_v2_admission("repo", "msg_A", item)
    evidence["first_observed_at"] = float("inf")
    prepared_state.update("repo", "msg_A", prompt_admission_evidence=json.dumps(evidence))
    with pytest.raises(ha.PromptIntentError, match="evidence"):
        prepared_state.load_v2_prompt("repo", "msg_A")


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


@pytest.mark.parametrize("admission", ["intent", "unknown", "admitted"])
def test_historical_unlinked_prompt_is_refused_without_mutation(prepared_state, admission):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    prepared_state.update("repo", "msg_A", prompt_admission=admission, prompt_launch_binding_sha256=None)
    before = dict(prepared_state.get("repo", "msg_A"))
    with pytest.raises(ha.PromptIntentError):
        prepared_state.load_v2_prompt("repo", "msg_A")
    assert dict(prepared_state.get("repo", "msg_A")) == before


@pytest.mark.parametrize("field,value", [("directory", "/other"),
                                        ("permissions", [{"action": "*", "resource": "*", "effect": "allow"}])])
def test_prompt_rejects_changed_launch_binding(prepared_state, field, value):
    prepared_state.prepare_v2_prompt("repo", "msg_A")
    row = prepared_state.get("repo", "msg_A")
    binding = json.loads(row["v2_launch_binding"])
    binding[field] = value
    raw = ha.canonical(binding)
    prepared_state.update("repo", "msg_A", v2_launch_binding=raw,
                          v2_launch_binding_sha256=hashlib.sha256(raw.encode()).hexdigest())
    with pytest.raises(ha.PromptIntentError):
        prepared_state.load_v2_prompt("repo", "msg_A")


@pytest.mark.parametrize("field", ["v2_launch_binding", "prompt_launch_binding_sha256"])
def test_missing_launch_or_link_only_state_is_refused(prepared_state, field):
    if field == "v2_launch_binding":
        prepared_state.update("repo", "msg_A", v2_launch_binding=None)
    else:
        prepared_state.update("repo", "msg_A", prompt_launch_binding_sha256="0" * 64)
    before = dict(prepared_state.get("repo", "msg_A"))
    with pytest.raises(ha.PromptIntentError):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    assert dict(prepared_state.get("repo", "msg_A")) == before


def test_prior_schema_unlinked_prompt_is_preserved_and_refused(prepared_state, tmp_path):
    original = prepared_state.prepare_v2_prompt("repo", "msg_A")
    before = dict(prepared_state.get("repo", "msg_A"))
    prepared_state.close()
    db = sqlite3.connect(tmp_path / "adapter.sqlite3")
    db.execute("ALTER TABLE messages DROP COLUMN prompt_launch_binding_sha256")
    db.close()
    reopened = ha.State(tmp_path)
    try:
        after = dict(reopened.get("repo", "msg_A"))
        assert after["prompt_launch_binding_sha256"] is None
        for key in ("prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256", "prompt_admission"):
            assert after[key] == before[key]
        assert after["prompt_id"] == original["id"]
        with pytest.raises(ha.PromptIntentError):
            reopened.load_v2_prompt("repo", "msg_A")
        assert dict(reopened.get("repo", "msg_A")) == after
    finally:
        reopened.close()


def test_failure_before_persist_rolls_back_all_intent_fields(prepared_state, monkeypatch):
    def fail(*args):
        raise RuntimeError("injected failure")
    monkeypatch.setattr(ha, "build_prompt", fail)
    with pytest.raises(RuntimeError, match="injected"):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    row = prepared_state.get("repo", "msg_A")
    assert all(row[key] is None for key in ("prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256", "prompt_admission"))
    assert row["prompt_launch_binding_sha256"] is None


def test_database_rejection_does_not_leave_partial_intent(prepared_state):
    prepared_state.db.execute("""CREATE TRIGGER reject_intent BEFORE UPDATE OF prompt_id ON messages
        BEGIN SELECT RAISE(ABORT, 'injected rejection'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected rejection"):
        prepared_state.prepare_v2_prompt("repo", "msg_A")
    row = prepared_state.get("repo", "msg_A")
    assert all(row[key] is None for key in ("prompt_id", "prompt_nonce", "prompt_sha256", "prompt_binding_sha256", "prompt_admission"))
    assert row["prompt_launch_binding_sha256"] is None


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
