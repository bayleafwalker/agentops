"""P4: a retired component renders as a RETIRED move and a repaired divergence, never as a hazard or a durability loss."""

from fakes import MemoryGit
from test_generate import served, uncelled
from operator_projection import render_text
from operator_projection.evaluators import Row, classify, durability_rows
from operator_projection.generate import generate
from world import COCKPIT, NOW, REGISTRY, S, TAGS, estate


def test_a_retired_store_is_no_member_and_its_removal_is_retired_not_durability_down():
    assert "cockpit.reconciliation-state" not in durability_rows(None, {"receipt_path": "/x"}, True)
    assert classify("durability.store", {"s": Row(True, "D2")}, {}) == [("s", "RETIRED")]
    assert classify("durability.store", {}, {"s": Row(True, "D0")}) == []


def test_post_retirement_render_has_no_false_hazard_and_no_degraded_source():
    before, after = (generate(estate(retired=r), served(), REGISTRY, NOW, tags=lambda: TAGS) for r in (False, True))
    assert ("DIVERGED", "vuoro-service image") in {(r["kind"], r["subject"]) for r in before["panels"]["hazards"]["rows"]}
    rows = after["panels"]["hazards"]["rows"]
    assert all(r["kind"] != "DIVERGED" for r in rows) and "agent-cockpit sidecar" not in render_text.render(after)
    moves = after["panels"]["moves"]
    assert moves["counts"]["value"]["RETIRED"] == 1 and moves["counts"]["value"]["DURABILITY-DOWN"] == 0
    assert {"at": "c3", "class": "RETIRED", "vocabulary": "durability.store", "members": ["cockpit.reconciliation-state"]}.items() <= next(
        r for r in moves["rows"] if r["class"] == "RETIRED").items()
    assert moves["recall"]["value"]["misses"] == [] and uncelled(after["panels"]) == []
    assert all(s["degraded"] is None for s in after["sources"])
    assert "· 1 retired)" in render_text.render(after)


def test_a_present_manifest_without_a_digest_still_diverges():
    git = estate()
    head = git.history["appservice"][-1][0]
    git.files["appservice"][head] = git.files["appservice"][head] | {COCKPIT: "spec:\n  image: ghcr.io/x/vuoro-service:0.1.41\n"}
    doc = generate(MemoryGit(git.files, git.history), served(), REGISTRY, NOW, tags=lambda: TAGS)
    diverged = next(r for r in doc["panels"]["hazards"]["rows"] if r["kind"] == "DIVERGED" and r["subject"] == "vuoro-service image")
    assert "agent-cockpit sidecar none" in diverged["detail"] and S["shared_deployment"]
