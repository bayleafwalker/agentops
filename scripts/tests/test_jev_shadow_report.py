"""The routing report measures agreement from scored records without editorialising."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_shadow_report as report  # noqa: E402


def _record(baseline, jev, confidence, *, mode="live", source="explicit", latency=100):
    return {
        "gate": "route",
        "repo": "example",
        "unit": "u",
        "jev_mode": mode,
        "baseline": {"source": source},
        "baseline_label": baseline,
        "jev_label": jev,
        "agree": None if baseline is None else baseline == jev,
        "answer_summary": {"tier": {"choice": jev, "confidence": confidence}},
        "latency_ms": latency,
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "bundle_id": "route-v1",
        "bundle_sha256": "a" * 64,
        "model": "jev-1.13.0",
    }


def test_summary_counts_agreement_confusion_and_bands(tmp_path):
    scored = tmp_path / "score.jsonl"
    scored.write_text("\n".join(json.dumps(row) for row in [
        _record("bounded", "bounded", 0.9),
        _record("bounded", "standard", 0.55, source="haiku-triage"),
        _record("hard", "needs_planning", 0.85, source="haiku-triage"),
        _record(None, "bounded", 0.9),
        {"gate": "route", "jev_mode": "error", "error": "x"},
    ]) + "\n\n")

    summary, disagreements = report.summarize(report.load_records([scored]))

    route = summary["route"]
    assert route["records"] == 5
    assert route["jev_modes"] == {"live": 4, "error": 1}
    assert route["labelled"] == 3
    assert route["agreement"] == round(1 / 3, 3)
    # needs_planning is a real label, not an abstention, so it stays in the denominator.
    assert route["agreement_excluding_no_match"] == round(1 / 3, 3)
    assert route["agreement_by_source"] == {"explicit": 1.0, "haiku-triage": 0.0}
    assert route["confusion"] == {"bounded": {"bounded": 1, "standard": 1}, "hard": {"needs_planning": 1}}
    assert route["agreement_by_confidence"]["0.9-1.0"] == {"agree": 1, "rate": 1.0}
    assert route["agreement_by_confidence"]["0.5-0.7"] == {"disagree": 1, "rate": 0.0}
    assert route["no_match_rate"] == 0.25
    assert route["tokens"] == {"input": 40, "output": 8}
    assert {row["jev_label"] for row in disagreements} == {"standard", "needs_planning"}


def test_non_numeric_confidence_is_banded_as_unknown():
    summary, _ = report.summarize([_record("bounded", "bounded", "high")])
    assert summary["route"]["agreement_by_confidence"] == {"unknown": {"agree": 1, "rate": 1.0}}


def test_main_writes_disagreements(tmp_path, capsys):
    scored = tmp_path / "score.jsonl"
    scored.write_text(json.dumps(_record("bounded", "hard", 0.6)) + "\n")
    out = tmp_path / "dis.jsonl"
    assert report.main([str(scored), "--disagreements-out", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["route"]["labelled"] == 1
    assert len(out.read_text().splitlines()) == 1
