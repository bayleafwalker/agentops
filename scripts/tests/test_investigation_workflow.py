from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import investigation_workflow as iw


class InvestigationWorkflowAdversarialTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.record = self.base / "INV-1"
        self.source = self.base / "source"
        self.source.mkdir()
        self.hypotheses = [
            {"id": "configured", "statement": "The expected setting is present.", "prior": 0.5},
            {"id": "missing", "statement": "The expected setting is absent.", "prior": 0.5},
        ]
        iw.initialize(self.record, title="Configuration check", hypotheses=self.hypotheses)

    def tearDown(self):
        self.temporary.cleanup()

    def probe(self, *, probe_id="config", implementation=None, likelihoods=None, risk="low", cost=0.1):
        if implementation is None:
            implementation = {"kind": "text_contains", "path": "service.conf", "literal": "enabled=true"}
        if likelihoods is None:
            likelihoods = {
                "configured": {"present": 0.99, "absent": 0.01, "missing": 0.0},
                "missing": {"present": 0.01, "absent": 0.99, "missing": 0.0},
            }
        return {
            "id": probe_id,
            "statement": "Check whether the expected setting is present.",
            "risk": risk,
            "cost": cost,
            "implementation": implementation,
            "likelihoods": likelihoods,
        }

    def add_and_select(self, probe=None):
        iw.add_probe(self.record, probe or self.probe())
        return iw.select_next(self.record)

    def test_01_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(iw.InvestigationError):
            iw._loads('{"prior":0.5,"prior":0.9}', "test")

    def test_02_hypothesis_priors_must_sum_to_one(self):
        with self.assertRaises(iw.InvestigationError):
            iw._validate_hypotheses([
                {"id": "a", "statement": "A", "prior": 0.4},
                {"id": "b", "statement": "B", "prior": 0.4},
            ])

    def test_03_duplicate_hypothesis_ids_are_rejected(self):
        with self.assertRaises(iw.InvestigationError):
            iw._validate_hypotheses([
                {"id": "same", "statement": "A", "prior": 0.5},
                {"id": "same", "statement": "B", "prior": 0.5},
            ])

    def test_04_probe_path_traversal_is_rejected_before_registration(self):
        probe = self.probe(implementation={"kind": "file_exists", "path": "../secret"})
        with self.assertRaises(iw.InvestigationError):
            iw.add_probe(self.record, probe)

    def test_05_symlink_probe_target_is_refused(self):
        outside = self.base / "private.txt"
        outside.write_text("enabled=true", encoding="utf-8")
        (self.source / "service.conf").symlink_to(outside)
        self.add_and_select()
        with self.assertRaises(iw.InvestigationError):
            iw.execute_selected(self.record, self.source)

    def test_06_shell_and_unknown_probe_implementations_are_refused(self):
        probe = self.probe(implementation={
            "kind": "shell", "command": "cat private.txt", "effects": "read_only",
        })
        with self.assertRaises(iw.InvestigationError):
            iw.add_probe(self.record, probe)

    def test_07_every_hypothesis_and_outcome_needs_a_prediction(self):
        probe = self.probe()
        del probe["likelihoods"]["missing"]
        with self.assertRaises(iw.InvestigationError):
            iw.add_probe(self.record, probe)

    def test_08_partial_event_line_is_not_silently_discarded(self):
        self.add_and_select()
        with (self.record / iw.EVENTS).open("ab") as stream:
            stream.write(b'{"seq":')
        with self.assertRaisesRegex(iw.InvestigationError, "partial trailing line"):
            iw.load_state(self.record)

    def test_09_event_tampering_breaks_hash_chain(self):
        self.add_and_select()
        path = self.record / iw.EVENTS
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["data"]["title"] = "Changed after registration"
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(iw.InvestigationError, "digest mismatch"):
            iw.load_state(self.record)

    def test_10_selector_chooses_lowest_risk_discriminating_probe(self):
        file_probe = self.probe(probe_id="file", cost=0.1)
        risky_probe = self.probe(probe_id="risky", risk="high", cost=0.0)
        iw.add_probe(self.record, file_probe)
        iw.add_probe(self.record, risky_probe)
        selected = iw.select_next(self.record)
        self.assertEqual(selected["probe_id"], "file")
        self.assertGreater(selected["information_gain_bits"], 0)

    def test_11_replay_uses_recorded_evidence_without_rerunning_probe(self):
        (self.source / "service.conf").write_text("enabled=true\n", encoding="utf-8")
        self.add_and_select()
        result = iw.execute_selected(self.record, self.source)
        before = iw.load_state(self.record)["posterior"]
        (self.source / "service.conf").write_text("enabled=false\n", encoding="utf-8")
        replayed = iw.load_state(self.record)
        self.assertEqual(result["outcome"], "present")
        self.assertEqual(replayed["posterior"], before)
        self.assertEqual(len(replayed["observations"]), 1)

    def test_12_probe_predictions_cannot_be_replaced_after_registration(self):
        self.add_and_select()
        (self.source / "service.conf").write_text("enabled=true\n", encoding="utf-8")
        iw.execute_selected(self.record, self.source)
        with self.assertRaisesRegex(iw.InvestigationError, "already registered"):
            iw.add_probe(self.record, self.probe())

    def test_13_unpredicted_external_result_preserves_uncertainty(self):
        external = self.probe(
            implementation={
                "kind": "external_observation", "outcomes": ["yes", "no", "surprise"],
            },
            likelihoods={
                "configured": {"yes": 1, "no": 0, "surprise": 0},
                "missing": {"yes": 0, "no": 1, "surprise": 0},
            },
        )
        iw.add_probe(self.record, external)
        iw.select_next(self.record)
        with self.assertRaisesRegex(iw.InvestigationError, "absolute host paths"):
            iw.record_external_observation(
                self.record, outcome="surprise", evidence_ref="/tmp/private.txt",
                evidence_digest="sha256:" + "a" * 64, collector="native-runtime",
            )
        iw.record_external_observation(
            self.record, outcome="surprise", evidence_ref="evidence/observation.json",
            evidence_digest="sha256:" + "a" * 64, collector="native-runtime",
        )
        state = iw.load_state(self.record)
        self.assertEqual(state["posterior"], {"configured": 0.5, "missing": 0.5})
        self.assertEqual(len(state["surprises"]), 1)
        self.assertEqual(iw.build_report(self.record)["conclusion"], "insufficient_evidence")

    def test_14_interrupted_probe_cannot_be_automatically_retried(self):
        self.source.joinpath("service.conf").write_text("enabled=true\n", encoding="utf-8")
        self.add_and_select()
        iw._append(self.record, "probe_started", {
            "probe_id": "config", "started_at": iw._now(),
            "runner": iw.COLLECTOR, "effects": "read_only",
        })
        with self.assertRaisesRegex(iw.InvestigationError, "interrupted"):
            iw.execute_selected(self.record, self.source)
        iw.resolve_interrupted_probe(self.record, "process_exit")
        state = iw.load_state(self.record)
        self.assertIsNone(state["active"])
        self.assertIn("config", state["completed"])
        with self.assertRaisesRegex(iw.InvestigationError, "select a safe probe"):
            iw.execute_selected(self.record, self.source)


