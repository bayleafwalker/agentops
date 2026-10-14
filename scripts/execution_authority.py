#!/usr/bin/env python3
"""Effect-boundary authority check for a bounded execution environment.

Call `decide()` immediately before an effect is dispatched. It answers allow or
refuse, with a stable reason code, from three inputs:

* the environment record's `authority` block (environment-record/v1),
* the requested operation and its work/run context (`ExecutionRequest`),
* the work owner's served state (`WorkOwner`): `work.run.resolve-v1` for the
  run binding and `work.effect.attempt-get-v1` for attempt state.

Tiers (docs/architecture/bounded-execution-environment.md):

1. standing read     - diagnosis operations, always allowed;
2. scoped execution  - listed operations, listed repositories, a live grant
                       within max TTL, a live unsuperseded run;
3. explicit approval - consequential transitions; refused without an operator
                       approval reference.

Everything fails closed: no authority block, no owner, an owner error, or an
unknown operation all refuse. Refusals happen here, before the effect, never at
settlement.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
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

APPROVAL_REF = re.compile(r"^approval:[A-Za-z0-9][A-Za-z0-9._:/#-]{2,255}$")
ATTEMPT_PREFIX = "work.effect.attempt-"
#: Attempt state each attempt operation requires before it may be dispatched
#: (sprintctl effect_attempt_schema: accepted | redeemed | sealed_unused).
ATTEMPT_PRECONDITION = {
    "work.effect.attempt-redeem-v1": "accepted",
    "work.effect.attempt-seal-unused-v1": "accepted",
    "work.effect.attempt-report-applied-v1": "redeemed",
}
APPLICATION_REPORTED = "application_report_received"


class OwnerRefusal(Exception):
    """A served-error-shaped refusal from the work owner (`code` is the contract code)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message


class WorkOwner(Protocol):
    def resolve_run(self, repo_id: str, run_id: str) -> dict: ...
    def attempt_get(self, repo_id: str, attempt_id: str) -> dict: ...


@dataclass(frozen=True)
class ExecutionRequest:
    operation: str
    repo_id: str
    run_id: str | None = None
    #: Epoch seconds the scoped execution grant was issued; TTL counts from here.
    granted_at: float | None = None
    #: Requested grant lifetime; must not exceed the record's max_ttl_seconds.
    ttl_seconds: int | None = None
    #: The grant the run was bound under when the grant was issued; a different
    #: grant on resolve means the authority was re-issued (superseded).
    grant_id: str | None = None
    #: A successor run already registered for this run (e.g. by the host adapter's
    #: predecessor_run_id). Its presence supersedes this run.
    successor_run_id: str | None = None
    attempt_id: str | None = None
    approval_ref: str | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    code: str
    reason: str
    tier: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _refuse(code: str, reason: str, tier: str | None = None) -> Decision:
    return Decision(False, code, reason, tier)


def _matches(patterns: list[str], operation: str) -> bool:
    return any(operation_matches(p, operation) for p in patterns)


def _approval_transition(authority: dict, operation: str) -> str | None:
    for entry in authority["explicit_approval"]:
        if _matches(entry["operations"], operation):
            return entry["transition"]
    return None


def _check_run(request: ExecutionRequest, owner: WorkOwner | None) -> Decision | None:
    if not request.run_id:
        return _refuse("run-missing", "scoped execution requires a run_id")
    if request.successor_run_id:
        return _refuse("run-superseded", f"run {request.run_id} is superseded by {request.successor_run_id}")
    if owner is None:
        return _refuse("run-unverified", "no work owner to resolve the run against; failing closed")
    try:
        resolved = owner.resolve_run(request.repo_id, request.run_id)
    except OwnerRefusal as exc:
        if exc.code == "run-not-found":
            # resolve-v1 answers run-not-found both for an unknown run and for one
            # no longer bound to this caller; either way this caller may not act.
            return _refuse("run-superseded", f"work.run.resolve-v1: run {request.run_id} no longer resolves to this binding")
        return _refuse("owner-unavailable", f"work.run.resolve-v1 failed: {exc.code}")
    if resolved.get("run_id") != request.run_id:
        return _refuse("run-superseded", "work.run.resolve-v1 returned a different run")
    if request.grant_id and resolved.get("grant_id") != request.grant_id:
        return _refuse("run-superseded", "the run's grant was re-issued since this request was authorized")
    return None


