#!/usr/bin/env python3
"""Effect-boundary authority check for a bounded execution environment.

Call `decide()` immediately before an effect is dispatched. It answers allow or
refuse, with a stable reason code, from three inputs:

* the environment record's `authority` block (environment-record/v1),
* the requested operation and its work/run context (`ExecutionRequest`),
* the work owner's served state (`WorkOwner`): `work.run.resolve-v1` for the
  run binding, `work.effect.attempt-get-v1` for attempt state and owner-side
  issue time, `work.read.item-decisions` for operator approval decisions.

Tiers (docs/architecture/bounded-execution-environment.md):

1. standing read     - listed diagnosis operations, always allowed;
2. scoped execution  - listed operations on listed repositories, a run that
                       still resolves to the request's grant, within max TTL,
                       and for attempt-bound operations an attempt in the
                       right state bound to the same grant;
3. explicit approval - consequential transitions; refused without a served
                       accept decision by a listed approver that names the
                       transition, repository and run and is not older than
                       max_approval_age_seconds.

Everything fails closed: no authority block, no owner, any owner or client
error, malformed or self-contradicting input. Refusals happen here, before the
effect, never at settlement. `decide()` never raises.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as _dt
import json
import math
import os
import re
import stat
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_vuoro_profiles import ProfileError, operation_matches, validate_authority  # noqa: E402

#: `decision:<work item id>:<decision id>`: a `work.decision.record` row.
APPROVAL_REF = re.compile(r"^decision:([1-9][0-9]{0,18}):([1-9][0-9]{0,18})$")
#: A client clock may run ahead of the owner by at most this much.
CLOCK_SKEW_SECONDS = 60
OPEN = "work.effect.attempt-open-v1"
#: Attempt state each attempt-bound operation requires
#: (sprintctl effect_attempt_schema: accepted | redeemed | sealed_unused).
ATTEMPT_PRECONDITION = {
    "work.effect.attempt-redeem-v1": "accepted",
    "work.effect.attempt-seal-unused-v1": "accepted",
    "work.effect.attempt-report-applied-v1": "redeemed",
}
EVENT_ACCEPTED = "attempt_authorization_accepted"
EVENT_REPORTED = "application_report_received"
#: Provider operations a served attempt can authorize (sprintctl effect_attempt.canonical_target).
PUBLICATION_TARGETS = {"push_branch", "open_pull_request"}


class OwnerRefusal(Exception):
    """A served-error-shaped refusal from the work owner (`code` is the contract code)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


class WorkOwner(Protocol):
    def resolve_run(self, repo_id: str, run_id: str) -> dict: ...
    def attempt_get(self, repo_id: str, attempt_id: str) -> dict: ...
    def item_decisions(self, repo_id: str, item_id: int) -> dict: ...


@dataclass(frozen=True)
class ExecutionRequest:
    operation: str
    repo_id: str
    run_id: str | None = None
    #: The grant the run was bound under when this request was authorized.
    #: Required for tiers 2 and 3; compared with resolve-v1's grant_id.
    grant_id: str | None = None
    #: Epoch seconds the execution grant was issued. Self-attested, so only used
    #: where the owner exposes no issue time (attempt-open, host-adapter launch);
    #: attempt-bound operations use the owner's attempt acceptance time instead.
    granted_at: float | None = None
    #: Requested grant lifetime (seconds); must be a positive integer <= max_ttl_seconds.
    ttl_seconds: int | None = None
    #: A successor run already registered for this run (e.g. by the host adapter's
    #: predecessor_run_id). Its presence supersedes this run.
    successor_run_id: str | None = None
    attempt_id: str | None = None
    #: The commit the effect will publish; must equal the attempt's target commit.
    commit_sha: str | None = None
    #: `decision:<item>:<decision>` for tier 3 operations.
    approval_ref: str | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str
    reason: str
    tier: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class _Refused(Exception):
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _call(fn, operation: str, *args: Any) -> dict:
    """Invoke an owner read; every failure (refusal, transport, bad shape) refuses."""
    try:
        result = fn(*args)
    except OwnerRefusal as exc:
        raise _Refused("owner-unavailable" if exc.code != "run-not-found" else "run-not-found",
                       f"{operation} failed: {exc.code}") from None
    except Exception as exc:  # noqa: BLE001 - fail closed on any client error
        raise _Refused("owner-unavailable", f"{operation} failed: {type(exc).__name__}") from None
    if not isinstance(result, dict):
        raise _Refused("owner-unavailable", f"{operation} returned a non-object")
    return result


def _parse_time(value: Any) -> float:
    if not isinstance(value, str):
        raise _Refused("owner-unavailable", "owner timestamp missing")
    try:
        parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise _Refused("owner-unavailable", "owner timestamp malformed") from None
    if parsed.tzinfo is None:
        raise _Refused("owner-unavailable", "owner timestamp has no timezone")
    return parsed.timestamp()


