"""Portable P1 presentation keeps exact links but drops private source bytes."""

from copy import deepcopy
import hashlib
import json

import pytest

from operator_projection import reconstruction as p1
from operator_projection import portable_acceptance as portable
from test_reconstruction import capture, intent, protected_capture


def test_complete_protected_p1_has_same_links_and_exact_identity_without_authority_claim():
    report = p1.reconstruct(protected_capture())
    dto = portable.present(report)
    text = portable.render_text(report)
    assert dto["schema"] == portable.SCHEMA
    assert dto["status"] == report["status"] == "complete"
    assert dto["status_scope"] == "p1-link-consistency"
    assert list(dto["links"]) == list(p1.LINKS)
    assert {key: row["status"] for key, row in dto["links"].items()} == {
        key: row["status"] for key, row in report["links"].items()}
    assert dto["links"]["artifact"]["facts"]["canonical_intent_digest"] == report["links"]["artifact"]["value"]["digest"]
    assert dto["links"]["verification_evidence"]["facts"]["evidence_digest"] == report["links"]["verification_evidence"]["value"]["evidence_digest"]
    assert dto["links"]["acceptance"]["facts"]["accepting_identity"] == "unknown"
    assert set(dto["provenance"].values()) == {"supplied-capture", "unknown"}
    assert dto["authorizes_effects"] is False and "authorizes no effect" in text
    assert "not a terminal acceptance outcome" in text
    assert [s["operation"] for s in dto["sources"]] == [s["operation"] for s in report["sources"]]


def test_missing_receipt_and_changed_release_preserve_p1_missing_and_conflicts():
    doc = protected_capture()
    intent(doc)["application"] = None
    report = p1.reconstruct(doc)
    dto = portable.present(report)
    assert dto["missing"] == report["missing"] == ["effect_receipt"]
    assert "effect_receipt: missing" in portable.render_text(report)
    doc = protected_capture()
    doc["results"][p1.RELEASE]["value"]["release"]["release_digest"] = "0" * 64
    report = p1.reconstruct(doc)
    dto = portable.present(report)
    assert dto["status"] == "conflict"
    for key in ("release_intent_binding", "verification_evidence", "acceptance", "effect_receipt"):
        assert dto["links"][key] == {"status": "conflict"}


def test_raw_private_owner_changes_and_source_hashes_do_not_change_output():
    original = protected_capture()
    changed = deepcopy(original)
    marker = "PRIVATE-SENTINEL-123456789"
    changed["results"][p1.RELEASE]["value"]["release"]["acceptance_contract"]["secret"] = marker
    changed["results"][p1.LEASES]["value"]["outcome_reports"] = [{"private": marker}]
    changed["results"][p1.EFFECT]["value"]["intent"]["acceptance"]["acceptor_principal"] = marker
    changed["results"][p1.EFFECT]["value"]["intent"]["acceptance"]["verification"]["verifier_principal"] = marker
    changed["results"][p1.EFFECT]["value"]["intent"]["application"]["pr_url"] = "https://example.test/" + marker
    first, second = p1.reconstruct(original), p1.reconstruct(changed)
    assert first["status"] == second["status"] == "complete"
    assert first["sources"][0]["result_digest"] != second["sources"][0]["result_digest"]
    assert portable.present(first) == portable.present(second)
    output = json.dumps(portable.present(second), sort_keys=True) + portable.render_text(second)
    assert marker not in output
    assert hashlib.sha256(marker.encode()).hexdigest() not in output
    assert second["sources"][0]["result_digest"] not in output
    for forbidden in ("acceptance_contract", "current_lease", "outcome_reports", "pr_url", "result_digest", "verifier_principal"):
        assert forbidden not in output


def test_supplied_or_claimed_live_report_still_has_unknown_authority():
    report = p1.reconstruct(capture())
    report["source_mode"] = "live-owner-reads"
    dto = portable.present(report)
    assert dto["provenance"]["reported_source_mode"] == "live-owner-reads"
    assert dto["provenance"]["owner_authentication"] == "unknown"
    assert dto["provenance"]["owner_currentness"] == "unknown"
    assert dto["provenance"]["current_authorization"] == "unknown"


@pytest.mark.parametrize("mutation", [
    lambda r: r["links"]["artifact"].update(value={"digest": "private", "domain": "sprintctl-effect-intent/v1"}),
    lambda r: r["links"]["intent"].update(status="secret"),
    lambda r: r.update(missing=["effect_receipt"]),
    lambda r: r["sources"][0].update(observed_at="2026-10-10X12:00:00Z"),
    lambda r: r["sources"][0].update(observed_at="2026-10-10T12:00:00+03:00"),
    lambda r: r["sources"][0].update(operation="private.operation"),
    lambda r: r.update(intent_id="effect_demo\nPRIVATE-SENTINEL"),
    lambda r: r["links"]["acceptance"]["value"].update(canonical_intent_digest="PRIVATE-SENTINEL"),
])
def test_malformed_p1_shapes_refuse_without_echo(mutation):
    report = p1.reconstruct(protected_capture())
    mutation(report)
    with pytest.raises(p1.ReconstructionError, match="^unsupported acceptance presentation input$"):
        portable.present(report)


def test_source_time_is_strict_utc_and_not_owner_event_time():
    report = p1.reconstruct(capture())
    report["sources"][0]["observed_at"] = "2026-10-10T12:00:00+00:00"
    dto = portable.present(report)
    assert dto["sources"][0]["observed_at"] == "2026-10-10T12:00:00Z"
    report["sources"][0]["observed_at"] = "2026-02-30T12:00:00Z"
    with pytest.raises(p1.ReconstructionError):
        portable.present(report)


@pytest.mark.parametrize("link,field,value", [
    ("intent", "revision", 10**1000),
    ("intent", "revision", portable.OWNER_INT_MAX + 1),
    ("intent", "item_id", portable.OWNER_BIGINT_MAX + 1),
    ("acceptance", "intent_revision", 10**1000),
])
def test_owner_storage_domain_bounds_refuse_oversized_report_numbers(link, field, value):
    # These mutate a genuine P1 complete report; a presentation may not render
    # arbitrary precision numbers that cannot exist in the owner's PG columns.
    report = p1.reconstruct(protected_capture())
    report["links"][link]["value"][field] = value
    assert report["status"] == "complete"
    with pytest.raises(p1.ReconstructionError, match="^unsupported acceptance presentation input$"):
        portable.present(report)


@pytest.mark.parametrize("link,field,value", [
    ("acceptance", "intent_revision", 2),
    ("acceptance", "canonical_intent_digest", "0" * 64),
    ("release_intent_binding", "release_digest", "0" * 64),
    ("release_intent_binding", "intent_revision", 2),
    ("release_intent_binding", "intent_id", "other_intent"),
])
def test_safe_observed_facts_cannot_contradict_each_other_in_complete_p1_report(link, field, value):
    report = p1.reconstruct(protected_capture())
    report["links"][link]["value"][field] = value
    assert report["status"] == "complete"
    with pytest.raises(p1.ReconstructionError, match="^unsupported acceptance presentation input$"):
        portable.present(report)
