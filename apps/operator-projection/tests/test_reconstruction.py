"""Independent missing-link, stale-artifact and read-boundary histories."""
from copy import deepcopy
import hashlib
import json

import pytest

from operator_projection import reconstruction as r
from operator_projection.cli import main
from operator_projection.sources import Authority, READ_OPS as FRONT_PAGE_READS

# Golden generated independently with the released owner's pure digest function.
DIGEST = "54d0286afc0a99c2a8737a14c2a4feb174458c284c6bfe257db68970d1e2fddb"


def capture():
    intent = dict(intent_id="effect_demo", revision=1, item_id=42, run_id="run_demo",
        repository="bayleafwalker/demo", base_commit="a" * 40, title="A bounded change",
        rationale="Review the exact bytes", unified_diff="--- a/demo\n+++ b/demo\n@@ -1 +1 @@\n-old\n+new\n",
        canonical_intent_digest=DIGEST, state="applied",
        acceptance=dict(intent_id="effect_demo", intent_revision=1, canonical_intent_digest=DIGEST,
            acceptor_principal="issuer:reviewer:0", acceptor_policy_version=None, accepted_at="2026-10-06T12:00:00Z"),
        application=dict(applier_principal="issuer:reconciler:0", commit_sha="b" * 40,
            pr_url="https://github.com/bayleafwalker/demo/pull/1", applied_at="2026-10-06T12:01:00Z"))
    def entry(value, arguments):
        return dict(status="observed", value=value, arguments=arguments, observed_at="2026-10-06T12:02:00Z")
    return dict(schema=r.CAPTURE_SCHEMA, repo_id="demo", intent_id="effect_demo", results={
        r.EFFECT: entry(dict(repo_id="demo", intent=intent), dict(intent_id="effect_demo")),
        r.RELEASE: entry(dict(repo_id="demo", release=dict(work_item_id=42, release_digest="c" * 64,
            item_revision="item:demo@description:v1@revise:0", acceptance_contract={"review_required": True}), commits=[]), dict(item_id=42)),
        r.DECISIONS: entry(dict(repo_id="demo", item_id=42, decisions=[dict(id=5, kind="accept",
            release_digest="c" * 64, evidence_digests=["d" * 64])]), dict(item_id=42)),
        r.LEASES: entry(dict(repo_id="demo", item_id=42, current_lease=None,
            leases=[dict(lease_id="lease_demo", run_id="run_demo")], outcome_reports=[],
            verification={"ready": True}, evaluated_at="2026-10-06T12:02:00Z"), dict(item_id=42))})


def intent(doc):
    return doc["results"][r.EFFECT]["value"]["intent"]


