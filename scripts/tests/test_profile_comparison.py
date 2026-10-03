"""Profile/outcome oracles use schema-valid bindings and independently timed notes."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import profile_comparison as subject
import schema_check

SCHEMA = json.loads((ROOT / "schemas/session-binding.schema.json").read_text())


def binding(session="session-A", source_digest="a" * 64, skills=None):
    value = {
        "schema_version": "session-binding/v0",
        "binding_id": "00000000-0000-0000-0000-000000000001",
        "runtime_session_id": session,
        "resolved_at": "2026-01-01T00:00:00Z",
        "harness": {"name": "test"}, "created_at_entry": {"source": "startup"},
        "actor": {"os_user": "fixture", "uid": 1000}, "host": {"hostname": "fixture"},
        "environment": {"record": None, "resolution_source": "unresolved"},
        "workspace": {"cwd": "/repo", "project": {"project_id": None, "path": None,
            "sha256": None, "resolution_source": "undeclared"}},
        "entitlement": {"settings_sources": [{"scope": "user", "path": "/settings",
            "present": False, "sha256": None}], "resolution_source": "declared-layers"},
        "instructions": {"root": "/repo", "root_source": "git-toplevel",
            "sources": [{"name": "AGENTS.md", "path": "/repo/AGENTS.md", "sha256": source_digest}],
            "skills": skills or []},
    }
    assert schema_check.validate(value, SCHEMA) == []
    return value


def skill(name="review", digest="b" * 64, unresolved=False):
    return {"name": name, "path": None if unresolved else "/skills/" + name,
        "sha256": None if unresolved else digest,
        "resolution": "unresolved" if unresolved else "user",
        "loaded_at": "2026-01-01T00:00:00Z"}


def save(tmp_path, value):
    path = tmp_path / (value["runtime_session_id"] + ".json")
    path.write_text(json.dumps(value))


def tick(session="session-A", end="2026-01-01T00:20:00Z"):
    return {"decision": "done", "session_id": session, "ts": end, "minutes": 10}


def note(item, minute, kind="lane.review", tags=None, actor="devbox-agent-vuoro"):
    return {"work_item_id": item, "event_type": kind, "actor": actor,
        "created_at": "2026-01-01T00:" + minute + ":00Z",
        "payload": json.dumps({"tags": tags if tags is not None else ["lane", "verdict:accepted", "first-pass"]})}


def test_sources_alone_separate_profiles(tmp_path):
    save(tmp_path, binding())
    save(tmp_path, binding("session-B", "c" * 64))
    report = subject.build_report([tick(), tick("session-B")], [], tmp_path)
    assert len(report["rows"]) == 2
    assert len({row["digest"] for row in report["rows"]}) == 2
    assert report["no_binding"] == 0


def test_skill_content_changes_digest():
    a = binding(skills=[skill()])
    b = binding(skills=[skill(digest="c" * 64)])
    assert subject.observed_profile_digest(a) != subject.observed_profile_digest(b)


def test_unresolved_skill_is_kept():
    value = binding(skills=[skill(unresolved=True)])
    assert subject.observed_profile(value)["skills"] == [{"name": "review", "path": None, "sha256": None}]
    assert subject.observed_profile_digest(value) != subject.observed_profile_digest(binding())


def test_identical_profiles_merge_sessions(tmp_path):
    save(tmp_path, binding())
    save(tmp_path, binding("session-B"))
    report = subject.build_report([tick(), tick("session-B")], [], tmp_path)
    assert len(report["rows"]) == 1
    assert report["rows"][0]["sessions"] == 2


def test_missing_binding_is_counted_not_fabricated(tmp_path):
    save(tmp_path, binding())
    report = subject.build_report([tick(), tick("missing"), tick("missing")], [], tmp_path)
    assert report["no_binding"] == 1
    assert report["rows"][0]["sessions"] == 1
    assert report["done_ticks"] == 3


def test_exact_canonical_digest_and_timing_exclusion():
    value = binding()
    expected = ('{"root":"/repo","skills":[],"sources":[{"path":"/repo/AGENTS.md",'
                '"sha256":"' + "a" * 64 + '"}]}').encode()
    assert subject.observed_profile_digest(value) == hashlib.sha256(expected).hexdigest()
    a = binding(skills=[skill()])
    b = copy.deepcopy(a)
    b["instructions"]["skills"][0].update(loaded_at="2026-01-02T00:00:00Z", resolution="root")
    assert schema_check.validate(b, SCHEMA) == []
    assert subject.observed_profile_digest(a) == subject.observed_profile_digest(b)


def test_skill_order_ignored_source_order_preserved():
    a = binding(skills=[skill("z"), skill("a")])
    b = copy.deepcopy(a)
    b["instructions"]["skills"].reverse()
    assert subject.observed_profile_digest(a) == subject.observed_profile_digest(b)
    a["instructions"]["sources"].append({"name": "CLAUDE.md", "path": "/repo/CLAUDE.md", "sha256": "c" * 64})
    b = copy.deepcopy(a)
    b["instructions"]["sources"].reverse()
    assert schema_check.validate(a, SCHEMA) == schema_check.validate(b, SCHEMA) == []
    assert subject.observed_profile_digest(a) != subject.observed_profile_digest(b)


def test_latest_review_in_window_wins_and_noise_is_excluded(tmp_path):
    save(tmp_path, binding())
    events = [note(1, "11", "lane.dispatch"), note(1, "12"),
        note(1, "18", tags=["lane", "verdict:reworked"]),
        note(1, "19", actor="another-agent"), note(1, "19", tags=["verdict:accepted"]),
        note(1, "21"), note(2, "14", "lane.dispatch"), note(2, "17")]
    row = subject.build_report([tick()], events, tmp_path)["rows"][0]
    assert (row["items"], row["first_pass"], row["accepted"], row["reworked"]) == (2, 1, 1, 1)
    assert row["first_pass_rate"] == 0.5


def test_multi_item_and_repeat_session_counts(tmp_path):
    save(tmp_path, binding())
    events = [note(1, "11", "lane.dispatch"), note(1, "19"),
        note(2, "12", "lane.dispatch"), note(2, "18", tags=["lane", "verdict:accepted"]),
        note(3, "13", "lane.dispatch")]
    row = subject.build_report([tick()], events, tmp_path)["rows"][0]
    assert (row["sessions"], row["items"], row["first_pass"], row["accepted"], row["reworked"], row["no_review"]) == (1, 3, 1, 2, 0, 1)
    assert row["first_pass_rate"] == 0.5


def test_reworked_tag_cannot_count_as_first_pass_acceptance(tmp_path):
    save(tmp_path, binding())
    row = subject.build_report([tick()], [note(1, "19", tags=["lane", "first-pass", "verdict:reworked"])], tmp_path)["rows"][0]
    assert row["first_pass"] == row["accepted"] == 0
    assert row["reworked"] == 1 and row["first_pass_rate"] == 0


def test_equal_timestamp_uses_event_id_not_export_order(tmp_path):
    save(tmp_path, binding())
    older = note(1, "19", tags=["lane", "verdict:reworked"])
    older["id"] = 10
    newer = note(1, "19")
    newer["id"] = 11
    row = subject.build_report([tick()], [newer, older], tmp_path)["rows"][0]
    assert row["accepted"] == row["first_pass"] == 1


@pytest.mark.parametrize("session", ["../outside", "/absolute", "bad\\path"])
def test_session_path_is_refused(tmp_path, session):
    with pytest.raises(ValueError, match="filename"):
        subject.build_report([tick(session)], [], tmp_path)


def test_binding_session_mismatch_is_refused(tmp_path):
    value = binding("different")
    (tmp_path / "session-A.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="does not match"):
        subject.build_report([tick()], [], tmp_path)


def test_cli_is_read_only_and_imports_existing_join(tmp_path):
    save(tmp_path, binding())
    ledger = tmp_path / "ticks.jsonl"
    ledger.write_text(json.dumps(tick()) + "\n" + json.dumps({"decision": "running"}) + "\n")
    events = tmp_path / "events.json"
    events.write_text(json.dumps([note(1, "19")]))
    before = {path: path.read_bytes() for path in tmp_path.iterdir()}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/profile_comparison.py"),
        "--ledger", str(ledger), "--bindings-dir", str(tmp_path), "--events-json", str(events), "--json"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["done_ticks"] == 1 and report["rows"][0]["accepted"] == 1
    assert "canonical JSON" in report["digest_definition"]
    assert before == {path: path.read_bytes() for path in tmp_path.iterdir()}
    assert subject.apportion_tick.__module__ == "cost_per_release"


def test_missing_ledger_fails_instead_of_reporting_zero_history(tmp_path):
    events = tmp_path / "events.json"
    events.write_text("[]")
    result = subprocess.run([sys.executable, str(ROOT / "scripts/profile_comparison.py"),
        "--ledger", str(tmp_path / "missing"), "--events-json", str(events)], capture_output=True, text=True)
    assert result.returncode == 2 and "ledger does not exist" in result.stderr
    assert result.stdout == ""
