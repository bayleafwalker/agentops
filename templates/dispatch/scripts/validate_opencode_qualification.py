#!/usr/bin/env python3
"""Validate the bounded, offline corpus for an OpenCode qualification run.

This command never invokes OpenCode and never changes qualification state.  It
checks the repository opt-in and the packet that a future, single provider run
must satisfy.  A provider receipt can be checked with ``--receipt`` after an
independent review; a passing receipt is a candidate for qualification, not a
promotion of the checked-in profile.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import stat
from typing import Any


ROOT = Path(__file__).parents[3]
DEFAULT_CORPUS = ROOT / "templates/dispatch/provider-qualification/opencode-go-deepseek-v4-flash.json"
DEFAULT_PROFILE = ROOT / "templates/dispatch/harness-profiles/opencode-nixpkgs-devbox-1.18.4.json"
DEFAULT_CONFIG = ROOT / "templates/dispatch/hybrid/opencode.hybrid.json"
DEFAULT_MANIFEST = ROOT / "agentops.dispatch.json"
DEFAULT_PREFLIGHT_ROOT = ROOT / "templates/dispatch/provider-qualification/preflight-evidence"
PROFILE_VALIDATOR_SCRIPT = Path(__file__).with_name("validate_harness_profiles.py")
HYBRID_VALIDATOR_SCRIPT = Path(__file__).with_name("validate_hybrid_dispatch.py")
HYBRID_DISPATCH_SCRIPT = ROOT / "templates/dispatch/scripts/hybrid_dispatch.py"
POLICY_PATH = ROOT / "templates/dispatch/hybrid/hybrid-dispatch.v1.json"
HISTORY_ROOT = ROOT
VERIFY_HISTORY_FILES = True
EXPECTED_MODEL = "opencode-go/deepseek-v4-flash"
EXPECTED_PROVIDER = "opencode-go"
EXPECTED_MODEL_ID = "deepseek-v4-flash"
EXPECTED_REQUEST = {"prompt": "Reply with the bounded qualification acknowledgement.", "agent": "ao-mechanical-bulk", "format": "json"}
EXPECTED_WORKER = "agentworker"
EXPECTED_CLI_VERSION = "1.18.4"
EXPECTED_REQUIRED_PROBES = (
    "cli-version", "run-help", "contained-worktree-model-list", "explicit-tool-enumeration",
    "message-before-file", "json-events", "stable-session-identity", "session-continuation",
    "contained-identity", "no-tools-finalizer", "provider-qualification",
)
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
RUN_ID = re.compile(r"^run-[0-9a-f]{32}$")
RUN_NONCE = re.compile(r"^nonce-[0-9a-f]{64}$")
RUNNER_ID = "agentops-opencode-qualification-runner/v1"
SIGNATURE_NAMESPACE = "agentops-opencode-qualification"
SSH_KEYGEN = "/run/current-system/sw/bin/ssh-keygen"
EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT = "sha256:309ddaae451d99a2350bdbaff31f9e6bfbd9b1f462bb5783e00f26ca41b49a5a"
EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT = "sha256:0192272e12634cc312f56e3b32789be3a0e99e6c4b9295e5b1588bd13cd970a0"
EXPECTED_RUNNER_PUBLIC_KEY_PATH = "/var/lib/agentops/opencode-qualification/runner.pub"
EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH = "/var/lib/agentops/opencode-qualification/allowed_signers"
EXPECTED_RECORD_ROOT = "/var/lib/agentops/opencode-qualification/records"
EXPECTED_LEDGER_ROOT = "/var/lib/agentops/opencode-qualification/ledger"
EXPECTED_EVIDENCE_ROOT = "/var/lib/agentops/opencode-qualification/evidence"
EXPECTED_AUTH_SOURCE = "/var/lib/agentops/opencode-qualification/provider-auth.json"
EXPECTED_AUTH_DISCOVERY = "XDG_DATA_HOME/opencode/auth.json"
EXPECTED_AUTH_CONTENT_ENV = "OPENCODE_AUTH_CONTENT"
EXPECTED_AUTH_PROVIDER = "opencode-go"
EXPECTED_AUTH_TYPE = "api"
EXPECTED_RUNNER_PATH = "/usr/local/sbin/agentops-opencode-qualification-runner"
EXPECTED_OPENCODE_PATH = "/run/current-system/sw/bin/opencode"
RUN_RECORD_SCHEMA = "opencode-provider-qualification-runner-record/v1"
PACKET_SCHEMA = "opencode-provider-qualification-packet/v1"
MAX_RECORD_AGE_SECONDS = 900
MAX_STRING_LENGTH = 256
MAX_FIELD_NAME_LENGTH = 96
ARTIFACT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}\.json$")
PHASE = re.compile(r"^worker$")
CHANNEL_REVISION = re.compile(r"^nixpkgs/nixos-unstable@[0-9a-f]{7,40}$")
SECRET_LIKE = (
    re.compile(r"-----BEGIN [A-Z0-9 ]+-----"),
    re.compile(r"^(?:https?|ssh)://"),
    re.compile(r"(?i)(?:api[_ -]?key|bearer|secret|password|token)\s*[:=]"),
    re.compile(r"^[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}$"),
)
MAX_USAGE_MULTIPLIER = 2
MAX_COST_USD = 3.0
SOFT_TOKEN_CEILING = 500_000
HARD_TOKEN_CEILING = 1_000_000
EXPECTED_OWNER_UID = 0
SENSITIVE_KEYS = frozenset({
    "prompt", "prompts", "transcript", "transcripts", "output", "outputs",
    "stdout", "stderr", "response", "responses", "raw", "path", "paths", "cwd", "command", "argv",
    "credential", "credentials", "secret", "secrets", "api_key", "apiKey",
    "claim_token", "claimToken", "environment", "env", "worktree", "worktree_path",
    "absolute_path", "raw_transcript", "raw_output",
})


class QualificationError(ValueError):
    """A missing or contradictory requirement fails qualification closed."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QualificationError(f"{path}: top-level value must be an object")
    return value


def _keys(value: dict[str, Any], required: set[str], optional: set[str], field: str) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required - optional)
    if missing:
        raise QualificationError(f"{field} is missing fields: {', '.join(missing)}")
    if extra:
        raise QualificationError(f"{field} has unexpected fields: {', '.join(extra)}")


