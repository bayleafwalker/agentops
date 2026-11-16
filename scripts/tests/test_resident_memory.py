"""Fault and trust-boundary tests; no provider credentials or network required."""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resident_memory.client import UpstreamError
from resident_memory.policy import Policy, Principal, Scope, canonical, digest
from resident_memory.service import MemoryService
from resident_memory.store import Store
from resident_context import build_context, recheck_context


class Engine:
    def __init__(self):
        self.operations = {}
        self.results = []
        self.facts = {}
        self.calls = []
        self.lose_ack = False
        self.unavailable = False

    def retain(self, bank, payload):
        self.calls.append((bank, payload))
        self.operations.setdefault(payload["operation_id"], {"status": "completed"})
        if self.lose_ack:
            raise UpstreamError("lost ack")
        return {"success": True, "operation_id": payload["operation_id"]}

    def operation(self, bank, operation):
        return self.operations.get(operation, {"status": "not_found"})

    def recall(self, bank, query, tags):
        if self.unavailable:
            raise UpstreamError("offline")
        return {"results": self.results, "source_facts": self.facts}


@pytest.fixture
def rig(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "canon.md").write_text("The city is called Ash.\n")
    (root / "rumour.md").write_text("A traveller alleges that the moon is hollow.\n")
    scope = Scope("story", "resident-story", "r01", "story", "main", root, ("canon.md", "rumour.md"))
    policy = Policy(tmp_path / "state", "http://127.0.0.1:8888", tmp_path / "token",
                    {"story": scope}, (Principal("reader", digest(b"a" * 32), ("story",)),), "0" * 64)
    store = Store(policy)
    engine = Engine()
    service = MemoryService(policy, store, engine)
    yield policy, store, engine, service
    store.close()


def retain(rig, path="canon.md", kind="canon"):
    policy, store, engine, service = rig
    ref = store.capture("story", path, kind)
    receipt = service.ingest(ref["source_id"])
    receipt = service.reconcile(receipt["operation_id"])
    assert receipt["status"] == "retained"
    item = engine.calls[-1][1]["items"][0]
    fact = {"id": "fact-" + path, "text": item["content"], "type": "world",
            "document_id": item["document_id"], "tags": item["tags"]}
    return ref, fact


def test_exact_capture_and_semantic_classification(rig):
    _, store, _, _ = rig
    a = store.capture("story", "canon.md", "canon")
    b = store.capture("story", "canon.md", "canon")
    c = store.capture("story", "canon.md", "rumour")
    assert a == b
    assert a["source_id"] == c["source_id"] and a["revision"] != c["revision"]
    assert store.source(a["source_id"], a["revision"])["body"] == b"The city is called Ash.\n"


@pytest.mark.parametrize("name", ["../token", "/etc/passwd", ".env", "missing.md", "canon.md/../rumour.md"])
def test_capture_denies_unapproved_paths(rig, name):
    with pytest.raises((ValueError, PermissionError)):
        rig[1].capture("story", name, "canon")


def test_capture_denies_symlink_and_oversize(rig):
    policy, store, _, _ = rig
    target = policy.scopes["story"].source_root / "canon.md"
    target.unlink()
    target.symlink_to("/etc/passwd")
    with pytest.raises(OSError):
        store.capture("story", "canon.md", "canon")
    target.unlink()
    target.write_bytes(b"x" * (policy.max_source_bytes + 1))
    with pytest.raises(ValueError):
        store.capture("story", "canon.md", "canon")


def test_lost_ack_reconciles_same_operation_without_second_submission(rig):
    _, store, engine, service = rig
    ref = store.capture("story", "canon.md", "canon")
    engine.lose_ack = True
    first = service.ingest(ref["source_id"])
    assert first["status"] == "unknown"
    again = service.ingest(ref["source_id"])
    assert again["operation_id"] == first["operation_id"]
    assert again["status"] == "retained"
    assert len(engine.calls) == 1


def test_expired_receipt_is_not_permission_to_replay(rig):
    _, store, engine, service = rig
    ref = store.capture("story", "canon.md", "canon")
    engine.lose_ack = True
    first = service.ingest(ref["source_id"])
    engine.operations.clear()
    assert service.ingest(ref["source_id"])["status"] == "unknown"
    assert len(engine.calls) == 1
    with pytest.raises(ValueError):
        service.retry_unknown(first["operation_id"])


def test_async_ack_does_not_mean_retained(rig):
    _, store, engine, service = rig
    ref = store.capture("story", "canon.md", "canon")
    receipt = service.ingest(ref["source_id"])
    assert receipt["status"] == "submitted"
    engine.operations[receipt["operation_id"]] = {"status": "failed"}
    assert service.reconcile(receipt["operation_id"])["status"] == "failed"
    assert service.ingest(ref["source_id"])["status"] == "failed"
    assert len(engine.calls) == 1


