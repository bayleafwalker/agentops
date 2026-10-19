"""Owner metadata is an observation, never an authority or execution receipt."""
from __future__ import annotations

import copy
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha


@pytest.fixture
def expected():
    return ha._owner_inventory(ha._declared_owner_operations())[0]


@pytest.fixture
def metadata_owner(monkeypatch, expected):
    class MetadataOwner:
        calls = []
        handshake = {"service_release": {"distribution": "vuoro-service", "version": "fixture-secret"}}
        catalog = {"revision": "private-catalog-revision", "operations": list(copy.deepcopy(expected).values())}
        supported = frozenset({"json-schema-draft-2020-12", "local-defs-ref"})
        failure = None

        def __init__(self, profile):
            self.calls.append("construct")

        def _ensure(self):
            self.calls.append("ensure")
            if self.failure == "handshake":
                raise ValueError("https://private-endpoint?token=TOP-SECRET credential-ref file:/secret")

        def metadata(self):
            self.calls.append("metadata")
            if self.failure == "catalog":
                raise ValueError("TOP-SECRET")
            return self.handshake, self.catalog, self.supported

        def close(self):
            self.calls.append("close")

    monkeypatch.setattr(ha, "VuoroOwner", MetadataOwner)
    return MetadataOwner


def test_all_fourteen_calls_join_exact_metadata_without_authority_claim(metadata_owner):
    report = ha.inspect_owner("/private/profile")
    assert report["status"] == "exact-match"
    assert len(report["operations"]) == 14
    assert report["effective_authority"] == report["execution_acceptance"] == "unknown"
    assert {row["status"] for row in report["operations"]} == {"exact-match"}
    assert all(row["effective_authority"] == "unknown" for row in report["operations"])
    rendered = json.dumps(report)
    assert all(secret not in rendered for secret in ("fixture-secret", "private-catalog-revision", "/private/profile"))
    assert metadata_owner.calls == ["construct", "ensure", "metadata", "close"]


@pytest.mark.parametrize("field,value", [
    ("input_schema", {"type": "null"}), ("result_schema", {"type": "null"}),
    ("required_authority", "private:secret"), ("idempotency", "required"),
    ("repo_scoped", False), ("execution_semantics", "read"),
    ("owning_domain", "private-owner"), ("deprecation", {"deprecated": True}),
    ("required_client_schema_features", ["private-schema-feature"]),
])
def test_contract_field_drift_is_explicit_and_redacted(metadata_owner, field, value):
    operation = metadata_owner.catalog["operations"][0]
    assert operation[field] != value
    operation[field] = value
    report = ha.inspect_owner("unused")
    assert report["status"] == "drift"
    row = next(row for row in report["operations"] if row["name"] == operation["name"])
    assert row["status"] == row["fields"][field]["status"] == "drift"
    assert "private" not in json.dumps(report)


def test_missing_and_duplicate_operations_cannot_be_exact(metadata_owner):
    removed = metadata_owner.catalog["operations"].pop()
    duplicated = metadata_owner.catalog["operations"][0]
    metadata_owner.catalog["operations"].append(copy.deepcopy(duplicated))
    report = ha.inspect_owner("unused")
    rows = {row["name"]: row for row in report["operations"]}
    assert report["status"] == "drift"
    assert len(rows) == 14
    assert rows[removed["name"]]["status"] == "missing"
    assert rows[duplicated["name"]]["status"] == "ambiguous"


def test_missing_field_differs_from_null_and_additive_contract_is_drift(metadata_owner):
    one, two = metadata_owner.catalog["operations"][:2]
    one.pop("deprecation")
    two["result_contract"] = {"mode": "resource-reference", "private": "TOP-SECRET"}
    report = ha.inspect_owner("unused")
    rows = {row["name"]: row for row in report["operations"]}
    assert rows[one["name"]]["fields"]["deprecation"]["status"] == "missing"
    assert rows[two["name"]]["additional_field_count"] == 1
    assert rows[two["name"]]["status"] == "drift"
    assert "TOP-SECRET" not in json.dumps(report)


def test_extra_unconsumed_operations_do_not_claim_extra_coverage(metadata_owner):
    metadata_owner.catalog["operations"].append({"name": "secret-unconsumed-operation"})
    report = ha.inspect_owner("unused")
    assert report["status"] == "exact-match"
    assert report["catalog"]["operation_count"] == 15
    assert len(report["operations"]) == 14
    assert "secret-unconsumed-operation" not in json.dumps(report)


@pytest.mark.parametrize("failure,reason", [("handshake", "profile-or-handshake-unavailable"),
                                           ("catalog", "catalog-unavailable")])
def test_metadata_failure_keeps_every_operation_unknown_and_closes(metadata_owner, failure, reason):
    metadata_owner.failure = failure
    report = ha.inspect_owner("unused")
    assert report["status"] == "unavailable"
    assert report["reason"] == reason
    assert len(report["operations"]) == 14
    assert {row["status"] for row in report["operations"]} == {"unavailable"}
    assert metadata_owner.calls[-1] == "close"
    assert "TOP-SECRET" not in json.dumps(report)


