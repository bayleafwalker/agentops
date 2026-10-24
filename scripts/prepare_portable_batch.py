#!/usr/bin/env python3
"""Prepare a deterministic, local-only portable programme dry-run packet.

The command reads a caller-supplied request and local Git object databases. It
never fetches source, contacts an owner, grants access, dispatches work, or
changes a repository. Output is a review packet, not an authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from verify_portable_batch_pins import PinError, load_manifest, state_for_repo

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PIN_MANIFEST = SCRIPT_ROOT / "docs/plans/agentops/portable-feature-batch-pins.v1.json"
MAX_REQUEST_BYTES = 1_048_576
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 100_000
MAX_REPOSITORIES = 32
MAX_DEPENDENCIES = 256
MAX_OBSERVATIONS = 256
MAX_TEXT = 4096
MAX_DEPENDENCY_BLOB_BYTES = 4 * 1024 * 1024
OWNER = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
IDENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
OBJECT_ID = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BRANCH = re.compile(r"^[A-Za-z0-9._/-]{1,240}$")
CANONICAL_REPO = re.compile(r"^[A-Za-z0-9.-]+/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$")
SCP_REMOTE = re.compile(r"^(?:[^/@:]+@)?(?P<host>[^/:]+):(?P<path>.+)$")
MONEY = re.compile(r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?$")
ACCESS = {"source-read", "candidate-write", "artifact-read"}
OBSERVATION_STATES = {"ready", "blocked", "unknown", "stale", "refused", "uncertain"}


class PacketError(ValueError):
    """Invalid request or local source observation."""


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
                raise PacketError("request file exceeds JSON depth limit")
        elif char in "]}":
            depth -= 1
        elif char == ",":
            nodes += 1
        if nodes > MAX_JSON_NODES:
            raise PacketError("request file exceeds JSON node limit")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PacketError("duplicate JSON object key")
        result[key] = value
    return result


def _constant(_value: str) -> Any:
    raise PacketError("non-finite JSON number")


def _keys(value: Any, required: set[str], allowed: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PacketError(f"{label} must be an object")
    missing = required - set(value)
    extra = set(value) - allowed
    if missing:
        raise PacketError(f"{label} is missing required fields")
    if extra:
        raise PacketError(f"{label} has unknown fields")
    return value


def _text(value: Any, label: str, *, maximum: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise PacketError(f"{label} must be non-empty text within its limit")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise PacketError(f"{label} contains an invalid Unicode scalar")
    return value


def _identity(value: Any, label: str, pattern: re.Pattern[str] = IDENT) -> str:
    text = _text(value, label, maximum=256)
    if not pattern.fullmatch(text):
        raise PacketError(f"{label} has an invalid identifier")
    return text


def _branch(value: Any, label: str) -> str:
    branch = _text(value, label, maximum=240)
    if (
        not BRANCH.fullmatch(branch)
        or branch.startswith("/")
        or branch.endswith("/")
        or ".." in branch
        or "@{" in branch
        or "//" in branch
        or any(
            part.startswith(".") or part.endswith(".") or part.endswith(".lock")
            for part in branch.split("/")
        )
    ):
        raise PacketError(f"{label} has an invalid branch name")
    return branch


def _canonical_repository_id(value: Any, label: str) -> str:
    repository_id = _text(value, label, maximum=512)
    if not CANONICAL_REPO.fullmatch(repository_id):
        raise PacketError(f"{label} must use host/namespace/repository form")
    host, _, path = repository_id.partition("/")
    return f"{host.lower()}/{path}"


def _repo_path(value: Any, label: str) -> str:
    path = _text(value, label, maximum=512)
    pure = PurePosixPath(path)
    if (
        path.startswith("/")
        or "\\" in path
        or "\x00" in path
        or any(part in ("", ".", "..") for part in path.split("/"))
        or pure.is_absolute()
    ):
        raise PacketError(f"{label} must be a normalized repository-relative path")
    return path


def _aware_datetime(value: Any, label: str) -> str:
    text = _text(value, label, maximum=80)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise PacketError(f"{label} must be an offset-aware ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PacketError(f"{label} must be an offset-aware ISO timestamp")
    return parsed.isoformat()


def _load_request(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_REQUEST_BYTES + 1)
    except OSError as exc:
        raise PacketError("cannot read request file") from exc
    if len(raw) > MAX_REQUEST_BYTES:
        raise PacketError("request file exceeds 1 MiB")
    try:
        decoded = raw.decode("utf-8")
        _check_json_bounds(decoded)
        value = json.loads(decoded, object_pairs_hook=_pairs, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, PacketError, RecursionError):
        raise PacketError("request file is not strict UTF-8 JSON") from None
    if not isinstance(value, dict):
        raise PacketError("request root must be an object")
    return value


def _validate_request(raw: dict[str, Any]) -> dict[str, Any]:
    root = _keys(
        raw,
        {
            "schema",
            "request_id",
            "goal",
            "completion_evidence",
            "repositories",
            "dependencies",
            "bounds",
            "readiness_observations",
            "review_policy",
            "landing_policy",
        },
        {
            "schema",
            "request_id",
            "goal",
            "completion_evidence",
            "repositories",
            "dependencies",
            "bounds",
            "readiness_observations",
            "review_policy",
            "landing_policy",
        },
        "request",
    )
    if root["schema"] != "portable-programme-run-request/v1":
        raise PacketError("unsupported request schema")
    normalized: dict[str, Any] = {
        "schema": root["schema"],
        "request_id": _identity(root["request_id"], "request_id"),
        "goal": _text(root["goal"], "goal", maximum=8000),
    }

    completion = root["completion_evidence"]
    if not isinstance(completion, list) or not 1 <= len(completion) <= 32:
        raise PacketError("completion_evidence must contain 1..32 entries")
    normalized["completion_evidence"] = [
        _text(item, "completion evidence", maximum=1000) for item in completion
    ]

    repositories = root["repositories"]
    if not isinstance(repositories, list) or not 1 <= len(repositories) <= MAX_REPOSITORIES:
        raise PacketError("repositories must contain 1..32 entries")
    seen_owners: set[str] = set()
    normalized_repositories = []
    for index, item in enumerate(repositories):
        label = f"repositories[{index}]"
        row = _keys(
            item,
            {
                "owner",
                "repository_id",
                "source_branch",
                "source_commit",
                "target_branch",
                "permitted_paths",
                "access_class",
                "requested_harness",
                "requested_model",
            },
            {
                "owner",
                "repository_id",
                "source_branch",
                "source_commit",
                "target_branch",
                "permitted_paths",
                "access_class",
                "requested_harness",
                "requested_model",
            },
            label,
        )
        owner = _identity(row["owner"], f"{label}.owner", OWNER)
        if owner in seen_owners:
            raise PacketError("repository owners must be unique")
        seen_owners.add(owner)
        repo_id = _canonical_repository_id(row["repository_id"], f"{label}.repository_id")
        commit = _text(row["source_commit"], f"{label}.source_commit", maximum=64)
        if not OBJECT_ID.fullmatch(commit):
            raise PacketError(f"{label}.source_commit must be a full lowercase object ID")
        access = row["access_class"]
        if not isinstance(access, str) or access not in ACCESS:
            raise PacketError(f"{label}.access_class is unsupported")
        paths = row["permitted_paths"]
        if not isinstance(paths, list) or not 1 <= len(paths) <= 128:
            raise PacketError(f"{label}.permitted_paths must contain 1..128 entries")
        normalized_paths = [_repo_path(v, f"{label}.permitted_paths") for v in paths]
        if len(set(normalized_paths)) != len(normalized_paths):
            raise PacketError(f"{label}.permitted_paths contains duplicates")
        normalized_repositories.append(
            {
                "owner": owner,
                "repository_id": repo_id,
                "source_branch": _branch(row["source_branch"], f"{label}.source_branch"),
                "source_commit": commit,
                "target_branch": _branch(row["target_branch"], f"{label}.target_branch"),
                "permitted_paths": sorted(normalized_paths),
                "access_class": access,
                "requested_harness": _text(row["requested_harness"], f"{label}.requested_harness", maximum=160),
                "requested_model": _text(row["requested_model"], f"{label}.requested_model", maximum=160),
            }
        )
    normalized["repositories"] = sorted(normalized_repositories, key=lambda row: row["owner"])

    dependencies = root["dependencies"]
    if not isinstance(dependencies, list) or len(dependencies) > MAX_DEPENDENCIES:
        raise PacketError("dependencies must contain 0..256 entries")
    seen_dependencies: set[str] = set()
    normalized_dependencies = []
    for index, item in enumerate(dependencies):
        label = f"dependencies[{index}]"
        row = _keys(
            item,
            {"id", "owner", "commit", "path", "sha256", "purpose", "access_class"},
            {"id", "owner", "commit", "path", "sha256", "purpose", "access_class"},
            label,
        )
        dependency_id = _identity(row["id"], f"{label}.id")
        if dependency_id in seen_dependencies:
            raise PacketError("dependency IDs must be unique")
        seen_dependencies.add(dependency_id)
        owner = _identity(row["owner"], f"{label}.owner", OWNER)
        commit = _text(row["commit"], f"{label}.commit", maximum=64)
        digest = _text(row["sha256"], f"{label}.sha256", maximum=64)
        if not OBJECT_ID.fullmatch(commit) or not SHA256.fullmatch(digest):
            raise PacketError(f"{label} has an invalid commit or digest")
        access = row["access_class"]
        if not isinstance(access, str) or access not in {"source-read", "artifact-read"}:
            raise PacketError(f"{label}.access_class must be source-read or artifact-read")
        normalized_dependencies.append(
            {
                "id": dependency_id,
                "owner": owner,
                "commit": commit,
                "path": _repo_path(row["path"], f"{label}.path"),
                "sha256": digest,
                "purpose": _text(row["purpose"], f"{label}.purpose", maximum=1000),
                "access_class": access,
            }
        )
    owner_set = seen_owners
    if any(item["owner"] not in owner_set for item in normalized_dependencies):
        raise PacketError("every dependency owner must have a repository entry")
    normalized["dependencies"] = sorted(normalized_dependencies, key=lambda row: row["id"])

    bounds = _keys(
        root["bounds"],
        {
            "deadline_utc",
            "spend_limit_usd",
            "aggregate_concurrency",
            "replanning_limit",
            "checkpoint_interval_seconds",
            "stop_conditions",
            "escalation_route",
        },
        {
            "deadline_utc",
            "spend_limit_usd",
            "aggregate_concurrency",
            "replanning_limit",
            "checkpoint_interval_seconds",
            "stop_conditions",
            "escalation_route",
        },
        "bounds",
    )
    spend = _text(bounds["spend_limit_usd"], "spend_limit_usd", maximum=16)
    if not MONEY.fullmatch(spend):
        raise PacketError("spend_limit_usd must be a non-negative decimal string")
    concurrency = bounds["aggregate_concurrency"]
    replans = bounds["replanning_limit"]
    checkpoint = bounds["checkpoint_interval_seconds"]
    if type(concurrency) is not int or not 1 <= concurrency <= 32:
        raise PacketError("aggregate_concurrency must be an integer in 1..32")
    if type(replans) is not int or not 0 <= replans <= 100:
        raise PacketError("replanning_limit must be an integer in 0..100")
    if type(checkpoint) is not int or not 30 <= checkpoint <= 86_400:
        raise PacketError("checkpoint_interval_seconds must be in 30..86400")
    stop_conditions = bounds["stop_conditions"]
    if not isinstance(stop_conditions, list) or not 1 <= len(stop_conditions) <= 32:
        raise PacketError("stop_conditions must contain 1..32 entries")
    normalized["bounds"] = {
        "deadline_utc": _aware_datetime(bounds["deadline_utc"], "deadline_utc"),
        "spend_limit_usd": spend,
        "aggregate_concurrency": concurrency,
        "replanning_limit": replans,
        "checkpoint_interval_seconds": checkpoint,
        "stop_conditions": [_text(v, "stop condition", maximum=500) for v in stop_conditions],
        "escalation_route": _text(bounds["escalation_route"], "escalation_route", maximum=500),
    }

    observations = root["readiness_observations"]
    if not isinstance(observations, list) or len(observations) > MAX_OBSERVATIONS:
        raise PacketError("readiness_observations must contain 0..256 entries")
    normalized_observations = []
    for index, item in enumerate(observations):
        label = f"readiness_observations[{index}]"
        row = _keys(
            item,
            {"owner", "kind", "reported_state"},
            {"owner", "kind", "reported_state", "observed_at", "evidence_id"},
            label,
        )
        owner = _identity(row["owner"], f"{label}.owner", OWNER)
        state = row["reported_state"]
        if (
            owner not in owner_set
            or not isinstance(state, str)
            or state not in OBSERVATION_STATES
        ):
            raise PacketError(f"{label} has an unknown owner or state")
        observation = {
            "owner": owner,
            "kind": _identity(row["kind"], f"{label}.kind"),
            "reported_state": state,
        }
        if "observed_at" in row:
            observation["observed_at"] = _aware_datetime(row["observed_at"], f"{label}.observed_at")
        if "evidence_id" in row:
            evidence_id = _identity(row["evidence_id"], f"{label}.evidence_id")
            if evidence_id not in seen_dependencies:
                raise PacketError(f"{label}.evidence_id must name a dependency")
            observation["evidence_id"] = evidence_id
        normalized_observations.append(observation)
    normalized["readiness_observations"] = sorted(
        normalized_observations,
        key=lambda row: (row["owner"], row["kind"], row["reported_state"]),
    )

    if root["review_policy"] != "independent-exact-head-review":
        raise PacketError("review_policy must be independent-exact-head-review")
    if not isinstance(root["landing_policy"], str) or root["landing_policy"] not in {
        "candidate-only",
        "hold-for-operator",
    }:
        raise PacketError("landing_policy must retain candidate-only operator control")
    normalized["review_policy"] = root["review_policy"]
    normalized["landing_policy"] = root["landing_policy"]
    return normalized


def _git(repo: str, *args: str) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return subprocess.run(
        ["git", "-C", repo, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )


def _origin_identity(repo: str) -> str | None:
    """Read and normalize only the local origin URL; never print it or connect."""
    origin = _git(repo, "config", "--local", "--get", "remote.origin.url")
    if origin.returncode != 0:
        return None
    try:
        raw = origin.stdout.decode("utf-8").strip()
    except UnicodeError:
        return None
    if not raw or any(ord(ch) < 0x20 for ch in raw):
        return None
    if "://" not in raw:
        match = SCP_REMOTE.fullmatch(raw)
        if match is None:
            return None
        host, path = match.group("host"), match.group("path")
    else:
        try:
            parsed = urlsplit(raw)
            host = parsed.hostname or ""
            path = parsed.path
        except ValueError:
            return None
        if (
            parsed.scheme.lower() not in {"https", "ssh", "git"}
            or parsed.port is not None
            or parsed.query
            or parsed.fragment
        ):
            return None
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    identity = f"{host.lower()}/{path}"
    return identity if CANONICAL_REPO.fullmatch(identity) else None


def _source_observation(repo_path: str | None, row: dict[str, Any]) -> dict[str, Any]:
    result = {
        "owner": row["owner"],
        "repository_id": row["repository_id"],
        "source_branch": row["source_branch"],
        "expected_source_commit": row["source_commit"],
        "checks": {
            "repository": "missing",
            "canonical_identity": "unknown",
            "commit_object": "missing",
            "source_branch_tip": "missing",
            "working_tree": "missing",
        },
        "actual_source_branch_tip": None,
        "target_branch_tip": None,
        "target_branch_observation": "unknown",
        "canonical_identity_verification": "unknown",
        "working_tree_state": "unknown",
        "local_repo_path_included": False,
    }
    if repo_path is None:
        return result
    try:
        resolved = str(Path(repo_path).resolve(strict=True))
    except (OSError, RuntimeError):
        result["checks"]["repository"] = "failed"
        return result
    root = _git(resolved, "rev-parse", "--show-toplevel")
    if root.returncode != 0:
        result["checks"]["repository"] = "failed"
        return result
    result["checks"]["repository"] = "passed"
    actual_identity = _origin_identity(resolved)
    identity_status = (
        "unknown"
        if actual_identity is None
        else "passed"
        if actual_identity == row["repository_id"]
        else "mismatch"
    )
    result["checks"]["canonical_identity"] = identity_status
    result["canonical_identity_verification"] = identity_status
    worktree = _git(
        resolved,
        "-c",
        "core.fsmonitor=false",
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    if worktree.returncode == 0:
        is_clean = not worktree.stdout
        result["checks"]["working_tree"] = "passed" if is_clean else "failed"
        result["working_tree_state"] = "clean" if is_clean else "dirty"
    commit_check = _git(resolved, "cat-file", "-e", f"{row['source_commit']}^{{commit}}")
    if commit_check.returncode == 0:
        result["checks"]["commit_object"] = "passed"
    else:
        result["checks"]["commit_object"] = "failed"
    ref = f"refs/heads/{row['source_branch']}"
    tip_check = _git(resolved, "rev-parse", "--verify", ref)
    if tip_check.returncode == 0:
        tip = tip_check.stdout.decode("ascii", errors="replace").strip()
        result["actual_source_branch_tip"] = tip
        result["checks"]["source_branch_tip"] = "passed" if tip == row["source_commit"] else "stale"
    else:
        result["checks"]["source_branch_tip"] = "missing"
    target_ref = f"refs/heads/{row['target_branch']}"
    target = _git(resolved, "rev-parse", "--verify", target_ref)
    if target.returncode == 0:
        result["target_branch_tip"] = target.stdout.decode("ascii", errors="replace").strip()
        result["target_branch_observation"] = "local-tip-observed-not-authorized"
    return result


def _dependency_observation(repo_path: str | None, row: dict[str, Any]) -> dict[str, Any]:
    result = {
        **row,
        "checks": {"commit_object": "missing", "blob": "missing", "sha256": "missing"},
        "actual_sha256": None,
        "verification_scope": "local-git-object-only",
    }
    if repo_path is None:
        return result
    try:
        resolved = str(Path(repo_path).resolve(strict=True))
    except (OSError, RuntimeError):
        return result
    commit = _git(resolved, "cat-file", "-e", f"{row['commit']}^{{commit}}")
    if commit.returncode != 0:
        result["checks"]["commit_object"] = "failed"
        return result
    result["checks"]["commit_object"] = "passed"
    size = _git(resolved, "cat-file", "-s", f"{row['commit']}:{row['path']}")
    if size.returncode != 0:
        result["checks"]["blob"] = "failed"
        return result
    try:
        blob_size = int(size.stdout.decode("ascii").strip())
    except (UnicodeError, ValueError):
        result["checks"]["blob"] = "failed"
        return result
    if blob_size > MAX_DEPENDENCY_BLOB_BYTES:
        result["checks"]["blob"] = "oversized"
        result["checks"]["sha256"] = "unknown"
        return result
    env = os.environ.copy()
    env.update(
        {
            "GIT_NO_LAZY_FETCH": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    try:
        process = subprocess.Popen(
            ["git", "-C", resolved, "cat-file", "blob", f"{row['commit']}:{row['path']}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        digest = hashlib.sha256()
        total = 0
        assert process.stdout is not None
        while True:
            chunk = process.stdout.read(min(65_536, MAX_DEPENDENCY_BLOB_BYTES + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_DEPENDENCY_BLOB_BYTES:
                process.kill()
                process.wait()
                result["checks"]["blob"] = "oversized"
                result["checks"]["sha256"] = "unknown"
                return result
            digest.update(chunk)
        return_code = process.wait()
    except OSError:
        result["checks"]["blob"] = "failed"
        return result
    if return_code != 0 or total != blob_size:
        result["checks"]["blob"] = "failed"
        return result
    actual = digest.hexdigest()
    result["actual_sha256"] = actual
    result["checks"]["blob"] = "passed"
    result["checks"]["sha256"] = "passed" if actual == row["sha256"] else "mismatch"
    return result


def prepare(
    request: dict[str, Any],
    repo_map: dict[str, str],
    pin_rows: list[dict[str, str]],
) -> dict[str, Any]:
    sources = [
        _source_observation(repo_map.get(row["owner"]), row)
        for row in request["repositories"]
    ]
    dependencies = [
        _dependency_observation(repo_map.get(row["owner"]), row)
        for row in request["dependencies"]
    ]
    pins = []
    for row in pin_rows:
        state = state_for_repo(row, repo_map.get(row["owner"]))
        state.pop("repo_path", None)
        state["status"] = (
            "passed"
            if all(value == "passed" for value in state["checks"].values())
            else "failed"
        )
        pins.append(state)
    source_ok = all(
        all(state == "passed" for state in row["checks"].values())
        for row in sources
    )
    dependency_ok = all(
        all(state == "passed" for state in row["checks"].values())
        for row in dependencies
    )
    pins_ok = all(row["status"] == "passed" for row in pins)
    unknowns = [
        "canonical repository identity was compared only with local origin config; no remote identity or authenticity check occurred",
        "owner readiness observations are caller-provided and not independently authenticated",
        "resolved harness, model, runtime, network, and credential capability is unknown",
        "task submission, acknowledgement, startup, and useful progress are unknown",
        "actual spend and provider-usage coverage are unknown",
        "review, acceptance, landing, and deployment receipts are absent",
        "the local source-branch check does not verify deployed or released versions",
    ]
    packet: dict[str, Any] = {
        "schema": "portable-programme-packet/v1",
        "request": request,
        "status": "prepared-for-review" if source_ok and dependency_ok and pins_ok else "blocked",
        "source_observations": sources,
        "dependency_observations": dependencies,
        "source_pin_observations": pins,
        "readiness_observations": [
            {**row, "verification": "caller-provided-unverified"}
            for row in request["readiness_observations"]
        ],
        "bounds": request["bounds"],
        "authority": {
            "dispatch": "not-authorized-by-packet",
            "grant_changes": "none",
            "landing": "candidate-only-operator-review-required",
            "deployment": "excluded",
        },
        "unknowns": unknowns,
    }
    canonical = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    packet["packet_sha256"] = hashlib.sha256(canonical).hexdigest()
    return packet


def render_text(packet: dict[str, Any]) -> str:
    lines = [
        f"Portable programme packet: {packet['status']}",
        f"Request: {packet['request']['request_id']}",
        f"Goal: {packet['request']['goal']}",
        f"Repositories: {len(packet['source_observations'])}; dependencies: {len(packet['dependency_observations'])}",
        f"Packet SHA256: {packet['packet_sha256']}",
        "Source observations:",
    ]
    for row in packet["source_observations"]:
        states = ", ".join(f"{key}={value}" for key, value in row["checks"].items())
        lines.append(f"  {row['owner']} ({row['repository_id']}): {states}")
    lines.append("Portable batch source pins:")
    for row in packet["source_pin_observations"]:
        lines.append(f"  {row['owner']}: {row['status']} ({row['expected_commit'][:12]})")
    lines.append("Unknowns:")
    lines.extend(f"  - {item}" for item in packet["unknowns"])
    lines.append("Authority: dispatch not authorized; landing candidate-only; deployment excluded")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True, help="strict request JSON")
    parser.add_argument(
        "--pin-manifest",
        type=Path,
        default=DEFAULT_PIN_MANIFEST,
        help=f"local portable batch pin manifest (default: {DEFAULT_PIN_MANIFEST})",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        metavar="OWNER=PATH",
        help="local Git repository path for an owner; repeat as needed",
    )
    parser.add_argument("--format", choices=("json", "text"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = _load_request(args.request)
        request = _validate_request(raw)
        pin_rows = load_manifest(args.pin_manifest)
        repo_map: dict[str, str] = {}
        mapping_errors: list[str] = []
        for value in args.repo:
            owner, separator, path = value.partition("=")
            if not separator or not OWNER.fullmatch(owner) or not path:
                raise PacketError("repository mapping must use OWNER=PATH")
            if owner in repo_map:
                mapping_errors.append(f"duplicate local repository mapping: {owner}")
            else:
                repo_map[owner] = path
        allowed = {row["owner"] for row in request["repositories"]} | {
            row["owner"] for row in pin_rows
        }
        if set(repo_map) - allowed:
            mapping_errors.append("a local repository mapping names an owner outside the request")
        if mapping_errors:
            raise PacketError("; ".join(mapping_errors))
        packet = prepare(request, repo_map, pin_rows)
    except (PacketError, PinError) as exc:
        print(json.dumps({"schema": "portable-programme-packet/v1", "status": "error", "error": str(exc)}, sort_keys=True))
        return 2
    if args.format == "text":
        print(render_text(packet))
    else:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if packet["status"] == "prepared-for-review" else 1


if __name__ == "__main__":
    sys.exit(main())
