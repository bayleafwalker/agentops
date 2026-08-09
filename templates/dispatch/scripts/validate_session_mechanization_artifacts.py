#!/usr/bin/env python3
"""Validate AgentOps session-mechanization artifacts without dependencies."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

TARGET_RANKS = {"explicit", "path-scope", "doc-link", "candidate", "repo-level"}
VERIFICATION_RESULTS = {"pass", "fail", "error", "skipped"}
REF_KINDS = {"git-commit", "sprint-event", "document", "verification-result", "release", "artifact"}
CLASSIFICATIONS = {
    "link-existing-item",
    "mark-item-advanced",
    "propose-completion",
    "flag-conflict-or-duplicate",
    "propose-new-item",
    "incidental-no-change",
}
LIFECYCLE_STATES = {"pending", "accepted", "rejected", "superseded"}
NOTE_KINDS = {"handover", "summary", "outcome"}
NOTE_BODY_MAX_BYTES = 16384
COMPLETION_KINDS = {"succeeded", "failed", "cancelled", "timed-out", "usage-limited", "end-inferred"}
COMPLETION_REASON_CODES = {
    "succeeded": {"completed"},
    "failed": {"process-exit", "start-failed"},
    "cancelled": {"cancelled"},
    "timed-out": {"timeout"},
    "usage-limited": {"usage-limit"},
    "end-inferred": {"crash-inferred"},
}
COMPLETION_PRIVACY_ASSERTIONS = {
    "prompt_absent", "transcript_absent", "raw_output_absent", "environment_absent",
    "credentials_absent", "absolute_paths_absent", "claim_proofs_absent",
}
PROHIBITED_COMPLETION_KEYS = {
    "prompt", "transcript", "raw_output", "rawoutput", "stdout", "stderr", "environment", "env",
    "secret", "secrets", "token", "password", "credential", "credentials", "claim_token",
    "access_token", "accesstoken", "client_secret", "clientsecret", "claim_proof", "claimproof", "worktree",
    "request_snapshot", "requestsnapshot", "provenance", "api_key", "apikey",
    "command_output", "commandoutput", "failure_details", "failuredetails", "failure_detail",
    "request_body", "requestbody", "headers",
}
SECRET_LIKE_VALUE = re.compile(
    r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~+/=-]{8,}|\b(?:sk|ghp|github_pat)_[A-Za-z0-9_-]{8,})"
)
ABSOLUTE_PATH_VALUE = re.compile(r"^(?:/|[A-Za-z]:[\\/]|\\\\)")


def _require(value: dict[str, Any], fields: tuple[str, ...], path: Path) -> None:
    missing = [field for field in fields if field not in value]
    if missing:
        raise ValueError(f"{path}: missing fields: {', '.join(missing)}")


def _uuid(value: Any, field: str, path: Path) -> None:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise ValueError(f"{path}: {field} must be a lowercase UUID")


def _non_blank(value: Any, field: str, path: Path) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {field} must be a non-empty string")


def _validate_ref(ref: Any, field: str, path: Path) -> None:
    if not isinstance(ref, dict):
        raise ValueError(f"{path}: {field} must be an object")
    _require(ref, ("kind", "source", "revision"), path)
    if ref["kind"] not in REF_KINDS:
        raise ValueError(f"{path}: {field}.kind {ref['kind']!r} is not a recognized ref kind")
    _non_blank(ref["source"], f"{field}.source", path)
    _non_blank(ref["revision"], f"{field}.revision", path)


def _timestamp(value: Any, field: str, path: Path) -> datetime:
    _non_blank(value, field, path)
    if not value.endswith("Z"):
        raise ValueError(f"{path}: {field} must be a UTC timestamp ending in Z")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError(f"{path}: {field} must be an RFC 3339 timestamp") from exc


def _reject_prohibited_completion_keys(value: Any, path: Path, prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            dotted = f"{prefix}.{key}" if prefix else key
            normalized_key = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            if normalized_key in PROHIBITED_COMPLETION_KEYS:
                raise ValueError(f"{path}: prohibited completion field {dotted!r}")
            _reject_prohibited_completion_keys(child, path, dotted)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_prohibited_completion_keys(child, path, f"{prefix}[{index}]")
    elif isinstance(value, str) and SECRET_LIKE_VALUE.search(value):
        raise ValueError(f"{path}: secret-like content is prohibited at {prefix!r}")
    elif isinstance(value, str) and ABSOLUTE_PATH_VALUE.match(value):
        raise ValueError(f"{path}: absolute path is prohibited at {prefix!r}")


def validate_session_completion_observed(value: dict[str, Any], path: Path) -> None:
    _require(value, (
        "event_id", "origin_stream_id", "origin_sequence", "runtime_session_id", "attempt_id",
        "action_id", "repo", "harness", "model", "terminal", "started_at", "completed_at",
        "observed_at", "duration_ms", "refs", "evidence", "privacy",
    ), path)
    _reject_prohibited_completion_keys(value, path)
    _uuid(value["event_id"], "event_id", path)
    _uuid(value["origin_stream_id"], "origin_stream_id", path)
    if isinstance(value["origin_sequence"], bool) or not isinstance(value["origin_sequence"], int) or value["origin_sequence"] <= 0:
        raise ValueError(f"{path}: origin_sequence must be a positive integer")
    _non_blank(value["runtime_session_id"], "runtime_session_id", path)
    attempt_id, action_id = value["attempt_id"], value["action_id"]
    if (attempt_id is None) != (action_id is None):
        raise ValueError(f"{path}: attempt_id and action_id must both be null or both be present")
    if attempt_id is not None:
        _non_blank(attempt_id, "attempt_id", path)
        _non_blank(action_id, "action_id", path)
    repo = value["repo"]
    if not isinstance(repo, dict):
        raise ValueError(f"{path}: repo must be an object")
    _require(repo, ("project",), path)
    _non_blank(repo["project"], "repo.project", path)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", repo["project"]):
        raise ValueError(f"{path}: repo.project must be a portable identifier")
    if "repo_id" in repo:
        _uuid(repo["repo_id"], "repo.repo_id", path)
    _non_blank(value["harness"], "harness", path)
    model = value["model"]
    if model is not None:
        if not isinstance(model, dict):
            raise ValueError(f"{path}: model must be null or an object")
        _require(model, ("name",), path)
        _non_blank(model["name"], "model.name", path)
        if "version" in model and not isinstance(model["version"], str):
            raise ValueError(f"{path}: model.version must be a string")

    terminal = value["terminal"]
    if not isinstance(terminal, dict):
        raise ValueError(f"{path}: terminal must be an object")
    _require(terminal, ("kind", "exit_code", "reason_code", "retryable"), path)
    kind = terminal["kind"]
    if kind not in COMPLETION_KINDS:
        raise ValueError(f"{path}: terminal.kind {kind!r} is not recognized")
    if terminal["reason_code"] not in COMPLETION_REASON_CODES[kind]:
        raise ValueError(f"{path}: terminal.reason_code is invalid for terminal.kind {kind!r}")
    if not isinstance(terminal["retryable"], bool):
        raise ValueError(f"{path}: terminal.retryable must be a boolean")
    exit_code = terminal["exit_code"]
    if isinstance(exit_code, bool) or (exit_code is not None and not isinstance(exit_code, int)):
        raise ValueError(f"{path}: terminal.exit_code must be null or an integer")
    if kind == "succeeded" and (exit_code != 0 or terminal["retryable"]):
        raise ValueError(f"{path}: succeeded requires exit_code 0 and retryable false")
    if kind == "failed" and terminal["reason_code"] == "process-exit" and (isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code == 0):
        raise ValueError(f"{path}: process-exit failure requires a non-zero exit_code")
    if kind in {"cancelled", "timed-out", "usage-limited", "end-inferred"} and exit_code is not None:
        raise ValueError(f"{path}: terminal.kind {kind!r} requires a null exit_code")

    started = _timestamp(value["started_at"], "started_at", path)
    completed = _timestamp(value["completed_at"], "completed_at", path)
    observed = _timestamp(value["observed_at"], "observed_at", path)
    if completed < started or observed < completed:
        raise ValueError(f"{path}: timestamps must satisfy started_at <= completed_at <= observed_at")
    duration = value["duration_ms"]
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int) or duration < 0):
        raise ValueError(f"{path}: duration_ms must be null or a non-negative integer")
    refs = value["refs"]
    if not isinstance(refs, list):
        raise ValueError(f"{path}: refs must be an array")
    for ref in refs:
        _validate_ref(ref, "refs[]", path)
    evidence = value["evidence"]
    if not isinstance(evidence, dict):
        raise ValueError(f"{path}: evidence must be an object")
    _require(evidence, ("dirty", "commit_count", "verification"), path)
    if not isinstance(evidence["dirty"], bool):
        raise ValueError(f"{path}: evidence.dirty must be a boolean")
    verification = evidence["verification"]
    if not isinstance(verification, dict):
        raise ValueError(f"{path}: evidence.verification must be an object")
    _require(verification, ("pass", "fail", "error"), path)
    for field in ("commit_count",):
        if isinstance(evidence[field], bool) or not isinstance(evidence[field], int) or evidence[field] < 0:
            raise ValueError(f"{path}: evidence.{field} must be a non-negative integer")
    for field in ("pass", "fail", "error"):
        count = verification[field]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError(f"{path}: evidence.verification.{field} must be a non-negative integer")
    privacy = value["privacy"]
    if not isinstance(privacy, dict):
        raise ValueError(f"{path}: privacy must be an object")
    _require(privacy, tuple(sorted(COMPLETION_PRIVACY_ASSERTIONS)), path)
    if any(privacy[field] is not True for field in COMPLETION_PRIVACY_ASSERTIONS):
        raise ValueError(f"{path}: every completion privacy assertion must be true")


def validate_session_capsule(value: dict[str, Any], path: Path) -> None:
    _require(
        value,
        (
            "capsule_id",
            "origin_stream_id",
            "runtime_session_id",
            "repo",
            "harness",
            "model",
            "actor",
            "target",
            "claim",
            "starting_watermark",
            "started_at",
            "ended_at",
            "end",
            "git",
            "verification",
            "privacy",
        ),
        path,
    )
    _uuid(value["capsule_id"], "capsule_id", path)
    _uuid(value["origin_stream_id"], "origin_stream_id", path)
    _non_blank(value["runtime_session_id"], "runtime_session_id", path)
    _non_blank(value.get("repo", {}).get("project"), "repo.project", path)
    _non_blank(value["harness"], "harness", path)
    _non_blank(value["actor"], "actor", path)

    model = value["model"]
    if model is not None:
        if not isinstance(model, dict) or not model.get("name"):
            raise ValueError(f"{path}: model must be null or an object with a non-empty name")

    target = value["target"]
    claim = value["claim"]
    if target is not None:
        if not isinstance(target, dict):
            raise ValueError(f"{path}: target must be null or an object")
        _require(target, ("rank", "ref"), path)
        if target["rank"] not in TARGET_RANKS:
            raise ValueError(f"{path}: target.rank {target['rank']!r} is not a recognized rank")
        _non_blank(target["ref"], "target.ref", path)
    if claim is not None:
        if not isinstance(claim, dict):
            raise ValueError(f"{path}: claim must be null or an object")
        _require(claim, ("claim_id", "work_item_id", "claim_type", "acquired_automatically"), path)
        if claim["acquired_automatically"] and (target is None or target["rank"] != "explicit"):
            raise ValueError(
                f"{path}: claim.acquired_automatically requires target.rank == explicit"
            )

    watermark = value["starting_watermark"]
    _require(watermark, ("ingest_offset", "age_seconds"), path)

    end = value["end"]
    _require(end, ("kind",), path)
    if end["kind"] not in {"clean-end", "end-inferred"}:
        raise ValueError(f"{path}: end.kind must be clean-end or end-inferred")

    git = value["git"]
    _require(
        git,
        ("base_commit", "head_commit", "commits", "branch", "worktree", "dirty", "diff_stat", "touched_paths"),
        path,
    )
    if not _GIT_SHA.fullmatch(git["base_commit"]) or not _GIT_SHA.fullmatch(git["head_commit"]):
        raise ValueError(f"{path}: git.base_commit and git.head_commit must be full Git object ids")
    for sha in git["commits"]:
        if not _GIT_SHA.fullmatch(sha):
            raise ValueError(f"{path}: git.commits entries must be full Git object ids")
    patch_digest = git.get("patch_digest")
    if patch_digest is not None and not _SHA256.fullmatch(patch_digest):
        raise ValueError(f"{path}: git.patch_digest must be null or a lowercase sha256")
    if git["dirty"] and not patch_digest:
        raise ValueError(f"{path}: git.patch_digest is required when git.dirty is true")
    _require(git["diff_stat"], ("files_changed", "insertions", "deletions"), path)

    for entry in value["verification"]:
        _require(entry, ("command", "result"), path)
        if entry["result"] not in VERIFICATION_RESULTS:
            raise ValueError(f"{path}: verification result {entry['result']!r} is not recognized")
        evidence_ref = entry.get("evidence_ref")
        if evidence_ref is not None:
            _validate_ref(evidence_ref, "verification[].evidence_ref", path)

    privacy = value["privacy"]
    _require(privacy, ("raw_transcript_captured",), path)
    if not privacy["raw_transcript_captured"] and privacy.get("raw_transcript_ref"):
        raise ValueError(f"{path}: raw_transcript_ref must be null when raw_transcript_captured is false")


def validate_reconciliation_proposal(value: dict[str, Any], path: Path) -> None:
    _require(
        value,
        (
            "proposal_id",
            "dedup_key",
            "created_at",
            "source_capsules",
            "evidence_refs",
            "basis",
            "target",
            "classification",
            "proposed_commands",
            "confidence",
            "lifecycle",
        ),
        path,
    )
    _uuid(value["proposal_id"], "proposal_id", path)
    _non_blank(value["dedup_key"], "dedup_key", path)

    source_capsules = value["source_capsules"]
    if not isinstance(source_capsules, list) or not source_capsules:
        raise ValueError(f"{path}: source_capsules must be a non-empty array")
    for entry in source_capsules:
        _require(entry, ("runtime_session_id", "capsule_ref"), path)
        _non_blank(entry["runtime_session_id"], "source_capsules[].runtime_session_id", path)
        _validate_ref(entry["capsule_ref"], "source_capsules[].capsule_ref", path)

    for ref in value["evidence_refs"]:
        _validate_ref(ref, "evidence_refs[]", path)

    _require(value["basis"], ("observed_revision", "current_revision"), path)

    classification = value["classification"]
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"{path}: classification {classification!r} is not recognized")

    target = value["target"]
    commands = value["proposed_commands"]
    if classification == "incidental-no-change":
        if target is not None:
            raise ValueError(f"{path}: target must be null when classification is incidental-no-change")
        if commands:
            raise ValueError(f"{path}: proposed_commands must be empty when classification is incidental-no-change")
    else:
        if not isinstance(target, dict):
            raise ValueError(f"{path}: target must be an object when classification is not incidental-no-change")
        _require(target, ("kind", "ref"), path)
        if target["kind"] not in {"work-item", "sprint"}:
            raise ValueError(f"{path}: target.kind must be work-item or sprint")
        if not commands:
            raise ValueError(f"{path}: proposed_commands must be non-empty for classification {classification!r}")
    for command in commands:
        _require(command, ("command_type", "params"), path)
        _non_blank(command["command_type"], "proposed_commands[].command_type", path)

    _require(value["confidence"], ("level", "rationale"), path)
    if value["confidence"]["level"] not in {"high", "medium", "low"}:
        raise ValueError(f"{path}: confidence.level must be high, medium, or low")

    lifecycle = value["lifecycle"]
    _require(lifecycle, ("state",), path)
    state = lifecycle["state"]
    if state not in LIFECYCLE_STATES:
        raise ValueError(f"{path}: lifecycle.state {state!r} is not recognized")
    if state == "pending":
        if lifecycle.get("decided_at") or lifecycle.get("decided_by"):
            raise ValueError(f"{path}: a pending proposal must not carry a decision")
    else:
        if not lifecycle.get("decided_at") or not lifecycle.get("decided_by"):
            raise ValueError(f"{path}: lifecycle.state {state!r} requires decided_at and decided_by")
        if state == "rejected" and not lifecycle.get("rejection_reason"):
            raise ValueError(f"{path}: a rejected proposal requires lifecycle.rejection_reason")
        if state == "superseded":
            superseded_by = lifecycle.get("superseded_by")
            if not superseded_by:
                raise ValueError(f"{path}: a superseded proposal requires lifecycle.superseded_by")
            _uuid(superseded_by, "lifecycle.superseded_by", path)


def validate_session_note(value: dict[str, Any], path: Path) -> None:
    _require(
        value,
        (
            "note_id",
            "origin_stream_id",
            "runtime_session_id",
            "repo",
            "note_kind",
            "target_refs",
            "capsule_ref",
            "created_at",
            "supersedes",
            "body",
            "privacy",
        ),
        path,
    )
    _uuid(value["note_id"], "note_id", path)
    _uuid(value["origin_stream_id"], "origin_stream_id", path)

    runtime_session_id = value["runtime_session_id"]
    if runtime_session_id is not None:
        _non_blank(runtime_session_id, "runtime_session_id", path)

    _non_blank(value.get("repo", {}).get("project"), "repo.project", path)

    if value["note_kind"] not in NOTE_KINDS:
        raise ValueError(f"{path}: note_kind {value['note_kind']!r} is not a recognized kind")

    target_refs = value["target_refs"]
    if not isinstance(target_refs, list):
        raise ValueError(f"{path}: target_refs must be an array")
    for ref in target_refs:
        _non_blank(ref, "target_refs[]", path)

    capsule_ref = value["capsule_ref"]
    if capsule_ref is not None:
        _validate_ref(capsule_ref, "capsule_ref", path)

    supersedes = value["supersedes"]
    if supersedes is not None:
        _uuid(supersedes, "supersedes", path)

    body = value["body"]
    if not isinstance(body, str) or not body.strip():
        raise ValueError(f"{path}: body must be a non-empty string")
    if len(body.encode("utf-8")) > NOTE_BODY_MAX_BYTES:
        raise ValueError(f"{path}: body exceeds {NOTE_BODY_MAX_BYTES} bytes")

    privacy = value["privacy"]
    _require(privacy, ("raw_transcript_captured",), path)
    if not privacy["raw_transcript_captured"] and privacy.get("raw_transcript_ref"):
        raise ValueError(f"{path}: raw_transcript_ref must be null when raw_transcript_captured is false")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level value must be an object")
    return value


def validate(path: Path) -> dict[str, Any]:
    value = load_json(path)
    version = value.get("schema_version")
    if version == "session-capsule/v1":
        validate_session_capsule(value, path)
    elif version == "reconciliation-proposal/v1":
        validate_reconciliation_proposal(value, path)
    elif version == "session-note/v1":
        validate_session_note(value, path)
    elif version == "session.completion-observed/v1":
        validate_session_completion_observed(value, path)
    else:
        raise ValueError(f"{path}: unknown schema_version {version!r}")
    return value


def discover(root: Path) -> list[Path]:
    return sorted(
        set(root.glob("session-capsules/*.json"))
        | set(root.glob("reconciliation-proposals/*.json"))
        | set(root.glob("session-notes/*.json"))
        | set(root.glob("session-completions/*.json"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    paths = args.paths or discover(root)
    seen_ids: set[str] = set()
    seen_stream_positions: set[tuple[str, int]] = set()
    for path in paths:
        value = validate(path)
        artifact_id = value.get("capsule_id") or value.get("proposal_id") or value.get("note_id") or value.get("event_id")
        if artifact_id in seen_ids:
            raise ValueError(f"{path}: duplicate artifact id {artifact_id!r}")
        seen_ids.add(artifact_id)
        if value.get("schema_version") == "session.completion-observed/v1":
            position = (value["origin_stream_id"], value["origin_sequence"])
            if position in seen_stream_positions:
                raise ValueError(f"{path}: duplicate origin stream position {position!r}")
            seen_stream_positions.add(position)
        print(f"ok {path}")
    if not paths:
        print("no session mechanization artifacts found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
