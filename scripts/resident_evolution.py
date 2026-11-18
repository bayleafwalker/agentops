"""Operator-side, receipt-bound runtime-pointer transitions for a local resident.

This is metadata preparation, not a supervisor or deployment executor. It never
executes candidate code, restores a database, issues a credential, or changes
the budget/effect/correction owners. A separately qualified host must keep this
root and evaluator receipts outside candidate write access, enforce separate
service identities, verify actual selected bytes, and activate the runtime.
Unix ownership/mode checks here are necessary checks, not proof of that isolation.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
import uuid


_HASH = re.compile(r"^[0-9a-f]{64}$")
_CHECKS = {"startup", "context", "isolation", "recovery", "state_compatibility", "monotonic_preserved"}
_BOUNDARIES = {"budget", "effects", "corrections"}
_POINTER_FIELDS = {"schema", "generation", "candidate_sha256", "config_sha256", "state_manifest_sha256",
                   "boundary_sha256", "evaluation_sha256", "previous_pointer_digest", "action", "digest"}


class TransitionConflict(ValueError):
    """The protected current pointer no longer matches the evaluated base."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def record_digest(record: dict[str, Any]) -> str:
    """Digest an evaluator/state/boundary record, with no self-digest field."""
    return hashlib.sha256(_canonical(record)).hexdigest()


def _digest(value: Any) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError("expected lowercase SHA-256 digest")
    return value


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field in protected record")
        value[key] = item
    return value


def _protected_directory(path: Path) -> Path:
    path = path.absolute()
    if path.resolve() != path:
        raise ValueError("protected path must be canonical without symlinks")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise ValueError("protected directory must be owned by this service and not writable by others")
    return path