def _check_attempt(request: ExecutionRequest, owner: WorkOwner, required: str) -> Decision | None:
    if not request.attempt_id:
        return _refuse("attempt-missing", f"{request.operation} requires an attempt_id")
    try:
        attempt = owner.attempt_get(request.repo_id, request.attempt_id)
    except OwnerRefusal as exc:
        return _refuse("owner-unavailable", f"work.effect.attempt-get-v1 failed: {exc.code}")
    state = attempt.get("state")
    if state != required:
        return _refuse("attempt-state-conflict", f"attempt {request.attempt_id} is {state!r}, {request.operation} needs {required!r}")
    events = attempt.get("events") or []
    if any(isinstance(e, dict) and e.get("kind") == APPLICATION_REPORTED for e in events):
        return _refuse("attempt-already-applied", f"attempt {request.attempt_id} already has an application report")
    return None


def decide(record: dict, request: ExecutionRequest, owner: WorkOwner | None = None,
           now: float | None = None) -> Decision:
    """Allow or refuse `request` against `record`. Pure apart from owner reads."""
    if "authority" not in record:
        return _refuse("no-authority-block", f"environment {record.get('id')!r} declares no authority; it grants nothing")
    try:
        authority = validate_authority(record["authority"], Path(f"<environment {record.get('id')}>"))
    except ProfileError as exc:
        return _refuse("authority-invalid", str(exc))
    op = request.operation
    scoped = authority["scoped_execution"]

    transition = _approval_transition(authority, op)
    if transition is not None:
        if not request.approval_ref or not APPROVAL_REF.fullmatch(request.approval_ref):
            return _refuse("approval-required", f"{op} is the consequential transition {transition!r}; an operator approval reference (approval:...) is required", "explicit-approval")
        if request.repo_id not in scoped["repositories"]:
            return _refuse("repository-not-in-scope", f"repository {request.repo_id!r} is outside this environment's scope", "explicit-approval")
        denial = _check_run(request, owner)
        return denial or Decision(True, "approved-transition", f"{transition} under {request.approval_ref}", "explicit-approval")

    if _matches(authority["standing_read"]["operations"], op):
        return Decision(True, "standing-read", f"{op} is a standing read", "standing-read")

    if not _matches(scoped["operations"], op):
        return _refuse("operation-not-in-scope", f"{op} is not within this environment's scoped execution authority")
    tier = "scoped-execution"
    if request.repo_id not in scoped["repositories"]:
        return _refuse("repository-not-in-scope", f"repository {request.repo_id!r} is outside this environment's scope", tier)
    max_ttl = scoped["max_ttl_seconds"]
    if request.ttl_seconds is not None and request.ttl_seconds > max_ttl:
        return _refuse("ttl-exceeds-maximum", f"requested ttl {request.ttl_seconds}s exceeds max_ttl_seconds {max_ttl}", tier)
    if request.granted_at is None:
        return _refuse("grant-time-missing", "scoped execution requires granted_at to bound the TTL", tier)
    ttl = min(max_ttl, request.ttl_seconds or max_ttl)
    current = time.time() if now is None else now
    if current >= request.granted_at + ttl:
        return _refuse("ttl-expired", f"execution grant expired {int(current - request.granted_at - ttl)}s ago", tier)
    denial = _check_run(request, owner)
    if denial:
        return Decision(False, denial.code, denial.reason, tier)
    assert owner is not None  # _check_run refuses without an owner
    required = ATTEMPT_PRECONDITION.get(op)
    if op == scoped["publication_operation"]:
        # The publication effect itself runs only under a redeemed, unreported attempt.
        required = "redeemed"
    if required:
        denial = _check_attempt(request, owner, required)
        if denial:
            return Decision(False, denial.code, denial.reason, tier)
    return Decision(True, "scoped-execution", f"{op} on {request.repo_id} within run {request.run_id}", tier)


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
    parser.add_argument("--approval-ref")
    parser.add_argument("--profile", type=Path, help="vuoro client profile; without it run checks fail closed")
    args = parser.parse_args(argv)
    from validate_vuoro_profiles import validate_environment  # noqa: PLC0415

    try:
        record = validate_environment(args.environment)
    except ProfileError as exc:
        print(json.dumps({"allowed": False, "code": "environment-invalid", "reason": str(exc), "tier": None}))
        return 2
    owner = ServedWorkOwner(args.profile) if args.profile else None
    try:
        decision = decide(record, ExecutionRequest(
            operation=args.operation, repo_id=args.repo, run_id=args.run_id, granted_at=args.granted_at,
            ttl_seconds=args.ttl_seconds, grant_id=args.grant_id, successor_run_id=args.successor_run_id,
            attempt_id=args.attempt_id, approval_ref=args.approval_ref), owner)
    finally:
        if owner is not None:
            owner.close()
    print(json.dumps(decision.as_dict(), sort_keys=True))
    return 0 if decision.allowed else 1


if __name__ == "__main__":
    raise SystemExit(main())