def test_delayed_ack_cannot_regress_concurrent_completion(rig):
    _, store, engine, service = rig
    source = store.capture("story", "canon.md", "canon")
    original = engine.retain
    def complete_before_ack(bank, payload):
        ack = original(bank, payload)
        assert service.reconcile(payload["operation_id"])["status"] == "retained"
        return ack
    engine.retain = complete_before_ack
    receipt = service.ingest(source["source_id"])
    assert receipt["status"] == "retained"


def test_delayed_not_found_cannot_regress_terminal_receipt(rig):
    _, store, engine, service = rig
    source = store.capture("story", "canon.md", "canon")
    receipt = service.ingest(source["source_id"])
    def stale_poll(bank, operation):
        service._state(operation, "retained")  # Other reconciliation commits first.
        return {"status": "not_found"}
    engine.operation = stale_poll
    assert service.reconcile(receipt["operation_id"])["status"] == "retained"


def test_changed_source_blocks_existing_fact_before_recapture(rig):
    policy, _, engine, service = rig
    _, fact = retain(rig)
    engine.results = [fact]
    assert len(service.search("story", "city")["entries"]) == 1
    (policy.scopes["story"].source_root / "canon.md").write_text("The city is called Ember.\n")
    result = service.search("story", "city")
    assert result["entries"] == []
    assert result["omissions"][0]["reason"] == "stale-or-retracted-source"


def test_retraction_blocks_raw_and_derived_lineage(rig):
    _, store, engine, service = rig
    ref, fact = retain(rig)
    engine.facts = {fact["id"]: fact}
    derived = {"id": "observation", "type": "observation", "text": "Ash is a city.",
               "source_fact_ids": [fact["id"]], "tags": fact["tags"]}
    engine.results = [fact, derived]
    assert len(service.search("story", "city")["entries"]) == 2
    store.retract(ref["source_id"], "canon withdrawn")
    assert service.search("story", "city")["entries"] == []
    with pytest.raises(ValueError):
        store.capture("story", "canon.md", "canon")


@pytest.mark.parametrize("parents", [None, [], ["missing"], ["observation"]])
def test_unverifiable_observation_is_omitted(rig, parents):
    policy, _, engine, service = rig
    fact = {"id": "observation", "type": "observation", "text": "claim",
            "source_fact_ids": parents, "tags": policy.scopes["story"].tags}
    engine.results = [fact]
    engine.facts = {"observation": fact}
    assert service.search("story", "x")["entries"] == []


def test_untagged_or_foreign_scope_is_denied(rig):
    _, _, engine, service = rig
    _, fact = retain(rig)
    fact["tags"] = []
    engine.results = [fact]
    assert service.search("story", "x")["omissions"][0]["reason"] == "scope-mismatch"
    with pytest.raises(PermissionError):
        rig[0].authenticate("a" * 32, "foreign")


def test_observation_source_map_cannot_substitute_another_fact(rig):
    _, _, engine, service = rig
    _, fact = retain(rig)
    engine.facts = {"requested-fact": fact}
    engine.results = [{"id": "observation", "type": "observation", "text": "claim",
                       "source_fact_ids": ["requested-fact"], "tags": fact["tags"]}]
    result = service.search("story", "city")
    assert result["entries"] == []
    assert result["omissions"][0]["reason"] == "lineage-key-mismatch"


def test_outage_is_explicit_and_exact_result_is_preserved(rig):
    _, store, engine, service = rig
    engine.unavailable = True
    result = service.search("story", "x")
    assert result["state"] == "unavailable" and result["authorizes_effects"] is False
    row = store.db.execute("SELECT body FROM selections").fetchone()
    assert row["body"] == canonical(result)


def test_final_json_is_bounded_in_utf8(rig):
    _, _, engine, service = rig
    _, fact = retain(rig)
    fact["text"] = "界" * 10000
    engine.results = [{**fact, "id": str(i)} for i in range(50)]
    service.policy = replace(service.policy, max_result_bytes=4096)
    result = service.search("story", "city")
    assert len(canonical(result)) <= 4096
    assert result["entries"] == [] and result["omissions"]


def test_database_backup_includes_wal_and_does_not_clobber(rig, tmp_path):
    _, store, _, _ = rig
    store.capture("story", "canon.md", "canon")
    target = tmp_path / "backup.sqlite"
    store.backup(target)
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT count(*) FROM sources").fetchone()[0] == 1
    with pytest.raises(ValueError):
        store.backup(target)


