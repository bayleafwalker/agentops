"""Panels 2 and 7: the served pick-up answer over the project-1 shape, and the BLIND paths."""

import httpx

from fakes import FakeAuthorityClient, fixture
from operator_projection import render_text
from operator_projection.evaluators import Move
from operator_projection.generate import UNCONTRACTED, Run, blind_spots, candidates_of, describe, entries, generate, pickup
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
    assert panel["counts"]["value"] == {"needs_you": 4, "stale_holds": 2, "active_no_holder": 1, "ready": 2}
    assert panel["overflow"] == 4  # 9 counted items - 5 rows; repo-beta#202 shares repo-beta#201's conflict and yields its row
    assert [(r["ref"], r["class"], r["boundary"]) for r in panel["rows"]] == [
        ("repo-beta#201", "NEEDS YOU", "NONE"), ("repo-alpha#104", "NEEDS YOU", "HANDOFF"), ("repo-beta#203", "NEEDS YOU", "CONTEXT"),
        ("repo-gamma#305", "STALE HOLD", "NONE"), ("repo-alpha#103", "STALE HOLD", "HANDOFF")]
    conflict, stale = panel["rows"][0], panel["rows"][4]
    assert (conflict["next_action"], conflict["detail"], conflict["holder"], conflict["age"], conflict["moved_since_touch"]) == (
        "waits on an open dependency", "dependency-blocked · 2 items", "not contracted", UNCONTRACTED, UNCONTRACTED)
    assert panel["rows"][3]["detail"] is None
    assert (stale["next_action"], stale["age"], stale["moved_since_touch"], stale["holder"]) == ("stale alpha work", 4, 1, "not contracted")
    assert repositories == ["agentops", "vuoro", "kctl"]
    assert {op for op, _ in client.invoked} <= READ_OPS and len(client.invoked) == 7


def test_project_context_is_read_without_repo_id_and_boundary_reads_carry_the_rows_repo():
    client, current = run()
    pickup(current, [])
    assert client.invoked[0] == ("work.project.context", {}) and client.repo_ids[0] is None
    scoped = list(zip(client.invoked[1:], client.repo_ids[1:]))
    assert all(op != "work.project.context" for (op, _), _ in scoped)
    beta = [("work.read.handoff", 12, "repo-beta"), ("work.read.context-candidates", 12, "repo-beta")]
    assert [(op, args["sprint_id"], repo) for (op, args), repo in scoped] == [
        *beta, ("work.read.handoff", 11, "repo-alpha"), *beta, ("work.read.handoff", 11, "repo-alpha")]  # repo-gamma: no active sprint


def test_mapping_uses_only_contracted_fields():
    found = dict((item["ref"], (cls, item)) for cls, item in candidates_of(fixture("project-context.json")))
    assert found["repo-gamma#306"][0] == "ACTIVE, NO HOLDER" and found["repo-gamma#306"][1]["holder"] == "no holder"
    assert found["repo-alpha#104"][0] == "NEEDS YOU"  # one row per item, at its highest class
    assert found["repo-beta#201"][0] == "NEEDS YOU"  # the second item of a conflict is counted, not only item_ids[0]
    assert [ref for ref, (cls, _) in found.items() if cls == "READY"] == ["repo-alpha#106", "repo-beta#207"]
    assert "repo-beta#208" not in found  # kind no-action is not ready work
    [bare] = entries("conflicts", {"kind": "stale-work", "severity": "warning", "summary": "no item named", "item_ids": [], "origin_repo": "repo-x"})
    assert (bare["ref"], bare["id"], bare["text"], bare["detail"], bare["idle_seconds"]) == ("repo-x:stale-work", None, "no item named", "stale-work · 0 items", None)
    context = {"conflicts": [{"kind": k, "severity": "warning", "summary": k, "item_ids": [], "origin_repo": "repo-x"} for k in ("stale-work", "blocked-work")]}
    assert [(cls, item["ref"]) for cls, item in candidates_of(context)] == [("NEEDS YOU", "repo-x:blocked-work"), ("NEEDS YOU", "repo-x:stale-work")]


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
    assert [r["boundary"] for r in panel["rows"]] == ["UNDETERMINED"] * 3 + ["NONE", "UNDETERMINED"]  # repo-gamma needs no read
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


