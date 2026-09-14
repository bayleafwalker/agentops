import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from replay import (  # noqa: E402
    Move,
    Row,
    authorized,
    broker_rows,
    classify,
    durability_rows,
    lock_rows,
    record_classes,
    score,
    service_rows,
)

DIGEST = "sha256:" + "a" * 64
DEPLOYMENT = f"spec:\n  replicas: {{replicas}}\n  template:\n    image: ghcr.io/x/vuoro-service@{DIGEST}\n"


def test_service_is_reachable_only_with_replicas_and_no_suspend():
    assert service_rows(DEPLOYMENT.format(replicas=1), None) == {"vuoro-shared": Row(True, DIGEST)}
    assert service_rows(DEPLOYMENT.format(replicas=0), None)["vuoro-shared"].passed is False
    assert service_rows(DEPLOYMENT.format(replicas=1), "spec:\n  suspend: true\n")["vuoro-shared"].passed is False
    assert service_rows(None, None) == {}


def test_v1_domains_and_v2_lock_ids_share_member_identity():
    v1 = {"adapters": [{"domain": "work", "source_revision": "r1", "distribution_version": "0.2.0"}]}
    v2 = {"release_locks": [{"lock_id": "work-adapter", "source_revision": "r1", "distribution_version": "0.2.0"}]}
    assert lock_rows(v1) == lock_rows(v2) == {"work-adapter": Row(True, "r1", "0.2.0")}


def test_record_classes_from_tuple_or_single_literal_check():
    assert record_classes('RECORD_CLASSES = ("observation", "decision")\n') == {"observation", "decision"}
    assert record_classes('        raise ValueError("record_class must be observation")\n') == {"observation"}


def forgejo_policy(audiences, active=True, per_repository=True):
    provider = {"repository_audiences": audiences} if per_repository else {"audiences": audiences}
    return {
        "providers": {"forgejo": provider},
        "repositories": [{"repository_id": "r", "provider": "forgejo"}],
        "policy": {
            "hosts": [{"host_id": "h", "active": active}],
            "bindings": [{"host_id": "h", "repository_id": "r", "capabilities": ["pr.merge"]}],
            "capabilities": {"pr.merge": {"ttl_seconds": 300}},
        },
    }


def test_forgejo_binding_needs_a_real_audience_and_an_active_host():
    real = {"pr.merge": {"r": "0123456789abcdef"}}
    assert broker_rows(forgejo_policy(real))["credbroker.binding"] == {"h|r|pr.merge": Row(True)}
    assert not broker_rows(forgejo_policy({"pr.merge": {"r": "REPLACE_WITH_AUDIENCE"}}))["credbroker.binding"]["h|r|pr.merge"].passed
    assert not broker_rows(forgejo_policy(real, active=False))["credbroker.binding"]["h|r|pr.merge"].passed
    assert authorized(forgejo_policy({"pr.merge": "aud"}, per_repository=False), "forgejo", "pr.merge", "other")
    assert not authorized(forgejo_policy(real), None, "pr.merge", "r")


def test_durability_needs_both_the_path_and_the_volume():
    assert durability_rows(True, {"receipt_path": "/x"}, True) == {
        "cockpit.reconciliation-state": Row(True, "D2"),
        "credbroker.receipts": Row(True, "D2"),
    }
    assert durability_rows(False, {"receipt_path": "/x"}, False)["credbroker.receipts"].value == "D0"


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ({}, {"m": Row(True, "1")}, [("m", "GAINED")]),
        ({}, {"m": Row(False, "1")}, []),
        ({"m": Row(True, "1")}, {}, [("m", "FORECLOSED")]),
        ({"m": Row(False, "1")}, {}, []),
        ({"m": Row(True, "1")}, {"m": Row(False, "2")}, [("m", "REGRESSED"), ("m", "CONTRACT-CHANGE")]),
        ({"m": Row(False, "1")}, {"m": Row(True, "1")}, [("m", "GAINED")]),
        ({"m": Row(True, "1")}, {"m": Row(True, "1")}, []),
        ({"m": Row(False, "1")}, {"m": Row(False, "2")}, []),
    ],
)
def test_classify_can_do_ledger(before, after, expected):
    assert classify("composition.release_lock", before, after) == expected


def test_classify_durability_moves_only_on_rung_change():
    assert classify("durability.store", {"s": Row(True, "D0")}, {"s": Row(True, "D2")}) == [("s", "DURABILITY-UP")]
    assert classify("durability.store", {"s": Row(True, "D2")}, {"s": Row(True, "D0")}) == [("s", "DURABILITY-DOWN")]
    assert classify("durability.store", {"s": Row(True, "D2")}, {"s": Row(True, "D2")}) == []


def move(vocabulary, member, cls, boundary):
    return Move(vocabulary, member, cls, boundary + "00000000", "2026-08-01T00:00:00+00:00")


def test_score_counts_groups_and_checks_members_separately():
    truth = {"moves": [
        {"v": "a", "at": "11111111", "class": "GAINED", "members": ["x"]},
        {"v": "a", "at": "22222222", "class": "GAINED", "members": "*", "count": 2},
        {"v": "b", "at": "33333333", "class": "REGRESSED", "members": ["y"]},
        {"v": "c", "at": "44444444", "class": "FORECLOSED", "members": "*", "scored": False},
    ]}
    produced = [
        move("a", "x", "GAINED", "11111111"),
        move("a", "p", "GAINED", "22222222"),
        move("b", "y", "CONTRACT-CHANGE", "33333333"),
    ]
    result = score(truth, produced)
    assert (result["expected"], result["produced"]) == (3, 3)
    assert result["recall"] == pytest.approx(2 / 3)
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["misses"] == [("b", "33333333", "REGRESSED")]
    assert result["false_positives"] == [("b", "33333333", "CONTRACT-CHANGE")]
    assert [m["group"] for m in result["member_mismatches"]] == [("a", "22222222", "GAINED")]


def test_score_rejects_duplicate_truth_groups():
    row = {"v": "a", "at": "11111111", "class": "GAINED", "members": ["x"]}
    with pytest.raises(ValueError, match="duplicate"):
        score({"moves": [row, row]}, [])
