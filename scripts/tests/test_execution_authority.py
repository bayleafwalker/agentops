from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("execution_authority", ROOT / "scripts/execution_authority.py")
assert SPEC is not None and SPEC.loader is not None
ea = importlib.util.module_from_spec(SPEC)
sys.modules["execution_authority"] = ea
SPEC.loader.exec_module(ea)

DEVBOX = ROOT / "environment-record/devbox-vm.vuoro-shared.json"
NOW = 1_800_000_000.0
PUBLISH = "agentops.dispatch.publish-v1"


def _record() -> dict:
    return json.loads(DEVBOX.read_text(encoding="utf-8"))


class FakeOwner:
    def __init__(self, *, run: dict | None = None, run_error: str | None = None,
                 attempt: dict | None = None, attempt_error: str | None = None) -> None:
        self.run = run if run is not None else {"run_id": "run_1", "grant_id": "grant_1"}
        self.run_error = run_error
        self.attempt = attempt if attempt is not None else {"state": "accepted", "events": []}
        self.attempt_error = attempt_error
        self.calls: list[tuple[str, str]] = []

    def resolve_run(self, repo_id: str, run_id: str) -> dict:
        self.calls.append(("work.run.resolve-v1", run_id))
        if self.run_error:
            raise ea.OwnerRefusal(self.run_error)
        return self.run

    def attempt_get(self, repo_id: str, attempt_id: str) -> dict:
        self.calls.append(("work.effect.attempt-get-v1", attempt_id))
        if self.attempt_error:
            raise ea.OwnerRefusal(self.attempt_error)
        return self.attempt


def _req(operation: str = "work.effect.attempt-open-v1", **overrides) -> ea.ExecutionRequest:
    fields = dict(operation=operation, repo_id="agentops", run_id="run_1", granted_at=NOW - 60,
                  grant_id="grant_1")
    fields.update(overrides)
    return ea.ExecutionRequest(**fields)


def _decide(request: ea.ExecutionRequest, owner: FakeOwner | None = None, record: dict | None = None) -> ea.Decision:
    return ea.decide(record or _record(), request, FakeOwner() if owner is None else owner, now=NOW)


def test_scoped_attempt_open_is_allowed() -> None:
    decision = _decide(_req())
    assert decision.allowed and decision.code == "scoped-execution"


def test_standing_read_needs_no_run_or_grant() -> None:
    owner = FakeOwner()
    decision = ea.decide(_record(), ea.ExecutionRequest("work.run.resolve-v1", "any-repo"), owner, now=NOW)
    assert decision.allowed and decision.tier == "standing-read"
    assert owner.calls == []


def test_missing_authority_block_refuses() -> None:
    record = _record()
    del record["authority"]
    assert _decide(_req(), record=record).code == "no-authority-block"


def test_invalid_authority_block_refuses() -> None:
    record = _record()
    record["authority"]["scoped_execution"]["max_ttl_seconds"] = 0
    assert _decide(_req(), record=record).code == "authority-invalid"


def test_operation_not_in_scope_refuses() -> None:
    decision = _decide(_req("work.item.delete-v1"))
    assert not decision.allowed and decision.code == "operation-not-in-scope"


def test_repository_not_in_scope_refuses() -> None:
    assert _decide(_req(repo_id="sprintctl")).code == "repository-not-in-scope"


def test_ttl_expired_refuses() -> None:
    decision = _decide(_req(granted_at=NOW - 3600))
    assert decision.code == "ttl-expired"


def test_requested_ttl_shorter_than_max_is_honoured() -> None:
    assert _decide(_req(granted_at=NOW - 120, ttl_seconds=60)).code == "ttl-expired"


def test_ttl_over_maximum_refuses() -> None:
    assert _decide(_req(ttl_seconds=7200)).code == "ttl-exceeds-maximum"


def test_missing_grant_time_refuses() -> None:
    assert _decide(_req(granted_at=None)).code == "grant-time-missing"


