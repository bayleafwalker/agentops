#!/usr/bin/env python3
"""Artifact-based investigation workflow for use inside native agent runtimes.

This CLI owns no work state and never starts an agent runtime. It records
pre-registered predictions, selects bounded read-only probes, stores immutable
evidence, replays the decision chain and emits references for existing Vuoro
evidence APIs.
"""
from __future__ import annotations

import argparse
import datetime as dt
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any


EVENTS = "events.jsonl"
OBJECTS = "objects"
MAX_LOG_BYTES = 32 * 1024 * 1024
MAX_EVENT_BYTES = 2 * 1024 * 1024
MAX_PROBE_BYTES = 2 * 1024 * 1024
_UNCONDITIONAL = object()
SCHEMA = "agentops.investigation.v1"
EVAL_SCHEMA = "agentops.investigation-evaluation.v1"
COLLECTOR = "agentops.autonomous-investigation.v1"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RISK_PENALTY = {"low": 0.0, "medium": 0.15, "high": 0.45}
RISK_LEVELS = frozenset(RISK_PENALTY)
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}
BUILTIN_OUTCOMES = {
    "file_exists": ("present", "absent"),
    "sha256_matches": ("match", "different", "missing"),
    "text_contains": ("present", "absent", "missing"),
    "json_equals": ("match", "different", "missing", "invalid"),
}


class InvestigationError(ValueError):
    """Invalid or unsafe investigation input."""


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise InvestigationError(f"value is not canonical JSON: {exc}") from exc


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise InvestigationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _loads(data: bytes | str, label: str) -> Any:
    def reject_constant(value: str) -> None:
        raise InvestigationError(f"invalid number {value} in {label}")
    try:
        return json.loads(data, object_pairs_hook=_object_pairs, parse_constant=reject_constant)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise InvestigationError(f"invalid JSON in {label}: {exc}") from exc


def _write_new(path: Path, data: bytes, mode: int = 0o600) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, mode)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def _check_root(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise InvestigationError(f"investigation directory must be a real directory: {path}")
    resolved = path.resolve(strict=True)
    if resolved != path.absolute():
        raise InvestigationError("investigation directory path may not traverse symlinks")
    return resolved


def _read_log(root: Path) -> list[dict[str, Any]]:
    root = _check_root(root)
    path = root / EVENTS
    if path.is_symlink():
        raise InvestigationError("event log may not be a symlink")
    try:
        info = path.stat()
    except FileNotFoundError as exc:
        raise InvestigationError("investigation event log is missing") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_LOG_BYTES:
        raise InvestigationError("event log is not a bounded regular file")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    try:
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_LOG_BYTES + 1)
    finally:
        os.close(fd)
    if len(raw) > MAX_LOG_BYTES:
        raise InvestigationError("event log exceeds the size limit")
    if raw and not raw.endswith(b"\n"):
        raise InvestigationError("event log has a partial trailing line; preserve it for recovery")
    rows: list[dict[str, Any]] = []
    previous: str | None = None
    for index, line in enumerate(raw.splitlines()):
        if len(line) > MAX_EVENT_BYTES:
            raise InvestigationError(f"event {index + 1} exceeds the size limit")
        row = _loads(line, f"event {index + 1}")
        if not isinstance(row, dict) or set(row) != {
            "seq", "kind", "data", "previous_digest", "digest"
        }:
            raise InvestigationError(f"event {index + 1} has an invalid envelope")
        if row["seq"] != index + 1 or row["previous_digest"] != previous:
            raise InvestigationError(f"event {index + 1} breaks the sequence or hash chain")
        if not isinstance(row["kind"], str) or not isinstance(row["data"], dict):
            raise InvestigationError(f"event {index + 1} has invalid content")
        signed = {key: row[key] for key in ("seq", "kind", "data", "previous_digest")}
        actual = _sha(_canonical(signed))
        if row["digest"] != actual:
            raise InvestigationError(f"event {index + 1} digest mismatch")
        previous = actual
        rows.append(row)
    return rows


def _append(root: Path, kind: str, data: dict[str, Any], *,
            expected_head: Any = _UNCONDITIONAL) -> dict[str, Any]:
    root = _check_root(root)
    log = root / EVENTS
    if log.is_symlink():
        raise InvestigationError("event log may not be a symlink")
    lock_path = root / ".lock"
    if lock_path.is_symlink():
        raise InvestigationError("investigation lock may not be a symlink")
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        rows = _read_log(root)
        previous = rows[-1]["digest"] if rows else None
        if expected_head is not _UNCONDITIONAL and expected_head != previous:
            raise InvestigationError("investigation changed concurrently; reload before retrying")
        if not rows and kind != "initialized":
            raise InvestigationError("first event must initialize the investigation")
        if rows and kind == "initialized":
            raise InvestigationError("investigation is already initialized")
        signed = {"seq": len(rows) + 1, "kind": kind, "data": data,
                  "previous_digest": previous}
        row = {**signed, "digest": _sha(_canonical(signed))}
        encoded = _canonical(row) + b"\n"
        if len(encoded) > MAX_EVENT_BYTES:
            raise InvestigationError("event exceeds the size limit")
        fd = os.open(log, os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0))
        try:
            view = memoryview(encoded)
            while view:
                view = view[os.write(fd, view):]
            os.fsync(fd)
        finally:
            os.close(fd)
        return row
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


