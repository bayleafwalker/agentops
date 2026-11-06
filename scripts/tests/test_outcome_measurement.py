"""outcome_measurement preflight: each gate is paired with a fixture that passes it."""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SCRIPT = HERE.parent / "outcome_measurement.py"
TEMPLATE = (REPO / "docs/plans/agentops/2026-10-22-opportunistic-follow-through"
            / "outcome-observations.template.json")
_spec = importlib.util.spec_from_file_location("outcome_measurement", SCRIPT)
om = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["outcome_measurement"] = om
_spec.loader.exec_module(om)

REG = "2026-11-01T00:00:00Z"
OBS = "2026-11-03T00:00:00Z"
CASES = ("c1", "c2")
REV = {"baseline": "rev-base", "candidate": "rev-cand"}
BURDEN_KEYS = ("maintenance_minutes", "reexplanation_minutes", "review_minutes", "failed_attempts")


def _template() -> dict:
    return json.loads(TEMPLATE.read_text())


def _case(template: dict, case_id: str, arm: str, *, passed: bool, burden: float,
          defects: int, cost: float, currency: str = "EUR") -> dict:
    case = copy.deepcopy(template["case_template"])
    case["case_id"], case["arm_id"] = case_id, arm
    case["observed_at"] = OBS
    case["artifact_revision_ref"] = REV[arm]
    case["run_ids"] = [f"run-{arm}-{case_id}"]
    case["internal_acceptance"] = {
        "disposition": "accepted", "owner_decision_ref": "decision-1", "observed_at": OBS,
    }
    case["independent_requirements"].update({
        "status": "pass" if passed else "fail",
        "criterion_refs": ["crit"], "oracle_refs": ["oracle"], "oracle_origin": "owner-fixture",
        "independence_basis": "external", "evaluator_ref": "evaluator",
        "evaluated_revision_ref": REV[arm], "evidence_refs": ["ev"],
    })
    case["actual_use"].update({
        "status": "observed", "consumer_ref": "consumer", "window_start": OBS,
        "window_end": "2026-11-04T00:00:00Z", "evidence_refs": ["use-ev"],
    })
    case["escaped_defects"].update({
        "observed_count": defects, "detection_method_ref": "method", "window_start": OBS,
        "window_end": "2026-11-04T00:00:00Z", "coverage_description": "all", "evidence_refs": ["d-ev"],
    })
    for key in BURDEN_KEYS:
        case["burden"][key] = {"value": burden, "source_refs": ["b-ev"]}
    case["burden"]["direct_cost"] = {"amount": cost, "currency": currency, "source_refs": ["c-ev"]}
    return case


def _prereg(*, candidate_better: bool = True) -> dict:
    doc = _template()
    doc.update({
        "population_ref": "pop", "requirements_ref": "req", "evaluation_policy_ref": "pol",
        "population_registered_at": REG,
        "observation_window": {"start": "2026-11-02T00:00:00Z", "end": "2026-11-30T00:00:00Z"},
        "expected_case_ids": list(CASES),
    })
    plan = doc["comparison"]
    plan.update({"cohort_id": "software", "registered_at": REG, "use_required": True,
                 "threshold_owner_ref": "owner", "claim_rule_ref": "rule"})
    plan["arms"] = {arm: {"experiment_record_ref": f"exp-{arm}", "revision_ref": REV[arm]}
                    for arm in om.ARMS}
    thresholds = [("useful_verified_rate", "increase", 0.5)]
    thresholds += [(m, "decrease", 1) for m in sorted(om.REQUIRED_CLAIM_METRICS)
                   if m != "useful_verified_rate"]
    plan["thresholds"] = [{"metric": m, "direction": d, "amount": a,
                           "owner_ref": "owner", "registered_at": REG} for m, d, a in thresholds]
    cases = []
    for case_id in CASES:
        cases.append(_case(doc, case_id, "baseline", passed=False, burden=10, defects=2, cost=10))
        cases.append(_case(doc, case_id, "candidate", passed=candidate_better, burden=5 if candidate_better else 10,
                           defects=0 if candidate_better else 2, cost=5 if candidate_better else 10))
    doc["cases"] = cases
    return doc


def _write(tmp: Path, doc: dict) -> Path:
    path = tmp / "companion.json"
    path.write_text(json.dumps(doc))
    return path


