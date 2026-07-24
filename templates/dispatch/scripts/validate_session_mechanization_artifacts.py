#!/usr/bin/env python3
"""Validate session-capsule/v1, reconciliation-proposal/v1, and session-note/v1 artifacts without dependencies."""

from __future__ import annotations

import argparse
import json
import re
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
    else:
        raise ValueError(f"{path}: unknown schema_version {version!r}")
    return value


def discover(root: Path) -> list[Path]:
    return sorted(
        set(root.glob("session-capsules/*.json"))
        | set(root.glob("reconciliation-proposals/*.json"))
        | set(root.glob("session-notes/*.json"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    paths = args.paths or discover(root)
    seen_ids: set[str] = set()
    for path in paths:
        value = validate(path)
        artifact_id = value.get("capsule_id") or value.get("proposal_id") or value.get("note_id")
        if artifact_id in seen_ids:
            raise ValueError(f"{path}: duplicate artifact id {artifact_id!r}")
        seen_ids.add(artifact_id)
        print(f"ok {path}")
    if not paths:
        print("no session mechanization artifacts found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