def test_consequential_transition_needs_approval_ref() -> None:
    decision = _decide(_req("rollout.resume-v1"))
    assert decision.code == "approval-required" and decision.tier == "explicit-approval"
    assert _decide(_req("rollout.resume-v1", approval_ref="looks fine")).code == "approval-required"


def test_protected_publication_needs_approval_ref() -> None:
    assert _decide(_req("agentops.publication.protected-main-v1")).code == "approval-required"


def test_consequential_transition_with_approval_ref_is_allowed() -> None:
    decision = _decide(_req("rollout.resume-v1", approval_ref="approval:operator/2026-10-14#1"))
    assert decision.allowed and decision.code == "approved-transition"


def test_approved_transition_still_refuses_superseded_run() -> None:
    decision = _decide(_req("rollout.resume-v1", approval_ref="approval:op/1", successor_run_id="run_2"))
    assert decision.code == "run-superseded"


def test_locally_known_successor_supersedes_run() -> None:
    owner = FakeOwner()
    decision = _decide(_req(successor_run_id="run_2"), owner)
    assert decision.code == "run-superseded"
    assert owner.calls == []  # refused before any served call


def test_served_run_not_found_is_superseded() -> None:
    assert _decide(_req(), FakeOwner(run_error="run-not-found")).code == "run-superseded"


def test_rotated_grant_is_superseded() -> None:
    owner = FakeOwner(run={"run_id": "run_1", "grant_id": "grant_2"})
    assert _decide(_req(), owner).code == "run-superseded"


def test_owner_failure_fails_closed() -> None:
    assert _decide(_req(), FakeOwner(run_error="transport")).code == "owner-unavailable"


def test_no_owner_fails_closed() -> None:
    assert ea.decide(_record(), _req(), None, now=NOW).code == "run-unverified"


def test_missing_run_refuses() -> None:
    assert _decide(_req(run_id=None)).code == "run-missing"


def test_redeem_requires_accepted_attempt() -> None:
    ok = _decide(_req("work.effect.attempt-redeem-v1", attempt_id="att_1"))
    assert ok.allowed
    sealed = FakeOwner(attempt={"state": "sealed_unused", "events": []})
    assert _decide(_req("work.effect.attempt-redeem-v1", attempt_id="att_1"), sealed).code == "attempt-state-conflict"


def test_attempt_operation_without_attempt_id_refuses() -> None:
    assert _decide(_req("work.effect.attempt-redeem-v1")).code == "attempt-missing"


def test_publication_requires_redeemed_unreported_attempt() -> None:
    redeemed = FakeOwner(attempt={"state": "redeemed", "events": [{"kind": "redeemed"}]})
    assert _decide(_req(PUBLISH, attempt_id="att_1"), redeemed).allowed
    accepted = FakeOwner(attempt={"state": "accepted", "events": []})
    assert _decide(_req(PUBLISH, attempt_id="att_1"), accepted).code == "attempt-state-conflict"
    applied = FakeOwner(attempt={"state": "redeemed", "events": [{"kind": "application_report_received"}]})
    assert _decide(_req(PUBLISH, attempt_id="att_1"), applied).code == "attempt-already-applied"


def test_report_applied_refuses_duplicate_report() -> None:
    applied = FakeOwner(attempt={"state": "redeemed", "events": [{"kind": "application_report_received"}]})
    decision = _decide(_req("work.effect.attempt-report-applied-v1", attempt_id="att_1"), applied)
    assert decision.code == "attempt-already-applied"


def test_cli_refuses_without_profile(capsys: pytest.CaptureFixture[str]) -> None:
    code = ea.main(["--environment", str(DEVBOX), "--operation", PUBLISH, "--repo", "agentops",
                    "--run-id", "run_1", "--granted-at", str(9e12)])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["code"] == "run-unverified"


def test_record_is_not_mutated() -> None:
    record = _record()
    before = copy.deepcopy(record)
    _decide(_req(), record=record)
    assert record == before