def protected_capture():
    doc = capture()
    row = intent(doc)
    row["release_digest"] = "c" * 64
    receipt = dict(schema="sprintctl-protected-artifact-verification/v1",
        intent_id=row["intent_id"], intent_revision=1, canonical_intent_digest=DIGEST,
        release_digest="c" * 64,
        artifact=dict(domain="utf8-unified-diff/v1", digest="sha256:" +
            hashlib.sha256(row["unified_diff"].encode()).hexdigest()),
        checks=[dict(name="clean-patch-application", revision="sha256:" + "e" * 64, status="passed")])
    row["acceptance"]["verification"] = dict(run_id="run_verifier", item_id="proof_demo",
        evidence_digest="sha256:" + hashlib.sha256(json.dumps(receipt, sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
        entry_digest="sha256:" + "f" * 64, verifier_principal="issuer:reviewer:0",
        workspace_id="native:demo:0", client_id=None, grant_id=None, receipt=receipt)
    doc["results"][r.RELEASE]["value"]["release"]["acceptance_contract"]["effect_verification_required"] = True
    return doc


def test_protected_owner_links_explain_exact_artifact_without_inferred_authority():
    doc = protected_capture(); before = deepcopy(doc)
    report = r.reconstruct(doc)
    assert report["status"] == "complete" and report["missing"] == []
    proof = report["links"]["verification_evidence"]["value"]
    assert proof["verifier_principal"] == "issuer:reviewer:0"
    assert proof["receipt"]["artifact"]["digest"] != "sha256:" + DIGEST
    assert report["links"]["release_intent_binding"]["value"]["release_digest"] == "c" * 64
    assert not report["authorizes_effects"] and "not authenticated" in report["assurance"]
    assert doc == before


@pytest.mark.parametrize("change", ["raw-artifact", "receipt-digest", "intent", "revision",
    "release", "verifier", "failed-check", "empty-checks", "duplicate-checks", "check-revision",
    "entry-digest", "run", "workspace", "grant", "unknown-field", "proof-type"])
def test_malformed_or_changed_protected_proof_cannot_explain_an_applied_effect(change):
    doc = protected_capture(); proof = intent(doc)["acceptance"]["verification"]
    detail = proof["receipt"]
    if change == "raw-artifact": detail["artifact"]["digest"] = "sha256:" + "0" * 64
    if change == "receipt-digest": proof["evidence_digest"] = "sha256:" + "0" * 64
    if change == "intent": detail["intent_id"] = "another"
    if change == "revision": detail["intent_revision"] = True
    if change == "release": detail["release_digest"] = "0" * 64
    if change == "verifier": proof["verifier_principal"] = "issuer:proposer:0"
    if change == "failed-check": detail["checks"][0]["status"] = "failed"
    if change == "empty-checks": detail["checks"] = []
    if change == "duplicate-checks": detail["checks"] *= 2
    if change == "check-revision": detail["checks"][0]["revision"] = "unknown"
    if change == "entry-digest": proof["entry_digest"] = "unknown"
    if change == "run": proof["run_id"] = ""
    if change == "workspace": proof["workspace_id"] = ""
    if change == "grant": proof["grant_id"] = 1
    if change == "unknown-field": proof["provider_verdict"] = "success"
    if change == "proof-type": intent(doc)["acceptance"]["verification"] = []
    # Recompute the outer digest except for the deliberate digest fault, so
    # semantic counterexamples cannot pass only because their old hash differs.
    if change != "receipt-digest":
        proof["evidence_digest"] = "sha256:" + hashlib.sha256(json.dumps(detail,
            sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    report = r.reconstruct(doc)
    assert report["status"] == "conflict"
    for key in ("verification_evidence", "acceptance", "effect_receipt"):
        assert report["links"][key]["status"] == "conflict"


def test_current_release_change_invalidates_old_binding_and_verification():
    doc = protected_capture()
    doc["results"][r.RELEASE]["value"]["release"]["release_digest"] = "0" * 64
    report = r.reconstruct(doc)
    for key in ("release_intent_binding", "verification_evidence", "acceptance", "effect_receipt"):
        assert report["links"][key]["status"] == "conflict"


def test_missing_release_or_receipt_stays_missing_even_with_valid_protected_proof():
    doc = protected_capture(); del doc["results"][r.RELEASE]
    report = r.reconstruct(doc)
    assert report["status"] == "incomplete"
    assert "release_intent_binding" in report["missing"]
    doc = protected_capture(); intent(doc)["application"] = None
    assert "effect_receipt" in r.reconstruct(doc)["missing"]


def test_work_decisions_do_not_replace_a_missing_required_protected_proof():
    doc = protected_capture(); del intent(doc)["acceptance"]["verification"]
    report = r.reconstruct(doc)
    assert report["links"]["verification_evidence"]["status"] == "missing"
    assert report["status"] == "incomplete"


def test_owner_acceptance_and_receipt_do_not_fabricate_missing_release_or_verifier_binding():
    doc = capture(); before = deepcopy(doc)
    report = r.reconstruct(doc)
    assert report["status"] == "incomplete" and not report["authorizes_effects"]
    assert report["links"]["artifact"]["value"]["digest"] == DIGEST
    assert report["links"]["work_release"]["value"]["release_digest"] != DIGEST
    assert report["missing"] == ["release_intent_binding", "verification_evidence"]
    assert report["links"]["acceptance"]["value"]["acceptor_policy_version"] is None
    assert '"unified_diff"' not in json.dumps(report)
    assert "not every attempt" in report["links"]["attempts_and_claims"]["value"]["scope"]
    assert doc == before


def test_deleting_receipt_remains_an_explicit_missing_row_in_json_and_text():
    doc = capture(); intent(doc)["application"] = None
    report = r.reconstruct(doc)
    assert "effect_receipt" in report["missing"]
    assert "effect_receipt: missing" in r.render_text(report)


def test_changed_artifact_cannot_reuse_acceptance_or_application_receipt():
    doc = capture(); intent(doc)["unified_diff"] += "+extra\n"
    report = r.reconstruct(doc)
    assert report["status"] == "conflict"
    for key in ("artifact", "acceptance", "effect_receipt"):
        assert report["links"][key]["status"] == "conflict"


@pytest.mark.parametrize("field,value", [("intent_id", "another"), ("intent_revision", 2),
    ("intent_revision", True), ("canonical_intent_digest", "f" * 64), ("acceptor_principal", "")])
def test_wrong_or_malformed_acceptance_never_explains_the_recorded_effect(field, value):
    doc = capture(); intent(doc)["acceptance"][field] = value
    report = r.reconstruct(doc)
    assert report["links"]["acceptance"]["status"] == "conflict"
    assert report["links"]["effect_receipt"]["status"] == "conflict"


def test_proposed_or_rejected_state_cannot_reuse_an_acceptance_row():
    doc = capture(); intent(doc)["state"] = "proposed"
    assert r.reconstruct(doc)["links"]["acceptance"]["status"] == "conflict"


@pytest.mark.parametrize("operation", [r.RELEASE, r.DECISIONS, r.LEASES])
def test_missing_read_cannot_be_filled_by_labels_or_other_records(operation):
    doc = capture(); del doc["results"][operation]
    report = r.reconstruct(doc)
    key = {r.RELEASE: "work_release", r.DECISIONS: "verification_evidence", r.LEASES: "attempts_and_claims"}[operation]
    assert report["links"][key]["status"] == "missing"


@pytest.mark.parametrize("operation", list(r.READ_OPS))
def test_cross_repository_result_refuses_the_entire_projection(operation):
    doc = capture(); doc["results"][operation]["value"]["repo_id"] = "other"
    with pytest.raises(r.ReconstructionError, match="repository mismatch"):
        r.reconstruct(doc)


def test_cross_item_release_and_swapped_request_refuse_instead_of_joining():
    doc = capture(); doc["results"][r.RELEASE]["value"]["release"]["work_item_id"] = 43
    with pytest.raises(r.ReconstructionError, match="item or revision mismatch"):
        r.reconstruct(doc)
    doc = capture(); doc["results"][r.LEASES]["arguments"]["item_id"] = 43
    with pytest.raises(r.ReconstructionError, match="arguments"):
        r.reconstruct(doc)


def test_supplied_capture_cannot_promote_itself_to_authenticated_owner_provenance():
    doc = capture(); doc["source_mode"] = "live-owner-reads"
    report = r.reconstruct(doc)
    assert report["source_mode"] == "supplied-capture"
    assert "not authenticated" in report["assurance"]


class Client:
    def __init__(self, doc, write=None):
        self.doc, self.write, self.invoked = doc, write, []

    async def catalog(self):
        return dict(revision="catalog_demo", operations=[dict(name=o, repo_scoped=True,
            execution_semantics="write" if o == self.write else "read") for o in r.READ_OPS])

    async def invoke(self, operation, arguments, *, repo_id=None):
        self.invoked.append((operation, arguments, repo_id))
        return deepcopy(self.doc["results"][operation]["value"])


def test_live_collection_only_invokes_the_explicit_read_allowlist_and_owner_scope():
    client = Client(capture()); authority = Authority(client, lambda: True, r.READ_OPS)
    try:
        report = r.reconstruct(r.collect(authority, "demo", "effect_demo"), live=True)
    finally:
        authority.loop.close()
    assert {o for o, _, _ in client.invoked} == r.READ_OPS
    assert all(repo == "demo" for _, _, repo in client.invoked)
    assert report["source_mode"] == "live-owner-reads"
    assert FRONT_PAGE_READS == frozenset({"work.project.context", "work.read.handoff", "work.read.context-candidates"})


def test_catalog_write_semantics_are_refused_before_invocation_and_show_missing_receipt():
    client = Client(capture(), write=r.EFFECT); authority = Authority(client, lambda: True, r.READ_OPS)
    try:
        report = r.reconstruct(r.collect(authority, "demo", "effect_demo"), live=True)
    finally:
        authority.loop.close()
    assert client.invoked == []
    assert set(report["missing"]) == set(r.LINKS)
    assert "unavailable" in report["assurance"]


def test_transport_exception_body_is_not_emitted_in_the_projection():
    class Down:
        def catalog(self):
            raise ConnectionError("a credential-bearing error must not escape")
    report = r.reconstruct(r.collect(Down(), "demo", "effect_demo"), live=True)
    assert "credential-bearing" not in json.dumps(report)
    assert report["status"] == "incomplete"


def test_cli_snapshot_is_read_only_and_cannot_self_assert_live_provenance(tmp_path, capsys):
    path = tmp_path / "capture.json"; doc = capture(); doc["source_mode"] = "live-owner-reads"
    path.write_text(json.dumps(doc)); before = path.read_bytes()
    assert main(["reconstruct", "--snapshot", str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert "not authenticated" in report["assurance"]
    assert path.read_bytes() == before


def test_cli_refusal_has_no_partial_output(tmp_path, capsys):
    path = tmp_path / "capture.json"; doc = capture()
    doc["results"]["work.effect.accept-v1"] = {}
    path.write_text(json.dumps(doc))
    assert main(["reconstruct", "--snapshot", str(path)]) == 2
    output = capsys.readouterr()
    assert not output.out and "refused" in output.err


def test_observed_response_without_an_intent_is_malformed_not_missing():
    doc = capture(); doc["results"][r.EFFECT]["value"]["intent"] = None
    with pytest.raises(r.ReconstructionError, match="malformed owner intent"):
        r.reconstruct(doc)


def test_duplicate_capture_fields_are_refused_before_any_output(tmp_path, capsys):
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(capture()).replace('"intent_revision": 1', '"intent_revision": 2, "intent_revision": 1'))
    assert main(["reconstruct", "--snapshot", str(path)]) == 2
    output = capsys.readouterr()
    assert not output.out and "refused" in output.err
