"""Test 1: no cell can be constructed without its provenance triple."""

import pytest

from operator_projection.cell import Cell, Provenance, blind, cell, demote, is_cell

NOW = "2026-09-14T12:00:00Z"


@pytest.mark.parametrize(
    "args",
    [("", NOW, "rev"), ("git", "", "rev"), ("git", NOW, None)],
)
def test_provenance_raises_on_a_missing_triple_part(args):
    with pytest.raises(ValueError):
        Provenance(*args)


def test_mtime_satisfies_the_revision_part():
    assert Provenance("file", NOW, mtime="2026-09-01T00:00:00Z").to_dict() == {
        "transport": "file", "mtime": "2026-09-01T00:00:00Z", "observed_at": NOW,
    }


def test_blind_needs_a_reason_and_kinds_are_closed():
    with pytest.raises(ValueError):
        Cell("BLIND", None, Provenance("git", NOW, "r"))
    with pytest.raises(ValueError):
        Cell("GUESSED", 1, Provenance("git", NOW, "r"))
    with pytest.raises(TypeError):
        Cell("OBSERVED", 1, {"transport": "git"})


def test_cell_serializes_with_its_triple():
    value = cell("OBSERVED", "0.1.59", "http-get", "sha256:e9be", NOW)
    assert value == {"kind": "OBSERVED", "value": "0.1.59", "prov": {"transport": "http-get", "record_revision": "sha256:e9be", "observed_at": NOW}}
    assert is_cell(value)


def test_demote_keeps_provenance_and_names_the_reason():
    demoted = demote(cell("DECLARED", 25, "github-rest", "8feff32e", NOW), "source degraded")
    assert demoted["kind"] == "BLIND" and demoted["value"] is None
    assert demoted["prov"]["record_revision"] == "8feff32e" and demoted["reason"] == "source degraded"
    assert blind("no identity", "vuoro-invoke", None, NOW)["prov"]["record_revision"] == "none"
