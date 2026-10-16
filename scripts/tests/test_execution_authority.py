from __future__ import annotations

import copy
import datetime as dt
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
REDEEM = "work.effect.attempt-redeem-v1"
REPORT = "work.effect.attempt-report-applied-v1"
RUN = "run_01JZZZZZZZZZZZZZZZZZZZZZZZ"
ATTEMPT = "attempt_01JZZZZZZZZZZZZZZZZZZZZZZZ"
COMMIT = "a" * 40
OPERATOR = "workstation-vuoro"


def _iso(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat()


def _record() -> dict:
    return json.loads(DEVBOX.read_text(encoding="utf-8"))


def served_resolve(grant_id: str = "grant_1") -> dict:
    """work.run.resolve-v1 result (sprintctl work_application._run_resolve)."""
    return {"repo_id": "agentops", "run_id": RUN, "principal_id": "devbox-agent-vuoro",
            "workspace_id": "ws-1", "client_id": None, "grant_id": grant_id}


def served_attempt(state: str = "accepted", kinds: tuple[str, ...] = ("attempt_authorization_accepted",),
                   opened_at: float = NOW - 60, grant_id: str = "grant_1", operation: str = "push_branch",
                   branch: str = "dispatch/publish-batch/intent_01JZZZZZZZZZZZZZZZZZZZZZZZ") -> dict:
    """work.effect.attempt-get-v1 result, field for field as sprintctl
    effect_attempt_pg.get_in_transaction / _event build it."""
    authorization = {
        "repo_id": "agentops", "attempt_id": ATTEMPT, "principal_id": "devbox-agent-vuoro",
        "workspace_id": "ws-1", "client_id": None, "grant_id": grant_id,
        "intent_id": "intent_01JZZZZZZZZZZZZZZZZZZZZZZZ", "intent_revision": 1,
        "canonical_intent_digest": "c" * 64, "work_item_id": 42, "expected_revision": "r1",
        "release_digest": "d" * 64,
        "target": {"operation": operation, "repository": "agentops",
                   "branch": branch, "commit_sha": COMMIT,
                   "base_commit": "b" * 40, "title_sha256": "e" * 64, "body_sha256": "f" * 64},
        "target_digest": "9" * 64, "acceptance": {}, "verification_binding": None,
    }
    payloads = {
        "attempt_authorization_accepted": {"authorization": authorization},
        "invocation_authorization_redeemed": {"target_digest": "9" * 64},
        "attempt_closed_without_redemption": {"target_digest": "9" * 64},
        "application_report_received": {"commit_sha": COMMIT, "pr_url": None},
    }
    events, previous = [], None
    for seq, kind in enumerate(kinds):
        digest = f"{seq:064d}"
        events.append({"repo_id": "agentops", "attempt_id": ATTEMPT, "event_seq": seq, "event_kind": kind,
                       "authorization_digest": "8" * 64, "previous_event_digest": previous,
                       "event_digest": digest, "payload": payloads[kind], "created_at": _iso(opened_at + seq)})
        previous = digest
    return {"repo_id": "agentops", "authorization": authorization, "authorization_digest": "8" * 64,
            "state": state, "events": events}


REDEEMED = ("attempt_authorization_accepted", "invocation_authorization_redeemed")
REPORTED = REDEEMED + ("application_report_received",)


def served_decision(decision_id: int = 7, *, kind: str = "accept", actor: str = OPERATOR,
                    rationale: str = f"approve rollout-resume repo=agentops run={RUN} commit={COMMIT}",
                    created_at: float = NOW - 60) -> dict:
    """One work_decision row in work.read.item-decisions."""
    return {"id": decision_id, "repo_id": "agentops", "kind": kind, "work_item_id": 42, "sprint_id": 1,
            "release_digest": None, "evidence_digests": [], "rationale": rationale, "actor": actor,
            "superseded_by_item_id": None, "legacy_source": None, "created_at": _iso(created_at)}


class FakeOwner:
    def __init__(self, *, run: dict | None = None, run_error: Exception | None = None,
                 attempt: dict | None = None, attempt_error: Exception | None = None,
                 decisions: list[dict] | None = None) -> None:
        self.run = run if run is not None else served_resolve()
        self.run_error = run_error
        self.attempt = attempt if attempt is not None else served_attempt()
        self.attempt_error = attempt_error
        self.decisions = decisions if decisions is not None else [served_decision()]
        self.consumed: dict[int, dict] = {}
        self.calls: list[str] = []

    def resolve_run(self, repo_id: str, run_id: str) -> dict:
        self.calls.append("work.run.resolve-v1")
        if self.run_error:
            raise self.run_error
        return self.run

    def attempt_get(self, repo_id: str, attempt_id: str) -> dict:
        self.calls.append("work.effect.attempt-get-v1")
        if self.attempt_error:
            raise self.attempt_error
        return self.attempt

    def item_decisions(self, repo_id: str, item_id: int) -> dict:
        self.calls.append("work.read.item-decisions")
        return {"repo_id": repo_id, "item_id": item_id, "status": "done", "resolution": None,
                "terminal_decision_id": None, "decisions": self.decisions}

    def consume_approval(self, repo_id: str, run_id: str, decision_id: int, use: dict) -> dict:
        """work.session-note.write-v1 keyed `approval-consume.<decision>`: the owner's
        idempotency ledger replays the same use and conflicts on any other."""
        self.calls.append("work.session-note.write-v1")
        previous = self.consumed.setdefault(decision_id, use)
        if previous != use:
            raise ea.OwnerRefusal("idempotency-conflict")
        return {"repo_id": repo_id, "run_id": run_id, "note_id": decision_id}


def _req(operation: str = "work.effect.attempt-open-v1", **overrides) -> ea.ExecutionRequest:
    fields = dict(operation=operation, repo_id="agentops", run_id=RUN, granted_at=NOW - 60, grant_id="grant_1")
    fields.update(overrides)
    return ea.ExecutionRequest(**fields)


def _decide(request: ea.ExecutionRequest, owner: FakeOwner | None = None, record: dict | None = None) -> ea.Decision:
    return ea.decide(record or _record(), request, FakeOwner() if owner is None else owner, now=NOW)


# ---------------------------------------------------------------- tiers and scope

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


def test_wildcard_grant_is_rejected_as_invalid_authority() -> None:
    record = _record()
    record["authority"]["scoped_execution"]["operations"].append("work.effect.*")
    assert _decide(_req(), record=record).code == "authority-invalid"


def test_operation_not_in_scope_refuses() -> None:
    decision = _decide(_req("work.item.delete-v1"))
    assert not decision.allowed and decision.code == "operation-not-in-scope"


def test_unlisted_attempt_operation_is_not_prefix_granted() -> None:
    assert _decide(_req("work.effect.attempt-rewrite-v1")).code == "operation-not-in-scope"


def test_repository_not_in_scope_refuses() -> None:
    assert _decide(_req(repo_id="sprintctl")).code == "repository-not-in-scope"


# ---------------------------------------------------------------- TTL

def test_ttl_expired_refuses() -> None:
    assert _decide(_req(granted_at=NOW - 3600)).code == "ttl-expired"


def test_requested_ttl_shorter_than_max_is_honoured() -> None:
    assert _decide(_req(granted_at=NOW - 120, ttl_seconds=60)).code == "ttl-expired"


def test_ttl_over_maximum_refuses() -> None:
    assert _decide(_req(ttl_seconds=7200)).code == "ttl-exceeds-maximum"


@pytest.mark.parametrize("ttl", [0, -5, True, 1.5])
def test_non_positive_or_non_integer_ttl_refuses(ttl) -> None:
    assert _decide(_req(ttl_seconds=ttl)).code == "ttl-invalid"


def test_missing_grant_time_refuses() -> None:
    assert _decide(_req(granted_at=None)).code == "grant-time-missing"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "1800000000"])
