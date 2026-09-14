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
