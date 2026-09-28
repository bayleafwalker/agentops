"""Jev shadow judgments: what leaves the host, what is recorded, and that they never fail.

The state builders are the only code deciding what is sent to api.typesafe.ai, so
they are tested against an item carrying every field a sprintctl record or verifier
result could hold: nothing outside the allowlist may appear in the state.
"""

from __future__ import annotations

import io
import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_client  # noqa: E402
import jev_shadow  # noqa: E402

FULL_ITEM = {
    "repo_id": "example",
    "id": 7,
    "title": "Add a flag",
    "description": "Add --flag to the CLI; tests cover it.",
    "status": "done",
    "assignee": "someone",
    "aggregate_uuid": "0000",
    "edit_revision": "rev",
    "status_revision": "srev",
    "claim_token": "SECRET-CLAIM",
    "transcript_path": "/home/x/transcript.jsonl",
}


def _strings(value):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield str(key)
            yield from _strings(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _strings(inner)
    else:
        yield str(value)


@pytest.fixture(autouse=True)
def _fake_mode(tmp_path, monkeypatch):
    monkeypatch.setenv(jev_client.KEY_FILE_ENV, str(tmp_path / "no-key"))


@pytest.fixture
def auditctl_stub(tmp_path, monkeypatch):
    log = tmp_path / "auditctl-calls.jsonl"
    stub = tmp_path / "auditctl"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("AUDITCTL_BIN", str(stub))

    def calls():
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    return calls


def _metadata(argv):
    return json.loads(argv[argv.index("--metadata") + 1])


def test_route_state_keeps_only_allowlisted_fields():
    surfaces = [{"id": "auth", "paths": ["src/auth/**"], "required_on_change": True}]
    state = jev_shadow.route_state("example", "api", [FULL_ITEM], surfaces)
    assert state == {
        "repo": "example",
        "unit": "api",
        "items": [{"item_id": "7", "title": "Add a flag", "description": "Add --flag to the CLI; tests cover it."}],
        "manifest": {"risk_surfaces": surfaces},
    }
    leaked = " ".join(_strings(state))
    for forbidden in ("SECRET-CLAIM", "transcript", "someone", "srev", "done"):
        assert forbidden not in leaked


def test_verify_state_keeps_only_allowlisted_fields():
    result = {"item_id": "7", "verdict": "confirmed", "summary": "ok", "concerns": ["c"], "claim_token": "SECRET"}
    evidence = {
        "checks_run": [{"command": "pytest -q", "outcome": "passed", "stdout": "RAW LOG"}],
        "full_suite": {"outcome": "passed", "reason": "ran", "raw_tail": "TAIL"},
        "diff": "DIFF",
    }
    state = jev_shadow.verify_state("example", "api", result, evidence)
    assert set(state) == {"repo", "unit", "item", "checks_run", "full_suite"}
    assert state["item"] == {"item_id": "7", "summary": "ok", "concerns": ["c"]}
    leaked = " ".join(_strings(state))
    for forbidden in ("SECRET", "RAW LOG", "TAIL", "DIFF", "confirmed"):
        assert forbidden not in leaked


def test_long_text_is_truncated():
    item = {**FULL_ITEM, "description": "x" * 10_000}
    state = jev_shadow.route_state("example", "api", [item], [])
    assert len(state["items"][0]["description"]) < 4100


@pytest.mark.parametrize(
    ("baseline", "label"),
    [
        (None, None),
        ({"tier": "standard", "dispatch_ready": True}, "standard"),
        ({"tier": "mechanical", "dispatch_ready": True}, "bounded"),
        ({"tier": "hard", "dispatch_ready": False}, "needs_planning"),
        ({"tier": "bogus", "dispatch_ready": True}, None),
    ],
)
def test_route_baseline_label(baseline, label):
    assert jev_shadow.route_baseline_label(baseline) == label


def test_judge_route_records_baseline_answers_and_bundle():
    bundle = jev_client.load_bundle("route-v1")
    record = jev_shadow.judge_route(
        {"repo": "example", "unit": "api", "items": [{"item_id": "7"}], "baseline": {"tier": "bounded", "dispatch_ready": True, "source": "explicit"}},
        bundle=bundle,
        item_loader=lambda repo, item_id: FULL_ITEM,
        risk_loader=lambda repo: [],
    )
    assert record["jev_mode"] == "fake"
    assert record["jev_label"] == "bounded"  # fake mode answers the first option
    assert record["baseline_label"] == "bounded"
    assert record["agree"] is True
    assert record["bundle_sha256"] == bundle["bundle_sha256"]
    assert set(record["answer_summary"]) == set(bundle["questions"])


def test_judge_verify_emits_one_record_per_item():
    records = list(jev_shadow.judge_verify(
        {
            "repo": "example",
            "unit": "api",
            "mode": "gate",
            "results": [
                {"item_id": "1", "verdict": "confirmed", "summary": "s", "concerns": []},
                {"item_id": "2", "verdict": "issues_found", "summary": "s", "concerns": ["bug"]},
            ],
            "checks_run": [{"command": "pytest", "outcome": "passed"}],
            "full_suite": {"outcome": "passed", "reason": ""},
        },
        bundle=jev_client.load_bundle("verify-v1"),
    ))
    assert [record["item_ids"] for record in records] == [["1"], ["2"]]
    assert [record["agree"] for record in records] == [True, False]
    assert all(record["verify_mode"] == "gate" for record in records)


def test_route_command_publishes_one_event(auditctl_stub, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(jev_shadow, "load_item", lambda repo, item_id: FULL_ITEM)
    monkeypatch.setattr(jev_shadow, "load_risk_surfaces", lambda repo: [])
    document = tmp_path / "in.json"
    document.write_text(json.dumps({"repo": "example", "unit": "api", "items": [{"item_id": "7"}], "baseline": {"tier": "hard", "dispatch_ready": True}}))
    assert jev_shadow.main(["route", "--input", str(document)]) == 0
    calls = auditctl_stub()
    assert len(calls) == 1
    assert calls[0][calls[0].index("--type") + 1] == jev_shadow.ROUTE_EVENT
    assert calls[0][calls[0].index("--source") + 1] == "jev-shadow"
    metadata = _metadata(calls[0])
    assert metadata["baseline_label"] == "hard"
    assert metadata["agree"] is False
    printed = json.loads(capsys.readouterr().out)
    assert printed[0]["jev_mode"] == "fake"


def test_route_reads_stdin(auditctl_stub, monkeypatch):
    monkeypatch.setattr(jev_shadow, "load_item", lambda repo, item_id: FULL_ITEM)
    monkeypatch.setattr(jev_shadow, "load_risk_surfaces", lambda repo: [])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"repo": "example", "items": ["7"]})))
    assert jev_shadow.main(["route", "--input", "-"]) == 0
    assert _metadata(auditctl_stub()[0])["unit"] == "example"