def test_non_finite_grant_time_refuses(value) -> None:
    assert _decide(_req(granted_at=value)).code == "grant-time-invalid"


def test_future_grant_time_beyond_skew_refuses() -> None:
    assert _decide(_req(granted_at=NOW + 61)).code == "grant-time-in-future"
    assert _decide(_req(granted_at=NOW + 30)).allowed


def test_attempt_bound_operation_uses_owner_issue_time_not_self_attested() -> None:
    stale = FakeOwner(attempt=served_attempt(opened_at=NOW - 7200))
    decision = _decide(_req(REDEEM, attempt_id=ATTEMPT, granted_at=NOW), stale)
    assert decision.code == "ttl-expired"
    fresh = FakeOwner(attempt=served_attempt(opened_at=NOW - 60))
    assert _decide(_req(REDEEM, attempt_id=ATTEMPT, granted_at=None), fresh).allowed


# ---------------------------------------------------------------- run and grant

def test_grant_id_is_required() -> None:
    assert _decide(_req(grant_id=None)).code == "grant-id-missing"


def test_locally_known_successor_supersedes_run() -> None:
    owner = FakeOwner()
    assert _decide(_req(successor_run_id="run_2"), owner).code == "run-superseded"
    assert owner.calls == []  # refused before any served call


def test_served_run_not_found_is_superseded() -> None:
    assert _decide(_req(), FakeOwner(run_error=ea.OwnerRefusal("run-not-found"))).code == "run-superseded"


def test_rotated_grant_is_superseded() -> None:
    assert _decide(_req(), FakeOwner(run=served_resolve(grant_id="grant_2"))).code == "run-superseded"