def _non_blank(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QualificationError(f"{field} must be a non-blank string")
    return value


def _sha256_file(path: Path) -> str:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise QualificationError(f"cannot hash {path}: {exc}") from exc


def _digest(value: Any, field: str) -> str:
    text = _non_blank(value, field)
    if not SHA256.fullmatch(text):
        raise QualificationError(f"{field} must be a lowercase sha256 digest")
    return text


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _parse_time(value: Any, field: str) -> datetime:
    text = _non_blank(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise QualificationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise QualificationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite_number(value: Any, field: str, *, positive: bool = False) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or (positive and value <= 0):
        raise QualificationError(f"{field} must be finite numeric evidence")
    return float(value)


def _bundle_digest(artifacts: dict[str, Any]) -> str:
    normalized: dict[str, Any] = {}
    for name in sorted(artifacts):
        descriptor = artifacts[name]
        if not isinstance(descriptor, dict):
            raise QualificationError(f"receipt.evidence_artifacts.{name} is malformed")
        _keys(descriptor, {"artifact", "digest"}, set(), f"receipt.evidence_artifacts.{name}")
        normalized[name] = {"artifact": descriptor["artifact"], "digest": _digest(descriptor["digest"], f"receipt.evidence_artifacts.{name}.digest")}
    return _canonical_digest(normalized)


def _receipt_binding_digest(receipt: dict[str, Any]) -> str:
    binding = dict(receipt)
    binding.pop("runner_record_digest", None)
    binding.pop("runner_signature_digest", None)
    return _canonical_digest(binding)


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise QualificationError(f"cannot load validator {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_inputs(
    corpus: dict[str, Any],
    profile: dict[str, Any],
    config: dict[str, Any],
    manifest: dict[str, Any],
    *,
    corpus_path: Path,
) -> None:
    _keys(corpus, {"schema_version", "corpus_id", "route", "workspace", "containment", "budgets", "live_run", "qualification", "historical_basis"}, set(), "corpus")
    if corpus["schema_version"] != "opencode-provider-qualification/v2":
        raise QualificationError("corpus schema_version is not opencode-provider-qualification/v2")
    _non_blank(corpus["corpus_id"], "corpus.corpus_id")

    route = corpus["route"]
    if not isinstance(route, dict):
        raise QualificationError("corpus.route must be an object")
    _keys(route, {"harness", "agent", "profile_id", "provider_model", "provider", "model", "model_override", "max_attempts"}, set(), "corpus.route")
    if route["harness"] != "opencode" or route["agent"] != "ao-mechanical-bulk":
        raise QualificationError("corpus route is not the OpenCode mechanical-bulk route")
    if route["provider_model"] != EXPECTED_MODEL or route["provider"] != EXPECTED_PROVIDER or route["model"] != EXPECTED_MODEL_ID:
        raise QualificationError("corpus route must name the exact provider/model")
    if route["model_override"] is not False:
        raise QualificationError("provider qualification forbids a model override")
    if route["max_attempts"] != 1:
        raise QualificationError("provider qualification permits exactly one attempt")
    if route["profile_id"] != "opencode-nixpkgs-devbox-1.18.4" or profile.get("profile_id") != route["profile_id"]:
        raise QualificationError("corpus is bound to the reviewed 1.18.4 profile")
    if profile.get("worker_identity") != EXPECTED_WORKER:
        raise QualificationError("profile worker identity must be agentworker")
    if profile.get("qualification") != {"state": "preflight_observed", "blocking_probes": ["contained-identity", "provider-qualification"], "receipt_ref": None, "review_ref": None}:
        raise QualificationError("checked-in profile qualification state is not the reviewed fail-closed state")
    if config.get("model") != EXPECTED_MODEL or config.get("agent", {}).get("ao-mechanical-bulk", {}).get("model") != EXPECTED_MODEL:
        raise QualificationError("checked-in OpenCode config does not bind the exact route model")

    workspace = corpus["workspace"]
    if not isinstance(workspace, dict):
        raise QualificationError("corpus.workspace must be an object")
    _keys(workspace, {"repository_opt_in_required", "provider_workspace_opt_in_required", "usage_multiplier_ceiling"}, set(), "corpus.workspace")
    if workspace["repository_opt_in_required"] is not True or workspace["provider_workspace_opt_in_required"] is not True:
        raise QualificationError("both repository and provider workspace opt-in must be required")
    if workspace["usage_multiplier_ceiling"] != MAX_USAGE_MULTIPLIER:
        raise QualificationError("workspace usage multiplier ceiling must be exactly 2")
    hybrid = manifest.get("hybrid")
    if not isinstance(hybrid, dict) or hybrid.get("enabled") is not True:
        raise QualificationError("repository has not explicitly opted into hybrid dispatch")
    if "mechanical_bulk" not in hybrid.get("worker_routes", []):
        raise QualificationError("repository has not opted into the mechanical_bulk route")
    if not hybrid.get("commands") or not hybrid.get("protected_paths"):
        raise QualificationError("repository opt-in must register commands and protected paths")
    if not manifest.get("scope", {}).get("allowed_path_roots"):
        raise QualificationError("repository opt-in must declare allowed path roots")

    containment = corpus["containment"]
    if not isinstance(containment, dict):
        raise QualificationError("corpus.containment must be an object")
    _keys(containment, {"worker_identity", "coordinator_write_denied", "workspace_round_trip", "exact_groups", "reads_contained"}, set(), "corpus.containment")
    if containment["worker_identity"] != EXPECTED_WORKER or containment["coordinator_write_denied"] is not True or containment["workspace_round_trip"] is not True:
        raise QualificationError("containment requires agentworker, kernel write denial, and a two-way workspace round trip")
    if containment["exact_groups"] != ["agentworker", "agentdispatch"]:
        raise QualificationError("containment group set is not the exact reviewed set")
    if containment["reads_contained"] is not False:
        raise QualificationError("corpus must retain the known uncontained-read limitation")

    budgets = corpus["budgets"]
    if not isinstance(budgets, dict):
        raise QualificationError("corpus.budgets must be an object")
    _keys(budgets, {"max_cost_usd", "soft_token_ceiling", "hard_token_ceiling"}, set(), "corpus.budgets")
    if budgets != {"max_cost_usd": MAX_COST_USD, "soft_token_ceiling": SOFT_TOKEN_CEILING, "hard_token_ceiling": HARD_TOKEN_CEILING}:
        raise QualificationError("provider budget does not match the reviewed bounded limits")

    live_run = corpus["live_run"]
    if not isinstance(live_run, dict):
        raise QualificationError("corpus.live_run must be an object")
    _keys(live_run, {"runner_id", "runner_public_key_fingerprint", "runner_public_key_path", "runner_allowed_signers_fingerprint", "runner_allowed_signers_path", "record_root", "consumption_ledger_root", "evidence_root", "provider_auth_source", "provider_auth_discovery", "provider_auth_content_env", "provider_auth_provider", "provider_auth_type", "runner_path", "runner_digest", "opencode_path", "opencode_digest", "preflight_evidence", "one_time", "packet"}, set(), "corpus.live_run")
    if live_run["runner_id"] != RUNNER_ID or live_run["one_time"] is not True:
        raise QualificationError("live run must be issued by the trusted one-time runner")
    if _digest(live_run["runner_public_key_fingerprint"], "corpus.live_run.runner_public_key_fingerprint") != EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT:
        raise QualificationError("corpus is not bound to the pinned trusted runner public key")
    if _digest(live_run["runner_allowed_signers_fingerprint"], "corpus.live_run.runner_allowed_signers_fingerprint") != EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT:
        raise QualificationError("corpus is not bound to the pinned allowed-signers file")
    expected_paths = {
        "runner_public_key_path": EXPECTED_RUNNER_PUBLIC_KEY_PATH,
        "runner_allowed_signers_path": EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH,
        "record_root": EXPECTED_RECORD_ROOT,
        "consumption_ledger_root": EXPECTED_LEDGER_ROOT,
        "evidence_root": EXPECTED_EVIDENCE_ROOT,
    }
    for field, expected in expected_paths.items():
        if not isinstance(live_run[field], str) or live_run[field] != expected:
            raise QualificationError(f"corpus.live_run.{field} is not the exact configured trusted path")
    if live_run["provider_auth_source"] != EXPECTED_AUTH_SOURCE or live_run["provider_auth_discovery"] != EXPECTED_AUTH_DISCOVERY or live_run["provider_auth_content_env"] != EXPECTED_AUTH_CONTENT_ENV or live_run["provider_auth_provider"] != EXPECTED_AUTH_PROVIDER or live_run["provider_auth_type"] != EXPECTED_AUTH_TYPE:
        raise QualificationError("corpus provider authentication provisioning is not the exact native OpenCode contract")
    if live_run["runner_path"] != EXPECTED_RUNNER_PATH or live_run["opencode_path"] != EXPECTED_OPENCODE_PATH:
        raise QualificationError("corpus live executable paths are not exact")
    _digest(live_run["runner_digest"], "corpus.live_run.runner_digest")
    _digest(live_run["opencode_digest"], "corpus.live_run.opencode_digest")
    preflight = live_run["preflight_evidence"]
    if not isinstance(preflight, dict) or set(preflight) != {"capability.json", "lifecycle.json", "overlay.json", "workspace.json"}:
        raise QualificationError("corpus preflight evidence pins are incomplete")
    for name, digest in preflight.items():
        _digest(digest, f"corpus.live_run.preflight_evidence.{name}")
        source = DEFAULT_PREFLIGHT_ROOT / name
        if not source.is_file() or _sha256_file(source) != digest:
            raise QualificationError(f"checked-in preflight evidence bytes are not pinned for {name}")
    packet = live_run["packet"]
    if not isinstance(packet, dict):
        raise QualificationError("corpus.live_run.packet must be an object")
    _keys(packet, {"schema_version", "packet_id", "route", "profile_id", "provider_model", "agent", "model_override", "task_class", "action_id", "allowed_command_ids", "attempts", "soft_token_ceiling", "hard_token_ceiling", "freshness_window_seconds", "provider_origin_required", "containment_probe_required", "request"}, set(), "corpus.live_run.packet")
    if packet["schema_version"] != PACKET_SCHEMA or packet["route"] != "mechanical_bulk" or packet["profile_id"] != route["profile_id"] or packet["provider_model"] != EXPECTED_MODEL or packet["agent"] != "ao-mechanical-bulk" or packet["model_override"] is not False or packet["task_class"] != "docs-only-qualification" or packet["action_id"] != "opencode-provider-qualification-v1":
        raise QualificationError("live packet is not bound to the exact qualification action")
    if packet["allowed_command_ids"] != ["agentops.dispatch.tests"] or packet["attempts"] != 1 or packet["soft_token_ceiling"] != SOFT_TOKEN_CEILING or packet["hard_token_ceiling"] != HARD_TOKEN_CEILING or packet["freshness_window_seconds"] != MAX_RECORD_AGE_SECONDS or packet["provider_origin_required"] is not True or packet["containment_probe_required"] is not True:
        raise QualificationError("live packet limits or evidence requirements are not bounded")
    if packet["request"] != EXPECTED_REQUEST:
        raise QualificationError("live packet request is not the exact pinned request")

    qualification = corpus["qualification"]
    if not isinstance(qualification, dict):
        raise QualificationError("corpus.qualification must be an object")
    _keys(qualification, {"state", "qualification_eligible", "blocking_probes", "live_run_required"}, set(), "corpus.qualification")
    if qualification["state"] != "preflight_observed" or qualification["qualification_eligible"] is not False:
        raise QualificationError("corpus must remain preflight_observed and ineligible")
    if "provider-qualification" not in qualification["blocking_probes"] or qualification["live_run_required"] is not True:
        raise QualificationError("provider qualification must remain an explicit live blocker")
    if not isinstance(corpus["historical_basis"], list) or not corpus["historical_basis"]:
        raise QualificationError("historical basis must be retained")
    for item in corpus["historical_basis"]:
        if not isinstance(item, dict) or set(item) != {"kind", "source", "claim"}:
            raise QualificationError("historical basis entries must identify a source and claim")
        if item["kind"] not in {"commit", "document"}:
            raise QualificationError("historical basis kind is unsupported")
        _non_blank(item["source"], "corpus.historical_basis[].source")
        _non_blank(item["claim"], "corpus.historical_basis[].claim")
        if item["kind"] == "document":
            source_path = HISTORY_ROOT / item["source"]
            if VERIFY_HISTORY_FILES and not source_path.is_file():
                raise QualificationError(f"historical basis document does not exist: {item['source']}")


def _reject_sensitive(value: Any, path: str = "receipt") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in SENSITIVE_KEYS:
                raise QualificationError(f"{path}.{key} is not allowed in a qualification receipt")
            if isinstance(key, str) and (key.startswith("/") or "/projects/" in key):
                raise QualificationError(f"{path} contains an absolute workspace path in a field name")
            if key == "$schema" and child == "https://opencode.ai/config.json":
                continue
            _reject_sensitive(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if value.startswith("/") or "/projects/" in value:
            raise QualificationError(f"{path} must not contain an absolute workspace path")
        if any(pattern.search(value) for pattern in SECRET_LIKE):
            raise QualificationError(f"{path} contains secret-like or externally addressable text")


def _validate_bounded_strings(value: Any, path: str = "receipt") -> None:
    """Keep every retained string structurally bounded and control-free."""
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > MAX_FIELD_NAME_LENGTH:
                raise QualificationError(f"{path} contains an overlong field name")
            _validate_bounded_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_bounded_strings(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH or any(ord(char) < 0x20 and char not in "\t" for char in value):
            raise QualificationError(f"{path} contains an unbounded or control-bearing string")


def _verify_artifact(root: Path, descriptor: Any, field: str) -> str:
    if not isinstance(descriptor, dict):
        raise QualificationError(f"{field} must describe an evidence artifact")
    _keys(descriptor, {"artifact", "digest"}, set(), field)
    artifact = _non_blank(descriptor["artifact"], f"{field}.artifact")
    if not ARTIFACT_NAME.fullmatch(artifact):
        raise QualificationError(f"{field}.artifact must use the bounded JSON artifact grammar")
    relative = Path(artifact)
    if relative.is_absolute() or ".." in relative.parts:
        raise QualificationError(f"{field}.artifact must stay inside the evidence root")
    _owned_mode(root, {0o700}, f"{field} evidence root")
    _safe_parent_chain(root, f"{field} evidence root")
    root_resolved = root.resolve()
    target = root / relative
    if target.is_symlink() or not target.is_file() or target.resolve() != target:
        raise QualificationError(f"{field}.artifact must be a regular non-symlink file")
    if root_resolved not in target.parents:
        raise QualificationError(f"{field}.artifact escapes the evidence root")
    actual = _sha256_file(target)
    if _digest(descriptor["digest"], f"{field}.digest") != actual:
        raise QualificationError(f"{field}.digest does not match the evidence bytes")
    return actual


def _read_artifact_json(root: Path, descriptor: Any, field: str) -> tuple[str, Any]:
    """Hash, parse, and privacy-check one structural evidence artifact."""
    if not isinstance(descriptor, dict):
        raise QualificationError(f"{field} must describe an evidence artifact")
    _keys(descriptor, {"artifact", "digest"}, set(), field)
    artifact = _non_blank(descriptor["artifact"], f"{field}.artifact")
    if not ARTIFACT_NAME.fullmatch(artifact):
        raise QualificationError(f"{field}.artifact must use the bounded JSON artifact grammar")
    relative = Path(artifact)
    if relative.is_absolute() or ".." in relative.parts:
        raise QualificationError(f"{field}.artifact must stay inside the evidence root")
    target = root / relative
    actual = _verify_artifact(root, descriptor, field)
    try:
        parsed = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"{field}.artifact must be UTF-8 JSON: {exc}") from exc
    _reject_sensitive(parsed, f"{field}.artifact")
    _validate_bounded_strings(parsed, f"{field}.artifact")
    return actual, parsed


def _owned_mode(path: Path, modes: set[int], field: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise QualificationError(f"cannot stat {field}: {exc}") from exc
    if info.st_uid != EXPECTED_OWNER_UID:
        raise QualificationError(f"{field} must be owned by the configured runner owner")
    if stat.S_IMODE(info.st_mode) not in modes:
        expected = ", ".join(f"{mode:04o}" for mode in sorted(modes))
        raise QualificationError(f"{field} must have mode {expected}")


def _safe_parent_chain(path: Path, field: str) -> None:
    """Reject symlinked or group/world-writable parents in trust paths."""
    current = path.parent
    while True:
        try:
            info = current.lstat()
        except OSError as exc:
            raise QualificationError(f"cannot stat parent of {field}: {exc}") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise QualificationError(f"{field} has a non-directory or symlinked parent")
        if info.st_uid not in {0, EXPECTED_OWNER_UID}:
            raise QualificationError(f"{field} has a parent with an unexpected owner")
        mode = stat.S_IMODE(info.st_mode)
        if mode & 0o022 and not (mode & stat.S_ISVTX):
            raise QualificationError(f"{field} has a group/world-writable parent")
        if current.parent == current:
            return
        current = current.parent


def _runner_evidence_digest(artifact_digests: dict[str, str]) -> str:
    return _canonical_digest({name: artifact_digests[name] for name in ("provider_model", "usage", "containment")})


def _verify_nonce_ledger(record: dict[str, Any], corpus: dict[str, Any], record_path: Path, signature_path: Path) -> None:
    ledger_root = Path(corpus["live_run"]["consumption_ledger_root"])
    sentinel_path = ledger_root / "packet.attempted"
    _owned_mode(sentinel_path, {0o400}, "packet attempt sentinel")
    _safe_parent_chain(sentinel_path, "packet attempt sentinel")
    sentinel = _load(sentinel_path)
    _keys(sentinel, {"schema_version", "runner_id", "packet_digest", "attempts", "reserved_at"}, set(), "packet_attempt")
    if sentinel["schema_version"] != "opencode-provider-qualification-attempt/v1" or sentinel["runner_id"] != RUNNER_ID or sentinel["packet_digest"] != _canonical_digest(corpus["live_run"]["packet"]) or sentinel["attempts"] != 1:
        raise QualificationError("packet attempt sentinel is not the exact one-attempt reservation")
    issued_path = ledger_root / f"{record['nonce']}.issued"
    completed_path = ledger_root / f"{record['nonce']}.completed"
    for path, label in ((issued_path, "issued nonce record"), (completed_path, "completed nonce record")):
        _owned_mode(path, {0o400}, label)
        _safe_parent_chain(path, label)
    issued = _load(issued_path)
    _keys(issued, {"schema_version", "runner_id", "run_id", "nonce", "packet_digest", "issued_at", "attempts", "consumed"}, set(), "issued_nonce")
    if issued["schema_version"] != "opencode-provider-qualification-nonce/v1" or issued["runner_id"] != RUNNER_ID or issued["run_id"] != record["run_id"] or issued["nonce"] != record["nonce"] or issued["attempts"] != 1 or issued["consumed"] is not False:
        raise QualificationError("issued nonce ledger record is not the exact fresh one-attempt packet")
    packet_digest = _canonical_digest(corpus["live_run"]["packet"])
    if issued["packet_digest"] != packet_digest or record["packet_digest"] != packet_digest:
        raise QualificationError("issued nonce is not bound to the checked-in packet")
    completed = _load(completed_path)
    _keys(completed, {"schema_version", "run_id", "nonce", "packet_digest", "record_digest", "signature_digest"}, set(), "completed_nonce")
    if completed["schema_version"] != "opencode-provider-qualification-nonce/v1-completed" or completed["run_id"] != record["run_id"] or completed["nonce"] != record["nonce"] or completed["packet_digest"] != packet_digest or completed["record_digest"] != _sha256_file(record_path) or completed["signature_digest"] != _sha256_file(signature_path):
        raise QualificationError("completed nonce ledger record does not bind the immutable record and signature")


def _verify_runner_record(
    record_path: Path,
    public_key_path: Path,
    allowed_signers_path: Path,
    receipt: dict[str, Any],
    corpus: dict[str, Any],
    artifact_digests: dict[str, str],
    *,
    evidence_bundle_digest: str,
) -> dict[str, Any]:
    """Verify the sealed, runner-authenticated, one-shot execution record."""
    expected_public = Path(corpus["live_run"]["runner_public_key_path"]).resolve()
    expected_allowed = Path(corpus["live_run"]["runner_allowed_signers_path"]).resolve()
    _owned_mode(record_path, {0o400}, "runner execution record")
    _safe_parent_chain(record_path, "runner execution record")
    if public_key_path.resolve() != expected_public or public_key_path.resolve() != Path(EXPECTED_RUNNER_PUBLIC_KEY_PATH).resolve():
        raise QualificationError("runner public-key path is not the exact configured trusted path")
    if allowed_signers_path.resolve() != expected_allowed or allowed_signers_path.resolve() != Path(EXPECTED_RUNNER_ALLOWED_SIGNERS_PATH).resolve():
        raise QualificationError("runner allowed-signers path is not the exact configured trusted path")
    _owned_mode(public_key_path, {0o444}, "trusted runner public key")
    _owned_mode(allowed_signers_path, {0o444}, "trusted runner allowed-signers file")
    _safe_parent_chain(public_key_path, "trusted runner public key")
    _safe_parent_chain(allowed_signers_path, "trusted runner allowed-signers file")
    if _sha256_file(public_key_path) != corpus["live_run"]["runner_public_key_fingerprint"] or _sha256_file(public_key_path) != EXPECTED_RUNNER_PUBLIC_KEY_FINGERPRINT:
        raise QualificationError("trusted runner public key is not the pinned public key")
    if _sha256_file(allowed_signers_path) != corpus["live_run"]["runner_allowed_signers_fingerprint"] or _sha256_file(allowed_signers_path) != EXPECTED_RUNNER_ALLOWED_SIGNERS_FINGERPRINT:
        raise QualificationError("trusted runner allowed-signers file is not pinned")
    record = _load(record_path)
    _reject_sensitive(record, "runner_record")
    _validate_bounded_strings(record, "runner_record")
    _keys(record, {
        "schema_version", "runner_id", "run_id", "nonce", "packet_digest", "issued_at", "started_at", "finished_at",
        "status", "attempts", "record_filename", "signature_filename", "token_budget", "cost_usd", "cost_limit_semantics", "hard_wall_seconds", "runner_digest", "opencode_digest", "provider_origin", "usage", "containment", "evidence_bundle_digest", "receipt_binding_digest", "request_digest", "sealed",
    }, set(), "runner_record")
    if record["schema_version"] != RUN_RECORD_SCHEMA or record["runner_id"] != RUNNER_ID or record["status"] != "completed" or record["sealed"] is not True:
        raise QualificationError("runner record is not a sealed completed record from the trusted runner")
    if not RUN_ID.fullmatch(record["run_id"]) or not RUN_NONCE.fullmatch(record["nonce"]):
        raise QualificationError("runner record run identity or nonce is malformed")
    record_root_raw = Path(corpus["live_run"]["record_root"])
    _owned_mode(record_root_raw, {0o700}, "trusted runner record root")
    _safe_parent_chain(record_root_raw, "trusted runner record root")
    record_root = record_root_raw.resolve()
    if record_root != Path(EXPECTED_RECORD_ROOT).resolve():
        raise QualificationError("corpus record root is not the exact configured trusted root")
    if record_path.resolve().parent != record_root or record["record_filename"] != record_path.name or record_path.name != f"{record['run_id']}.json":
        raise QualificationError("runner record is outside the pinned trusted record root")
    signature_path = record_path.with_name(record_path.name + ".sig")
    if record["signature_filename"] != signature_path.name:
        raise QualificationError("runner signature filename is not the exact detached signature")
    _owned_mode(signature_path, {0o400}, "runner detached signature")
    _safe_parent_chain(signature_path, "runner detached signature")
    if _digest(receipt["runner_signature_digest"], "receipt.runner_signature_digest") != _sha256_file(signature_path):
        raise QualificationError("receipt does not bind the detached runner signature")
    if not Path(SSH_KEYGEN).is_file() or not os.access(SSH_KEYGEN, os.X_OK):
        raise QualificationError("pinned ssh-keygen verifier is unavailable")
    try:
        verification = subprocess.run(
            [SSH_KEYGEN, "-Y", "verify", "-f", str(allowed_signers_path), "-I", RUNNER_ID, "-n", SIGNATURE_NAMESPACE, "-s", str(signature_path)],
            input=record_path.read_bytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise QualificationError(f"runner detached signature verification failed: {exc}") from exc
    if verification.returncode != 0:
        raise QualificationError("runner record signature is not trusted")
    _verify_nonce_ledger(record, corpus, record_path, signature_path)
    if record["run_id"] != receipt["run_id"] or record["nonce"] != receipt["run_nonce"]:
        raise QualificationError("receipt run identity does not match the runner record")
    packet = corpus["live_run"]["packet"]
    packet_digest = _canonical_digest(packet)
    if _digest(record["packet_digest"], "runner_record.packet_digest") != packet_digest or _digest(receipt["packet_digest"], "receipt.packet_digest") != packet_digest:
        raise QualificationError("receipt and runner record are not bound to the checked-in one-time packet")
    request_digest = _canonical_digest(packet["request"])
    if record["request_digest"] != request_digest or receipt["request_digest"] != request_digest:
        raise QualificationError("receipt and runner record are not bound to the exact packet request")
    if _digest(receipt["runner_record_digest"], "receipt.runner_record_digest") != _sha256_file(record_path):
        raise QualificationError("receipt does not bind the immutable runner record bytes")
    issued = _parse_time(record["issued_at"], "runner_record.issued_at")
    started = _parse_time(record["started_at"], "runner_record.started_at")
    finished = _parse_time(record["finished_at"], "runner_record.finished_at")
    now = datetime.now(timezone.utc)
    if not (issued <= started <= finished <= now + timedelta(seconds=5)):
        raise QualificationError("runner execution record timestamps are contradictory or from the future")
    if now - finished > timedelta(seconds=packet["freshness_window_seconds"]):
        raise QualificationError("runner execution record is stale")
    if record["attempts"] != 1:
        raise QualificationError("runner record permits more than one attempt")
    record_cost = _finite_number(record["cost_usd"], "runner_record.cost_usd")
    if record_cost < 0 or record_cost > MAX_COST_USD or record_cost != receipt["cost_usd"]:
        raise QualificationError("runner-authenticated cost is outside the bounded provider cap")
    if record["cost_limit_semantics"] != "post-hoc-acceptance" or record["hard_wall_seconds"] != 120 or receipt["cost_limit_semantics"] != "post-hoc-acceptance" or receipt["hard_wall_seconds"] != 120:
        raise QualificationError("runner budget semantics do not distinguish the 120-second wall from post-hoc spend acceptance")
    if record["runner_digest"] != corpus["live_run"]["runner_digest"] or record["opencode_digest"] != corpus["live_run"]["opencode_digest"]:
        raise QualificationError("runner record does not bind the pinned runner and OpenCode bytes")
    token_budget = record["token_budget"]
    if not isinstance(token_budget, dict):
        raise QualificationError("runner token budget is malformed")
    _keys(token_budget, {"soft_ceiling", "hard_ceiling", "observed_tokens", "soft_enforced", "hard_enforced", "soft_limit_hit", "hard_limit_hit", "attempts", "enforcement_events"}, set(), "runner_record.token_budget")
    if token_budget["soft_ceiling"] != SOFT_TOKEN_CEILING or token_budget["hard_ceiling"] != HARD_TOKEN_CEILING or token_budget["soft_enforced"] is not True or token_budget["hard_enforced"] is not True or token_budget["soft_limit_hit"] is not False or token_budget["hard_limit_hit"] is not False or token_budget["attempts"] != 1:
        raise QualificationError("runner did not enforce both token ceilings for one attempt")
    observed_tokens = token_budget["observed_tokens"]
    if not isinstance(observed_tokens, int) or isinstance(observed_tokens, bool) or observed_tokens < 0:
        raise QualificationError("runner observed token count is malformed")
    if observed_tokens > HARD_TOKEN_CEILING:
        raise QualificationError("runner execution exceeded the hard token ceiling")
    if observed_tokens > SOFT_TOKEN_CEILING:
        raise QualificationError("runner execution exceeded the soft token ceiling")
    if observed_tokens != receipt["tokens"]:
        raise QualificationError("receipt token count is not runner-authenticated")
    enforcement_events = token_budget["enforcement_events"]
    if not isinstance(enforcement_events, list) or len(enforcement_events) != 1 or not isinstance(enforcement_events[0], dict):
        raise QualificationError("runner token enforcement events are missing")
    _keys(enforcement_events[0], {"phase", "observed_tokens", "soft_ceiling", "hard_ceiling", "soft_enforced", "hard_enforced"}, set(), "runner_record.token_budget.enforcement_events[]")
    event = enforcement_events[0]
    if event["phase"] != "worker" or event["observed_tokens"] != observed_tokens or event["soft_ceiling"] != SOFT_TOKEN_CEILING or event["hard_ceiling"] != HARD_TOKEN_CEILING or event["soft_enforced"] is not True or event["hard_enforced"] is not True:
        raise QualificationError("runner token enforcement event is not exact")
    provider_origin = record["provider_origin"]
    if not isinstance(provider_origin, dict):
        raise QualificationError("runner provider-origin evidence is malformed")
    _keys(provider_origin, {"source", "providerID", "modelID", "artifact_digest", "session_count", "session_id_digest", "request_binding_digest", "event_count"}, set(), "runner_record.provider_origin")
    if provider_origin["source"] != "opencode-sanitized-export" or provider_origin["providerID"] != EXPECTED_PROVIDER or provider_origin["modelID"] != EXPECTED_MODEL_ID or provider_origin["session_count"] != 1 or provider_origin["artifact_digest"] != artifact_digests["provider_model"] or provider_origin["event_count"] != 1:
        raise QualificationError("runner record lacks verifiable provider-origin evidence")
    _digest(provider_origin["session_id_digest"], "runner_record.provider_origin.session_id_digest")
    _digest(provider_origin["request_binding_digest"], "runner_record.provider_origin.request_binding_digest")
    usage = record["usage"]
    if not isinstance(usage, dict):
        raise QualificationError("runner usage evidence is malformed")
    _keys(usage, {"source", "baseline", "observed", "artifact_digest", "provider_request_id_digest", "source_event_digest"}, set(), "runner_record.usage")
    if usage["source"] != "opencode-provider-step-finish" or usage["artifact_digest"] != artifact_digests["usage"]:
        raise QualificationError("runner usage evidence is not bound to provider output")
    _digest(usage["provider_request_id_digest"], "runner_record.usage.provider_request_id_digest")
    _digest(usage["source_event_digest"], "runner_record.usage.source_event_digest")
    if usage["provider_request_id_digest"] == usage["source_event_digest"]:
        raise QualificationError("provider request identifier must not be relabeled whole-event digest")
    record_baseline = _finite_number(usage["baseline"], "runner_record.usage.baseline", positive=True)
    record_observed = _finite_number(usage["observed"], "runner_record.usage.observed")
    if record_observed < 0 or record_observed > MAX_USAGE_MULTIPLIER * record_baseline or record_baseline != receipt["usage_baseline"] or record_observed != receipt["usage_observed"]:
        raise QualificationError("runner-authenticated usage inputs violate the two-times constraint")
    containment = record["containment"]
    if not isinstance(containment, dict):
        raise QualificationError("runner containment evidence is malformed")
    _keys(containment, {"probe_id", "status", "worker_identity", "coordinator_write_denied", "workspace_round_trip", "exact_groups", "reads_contained", "artifact_digest"}, set(), "runner_record.containment")
    if containment["probe_id"] != "contained-identity" or containment["status"] != "pass" or containment["worker_identity"] != EXPECTED_WORKER or containment["coordinator_write_denied"] is not True or containment["workspace_round_trip"] is not True or containment["exact_groups"] != ["agentworker", "agentdispatch"] or containment["reads_contained"] is not False or containment["artifact_digest"] != artifact_digests["containment"]:
        raise QualificationError("runner record lacks verifiable containment evidence")
    if _digest(record["evidence_bundle_digest"], "runner_record.evidence_bundle_digest") != evidence_bundle_digest or _digest(receipt["evidence_bundle_digest"], "receipt.evidence_bundle_digest") != evidence_bundle_digest:
        raise QualificationError("runner record and receipt do not bind the same evidence bundle")
    if _digest(record["receipt_binding_digest"], "runner_record.receipt_binding_digest") != _receipt_binding_digest(receipt):
        raise QualificationError("receipt fields are not authenticated by the trusted runner record")
    return record


def _consume_runner_record(record_path: Path, receipt: dict[str, Any], ledger_root: Path) -> None:
    """Atomically consume the runner nonce so a second candidate is a replay."""
    if str(ledger_root) != EXPECTED_LEDGER_ROOT:
        raise QualificationError("ledger root is not the exact configured trusted root")
    _owned_mode(ledger_root, {0o700}, "trusted one-time nonce ledger root")
    _safe_parent_chain(ledger_root, "trusted one-time nonce ledger root")
    marker = ledger_root / f"{receipt['run_nonce']}.consumed"
    payload = _canonical({"run_id": receipt["run_id"], "run_nonce": receipt["run_nonce"], "receipt_digest": _canonical_digest(receipt)})
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    except FileExistsError as exc:
        raise QualificationError("one-time runner nonce has already been consumed") from exc
    except OSError as exc:
        raise QualificationError(f"cannot consume one-time runner nonce: {exc}") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
    except OSError as exc:
        raise QualificationError(f"cannot seal one-time runner consumption record: {exc}") from exc
    _owned_mode(marker, {0o400}, "one-time runner consumption record")


def validate_provider_receipt(
    receipt: dict[str, Any],
    corpus: dict[str, Any],
    *,
    evidence_root: Path | None = None,
    runner_record_path: Path | None = None,
    runner_public_key_path: Path | None = None,
    runner_allowed_signers_path: Path | None = None,
    consume: bool = False,
) -> None:
    """Validate a receipt only when a trusted, fresh, one-time run is bound."""
    _reject_sensitive(receipt)
    _validate_bounded_strings(receipt)
    _keys(receipt, {
        "schema_version", "profile_id", "semantic_adapter", "cli_version", "executable_fingerprint", "channel_revision",
        "profile_digest", "config_digest", "overlay_digest", "policy_digest",
        "schema_version", "profile_id", "semantic_adapter", "provider_model", "provider_id", "model_id",
        "route_model", "worker_model", "model_override", "worker_identity", "provider_contacted",
        "workspace_opt_in", "workspace_evidence", "usage_baseline", "usage_observed", "usage_multiplier", "usage_evidence", "usage_evidence_digest",
        "cost_usd", "tokens", "attempts", "containment", "provider_model_evidence", "capability_probe_results",
        "lifecycle_probe_results", "capability_evidence_digest", "lifecycle_evidence_digest", "evidence_artifacts", "raw_transcript_captured", "qualification_state", "independent_review",
        "runner_id", "run_id", "run_nonce", "packet_digest", "request_digest", "runner_digest", "opencode_digest", "runner_record_digest", "runner_signature_digest", "evidence_bundle_digest", "cost_limit_semantics", "hard_wall_seconds",
    }, set(), "receipt")
    if receipt["schema_version"] != "opencode-provider-qualification-receipt/v2":
        raise QualificationError("receipt schema_version is unsupported")
    if receipt["profile_id"] != corpus["route"]["profile_id"]:
        raise QualificationError("receipt profile_id does not match the corpus")
    if receipt["semantic_adapter"] != "opencode-noninteractive/v1":
        raise QualificationError("receipt semantic adapter does not match the profile")
    if receipt["cli_version"] != EXPECTED_CLI_VERSION:
        raise QualificationError("receipt CLI version does not match the profile")
    _digest(receipt["executable_fingerprint"], "receipt.executable_fingerprint")
    if receipt["opencode_digest"] != corpus["live_run"]["opencode_digest"] or receipt["executable_fingerprint"] != receipt["opencode_digest"] or receipt["runner_digest"] != corpus["live_run"]["runner_digest"]:
        raise QualificationError("receipt does not bind the pinned runner and OpenCode executable bytes")
    if not isinstance(receipt["channel_revision"], str) or not CHANNEL_REVISION.fullmatch(receipt["channel_revision"]):
        raise QualificationError("receipt.channel_revision must use the bounded channel grammar")
    expected_digests = {
        "profile_digest": _sha256_file(DEFAULT_PROFILE),
        "config_digest": _sha256_file(DEFAULT_CONFIG),
        "policy_digest": _sha256_file(POLICY_PATH),
    }
    for field, expected in expected_digests.items():
        if _digest(receipt[field], f"receipt.{field}") != expected:
            raise QualificationError(f"receipt {field} does not bind the checked-in artifact")
    if receipt["provider_model"] != EXPECTED_MODEL or receipt["route_model"] != EXPECTED_MODEL or receipt["worker_model"] != EXPECTED_MODEL:
        raise QualificationError("receipt provider, route, and worker model must all be exact")
    if receipt["provider_id"] != EXPECTED_PROVIDER or receipt["model_id"] != EXPECTED_MODEL_ID:
        raise QualificationError("receipt providerID/modelID evidence is not exact")
    if receipt["model_override"] is not False or receipt["provider_contacted"] is not True:
        raise QualificationError("receipt must prove the real route ran without an override")
    if receipt["worker_identity"] != EXPECTED_WORKER or receipt["workspace_opt_in"] is not True:
        raise QualificationError("receipt must prove the contained identity and explicit provider workspace opt-in")
    workspace_evidence = receipt["workspace_evidence"]
    if not isinstance(workspace_evidence, dict):
        raise QualificationError("receipt workspace evidence is malformed")
    _keys(workspace_evidence, {"manifest_digest", "repository_opt_in", "provider_workspace_opt_in"}, set(), "receipt.workspace_evidence")
    if workspace_evidence["repository_opt_in"] is not True or workspace_evidence["provider_workspace_opt_in"] is not True or _digest(workspace_evidence["manifest_digest"], "receipt.workspace_evidence.manifest_digest") != _sha256_file(DEFAULT_MANIFEST):
        raise QualificationError("receipt workspace opt-in is not bound to the checked-in manifest")
    baseline = receipt["usage_baseline"]
    observed = receipt["usage_observed"]
    multiplier = receipt["usage_multiplier"]
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) for value in (baseline, observed, multiplier)):
        raise QualificationError("receipt usage accounting must be finite numeric evidence")
    if baseline <= 0 or observed < 0 or observed > MAX_USAGE_MULTIPLIER * baseline:
        raise QualificationError("receipt usage exceeds the two-times baseline constraint")
    if abs(multiplier - (observed / baseline)) > 1e-9 or not 0 < multiplier <= MAX_USAGE_MULTIPLIER:
        raise QualificationError("receipt usage multiplier is inconsistent or greater than 2")
    if not isinstance(receipt["cost_usd"], (int, float)) or isinstance(receipt["cost_usd"], bool) or not math.isfinite(receipt["cost_usd"]) or receipt["cost_usd"] < 0 or receipt["cost_usd"] > MAX_COST_USD:
        raise QualificationError("receipt cost exceeds the bounded provider cap")
    if not isinstance(receipt["tokens"], int) or isinstance(receipt["tokens"], bool) or receipt["tokens"] < 0:
        raise QualificationError("receipt token usage is malformed")
    if receipt["tokens"] > HARD_TOKEN_CEILING:
        raise QualificationError("receipt token usage exceeds the hard ceiling")
    if receipt["tokens"] > SOFT_TOKEN_CEILING:
        raise QualificationError("receipt token usage exceeds the soft ceiling")
    if receipt["attempts"] != 1 or receipt["raw_transcript_captured"] is not False:
        raise QualificationError("receipt must describe one attempt and no raw transcript capture")
    containment = receipt["containment"]
    if not isinstance(containment, dict) or containment.get("coordinator_write_denied") is not True or containment.get("workspace_round_trip") is not True or containment.get("worker_identity") != EXPECTED_WORKER or containment.get("exact_groups") != ["agentworker", "agentdispatch"] or containment.get("reads_contained") is not False:
        raise QualificationError("receipt lacks executable containment evidence")
    _keys(containment, {"coordinator_write_denied", "workspace_round_trip", "worker_identity", "exact_groups", "reads_contained", "evidence_digest"}, set(), "receipt.containment")
    _digest(containment["evidence_digest"], "receipt.containment.evidence_digest")
    evidence = receipt["provider_model_evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise QualificationError("receipt has no provider/model evidence")
    for item in evidence:
        if not isinstance(item, dict):
            raise QualificationError("every provider/model observation must match exactly")
        _keys(item, {"phase", "providerID", "modelID", "finish", "part_types", "evidence_digest"}, set(), "receipt.provider_model_evidence[]")
        if item.get("phase") != "worker" or item.get("providerID") != EXPECTED_PROVIDER or item.get("modelID") != EXPECTED_MODEL_ID or item.get("finish") != "stop" or item.get("part_types") != ["text", "step-finish"]:
            raise QualificationError("every provider/model observation must match exactly")
        _digest(item["evidence_digest"], "receipt.provider_model_evidence[].evidence_digest")
    for field in ("capability_probe_results", "lifecycle_probe_results"):
        results = receipt[field]
        if not isinstance(results, dict) or set(results) != set(EXPECTED_REQUIRED_PROBES) or any(value != "pass" for value in results.values()):
            raise QualificationError(f"{field} must report every declared probe as pass")
    usage_evidence = receipt["usage_evidence"]
    if not isinstance(usage_evidence, dict):
        raise QualificationError("receipt usage evidence is malformed")
    _keys(usage_evidence, {"source", "provider_request_id_digest", "source_event_digest", "phase_units"}, set(), "receipt.usage_evidence")
    if usage_evidence["source"] != "provider-reported":
        raise QualificationError("usage evidence must come from the provider")
    _digest(usage_evidence["provider_request_id_digest"], "receipt.usage_evidence.provider_request_id_digest")
    _digest(usage_evidence["source_event_digest"], "receipt.usage_evidence.source_event_digest")
    if usage_evidence["provider_request_id_digest"] == usage_evidence["source_event_digest"]:
        raise QualificationError("provider request identifier must not be relabeled whole-event digest")
    phase_units = usage_evidence["phase_units"]
    if not isinstance(phase_units, list) or not phase_units or any(not isinstance(item, dict) or set(item) != {"phase", "units"} for item in phase_units):
        raise QualificationError("provider usage evidence must contain finite phase units")
    if any(not isinstance(item["phase"], str) or PHASE.fullmatch(item["phase"]) is None for item in phase_units):
        raise QualificationError("provider usage evidence phase must use the bounded phase grammar")
    if any(not isinstance(item["units"], (int, float)) or isinstance(item["units"], bool) or not math.isfinite(item["units"]) or item["units"] < 0 for item in phase_units):
        raise QualificationError("provider usage evidence must contain finite phase units")
    if abs(sum(item["units"] for item in phase_units) - observed) > 1e-9:
        raise QualificationError("provider phase usage does not equal observed usage")
    _digest(receipt["usage_evidence_digest"], "receipt.usage_evidence_digest")
    _digest(receipt["capability_evidence_digest"], "receipt.capability_evidence_digest")
    _digest(receipt["lifecycle_evidence_digest"], "receipt.lifecycle_evidence_digest")
    _digest(receipt["overlay_digest"], "receipt.overlay_digest")
    independent_review = receipt["independent_review"]
    if independent_review != {"status": "pending", "ref": None}:
        raise QualificationError("this gate accepts only a receipt pending independent review")
    if receipt["qualification_state"] != "preflight_observed":
        raise QualificationError("a receipt cannot promote the checked-in qualification state")
    if evidence_root is None:
        raise QualificationError("a receipt requires an evidence root for byte-level provenance checks")
    configured_evidence = Path(corpus["live_run"]["evidence_root"]).resolve()
    evidence_resolved = evidence_root.resolve()
    if evidence_resolved != configured_evidence and evidence_resolved.parent != configured_evidence:
        raise QualificationError("evidence root is not the exact configured root or a direct run child")
    _owned_mode(evidence_root, {0o700}, "trusted evidence root")
    _safe_parent_chain(evidence_root, "trusted evidence root")
    artifacts = receipt["evidence_artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != {"provider_model", "usage", "containment", "capability", "lifecycle", "overlay", "workspace"}:
        raise QualificationError("receipt must name all seven bounded evidence artifacts")
    artifact_results = {
        name: _read_artifact_json(evidence_root, descriptor, f"receipt.evidence_artifacts.{name}")
        for name, descriptor in artifacts.items()
    }
    artifact_digests = {name: result[0] for name, result in artifact_results.items()}
    artifact_payloads = {name: result[1] for name, result in artifact_results.items()}
    provider_artifact = artifact_payloads["provider_model"]
    if not isinstance(provider_artifact, dict):
        raise QualificationError("provider/model artifact is not a bounded origin record")
    _keys(provider_artifact, {"schema_version", "session_id_digest", "request_binding_digest", "events"}, set(), "provider_model_artifact")
    if provider_artifact["schema_version"] != "opencode-provider-origin/v1":
        raise QualificationError("provider/model artifact schema is not runner-compatible")
    _digest(provider_artifact["session_id_digest"], "provider_model_artifact.session_id_digest")
    _digest(provider_artifact["request_binding_digest"], "provider_model_artifact.request_binding_digest")
    provider_events = provider_artifact["events"]
    if not isinstance(provider_events, list) or len(provider_events) != 1:
        raise QualificationError("provider/model artifact must contain exactly one runner-observed event")
    for event in provider_events:
        if not isinstance(event, dict):
            raise QualificationError("provider/model origin event is malformed")
        _keys(event, {"phase", "providerID", "modelID", "finish", "part_types"}, set(), "provider_model_artifact.events[]")
        if event["phase"] != "worker" or event["providerID"] != EXPECTED_PROVIDER or event["modelID"] != EXPECTED_MODEL_ID or event["finish"] != "stop" or event["part_types"] != ["text", "step-finish"]:
            raise QualificationError("provider/model origin event is not the exact OpenCode observation")
    expected_provider_evidence = [
        {"phase": item["phase"], "providerID": item["providerID"], "modelID": item["modelID"], "finish": item["finish"], "part_types": item["part_types"]}
        for item in receipt["provider_model_evidence"]
    ]
    if provider_events != expected_provider_evidence:
        raise QualificationError("provider/model artifact does not match the authenticated runner observation")
    if any(item["evidence_digest"] != artifact_digests["provider_model"] for item in receipt["provider_model_evidence"]):
        raise QualificationError("provider/model evidence digest bindings are inconsistent")
    expected_usage_evidence = {
        "schema_version": "opencode-provider-usage/v1",
        "provider_request_id_digest": usage_evidence["provider_request_id_digest"],
        "source_event_digest": usage_evidence["source_event_digest"],
        "source": usage_evidence["source"],
        "usage_baseline": baseline,
        "usage_observed": observed,
        "phase_units": phase_units,
    }
    if artifact_payloads["usage"] != expected_usage_evidence or artifact_digests["usage"] != receipt["usage_evidence_digest"]:
        raise QualificationError("provider usage artifact does not bind the denominator and observed units")
    expected_containment = {key: containment[key] for key in ("coordinator_write_denied", "workspace_round_trip", "worker_identity", "exact_groups", "reads_contained")}
    if artifact_payloads["containment"] != expected_containment or artifact_digests["containment"] != containment["evidence_digest"]:
        raise QualificationError("containment artifact does not match the receipt")
    if artifact_payloads["capability"] != receipt["capability_probe_results"] or artifact_digests["capability"] != receipt["capability_evidence_digest"]:
        raise QualificationError("capability artifact does not match the receipt")
    if artifact_payloads["lifecycle"] != receipt["lifecycle_probe_results"] or artifact_digests["lifecycle"] != receipt["lifecycle_evidence_digest"]:
        raise QualificationError("lifecycle artifact does not match the receipt")
    expected_workspace = {
        "manifest_digest": workspace_evidence["manifest_digest"],
        "repository_opt_in": workspace_evidence["repository_opt_in"],
        "provider_workspace_opt_in": workspace_evidence["provider_workspace_opt_in"],
    }
    if artifact_payloads["workspace"] != expected_workspace:
        raise QualificationError("workspace opt-in artifact does not match the receipt")
    overlay = artifact_payloads["overlay"]
    if not isinstance(overlay, dict):
        raise QualificationError("session overlay artifact is malformed")
    _keys(overlay, {"route", "agent", "allowed_command_ids", "model_override", "overlay"}, set(), "receipt.evidence_artifacts.overlay")
    if overlay["route"] != "mechanical_bulk" or overlay["agent"] != "ao-mechanical-bulk" or overlay["model_override"] is not None:
        raise QualificationError("session overlay artifact has an unexpected route or override")
    allowed_commands = overlay["allowed_command_ids"]
    manifest = _load(DEFAULT_MANIFEST)
    command_map = manifest.get("hybrid", {}).get("commands", {})
    if not isinstance(allowed_commands, list) or not allowed_commands or any(command not in command_map for command in allowed_commands):
        raise QualificationError("session overlay artifact has unknown or empty command bindings")
    hybrid_dispatch = _load_module(HYBRID_DISPATCH_SCRIPT, "opencode_hybrid_dispatch")
    policy = _load(POLICY_PATH)
    canonical_overlay = hybrid_dispatch.build_overlay(
        {"route": "mechanical_bulk", "allowed_command_ids": allowed_commands},
        manifest,
        policy,
        _load(DEFAULT_CONFIG),
    )
    if overlay["overlay"] != canonical_overlay or artifact_digests["overlay"] != receipt["overlay_digest"]:
        raise QualificationError("session overlay artifact does not bind the canonical permission policy")
    if runner_record_path is None or runner_public_key_path is None or runner_allowed_signers_path is None:
        raise QualificationError("candidate admission requires a trusted runner record and pinned public verification material")
    if receipt["runner_id"] != RUNNER_ID or not RUN_ID.fullmatch(receipt["run_id"]) or not RUN_NONCE.fullmatch(receipt["run_nonce"]):
        raise QualificationError("receipt runner identity or one-time nonce is malformed")
    evidence_bundle_digest = _bundle_digest(artifacts)
    runner_record = _verify_runner_record(
        runner_record_path,
        runner_public_key_path,
        runner_allowed_signers_path,
        receipt,
        corpus,
        artifact_digests,
        evidence_bundle_digest=evidence_bundle_digest,
    )
    origin = runner_record["provider_origin"]
    if provider_artifact["session_id_digest"] != origin["session_id_digest"] or provider_artifact["request_binding_digest"] != origin["request_binding_digest"]:
        raise QualificationError("provider-origin artifact is not bound to the trusted runner attestation")
    usage_artifact = artifact_payloads["usage"]
    if not isinstance(usage_artifact, dict) or usage_artifact.get("provider_request_id_digest") != runner_record["usage"]["provider_request_id_digest"] or usage_artifact.get("source_event_digest") != runner_record["usage"]["source_event_digest"]:
        raise QualificationError("usage artifact is not bound to the trusted provider event attestation")
    if consume:
        _consume_runner_record(runner_record_path, receipt, Path(corpus["live_run"]["consumption_ledger_root"]).resolve())


def evaluate(
    corpus_path: Path = DEFAULT_CORPUS,
    *,
    receipt_path: Path | None = None,
    evidence_root: Path | None = None,
    runner_record_path: Path | None = None,
    runner_public_key_path: Path | None = None,
    runner_allowed_signers_path: Path | None = None,
    consume: bool = False,
) -> dict[str, Any]:
    corpus = _load(corpus_path)
    profile = _load(DEFAULT_PROFILE)
    config = _load(DEFAULT_CONFIG)
    manifest = _load(DEFAULT_MANIFEST)
    profile_validator = _load_module(PROFILE_VALIDATOR_SCRIPT, "opencode_profile_validator")
    profile_validator.validate_profile(profile, DEFAULT_PROFILE)
    hybrid_validator = _load_module(HYBRID_VALIDATOR_SCRIPT, "hybrid_dispatch_validator")
    hybrid_validator.validate_policy(_load(POLICY_PATH), config)
    _validate_inputs(corpus, profile, config, manifest, corpus_path=corpus_path)
    result: dict[str, Any] = {
        "status": "passed",
        "qualification_state": "preflight_observed",
        "qualification_eligible": False,
        "provider_contacted": False,
        "gates": {
            "repository-opt-in": "pass",
            "exact-route-model": "pass",
            "contained-identity": "pass",
            "bounded-usage": "pass",
            "provider-qualification": "blocked",
        },
        "outstanding_evidence": ["provider-qualification"],
    }
    if receipt_path is not None:
        if not consume:
            raise QualificationError("receipt validation is not candidate admission without one-time nonce consumption")
        receipt = _load(receipt_path)
        validate_provider_receipt(receipt, corpus, evidence_root=evidence_root, runner_record_path=runner_record_path, runner_public_key_path=runner_public_key_path, runner_allowed_signers_path=runner_allowed_signers_path, consume=True)
        result["provider_contacted"] = True
        result["candidate_ready"] = True
        result["qualification_eligible"] = False
        result["gates"]["provider-qualification"] = "candidate"
        result["outstanding_evidence"] = ["independent-review", "human-qualification"]
        result["note"] = "trusted one-time runner record and receipt passed the bounded gate; independent review and human qualification decision remain required"
    else:
        result["note"] = "offline corpus only; no provider was contacted and qualification remains blocked"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--evidence-root", type=Path, help="Evidence directory containing the receipt's hashed structural artifacts")
    parser.add_argument("--runner-record", type=Path, help="Sealed 0400 execution record issued by the trusted runner")
    parser.add_argument("--runner-public-key-file", type=Path, help="Pinned public verification key; the private signing key is never accepted")
    parser.add_argument("--runner-allowed-signers-file", type=Path, help="Pinned OpenSSH allowed-signers file")
    parser.add_argument("--consume", action="store_true", help="Atomically consume the one-time runner nonce")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(evaluate(args.corpus, receipt_path=args.receipt, evidence_root=args.evidence_root, runner_record_path=args.runner_record, runner_public_key_path=args.runner_public_key_file, runner_allowed_signers_path=args.runner_allowed_signers_file, consume=args.consume), indent=2, sort_keys=True))
    except (OSError, QualificationError, ValueError) as exc:
        print(json.dumps({"status": "failed", "qualification_state": "preflight_observed", "qualification_eligible": False, "error": str(exc)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