def conflict(kind, severity, repo, ids):
    return {"kind": kind, "reason_code": None, "severity": severity, "summary": f"synthetic {kind}", "item_ids": ids, "origin_repo": repo}


# The production undercount, synthetic: four conflicts name 14 distinct items; two of them share repo-b#50, which is also
# the only stale, active-unreserved and resume item. Taking item_ids[0] and de-duplicating showed needs_you 3.
MULTI = {"contract_version": "project-1", "sprints": [], "blocked_items": [], "active_reservations": [], "ready_items": [],
         "conflicts": [conflict("unreserved-active-work", "warning", "repo-b", [50]),
                       conflict("dependency-blocked", "error", "repo-a", [1, 2, 3, 4, 5, 6]),
                       conflict("dependency-blocked", "error", "repo-b", [11, 12, 13, 14, 15, 16]),
                       conflict("stale-work", "warning", "repo-b", [50, 16, 17])],
         "stale_items": [{"id": 50, "title": "stale", "status": "active", "track": "t", "idle_seconds": 90000, "origin_repo": "repo-b"}],
         "active_unreserved_items": [{"id": 50, "title": "unheld", "track": "t", "origin_repo": "repo-b"}],
         "next_actions": [{"kind": "resume-unreserved-active-item", "summary": "resume", "item_id": 50, "reason": "r", "origin_repo": "repo-b"},
                          {"kind": "start-ready-item", "summary": "start", "item_id": 7, "reason": "r", "origin_repo": "repo-c"},
                          {"kind": "unblock-dependent-work", "summary": "unblock", "item_id": 1, "reason": "r", "origin_repo": "repo-a"},
                          {"kind": "no-action", "summary": "nothing", "item_id": None, "reason": "r", "origin_repo": "repo-c"}],
         "repositories": [{"origin_repo": r, "status": "available", "context": {}} for r in ("repo-a", "repo-b", "repo-c")]}


def test_every_item_a_conflict_names_is_counted_once_at_its_highest_class():
    client, current = run(**{"work.project.context": MULTI})
    panel, _ = pickup(current, [])
    assert panel["counts"]["value"] == {"needs_you": 14, "stale_holds": 0, "active_no_holder": 0, "ready": 1}
    assert len(panel["rows"]) == 5 and panel["overflow"] == 15 - 5
    # One row per conflict before a conflict's further items: the 6-item conflict no longer fills every row.
    assert [(r["ref"], r["detail"]) for r in panel["rows"]] == [
        ("repo-a#1", "dependency-blocked · 6 items"), ("repo-b#11", "dependency-blocked · 6 items"), ("repo-b#17", "stale-work · 3 items"),
        ("repo-b#50", "unreserved-active-work · 1 items; stale-work · 3 items"), ("repo-c#7", None)]
    # repo-b#16 is in the repo-b dependency-blocked and stale-work conflicts; the row names both, most severe first.
    shared = dict((item["ref"], item["detail"]) for _, item in candidates_of(MULTI))
    assert shared["repo-b#16"] == "dependency-blocked · 6 items; stale-work · 3 items" and shared["repo-b#17"] == "stale-work · 3 items"
    assert len(client.invoked) == 1  # no active sprint anywhere: no boundary reads
    text = render_text.render(generate(estate(), Authority(FakeAuthorityClient(results=RESULTS | {"work.project.context": MULTI}), lambda: True),
                                       REGISTRY, NOW, tags=lambda: TAGS), NOW)
    assert "needs you 14 · stale holds 0 · active, no holder 0 · ready 1" in text
    assert " repo-a#1  NEEDS YOU  synthetic dependency-blocked · dependency-blocked · 6 items · not contracted · NONE" in text