def _matches(patterns: list[str], operation: str) -> bool:
    return any(operation_matches(p, operation) for p in patterns)


def _approval_entry(authority: dict, operation: str) -> dict | None:
    for entry in authority["explicit_approval"]:
        if _matches(entry["operations"], operation):
            return entry
    return None


def _check_window(issued_at: float, ttl: int, now: float, what: str) -> None:
    if issued_at > now + CLOCK_SKEW_SECONDS:
        raise _Refused("grant-time-in-future", f"{what} is {int(issued_at - now)}s in the future")
    if now >= issued_at + ttl:
        raise _Refused("ttl-expired", f"{what} expired {int(now - issued_at - ttl)}s ago")


def _requested_ttl(request: ExecutionRequest, max_ttl: int) -> int:
    ttl = request.ttl_seconds
    if ttl is None:
        return max_ttl
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        raise _Refused("ttl-invalid", "ttl_seconds must be a positive integer")
    if ttl > max_ttl:
        raise _Refused("ttl-exceeds-maximum", f"requested ttl {ttl}s exceeds max_ttl_seconds {max_ttl}")
    return ttl


def _check_run(request: ExecutionRequest, owner: WorkOwner | None) -> dict:
    """The run must still resolve, for this caller, to the request's grant."""
    if not request.run_id:
        raise _Refused("run-missing", "execution requires a run_id")
    if not request.grant_id:
        raise _Refused("grant-id-missing", "execution requires the grant_id the request was authorized under")
    if request.successor_run_id:
        raise _Refused("run-superseded", f"run {request.run_id} is superseded by {request.successor_run_id}")
    if owner is None:
        raise _Refused("run-unverified", "no work owner to resolve the run against; failing closed")
    try:
        resolved = _call(owner.resolve_run, "work.run.resolve-v1", request.repo_id, request.run_id)
    except _Refused as exc:
        if exc.code == "run-not-found":
            # resolve-v1 answers run-not-found both for an unknown run and for one
            # no longer bound to this caller; either way this caller may not act.
            raise _Refused("run-superseded", f"work.run.resolve-v1: run {request.run_id} no longer resolves to this binding") from None
        raise
    if resolved.get("run_id") != request.run_id:
        raise _Refused("run-superseded", "work.run.resolve-v1 returned a different run")
    if resolved.get("grant_id") != request.grant_id:
        raise _Refused("run-superseded", "the caller's grant differs from the one this request was authorized under")
    return resolved


def _check_attempt(request: ExecutionRequest, owner: WorkOwner, resolved: dict,
                   required: str, publication: bool) -> float:
    """Attempt state, binding and target; returns the owner-side acceptance time."""
    if not request.attempt_id:
        raise _Refused("attempt-missing", f"{request.operation} requires an attempt_id")
    attempt = _call(owner.attempt_get, "work.effect.attempt-get-v1", request.repo_id, request.attempt_id)
    authorization = attempt.get("authorization")
    events = attempt.get("events")
    if not isinstance(authorization, dict) or not isinstance(events, list) or not events:
        raise _Refused("owner-unavailable", "work.effect.attempt-get-v1 returned an unexpected shape")
    if authorization.get("attempt_id") != request.attempt_id or authorization.get("repo_id") != request.repo_id:
        raise _Refused("attempt-binding-mismatch", "attempt does not belong to this repository")
    for key in ("principal_id", "grant_id"):
        if authorization.get(key) != resolved.get(key):
            raise _Refused("attempt-binding-mismatch", f"attempt {key} differs from the run's binding")
    target = authorization.get("target") if isinstance(authorization.get("target"), dict) else {}
    if publication:
        if target.get("operation") not in PUBLICATION_TARGETS:
            raise _Refused("attempt-binding-mismatch", "attempt does not authorize a publication target")
        if not request.commit_sha:
            raise _Refused("commit-missing", "publication requires the commit it will publish")
    if request.commit_sha and target.get("commit_sha") != request.commit_sha:
        raise _Refused("attempt-binding-mismatch", "commit differs from the attempt's authorized target commit")
    state = attempt.get("state")
    if state != required:
        raise _Refused("attempt-state-conflict", f"attempt {request.attempt_id} is {state!r}, {request.operation} needs {required!r}")
    if any(isinstance(e, dict) and e.get("event_kind") == EVENT_REPORTED for e in events):
        raise _Refused("attempt-already-applied", f"attempt {request.attempt_id} already has an application report")
    first = events[0]
    if not isinstance(first, dict) or first.get("event_kind") != EVENT_ACCEPTED:
        raise _Refused("owner-unavailable", "attempt history does not start with its acceptance")
    return _parse_time(first.get("created_at"))