def _read(path: Path) -> dict[str, Any]:
    _protected_directory(path.parent)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022 or info.st_nlink != 1 or info.st_size > 1048576):
            raise ValueError("invalid protected record ownership, links, type or size")
        value = json.loads(source.read(1048577), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON number")))
    if not isinstance(value, dict):
        raise ValueError("protected record must be an object")
    return value


def _addressed(root: Path, kind: str, digest: str) -> dict[str, Any]:
    record = _read(root / kind / f"{_digest(digest)}.json")
    if record_digest(record) != digest:
        raise ValueError("protected record digest mismatch")
    return record


def _pointer(record: dict[str, Any]) -> dict[str, Any]:
    if set(record) != _POINTER_FIELDS or record.get("schema") != "resident-runtime-pointer/v1":
        raise ValueError("invalid runtime pointer")
    if type(record["generation"]) is not int or record["generation"] < 1:
        raise ValueError("invalid runtime generation")
    for name in ("candidate_sha256", "config_sha256", "state_manifest_sha256", "boundary_sha256", "evaluation_sha256"):
        _digest(record[name])
    previous = record["previous_pointer_digest"]
    if previous is not None:
        _digest(previous)
    if (record["generation"] == 1) != (previous is None):
        raise ValueError("runtime generation does not match pointer ancestry")
    if record["action"] not in {"activate", "rollback"}:
        raise ValueError("invalid pointer action")
    if record_digest({k: v for k, v in record.items() if k != "digest"}) != _digest(record["digest"]):
        raise ValueError("runtime pointer digest mismatch")
    return record


def read_pointer(root: Path) -> dict[str, Any] | None:
    root = _protected_directory(root)
    try:
        return _pointer(_read(root / "current.json"))
    except FileNotFoundError:
        return None


@contextmanager
def _locked(root: Path):
    descriptor = os.open(root / ".transition.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022 or info.st_nlink != 1):
            raise ValueError("invalid transition lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def _publish(path: Path, data: bytes, *, replace: bool) -> None:
    """Publish under the transition lock, keeping prior archives immutable.

    All directory writers must honor that lock. Atomic rename avoids a staged
    hard-link alias surviving a process crash and violating protected-file
    single-link checks on recovery.
    """
    parent = _protected_directory(path.parent)
    if not replace:
        try:
            existing = _read(path)
        except FileNotFoundError:
            pass
        else:
            if _canonical(existing) != data:
                raise ValueError("immutable runtime pointer has conflicting bytes")
            return
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = f".staging-{uuid.uuid4()}"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        os.close(directory)


def _boundary(value: dict[str, Any]) -> None:
    if set(value) != {"schema", "sources"} or value["schema"] != "resident-boundary-observation/v1":
        raise ValueError("invalid monotonic-boundary observation")
    if not isinstance(value["sources"], dict) or set(value["sources"]) != _BOUNDARIES:
        raise ValueError("budget, effects and corrections owner references are required")
    for ref in value["sources"].values():
        if not isinstance(ref, dict) or set(ref) != {"owner", "revision", "sha256"}:
            raise ValueError("invalid boundary owner reference")
        if not all(isinstance(ref[key], str) and ref[key].strip() for key in ("owner", "revision")):
            raise ValueError("boundary owner and revision are required")
        _digest(ref["sha256"])


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("evaluation time must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("evaluation time must include timezone")
    return parsed.astimezone(timezone.utc)


def _previously_selected(root: Path, pointer: dict[str, Any], candidate: str, config: str) -> bool:
    previous = pointer["previous_pointer_digest"]
    generation = pointer["generation"]
    for _ in range(10000):
        if previous is None:
            return False
        record = _pointer(_read(root / "pointers" / f"{previous}.json"))
        if record["digest"] != previous or record["generation"] != generation - 1:
            raise ValueError("invalid prior runtime-pointer chain")
        if (record["candidate_sha256"], record["config_sha256"]) == (candidate, config):
            return True
        previous, generation = record["previous_pointer_digest"], record["generation"]
    raise ValueError("runtime-pointer history exceeds the bounded traversal")


def transition_pointer(root: Path, *, receipt_digest: str, expected_pointer_digest: str | None,
                       trusted_evaluator_ids: set[str] | frozenset[str], action: str = "activate") -> dict[str, Any]:
    """CAS a local pointer using an independently produced protected receipt.

    The caller's evaluator allowlist is protected service configuration, never
    a candidate/tool argument. All owners updating boundary.json must share this
    lock or hold a broader quiescence fence. This function does not invent an
    atomic cross-owner snapshot. Receipt/state assertions still require actual
    evaluator and host qualification; matching hashes alone cannot supply it.
    """
    root = _protected_directory(root)
    _digest(receipt_digest)
    if expected_pointer_digest is not None:
        _digest(expected_pointer_digest)
    if action not in {"activate", "rollback"} or not trusted_evaluator_ids:
        raise ValueError("an explicit action and trusted evaluator set are required")
    with _locked(root):
        current = read_pointer(root)
        actual = current["digest"] if current else None
        # This is a prior result read, not a renewed evaluation or activation.
        if (current and current["evaluation_sha256"] == receipt_digest and current["action"] == action
                and current["previous_pointer_digest"] == expected_pointer_digest):
            return {"pointer": current, "replayed": True, "runtime_activated": False, "authorizes_effects": False}
        if actual != expected_pointer_digest:
            raise TransitionConflict("current runtime pointer differs from evaluated base")
        receipt = _addressed(root, "receipts", receipt_digest)
        required = {"schema", "evaluator_id", "decision", "action", "candidate_sha256", "config_sha256",
                    "state_manifest_sha256", "boundary_sha256", "expected_pointer_digest", "checks",
                    "observed_at", "valid_until"}
        if set(receipt) != required or receipt["schema"] != "resident-evaluation/v1":
            raise ValueError("invalid protected evaluation receipt")
        if (not isinstance(receipt["evaluator_id"], str)
                or receipt["evaluator_id"] not in trusted_evaluator_ids or receipt["decision"] != "pass"
                or receipt["action"] != action or receipt["expected_pointer_digest"] != actual):
            raise ValueError("receipt does not qualify this transition")
        if (not isinstance(receipt["checks"], dict) or set(receipt["checks"]) != _CHECKS
                or any(value != "passed" for value in receipt["checks"].values())):
            raise ValueError("required protected evaluation checks did not all pass")
        now = datetime.now(timezone.utc)
        if not _time(receipt["observed_at"]) <= now < _time(receipt["valid_until"]):
            raise ValueError("evaluation receipt is not currently time-valid")
        candidate, config = _digest(receipt["candidate_sha256"]), _digest(receipt["config_sha256"])
        boundary = _read(root / "boundary.json")
        _boundary(boundary)
        boundary_digest = record_digest(boundary)
        if boundary_digest != receipt["boundary_sha256"]:
            raise ValueError("budget/effect/correction boundary changed after evaluation")
        state = _addressed(root, "states", receipt["state_manifest_sha256"])
        state_fields = {"schema", "candidate_sha256", "config_sha256", "state_generation",
                        "preserved_boundary_sha256", "snapshots"}
        if (set(state) != state_fields or state["schema"] != "resident-state-manifest/v1"
                or state["candidate_sha256"] != candidate or state["config_sha256"] != config
                or state["preserved_boundary_sha256"] != boundary_digest):
            raise ValueError("runtime, configuration and preserved boundary do not match the state manifest")
        if not isinstance(state["state_generation"], str) or not state["state_generation"].strip():
            raise ValueError("state generation is required")
        if not isinstance(state["snapshots"], list) or not 1 <= len(state["snapshots"]) <= 32:
            raise ValueError("state manifest needs bounded owner snapshot references")
        preserved_owners = {ref["owner"] for ref in boundary["sources"].values()}
        snapshot_owners = set()
        for ref in state["snapshots"]:
            if (not isinstance(ref, dict) or set(ref) != {"owner", "revision", "sha256"}
                    or not all(isinstance(ref[key], str) and ref[key].strip() for key in ("owner", "revision"))):
                raise ValueError("invalid snapshot reference")
            _digest(ref["sha256"])
            if ref["owner"] in preserved_owners or ref["owner"] in snapshot_owners:
                raise ValueError("snapshot owners must be unique and exclude the preserved monotonic owners")
            snapshot_owners.add(ref["owner"])
        if action == "rollback" and (current is None or not _previously_selected(root, current, candidate, config)):
            raise ValueError("rollback target was not previously selected in this pointer ancestry")
        pointer = {"schema": "resident-runtime-pointer/v1", "generation": current["generation"] + 1 if current else 1,
                   "candidate_sha256": candidate, "config_sha256": config,
                   "state_manifest_sha256": receipt["state_manifest_sha256"], "boundary_sha256": boundary_digest,
                   "evaluation_sha256": receipt_digest, "previous_pointer_digest": actual, "action": action}
        pointer["digest"] = record_digest(pointer)
        pointers = root / "pointers"
        pointers.mkdir(mode=0o700, exist_ok=True)
        _publish(pointers / f"{pointer['digest']}.json", _canonical(pointer), replace=False)
        _publish(root / "current.json", _canonical(pointer), replace=True)
        return {"pointer": pointer, "replayed": False, "runtime_activated": False, "authorizes_effects": False}
