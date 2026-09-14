"""Panels 1, 3 and 5 over the synthetic estate."""

from fakes import FakeAuthorityClient
from operator_projection.generate import Run, ground_tools, hazards, provenance
from operator_projection.sources import Authority
from world import NOW, REGISTRY, TAGS, estate


def run(down=False, git=None):
    return Run(git or estate(), Authority(FakeAuthorityClient(down=down), lambda: False), REGISTRY, NOW, lambda: TAGS)


def test_provenance_is_observed_from_handshake_and_catalog():
    panel = provenance(run())
    assert panel["authority"]["kind"] == "OBSERVED" and panel["authority"]["value"]["release"] == "9.9.1"
    assert panel["catalog"]["prov"]["record_revision"] == "synthetic-catalog-0001"
    assert panel["compatibility"]["value"]["audit"] == "compatible"


def test_unreachable_authority_renders_blind_not_empty():
    current = run(down=True)
    panel = provenance(current)
    assert {c["kind"] for c in panel.values()} == {"BLIND"}
    assert current.sources["authority.handshake"]["degraded"]["source"] == "authority.handshake"


def test_hazards_name_orphan_foreclosed_unreachable_and_diverged():
    rows = {(r["kind"], r["subject"]): r for r in hazards(run())["rows"]}
    claim = rows[("FORECLOSED", "work:claim")]
    assert claim["consumers"] == [f"agent-cockpit {REGISTRY['consumer_set']['code'][0]['path']}:3"]
    assert "requested by 2 client profiles" in claim["detail"] and claim["since"] == "2026-08-15"
    assert "history undetermined" in rows[("ORPHAN", "work:pilot-read")]["detail"]
    decision = rows[("UNREACHABLE", "audit record_class=decision")]
    assert "pinned 0.1.0 rejects" in decision["detail"] and decision["served_const"] == ["observation"]
    diverged = rows[("DIVERGED", "vuoro-service image")]
    assert "(9.9.1)" in diverged["detail"] and "(9.8.0)" in diverged["detail"] and diverged["since"] == "2026-09-01"
    assert all(r["evidence"]["kind"] == "DECLARED" for r in rows.values())


def test_hazards_without_catalog_are_undetermined_rows():
    rows = hazards(run(down=True))["rows"]
    assert rows[0]["kind"] == "FORECLOSED" and rows[0]["flags"] == ["UNDETERMINED"] and rows[0]["evidence"]["kind"] == "BLIND"


def test_ground_tools_triples_and_agreement():
    panel = ground_tools(run())
    assert panel["authority"]["value"]["agrees"] is True and panel["authority"]["value"]["as_of"] == "c2"
    assert panel["adapters"]["value"]["audit-adapter"] == {"head": "0.1.1", "pinned": "0.1.1", "deployed": "0.1.0"}
    assert panel["adapters"]["value"]["work-adapter"] == {"head": "0.3.6", "pinned": "0.3.5", "deployed": "0.3.5"}
    assert panel["installed"]["kind"] == "BLIND" and panel["domains"]["kind"] == "OBSERVED"
