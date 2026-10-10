"""The local dispatcher's RunManifest (agentops#2479).

A dispatch run emits one manifest at start; every evidence record it writes cites
``{run_id, manifest_digest}``. These tests pin the three things that make the
reference worth having: the composition matches vuoro-evidence's ``RunManifest``
(same fields, same ``composition_digest``), a manifest is immutable once published,
and a reference resolves only to the exact record it was issued for.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_shadow  # noqa: E402
import run_manifest  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INPUT = {"workflow": "vuoro-dispatch-build", "harness_id": "claude-code",
         "model_ids": ["claude-sonnet-5-5", "claude-opus-5-5", "claude-sonnet-5-5"]}
DECISION = {"repo": "example", "unit": "api", "item_ids": ["7"], "tier": "bounded",
            "dispatch_ready": True, "source": "explicit"}


@pytest.fixture
def auditctl_stub(tmp_path, monkeypatch):
    log = tmp_path / "auditctl-calls.jsonl"
    stub = tmp_path / "auditctl"
    stub.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("AUDITCTL_BIN", str(stub))
    return lambda: [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _metadata(argv):
    return json.loads(argv[argv.index("--metadata") + 1])


def _emit(capsys, document=INPUT, *extra):
    assert run_manifest.main(["emit", "--input-json", json.dumps(document), *extra]) == 0
    return json.loads(capsys.readouterr().out)


def test_composition_digest_matches_vuoro_evidence_vector():
    """Vector computed with vuoro_evidence.run.RunManifest.composition_digest (vuoro main)."""
    record = {
        "run_id": "lrun_01J0000000000000000000000A",
        "harness_id": "claude-code",
        "harness_build": "2.1.0 (Claude Code)",
        "model_id": "claude-haiku-4-5-20251001,claude-opus-5-5,claude-sonnet-5-5",
        "recipe_id": "vuoro-dispatch-build@sha256:" + "a" * 64,
        "observed_profile": {"instruction_digest": "sha256:" + "b" * 64, "skill_digests": []},
        "grant_ids": [],
        "claim_ids": [],
    }
    assert run_manifest.composition_digest(record) == (
        "sha256:9644cebf844eda43390096589bc56f5355142f6f45f307c03b86e190c6a8c8cb")
    # run_id is excluded, as in vuoro: two runs of one composition share the key.
    assert run_manifest.composition_digest({**record, "run_id": "lrun_01J0000000000000000000000B"}) == \
        run_manifest.composition_digest(record)


def test_composition_matches_vuoro_evidence_when_importable():
    try:
        from vuoro_evidence.run import ObservedProfile, RunManifest
    except ImportError:
        candidate = Path("/projects/dev/vuoro/packages/vuoro-evidence/src")
        if not candidate.is_dir():
            pytest.skip("vuoro-evidence is not available on this host")
        sys.path.insert(0, str(candidate))
        try:
            from vuoro_evidence.run import ObservedProfile, RunManifest
        except ImportError:
            pytest.skip("vuoro-evidence is not importable")
    record = run_manifest.build_manifest(INPUT, harness_build="test-build")
    profile = record["observed_profile"]
    manifest = RunManifest(
        run_id=record["run_id"], harness_id=record["harness_id"], harness_build=record["harness_build"],
        model_id=record["model_id"], recipe_id=record["recipe_id"],
        observed_profile=ObservedProfile(profile["instruction_digest"],
                                         tuple(tuple(pair) for pair in profile["skill_digests"])),
        grant_ids=tuple(record["grant_ids"]), claim_ids=tuple(record["claim_ids"]),
    )
    assert manifest.composition() == run_manifest.composition(record)
    assert manifest.composition_digest() == record["composition_digest"]


def test_build_observes_recipe_profile_and_declared_models():
    record = run_manifest.build_manifest(INPUT, harness_build="test-build")
    run_manifest.validate_record(record)
    assert run_manifest.RUN_ID_RE.fullmatch(record["run_id"])
    assert record["model_id"] == "claude-opus-5-5,claude-sonnet-5-5"
    script = ROOT / ".claude" / "workflows" / "vuoro-dispatch-build.js"
    assert record["recipe_id"] == "vuoro-dispatch-build@" + run_manifest._sha256(script.read_bytes())
    assert run_manifest.DIGEST_RE.fullmatch(record["observed_profile"]["instruction_digest"])
    assert record["grant_ids"] == [] and record["claim_ids"] == []  # nothing is held at start


def test_instruction_digest_follows_the_observed_chain(tmp_path):
    (tmp_path / "project.toml").write_text("")
    (tmp_path / "AGENTS.md").write_text("one")
    first = run_manifest.observe_profile(tmp_path)["instruction_digest"]
    assert run_manifest.observe_profile(tmp_path)["instruction_digest"] == first
    (tmp_path / "AGENTS.md").write_text("two")
    assert run_manifest.observe_profile(tmp_path)["instruction_digest"] != first


def test_missing_harness_binary_is_unobserved_not_guessed(monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    assert run_manifest.observe_harness_build("claude-code") == run_manifest.UNOBSERVED


@pytest.mark.parametrize("document", [
    [],
    {**INPUT, "workflow": "other"},
    {**INPUT, "harness_id": "gpt"},
    {**INPUT, "model_ids": []},
    {**INPUT, "model_ids": ["bad model; rm"]},
    {**INPUT, "claim_ids": ["1"]},  # work identity is never declared into a manifest
    {**INPUT, "run_id": "run_01J0000000000000000000000A"},
])
def test_build_rejects(document):
    with pytest.raises(run_manifest.RunManifestError):
        run_manifest.build_manifest(document, harness_build="test-build")


def test_run_ids_are_ulids_outside_the_served_namespace():
    run_id = run_manifest.mint_run_id(now_ms=0, entropy=bytes(10))
    assert run_id == "lrun_" + "0" * 26
    assert run_manifest.RUN_ID_RE.fullmatch(run_manifest.mint_run_id())
    assert not run_manifest.RUN_ID_RE.fullmatch("run_" + "0" * 26)
    assert run_manifest.mint_run_id(now_ms=2) > run_manifest.mint_run_id(now_ms=1, entropy=b"\xff" * 10)


def test_emit_writes_publishes_and_resolves(capsys, auditctl_stub, monkeypatch):
    monkeypatch.setattr(run_manifest, "observe_harness_build", lambda harness: "test-build")
    printed = _emit(capsys)
    assert printed["emitted"] is True and printed["published"] is True
    record = json.loads(Path(printed["path"]).read_text())
    run_manifest.validate_record(record)
    assert record["manifest_digest"] == printed["manifest_digest"]
    [call] = auditctl_stub()
    assert call[call.index("--type") + 1] == run_manifest.EVENT_TYPE
    assert _metadata(call)["run_id"] == printed["run_id"]
    assert _metadata(call)["manifest_digest"] == printed["manifest_digest"]
    assert run_manifest.resolve_reference(printed["run_id"], printed["manifest_digest"])["status"] == "resolved"
    assert run_manifest.main(["resolve", "--run-id", printed["run_id"],
                              "--digest", printed["manifest_digest"]]) == 0


def test_emit_never_fails_its_host(capsys, auditctl_stub):
    printed = _emit(capsys, {"workflow": "nope"})
    assert printed["emitted"] is False and "RunManifestError" in printed["error"]
    assert auditctl_stub() == []


def test_a_published_manifest_is_never_rewritten(tmp_path):
    record = run_manifest.build_manifest(INPUT, harness_build="test-build")
    path = run_manifest.write_manifest(tmp_path, record)
    before = path.read_bytes()
    with pytest.raises(run_manifest.RunManifestError):
        run_manifest.write_manifest(tmp_path, {**record, "harness_build": "other"})
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == [path.name]  # no pending file left behind
    assert stat.S_IMODE(path.stat().st_mode) == 0o444  # write-once is literal
    with pytest.raises(PermissionError):
        path.open("w")


def test_references_resolve_only_to_the_exact_record(tmp_path):
    record = run_manifest.build_manifest(INPUT, harness_build="test-build")
    run_id, digest = record["run_id"], record["manifest_digest"]
    assert run_manifest.resolve_reference(run_id, digest, tmp_path)["status"] == "unresolved"
    path = run_manifest.write_manifest(tmp_path, record)
    assert run_manifest.resolve_reference(run_id, digest, tmp_path)["status"] == "resolved"
    assert run_manifest.resolve_reference(run_id, "sha256:" + "0" * 64, tmp_path)["status"] == "digest-mismatch"
    assert run_manifest.resolve_reference("lrun_$(x)", digest, tmp_path) == {
        "run_id": None, "manifest_digest": None, "status": "invalid"}
    assert run_manifest.resolve_reference(run_id, None, tmp_path)["status"] == "invalid"
    # A tampered manifest no longer validates: present but invalid, not missing.
    path.chmod(0o644)
    path.write_text(json.dumps({**record, "model_id": "swapped"}))
    assert run_manifest.resolve_reference(run_id, digest, tmp_path)["status"] == "manifest-invalid"
    path.write_text("not json")
    assert run_manifest.resolve_reference(run_id, digest, tmp_path)["status"] == "manifest-invalid"


def test_cited_reports_which_notes_carry_the_line(tmp_path, capsys):
    run_id, digest = "lrun_" + "0" * 26, "sha256:" + "c" * 64
    line = run_manifest.citation_line(run_id, digest)
    item = {"events": [
        {"id": 1, "payload": json.dumps({"summary": "verified", "detail": f"evidence ok\n{line}"})},
        {"id": 2, "payload": json.dumps({"summary": "other", "detail": "no citation"})},
        {"id": 3, "payload": {"summary": "x", "detail": f"  {line}  "}},
        {"id": 4, "payload": "not json"},
    ]}
    assert run_manifest.note_citations(item, run_id, digest)["cited_event_ids"] == [1, 3]
    assert run_manifest.note_citations({"events": []}, run_id, digest)["status"] == "not-cited"
    path = tmp_path / "item.json"
    path.write_text(json.dumps(item))
    assert run_manifest.main(["cited", "--item-json", str(path), "--run-id", run_id, "--digest", digest]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "cited"
    assert run_manifest.main(["cited", "--item-json", str(path), "--run-id", run_id,
                              "--digest", "sha256:" + "d" * 64]) == 1


def test_every_decision_event_cites_the_run(capsys, auditctl_stub, monkeypatch):
    monkeypatch.setattr(run_manifest, "observe_harness_build", lambda harness: "test-build")
    printed = _emit(capsys, INPUT, "--no-publish")
    reference = {"run_id": printed["run_id"], "manifest_digest": printed["manifest_digest"]}
    document = {"workflow": "vuoro-dispatch-build", "run": reference,
                "units": [DECISION, {**DECISION, "unit": "storage"}]}
    assert jev_shadow.main(["record", "--input-json", json.dumps(document)]) == 0
    assert json.loads(capsys.readouterr().out)["published"] == 2
    runs = [_metadata(call)["run"] for call in auditctl_stub()]
    assert runs == [{**reference, "status": "resolved"}] * 2


@pytest.mark.parametrize("reference,status", [
    (None, "absent"),
    ("lrun_x", "invalid"),
    ({"run_id": "lrun_" + "0" * 26, "manifest_digest": "sha256:" + "c" * 64}, "unresolved"),
    ({"run_id": "lrun_$(reboot)", "manifest_digest": "sha256:" + "c" * 64}, "invalid"),
])
def test_unbound_decisions_are_recorded_and_say_so(capsys, auditctl_stub, reference, status):
    document = {"workflow": "vuoro-dispatch-build", "units": [DECISION]}
    if reference is not None:
        document["run"] = reference
    assert jev_shadow.main(["record", "--input-json", json.dumps(document)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == {"published": 1, "rejected": []}
    [call] = auditctl_stub()
    run = _metadata(call)["run"]
    assert run["status"] == status
    assert "$(reboot)" not in json.dumps(run)
    # The decision itself still round-trips through the reader.
    assert jev_shadow.validate_decision(_metadata(call))["unit"] == "api"
