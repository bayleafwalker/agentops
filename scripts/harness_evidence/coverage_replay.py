"""Deterministically replay the AE-01 source-coverage envelope.

This is an offline qualification helper, not a session recorder or source of
authority. It counts expected source slots separately from observed events,
deduplicates exact redeliveries by origin sequence, and refuses conflicting
replays. It never opens a source reference, writes a store, or makes a network
request; source-byte digest verification remains the source owner's job.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Any


PACKET_SCHEMA = "agentops-ae01-coverage-fixture/v1"
REPORT_SCHEMA = "agentops-ae01-coverage-fixture-report/v1"
HARNESSES = ("claude-code", "codex")
SOURCE_KINDS = ("native-stop", "git-commit", "test-result")
UNAVAILABLE_REASONS = frozenset({"hook_not_emitted", "source_unavailable", "not_recorded"})

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,126}$")
_SECRET_VALUE = re.compile(
    r"(?i)(?:bearer\s|sk-[a-z0-9]{8,}|(?:api[_-]?key|token|secret)\s*[:=])"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
# Live source-reference formats are deliberately not guessed here. This
# fixture-only packet accepts no URL, host path, commit ID, or provider run ID.
_SOURCE_REF = re.compile(r"^fixture:[A-Za-z0-9._:-]{1,127}$")
_SOURCE_REFS = {
    "native-stop": _SOURCE_REF,
    "git-commit": _SOURCE_REF,
    "test-result": _SOURCE_REF,
}


class ReplayError(ValueError):
    """Raised when an offline packet is incomplete, conflicting, or unsafe."""


def _object(value: Any, required: set[str], optional: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayError(f"{label} must be an object")
    keys = set(value)
    if required - keys or keys - required - optional:
        raise ReplayError(f"{label} has missing or unsupported fields")
    return value


def _identifier(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not _IDENTIFIER.fullmatch(value)
        or _SECRET_VALUE.search(value)
    ):
        raise ReplayError(f"{label} must be a safe opaque identifier")
    return value


def _source_kind(value: Any) -> str:
    if not isinstance(value, str) or value not in SOURCE_KINDS:
        raise ReplayError("unsupported source kind")
    return value


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ReplayError("observed_at must be a UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReplayError("observed_at must be a UTC timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ReplayError("observed_at must be a UTC timestamp")
    return value


def _source_ref(kind: str, value: Any) -> str:
    if (
        not isinstance(value, str)
        or not _SOURCE_REFS[kind].fullmatch(value)
        or _SECRET_VALUE.search(value)
    ):
        raise ReplayError("source_ref must use a bounded, non-path reference")
    return value


def _validate_observation(case_id: str, expected: set[str], raw: Any) -> dict[str, Any]:
    event = _object(
        raw,
        {"origin_id", "origin_seq", "source_kind", "source_ref", "source_digest", "observed_at"},
        set(),
        "observation",
    )
    origin_id = _identifier(event["origin_id"], "origin_id")
    sequence = event["origin_seq"]
    if type(sequence) is not int or sequence < 1:
        raise ReplayError("origin_seq must be a positive integer")
    kind = _source_kind(event["source_kind"])
    if kind not in expected:
        raise ReplayError("observation is outside the declared source denominator")
    source_ref = _source_ref(kind, event["source_ref"])
    digest = event["source_digest"]
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ReplayError("source_digest must be a SHA-256 reference")
    observed_at = _timestamp(event["observed_at"])
    return {
        "case_id": case_id,
        "origin_id": origin_id,
        "origin_seq": sequence,
        "source_kind": kind,
        "source_ref": source_ref,
        "source_digest": digest,
        "observed_at": observed_at,
    }


def _validate_unavailable(expected: set[str], raw: Any) -> set[str]:
    if not isinstance(raw, list):
        raise ReplayError("unavailable_sources must be a list")
    unavailable: set[str] = set()
    for item in raw:
        value = _object(item, {"source_kind", "reason_code"}, set(), "unavailable source")
        kind = _source_kind(value["source_kind"])
        reason = value["reason_code"]
        if kind not in expected:
            raise ReplayError("unavailable source is outside the declared source denominator")
        if kind in unavailable:
            raise ReplayError("duplicate unavailable source")
        if not isinstance(reason, str) or reason not in UNAVAILABLE_REASONS:
            raise ReplayError("unsupported unavailable reason")
        unavailable.add(kind)
    return unavailable


def build_coverage_report(packet: dict[str, Any]) -> dict[str, Any]:
    """Return a count-only report for an AE-01 offline observation packet.

    Every case declares the same three denominator slots: the native harness
    stop observation, Git commit reference, and test-result reference. A slot
    with no captured observation remains unknown. Reports contain no case IDs,
    source references, timestamps, or payload values.
    """
    root = _object(packet, {"schema", "cases"}, set(), "packet")
    if root["schema"] != PACKET_SCHEMA:
        raise ReplayError("unsupported packet schema")
    cases = root["cases"]
    if not isinstance(cases, list) or not cases:
        raise ReplayError("packet must contain cases")

    seen_cases: set[str] = set()
    seen_harnesses: set[str] = set()
    matrix: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"expected": 0, "observed": 0, "unknown": 0}
    )
    replayed: dict[tuple[str, str, int], tuple[str, str, str]] = {}
    unique_observations = 0
    duplicate_deliveries = 0
    expected_slots = 0
    observed_slots = 0
    unknown_slots = 0

    for raw_case in cases:
        case = _object(
            raw_case,
            {"case_id", "harness", "expected_sources", "observations"},
            {"unavailable_sources"},
            "case",
        )
        case_id = _identifier(case["case_id"], "case_id")
        if case_id in seen_cases:
            raise ReplayError("case_id must be unique")
        seen_cases.add(case_id)

        harness = case["harness"]
        if not isinstance(harness, str) or harness not in HARNESSES:
            raise ReplayError("unsupported harness")
        seen_harnesses.add(harness)

        raw_expected = case["expected_sources"]
        if (
            not isinstance(raw_expected, list)
            or any(not isinstance(kind, str) for kind in raw_expected)
            or len(raw_expected) != len(SOURCE_KINDS)
            or set(raw_expected) != set(SOURCE_KINDS)
        ):
            raise ReplayError("each case must declare the full source denominator")
        expected = set(raw_expected)

        observations = case["observations"]
        if not isinstance(observations, list):
            raise ReplayError("observations must be a list")
        observed_kinds: set[str] = set()
        for raw_event in observations:
            event = _validate_observation(case_id, expected, raw_event)
            key = (case_id, event["origin_id"], event["origin_seq"])
            fingerprint = (event["source_kind"], event["source_ref"], event["source_digest"])
            prior = replayed.get(key)
            if prior is not None:
                if prior != fingerprint:
                    raise ReplayError("conflicting event for an existing origin sequence")
                duplicate_deliveries += 1
                continue
            replayed[key] = fingerprint
            observed_kinds.add(event["source_kind"])
            unique_observations += 1

        unavailable = _validate_unavailable(
            expected, case.get("unavailable_sources", [])
        )
        if observed_kinds & unavailable:
            raise ReplayError("source cannot be both observed and unavailable")

        for kind in SOURCE_KINDS:
            cell = matrix[(harness, kind)]
            cell["expected"] += 1
            expected_slots += 1
            if kind in observed_kinds:
                cell["observed"] += 1
                observed_slots += 1
            else:
                # Explicitly unavailable and wholly absent slots both remain
                # unknown. The report never claims the source fact did not exist.
                cell["unknown"] += 1
                unknown_slots += 1

    if seen_harnesses != set(HARNESSES):
        raise ReplayError("packet must cover both Claude Code and Codex")

    coverage_matrix = [
        {
            "harness": harness,
            "source_kind": kind,
            **matrix[(harness, kind)],
        }
        for harness in HARNESSES
        for kind in SOURCE_KINDS
    ]
    return {
        "schema": REPORT_SCHEMA,
        "qualification": "synthetic-fixture-only",
        "authority": "non-authoritative",
        "source_bytes_verified": False,
        "case_count": len(cases),
        "expected_slots": expected_slots,
        "observed_slots": observed_slots,
        "unknown_slots": unknown_slots,
        "unique_observations": unique_observations,
        "duplicate_deliveries": duplicate_deliveries,
        "coverage_status": "incomplete" if unknown_slots else "covered",
        "coverage_matrix": coverage_matrix,
    }