def test_existing_scope_cannot_be_rebound_to_another_bank(rig):
    policy, _, _, _ = rig
    changed = replace(policy, scopes={"story": replace(policy.scopes["story"], bank="other")})
    with pytest.raises(ValueError, match="scope identity changed"):
        Store(changed)


def test_episode_collection_pattern_never_crosses_directory(rig):
    policy, _, _, _ = rig
    from resident_memory.sources import read_source
    scope = replace(policy.scopes["story"], source_paths=("episodes/*.json",))
    episodes = scope.source_root / "episodes"
    episodes.mkdir()
    (episodes / "one.json").write_text('{"episode":"one"}')
    assert read_source(scope, "episodes/one.json", 1024) == b'{"episode":"one"}'
    with pytest.raises((ValueError, PermissionError)):
        read_source(scope, "episodes/nested/two.json", 1024)


def test_three_fresh_contexts_preserve_rumour_and_correct_canon(rig):
    policy, store, engine, service = rig
    scope = policy.scopes["story"]
    _, old = retain(rig)
    _, rumour = retain(rig, "rumour.md", "rumour")
    engine.results = [old, rumour]
    def episode():
        recall = service.search("story", "Continue this story")
        return build_context(instructions="Finish a local edition.", current_work="story#1",
                             required_sources=[], memories=recall["entries"], scope=scope.identity,
                             current_sources=store.current_sources("story"))
    first = episode()
    second = episode()  # Fresh packet; no prior transcript passed.
    assert first["digest"] == second["digest"]
    (scope.source_root / "canon.md").write_text("The city is now named Ember.\n")
    assert recheck_context(first, current_sources=store.current_sources("story"))["status"] == "review-required"
    _, corrected = retain(rig)
    engine.results = [old, corrected, rumour]
    third = episode()
    memories = next(section["items"] for section in third["sections"] if section["kind"] == "memories")
    assert any("Ember" in entry["content"] for entry in memories)
    assert not any("called Ash" in entry["content"] for entry in memories)
    assert any("source kinds: rumour" in entry["content"] for entry in memories)
    assert third["authorizes_effects"] is False


def test_policy_refuses_network_and_workspace_authority_changes(rig, tmp_path):
    policy = rig[0]
    raw = {"schema": "resident-memory-policy/v1", "state_dir": str(policy.state_dir),
           "upstream_url": policy.upstream_url, "upstream_token_file": str(policy.upstream_token_file),
           "scopes": [{"id": "story", "bank": "resident-story", **policy.scopes["story"].identity,
                       "source_root": str(policy.scopes["story"].source_root), "source_paths": ["canon.md"]}],
           "principals": [{"id": "reader", "token_sha256": digest(b"a" * 32), "scopes": ["story"]}]}
    path = tmp_path / "policy.json"
    path.write_bytes(canonical(raw))
    assert Policy.load(path).authenticate("a" * 32, "story").id == "reader"
    for url in ["http://external.test", "https://name:password@example.test", "https://example.test/other"]:
        path.write_bytes(canonical({**raw, "upstream_url": url}))
        with pytest.raises(ValueError):
            Policy.load(path)
    path.write_bytes(canonical({**raw, "state_dir": str(policy.scopes["story"].source_root / "state")}))
    with pytest.raises(ValueError):
        Policy.load(path)


def test_operator_cli_context_and_recheck_use_full_packet_hash(rig, tmp_path, monkeypatch, capsys):
    import resident_memory_cli as cli
    policy, store, engine, _ = rig
    ref, fact = retain(rig)
    engine.results = [fact]
    monkeypatch.setattr(cli.Policy, "load", lambda _: policy)
    monkeypatch.setattr(cli, "HindsightClient", lambda _: engine)
    charter = tmp_path / "charter.txt"
    work = tmp_path / "work.json"
    charter.write_text("Finish the local edition.")
    work.write_text('{"work_ref":"story#1"}')
    args = ["--policy", str(tmp_path / "unused-policy"), "context", "--scope", "story",
            "--instructions", str(charter), "--work", str(work), "--query", "city",
            "--required-source", ref["source_id"], "--output-dir", str(tmp_path / "packets")]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    target = Path(result["path"])
    assert result["status"] == "ready"
    recheck_args = ["--policy", str(tmp_path / "unused-policy"), "recheck", "--scope", "story",
                    "--context", str(target), "--generation", "1"]
    assert cli.main(recheck_args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["context_digest"] == result["digest"]
    assert receipt["context_sha256"] == digest(target.read_bytes())
    assert receipt["context_digest"] != receipt["context_sha256"]
    assert receipt["status"] == "unchanged" and receipt["generation"] == 1
    (policy.scopes["story"].source_root / "canon.md").write_text("Revised.")
    assert cli.main(recheck_args) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "review-required"
