"""Panels 2 and 7: the served pick-up answer over the project-1 shape, and the BLIND paths."""

import httpx

from fakes import FakeAuthorityClient, fixture
from operator_projection import render_text
from operator_projection.evaluators import Move
from operator_projection.generate import UNCONTRACTED, Run, blind_spots, candidates_of, describe, generate, normalized, pickup
from operator_projection.sources import READ_OPS, Authority, SourceUnavailable
from world import NOW, REGISTRY, TAGS, estate

RESULTS = {
    "work.project.context": fixture("project-context.json"),
    "work.read.handoff": lambda args: {"last_checkpoint": {"id": 1} if args["sprint_id"] == 11 else None},
    "work.read.context-candidates": lambda args: {"candidates": [{"path": "synthetic"}] if args["item_id"] == 203 else []},
}
MOVED = [Move("credbroker.binding", "h|r|c", "GAINED", "c9", "2026-09-11T00:00:00+00:00")]


def timeout(_args):
    raise httpx.ReadTimeout("")  # str() is '' exactly as the live httpx/httpcore ReadTimeout


def run(credential: bool = True, **overrides):
    client = FakeAuthorityClient(results=RESULTS | overrides)
    return client, Run(estate(), Authority(client, lambda: credential), REGISTRY, NOW, lambda: TAGS)


def test_pickup_ranks_by_class_then_boundary_none_then_age():
    client, current = run()
    panel, repositories = pickup(current, MOVED)
    assert panel["counts"]["value"] == {"needs_you": 3, "stale_holds": 2, "active_no_holder": 1, "ready": 3}
    assert panel["overflow"] == 4
    assert [(r["ref"], r["class"], r["boundary"]) for r in panel["rows"]] == [
        ("repo-beta#202", "NEEDS YOU", "NONE"), ("repo-alpha#104", "NEEDS YOU", "HANDOFF"), ("repo-beta#203", "NEEDS YOU", "CONTEXT"),
        ("repo-gamma#305", "STALE HOLD", "NONE"), ("repo-alpha#103", "STALE HOLD", "HANDOFF")]
    conflict, stale = panel["rows"][0], panel["rows"][4]
    assert (conflict["next_action"], conflict["holder"], conflict["age"], conflict["moved_since_touch"]) == (
        "waits on an open dependency", "not contracted", UNCONTRACTED, UNCONTRACTED)
    assert (stale["next_action"], stale["age"], stale["moved_since_touch"], stale["holder"]) == ("stale alpha work", 4, 1, "not contracted")
    assert repositories == ["agentops", "vuoro", "kctl"]
    assert {op for op, _ in client.invoked} <= READ_OPS and len(client.invoked) == 7


def test_project_context_is_read_without_repo_id_and_boundary_reads_carry_the_rows_repo():
    client, current = run()
    pickup(current, [])
    assert client.invoked[0] == ("work.project.context", {}) and client.repo_ids[0] is None
    scoped = list(zip(client.invoked[1:], client.repo_ids[1:]))
    assert all(op != "work.project.context" for (op, _), _ in scoped)
    assert [(op, args["sprint_id"], repo) for (op, args), repo in scoped] == [
        ("work.read.handoff", 11, "repo-alpha"),
        ("work.read.handoff", 12, "repo-beta"), ("work.read.context-candidates", 12, "repo-beta"),
        ("work.read.handoff", 12, "repo-beta"), ("work.read.context-candidates", 12, "repo-beta"),
        ("work.read.handoff", 11, "repo-alpha")]  # repo-gamma has no active sprint: NONE, nothing sent


def test_mapping_uses_only_contracted_fields():
    found = dict((item["ref"], (cls, item)) for cls, item in candidates_of(fixture("project-context.json")))
    assert found["repo-gamma#306"][0] == "ACTIVE, NO HOLDER" and found["repo-gamma#306"][1]["holder"] == "no holder"
    assert found["repo-alpha#104"][0] == "NEEDS YOU"  # one row per item, at its highest class
    assert [ref for ref, (cls, _) in found.items() if cls == "READY"] == ["repo-alpha#106", "repo-beta#207", "repo-beta#201"]
    assert "repo-beta#208" not in found  # kind no-action is not ready work
    bare = normalized("conflicts", {"kind": "stale-work", "summary": "no item named", "item_ids": [], "origin_repo": "repo-x"})
    assert (bare["ref"], bare["id"], bare["text"], bare["idle_seconds"]) == ("repo-x", None, "no item named", None)


def test_a_client_timeout_renders_blind_with_the_exception_type_named():
    _, current = run(**{"work.project.context": timeout})
    panel, repositories = pickup(current, [])
    assert panel["kind"] == "BLIND" and panel["reason"] == "authority.work: ReadTimeout" and repositories is None
    assert current.degraded("authority.work") == "ReadTimeout"
    doc = generate(estate(), Authority(FakeAuthorityClient(results=RESULTS | {"work.project.context": timeout}), lambda: True),
                   REGISTRY, NOW, tags=lambda: TAGS)
    assert "PICK UP HERE   BLIND(authority.work: ReadTimeout)" in render_text.render(doc, NOW)


def test_degradation_reasons_are_never_empty():
    assert describe(ValueError()) == "ValueError" and describe(ConnectionError("refused")) == "ConnectionError: refused"
    assert describe(SourceUnavailable("worded reason")) == "worded reason" and describe(SourceUnavailable()) == "SourceUnavailable"


def test_after_one_boundary_timeout_no_further_boundary_reads_are_sent():
    client, current = run(**{"work.read.handoff": timeout})
    panel, _ = pickup(current, [])
    assert {r["ref"]: r["boundary"] for r in panel["rows"]}["repo-gamma#305"] == "NONE"
    assert [r["boundary"] for r in panel["rows"] if r["ref"] != "repo-gamma#305"] == ["UNDETERMINED"] * 4
    assert len(client.invoked) == 2


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
    _, current = run()
    panel, repositories = pickup(current, [])
    scope = blind_spots(current, repositories, panel)["scope"]["served"]["value"]
    assert scope["undeclared"] == ["kctl"] and scope["not_served"] == ["sprintctl"]