def test_owner_refusal_fails_closed() -> None:
    assert _decide(_req(), FakeOwner(run_error=ea.OwnerRefusal("forbidden"))).code == "owner-unavailable"


@pytest.mark.parametrize("error", [RuntimeError("boom"), OSError("conn"), KeyError("x")])
def test_any_client_error_fails_closed_without_raising(error) -> None:
    assert _decide(_req(), FakeOwner(run_error=error)).code == "owner-unavailable"
    redeem = _req(REDEEM, attempt_id=ATTEMPT)
    assert _decide(redeem, FakeOwner(attempt_error=error)).code == "owner-unavailable"


def test_malformed_owner_payload_fails_closed() -> None:
    assert _decide(_req(REDEEM, attempt_id=ATTEMPT), FakeOwner(attempt={"state": "accepted"})).code == "owner-unavailable"


def test_no_owner_fails_closed() -> None:
    assert ea.decide(_record(), _req(), None, now=NOW).code == "run-unverified"


def test_missing_run_refuses() -> None:
    assert _decide(_req(run_id=None)).code == "run-missing"


# ---------------------------------------------------------------- attempts and publication

def test_redeem_requires_accepted_attempt() -> None:
    assert _decide(_req(REDEEM, attempt_id=ATTEMPT)).allowed
    sealed = FakeOwner(attempt=served_attempt("sealed_unused", ("attempt_authorization_accepted", "attempt_closed_without_redemption")))
    assert _decide(_req(REDEEM, attempt_id=ATTEMPT), sealed).code == "attempt-state-conflict"


@pytest.mark.parametrize("operation", [REDEEM, "work.effect.attempt-seal-unused-v1", REPORT, PUBLISH])
def test_attempt_bound_operations_require_attempt_id(operation) -> None:
    assert _decide(_req(operation, commit_sha=COMMIT)).code == "attempt-missing"


def test_attempt_of_another_grant_is_refused() -> None:
    owner = FakeOwner(attempt=served_attempt(grant_id="grant_other"))
    assert _decide(_req(REDEEM, attempt_id=ATTEMPT), owner).code == "attempt-binding-mismatch"


def test_publication_requires_redeemed_unreported_attempt_for_the_same_commit() -> None:
    redeemed = FakeOwner(attempt=served_attempt("redeemed", REDEEMED))
    assert _decide(_req(PUBLISH, attempt_id=ATTEMPT, commit_sha=COMMIT), redeemed).allowed
    assert _decide(_req(PUBLISH, attempt_id=ATTEMPT), redeemed).code == "commit-missing"
    other = _req(PUBLISH, attempt_id=ATTEMPT, commit_sha="b" * 40)
    assert _decide(other, redeemed).code == "attempt-binding-mismatch"
    accepted = FakeOwner(attempt=served_attempt("accepted"))
    assert _decide(_req(PUBLISH, attempt_id=ATTEMPT, commit_sha=COMMIT), accepted).code == "attempt-state-conflict"


def test_publish_after_report_applied_is_refused() -> None:
    # report-applied leaves state `redeemed` and appends a third event.
    reported = FakeOwner(attempt=served_attempt("redeemed", REPORTED))
    decision = _decide(_req(PUBLISH, attempt_id=ATTEMPT, commit_sha=COMMIT), reported)
    assert decision.code == "attempt-already-applied"


def test_duplicate_report_applied_is_refused() -> None:
    reported = FakeOwner(attempt=served_attempt("redeemed", REPORTED))
    assert _decide(_req(REPORT, attempt_id=ATTEMPT), reported).code == "attempt-already-applied"


# ---------------------------------------------------------------- explicit approval

def _approve(ref: str = "decision:42:7", operation: str = "rollout.resume-v1", **over) -> ea.ExecutionRequest:
    over.setdefault("commit_sha", COMMIT)
    return _req(operation, approval_ref=ref, **over)


def test_consequential_transition_needs_approval_ref() -> None:
    decision = _decide(_req("rollout.resume-v1"))
    assert decision.code == "approval-required" and decision.tier == "explicit-approval"
    assert _decide(_approve("looks fine")).code == "approval-required"


def test_protected_publication_needs_approval_ref() -> None:
    assert _decide(_req("agentops.publication.protected-main-v1")).code == "approval-required"


def test_served_operator_decision_bound_to_transition_repo_run_is_allowed() -> None:
    decision = _decide(_approve())
    assert decision.allowed and decision.code == "approved-transition"


def test_approval_by_non_approver_is_refused() -> None:
    owner = FakeOwner(decisions=[served_decision(actor="devbox-agent-vuoro")])
    assert _decide(_approve(), owner).code == "approval-invalid"