@pytest.mark.parametrize("malformed", [None, {}, [None], [{"name": 3}]])
def test_malformed_catalog_is_unavailable(metadata_owner, malformed):
    metadata_owner.catalog["operations"] = malformed
    report = ha.inspect_owner("unused")
    assert report["status"] == "unavailable"
    assert report["reason"] == "metadata-invalid"
    assert len(report["operations"]) == 14


def test_absent_release_is_unknown_under_existing_client_contract(metadata_owner):
    metadata_owner.handshake = {}
    report = ha.inspect_owner("unused")
    assert report["status"] == "exact-match"
    assert report["handshake"]["release_identity"] == "unknown"


def test_stale_inventory_refuses_before_any_client(monkeypatch, metadata_owner):
    monkeypatch.setattr(ha, "_declared_owner_operations", lambda: ["work.new-operation-v1"])
    report = ha.inspect_owner("unused")
    assert report["reason"] == "inventory-unavailable"
    assert report["operations"][0]["name"] == "work.new-operation-v1"
    assert metadata_owner.calls == []


def test_inspect_cli_opens_no_state_harness_or_password(monkeypatch, metadata_owner, tmp_path, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail("metadata command opened an execution dependency")
    for name in ("State", "OpenCodeServe", "Adapter", "_serve_password"):
        monkeypatch.setattr(ha, name, forbidden)
    state_dir = tmp_path / "must-not-exist"
    assert ha.main(["--state-dir", str(state_dir), "--profile", "private", "inspect-owner"]) == 0
    assert not state_dir.exists()
    assert json.loads(capsys.readouterr().out)["status"] == "exact-match"


@pytest.mark.parametrize("fail_at", ["load", "construct", "enter", "handshake"])
def test_failed_initialization_cleans_loop_and_retry_uses_fresh_client(monkeypatch, fail_at):
    events, loops, clients = [], [], []
    failure = [fail_at]
    new_loop = ha.asyncio.new_event_loop
    def loop_factory():
        loop = new_loop()
        loops.append(loop)
        return loop
    monkeypatch.setattr(ha.asyncio, "new_event_loop", loop_factory)
    def fail(stage):
        events.append(stage)
        if failure[0] == stage:
            raise ValueError("PRIVATE profile/path/endpoint")
    def load_profile(path):
        fail("load")
        return object()
    class Client:
        def __init__(self, profile, resolver):
            fail("construct")
            clients.append(self)
        async def __aenter__(self):
            fail("enter")
            return self
        async def handshake(self):
            fail("handshake")
            return {}
        async def __aexit__(self, *args):
            events.append("close")
        async def invoke(self, *args, **kwargs):
            events.append("invoke")
            return {}
    monkeypatch.setitem(sys.modules, "vuoro_client", types.SimpleNamespace(AsyncVuoroClient=Client))
    monkeypatch.setitem(sys.modules, "vuoro_client.profile", types.SimpleNamespace(load_profile=load_profile))
    owner = ha.VuoroOwner("private")
    with pytest.raises(ha.OwnerError) as exc:
        owner.agent_retire("repo", instance_id="id", reason="test", idempotency_key="key")
    assert "PRIVATE" not in str(exc.value)
    assert "invoke" not in events
    assert owner._client is owner._loop is None
    assert all(loop.is_closed() for loop in loops)
    assert events.count("close") == (1 if fail_at in ("enter", "handshake") else 0)
    failure[0] = None
    owner.agent_retire("repo", instance_id="id", reason="test", idempotency_key="key")
    assert events[-1] == "invoke"
    assert events[-2] == "handshake"
    owner.close()
    assert all(loop.is_closed() for loop in loops)


def test_unsupported_client_feature_refuses_exact_match_even_when_catalog_matches(metadata_owner):
    metadata_owner.supported = frozenset()
    report = ha.inspect_owner("unused")
    assert report["status"] == "drift"
    assert {row["client_schema_features"] for row in report["operations"]} == {"unsupported"}


@pytest.mark.parametrize("status,exit_code", [("drift", 1), ("unavailable", 2)])
def test_inspect_cli_non_success_exit_codes(monkeypatch, capsys, status, exit_code):
    monkeypatch.setattr(ha, "inspect_owner", lambda profile: {"status": status})
    assert ha.main(["--profile", "unused", "inspect-owner"]) == exit_code
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_inspect_without_profile_emits_unavailable_json(monkeypatch, capsys):
    monkeypatch.delenv("AGENTOPS_HOST_ADAPTER_PROFILE", raising=False)
    assert ha.main(["inspect-owner"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "unavailable"
    assert report["reason"] == "profile-or-handshake-unavailable"
    assert len(report["operations"]) == 14


@pytest.mark.parametrize("declaration", ["self._invoke(operation, {})", "self._invoke()"])
def test_dynamic_owner_operation_cannot_silently_escape_inventory(monkeypatch, declaration):
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: "class VuoroOwner:\n def call(self):\n  " + declaration)
    with pytest.raises(ValueError, match="dynamic owner operation"):
        ha._declared_owner_operations()