class OutcomeMeasurementTests(unittest.TestCase):
    def test_blank_template_is_not_preregistered(self):
        report = om.assess(_template())
        self.assertEqual(report["state"], "not-preregistered")
        self.assertFalse(report["benefit_claim_allowed"])
        self.assertFalse(report["outcome_improvement_claim_allowed"])

    def test_main_blank_template_exits_2(self):
        self.assertEqual(om.main([str(TEMPLATE)]), 2)

    def test_main_unreadable_input_exits_1(self):
        self.assertEqual(om.main(["/nonexistent/companion.json"]), 1)

    def test_thresholds_met(self):
        report = om.assess(_prereg())
        self.assertEqual(report["state"], "thresholds-met")
        self.assertTrue(report["benefit_claim_allowed"])
        self.assertTrue(report["outcome_improvement_claim_allowed"])
        self.assertTrue(all(t["status"] == "passed" for t in report["threshold_results"]))

    def test_main_thresholds_met_exits_0(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(om.main([str(_write(Path(tmp), _prereg())), "--json"]), 0)

    def test_thresholds_not_met_is_valid_and_exits_0(self):
        import tempfile
        doc = _prereg(candidate_better=False)
        report = om.assess(doc)
        self.assertEqual(report["state"], "thresholds-not-met")
        self.assertFalse(report["benefit_claim_allowed"])
        self.assertFalse(report["outcome_improvement_claim_allowed"])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(om.main([str(_write(Path(tmp), doc))]), 0)

    def test_missing_expected_case_is_not_preregistered(self):
        import tempfile
        doc = _prereg()
        doc["cases"] = [c for c in doc["cases"] if not (c["arm_id"] == "candidate" and c["case_id"] == "c2")]
        report = om.assess(doc)
        self.assertEqual(report["arms"]["candidate"]["missing_case_ids"], ["c2"])
        self.assertFalse(report["benefit_claim_allowed"])
        self.assertFalse(report["outcome_improvement_claim_allowed"])
        # A missing case pair fails full_observation_dates, so scope_ready is false.
        self.assertEqual(report["state"], "not-preregistered")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(om.main([str(_write(Path(tmp), doc))]), 2)

    def test_missing_burden_value_is_incomplete(self):
        doc = _prereg()
        doc["cases"][3]["burden"]["review_minutes"]["value"] = None
        report = om.assess(doc)
        self.assertEqual(report["state"], "incomplete")
        self.assertFalse(report["benefit_claim_allowed"])

    def test_mixed_currencies_block_claim(self):
        doc = _prereg()
        for case in doc["cases"]:
            if case["arm_id"] == "candidate":
                case["burden"]["direct_cost"]["currency"] = "USD"
        report = om.assess(doc)
        cost = next(t for t in report["threshold_results"] if t["metric"] == "direct_cost_per_case")
        self.assertEqual(cost["status"], "incomplete")
        self.assertEqual((cost["baseline_currency"], cost["candidate_currency"]), ("EUR", "USD"))
        self.assertEqual(report["state"], "incomplete")
        self.assertFalse(report["benefit_claim_allowed"])

    def test_mixed_currencies_within_one_arm_block_claim(self):
        doc = _prereg()
        doc["cases"][0]["burden"]["direct_cost"]["currency"] = "USD"
        report = om.assess(doc)
        self.assertFalse(report["benefit_claim_allowed"])
        self.assertEqual(report["state"], "incomplete")

    def test_threshold_after_comparison_registration_is_rejected(self):
        doc = _prereg()
        doc["comparison"]["thresholds"][0]["registered_at"] = "2026-11-02T00:00:00Z"
        with self.assertRaisesRegex(om.OutcomeMeasurementError, "follows comparison preregistration"):
            om.assess(doc)

    def test_registration_after_first_observation_is_not_preregistered(self):
        doc = _prereg()
        late = "2026-11-03T12:00:00Z"
        doc["comparison"]["registered_at"] = late
        for threshold in doc["comparison"]["thresholds"]:
            threshold["registered_at"] = late
        report = om.assess(doc)
        self.assertEqual(report["state"], "not-preregistered")
        self.assertFalse(report["benefit_claim_allowed"])

    def test_unexpected_case_id_raises(self):
        doc = _prereg()
        doc["cases"][0]["case_id"] = "c9"
        with self.assertRaisesRegex(om.OutcomeMeasurementError, "unexpected case id"):
            om.assess(doc)

    def test_duplicate_case_observation_raises(self):
        doc = _prereg()
        doc["cases"].append(copy.deepcopy(doc["cases"][0]))
        with self.assertRaisesRegex(om.OutcomeMeasurementError, "duplicate case observation"):
            om.assess(doc)

    def test_main_invalid_shape_exits_1(self):
        import tempfile
        doc = _prereg()
        doc["cases"].append(copy.deepcopy(doc["cases"][0]))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(om.main([str(_write(Path(tmp), doc))]), 1)

    def test_unknown_required_check_blocks_claim(self):
        doc = _prereg()
        doc["cases"][3]["independent_requirements"]["unknown_required_checks"] = ["perf"]
        report = om.assess(doc)
        self.assertFalse(report["benefit_claim_allowed"])
        self.assertFalse(report["outcome_improvement_claim_allowed"])
        self.assertEqual(report["state"], "incomplete")

    def test_unknown_use_blocks_useful_verified_claim(self):
        doc = _prereg()
        use = doc["cases"][3]["actual_use"]
        use.update({"status": "unknown", "consumer_ref": None})
        report = om.assess(doc)
        self.assertFalse(report["outcome_improvement_claim_allowed"])
        self.assertFalse(report["benefit_claim_allowed"])

    def test_null_cost_is_not_converted_to_zero(self):
        doc = _prereg()
        doc["cases"][3]["burden"]["direct_cost"]["amount"] = None
        report = om.assess(doc)
        self.assertFalse(report["benefit_claim_allowed"])
        self.assertEqual(report["state"], "incomplete")


if __name__ == "__main__":
    unittest.main()