def test_failures_are_recorded_and_exit_zero(auditctl_stub, monkeypatch, tmp_path):
    def broken(repo, item_id):
        raise RuntimeError("sprintctl unavailable")

    monkeypatch.setattr(jev_shadow, "load_item", broken)
    document = tmp_path / "in.json"
    document.write_text(json.dumps({"repo": "example", "unit": "api", "items": ["7"], "baseline": {"tier": "bounded"}}))
    assert jev_shadow.main(["route", "--input", str(document)]) == 0
    metadata = _metadata(auditctl_stub()[0])
    assert metadata["jev_mode"] == "error"
    assert "sprintctl unavailable" in metadata["error"]
    assert metadata["baseline"] == {"tier": "bounded"}

    garbage = tmp_path / "bad.json"
    garbage.write_text("not json")
    assert jev_shadow.main(["verify", "--input", str(garbage)]) == 0
    assert _metadata(auditctl_stub()[1])["jev_mode"] == "error"


def test_missing_publisher_still_exits_zero(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDITCTL_BIN", "")
    monkeypatch.setattr(jev_shadow, "load_item", lambda repo, item_id: FULL_ITEM)
    monkeypatch.setattr(jev_shadow, "load_risk_surfaces", lambda repo: [])
    document = tmp_path / "in.json"
    document.write_text(json.dumps({"repo": "example", "items": ["7"]}))
    assert jev_shadow.main(["route", "--input", str(document)]) == 0


def test_replay_writes_jsonl_and_never_publishes(auditctl_stub, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(jev_shadow, "load_item", lambda repo, item_id: FULL_ITEM)
    monkeypatch.setattr(jev_shadow, "load_risk_surfaces", lambda repo: [])
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps({"repo": "example", "unit": "a", "items": ["7"], "baseline": None}) + "\n\n"
        + json.dumps({"repo": "example", "unit": "b", "items": ["8"], "baseline": {"tier": "standard", "dispatch_ready": True}}) + "\n"
    )
    out = tmp_path / "out" / "replay.jsonl"
    assert jev_shadow.main(["replay", "--gate", "route", "--corpus", str(corpus), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [row["unit"] for row in rows] == ["a", "b"]
    assert all(row["replay"] for row in rows)
    assert rows[0]["agree"] is None
    assert auditctl_stub() == []
    assert json.loads(capsys.readouterr().out)["records"] == 2


def test_triage_failure_is_not_a_planning_label():
    baseline = {"tier": "bounded", "dispatch_ready": False, "source": "triage-missing"}
    assert jev_shadow.route_baseline_label(baseline) is None


def test_base64_input(auditctl_stub, monkeypatch):
    import base64

    monkeypatch.setattr(jev_shadow, "load_item", lambda repo, item_id: FULL_ITEM)
    monkeypatch.setattr(jev_shadow, "load_risk_surfaces", lambda repo: [])
    token = base64.b64encode(json.dumps({"repo": "example", "unit": "ä-unit", "items": ["7"]}).encode("utf-8")).decode()
    assert jev_shadow.main(["route", "--input-b64", token]) == 0
    assert _metadata(auditctl_stub()[0])["unit"] == "ä-unit"


def test_corrupted_base64_is_recorded_not_raised(auditctl_stub):
    assert jev_shadow.main(["verify", "--input-b64", "not*base64"]) == 0
    assert _metadata(auditctl_stub()[0])["jev_mode"] == "error"


@pytest.mark.parametrize("argv", [["route"], ["verify", "--input", "a", "--input-b64", "b"], ["route", "--bogus"]])
def test_mangled_relay_arguments_exit_zero(argv):
    assert jev_shadow.main(argv) == 0


def test_unsafe_repo_and_item_ids_are_refused():
    with pytest.raises(ValueError):
        jev_shadow.load_risk_surfaces("../etc")
    with pytest.raises(ValueError):
        jev_shadow.load_item("example", "7; rm -rf /")


def test_verify_publishes_each_item_and_records_items_past_the_deadline(auditctl_stub, tmp_path):
    document = tmp_path / "in.json"
    document.write_text(json.dumps({
        "repo": "example",
        "unit": "api",
        "results": [
            {"item_id": "1", "verdict": "confirmed", "summary": "s", "concerns": []},
            {"item_id": "2", "verdict": "confirmed", "summary": "s", "concerns": []},
        ],
    }))
    assert jev_shadow.main(["verify", "--input", str(document), "--deadline", "-1"]) == 0
    records = [_metadata(call) for call in auditctl_stub()]
    assert [record["item_ids"] for record in records] == [["1"], ["2"]]
    assert all(record["jev_mode"] == "error" and "deadline" in record["error"] for record in records)
