"""Panels 4 and 6; test 5 (deployed precedence: production.json in the ConfigMap only)."""

import hashlib
import json

from fakes import FakeAuthorityClient
from operator_projection.generate import Run, may_do, moves
from operator_projection.sources import Authority
from world import BINDINGS, NOW, REGISTRY, TAGS, estate, policy


def run(git):
    return Run(git, Authority(FakeAuthorityClient(), lambda: False), REGISTRY, NOW, lambda: TAGS)


def test_moves_over_the_trailing_window_rank_gains_before_contract_changes():
    panel = moves(run(estate()), [])
    assert panel["window"] == {"start": "2026-08-15T12:00:00Z", "end": "2026-09-14T12:00:00Z"}
    assert [(r["class"], r["vocabulary"], r["at"]) for r in panel["rows"]] == [
        ("GAINED", "credbroker.binding", "c2"), ("CONTRACT-CHANGE", "authority.service_release", "c1")]
    assert panel["counts"]["value"]["GAINED"] == 1 and panel["attributed"]["value"] == "0/2"
    assert panel["recall"]["value"] == {"boundary_commits": 2, "mapped": 2, "misses": []}
    assert panel["zero"] is None and panel["overflow"] == 0


def test_a_window_with_no_moves_carries_its_denominators_and_debts():
    hazard = {"kind": "UNREACHABLE", "subject": "audit record_class=decision", "since": "2026-07-16", "flags": []}
    claimed = {"kind": "ORPHAN", "subject": "work:x", "since": None, "flags": ["CLAIMED-UNATTESTED"]}
    panel = moves(run(estate(moves=False)), [hazard, claimed])
    assert panel["rows"] == [] and panel["counts"]["value"] == dict.fromkeys(panel["counts"]["value"], 0)
    zero = panel["zero"]
    assert zero["boundary_commits"] == 1 and zero["vocabularies"] == 7
    assert zero["unreachable"] == {"count": 1, "oldest_days": 60, "subject": "audit record_class=decision"}
    assert zero["unrepaired"] == {"count": 0, "oldest_days": None, "subject": None}
    assert zero["spend"]["kind"] == "BLIND"


def test_may_do_reads_the_deployed_configmap_only():
    git = estate()
    panel = may_do(run(git))
    value = panel["policy"]["value"]
    assert value["commit"] == "c2" and value["receipts"] == "D2"
    assert value["hosts"]["workstation"] == {"trust_profile": "interactive", "repositories": 1, "capabilities": {"repo.read": 1, "repo.write": 1}, "unusable": 0}
    assert value["hosts"]["devbox"]["repositories"] == 1
    source = policy(BINDINGS + [{"host_id": "devbox", "repository_id": "repo_b", "capabilities": ["repo.read"]}])["policy"]
    expected = "sha256:" + hashlib.sha256(json.dumps(source, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert value["policy_revision"] == expected
    assert not any("cred-broker/config/" in call[3] for call in git.calls)
    assert panel["grants"]["kind"] == "BLIND" and panel["admitted_policy_revision"]["kind"] == "BLIND"