def _store_object(root: Path, data: bytes) -> str:
    root = _check_root(root)
    if len(data) > MAX_PROBE_BYTES:
        raise InvestigationError("evidence object exceeds the size limit")
    digest = _sha(data)
    directory = root / OBJECTS
    if directory.is_symlink():
        raise InvestigationError("object store may not be a symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    target = directory / digest.removeprefix("sha256:")
    if target.exists():
        _verify_object(root, digest)
        return digest
    try:
        _write_new(target, data)
    except FileExistsError:
        _verify_object(root, digest)
    return digest


def _verify_object(root: Path, digest: str) -> bytes:
    if not isinstance(digest, str) or not DIGEST_RE.fullmatch(digest):
        raise InvestigationError(f"invalid evidence digest: {digest!r}")
    directory = _check_root(root) / OBJECTS
    if directory.is_symlink() or not directory.is_dir():
        raise InvestigationError("object store must be a real directory")
    path = directory / digest.removeprefix("sha256:")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError as exc:
        raise InvestigationError(f"evidence object is missing: {digest}") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PROBE_BYTES:
            raise InvestigationError(f"evidence object is not a bounded regular file: {digest}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_PROBE_BYTES + 1)
    finally:
        os.close(fd)
    if len(data) > MAX_PROBE_BYTES:
        raise InvestigationError(f"evidence object exceeds the size limit: {digest}")
    if _sha(data) != digest:
        raise InvestigationError(f"evidence object digest mismatch: {digest}")
    return data


def _validate_hypotheses(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) < 2:
        raise InvestigationError("at least two competing hypotheses are required")
    ids: set[str] = set()
    total = 0.0
    clean: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or set(item) - {"id", "statement", "prior"}:
            raise InvestigationError("hypotheses require only id, statement and prior")
        ident, statement, prior = item.get("id"), item.get("statement"), item.get("prior")
        if not isinstance(ident, str) or not ID_RE.fullmatch(ident) or ident in ids:
            raise InvestigationError(f"invalid or duplicate hypothesis id: {ident!r}")
        if not isinstance(statement, str) or not statement.strip() or len(statement) > 2048:
            raise InvestigationError(f"hypothesis {ident} needs a statement")
        if isinstance(prior, bool) or not isinstance(prior, (int, float)) or not 0 < prior <= 1:
            raise InvestigationError(f"hypothesis {ident} prior must be in (0, 1]")
        ids.add(ident)
        total += float(prior)
        clean.append({"id": ident, "statement": statement.strip(), "prior": float(prior)})
    if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise InvestigationError(f"hypothesis priors must sum to 1 (got {total:.12g})")
    return clean


def _validate_relative_file(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise InvestigationError("probe path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if (path.is_absolute() or any(part in ("", ".", "..") for part in path.parts)
            or "/".join(path.parts) != value):
        raise InvestigationError("probe path must stay within the selected read-only root")
    return value


def _implementation_outcomes(implementation: dict[str, Any]) -> tuple[str, ...]:
    kind = implementation.get("kind")
    common = {"kind", "effects"}
    allowed = {
        "file_exists": common | {"path"},
        "sha256_matches": common | {"path", "expected_digest"},
        "text_contains": common | {"path", "literal"},
        "json_equals": common | {"path", "pointer", "expected"},
        "external_observation": common | {"outcomes"},
    }
    if kind not in allowed or set(implementation) - allowed[kind]:
        raise InvestigationError(f"unsupported or unsafe probe implementation: {kind!r}")
    if implementation.get("effects", "read_only") != "read_only":
        raise InvestigationError("only probes declared read_only may be registered")
    if kind == "external_observation":
        outcomes = implementation.get("outcomes")
        if not isinstance(outcomes, list) or len(outcomes) < 2:
            raise InvestigationError("external probes need at least two named outcomes")
        if any(not isinstance(x, str) or not ID_RE.fullmatch(x) for x in outcomes):
            raise InvestigationError("external probe outcomes must be simple identifiers")
        if len(set(outcomes)) != len(outcomes):
            raise InvestigationError("external probe outcomes must be unique")
        return tuple(outcomes)
    _validate_relative_file(implementation.get("path"))
    if kind == "sha256_matches" and not DIGEST_RE.fullmatch(
        str(implementation.get("expected_digest", ""))
    ):
        raise InvestigationError("sha256_matches requires expected_digest as sha256:<hex>")
    if kind == "text_contains":
        literal = implementation.get("literal")
        if not isinstance(literal, str) or not literal or len(literal.encode("utf-8")) > 4096:
            raise InvestigationError("text_contains requires a bounded non-empty literal")
    if kind == "json_equals":
        pointer = implementation.get("pointer")
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise InvestigationError("json_equals pointer must be a JSON Pointer")
        if "expected" not in implementation:
            raise InvestigationError("json_equals requires expected")
    return BUILTIN_OUTCOMES[kind]


def _validate_probe(probe: Any, hypothesis_ids: set[str]) -> dict[str, Any]:
    required = {"id", "statement", "risk", "cost", "implementation", "likelihoods"}
    if not isinstance(probe, dict) or set(probe) != required:
        raise InvestigationError(f"probe must have exactly {sorted(required)}")
    ident = probe["id"]
    if not isinstance(ident, str) or not ID_RE.fullmatch(ident):
        raise InvestigationError(f"invalid probe id: {ident!r}")
    if not isinstance(probe["statement"], str) or not probe["statement"].strip():
        raise InvestigationError(f"probe {ident} needs a testable statement")
    if probe["risk"] not in RISK_LEVELS:
        raise InvestigationError(f"probe {ident} has an invalid risk")
    cost = probe["cost"]
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not 0 <= cost <= 1:
        raise InvestigationError(f"probe {ident} cost must be from 0 to 1")
    implementation = probe["implementation"]
    if not isinstance(implementation, dict):
        raise InvestigationError("probe implementation must be an object")
    outcomes = _implementation_outcomes(implementation)
    likelihoods = probe["likelihoods"]
    if not isinstance(likelihoods, dict) or set(likelihoods) != hypothesis_ids:
        raise InvestigationError(f"probe {ident} must predict outcomes for every hypothesis")
    clean_likelihoods: dict[str, dict[str, float]] = {}
    for hypothesis_id, distribution in likelihoods.items():
        if not isinstance(distribution, dict) or set(distribution) != set(outcomes):
            raise InvestigationError(
                f"probe {ident}/{hypothesis_id} must predict each outcome exactly once"
            )
        values: dict[str, float] = {}
        for outcome in outcomes:
            probability = distribution[outcome]
            if isinstance(probability, bool) or not isinstance(probability, (int, float)):
                raise InvestigationError("prediction probabilities must be numbers")
            if not 0 <= probability <= 1:
                raise InvestigationError("prediction probabilities must be between 0 and 1")
            values[outcome] = float(probability)
        if not math.isclose(sum(values.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise InvestigationError(f"predictions for {hypothesis_id} must sum to 1")
        clean_likelihoods[hypothesis_id] = values
    return {
        "id": ident,
        "statement": probe["statement"].strip(),
        "risk": probe["risk"],
        "cost": float(cost),
        "implementation": dict(implementation),
        "likelihoods": clean_likelihoods,
        "outcomes": list(outcomes),
    }


def initialize(root: Path, *, title: str, hypotheses: Any,
               repository: str | None = None, source_commit: str | None = None,
               work_item: int | None = None, vuoro_run_id: str | None = None,
               artifact_ref: str | None = None, decision_threshold: float = 0.9,
               max_risk: str = "low") -> dict[str, Any]:
    if not isinstance(title, str) or not title.strip() or len(title) > 512:
        raise InvestigationError("investigation title is required")
    clean_hypotheses = _validate_hypotheses(hypotheses)
    if isinstance(decision_threshold, bool) or not isinstance(decision_threshold, (float, int)) \
            or not 0.5 < decision_threshold <= 1:
        raise InvestigationError("decision threshold must be in (0.5, 1]")
    if max_risk not in RISK_LEVELS:
        raise InvestigationError("max risk must be low, medium or high")
    if repository is not None and (
        not isinstance(repository, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
    ):
        raise InvestigationError("repository reference must use owner/repository form")
    if source_commit is not None and not re.fullmatch(r"[0-9a-f]{7,64}", source_commit):
        raise InvestigationError("source commit must be a hexadecimal Git revision")
    if work_item is not None and (
        isinstance(work_item, bool) or not isinstance(work_item, int) or work_item < 1
    ):
        raise InvestigationError("work item must be a positive integer")
    if vuoro_run_id is not None and (
        not isinstance(vuoro_run_id, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", vuoro_run_id)
    ):
        raise InvestigationError("Vuoro run reference must be a bounded identifier")
    if artifact_ref is not None:
        artifact_ref = _validate_relative_file(artifact_ref)
    root = Path(root)
    if root.exists() or root.is_symlink():
        raise InvestigationError(f"refusing to overwrite existing investigation path: {root}")
    root.mkdir(mode=0o700, parents=True)
    (root / OBJECTS).mkdir(mode=0o700)
    root = _check_root(root)
    _write_new(root / EVENTS, b"")
    data = {
        "schema": SCHEMA,
        "investigation_id": root.name,
        "title": title.strip(),
        "created_at": _now(),
        "hypotheses": clean_hypotheses,
        "repository": repository,
        "source_commit": source_commit,
        "work_item": work_item,
        "vuoro_run_id": vuoro_run_id,
        "artifact_ref": artifact_ref,
        "decision_threshold": float(decision_threshold),
        "max_risk": max_risk,
        "planner": "expected_information_gain.v1",
        "probe_safety": "read_only_only",
    }
    _append(root, "initialized", data)
    return data


def _entropy(distribution: dict[str, float]) -> float:
    return -sum(p * math.log2(p) for p in distribution.values() if p > 0)


def rank_probes(probes: dict[str, dict[str, Any]], posterior: dict[str, float],
                completed: set[str], max_risk: str = "low") -> list[dict[str, Any]]:
    if max_risk not in RISK_LEVELS:
        raise InvestigationError("max risk must be low, medium or high")
    prior_entropy = _entropy(posterior)
    results = []
    for probe_id, probe in probes.items():
        if probe_id in completed or RISK_ORDER[probe["risk"]] > RISK_ORDER[max_risk]:
            continue
        predictive = {
            outcome: sum(posterior[h] * probe["likelihoods"][h][outcome] for h in posterior)
            for outcome in probe["outcomes"]
        }
        expected_entropy = 0.0
        for outcome, probability in predictive.items():
            if probability <= 0:
                continue
            after = {
                h: posterior[h] * probe["likelihoods"][h][outcome] / probability
                for h in posterior
            }
            expected_entropy += probability * _entropy(after)
        information_gain = max(0.0, prior_entropy - expected_entropy)
        utility = information_gain - RISK_PENALTY[probe["risk"]] - probe["cost"] * 0.1
        results.append({
            "probe_id": probe_id,
            "statement": probe["statement"],
            "information_gain_bits": information_gain,
            "risk": probe["risk"],
            "cost": probe["cost"],
            "utility": utility,
            "predictive_outcomes": predictive,
        })
    return sorted(results, key=lambda row: (-row["utility"], row["probe_id"]))


def _state_from_events(root: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise InvestigationError("first event must initialize the investigation")
    init = events[0]["data"]
    if init.get("schema") != SCHEMA or init.get("investigation_id") != root.name:
        raise InvestigationError("investigation identity or schema mismatch")
    hypotheses = _validate_hypotheses(init.get("hypotheses"))
    hypothesis_ids = {item["id"] for item in hypotheses}
    posterior = {item["id"]: item["prior"] for item in hypotheses}
    probes: dict[str, dict[str, Any]] = {}
    completed: set[str] = set()
    selected: str | None = None
    active: str | None = None
    observations: list[dict[str, Any]] = []
    surprises: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for row in events[1:]:
        kind, data = row["kind"], row["data"]
        if kind == "probe_registered":
            probe = _validate_probe(data.get("probe"), hypothesis_ids)
            if probe["id"] in probes:
                raise InvestigationError(f"probe {probe['id']} was registered more than once")
            probes[probe["id"]] = probe
        elif kind == "probe_selected":
            probe_id = data.get("probe_id")
            if selected is not None or active is not None:
                raise InvestigationError("a second probe was selected before the first was resolved")
            if probe_id not in probes or probe_id in completed:
                raise InvestigationError("selection references an unknown or completed probe")
            ranking = rank_probes(probes, posterior, completed, init.get("max_risk", "low"))
            if not ranking or ranking[0]["probe_id"] != probe_id:
                raise InvestigationError("recorded selection is not the deterministic top safe probe")
            if data.get("posterior_before") != posterior:
                raise InvestigationError("selection posterior does not match replayed state")
            utility = data.get("utility")
            if isinstance(utility, bool) or not isinstance(utility, (float, int)) \
                    or not math.isclose(utility, ranking[0]["utility"], rel_tol=0.0, abs_tol=1e-12):
                raise InvestigationError("selection utility does not match deterministic replay")
            selected = probe_id
            decisions.append({"seq": row["seq"], **data})
        elif kind == "probe_started":
            probe_id = data.get("probe_id")
            if selected != probe_id or active is not None:
                raise InvestigationError("probe start does not match the selected probe")
            if probes[probe_id]["implementation"]["kind"] == "external_observation":
                raise InvestigationError("external probes cannot be started by the local runner")
            active = probe_id
        elif kind == "probe_interrupted":
            probe_id = data.get("probe_id")
            if active != probe_id or selected != probe_id:
                raise InvestigationError("interrupted-probe record does not match active probe")
            if data.get("reason") not in {
                "timeout", "process_exit", "operator_stopped", "source_changed", "unknown"
            }:
                raise InvestigationError("interrupted-probe reason is invalid")
            evidence = data.get("evidence")
            if not isinstance(evidence, dict) or not DIGEST_RE.fullmatch(
                str(evidence.get("digest", ""))
            ):
                raise InvestigationError("interrupted probe requires a digest-addressed record")
            _verify_object(root, evidence["digest"])
            observation = {
                "seq": row["seq"], "event_digest": row["digest"],
                "probe_id": probe_id, "outcome": "unresolved",
                "evidence": evidence, "unexpected": True, "posterior_after": dict(posterior),
                "kind": kind,
            }
            observations.append(observation)
            surprises.append(observation)
            completed.add(probe_id)
            selected = None
            active = None
        elif kind in ("probe_observed", "external_observation"):
            probe_id = data.get("probe_id")
            expected = active if kind == "probe_observed" else selected
            if expected != probe_id:
                raise InvestigationError("observation does not match the selected probe")
            if probe_id not in probes or probe_id in completed:
                raise InvestigationError("observation references an unknown or completed probe")
            probe = probes[probe_id]
            outcome = data.get("outcome")
            if outcome not in probe["outcomes"]:
                raise InvestigationError(f"unregistered outcome {outcome!r} for {probe_id}")
            evidence = data.get("evidence")
            if not isinstance(evidence, dict) or not DIGEST_RE.fullmatch(
                str(evidence.get("digest", ""))
            ):
                raise InvestigationError("observation requires a SHA-256 evidence reference")
            if kind == "probe_observed":
                _verify_object(root, evidence["digest"])
            likelihood = {h: probe["likelihoods"][h][outcome] for h in hypothesis_ids}
            predictive = sum(posterior[h] * likelihood[h] for h in hypothesis_ids)
            unexpected = predictive <= 0.0
            if not unexpected:
                posterior = {h: posterior[h] * likelihood[h] / predictive for h in hypothesis_ids}
            observation = {
                "seq": row["seq"], "event_digest": row["digest"],
                "probe_id": probe_id,
                "outcome": outcome,
                "evidence": evidence,
                "unexpected": unexpected,
                "posterior_after": dict(posterior),
                "kind": kind,
            }
            observations.append(observation)
            if unexpected:
                surprises.append(observation)
            completed.add(probe_id)
            selected = None
            active = None
        elif kind == "report_created":
            if not DIGEST_RE.fullmatch(str(data.get("digest", ""))):
                raise InvestigationError("report event has an invalid digest")
            _verify_object(root, data["digest"])
            reports.append({**dict(data), "event_digest": row["digest"]})
        elif kind == "artifact_reference":
            ref = _validate_relative_file(data.get("artifact_ref"))
            if init.get("artifact_ref") not in (None, ref):
                raise InvestigationError("artifact reference changed after initialization")
            init["artifact_ref"] = ref
        else:
            raise InvestigationError(f"unknown event kind {kind!r}")
    return {
        "init": init, "hypotheses": hypotheses, "hypothesis_ids": hypothesis_ids,
        "posterior": posterior, "probes": probes, "completed": completed,
        "selected": selected, "active": active, "observations": observations,
        "surprises": surprises, "decisions": decisions, "reports": reports, "events": events,
    }


def load_state(root: Path) -> dict[str, Any]:
    root = _check_root(Path(root))
    return _state_from_events(root, _read_log(root))


def add_probe(root: Path, value: Any) -> dict[str, Any]:
    state = load_state(root)
    probe = _validate_probe(value, state["hypothesis_ids"])
    if probe["id"] in state["probes"]:
        raise InvestigationError(f"probe id already registered: {probe['id']}")
    if state["selected"] is not None or state["active"] is not None:
        raise InvestigationError("register the next probe only after resolving the current one")
    recorded = {key: value for key, value in probe.items() if key != "outcomes"}
    _append(root, "probe_registered", {"probe": recorded},
            expected_head=state["events"][-1]["digest"])
    return probe


def select_next(root: Path) -> dict[str, Any] | None:
    root = Path(root)
    state = load_state(root)
    if state["selected"] is not None or state["active"] is not None:
        raise InvestigationError("resolve the selected probe before planning another")
    ranking = rank_probes(state["probes"], state["posterior"], state["completed"],
                          state["init"].get("max_risk", "low"))
    if not ranking or ranking[0]["utility"] <= 1e-12:
        return None
    best = ranking[0]
    _append(root, "probe_selected", {
        "probe_id": best["probe_id"],
        "utility": best["utility"],
        "information_gain_bits": best["information_gain_bits"],
        "posterior_before": dict(state["posterior"]),
        "strategy": "expected_information_gain.v1",
        "reason": "highest expected entropy reduction after declared safety and cost penalties",
    }, expected_head=state["events"][-1]["digest"])
    return best


def _safe_read(root: Path, relative: str, limit: int = MAX_PROBE_BYTES) -> bytes | None:
    relative = _validate_relative_file(relative)
    root = _check_root(Path(root))
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                      getattr(os, "O_NOFOLLOW", 0))
    fd = root_fd
    try:
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            try:
                next_fd = os.open(part, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) |
                                  getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
            except FileNotFoundError:
                return None
            if fd != root_fd:
                os.close(fd)
            fd = next_fd
        try:
            file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK |
                              getattr(os, "O_NOFOLLOW", 0), dir_fd=fd)
        except FileNotFoundError:
            return None
        try:
            info = os.fstat(file_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise InvestigationError("probes read only bounded regular files")
            with os.fdopen(file_fd, "rb", closefd=False) as stream:
                data = stream.read(limit + 1)
            if len(data) > limit:
                raise InvestigationError("probe input exceeds the size limit")
            return data
        finally:
            os.close(file_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise InvestigationError("probe paths may not traverse symlinks or non-directories") from exc
        raise
    finally:
        if fd != root_fd:
            os.close(fd)
        os.close(root_fd)


def _json_pointer(value: Any, pointer: str) -> Any:
    current = value
    if not pointer:
        return current
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise KeyError(token)
            current = current[token]
        elif isinstance(current, list) and token.isdigit():
            current = current[int(token)]
        else:
            raise KeyError(token)
    return current


def _run_builtin(probe: dict[str, Any], probe_root: Path) -> tuple[str, dict[str, Any]]:
    implementation = probe["implementation"]
    kind, path = implementation["kind"], implementation["path"]
    raw = _safe_read(probe_root, path)
    if kind == "file_exists":
        outcome = "present" if raw is not None else "absent"
    elif kind == "sha256_matches":
        outcome = "missing" if raw is None else (
            "match" if _sha(raw) == implementation["expected_digest"] else "different"
        )
    elif kind == "text_contains":
        outcome = "missing" if raw is None else (
            "present" if implementation["literal"].encode("utf-8") in raw else "absent"
        )
    elif kind == "json_equals":
        if raw is None:
            outcome = "missing"
        else:
            try:
                actual = _json_pointer(_loads(raw, path), implementation["pointer"])
            except InvestigationError:
                outcome = "invalid"
            except (KeyError, IndexError):
                outcome = "different"
            else:
                outcome = "match" if _canonical(actual) == _canonical(implementation["expected"]) else "different"
    else:
        raise InvestigationError("local runner accepts only built-in read-only probes")
    evidence = {
        "probe_id": probe["id"], "implementation": kind, "path": path,
        "outcome": outcome, "input_digest": _sha(raw) if raw is not None else None,
        "input_bytes": len(raw) if raw is not None else 0, "captured_at": _now(),
        "side_effects": "none", "network": "none",
    }
    return outcome, evidence


def execute_selected(root: Path, probe_root: Path) -> dict[str, Any]:
    root = Path(root)
    state = load_state(root)
    if state["active"] is not None:
        raise InvestigationError("a probe was interrupted; reconcile it before any retry")
    probe_id = state["selected"]
    if probe_id is None:
        raise InvestigationError("select a safe probe before execution")
    probe = state["probes"][probe_id]
    if probe["implementation"]["kind"] == "external_observation":
        raise InvestigationError("external native-runtime probes must be recorded with observe")
    _append(root, "probe_started", {
        "probe_id": probe_id, "started_at": _now(), "runner": COLLECTOR, "effects": "read_only",
    }, expected_head=state["events"][-1]["digest"])
    outcome, evidence = _run_builtin(probe, probe_root)
    object_bytes = _canonical(evidence)
    digest = _store_object(root, object_bytes)
    latest_state = load_state(root)
    if latest_state["active"] != probe_id:
        raise InvestigationError("probe state changed while it was running; evidence was retained")
    observed = {
        "probe_id": probe_id, "outcome": outcome, "observed_at": _now(),
        "evidence": {
            "digest": digest, "size_bytes": len(object_bytes),
            "media_type": "application/json", "kind": "read_only_probe_result",
        },
    }
    _append(root, "probe_observed", observed,
            expected_head=latest_state["events"][-1]["digest"])
    return observed


def record_external_observation(root: Path, *, outcome: str, evidence_ref: str,
                                evidence_digest: str, collector: str) -> dict[str, Any]:
    root = Path(root)
    state = load_state(root)
    probe_id = state["selected"]
    if probe_id is None:
        raise InvestigationError("select an external probe before recording its result")
    probe = state["probes"][probe_id]
    if probe["implementation"]["kind"] != "external_observation":
        raise InvestigationError("observe is only for probes delegated to a native runtime")
    if outcome not in probe["outcomes"]:
        raise InvestigationError(f"outcome must be one of {probe['outcomes']}")
    if not isinstance(evidence_digest, str) or not DIGEST_RE.fullmatch(evidence_digest):
        raise InvestigationError("external evidence requires sha256:<64 lowercase hex>")
    if not isinstance(evidence_ref, str) or not evidence_ref.strip() or len(evidence_ref) > 512:
        raise InvestigationError("external evidence needs a bounded reference")
    reference_parts = PurePosixPath(evidence_ref).parts
    if (not reference_parts or PurePosixPath(evidence_ref).is_absolute()
            or ":" in reference_parts[0] or "\\" in evidence_ref
            or any(part == ".." for part in reference_parts)):
        raise InvestigationError("external evidence references must not expose absolute host paths")
    if not isinstance(collector, str) or not ID_RE.fullmatch(collector):
        raise InvestigationError("collector identity must be a simple identifier")
    data = {
        "probe_id": probe_id, "outcome": outcome, "observed_at": _now(),
        "collector": collector,
        "evidence": {
            "digest": evidence_digest, "ref": evidence_ref,
            "media_type": "external-reference", "kind": "native_runtime_observation",
        },
    }
    _append(root, "external_observation", data,
            expected_head=state["events"][-1]["digest"])
    return data


def resolve_interrupted_probe(root: Path, reason: str) -> dict[str, Any]:
    root = Path(root)
    state = load_state(root)
    probe_id = state["active"]
    if probe_id is None:
        raise InvestigationError("there is no interrupted local probe to resolve")
    if reason not in {"timeout", "process_exit", "operator_stopped", "source_changed", "unknown"}:
        raise InvestigationError("reason must be timeout, process_exit, operator_stopped, source_changed or unknown")
    evidence = {
        "probe_id": probe_id, "status": "unresolved", "reason": reason,
        "recorded_at": _now(), "side_effects": "none", "network": "none",
    }
    raw = _canonical(evidence)
    digest = _store_object(root, raw)
    data = {
        "probe_id": probe_id,
        "reason": reason,
        "evidence": {
            "digest": digest, "size_bytes": len(raw),
            "media_type": "application/json", "kind": "interrupted_probe",
        },
    }
    _append(root, "probe_interrupted", data,
            expected_head=state["events"][-1]["digest"])
    return data


def build_report(root: Path) -> dict[str, Any]:
    state = load_state(root)
    posterior = state["posterior"]
    ranking = sorted(posterior.items(), key=lambda pair: (-pair[1], pair[0]))
    top_id, top_probability = ranking[0]
    second_probability = ranking[1][1] if len(ranking) > 1 else 0.0
    margin = top_probability - second_probability
    threshold = state["init"]["decision_threshold"]
    clean_evidence = not state["surprises"]
    remaining = rank_probes(
        state["probes"], posterior, state["completed"], state["init"].get("max_risk", "low")
    )
    if state["observations"] and clean_evidence and top_probability >= threshold and margin >= 0.2:
        conclusion = "supported"
        confidence = "high" if top_probability >= 0.95 and margin >= 0.4 else "moderate"
        stop_reason = "posterior_threshold_reached"
    else:
        conclusion = "insufficient_evidence"
        confidence = "low" if top_probability < 0.65 or state["surprises"] else "moderate"
        stop_reason = None
    if state["active"] is not None:
        stop_reason = "probe_interrupted_or_incomplete"
    elif state["selected"] is not None:
        stop_reason = "selected_probe_not_yet_resolved"
    elif stop_reason is None:
        stop_reason = ("no_discriminating_safe_probe_remains"
                       if not remaining or remaining[0]["utility"] <= 1e-12
                       else "continue_with_next_probe")
    by_id = {item["id"]: item for item in state["hypotheses"]}
    return {
        "schema": "agentops.investigation-report.v1",
        "investigation_id": state["init"]["investigation_id"],
        "title": state["init"]["title"],
        "source": {"repository": state["init"]["repository"], "commit": state["init"]["source_commit"]},
        "work_refs": {"item_id": state["init"]["work_item"],
                      "vuoro_run_id": state["init"]["vuoro_run_id"]},
        "conclusion": conclusion, "confidence": confidence, "stop_reason": stop_reason,
        "decision_threshold": threshold,
        "posterior": [
            {"hypothesis_id": ident, "statement": by_id[ident]["statement"], "probability": probability}
            for ident, probability in ranking
        ],
        "observations": state["observations"],
        "unexpected_observations": len(state["surprises"]),
        "probe_decisions": state["decisions"],
        "selected_probe": state["selected"], "incomplete_probe": state["active"],
        "next_probe": (remaining[0] if stop_reason == "continue_with_next_probe" else None),
        "event_count": len(state["events"]), "event_head": state["events"][-1]["digest"],
        "limits": [
            "Posterior values depend on the pre-registered likelihood model.",
            "Unexpected outcomes do not update the posterior.",
            "A supported conclusion is not an owner acceptance or authorization.",
        ],
    }


def write_report(root: Path) -> dict[str, Any]:
    root = Path(root)
    state = load_state(root)
    report = build_report(root)
    data = _canonical(report) + b"\n"
    digest = _store_object(root, data)
    report_dir = root / "reports"
    if report_dir.is_symlink():
        raise InvestigationError("reports directory may not be a symlink")
    report_dir.mkdir(mode=0o700, exist_ok=True)
    report_path = report_dir / (digest.removeprefix("sha256:") + ".json")
    if not report_path.exists():
        _write_new(report_path, data)
    elif report_path.is_symlink() or _sha(report_path.read_bytes()) != digest:
        raise InvestigationError("immutable report path contains different bytes")
    ref_root = state["init"].get("artifact_ref")
    ref = f"{ref_root}/reports/{report_path.name}" if ref_root else f"reports/{report_path.name}"
    payload = {"digest": digest, "ref": ref, "size_bytes": len(data), "media_type": "application/json"}
    _append(root, "report_created", payload, expected_head=report["event_head"])
    return {**report, "evidence": payload}


def vuoro_evidence_payloads(root: Path) -> list[dict[str, Any]]:
    state = load_state(root)
    run_id = state["init"].get("vuoro_run_id")
    if not run_id:
        raise InvestigationError("Vuoro evidence export requires an existing registered run_id")
    ref_root = state["init"].get("artifact_ref") or f"_artifacts/investigations/{root.name}"
    provenance_base = {
        "investigation_id": state["init"]["investigation_id"],
        "source_repository": state["init"].get("repository"),
        "source_commit": state["init"].get("source_commit"),
    }

    def append_args(kind: str, ref: str, digest: str, event_head: str) -> dict[str, Any]:
        key_material = f"{run_id}\0{kind}\0{digest}\0{event_head}".encode("utf-8")
        idempotency_key = "inv:" + hashlib.sha256(key_material).hexdigest()[:48]
        return {
            "run_id": run_id, "kind": kind, "ref": ref, "digest": digest,
            "collector": COLLECTOR, "idempotency_key": idempotency_key,
            "provenance": {**provenance_base, "event_head": event_head},
            "validity": {
                "basis": "until_inputs_change",
                "valid_from": state["init"]["created_at"],
                "component_digests": {"investigation_event_head": event_head},
            },
        }

    payloads: list[dict[str, Any]] = []
    for observation in state["observations"]:
        evidence = observation["evidence"]
        ref = evidence.get("ref") or f"{ref_root}/objects/{evidence['digest'].removeprefix('sha256:')}"
        payloads.append(append_args(
            "investigation_observation", ref, evidence["digest"], observation["event_digest"]
        ))
    for report in state["reports"]:
        payloads.append(append_args(
            "investigation_report", report["ref"], report["digest"], report["event_digest"]
        ))
    return payloads


def evaluate_dataset(dataset: Any) -> dict[str, Any]:
    if not isinstance(dataset, dict) or dataset.get("schema") != EVAL_SCHEMA:
        raise InvestigationError(f"evaluation dataset schema must be {EVAL_SCHEMA}")
    cases = dataset.get("cases")
    if not isinstance(cases, list) or not cases:
        raise InvestigationError("evaluation dataset must contain at least one frozen case")
    rows = []
    case_ids: set[str] = set()
    total_brier = 0.0
    total_probe_match = 0
    correct = 0
    abstained = 0
    for case in cases:
        if not isinstance(case, dict):
            raise InvestigationError("evaluation case must be an object")
        case_id = case.get("id")
        if not isinstance(case_id, str) or not ID_RE.fullmatch(case_id) or case_id in case_ids:
            raise InvestigationError(f"evaluation case id is invalid or duplicated: {case_id!r}")
        case_ids.add(case_id)
        if not isinstance(case.get("source_ref"), str) or not case["source_ref"].strip():
            raise InvestigationError(f"evaluation case {case_id} needs a source reference")
        hypotheses = _validate_hypotheses(case.get("hypotheses"))
        hypothesis_ids = {item["id"] for item in hypotheses}
        posterior = {item["id"]: item["prior"] for item in hypotheses}
        probes: dict[str, dict[str, Any]] = {}
        for raw_probe in case.get("probes", []):
            probe = _validate_probe(raw_probe, hypothesis_ids)
            if probe["id"] in probes:
                raise InvestigationError(f"evaluation case {case_id} has duplicate probes")
            probes[probe["id"]] = probe
        if not probes:
            raise InvestigationError(f"evaluation case {case_id} has no probes")
        expected_first = case.get("expected_first_probe")
        if expected_first not in probes:
            raise InvestigationError(f"evaluation case {case_id} expected probe is not registered")
        ranking = rank_probes(probes, posterior, set(), case.get("max_risk", "low"))
        selected = ranking[0]["probe_id"] if ranking and ranking[0]["utility"] > 0 else None
        total_probe_match += int(selected == expected_first)
        observations = case.get("observations")
        if not isinstance(observations, list) or not observations:
            raise InvestigationError(f"evaluation case {case_id} needs observed outcomes")
        unexpected_observation = False
        for observation in observations:
            probe = probes.get(observation.get("probe_id"))
            if probe is None or observation.get("outcome") not in probe["outcomes"]:
                raise InvestigationError(f"evaluation case {case_id} has an unregistered outcome")
            likelihood = {h: probe["likelihoods"][h][observation["outcome"]] for h in hypothesis_ids}
            predictive = sum(posterior[h] * likelihood[h] for h in hypothesis_ids)
            if predictive > 0:
                posterior = {h: posterior[h] * likelihood[h] / predictive for h in hypothesis_ids}
            else:
                unexpected_observation = True
        expected_hypothesis = case.get("expected_hypothesis")
        if expected_hypothesis not in hypothesis_ids:
            raise InvestigationError(f"evaluation case {case_id} target hypothesis is missing")
        ordered = sorted(posterior.items(), key=lambda pair: (-pair[1], pair[0]))
        threshold = float(case.get("decision_threshold", 0.9))
        predicted = (ordered[0][0] if not unexpected_observation
                     and ordered[0][1] >= threshold
                     and ordered[0][1] - ordered[1][1] >= 0.2 else None)
        is_correct = predicted == expected_hypothesis
        correct += int(is_correct)
        abstained += int(predicted is None)
        brier = sum((posterior[h] - (1.0 if h == expected_hypothesis else 0.0)) ** 2
                    for h in hypothesis_ids)
        total_brier += brier
        rows.append({
            "id": case_id, "source_ref": case.get("source_ref"),
            "expected_hypothesis": expected_hypothesis,
            "selected_first_probe": selected, "expected_first_probe": expected_first,
            "posterior": dict(sorted(posterior.items())), "prediction": predicted,
            "correct": is_correct, "abstained": predicted is None, "brier_score": brier,
        })
    count = len(rows)
    return {
        "schema": "agentops.investigation-evaluation-result.v1",
        "dataset_digest": _sha(_canonical(dataset)), "case_count": count,
        "top1_accuracy": correct / count, "mean_brier_score": total_brier / count,
        "probe_selection_match": total_probe_match / count, "abstention_rate": abstained / count,
        "cases": rows, "qualification": "offline_dataset_replay",
    }


def _read_json_file(path: Path) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_EVENT_BYTES:
        raise InvestigationError(f"input must be a bounded regular JSON file: {path}")
    return _loads(path.read_bytes(), str(path))


def _cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="investigate",
        description="Record, plan, replay and report a bounded agent investigation.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("init", help="create an investigation artifact")
    create.add_argument("directory", type=Path)
    create.add_argument("--title", required=True)
    create.add_argument("--hypotheses", required=True, type=Path)
    create.add_argument("--repository")
    create.add_argument("--source-commit")
    create.add_argument("--work-item", type=int)
    create.add_argument("--vuoro-run-id")
    create.add_argument("--artifact-ref")
    create.add_argument("--decision-threshold", type=float, default=0.9)
    create.add_argument("--max-risk", choices=sorted(RISK_LEVELS), default="low")
    add = sub.add_parser("add-probe", help="pre-register immutable probe predictions")
    add.add_argument("directory", type=Path)
    add.add_argument("--file", required=True, type=Path)
    plan = sub.add_parser("plan", help="rank safe probes by expected information gain")
    plan.add_argument("directory", type=Path)
    select = sub.add_parser("select", help="record the deterministic next-probe decision")
    select.add_argument("directory", type=Path)
    run = sub.add_parser("run", help="execute one selected built-in read-only probe")
    run.add_argument("directory", type=Path)
    run.add_argument("--root", required=True, type=Path,
                     help="local source tree read by the probe; absolute path is never recorded")
    observe = sub.add_parser("observe", help="record an external native-runtime result by digest")
    observe.add_argument("directory", type=Path)
    observe.add_argument("--outcome", required=True)
    observe.add_argument("--evidence-ref", required=True)
    observe.add_argument("--evidence-digest", required=True)
    observe.add_argument("--collector", required=True)
    interrupted = sub.add_parser("resolve-interrupted", help="record an incomplete read-only probe without retrying it")
    interrupted.add_argument("directory", type=Path)
    interrupted.add_argument("--reason", required=True, choices=(
        "timeout", "process_exit", "operator_stopped", "source_changed", "unknown",
    ))
    replay = sub.add_parser("replay", help="verify the hash chain and replay decisions")
    replay.add_argument("directory", type=Path)
    report = sub.add_parser("report", help="render an uncertainty-aware report artifact")
    report.add_argument("directory", type=Path)
    report.add_argument("--write", action="store_true")
    export = sub.add_parser("vuoro-evidence", help="render existing append_evidence payloads")
    export.add_argument("directory", type=Path)
    evaluate = sub.add_parser("evaluate", help="replay a frozen incident or synthetic dataset")
    evaluate.add_argument("--dataset", required=True, type=Path)
    evaluate.add_argument(
        "--expected-digest",
        help="require this SHA-256 of the canonical parsed dataset (same value as dataset_digest)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _cli().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(
                args.directory, title=args.title, hypotheses=_read_json_file(args.hypotheses),
                repository=args.repository, source_commit=args.source_commit,
                work_item=args.work_item, vuoro_run_id=args.vuoro_run_id,
                artifact_ref=args.artifact_ref, decision_threshold=args.decision_threshold,
                max_risk=args.max_risk,
            )
        elif args.command == "add-probe":
            result = add_probe(args.directory, _read_json_file(args.file))
        elif args.command == "plan":
            state = load_state(args.directory)
            result = rank_probes(state["probes"], state["posterior"], state["completed"],
                                 state["init"].get("max_risk", "low"))
        elif args.command == "select":
            result = select_next(args.directory)
            if result is None:
                result = {"selected": None, "reason": "no safe probe has positive expected utility"}
        elif args.command == "run":
            result = execute_selected(args.directory, args.root)
        elif args.command == "observe":
            result = record_external_observation(
                args.directory, outcome=args.outcome, evidence_ref=args.evidence_ref,
                evidence_digest=args.evidence_digest, collector=args.collector,
            )
        elif args.command == "resolve-interrupted":
            result = resolve_interrupted_probe(args.directory, args.reason)
        elif args.command == "replay":
            state = load_state(args.directory)
            result = {
                "valid": True, "event_count": len(state["events"]),
                "event_head": state["events"][-1]["digest"], "posterior": state["posterior"],
                "completed_probes": sorted(state["completed"]),
                "unexpected_observations": len(state["surprises"]),
                "report": build_report(args.directory),
            }
        elif args.command == "report":
            result = write_report(args.directory) if args.write else build_report(args.directory)
        elif args.command == "vuoro-evidence":
            result = vuoro_evidence_payloads(args.directory)
        elif args.command == "evaluate":
            dataset = _read_json_file(args.dataset)
            if args.expected_digest and _sha(_canonical(dataset)) != args.expected_digest:
                raise InvestigationError("evaluation dataset digest does not match the supplied pin")
            result = evaluate_dataset(dataset)
        else:
            raise InvestigationError(f"unsupported command: {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except (InvestigationError, OSError) as exc:
        print(f"investigate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