def _check_approval(request: ExecutionRequest, owner: WorkOwner, entry: dict, now: float) -> str:
    match = APPROVAL_REF.fullmatch(request.approval_ref or "")
    if not match:
        raise _Refused("approval-required", f"{request.operation} is the consequential transition "
                       f"{entry['transition']!r}; a decision:<item>:<decision> approval reference is required")
    item_id, decision_id = int(match.group(1)), int(match.group(2))
    result = _call(owner.item_decisions, "work.read.item-decisions", request.repo_id, item_id)
    decisions = result.get("decisions")
    found = [d for d in decisions or [] if isinstance(d, dict) and d.get("id") == decision_id]
    if len(found) != 1:
        raise _Refused("approval-invalid", f"decision {decision_id} is not recorded on item {item_id}")
    decision = found[0]
    if decision.get("work_item_id", item_id) != item_id or decision.get("kind") != "accept":
        raise _Refused("approval-invalid", "approval must be an accept decision on the referenced item")
    if decision.get("actor") not in entry["approvers"]:
        raise _Refused("approval-invalid", f"decision actor {decision.get('actor')!r} is not an approver for {entry['transition']!r}")
    binding = f"approve {entry['transition']} repo={request.repo_id} run={request.run_id}"
    rationale = decision.get("rationale")
    if not isinstance(rationale, str) or binding not in rationale.splitlines():
        raise _Refused("approval-invalid", f"decision rationale must contain the line {binding!r}")
    try:
        _check_window(_parse_time(decision.get("created_at")), entry["max_approval_age_seconds"], now, "approval")
    except _Refused as exc:
        raise _Refused("approval-expired" if exc.code == "ttl-expired" else "approval-invalid", exc.reason) from None
    return f"{entry['transition']} approved by {decision.get('actor')} (decision {decision_id})"


def _self_attested_window(request: ExecutionRequest, ttl: int, now: float) -> None:
    granted_at = request.granted_at
    if granted_at is None:
        raise _Refused("grant-time-missing", "this operation has no owner-side issue time; granted_at is required")
    if isinstance(granted_at, bool) or not isinstance(granted_at, (int, float)) or not math.isfinite(granted_at):
        raise _Refused("grant-time-invalid", "granted_at must be a finite epoch time")
    _check_window(float(granted_at), ttl, now, "execution grant")


def decide(record: dict, request: ExecutionRequest, owner: WorkOwner | None = None,
           now: float | None = None) -> Decision:
    """Allow or refuse `request` against `record`. Never raises; refuses on any doubt."""
    tier: str | None = None
    try:
        if not isinstance(record, dict) or "authority" not in record:
            raise _Refused("no-authority-block", "the environment declares no authority; it grants nothing")
        try:
            authority = validate_authority(record["authority"], Path(f"<environment {record.get('id')}>"))
        except ProfileError as exc:
            raise _Refused("authority-invalid", str(exc)) from None
        current = time.time() if now is None else now
        op = request.operation
        scoped = authority["scoped_execution"]

        entry = _approval_entry(authority, op)
        if entry is not None:
            tier = "explicit-approval"
            if not request.approval_ref:
                raise _Refused("approval-required", f"{op} is the consequential transition {entry['transition']!r}; "
                               "an operator approval decision is required")
            if request.repo_id not in scoped["repositories"]:
                raise _Refused("repository-not-in-scope", f"repository {request.repo_id!r} is outside this environment's scope")
            _check_run(request, owner)
            assert owner is not None  # _check_run refuses without an owner
            return Decision(True, "approved-transition", _check_approval(request, owner, entry, current), tier)

        if op in authority["standing_read"]["operations"]:
            return Decision(True, "standing-read", f"{op} is a standing read", "standing-read")

        if op not in scoped["operations"]:
            raise _Refused("operation-not-in-scope", f"{op} is not within this environment's scoped execution authority")
        tier = "scoped-execution"
        if request.repo_id not in scoped["repositories"]:
            raise _Refused("repository-not-in-scope", f"repository {request.repo_id!r} is outside this environment's scope")
        ttl = _requested_ttl(request, scoped["max_ttl_seconds"])
        publication = op == scoped["publication_operation"]
        required = "redeemed" if publication else ATTEMPT_PRECONDITION.get(op)
        if required is None:
            # No owner-side issue time exists for this operation: bound the self-attested one.
            _self_attested_window(request, ttl, current)
        resolved = _check_run(request, owner)
        if required is not None:
            assert owner is not None
            accepted_at = _check_attempt(request, owner, resolved, required, publication)
            _check_window(accepted_at, ttl, current, "attempt authorization")
        return Decision(True, "scoped-execution", f"{op} on {request.repo_id} within run {request.run_id}", tier)
    except _Refused as exc:
        return Decision(False, exc.code, exc.reason, tier)
    except Exception as exc:  # noqa: BLE001 - decide() is the boundary; it never raises
        return Decision(False, "internal-error", f"{type(exc).__name__}", tier)


