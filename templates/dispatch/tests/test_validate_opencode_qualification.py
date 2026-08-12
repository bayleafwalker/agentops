from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates/dispatch/scripts/validate_opencode_qualification.py"


def _load_module(path: Path = SCRIPT, name: str = "validate_opencode_qualification"):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gate = _load_module()


def _corpus() -> dict[str, object]:
    return json.loads(gate.DEFAULT_CORPUS.read_text(encoding="utf-8"))


def _manifest() -> dict[str, object]:
    return json.loads(gate.DEFAULT_MANIFEST.read_text(encoding="utf-8"))


def _result() -> dict[str, object]:
    return {
        "schema_version": "opencode-admission-check-result/v1",
        "started_at": "2026-08-12T00:00:00Z",
        "finished_at": "2026-08-12T00:00:05Z",
        "provider": "opencode-go",
        "model": "deepseek-v4-flash",
        "agent": "ao-mechanical-bulk",
        "routable": True,
        "export_cross_check": {"providerID": "opencode-go", "modelID": "deepseek-v4-flash", "finish": "stop"},
        "cost_sane": True,
        "usage_baseline": 100,
        "usage_observed": 150,
        "usage_multiplier": 1.5,
        "cost_usd": 0.01,
        "tokens": 150,
        "completion_events": 1,
        "containment": {"probe_id": "contained-identity", "status": "pass", "worker_identity": "agentworker", "exact_groups": ["agentworker", "agentdispatch"], "opencode_version": "1.18.4"},
        "pass": True,
    }


class ValidateConfigTests(unittest.TestCase):
    def test_real_checked_in_corpus_is_valid(self) -> None:
        gate.validate_config(_corpus(), _manifest())

    def test_wrong_schema_version_fails_closed(self) -> None:
        corpus = _corpus()
        corpus["schema_version"] = "opencode-admission-check/v0"
        with self.assertRaisesRegex(gate.QualificationError, "schema_version"):
            gate.validate_config(corpus, _manifest())

    def test_missing_top_level_field_fails_closed(self) -> None:
        corpus = _corpus()
        del corpus["budgets"]
        with self.assertRaisesRegex(gate.QualificationError, "missing fields"):
            gate.validate_config(corpus, _manifest())

    def test_model_override_true_fails_closed(self) -> None:
        corpus = _corpus()
        corpus["route"]["model_override"] = True
        with self.assertRaisesRegex(gate.QualificationError, "model override"):
            gate.validate_config(corpus, _manifest())

    def test_wrong_provider_model_fails_closed(self) -> None:
        corpus = _corpus()
        corpus["route"]["model"] = "some-other-model"
        with self.assertRaisesRegex(gate.QualificationError, "exact provider/model"):
            gate.validate_config(corpus, _manifest())

    def test_budget_drift_fails_closed(self) -> None:
        corpus = _corpus()
        corpus["budgets"]["max_cost_usd"] = 999.0
        with self.assertRaisesRegex(gate.QualificationError, "reviewed bounded limits"):
            gate.validate_config(corpus, _manifest())

    def test_containment_group_drift_fails_closed(self) -> None:
        corpus = _corpus()
        corpus["containment"]["exact_groups"] = ["agentworker"]
        with self.assertRaisesRegex(gate.QualificationError, "exact reviewed set"):
            gate.validate_config(corpus, _manifest())

    def test_manifest_not_opted_into_hybrid_fails_closed(self) -> None:
        manifest = _manifest()
        manifest["hybrid"]["enabled"] = False
        with self.assertRaisesRegex(gate.QualificationError, "opted into hybrid dispatch"):
            gate.validate_config(_corpus(), manifest)


class ValidateResultTests(unittest.TestCase):
    def test_a_clean_result_is_valid(self) -> None:
        gate.validate_result(_result(), _corpus())

    def test_non_routable_fails_closed(self) -> None:
        result = _result()
        result["routable"] = False
        with self.assertRaisesRegex(gate.QualificationError, "actually reachable"):
            gate.validate_result(result, _corpus())

    def test_provider_model_mismatch_fails_closed(self) -> None:
        result = _result()
        result["model"] = "some-other-model"
        with self.assertRaisesRegex(gate.QualificationError, "reviewed route"):
            gate.validate_result(result, _corpus())

    def test_export_cross_check_mismatch_fails_closed(self) -> None:
        result = _result()
        result["export_cross_check"]["finish"] = "tool-calls"
        with self.assertRaisesRegex(gate.QualificationError, "export cross-check"):
            gate.validate_result(result, _corpus())

    def test_usage_exceeding_two_times_baseline_fails_closed(self) -> None:
        result = _result()
        result["usage_observed"] = 500
        with self.assertRaisesRegex(gate.QualificationError, "two-times baseline"):
            gate.validate_result(result, _corpus())

    def test_cost_exceeding_budget_fails_closed(self) -> None:
        result = _result()
        result["cost_usd"] = 999.0
        with self.assertRaisesRegex(gate.QualificationError, "exceeds the bounded budget"):
            gate.validate_result(result, _corpus())

    def test_zero_completion_events_fails_closed(self) -> None:
        result = _result()
        result["completion_events"] = 0
        with self.assertRaisesRegex(gate.QualificationError, "at least one clean completion"):
            gate.validate_result(result, _corpus())

    def test_multiple_completion_events_are_accepted(self) -> None:
        """Matches the checker's loosened at-least-one-clean-completion
        semantics -- the validator must not reintroduce exactly-one
        strictness on the result it's given."""
        result = _result()
        result["completion_events"] = 3
        gate.validate_result(result, _corpus())

    def test_failing_containment_fails_closed(self) -> None:
        result = _result()
        result["containment"]["status"] = "fail"
        with self.assertRaisesRegex(gate.QualificationError, "containment probe"):
            gate.validate_result(result, _corpus())

    def test_reported_failure_fails_closed(self) -> None:
        result = _result()
        result["pass"] = False
        with self.assertRaisesRegex(gate.QualificationError, "reports a failed check"):
            gate.validate_result(result, _corpus())

    def test_sensitive_key_is_rejected(self) -> None:
        result = _result()
        result["prompt"] = "leaked prompt text"
        with self.assertRaisesRegex(gate.QualificationError, "not allowed in a plain run-report"):
            gate.validate_result(result, _corpus())

    def test_absolute_workspace_path_is_rejected(self) -> None:
        result = _result()
        result["run_report"] = "/projects/dev/_worktrees/somewhere/report.json"
        with self.assertRaisesRegex(gate.QualificationError, "absolute workspace path"):
            gate.validate_result(result, _corpus())

    def test_secret_like_string_is_rejected(self) -> None:
        result = _result()
        result["containment"]["opencode_version"] = "api_key: sk-fake-not-real"
        with self.assertRaisesRegex(gate.QualificationError, "secret-like"):
            gate.validate_result(result, _corpus())


class MainCliTests(unittest.TestCase):
    def test_main_validates_the_real_checked_in_corpus(self) -> None:
        self.assertEqual(gate.main(["--corpus", str(gate.DEFAULT_CORPUS), "--manifest", str(gate.DEFAULT_MANIFEST)]), 0)

    def test_main_reports_failure_for_a_broken_result_file(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            broken = _result()
            broken["pass"] = False
            path.write_text(json.dumps(broken))
            self.assertEqual(gate.main(["--corpus", str(gate.DEFAULT_CORPUS), "--manifest", str(gate.DEFAULT_MANIFEST), "--result", str(path)]), 2)


if __name__ == "__main__":
    unittest.main()
