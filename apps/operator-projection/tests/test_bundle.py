"""Portable byte integrity and refusal cases; hashes never authenticate owners."""
from copy import deepcopy
import json
import socket

import pytest

from operator_projection import bundle as b, reconstruction as p1
from operator_projection.bundle_cli import main
from test_reconstruction import protected_capture, intent


def inputs(doc=None):
    doc = protected_capture() if doc is None else doc
    # Preserve original noncanonical formatting, Unicode and final newline.
    raw = (json.dumps(doc, indent=3, ensure_ascii=False) + "\n").encode()
    return raw, intent(doc)["unified_diff"].encode()


def packed(doc=None):
    return json.loads(b.export(*inputs(doc)))


def assert_unknown(report):
    assert report["integrity"] == "verified-local-bytes"
    assert all(report[k] == "UNKNOWN" for k in ("owner_authority", "owner_currentness", "history_completeness"))
    assert not report["authorizes_effects"]
    assert "unauthenticated" in report["owner_provenance"]
    assert not {"trusted_signature", "currently_accepted", "terminal_status", "decision"} & report.keys()


def test_roundtrip_preserves_exact_capture_and_artifact_bytes_without_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("offline verifier attempted network")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    raw, artifact = inputs()
    before = deepcopy((raw, artifact))
    blob = b.export(raw, artifact)
    envelope = json.loads(blob)
    assert envelope["capture_utf8"].encode() == raw
    assert envelope["artifact_utf8"].encode() == artifact
    report = b.verify(blob)
    assert_unknown(report)
    assert report["p1_consistency"] == "complete" and report["missing"] == []
    assert (raw, artifact) == before


@pytest.mark.parametrize("field", ["capture_utf8", "artifact_utf8", "report"])
def test_flipped_bytes_fail_old_manifest(field):
    value = packed()
    if field == "report":
        value[field]["assurance"] = "changed"
    else:
        value[field] += " "
    with pytest.raises(ValueError, match="integrity"):
        b.verify(p1.canonical(value))


def test_recomputed_all_local_hashes_do_not_establish_authority():
    doc = protected_capture()
    # Self-consistent entirely fabricated owner identity and claim still pass
    # local byte consistency; this is the independent authority counterexample.
    row = intent(doc)
    row["acceptance"]["acceptor_principal"] = "invented:reviewer:0"
    row["acceptance"]["verification"]["verifier_principal"] = "invented:reviewer:0"
    report = b.verify(b.export(*inputs(doc)))
    assert_unknown(report)
    assert report["p1_consistency"] == "complete"


def test_missing_effect_receipt_stays_missing():
    doc = protected_capture()
    intent(doc)["application"] = None
    report = b.verify(b.export(*inputs(doc)))
    assert_unknown(report)
    assert report["p1_consistency"] == "incomplete" and "effect_receipt" in report["missing"]


def test_stale_release_and_decision_substitution_never_imply_current_acceptance():
    doc = protected_capture()
    doc["results"][p1.RELEASE]["value"]["release"]["release_digest"] = "0" * 64
    doc["results"][p1.DECISIONS]["value"]["decisions"][0]["release_digest"] = "0" * 64
    report = b.verify(b.export(*inputs(doc)))
    assert_unknown(report)
    assert report["p1_consistency"] == "conflict"
    assert any(x["link"] == "release_intent_binding" for x in report["conflicts"])


def test_rehashed_arbitrary_report_refused():
    value = packed()
    value["report"]["assurance"] = "signed and current"
    value["manifest"]["report"] = b.entry("report", p1.canonical(value["report"]))
    with pytest.raises(ValueError, match="differs from capture"):
        b.verify(p1.canonical(value))


def test_rehashed_artifact_substitution_refused():
    value = packed()
    value["artifact_utf8"] = "different bytes"
    value["manifest"]["artifact"] = b.entry("artifact", value["artifact_utf8"].encode())
    with pytest.raises(ValueError, match="differ from P1"):
        b.verify(p1.canonical(value))


@pytest.mark.parametrize("mutation", ["unknown-entry", "unknown-field", "wrong-domain", "bool-length", "digest", "signature"])
def test_strict_manifest_refuses_extension_and_signature_claim(mutation):
    value = packed()
    if mutation == "unknown-entry": value["manifest"]["remote"] = {}
    if mutation == "unknown-field": value["manifest"]["capture"]["url"] = "https://not-fetched.invalid"
    if mutation == "wrong-domain": value["manifest"]["artifact"]["domain"] = "built-image/v1"
    if mutation == "bool-length": value["manifest"]["capture"]["bytes"] = True
    if mutation == "digest": value["manifest"]["capture"]["sha256"] = "A" * 64
    if mutation == "signature": value["trusted_owner_proof"] = {"signed": True}
    with pytest.raises(ValueError): b.verify(p1.canonical(value))


@pytest.mark.parametrize("blob", [b'{"schema":1,"schema":2}', b'NaN', b'"\\ud800"', b'\xff', b'[' * 66 + b'0' + b']' * 66])
def test_malicious_json_refused(blob):
    with pytest.raises(ValueError): b.verify(blob)


def test_duplicate_inside_carried_capture_refused():
    raw, artifact = inputs()
    raw = raw.replace(b'"repo_id": "demo"', b'"repo_id": "demo", "repo_id": "demo"', 1)
    with pytest.raises(ValueError): b.export(raw, artifact)


def test_size_limits_refused():
    raw, artifact = inputs()
    for capture, content in ((raw + b' ' * b.CAPTURE_LIMIT, artifact), (raw, b'x' * (b.ARTIFACT_LIMIT + 1))):
        with pytest.raises(ValueError): b.export(capture, content)
    with pytest.raises(ValueError): b.verify(b' ' * (b.LIMIT + 1))


def test_artifact_missing_and_wrong_scope_refused():
    doc = protected_capture()
    raw, artifact = inputs(doc)
    doc["results"][p1.EFFECT] = {"status": "unavailable", "value": None}
    with pytest.raises(ValueError): b.export(p1.canonical(doc), artifact)
    doc = protected_capture(); doc["repo_id"] = "foreign"
    with pytest.raises(ValueError): b.export(p1.canonical(doc), artifact)


def test_cli_roundtrip_no_input_writes_and_refusal_no_partial_output(tmp_path, capsys):
    raw, artifact = inputs()
    cap, art = tmp_path / "capture.json", tmp_path / "diff.txt"
    cap.write_bytes(raw); art.write_bytes(artifact)
    assert main(["export", "--capture", str(cap), "--artifact", str(art)]) == 0
    blob = capsys.readouterr().out.encode()
    path = tmp_path / "bundle.json"; path.write_bytes(blob)
    before = {x.name: x.read_bytes() for x in tmp_path.iterdir()}
    assert main(["verify", str(path)]) == 0
    assert_unknown(json.loads(capsys.readouterr().out))
    assert before == {x.name: x.read_bytes() for x in tmp_path.iterdir()}
    path.write_bytes(b'{"secret":"never-echo-this"}')
    assert main(["verify", str(path)]) == 2
    output = capsys.readouterr()
    assert output.out == "" and "never-echo-this" not in output.err
