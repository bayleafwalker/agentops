"""Routing decision records and offline Jev scoring.

``record`` runs inside dispatch, so it must accept only identifiers, enums and counts
and must never fail. ``route_state`` is the only code deciding what is sent to
api.typesafe.ai, so it is tested against an item carrying every field a sprintctl
record could hold: nothing outside the allowlist may appear in the state.
"""

from __future__ import annotations

import json
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

DECISION = {
    "repo": "example",
    "unit": "api",
    "item_ids": ["7"],
    "tier": "standard",
    "dispatch_ready": True,
    "source": "haiku-triage",
    "verify": {"verdicts": {"7": "confirmed"}, "checks": {"passed": 2, "failed": 0, "timed_out": 0}, "full_suite": "passed"},
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
def stub_loaders(monkeypatch):
    monkeypatch.setattr(jev_shadow, "load_item", lambda repo, item_id: {**FULL_ITEM, "id": item_id})
    monkeypatch.setattr(jev_shadow, "load_risk_surfaces", lambda repo: [])


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


# -- record ---------------------------------------------------------------------------


def test_validate_decision_keeps_only_allowed_fields():
    decision = jev_shadow.validate_decision({**DECISION, "rationale": "prose", "item_ids": [7]})
    assert decision == {**DECISION, "item_ids": ["7"]}


@pytest.mark.parametrize(
    "change",
    [
        {"repo": "../etc"},
        {"unit": "a b"},
        {"item_ids": []},
        {"item_ids": ["7; rm -rf /"]},
        {"tier": "needs_planning"},
        {"dispatch_ready": "yes"},
        {"source": "operator"},
        {"verify": {"verdicts": {"8": "confirmed"}, "checks": {}, "full_suite": "passed"}},
        {"verify": {"verdicts": {"7": "great"}, "checks": {}, "full_suite": "passed"}},
        {"verify": {"verdicts": {}, "checks": {"skipped": 1}, "full_suite": "passed"}},
        {"verify": {"verdicts": {}, "checks": {"passed": -1}, "full_suite": "passed"}},
        {"verify": {"verdicts": {}, "checks": {"passed": True}, "full_suite": "passed"}},
        {"verify": {"verdicts": {}, "checks": {}, "full_suite": "maybe"}},
    ],
)
def test_validate_decision_rejects(change):
    with pytest.raises(ValueError):
        jev_shadow.validate_decision({**DECISION, **change})


def test_record_publishes_one_event_per_valid_unit(auditctl_stub, capsys):
    blocked = {**DECISION, "unit": "later", "dispatch_ready": False, "verify": None}
    document = {"workflow": "vuoro-dispatch-build", "units": [DECISION, {"repo": "bad repo"}, blocked]}
    assert jev_shadow.main(["record", "--input-json", json.dumps(document)]) == 0
    calls = auditctl_stub()
    assert [call[call.index("--type") + 1] for call in calls] == [jev_shadow.DECISION_EVENT] * 2
    first, second = (_metadata(call) for call in calls)
    assert first["workflow"] == "vuoro-dispatch-build"
    assert first["verify"]["checks"]["passed"] == 2
    assert second["dispatch_ready"] is False and "verify" not in second
    printed = json.loads(capsys.readouterr().out)
    assert printed["published"] == 2
    assert printed["rejected"][0]["index"] == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["record", "--input-json", "not json"],
        ["record", "--input-json", "[]"],
        ["record"],
        ["record", "--bogus"],
    ],
)
def test_record_never_fails(auditctl_stub, argv):
    assert jev_shadow.main(argv) == 0
    assert auditctl_stub() == []


def test_record_without_publisher_still_exits_zero(monkeypatch):
    monkeypatch.setenv("AUDITCTL_BIN", "")
    assert jev_shadow.main(["record", "--input-json", json.dumps({"units": [DECISION]})]) == 0


# -- state and labels -----------------------------------------------------------------


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


def test_long_text_is_truncated():
    state = jev_shadow.route_state("example", "api", [{**FULL_ITEM, "description": "x" * 10_000}], [])
    assert len(state["items"][0]["description"]) < 4100