class InvestigationEvaluationAndIntegrationTests(unittest.TestCase):
    def test_synthetic_dataset_replays_with_expected_probe_and_conclusion(self):
        dataset_path = Path(__file__).parent / "fixtures/investigation/synthetic-known-cases.v1.json"
        result = iw.evaluate_dataset(iw._read_json_file(dataset_path))
        self.assertEqual(result["qualification"], "offline_dataset_replay")
        self.assertEqual(result["case_count"], 1)
        self.assertEqual(result["top1_accuracy"], 1.0)
        self.assertEqual(result["probe_selection_match"], 1.0)
        self.assertEqual(result["cases"][0]["prediction"], "feature_disabled")

    def test_frozen_retrospective_incident_set_replays_against_source_pins(self):
        dataset_path = Path(__file__).parent / "fixtures/investigation/retrospective-known-incidents.v1.json"
        dataset = iw._read_json_file(dataset_path)
        result = iw.evaluate_dataset(dataset)
        self.assertEqual(result["dataset_digest"],
                         "sha256:e745c889020d5f3dfa8aea68c92b1c540ba0a4bc1e92b3c9c28a62a14c310a3c")
        self.assertEqual(result["qualification"], "offline_dataset_replay")
        self.assertEqual(result["case_count"], 3)
        self.assertEqual(result["top1_accuracy"], 1.0)
        self.assertEqual(result["probe_selection_match"], 1.0)
        self.assertAlmostEqual(result["mean_brier_score"], 0.06842882713079586)
        self.assertTrue(all(row["correct"] for row in result["cases"]))
        self.assertTrue(all(row["selected_first_probe"] == row["expected_first_probe"]
                            for row in result["cases"]))
        repo = Path(__file__).parents[2]
        completed = subprocess.run(
            [sys.executable, "scripts/investigation_workflow.py", "evaluate",
             "--dataset", str(dataset_path), "--expected-digest", result["dataset_digest"]],
            cwd=repo, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_vuoro_export_emits_existing_evidence_payloads_for_registered_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            record = base / "INV-VUORO"
            hypotheses = [
                {"id": "a", "statement": "A is true.", "prior": 0.5},
                {"id": "b", "statement": "B is true.", "prior": 0.5},
            ]
            iw.initialize(record, title="Vuoro payload fixture", hypotheses=hypotheses,
                          vuoro_run_id="run_fixture", artifact_ref="_artifacts/investigations/fixture")
            probe = {
                "id": "observe", "statement": "Record a synthetic external finding.",
                "risk": "low", "cost": 0.05,
                "implementation": {
                    "kind": "external_observation", "outcomes": ["yes", "no"],
                },
                "likelihoods": {
                    "a": {"yes": 0.99, "no": 0.01},
                    "b": {"yes": 0.01, "no": 0.99},
                },
            }
            iw.add_probe(record, probe)
            iw.select_next(record)
            iw.record_external_observation(
                record, outcome="yes", evidence_ref="evidence/synthetic.json",
                evidence_digest="sha256:" + "c" * 64, collector="native-runtime",
            )
            iw.write_report(record)
            payloads = iw.vuoro_evidence_payloads(record)
            self.assertEqual([item["kind"] for item in payloads],
                             ["investigation_observation", "investigation_report"])
            self.assertTrue(all(item["run_id"] == "run_fixture" for item in payloads))
            self.assertTrue(all(item["digest"].startswith("sha256:") for item in payloads))
            self.assertTrue(all(8 <= len(item["idempotency_key"]) <= 128 for item in payloads))
            self.assertTrue(all(set(item["validity"]) == {"basis", "valid_from", "component_digests"}
                                for item in payloads))
            self.assertTrue(all(item["provenance"]["event_head"].startswith("sha256:")
                                for item in payloads))

    def test_schema_documents_are_valid_json(self):
        root = Path(__file__).parents[2] / "schemas"
        for name in (
            "investigation-probe.v1.schema.json",
            "investigation-event.v1.schema.json",
            "investigation-evaluation.v1.schema.json",
        ):
            with self.subTest(name=name):
                iw._loads((root / name).read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
