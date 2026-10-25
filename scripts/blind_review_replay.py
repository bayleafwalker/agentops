#!/usr/bin/env python3
"""Prepare blind code-review requests and score independently adjudicated runs.

This utility has no model client. It does not send review cards to any provider.
Source material, expected labels, and observations are supplied by the caller.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


CARD_SCHEMA = "blind-review-card/v1"
REQUEST_SCHEMA = "blind-review-request/v1"
OBSERVATION_SCHEMA = "blind-review-observation/v1"
LABEL_SCHEMA = "blind-review-label-set/v1"
REPORT_SCHEMA = "blind-review-qualification-report/v1"
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
CARD_FIELDS = {
    "schema", "card_id", "parent_revision", "source_revision", "path",
    "artifact_kind", "artifact_sha256", "artifact_utf8", "prompt",
    "input_digest",
}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"}
VERIFICATION = {"confirmed", "unsupported", "unknown"}


class ReplayError(ValueError):
    """Raised when a replay input is incomplete, inconsistent, or unsafe."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReplayError(f"{path}:{number}: invalid JSON") from exc
        if not isinstance(item, dict):
            raise ReplayError(f"{path}:{number}: record must be an object")
        records.append(item)
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_bytes(b"".join(canonical_json(record) + b"\n" for record in records))


def _require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReplayError(f"{field} must be a non-empty string")
    return value


def validate_cards(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not records:
        raise ReplayError("at least one review card is required")
    by_id: dict[str, dict[str, Any]] = {}
    for index, card in enumerate(records, 1):
        if set(card) != CARD_FIELDS:
            extra = sorted(set(card) - CARD_FIELDS)
            missing = sorted(CARD_FIELDS - set(card))
            if extra:
                raise ReplayError(f"card {index} has unexpected fields: {', '.join(extra)}")
            raise ReplayError(f"card {index} is missing fields: {', '.join(missing)}")
        if card["schema"] != CARD_SCHEMA:
            raise ReplayError(f"card {index} has unsupported schema")
        card_id = _require_text(card["card_id"], f"card {index} card_id")
        if card_id in by_id:
            raise ReplayError(f"duplicate card_id: {card_id}")
        if not SHA256.fullmatch(str(card["artifact_sha256"])):
            raise ReplayError(f"card {card_id} has malformed artifact_sha256")
        artifact = card["artifact_utf8"]
        if not isinstance(artifact, str):
            raise ReplayError(f"card {card_id} artifact_utf8 must be a string")
        if sha256(artifact.encode("utf-8")) != card["artifact_sha256"]:
            raise ReplayError(f"card {card_id} artifact digest mismatch")
        for field in ("source_revision", "path", "artifact_kind", "prompt"):
            _require_text(card[field], f"card {card_id} {field}")
        if card["parent_revision"] is not None and not isinstance(card["parent_revision"], str):
            raise ReplayError(f"card {card_id} parent_revision must be text or null")
        if not SHA256.fullmatch(str(card["input_digest"])):
            raise ReplayError(f"card {card_id} has malformed input_digest")
        unsigned = {key: value for key, value in card.items() if key != "input_digest"}
        if sha256(canonical_json(unsigned)) != card["input_digest"]:
            raise ReplayError(f"card {card_id} input digest mismatch")
        by_id[card_id] = card
    return by_id


def blind_request(card: dict[str, Any]) -> dict[str, Any]:
    """Return the exact reviewer envelope; expected-label fields are not representable."""
    validate_cards([card])
    request = {key: value for key, value in card.items() if key != "input_digest"}
    request.update(schema=REQUEST_SCHEMA, input_digest=card["input_digest"])
    request["request_sha256"] = sha256(canonical_json(request))
    return request


def prepare(cards_path: Path, output_path: Path) -> int:
    cards = validate_cards(_read_jsonl(cards_path))
    requests = [blind_request(card) for card in cards.values()]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        raise ReplayError(f"output already exists: {output_path}")
    _write_jsonl(output_path, requests)
    return len(requests)


def validate_observation(item: dict[str, Any], cards: dict[str, dict[str, Any]]) -> None:
    required = {"schema", "card_id", "input_digest", "model", "runtime", "findings"}
    if set(item) != required:
        raise ReplayError("observation has unexpected or missing fields")
    if item["schema"] != OBSERVATION_SCHEMA:
        raise ReplayError("observation has unsupported schema")
    card = cards.get(item["card_id"])
    if card is None:
        raise ReplayError(f"observation refers to unknown card: {item['card_id']}")
    if item["input_digest"] != card["input_digest"]:
        raise ReplayError(f"observation input digest mismatch: {item['card_id']}")
    model = item["model"]
    runtime = item["runtime"]
    if not isinstance(model, dict) or set(model) != {"provider", "id", "revision", "actual"}:
        raise ReplayError("observation model provenance is incomplete")
    for field in ("provider", "id", "revision"):
        _require_text(model[field], f"model.{field}")
    if not isinstance(model["actual"], bool):
        raise ReplayError("model.actual must be boolean")
    runtime_fields = {"adapter", "version", "request_id", "response_sha256", "actual",
                      "latency_ms", "usage"}
    if not isinstance(runtime, dict) or set(runtime) != runtime_fields:
        raise ReplayError("observation runtime provenance is incomplete")
    for field in ("adapter", "version", "request_id"):
        _require_text(runtime[field], f"runtime.{field}")
    if not SHA256.fullmatch(str(runtime["response_sha256"])):
        raise ReplayError("runtime.response_sha256 is malformed")
    if not isinstance(runtime["actual"], bool):
        raise ReplayError("runtime.actual must be boolean")
    latency = runtime["latency_ms"]
    if latency is not None and (not isinstance(latency, (int, float)) or isinstance(latency, bool)
                                or not math.isfinite(latency) or latency < 0):
        raise ReplayError("runtime.latency_ms must be a non-negative number or null")
    usage = runtime["usage"]
    if usage is not None:
        if not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens", "cost_usd"}:
            raise ReplayError("runtime.usage must contain input_tokens, output_tokens, cost_usd")
        for key, value in usage.items():
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                                      or not math.isfinite(value) or value < 0):
                raise ReplayError(f"runtime.usage.{key} must be non-negative or null")
    if not isinstance(item["findings"], list):
        raise ReplayError("findings must be a list")
    for finding in item["findings"]:
        if not isinstance(finding, dict) or set(finding) != {
                "finding_id", "severity", "claim", "verification", "support"}:
            raise ReplayError("finding has unexpected or missing fields")
        if finding["finding_id"] is not None:
            _require_text(finding["finding_id"], "finding.finding_id")
        if finding["severity"] not in SEVERITIES:
            raise ReplayError("finding severity is invalid")
        _require_text(finding["claim"], "finding.claim")
        verification = finding["verification"]
        if not isinstance(verification, dict) or set(verification) != {"status", "adjudicator"}:
            raise ReplayError("finding verification is incomplete")
        if verification["status"] not in VERIFICATION:
            raise ReplayError("finding verification status is invalid")
        _require_text(verification["adjudicator"], "verification.adjudicator")
        support = finding["support"]
        if verification["status"] == "confirmed":
            if not isinstance(support, dict) or set(support) != {"file", "line", "mechanism"}:
                raise ReplayError("confirmed finding needs file/line/mechanism support")
            _require_text(support["file"], "support.file")
            _require_text(support["mechanism"], "support.mechanism")
            if not isinstance(support["line"], int) or isinstance(support["line"], bool) or support["line"] < 1:
                raise ReplayError("support.line must be a positive integer")
        elif support is not None and not isinstance(support, dict):
            raise ReplayError("unconfirmed finding support must be an object or null")