@pytest.mark.parametrize("rationale", [
    f"approve protected-publication repo=agentops run={RUN} commit={COMMIT}",  # other transition
    f"approve rollout-resume repo=sprintctl run={RUN} commit={COMMIT}",       # other repo
    f"approve rollout-resume repo=agentops run=run_other commit={COMMIT}",     # other run
    f"approve rollout-resume repo=agentops run={RUN} commit={'b' * 40}",      # other commit
    f"approve rollout-resume repo=agentops run={RUN}",                        # no commit or PR
    "approved",
])
def test_approval_not_bound_to_this_transition_repo_and_run_is_refused(rationale) -> None:
    owner = FakeOwner(decisions=[served_decision(rationale=rationale)])
    assert _decide(_approve(), owner).code == "approval-invalid"


def test_reject_decision_is_not_an_approval() -> None:
    assert _decide(_approve(), FakeOwner(decisions=[served_decision(kind="reject")])).code == "approval-invalid"


def test_unknown_decision_is_refused() -> None:
    assert _decide(_approve("decision:42:8")).code == "approval-invalid"


def test_expired_approval_is_refused() -> None:
    owner = FakeOwner(decisions=[served_decision(created_at=NOW - 3601)])
    assert _decide(_approve(), owner).code == "approval-expired"


def test_approved_transition_still_refuses_superseded_run() -> None:
    assert _decide(_approve(successor_run_id="run_2")).code == "run-superseded"


# ---------------------------------------------------------------- CLI and purity

def test_cli_refuses_without_profile(capsys: pytest.CaptureFixture[str]) -> None:
    code = ea.main(["--environment", str(DEVBOX), "--operation", PUBLISH, "--repo", "agentops",
                    "--run-id", RUN, "--grant-id", "grant_1"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["code"] == "run-unverified"


def test_cli_rejects_nan_grant_time(capsys: pytest.CaptureFixture[str]) -> None:
    code = ea.main(["--environment", str(DEVBOX), "--operation", "work.effect.attempt-open-v1",
                    "--repo", "agentops", "--run-id", RUN, "--grant-id", "g", "--granted-at", "nan"])
    assert code == 1 and json.loads(capsys.readouterr().out)["code"] == "grant-time-invalid"


def test_record_is_not_mutated() -> None:
    record = _record()
    before = copy.deepcopy(record)
    _decide(_req(), record=record)
    assert record == before


# ---------------------------------------------------------------- single use and branch-bound publication

def test_approval_is_single_use() -> None:
    owner = FakeOwner()
    assert _decide(_approve(), owner).allowed
    # A retry of the same use (same operation, same commit) replays: still allowed.
    assert _decide(_approve(), owner).allowed
    # Any other use of the same decision is refused by the owner's idempotency ledger.
    other = _approve(operation="rollout.resume-v2")
    assert _decide(other, owner).code == "approval-already-used"
    assert owner.calls.count("work.session-note.write-v1") == 3


def test_approval_can_bind_a_pull_request() -> None:
    pr = "https://github.com/bayleafwalker/agentops/pull/999"
    owner = FakeOwner(decisions=[served_decision(rationale=f"approve rollout-resume repo=agentops run={RUN} pr={pr}")])
    assert _decide(_approve(commit_sha=None, pr_url=pr), owner).allowed
    assert _decide(_approve(commit_sha=None, pr_url=pr + "0"), FakeOwner(decisions=owner.decisions)).code == "approval-invalid"


def test_approval_request_must_name_commit_or_pr() -> None:
    assert _decide(_approve(commit_sha=None)).code == "approval-invalid"


def test_consumption_failure_fails_closed() -> None:
    class Down(FakeOwner):
        def consume_approval(self, *args):
            raise ea.OwnerRefusal("transport")
    assert _decide(_approve(), Down()).code == "owner-unavailable"


@pytest.mark.parametrize("branch", ["main", "refs/heads/main", "vuoro-effect/intent_01JZZZZZZZZZZZZZZZZZZZZZZZ",
                                    "dispatch/run-x/intent_01JZZZZZZZZZZZZZZZZZZZZZZZ"])
def test_tier2_publication_only_to_a_dispatch_publish_branch(branch) -> None:
    owner = FakeOwner(attempt=served_attempt("redeemed", REDEEMED, branch=branch))
    assert _decide(_req(PUBLISH, attempt_id=ATTEMPT, commit_sha=COMMIT), owner).code == "publication-branch-not-allowed"


def test_allowed_publication_returns_the_bound_target() -> None:
    owner = FakeOwner(attempt=served_attempt("redeemed", REDEEMED))
    decision = _decide(_req(PUBLISH, attempt_id=ATTEMPT, commit_sha=COMMIT), owner)
    assert decision.allowed
    assert decision.target["branch"] == "dispatch/publish-batch/intent_01JZZZZZZZZZZZZZZZZZZZZZZZ"
    assert decision.target["commit_sha"] == COMMIT
