"""validate_execution_placement: the repo matrix passes; each mutation is rejected."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "validate_execution_placement.py"
_spec = importlib.util.spec_from_file_location("validate_execution_placement", SCRIPT)
vp = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["validate_execution_placement"] = vp
_spec.loader.exec_module(vp)


def _matrix() -> dict:
    return json.loads(vp.DEFAULT_MATRIX.read_text())


def _first_official(doc: dict) -> dict:
    return next(s for s in doc["sources"] if s["kind"] == "official_docs")


class ExecutionPlacementTests(unittest.TestCase):
    def assertRejected(self, doc: dict, pattern: str) -> None:
        with self.assertRaisesRegex(vp.PlacementMatrixError, pattern):
            vp.validate(doc)
        # The same mutation must also fail through main() with exit 1.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "matrix.json"
            path.write_text(json.dumps(doc))
            self.assertEqual(vp.main([str(path)]), 1)

    def test_repo_matrix_is_valid_but_not_qualified(self):
        report = vp.validate(_matrix())
        self.assertTrue(report["valid"])
        self.assertEqual(report["qualification_status"], "source-mapped-not-qualified")
        self.assertEqual(report["scenarios_run"], 0)
        self.assertEqual(vp.main([]), 0)

    def test_placement_level_qualification_or_run_claim_rejected(self):
        for key, value in (("qualification_status", "qualified"), ("scenarios_run", 3)):
            doc = _matrix()
            doc["placements"][0][key] = value
            self.assertRejected(doc, "unrecognized fields")

    def test_non_https_source_ref_rejected(self):
        doc = _matrix()
        src = _first_official(doc)
        src["url"] = src["url"].replace("https://", "http://", 1)
        self.assertRejected(doc, "must use HTTPS")

    def test_non_allow_listed_host_rejected(self):
        doc = _matrix()
        _first_official(doc)["url"] = "https://example.com/docs/en/managed-agents/overview"
        self.assertRejected(doc, "outside the approved official documentation hosts")

    def test_lookalike_host_suffix_rejected(self):
        doc = _matrix()
        _first_official(doc)["url"] = "https://evilplatform.claude.com.example.net/x"
        self.assertRejected(doc, "outside the approved")

    def test_missing_reviewed_at_rejected(self):
        doc = _matrix()
        del doc["reviewed_at"]
        self.assertRejected(doc, "reviewed_at must be an ISO date")

    def test_missing_source_reviewed_at_rejected(self):
        doc = _matrix()
        del doc["sources"][0]["reviewed_at"]
        self.assertRejected(doc, r"sources\[0\]\.reviewed_at")

    def test_claiming_qualified_rejected(self):
        doc = _matrix()
        doc["qualification_status"] = "qualified"
        self.assertRejected(doc, "must remain source-mapped-not-qualified")

    def test_scenario_claiming_run_rejected(self):
        doc = _matrix()
        doc["qualification_scenarios"][0]["status"] = "passed"
        self.assertRejected(doc, "must remain not-run")

    def test_missing_required_scenario_rejected(self):
        doc = _matrix()
        doc["qualification_scenarios"] = [
            s for s in doc["qualification_scenarios"] if s["id"] != "failed-child"]
        self.assertRejected(doc, "qualification_scenarios must include")

    def test_unknown_source_ref_rejected(self):
        doc = _matrix()
        doc["placements"][0]["model_location"]["source_refs"] = ["no-such-source"]
        self.assertRejected(doc, "unknown source refs")

    def test_mutation_does_not_alter_original(self):
        doc = _matrix()
        before = copy.deepcopy(doc)
        vp.validate(doc)
        self.assertEqual(doc, before)


if __name__ == "__main__":
    unittest.main()
