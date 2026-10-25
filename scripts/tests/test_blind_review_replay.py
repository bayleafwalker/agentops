"""Synthetic-only tests for blind code-review replay preparation and scoring."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import blind_review_replay as replay  # noqa: E402


def card(card_id: str, artifact: str | None = None) -> dict:
    item = {
        "schema": replay.CARD_SCHEMA,
        "card_id": card_id,
        "parent_revision": "parent-fixture",
        "source_revision": "revision-fixture",
        "path": "src/example.rs",
        "artifact_kind": "synthetic_diff",
        "artifact_sha256": replay.sha256((artifact or f"// {card_id}\n").encode()),
        "artifact_utf8": artifact or f"// {card_id}\n",
        "prompt": "Review this synthetic fixture for correctness defects.",
    }
    item["input_digest"] = replay.sha256(replay.canonical_json(item))
    return item


def finding(finding_id: str, *, severity: str = "HIGH", status: str = "confirmed") -> dict:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "claim": "Synthetic state mismatch claim.",
        "verification": {"status": status, "adjudicator": "fixture-adjudicator"},
        "support": ({"file": "src/example.rs", "line": 12,
                     "mechanism": "Synthetic state is read from a different iteration."}
                    if status == "confirmed" else None),
    }


def observation(target: dict, findings: list[dict] | None = None, *,
                model_id: str = "fixture-model", actual: bool = True,
                latency: float | None = 12.0, usage: dict | None = None) -> dict:
    return {
        "schema": replay.OBSERVATION_SCHEMA,
        "card_id": target["card_id"],
        "input_digest": target["input_digest"],
        "model": {"provider": "fixture-provider", "id": model_id,
                  "revision": "fixture-revision", "actual": actual},
        "runtime": {
            "adapter": "fixture-adapter", "version": "fixture-1",
            "request_id": f"request-{target['card_id']}",
            "response_sha256": "sha256:" + "a" * 64,
            "actual": actual,
            "latency_ms": latency,
            "usage": usage if usage is not None else {
                "input_tokens": 100, "output_tokens": 40, "cost_usd": None,
            },
        },
        "findings": findings or [],
    }


def label_set(cards: list[dict]) -> dict:
    return {
        "schema": replay.LABEL_SCHEMA,
        "expected_findings": [
            {"finding_id": "synthetic-high-a", "severity": "HIGH",
             "card_ids": [cards[0]["card_id"]]},
            {"finding_id": "synthetic-high-b", "severity": "HIGH",
             "card_ids": [cards[1]["card_id"]]},
        ],
        "negative_controls": [
            {"card_id": cards[2]["card_id"],
             "absent_finding_ids": ["synthetic-high-a", "synthetic-high-b"]},
        ],
        "unknown_label_count": 7,
    }


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(item) + "\n" for item in records))


def test_prepare_request_is_digest_bound_and_has_no_answer_key(tmp_path: Path):
    card_item = card("opaque-a")
    cards_path = tmp_path / "cards.jsonl"
    output_path = tmp_path / "requests.jsonl"
    write_jsonl(cards_path, [card_item])

    assert replay.prepare(cards_path, output_path) == 1
    request = replay._read_jsonl(output_path)[0]
    assert request["schema"] == replay.REQUEST_SCHEMA
    assert request["input_digest"] == card_item["input_digest"]
    assert request["artifact_utf8"] == card_item["artifact_utf8"]
    assert "expected_findings" not in request
    assert "finding_id" not in request
    with pytest.raises(replay.ReplayError, match="already exists"):
        replay.prepare(cards_path, output_path)


def test_card_rejects_answer_key_fields_and_bad_artifact_digest():
    with pytest.raises(replay.ReplayError, match="unexpected fields"):
        replay.validate_cards([dict(card("opaque-a"), expected_finding_id="leak")])
    broken = card("opaque-b", "fn fixture() {}")
    broken["artifact_sha256"] = "sha256:" + "0" * 64
    broken["input_digest"] = replay.sha256(replay.canonical_json(
        {key: value for key, value in broken.items() if key != "input_digest"}))
    with pytest.raises(replay.ReplayError, match="artifact digest mismatch"):
        replay.validate_cards([broken])


def test_observation_rejects_mismatched_input_digest():
    card_item = card("opaque-a")
    item = observation(card_item)
    item["input_digest"] = "sha256:" + "0" * 64
    with pytest.raises(replay.ReplayError, match="input digest mismatch"):
        replay.validate_observation(item, {card_item["card_id"]: card_item})


def test_missing_actual_model_or_runtime_provenance_cannot_qualify(tmp_path: Path):
    cards = [card("opaque-a"), card("opaque-b"), card("opaque-c")]
    labels = label_set(cards)
    observations = [observation(c, actual=False) for c in cards]
    cards_path, labels_path, observations_path = tmp_path / "cards.jsonl", tmp_path / "labels.json", tmp_path / "observations.jsonl"
    write_jsonl(cards_path, cards)
    labels_path.write_text(json.dumps(labels))
    write_jsonl(observations_path, observations)

    report = replay.qualify(cards_path, labels_path, observations_path,
                            "fixture-model", tmp_path / "report.json")
    assert report["status"] == "not_qualified"
    assert report["checks"]["all_cards_covered_by_actual_target"] is False


def test_both_highs_and_control_are_required_for_operator_review(tmp_path: Path):
    cards = [card("opaque-a"), card("opaque-b"), card("opaque-control")]
    labels = label_set(cards)
    observations = [
        observation(cards[0], [finding("synthetic-high-a")]),
        observation(cards[1], [finding("synthetic-high-b")]),
        observation(cards[2]),
    ]
    cards_path, labels_path, observations_path = tmp_path / "cards.jsonl", tmp_path / "labels.json", tmp_path / "observations.jsonl"
    write_jsonl(cards_path, cards)
    labels_path.write_text(json.dumps(labels))
    write_jsonl(observations_path, observations)

    report = replay.qualify(cards_path, labels_path, observations_path,
                            "fixture-model", tmp_path / "report.json")
    assert report["status"] == "qualified_for_operator_review"
    assert report["unknown_label_count"] == 7
    assert report["checks"]["historical_high_recall"] is True
    assert report["changes_model_policy"] is False
    assert report["cost_coverage"] == {"known": 0, "total": 3}


@pytest.mark.parametrize("case", ["missing_high", "unsupported_high", "unadjudicated_high", "control_false_positive"])
def test_incomplete_or_unsupported_high_evidence_fails_closed(tmp_path: Path, case: str):
    cards = [card("opaque-a"), card("opaque-b"), card("opaque-control")]
    observations = [
        observation(cards[0], [finding("synthetic-high-a")]),
        observation(cards[1], [finding("synthetic-high-b")]),
        observation(cards[2]),
    ]
    if case == "missing_high":
        observations[1]["findings"] = []
    elif case == "unsupported_high":
        observations[0]["findings"] = [finding("novel-unsupported", status="unsupported")]
    elif case == "unadjudicated_high":
        observations[0]["findings"] = [finding("novel-unknown", status="unknown")]
    else:
        observations[2]["findings"] = [finding("synthetic-high-a")]
    cards_path, labels_path, observations_path = tmp_path / "cards.jsonl", tmp_path / "labels.json", tmp_path / "observations.jsonl"
    write_jsonl(cards_path, cards)
    labels_path.write_text(json.dumps(label_set(cards)))
    write_jsonl(observations_path, observations)

    report = replay.qualify(cards_path, labels_path, observations_path,
                            "fixture-model", tmp_path / f"{case}.json")
    assert report["status"] == "not_qualified"
    assert report["changes_model_policy"] is False


def test_missing_latency_or_usage_is_unknown_not_zero(tmp_path: Path):
    cards = [card("opaque-a"), card("opaque-b"), card("opaque-control")]
    observations = [observation(c, latency=None) for c in cards]
    for item in observations:
        item["runtime"]["usage"] = None
    observations[0]["findings"] = [finding("synthetic-high-a")]
    observations[1]["findings"] = [finding("synthetic-high-b")]
    cards_path, labels_path, observations_path = tmp_path / "cards.jsonl", tmp_path / "labels.json", tmp_path / "observations.jsonl"
    write_jsonl(cards_path, cards)
    labels_path.write_text(json.dumps(label_set(cards)))
    write_jsonl(observations_path, observations)

    report = replay.qualify(cards_path, labels_path, observations_path,
                            "fixture-model", tmp_path / "report.json")
    assert report["status"] == "not_qualified"
    assert report["latency_coverage"] == {"known": 0, "total": 3}
    assert report["usage_coverage"] == {"known": 0, "total": 3}
    assert report["cost_coverage"] == {"known": 0, "total": 3}
