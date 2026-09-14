"""Panels 2 and 7: the served pick-up answer, and the BLIND path without the generator identity."""

from fakes import FakeAuthorityClient, fixture
from operator_projection.evaluators import Move
from operator_projection.generate import UNCONTRACTED, Run, blind_spots, pickup
from operator_projection.sources import READ_OPS, Authority
from world import NOW, REGISTRY, TAGS, estate

RESULTS = {
    "work.project.context": fixture("project-context.json"),
    "work.read.handoff": lambda args: {"last_checkpoint": {"id": 1} if args["sprint_id"] == 11 else None},
    "work.read.context-candidates": lambda args: {"candidates": [{"path": "synthetic"}] if args["item_id"] == 202 else []},
}
MOVED = [Move("credbroker.binding", "h|r|c", "GAINED", "c9", "2026-09-11T00:00:00+00:00")]


def run(credential: bool):
    client = FakeAuthorityClient(results=RESULTS)
    return client, Run(estate(), Authority(client, lambda: credential), REGISTRY, NOW, lambda: TAGS)


def test_pickup_ranks_by_class_then_boundary_none_then_age():
    client, current = run(credential=True)
    panel, repositories = pickup(current, MOVED)
    assert panel["counts"]["value"] == {"needs_you": 2, "stale_holds": 1, "active_no_holder": 2, "ready": 3}
    assert panel["overflow"] == 3
    assert [(r["ref"], r["boundary"]) for r in panel["rows"]] == [
        ("repo-alpha#101", "HANDOFF"), ("repo-beta#202", "CONTEXT"), ("repo-alpha#103", "HANDOFF"),
        ("repo-gamma#305", "NONE"), ("repo-alpha#104", "HANDOFF")]
    first, stale = panel["rows"][0], panel["rows"][2]
    assert (first["age"], first["moved_since_touch"], first["holder"]) == (4, 1, "agent-one")
    assert stale["age"] == UNCONTRACTED and stale["moved_since_touch"] == UNCONTRACTED
    assert repositories == ["agentops", "vuoro", "kctl"]
    assert {op for op, _ in client.invoked} <= READ_OPS and len(client.invoked) == 6


def test_without_the_identity_pickup_and_scope_are_blind_and_nothing_is_sent():
    client, current = run(credential=False)
    panel, repositories = pickup(current, [])
    assert panel["kind"] == "BLIND" and "credential" in panel["reason"] and repositories is None
    assert client.invoked == []
    spots = blind_spots(current, repositories, panel)
    assert spots["scope"]["served"]["kind"] == "BLIND"
    assert spots["scope"]["declared"]["value"] == ["agentops", "vuoro", "sprintctl"]
    assert current.sources["authority.work"]["degraded"]["source"] == "authority.work"


def test_scope_names_drift_between_served_and_declared():
    _, current = run(credential=True)
    panel, repositories = pickup(current, [])
    scope = blind_spots(current, repositories, panel)["scope"]["served"]["value"]
    assert scope["undeclared"] == ["kctl"] and scope["not_served"] == ["sprintctl"]
