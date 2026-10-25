"""Retrospective governance is append-only, advisory, and restart-reconstructable."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared_execution.governance import (  # noqa: E402
    ATTESTATION_EVENT,
    INTENT_EVENT,
    InterpretationGovernance,
)
from shared_execution.runtime import Store  # noqa: E402


class InterpretationGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name)
        self.addCleanup(self._close_store)
        self.governance = InterpretationGovernance(self.store)

    def _close_store(self):
        if self.store:
            self.store.close()
            self.store = None

    @staticmethod
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def result(self, revision_id: str, *, depends_on=(), subject_ref="task:one"):
        source = "result-source:" + revision_id
        return self.governance.record_result_revision(
            revision_id, subject_ref=subject_ref, source_ref=source,
            source_sha256=self.digest(source), evidence_refs=["evidence:" + revision_id],
            depends_on=depends_on,
            provenance={"producer": "synthetic-fixture", "captured_from": source})

    def interpretation(self, revision_id: str, result_revision_ref: str, *, depends_on=(),
                       conclusion=None, subject_ref="task:one"):
        source = "interpretation-source:" + revision_id
        return self.governance.record_interpretation_revision(
            revision_id, subject_ref=subject_ref, result_revision_ref=result_revision_ref,
            conclusion=conclusion or "Conclusion for " + revision_id,
            source_ref=source, source_sha256=self.digest(source),
            evidence_refs=["evidence:" + revision_id], depends_on=depends_on,
            provenance={"reviewer": "synthetic-review", "basis": result_revision_ref})

    def test_revisions_are_immutable_idempotent_and_preserve_corrections(self):
        first = self.result("r1")
        before = len(self.store.events())
        self.assertEqual(self.result("r1"), first)
        self.assertEqual(len(self.store.events()), before)
        with self.assertRaisesRegex(ValueError, "immutable revision conflict"):
            self.governance.record_result_revision(
                "r1", subject_ref="task:one", source_ref="result-source:changed",
                source_sha256=self.digest("changed"), evidence_refs=["evidence:new"],
                provenance={"producer": "synthetic-fixture"})

        original = self.interpretation("i1", "result:r1", conclusion="Original interpretation")
        correction = self.interpretation("i2", "result:r1", conclusion="Corrected interpretation")
        self.assertNotEqual(original["revision_ref"], correction["revision_ref"])
        revisions = self.governance.revisions()
        self.assertEqual(revisions["interpretation:i1"]["conclusion"], "Original interpretation")
        self.assertEqual(revisions["interpretation:i2"]["conclusion"], "Corrected interpretation")

    def test_revision_references_and_dependencies_must_be_known_and_typed(self):
        with self.assertRaisesRegex(ValueError, "unknown dependency"):
            self.result("r0", depends_on=["interpretation:missing"])
        self.result("r1")
        with self.assertRaisesRegex(ValueError, "recorded result revision"):
            self.interpretation("i1", "interpretation:wrong-kind")
        with self.assertRaisesRegex(ValueError, "recorded result revision"):
            self.interpretation("i1", "result:missing")

    def test_revision_replay_rejects_conflicts_wrong_event_kind_and_schema(self):
        original = self.result("r1")
        self.store.event("governance.result_revision_recorded", "task:one",
                         schema_version="interpretation-governance/v1", revision=original)
        self.assertEqual(self.governance.revisions()["result:r1"], original)
        conflict = dict(original, source_ref="result-source:rewritten",
                        source_sha256=self.digest("rewritten"))
        self.store.event("governance.result_revision_recorded", "task:one",
                         schema_version="interpretation-governance/v1", revision=conflict)
        with self.assertRaisesRegex(ValueError, "immutable revision conflict"):
            self.governance.revisions()

    def test_revision_replay_rejects_wrong_inner_kind_and_schema(self):
        result = self.result("r1")
        with self.assertRaisesRegex(ValueError, "revision kind/event mismatch"):
            self.store.event("governance.result_revision_recorded", "task:one",
                             schema_version="interpretation-governance/v1",
                             revision=dict(result, kind="interpretation", revision_ref="interpretation:i1"))
            self.governance.revisions()

        self._close_store()
        self.store = Store(Path(self.temp.name) / "other")
        self.governance = InterpretationGovernance(self.store)
        result = self.result("r1")
        self.store.event("governance.result_revision_recorded", "task:one",
                         schema_version="interpretation-governance/v999", revision=result)
        with self.assertRaisesRegex(ValueError, "invalid revision event schema"):
            self.governance.revisions()

    def test_dispute_emits_transitive_intent_with_original_evidence_and_no_gate(self):
        self.result("r0")
        self.interpretation("i0", "result:r0")
        self.result("r1", depends_on=["interpretation:i0"])
        self.interpretation("i1", "result:r1")
        self.result("r2", depends_on=["interpretation:i1"])
        self.interpretation("i2", "result:r2")
        self.result("unrelated-result", subject_ref="task:unrelated")
        self.interpretation("unrelated-interpretation", "result:unrelated-result",
                            subject_ref="task:unrelated")

        self.store.save({"id": "unrelated-work"}, "PLANNED")
        disputed = self.governance.attest_disposition(
            "att-dispute", subject_ref="interpretation:i0", disposition="disputed",
            actor_ref="reviewer:two", evidence_refs=["evidence:counterexample"],
            note="Scenario evidence conflicts with the recorded conclusion.")
        intent = disputed["reconciliation_intent"]
        self.assertTrue(intent["advisory_only"])
        self.assertEqual(intent["disputed_revision_ref"], "interpretation:i0")
        self.assertEqual(set(intent["affected_revision_refs"]), {
            "interpretation:i0", "result:r1", "interpretation:i1", "result:r2", "interpretation:i2"})
        self.assertEqual(set(intent["reevaluate_interpretation_refs"]), {
            "interpretation:i0", "interpretation:i1", "interpretation:i2"})
        preserved = {item["revision_ref"]: item for item in intent["preserved_evidence"]}
        self.assertEqual(preserved["interpretation:i0"]["source_ref"], "interpretation-source:i0")
        self.assertEqual(preserved["interpretation:i0"]["evidence_refs"], ["evidence:i0"])
        self.assertEqual(self.governance.revisions()["interpretation:i0"]["conclusion"],
                         "Conclusion for i0")
        self.assertEqual(self.store.tasks()[0]["state"], "PLANNED")
        self.assertEqual(set(self.governance.revisions()).intersection({
            "interpretation:unrelated-interpretation"}), {"interpretation:unrelated-interpretation"})
        self.store.save({"id": "unrelated-work", "state": "PLANNED"}, "RUNNING")
        self.assertEqual(self.store.tasks()[0]["state"], "RUNNING")

    def test_dispositions_append_and_duplicate_disputes_deduplicate_intent(self):
        self.result("r1")
        self.interpretation("i1", "result:r1")
        self.interpretation("i2", "result:r1", conclusion="Replacement interpretation")
        subject = "interpretation:i1"
        for index, disposition in enumerate(("pending", "acknowledged", "ratified")):
            self.governance.attest_disposition(
                "att-" + str(index), subject_ref=subject, disposition=disposition,
                actor_ref="reviewer:one")
        superseded = self.governance.attest_disposition(
            "att-superseded", subject_ref=subject, disposition="superseded",
            actor_ref="reviewer:one", superseded_by_ref="interpretation:i2")
        self.assertEqual(superseded["superseded_by_ref"], "interpretation:i2")
        disputed = self.governance.attest_disposition(
            "att-dispute", subject_ref=subject, disposition="disputed", actor_ref="reviewer:two")
        intent = disputed["reconciliation_intent"]
        event_count = len(self.store.events())
        self.assertEqual(self.governance.attest_disposition(
            "att-dispute", subject_ref=subject, disposition="disputed", actor_ref="reviewer:two"),
            disputed)
        self.assertEqual(len(self.store.events()), event_count)

        second_attestation = self.governance.attest_disposition(
            "att-dispute-repeat", subject_ref=subject, disposition="disputed", actor_ref="reviewer:three")
        self.assertEqual(second_attestation["reconciliation_intent"]["intent_id"], intent["intent_id"])
        self.assertEqual(len(self.governance.reconciliation_intents()), 1)
        self.assertEqual([item["disposition"] for item in self.governance.attestations(subject)],
                         ["pending", "acknowledged", "ratified", "superseded", "disputed", "disputed"])
        with self.assertRaisesRegex(ValueError, "immutable attestation conflict"):
            self.governance.attest_disposition(
                "att-0", subject_ref=subject, disposition="acknowledged", actor_ref="reviewer:changed")

    def test_attestation_replay_accepts_exact_duplicate_but_rejects_conflicting_id(self):
        self.result("r1")
        self.interpretation("i1", "result:r1")
        attestation = self.governance.attest_disposition(
            "att-1", subject_ref="interpretation:i1", disposition="acknowledged",
            actor_ref="reviewer:one")
        self.store.event(ATTESTATION_EVENT, "task:one", schema_version="interpretation-governance/v1",
                         attestation=attestation, reconciliation_intent_id=None)
        self.assertEqual(self.governance.attestations(), [attestation])
        conflicting = dict(attestation, actor_ref="reviewer:forged")
        self.store.event(ATTESTATION_EVENT, "task:one", schema_version="interpretation-governance/v1",
                         attestation=conflicting, reconciliation_intent_id=None)
        with self.assertRaisesRegex(ValueError, "immutable attestation conflict"):
            self.governance.attestations()

    def test_superseded_disposition_requires_existing_same_kind_target(self):
        self.result("r1")
        self.result("r2")
        self.interpretation("i1", "result:r1")
        self.interpretation("i2", "result:r2")
        with self.assertRaisesRegex(ValueError, "superseded_by_ref"):
            self.governance.attest_disposition(
                "bad-no-target", subject_ref="interpretation:i1", disposition="superseded",
                actor_ref="reviewer:one")
        with self.assertRaisesRegex(ValueError, "same revision kind"):
            self.governance.attest_disposition(
                "bad-kind", subject_ref="interpretation:i1", disposition="superseded",
                actor_ref="reviewer:one", superseded_by_ref="result:r2")
        with self.assertRaisesRegex(ValueError, "cannot supersede itself"):
            self.governance.attest_disposition(
                "bad-self", subject_ref="interpretation:i1", disposition="superseded",
                actor_ref="reviewer:one", superseded_by_ref="interpretation:i1")

    def test_live_impact_query_finds_dependents_added_after_dispute_and_restart(self):
        self.result("r1")
        self.interpretation("i1", "result:r1")
        disputed = self.governance.attest_disposition(
            "att-dispute", subject_ref="interpretation:i1", disposition="disputed",
            actor_ref="reviewer:two")
        original_intent = disputed["reconciliation_intent"]
        self.assertEqual(original_intent["affected_revision_refs"], ["interpretation:i1"])

        self.result("r2", depends_on=["interpretation:i1"])
        self.interpretation("i2", "result:r2")
        self._close_store()
        self.store = Store(self.temp.name)
        self.governance = InterpretationGovernance(self.store)
        impact = self.governance.downstream_impacts("interpretation:i1")
        self.assertEqual(set(impact["affected_revision_refs"]), {
            "interpretation:i1", "result:r2", "interpretation:i2"})
        self.assertEqual(set(impact["reevaluate_interpretation_refs"]), {
            "interpretation:i1", "interpretation:i2"})
        self.assertEqual(self.governance.reconciliation_intents()[0], original_intent)

    def test_revisions_attestations_and_intents_reconstruct_after_restart(self):
        self.result("r1")
        self.interpretation("i1", "result:r1")
        first = self.governance.attest_disposition(
            "att-dispute", subject_ref="interpretation:i1", disposition="disputed",
            actor_ref="reviewer:two")
        intent_id = first["reconciliation_intent"]["intent_id"]
        self._close_store()
        self.store = Store(self.temp.name)
        self.governance = InterpretationGovernance(self.store)
        self.assertIn("result:r1", self.governance.revisions())
        self.assertIn("interpretation:i1", self.governance.revisions())
        event_count = len(self.store.events())
        duplicate = self.governance.attest_disposition(
            "att-dispute", subject_ref="interpretation:i1", disposition="disputed",
            actor_ref="reviewer:two")
        self.assertEqual(duplicate["reconciliation_intent"]["intent_id"], intent_id)
        self.assertEqual(len(self.store.events()), event_count)
        self.assertEqual(len([event for event in self.store.events()
                              if event["kind"] == INTENT_EVENT]), 1)
        self.assertEqual(len([event for event in self.store.events()
                              if event["kind"] == ATTESTATION_EVENT]), 1)


if __name__ == "__main__":
    unittest.main()
