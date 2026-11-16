"""Protected pointer preparation never replaces evaluation or runtime isolation."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "resident_evolution.py"
SPEC = importlib.util.spec_from_file_location("resident_evolution_under_test", SCRIPT)
EVOLUTION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVOLUTION)
TRUSTED = {"protected-evaluator"}
CHECKS = {key: "passed" for key in (
    "startup", "context", "isolation", "recovery", "state_compatibility", "monotonic_preserved"
)}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    path.chmod(0o600)


def addressed(root, kind, record):
    identity = EVOLUTION.record_digest(record)
    write_json(root / kind / f"{identity}.json", record)
    return identity


@pytest.fixture
def root(tmp_path):
    tmp_path.chmod(0o700)
    for name in ("receipts", "states"):
        (tmp_path / name).mkdir(mode=0o700)
    boundary = {"schema": "resident-boundary-observation/v1", "sources": {
        name: {"owner": f"existing-{name}-owner", "revision": "r1", "sha256": digest(name)}
        for name in ("budget", "effects", "corrections")
    }}
    write_json(tmp_path / "boundary.json", boundary)
    return tmp_path


def prepare(root, *, candidate="candidate-a", config="config-a", action="activate", expected=None,
            state_changes=None, receipt_changes=None):
    boundary_digest = EVOLUTION.record_digest(json.loads((root / "boundary.json").read_text()))
    state = {"schema": "resident-state-manifest/v1", "candidate_sha256": digest(candidate),
             "config_sha256": digest(config), "state_generation": "fixture-state-generation",
             "preserved_boundary_sha256": boundary_digest,
             "snapshots": [{"owner": "derived-memory", "revision": "snapshot-1", "sha256": digest("snapshot")}]}
    state.update(state_changes or {})
    state_digest = addressed(root, "states", state)
    now = datetime.now(timezone.utc)
    receipt = {"schema": "resident-evaluation/v1", "evaluator_id": "protected-evaluator", "decision": "pass",
               "action": action, "candidate_sha256": digest(candidate), "config_sha256": digest(config),
               "state_manifest_sha256": state_digest, "boundary_sha256": boundary_digest,
               "expected_pointer_digest": expected, "checks": dict(CHECKS),
               "observed_at": (now - timedelta(seconds=30)).isoformat(),
               "valid_until": (now + timedelta(minutes=5)).isoformat()}
    receipt.update(receipt_changes or {})
    return addressed(root, "receipts", receipt)


def transition(root, receipt, expected=None, action="activate", trusted=TRUSTED):
    return EVOLUTION.transition_pointer(root, receipt_digest=receipt, expected_pointer_digest=expected,
                                        trusted_evaluator_ids=trusted, action=action)


def test_first_selection_binds_evidence_and_replays_without_runtime_claim(root):
    receipt = prepare(root)
    result = transition(root, receipt)
    pointer = result["pointer"]
    assert pointer["generation"] == 1
    assert pointer["candidate_sha256"] == digest("candidate-a")
    assert pointer["config_sha256"] == digest("config-a")
    assert pointer["evaluation_sha256"] == receipt
    assert pointer["previous_pointer_digest"] is None
    assert result["runtime_activated"] is False
    assert result["authorizes_effects"] is False
    assert result["replayed"] is False
    assert EVOLUTION.read_pointer(root) == pointer
    replay = transition(root, receipt)
    assert replay == {**result, "replayed": True}
    assert len(list((root / "pointers").glob("*.json"))) == 1


def test_receipt_missing_and_untrusted_evaluator_fail_closed(root):
    with pytest.raises(FileNotFoundError):
        transition(root, digest("missing"))
    receipt = prepare(root, receipt_changes={"evaluator_id": "candidate-self"})
    with pytest.raises(ValueError, match="does not qualify"):
        transition(root, receipt)
    assert EVOLUTION.read_pointer(root) is None


@pytest.mark.parametrize("changes", [
    {"decision": "fail"}, {"action": "rollback"}, {"expected_pointer_digest": "f" * 64},
    {"checks": {**CHECKS, "recovery": "skipped"}},
    {"checks": {key: value for key, value in CHECKS.items() if key != "isolation"}},
])
def test_incomplete_or_different_evaluation_cannot_select(root, changes):
    receipt = prepare(root, receipt_changes=changes)
    with pytest.raises(ValueError):
        transition(root, receipt)
    assert EVOLUTION.read_pointer(root) is None


@pytest.mark.parametrize("changes", [
    {"candidate_sha256": digest("other-code")}, {"config_sha256": digest("other-config")},
    {"preserved_boundary_sha256": digest("old-boundary")},
])
def test_state_must_match_exact_code_config_and_monotonic_boundary(root, changes):
    receipt = prepare(root, state_changes=changes)
    with pytest.raises(ValueError, match="do not match"):
        transition(root, receipt)
    assert EVOLUTION.read_pointer(root) is None


@pytest.mark.parametrize("future", [False, True])
def test_receipt_must_be_currently_valid(root, future):
    now = datetime.now(timezone.utc)
    changes = ({"observed_at": (now + timedelta(minutes=5)).isoformat()} if future else
               {"valid_until": (now - timedelta(minutes=5)).isoformat()})
    receipt = prepare(root, receipt_changes=changes)
    with pytest.raises(ValueError, match="time-valid"):
        transition(root, receipt)


def test_boundary_change_invalidates_previous_evaluation(root):
    receipt = prepare(root)
    boundary = json.loads((root / "boundary.json").read_text())
    boundary["sources"]["corrections"].update(revision="r2", sha256=digest("retracted-source"))
    write_json(root / "boundary.json", boundary)
    with pytest.raises(ValueError, match="boundary changed"):
        transition(root, receipt)


def test_protected_state_record_cannot_be_changed_under_its_digest(root):
    receipt = prepare(root)
    state = next((root / "states").glob("*.json"))
    record = json.loads(state.read_text())
    record["state_generation"] = "tampered"
    write_json(state, record)
    with pytest.raises(ValueError, match="record digest mismatch"):
        transition(root, receipt)


@pytest.mark.parametrize("attack", ["group-write", "symlink", "hardlink"])
def test_unprotected_receipt_paths_are_rejected(root, attack):
    receipt = prepare(root)
    path = root / "receipts" / f"{receipt}.json"
    if attack == "group-write":
        path.chmod(0o660)
    elif attack == "symlink":
        moved = root / "receipt-original.json"
        path.rename(moved)
        path.symlink_to(moved)
    else:
        os.link(path, root / "receipt-alias.json")
    with pytest.raises((ValueError, OSError)):
        transition(root, receipt)
    assert EVOLUTION.read_pointer(root) is None


def test_writable_or_symlinked_protected_root_is_rejected(root):
    receipt = prepare(root)
    root.chmod(0o770)
    with pytest.raises(ValueError, match="not writable"):
        transition(root, receipt)
    root.chmod(0o700)
    alias = root.parent / f"{root.name}-alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError, match="without symlinks"):
        transition(alias, receipt)


def test_competing_selections_have_one_winner_and_a_cas_conflict(root):
    receipts = [prepare(root, candidate=f"candidate-{number}") for number in range(2)]

    def attempt(receipt):
        try:
            return transition(root, receipt)
        except EVOLUTION.TransitionConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, receipts))
    assert sum(isinstance(item, EVOLUTION.TransitionConflict) for item in outcomes) == 1
    winner = next(item for item in outcomes if isinstance(item, dict))
    assert EVOLUTION.read_pointer(root) == winner["pointer"]
    assert len(list((root / "pointers").glob("*.json"))) == 1


def test_rollback_requires_previously_selected_pair_and_compatible_current_state(root):
    first = transition(root, prepare(root))["pointer"]
    second = transition(root, prepare(root, candidate="candidate-b", config="config-b", expected=first["digest"]),
                        first["digest"])["pointer"]
    never_selected = prepare(root, candidate="candidate-never-selected", action="rollback", expected=second["digest"])
    with pytest.raises(ValueError, match="not previously selected"):
        transition(root, never_selected, second["digest"], "rollback")

    old_boundary_digest = second["boundary_sha256"]
    boundary = json.loads((root / "boundary.json").read_text())
    for name in ("budget", "effects", "corrections"):
        boundary["sources"][name].update(revision="r2", sha256=digest(f"new-{name}"))
    write_json(root / "boundary.json", boundary)
    boundary_bytes = (root / "boundary.json").read_bytes()
    stale_state = prepare(root, action="rollback", expected=second["digest"],
                          state_changes={"preserved_boundary_sha256": old_boundary_digest})
    with pytest.raises(ValueError, match="do not match"):
        transition(root, stale_state, second["digest"], "rollback")
    assert EVOLUTION.read_pointer(root) == second

    qualified = prepare(root, action="rollback", expected=second["digest"])
    rollback = transition(root, qualified, second["digest"], "rollback")["pointer"]
    assert rollback["generation"] == 3
    assert rollback["candidate_sha256"] == first["candidate_sha256"]
    assert rollback["config_sha256"] == first["config_sha256"]
    assert rollback["state_manifest_sha256"] != first["state_manifest_sha256"]
    assert rollback["boundary_sha256"] != first["boundary_sha256"]
    assert (root / "boundary.json").read_bytes() == boundary_bytes


@pytest.mark.parametrize("owner", ["existing-budget-owner", "existing-effects-owner", "existing-corrections-owner"])
def test_monotonic_owners_must_never_appear_in_rollback_snapshots(root, owner):
    receipt = prepare(root, state_changes={
        "snapshots": [{"owner": owner, "revision": "old", "sha256": digest("old")}]})
    with pytest.raises(ValueError, match="exclude the preserved"):
        transition(root, receipt)


def test_duplicate_snapshot_owner_is_ambiguous_and_rejected(root):
    snapshot = {"owner": "memory", "revision": "r1", "sha256": digest("one")}
    receipt = prepare(root, state_changes={"snapshots": [snapshot, copy.deepcopy(snapshot)]})
    with pytest.raises(ValueError, match="unique"):
        transition(root, receipt)


def test_interrupted_current_publication_leaves_prior_pointer_and_can_retry(root, monkeypatch):
    first = transition(root, prepare(root))["pointer"]
    receipt = prepare(root, candidate="candidate-b", expected=first["digest"])
    replace = os.replace

    def interrupted(source, destination, **kwargs):
        if destination == "current.json":
            raise OSError("simulated process interruption before current replacement")
        return replace(source, destination, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(EVOLUTION.os, "replace", interrupted)
        with pytest.raises(OSError, match="simulated process interruption"):
            transition(root, receipt, first["digest"])
    assert EVOLUTION.read_pointer(root) == first
    assert len(list((root / "pointers").glob("*.json"))) == 2
    recovered = transition(root, receipt, first["digest"])
    assert recovered["pointer"]["generation"] == 2
    assert recovered["replayed"] is False
    assert all(path.stat().st_nlink == 1 for path in (root / "pointers").glob("*.json"))
    assert not list(root.rglob(".staging-*"))


def test_stale_expected_pointer_cannot_overwrite_new_generation(root):
    first = transition(root, prepare(root))["pointer"]
    stale = prepare(root, candidate="stale", expected=None)
    before = (root / "current.json").read_bytes()
    with pytest.raises(EVOLUTION.TransitionConflict):
        transition(root, stale)
    assert EVOLUTION.read_pointer(root) == first
    assert (root / "current.json").read_bytes() == before


def test_corrupt_history_cannot_supply_rollback_ancestry(root):
    first = transition(root, prepare(root))["pointer"]
    second = transition(root, prepare(root, candidate="candidate-b", expected=first["digest"]), first["digest"])["pointer"]
    archive = root / "pointers" / f"{first['digest']}.json"
    record = json.loads(archive.read_text())
    record["candidate_sha256"] = digest("tampered")
    write_json(archive, record)
    receipt = prepare(root, action="rollback", expected=second["digest"])
    with pytest.raises(ValueError, match="pointer digest mismatch"):
        transition(root, receipt, second["digest"], "rollback")