# --------------------------------------------------------------------------
# Served owner over vuoro_client (the client sprintctl's served mode uses)
# --------------------------------------------------------------------------

def _file_credential(ref: str) -> str:
    """Strict `file:` credential reader (absolute or ~/ path, 0600, owned, no symlink)."""
    if not ref.startswith("file:"):
        raise OwnerRefusal("credential-unsupported", "expected a file: credential reference")
    raw = ref[5:]
    path = Path.home() / raw[2:] if raw.startswith("~/") else Path(raw)
    if not path.is_absolute():
        raise OwnerRefusal("credential-unsupported", "credential path must be absolute or ~/")
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise OwnerRefusal("credential-unsupported", "credential must be a regular, non-symlink file")
    if st.st_uid != os.geteuid() or stat.S_IMODE(st.st_mode) != 0o600:
        raise OwnerRefusal("credential-unsupported", "credential must be owned by this user, mode 0600")
    return path.read_text(encoding="utf-8").strip()


class ServedWorkOwner:
    """`WorkOwner` over `vuoro_client.AsyncVuoroClient` (read operations only)."""

    def __init__(self, profile_path: str | Path) -> None:
        self._profile_path = Path(profile_path)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client: Any = None

    def _invoke(self, operation: str, arguments: dict, repo_id: str) -> dict:
        if self._client is None:
            from vuoro_client import AsyncVuoroClient  # noqa: PLC0415 - optional dependency
            from vuoro_client.profile import load_profile  # noqa: PLC0415

            self._loop = asyncio.new_event_loop()
            client = AsyncVuoroClient(load_profile(self._profile_path), _file_credential)
            self._loop.run_until_complete(client.__aenter__())
            self._client = client
        try:
            return self._loop.run_until_complete(  # type: ignore[union-attr]
                self._client.invoke(operation, arguments, repo_id=repo_id))
        except Exception as exc:  # noqa: BLE001 - map the client's rejection
            code = getattr(exc, "code", None)
            raise OwnerRefusal(code if isinstance(code, str) else "transport", type(exc).__name__) from exc

    def close(self) -> None:
        if self._client is not None and self._loop is not None:
            with contextlib.suppress(Exception):
                self._loop.run_until_complete(self._client.__aexit__(None, None, None))
            self._loop.close()
        self._client = self._loop = None

    def resolve_run(self, repo_id: str, run_id: str) -> dict:
        return self._invoke("work.run.resolve-v1", {"run_id": run_id}, repo_id)

    def attempt_get(self, repo_id: str, attempt_id: str) -> dict:
        return self._invoke("work.effect.attempt-get-v1", {"attempt_id": attempt_id}, repo_id)

    def item_decisions(self, repo_id: str, item_id: int) -> dict:
        return self._invoke("work.read.item-decisions", {"item_id": item_id}, repo_id)


def authorize(environment: Path, request: ExecutionRequest, profile: Path | None) -> Decision:
    """Validate the record, open a served owner when a profile is given, and decide.

    The single entry point for callers that dispatch effects (dispatch_publish.py).
    """
    from validate_vuoro_profiles import validate_environment  # noqa: PLC0415

    try:
        record = validate_environment(environment)
    except ProfileError as exc:
        return Decision(False, "environment-invalid", str(exc), None)
    owner = ServedWorkOwner(profile) if profile else None
    try:
        return decide(record, request, owner)
    finally:
        if owner is not None:
            owner.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--operation", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--granted-at", type=float)
    parser.add_argument("--ttl-seconds", type=int)
    parser.add_argument("--grant-id")
    parser.add_argument("--successor-run-id")
    parser.add_argument("--attempt-id")
    parser.add_argument("--commit-sha")
    parser.add_argument("--approval-ref", help="decision:<work item id>:<decision id>")
    parser.add_argument("--profile", type=Path, help="vuoro client profile; without it run checks fail closed")
    args = parser.parse_args(argv)
    decision = authorize(args.environment, ExecutionRequest(
        operation=args.operation, repo_id=args.repo, run_id=args.run_id, grant_id=args.grant_id,
        granted_at=args.granted_at, ttl_seconds=args.ttl_seconds, successor_run_id=args.successor_run_id,
        attempt_id=args.attempt_id, commit_sha=args.commit_sha, approval_ref=args.approval_ref), args.profile)
    print(json.dumps(decision.as_dict(), sort_keys=True))
    return 0 if decision.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