def _load_labels(path: Path, cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    labels = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(labels, dict) or labels.get("schema") != LABEL_SCHEMA:
        raise ReplayError("labels file has unsupported schema")
    if set(labels) != {"schema", "expected_findings", "negative_controls", "unknown_label_count"}:
        raise ReplayError("labels file has unexpected or missing fields")
    expected = labels["expected_findings"]
    controls = labels["negative_controls"]
    unknown_count = labels["unknown_label_count"]
    if not isinstance(expected, list) or not isinstance(controls, list):
        raise ReplayError("expected_findings and negative_controls must be lists")
    if not isinstance(unknown_count, int) or isinstance(unknown_count, bool) or unknown_count < 0:
        raise ReplayError("unknown_label_count must be a non-negative integer")
    seen = set()
    for finding in expected:
        if not isinstance(finding, dict) or set(finding) != {"finding_id", "severity", "card_ids"}:
            raise ReplayError("expected finding record is invalid")
        finding_id = _require_text(finding["finding_id"], "expected finding_id")
        if finding_id in seen:
            raise ReplayError(f"duplicate expected finding_id: {finding_id}")
        seen.add(finding_id)
        if finding["severity"] not in SEVERITIES:
            raise ReplayError(f"invalid expected severity for {finding_id}")
        if not isinstance(finding["card_ids"], list) or not finding["card_ids"]:
            raise ReplayError(f"expected finding {finding_id} needs card_ids")
        if any(card_id not in cards for card_id in finding["card_ids"]):
            raise ReplayError(f"expected finding {finding_id} refers to unknown card")
    for control in controls:
        if not isinstance(control, dict) or set(control) != {"card_id", "absent_finding_ids"}:
            raise ReplayError("negative control record is invalid")
        if control["card_id"] not in cards:
            raise ReplayError("negative control refers to unknown card")
        if not isinstance(control["absent_finding_ids"], list):
            raise ReplayError("absent_finding_ids must be a list")
    return labels


def qualify(cards_path: Path, labels_path: Path, observations_path: Path,
            target_model: str, output_path: Path) -> dict[str, Any]:
    cards = validate_cards(_read_jsonl(cards_path))
    labels = _load_labels(labels_path, cards)
    observations = _read_jsonl(observations_path)
    if not observations:
        raise ReplayError("no observations provided; unknown is not a measured zero")
    pairs = set()
    for item in observations:
        validate_observation(item, cards)
        pair = (item["card_id"], item["model"]["id"])
        if pair in pairs:
            raise ReplayError(f"duplicate observation for card/model: {pair}")
        pairs.add(pair)
    target = [item for item in observations if item["model"]["id"] == target_model]
    covered_cards = {item["card_id"] for item in target if item["model"]["actual"]
                     and item["runtime"]["actual"]}
    expected_high = {item["finding_id"]: item for item in labels["expected_findings"]
                     if item["severity"] == "HIGH"}
    confirmed: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    unsupported_high = []
    unadjudicated_high = []
    for observation in target:
        for finding in observation["findings"]:
            status = finding["verification"]["status"]
            if finding["severity"] == "HIGH" and status == "unsupported":
                unsupported_high.append({"card_id": observation["card_id"], "finding_id": finding["finding_id"]})
            if finding["severity"] == "HIGH" and status == "unknown":
                unadjudicated_high.append({"card_id": observation["card_id"], "finding_id": finding["finding_id"]})
            if status == "confirmed" and finding["finding_id"]:
                confirmed.setdefault(finding["finding_id"], []).append((observation, finding))
    detected_high = {}
    for finding_id, expected in expected_high.items():
        detected_high[finding_id] = any(
            observation["card_id"] in expected["card_ids"]
            and finding["severity"] == "HIGH"
            for observation, finding in confirmed.get(finding_id, [])
        )
    control_false_positives = []
    for control in labels["negative_controls"]:
        ids = set(control["absent_finding_ids"])
        for observation, finding_list in ((item, item["findings"]) for item in target
                                          if item["card_id"] == control["card_id"]):
            for finding in finding_list:
                if (finding["finding_id"] in ids and finding["severity"] == "HIGH"
                        and finding["verification"]["status"] == "confirmed"):
                    control_false_positives.append({"card_id": observation["card_id"],
                                                    "finding_id": finding["finding_id"]})
    latency_covered = sum(item["runtime"]["latency_ms"] is not None for item in target)
    usage_covered = sum(item["runtime"]["usage"] is not None
                        and item["runtime"]["usage"]["input_tokens"] is not None
                        and item["runtime"]["usage"]["output_tokens"] is not None
                        for item in target)
    cost_covered = sum(item["runtime"]["usage"] is not None
                       and item["runtime"]["usage"]["cost_usd"] is not None
                       for item in target)
    all_high_found = bool(expected_high) and all(detected_high.values())
    checks = {
        "historical_high_recall": all_high_found,
        "all_cards_covered_by_actual_target": len(covered_cards) == len(cards),
        "no_unsupported_high": not unsupported_high,
        "no_unadjudicated_high": not unadjudicated_high,
        "negative_controls_clear": not control_false_positives,
        "latency_coverage_complete": len(target) > 0 and latency_covered == len(target),
        "usage_coverage_complete": len(target) > 0 and usage_covered == len(target),
    }
    report = {
        "schema": REPORT_SCHEMA,
        "target_model": target_model,
        "status": "qualified_for_operator_review" if all(checks.values()) else "not_qualified",
        "card_count": len(cards),
        "target_observation_count": len(target),
        "actual_target_card_coverage": len(covered_cards),
        "expected_high_identity_count": len(expected_high),
        "detected_high_identities": sorted(key for key, value in detected_high.items() if value),
        "missed_high_identities": sorted(key for key, value in detected_high.items() if not value),
        "unsupported_high_count": len(unsupported_high),
        "unadjudicated_high_count": len(unadjudicated_high),
        "control_false_positive_count": len(control_false_positives),
        "unknown_label_count": labels["unknown_label_count"],
        "latency_coverage": {"known": latency_covered, "total": len(target)},
        "usage_coverage": {"known": usage_covered, "total": len(target)},
        "cost_coverage": {"known": cost_covered, "total": len(target)},
        "card_inputs": [{"card_id": card["card_id"],
                         "input_digest": card["input_digest"],
                         "artifact_sha256": card["artifact_sha256"],
                         "source_revision": card["source_revision"],
                         "path": card["path"]}
                        for card in cards.values()],
        "checks": checks,
        "changes_model_policy": False,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare", help="validate cards and make blind request JSONL")
    prepare_parser.add_argument("--cards", type=Path, required=True)
    prepare_parser.add_argument("--output", type=Path, required=True)
    qualify_parser = subparsers.add_parser("qualify", help="score adjudicated observations")
    qualify_parser.add_argument("--cards", type=Path, required=True)
    qualify_parser.add_argument("--labels", type=Path, required=True,
                                help="private expected-label JSON; never include in review requests")
    qualify_parser.add_argument("--observations", type=Path, required=True)
    qualify_parser.add_argument("--target-model", required=True)
    qualify_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            count = prepare(args.cards, args.output)
            print(json.dumps({"prepared": count, "output": str(args.output)}))
            return 0
        report = qualify(args.cards, args.labels, args.observations,
                         args.target_model, args.output)
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "qualified_for_operator_review" else 2
    except (ReplayError, OSError, json.JSONDecodeError) as exc:
        print(f"blind-review-replay: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