@pytest.mark.parametrize(
    ("baseline", "label"),
    [
        (None, None),
        ({"tier": "standard", "dispatch_ready": True}, "standard"),
        ({"tier": "mechanical", "dispatch_ready": True}, "bounded"),
        ({"tier": "hard", "dispatch_ready": False}, "needs_planning"),
        ({"tier": "bounded", "dispatch_ready": False, "source": "triage-missing"}, None),
        ({"tier": "bogus", "dispatch_ready": True}, None),
    ],
)
def test_route_baseline_label(baseline, label):
    assert jev_shadow.route_baseline_label(baseline) == label


def test_unsafe_repo_and_item_ids_are_refused():
    with pytest.raises(ValueError):
        jev_shadow.load_risk_surfaces("../etc")
    with pytest.raises(ValueError):
        jev_shadow.load_item("example", "7; rm -rf /")


# -- scoring --------------------------------------------------------------------------


def test_judge_route_uses_a_recorded_decision_as_baseline(stub_loaders):
    bundle = jev_client.load_bundle("route-v1")
    record = jev_shadow.judge_route({**DECISION, "tier": "bounded"}, bundle=bundle)
    assert record["jev_mode"] == "fake"
    assert record["jev_label"] == "bounded"  # fake mode answers the first option
    assert record["baseline_label"] == "bounded"
    assert record["agree"] is True
    assert record["bundle_sha256"] == bundle["bundle_sha256"]
    assert set(record["answer_summary"]) == set(bundle["questions"])


def _decision_event(decision, occurred_at, event_type=jev_shadow.DECISION_EVENT, source=jev_shadow.SOURCE):
    return json.dumps({
        "event_id": f"ev-{occurred_at}",
        "event_type": event_type,
        "source": source,
        "occurred_at": occurred_at,
        "metadata": decision,
    })


def test_score_reads_recorded_decisions_from_shards(stub_loaders, tmp_path, capsys):
    shards = tmp_path / "audit"
    shards.mkdir()
    (shards / "events-2026-09-28.ndjson").write_text("\n".join([
        _decision_event(DECISION, "2026-09-27T10:00:00Z"),
        _decision_event({**DECISION, "unit": "later", "dispatch_ready": False}, "2026-09-28T10:00:00Z"),
        _decision_event(DECISION, "2026-09-28T11:00:00Z", event_type="dispatch.exit"),
        _decision_event(DECISION, "2026-09-28T12:00:00Z", source="someone-else"),
        _decision_event({**DECISION, "repo": "../etc"}, "2026-09-28T13:00:00Z"),
        "not json",
    ]) + "\n")
    out = tmp_path / "score.jsonl"
    argv = ["score", "--shards", str(shards), "--since", "2026-09-28", "--out", str(out)]
    assert jev_shadow.main(argv) == 0
    [row] = [json.loads(line) for line in out.read_text().splitlines()]
    assert row["unit"] == "later"
    assert row["baseline_label"] == "needs_planning"
    assert row["baseline"]["event_id"] == "ev-2026-09-28T10:00:00Z"
    assert json.loads(capsys.readouterr().out)["decisions"] == 1


def test_scoring_records_failures_and_continues(monkeypatch, tmp_path):
    def flaky(repo, item_id):
        if item_id == "8":
            raise RuntimeError("sprintctl unavailable")
        return FULL_ITEM

    monkeypatch.setattr(jev_shadow, "load_item", flaky)
    monkeypatch.setattr(jev_shadow, "load_risk_surfaces", lambda repo: [])
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps({"repo": "example", "unit": "a", "items": ["8"], "baseline": None}) + "\n\n"
        + json.dumps({"repo": "example", "unit": "b", "items": ["7"], "baseline": {"tier": "standard", "dispatch_ready": True}}) + "\n"
    )
    out = tmp_path / "out" / "replay.jsonl"
    assert jev_shadow.main(["replay", "--corpus", str(corpus), "--out", str(out)]) == 0
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [row["jev_mode"] for row in rows] == ["error", "fake"]
    assert "sprintctl unavailable" in rows[0]["error"]
    assert rows[1]["agree"] is False
