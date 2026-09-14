"""Test 4: the generator reaches the authority only through the read allowlist."""

import ast
from pathlib import Path

import pytest

from fakes import FakeAuthorityClient
from operator_projection.sources import READ_OPS, Authority, ReadRefused, SourceUnavailable

SRC = Path(__file__).resolve().parents[1] / "src" / "operator_projection"


def authority(credential=True, **overrides):
    client = FakeAuthorityClient(**overrides)
    return client, Authority(client, lambda: credential)


def test_allowlisted_read_is_invoked_after_the_catalog_is_fetched():
    client, auth = authority(results={"work.project.context": {"contract_version": "project-1"}})
    auth.catalog()
    assert auth.read("work.project.context", {}) == {"contract_version": "project-1"}
    assert client.invoked == [("work.project.context", {})]


def test_read_semantics_alone_is_not_enough():
    client, auth = authority()
    auth.catalog()
    with pytest.raises(ReadRefused, match="allowlist"):
        auth.read("work.read.events", {})
    assert client.invoked == []


def test_catalog_semantics_must_be_read_in_this_generation():
    client, auth = authority()
    with pytest.raises(ReadRefused, match="catalog"):
        auth.read("work.project.context", {})  # no catalog fetched yet
    client.semantics["work.project.context"] = "write"
    auth.catalog()
    with pytest.raises(ReadRefused, match="catalog"):
        auth.read("work.project.context", {})
    assert client.invoked == []


def test_missing_credential_is_unavailable_and_nothing_is_sent():
    client, auth = authority(credential=False)
    auth.catalog()
    with pytest.raises(SourceUnavailable, match="credential"):
        auth.read("work.project.context", {})
    assert client.invoked == []


def test_allowlist_is_read_only_operations():
    assert READ_OPS == {"work.project.context", "work.read.handoff", "work.read.context-candidates"}


def test_invoke_is_called_in_exactly_one_place():
    calls = [
        (path.name, node.lineno)
        for path in SRC.glob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Attribute) and node.attr == "invoke"
    ]
    assert [name for name, _ in calls] == ["sources.py"]


def test_repo_scoped_reads_carry_repo_id_and_project_context_does_not():
    client, auth = authority(results={"work.project.context": {}, "work.read.handoff": {"last_checkpoint": None}})
    auth.catalog()
    auth.read("work.read.handoff", {"sprint_id": 11, "events_limit": 1}, repo_id="repo-alpha")
    auth.read("work.project.context", {})
    assert client.repo_ids == ["repo-alpha", None]


def test_repo_scoped_read_without_repo_id_is_refused_before_sending():
    client, auth = authority(results={"work.read.handoff": {}})
    auth.catalog()
    with pytest.raises(ReadRefused, match="repo-scoped"):
        auth.read("work.read.handoff", {"sprint_id": 11, "events_limit": 1})
    assert client.invoked == []


def test_timed_transport_sets_every_httpx_timeout_phase():
    import asyncio

    import httpx

    from operator_projection.sources import TimedTransport

    seen = {}

    def answer(request):
        seen.update(request.extensions["timeout"])
        return httpx.Response(200, json={})

    async def get():
        async with httpx.AsyncClient(base_url="https://authority.invalid", transport=TimedTransport(30, httpx.MockTransport(answer))) as http:
            await http.get("/x")

    asyncio.run(get())
    assert seen == {"connect": 30, "read": 30, "write": 30, "pool": 30}


def test_open_authority_timeout_defaults_to_30s_and_is_set_by_the_profile():
    pytest.importorskip("vuoro_client")
    from operator_projection.sources import READ_TIMEOUT_S, open_authority

    profile = {"authority_url": "https://authority.invalid", "credential_ref": "file:/absent"}
    assert READ_TIMEOUT_S == 30.0
    assert open_authority(profile).client._http._transport.seconds == 30.0
    assert open_authority(profile | {"read_timeout_s": 7}).client._http._transport.seconds == 7.0
