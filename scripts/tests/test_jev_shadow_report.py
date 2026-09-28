"""The shadow report measures agreement from recorded events without editorialising."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_shadow_report as report  # noqa: E402


def _record(gate, baseline, jev, confidence, *, mode="live", latency=100):
    question = report.GATE_QUESTION[gate]
    return {
        "gate": gate,
        "repo": "example",
        "unit": "u",
        "jev_mode": mode,
        "baseline_label": baseline,
        "jev_label": jev,
        "agree": None if baseline is None else baseline == jev,
        "answer_summary": {question: {"choice": jev, "confidence": confidence}},
        "latency_ms": latency,
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "bundle_id": f"{gate}-v1",
        "bundle_sha256": "a" * 64,
        "model": "jev-1.13.0",
    }


def _event(record, event_type="dispatch.route.shadow"):
    return json.dumps({"event_type": event_type, "type": event_type, "metadata": record})


def test_summary_counts_agreement_confusion_and_bands(tmp_path):
    shard = tmp_path / "events-2026-09-28.ndjson"
    shard.write_text(
        "\n".join([
            _event(_record("route", "bounded", "bounded", 0.9)),
            _event(_record("route", "bounded", "standard", 0.55)),
            _event(_record("route", "hard", "needs_planning", 0.85)),
            _event(_record("route", None, "bounded", 0.9)),
            _event({"gate": "route", "jev_mode": "error", "error": "x"}),
            json.dumps({"event_type": "dispatch.exit", "metadata": {"gate": "route"}}),
            "not json",
        ])
        + "\n"
    )
    replay = tmp_path / "replay.jsonl"
    replay.write_text(json.dumps(_record("verify", "confirmed", "confirmed", 0.95)) + "\n")

    records = report.load_records([shard], [replay])
    summary, disagreements = report.summarize(records)

    route = summary["route"]
    assert route["records"] == 5
    assert route["jev_modes"] == {"live": 4, "error": 1}
    assert route["labelled"] == 3
    assert route["agreement"] == round(1 / 3, 3)
    assert route["confusion"] == {"bounded": {"bounded": 1, "standard": 1}, "hard": {"needs_planning": 1}}
    assert route["agreement_by_confidence"]["0.9-1.0"] == {"agree": 1, "rate": 1.0}
    assert route["agreement_by_confidence"]["0.5-0.7"] == {"disagree": 1, "rate": 0.0}
    assert route["no_match_rate"] == 0.25
    assert route["tokens"] == {"input": 40, "output": 8}
    assert summary["verify"]["agreement"] == 1.0
    assert len(disagreements) == 2
    assert {row["jev_label"] for row in disagreements} == {"standard", "needs_planning"}


def test_main_writes_disagreements(tmp_path, capsys):
    shards = tmp_path / "audit"
    shards.mkdir()
    (shards / "events-1.ndjson").write_text(_event(_record("route", "bounded", "hard", 0.6)) + "\n")
    out = tmp_path / "dis.jsonl"
    assert report.main(["--shards", str(shards), "--disagreements-out", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["route"]["labelled"] == 1
    assert len(out.read_text().splitlines()) == 1
