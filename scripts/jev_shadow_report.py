#!/usr/bin/env python3
"""Measure Jev shadow judgments against the decisions dispatch actually took.

Reads ``dispatch.route.shadow`` / ``dispatch.verify.shadow`` events from the audit
shards and any replay JSONL, and reports per gate: agreement, a confusion matrix of
baseline label against Jev label, agreement by Jev confidence band, how often Jev
chose a no-match option, latency and token usage. The disagreement set is written as
JSONL for operator labelling.

The report describes; it never recommends automation. Promotion of any confidence
region out of shadow is an operator decision taken on the labelled disagreement set.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
EVENT_TYPES = {"dispatch.route.shadow": "route", "dispatch.verify.shadow": "verify"}
GATE_QUESTION = {"route": "tier", "verify": "evidence_supports"}
NO_MATCH = {"needs_planning", "insufficient_evidence", "needs_clarification"}
BANDS = ((0.0, 0.5), (0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))


def _event_record(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = event.get("event_type") or event.get("type")
    if event_type not in EVENT_TYPES:
        return None
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        metadata = (event.get("payload") or {}).get("metadata")
    return metadata if isinstance(metadata, dict) else None


def load_records(shard_paths: Iterable[Path], replay_paths: Iterable[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in shard_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = _event_record(json.loads(line))
            except json.JSONDecodeError:
                continue
            if record is not None:
                records.append(record)
    for path in replay_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))]


def _band(confidence: float | None) -> str:
    if confidence is None:
        return "unknown"
    for low, high in BANDS:
        if low <= confidence < high:
            return f"{low:.1f}-{min(high, 1.0):.1f}"
    return "unknown"


def summarize(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_gate: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_gate[record.get("gate") or "unknown"].append(record)
    report: dict[str, Any] = {}
    disagreements: list[dict[str, Any]] = []
    for gate, rows in sorted(by_gate.items()):
        modes = Counter(row.get("jev_mode") for row in rows)
        answered = [row for row in rows if row.get("jev_mode") == "live"]
        labelled = [row for row in answered if row.get("agree") is not None]
        question = GATE_QUESTION.get(gate)
        confusion: dict[str, Counter] = defaultdict(Counter)
        bands: dict[str, Counter] = defaultdict(Counter)
        for row in labelled:
            confusion[row.get("baseline_label")][row.get("jev_label")] += 1
            confidence = ((row.get("answer_summary") or {}).get(question) or {}).get("confidence")
            bands[_band(confidence)]["agree" if row["agree"] else "disagree"] += 1
            if not row["agree"]:
                disagreements.append({
                    key: row.get(key)
                    for key in ("gate", "repo", "unit", "item_ids", "baseline", "baseline_label", "jev_label", "answer_summary", "model", "bundle_id", "bundle_sha256", "recorded_at")
                })
        latencies = [row["latency_ms"] for row in answered if isinstance(row.get("latency_ms"), (int, float))]
        report[gate] = {
            "records": len(rows),
            "jev_modes": dict(modes),
            "live_answered": len(answered),
            "labelled": len(labelled),
            "agreement": round(sum(row["agree"] for row in labelled) / len(labelled), 3) if labelled else None,
            "confusion": {str(base): dict(counts) for base, counts in confusion.items()},
            "agreement_by_confidence": {
                band: {**counts, "rate": round(counts["agree"] / (counts["agree"] + counts["disagree"]), 3)}
                for band, counts in sorted(bands.items())
            },
            "jev_label_distribution": dict(Counter(row.get("jev_label") for row in answered)),
            "no_match_rate": round(sum(row.get("jev_label") in NO_MATCH for row in answered) / len(answered), 3) if answered else None,
            "latency_ms": {"p50": _percentile(latencies, 0.5), "p95": _percentile(latencies, 0.95)},
            "tokens": {
                "input": sum((row.get("usage") or {}).get("input_tokens", 0) for row in answered),
                "output": sum((row.get("usage") or {}).get("output_tokens", 0) for row in answered),
            },
            "bundles": sorted({f"{row.get('bundle_id')}@{str(row.get('bundle_sha256'))[:12]}" for row in answered}),
            "models": sorted({str(row.get("model")) for row in answered}),
        }
    return report, disagreements


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--shards", default=str(ROOT / "_artifacts" / "agentops" / "audit"), help="audit shard directory")
    parser.add_argument("--replay", action="append", default=[], help="replay JSONL (repeatable)")
    parser.add_argument("--disagreements-out", help="write the disagreement set as JSONL")
    args = parser.parse_args(argv)

    shard_dir = Path(args.shards)
    shards = sorted(shard_dir.glob("*.ndjson")) if shard_dir.is_dir() else []
    records = load_records(shards, [Path(path) for path in args.replay])
    report, disagreements = summarize(records)
    if args.disagreements_out:
        out = Path(args.disagreements_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(row) + "\n" for row in disagreements), encoding="utf-8")
        report["disagreements_out"] = str(out)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
