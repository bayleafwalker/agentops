#!/usr/bin/env python3
"""Prepare an exact-candidate review packet from local Git and supplied receipts.

This tool never merges, pushes, fetches, dispatches, changes grants, or deploys.
Receipt matching is structural only: caller-supplied digests and identities are
not authenticated by this local packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prepare_portable_batch import (
    PacketError,
    _aware_datetime,
    _branch,
    _canonical_repository_id,
    _constant,
    _git,
    _identity,
    _keys,
    _origin_identity,
    _pairs,
    _text,
)


SCRIPT_ROOT = Path(__file__).resolve().parent.parent
MAX_REQUEST_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_RECEIPTS = 128
MAX_CHECKS = 64
OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
RECEIPT_RESULT = {"passed", "failed", "blocked", "unknown"}


class ReviewPacketError(ValueError):
    """Invalid review request or local candidate observation."""


def _check_json_bounds(text: str) -> None:
    depth = 0
    nodes = 1
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            nodes += 1
            if depth > MAX_JSON_DEPTH:
                raise ReviewPacketError("review request exceeds JSON depth limit")
        elif char in "]}":
            depth -= 1
        elif char == ",":
            nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ReviewPacketError("review request exceeds JSON node limit")


def _load_request(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_REQUEST_BYTES + 1)
    except OSError:
        raise ReviewPacketError("cannot read review request") from None
    if len(raw) > MAX_REQUEST_BYTES:
        raise ReviewPacketError("review request exceeds 1 MiB")
    try:
        decoded = raw.decode("utf-8")
        _check_json_bounds(decoded)
        value = json.loads(decoded, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, PacketError, RecursionError):
        raise ReviewPacketError("review request is not strict UTF-8 JSON") from None
    if not isinstance(value, dict):
        raise ReviewPacketError("review request root must be an object")
    return value


def _parse_instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _validate_request(raw: dict[str, Any]) -> dict[str, Any]:
    root = _keys(
        raw,
        {
            "schema",
            "request_id",
            "candidate",
            "evaluated_at",
            "max_receipt_age_seconds",
            "required_checks",
            "receipts",
        },
        {
            "schema",
            "request_id",
            "candidate",
            "evaluated_at",
            "max_receipt_age_seconds",
            "required_checks",
            "receipts",
        },
        "request",
    )
    if root["schema"] != "portable-candidate-review-request/v1":
        raise ReviewPacketError("unsupported review request schema")
    request: dict[str, Any] = {
        "schema": root["schema"],
        "request_id": _identity(root["request_id"], "request_id"),
        "evaluated_at": _aware_datetime(root["evaluated_at"], "evaluated_at"),
    }
    age = root["max_receipt_age_seconds"]
    if type(age) is not int or not 60 <= age <= 2_592_000:
        raise ReviewPacketError("max_receipt_age_seconds must be in 60..2592000")
    request["max_receipt_age_seconds"] = age

    candidate = _keys(
        root["candidate"],
        {"owner", "repository_id", "branch", "commit", "target_branch", "author_id"},
        {"owner", "repository_id", "branch", "commit", "target_branch", "author_id"},
        "candidate",
    )
    owner = _identity(candidate["owner"], "candidate.owner", re.compile(r"^[a-z][a-z0-9-]{0,62}$"))
    commit = _text(candidate["commit"], "candidate.commit", maximum=64)
    if not OBJECT_ID.fullmatch(commit):
        raise ReviewPacketError("candidate.commit must be a full lowercase Git object ID")
    request["candidate"] = {
        "owner": owner,
        "repository_id": _canonical_repository_id(candidate["repository_id"], "candidate.repository_id"),
        "branch": _branch(candidate["branch"], "candidate.branch"),
        "commit": commit,
        "target_branch": _branch(candidate["target_branch"], "candidate.target_branch"),
        "author_id": _text(candidate["author_id"], "candidate.author_id", maximum=256),
    }
    if request["candidate"]["branch"] == request["candidate"]["target_branch"]:
        raise ReviewPacketError("candidate and target branches must differ")

    checks = root["required_checks"]
    if not isinstance(checks, list) or not 1 <= len(checks) <= MAX_CHECKS:
        raise ReviewPacketError("required_checks must contain 1..64 entries")
    normalized_checks = [_identity(value, "required check") for value in checks]
    if "independent-review" in normalized_checks:
        raise ReviewPacketError("independent-review is a reserved evidence name")
    if len(set(normalized_checks)) != len(normalized_checks):
        raise ReviewPacketError("required_checks contains duplicate names")
    request["required_checks"] = sorted(normalized_checks)

    receipts = root["receipts"]
    if not isinstance(receipts, list) or len(receipts) > MAX_RECEIPTS:
        raise ReviewPacketError("receipts must contain 0..128 entries")
    normalized_receipts = []
    seen_receipt_ids: set[str] = set()
    for index, item in enumerate(receipts):
        label = f"receipts[{index}]"
        row = _keys(
            item,
            {
                "receipt_id",
                "kind",
                "subject_commit",
                "subject_tree",
                "result",
                "observed_at",
                "valid_until",
                "evidence_sha256",
            },
            {
                "receipt_id",
                "kind",
                "subject_commit",
                "subject_tree",
                "result",
                "observed_at",
                "valid_until",
                "evidence_sha256",
                "reviewer_id",
                "check_name",
            },
            label,
        )
        receipt_id = _identity(row["receipt_id"], f"{label}.receipt_id")
        if receipt_id in seen_receipt_ids:
            raise ReviewPacketError("receipt IDs must be unique")
        seen_receipt_ids.add(receipt_id)
        kind = row["kind"]
        if not isinstance(kind, str) or kind not in {"independent-review", "check"}:
            raise ReviewPacketError(f"{label}.kind is invalid")
        if kind == "independent-review":
            if "reviewer_id" not in row or "check_name" in row:
                raise ReviewPacketError(f"{label} review receipt fields are invalid")
            subject_name = {"reviewer_id": _text(row["reviewer_id"], f"{label}.reviewer_id", maximum=256)}
        else:
            if "check_name" not in row or "reviewer_id" in row:
                raise ReviewPacketError(f"{label} check receipt fields are invalid")
            subject_name = {"check_name": _identity(row["check_name"], f"{label}.check_name")}
        subject_commit = _text(row["subject_commit"], f"{label}.subject_commit", maximum=64)
        subject_tree = _text(row["subject_tree"], f"{label}.subject_tree", maximum=64)
        evidence_sha256 = _text(row["evidence_sha256"], f"{label}.evidence_sha256", maximum=64)
        if not OBJECT_ID.fullmatch(subject_commit) or not OBJECT_ID.fullmatch(subject_tree):
            raise ReviewPacketError(f"{label} has an invalid subject commit/tree")
        if not SHA256.fullmatch(evidence_sha256):
            raise ReviewPacketError(f"{label}.evidence_sha256 is invalid")
        result = row["result"]
        if not isinstance(result, str) or result not in RECEIPT_RESULT:
            raise ReviewPacketError(f"{label}.result is invalid")
        observed_at = _aware_datetime(row["observed_at"], f"{label}.observed_at")
        valid_until = _aware_datetime(row["valid_until"], f"{label}.valid_until")
        if _parse_instant(valid_until) < _parse_instant(observed_at):
            raise ReviewPacketError(f"{label}.valid_until precedes observed_at")
        normalized_receipts.append(
            {
                "receipt_id": receipt_id,
                "kind": kind,
                "subject_commit": subject_commit,
                "subject_tree": subject_tree,
                "result": result,
                "observed_at": observed_at,
                "valid_until": valid_until,
                "evidence_sha256": evidence_sha256,
                **subject_name,
            }
        )
    request["receipts"] = sorted(normalized_receipts, key=lambda row: row["receipt_id"])
    return request


def _candidate_observation(repo_path: str | None, candidate: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "owner": candidate["owner"],
        "repository_id": candidate["repository_id"],
        "branch": candidate["branch"],
        "commit": candidate["commit"],
        "tree": None,
        "target_branch": candidate["target_branch"],
        "target_branch_tip": None,
        "candidate_includes_local_target": "unknown",
        "checks": {
            "repository": "missing",
            "origin_identity": "unknown",
            "commit_object": "missing",
            "branch_tip": "missing",
            "clean_worktree": "missing",
            "tree_object": "missing",
        },
        "local_repo_path_included": False,
    }
    if repo_path is None:
        return result
    try:
        resolved = str(Path(repo_path).resolve(strict=True))
    except (OSError, RuntimeError):
        result["checks"]["repository"] = "failed"
        return result
    if _git(resolved, "rev-parse", "--show-toplevel").returncode != 0:
        result["checks"]["repository"] = "failed"
        return result
    result["checks"]["repository"] = "passed"
    origin = _origin_identity(resolved)
    result["checks"]["origin_identity"] = (
        "unknown"
        if origin is None
        else "passed"
        if origin == candidate["repository_id"]
        else "mismatch"
    )
    commit = candidate["commit"]
    if _git(resolved, "cat-file", "-e", f"{commit}^{{commit}}").returncode == 0:
        result["checks"]["commit_object"] = "passed"
        tree = _git(resolved, "rev-parse", "--verify", f"{commit}^{{tree}}")
        if tree.returncode == 0:
            tree_oid = tree.stdout.decode("ascii", errors="replace").strip()
            if OBJECT_ID.fullmatch(tree_oid):
                result["tree"] = tree_oid
                result["checks"]["tree_object"] = "passed"
            else:
                result["checks"]["tree_object"] = "failed"
    else:
        result["checks"]["commit_object"] = "failed"
        result["checks"]["tree_object"] = "failed"
    branch = _git(resolved, "rev-parse", "--verify", f"refs/heads/{candidate['branch']}")
    if branch.returncode == 0:
        actual = branch.stdout.decode("ascii", errors="replace").strip()
        result["checks"]["branch_tip"] = "passed" if actual == commit else "mismatch"
    else:
        result["checks"]["branch_tip"] = "missing"
    status = _git(
        resolved,
        "-c",
        "core.fsmonitor=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if status.returncode == 0:
        result["checks"]["clean_worktree"] = "passed" if not status.stdout else "dirty"
    target = _git(resolved, "rev-parse", "--verify", f"refs/heads/{candidate['target_branch']}")
    if target.returncode == 0:
        target_tip = target.stdout.decode("ascii", errors="replace").strip()
        result["target_branch_tip"] = target_tip
        ancestry = _git(resolved, "merge-base", "--is-ancestor", target_tip, commit)
        result["candidate_includes_local_target"] = (
            "yes-local-ancestry-observed"
            if ancestry.returncode == 0
            else "no-local-ancestry-observed"
            if ancestry.returncode == 1
            else "unknown"
        )
    return result


def _receipt_status(
    receipt: dict[str, Any],
    candidate: dict[str, Any],
    evaluated_at: str,
    max_age_seconds: int,
) -> str:
    if (
        receipt["subject_commit"] != candidate["commit"]
        or receipt["subject_tree"] != candidate["tree"]
    ):
        return "mismatched-head"
    now = _parse_instant(evaluated_at)
    observed = _parse_instant(receipt["observed_at"])
    valid_until = _parse_instant(receipt["valid_until"])
    if observed > now:
        return "future-dated"
    if valid_until < now or (now - observed).total_seconds() > max_age_seconds:
        return "stale"
    if receipt["result"] != "passed":
        return "not-passed"
    if receipt["kind"] == "independent-review" and receipt["reviewer_id"].casefold() == candidate["author_id"].casefold():
        return "not-independent"
    return "matches-exact-head-unverified"


def _evaluate_receipts(request: dict[str, Any], candidate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    evaluated = []
    for receipt in request["receipts"]:
        status = _receipt_status(
            receipt, candidate, request["evaluated_at"], request["max_receipt_age_seconds"]
        ) if candidate["tree"] else "candidate-tree-unavailable"
        evaluated.append(
            {
                "kind": receipt["kind"],
                "subject_commit": receipt["subject_commit"],
                "subject_tree": receipt["subject_tree"],
                "result": receipt["result"],
                "observed_at": receipt["observed_at"],
                "valid_until": receipt["valid_until"],
                "evidence_sha256": receipt["evidence_sha256"],
                **({"check_name": receipt["check_name"]} if receipt["kind"] == "check" else {}),
                "status": status,
                "evidence_authenticity": "caller-supplied-unverified",
            }
        )
    evaluated_by_check: dict[str, list[dict[str, Any]]] = {
        check: [row for row in evaluated if row.get("kind") == "check" and row.get("check_name") == check]
        for check in request["required_checks"]
    }
    required = []
    for check in request["required_checks"]:
        rows = evaluated_by_check[check]
        if not rows:
            state = "missing"
        elif len(rows) > 1:
            state = "ambiguous"
        else:
            state = rows[0]["status"]
        required.append({"check_name": check, "status": state})
    reviews = [row for row in evaluated if row["kind"] == "independent-review"]
    if not reviews:
        review_state = "missing"
    else:
        current = [
            row for row in reviews
            if row["status"] in {
                "matches-exact-head-unverified", "not-passed", "not-independent"
            }
        ]
        if len(current) > 1:
            review_state = "ambiguous"
        elif len(current) == 1:
            review_state = current[0]["status"]
        else:
            review_state = "blocked"
    required.append({"check_name": "independent-review", "status": review_state})
    return evaluated, required


MANUAL_ACTIONS = [
    "Confirm repository identity and source revision against the trusted owner source.",
    "Inspect the complete candidate diff and tree for the exact commit; this packet emits no file paths.",
    "Authenticate each independent-review and check receipt with its issuer and confirm it covers the exact commit and tree.",
    "Read the current target-branch protection and landing policy from the owner; the packet records this as unknown.",
    "Make the landing decision manually under repository policy; this tool does not merge or push.",
    "Keep deployment separate; this packet contains no deployment action or receipt.",
]


def _prepare(request: dict[str, Any], repo_path: str | None) -> dict[str, Any]:
    candidate = _candidate_observation(repo_path, request["candidate"])
    evaluated, evidence_summary = _evaluate_receipts(request, candidate)
    local_ok = all(value == "passed" for value in candidate["checks"].values())
    receipts_ok = all(row["status"] == "matches-exact-head-unverified" for row in evidence_summary)
    packet: dict[str, Any] = {
        "schema": "portable-candidate-review-packet/v1",
        "evaluated_at": request["evaluated_at"],
        "candidate": candidate,
        "receipt_observations": evaluated,
        "required_evidence": evidence_summary,
        "packet_state": (
            "metadata-consistent-for-manual-review"
            if local_ok and receipts_ok
            else "blocked"
        ),
        "landing_policy_observation": {
            "status": "unknown",
            "reason": "target protection and current owner policy were not read",
        },
        "manual_review_actions": [
            {"order": index + 1, "action": action}
            for index, action in enumerate(MANUAL_ACTIONS)
        ],
        "authority": {
            "merge": "not-performed-and-not-available",
            "push": "not-performed-and-not-available",
            "fetch": "not-performed-and-not-available",
            "dispatch": "not-performed-and-not-available",
            "grant_changes": "none",
            "deployment": "excluded",
        },
        "unknowns": [
            "receipt issuer authenticity and reviewer identity are not independently verified",
            "the target branch observation is local-only and may be stale",
            "target branch protection and required landing policy are unknown",
            "canonical repository identity was matched only against local origin config",
            "acceptance, merge, and deployment receipts are absent",
        ],
    }
    canonical = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    packet["packet_sha256"] = hashlib.sha256(canonical).hexdigest()
    return packet


def _render_text(packet: dict[str, Any]) -> str:
    candidate = packet["candidate"]
    lines = [
        f"Candidate review packet: {packet['packet_state']}",
        f"Candidate: {candidate['owner']} {candidate['repository_id']} {candidate['branch']} @ {candidate['commit']}",
        f"Candidate tree: {candidate['tree'] or 'unknown'}",
        f"Packet SHA256: {packet['packet_sha256']}",
        "Local checks: " + ", ".join(f"{key}={value}" for key, value in candidate["checks"].items()),
        "Required evidence:",
    ]
    lines.extend(f"  {row['check_name']}: {row['status']}" for row in packet["required_evidence"])
    lines.append("Landing policy: unknown")
    lines.append("Manual review actions:")
    lines.extend(f"  {row['order']}. {row['action']}" for row in packet["manual_review_actions"])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True, help="strict review request JSON")
    parser.add_argument("--repo", required=True, metavar="OWNER=PATH", help="local Git repository path")
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        request = _validate_request(_load_request(args.request))
        owner, separator, repo_path = args.repo.partition("=")
        if not separator or owner != request["candidate"]["owner"] or not repo_path:
            raise ReviewPacketError("repository mapping must match candidate owner")
        packet = _prepare(request, repo_path)
    except (PacketError, ReviewPacketError) as exc:
        print(json.dumps({"schema": "portable-candidate-review-packet/v1", "packet_state": "invalid", "error": str(exc)}, sort_keys=True))
        return 2
    print(_render_text(packet) if args.format == "text" else json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if packet["packet_state"] == "metadata-consistent-for-manual-review" else 1


if __name__ == "__main__":
    sys.exit(main())
