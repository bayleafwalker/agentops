"""Regression tests for the portable V2.1 execution extraction."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared_execution.runtime import Store  # noqa: E402
from shared_execution.process import run_child  # noqa: E402
from shared_execution.lock import source_digest, verify_dispatch_lock  # noqa: E402
from shared_execution.provider import decide_failover, harness_command_digest  # noqa: E402
from shared_execution.protocol import AttemptEnvelope, EventEnvelope, EvidenceRef, RunEnvelope  # noqa: E402

class ProtocolTests(unittest.TestCase):
    def test_envelopes_are_versioned_and_evidence_refs_are_serializable(self):
        run = RunEnvelope("run-1", "project-1", "repo", "abc123", "adapter-1")
        attempt = AttemptEnvelope("run-1", "task-1", "attempt-1", 1, ("true",), "/tmp", 5,
                                  evidence_refs=(EvidenceRef("sha256:abc", "sha256:abc"),))
        event = EventEnvelope("run-1", "task-1", "attempt-1", 1, 1.0, "attempt.started",
                              evidence_refs=(EvidenceRef("file:attempt.json"),))
        self.assertEqual(run.to_json()["schema_version"], "agentops-execution/v1")
        self.assertEqual(attempt.to_json()["evidence_refs"][0]["uri"], "sha256:abc")
        self.assertEqual(event.to_json()["kind"], "attempt.started")

    def test_unsupported_protocol_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported schema_version"):
            RunEnvelope("run-1", "project-1", "repo", "abc123", "adapter-1", "v9")

    def test_envelope_payloads_are_snapshotted_immutably(self):
        budget = {"spend": {"max": 3}}
        run = RunEnvelope("run-1", "project-1", "repo", "abc123", "adapter-1", budget=budget)
        budget["spend"]["max"] = 99
        self.assertEqual(run.to_json()["budget"]["spend"]["max"], 3)
        with self.assertRaises(TypeError):
            run.budget["spend"]["max"] = 1


class RuntimeTests(unittest.TestCase):
    def test_v21_event_table_keeps_row_shape_and_monotonic_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Store(directory)
            journal.event("attempt.started", "task-1", run_id="run-1", attempt_id="a1")
            journal.event("attempt.finished", "task-1", run_id="run-1", attempt_id="a1")
            rows = journal.events()
            self.assertEqual((rows[0]["seq"], rows[1]["seq"]), (1, 2))
            self.assertEqual(rows[0]["kind"], "attempt.started")
            self.assertEqual(rows[0]["attempt_id"], "a1")
            journal.close()

    def test_vendored_lock_digest_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "vendor" / "shared_execution"
            package.mkdir(parents=True)
            source = package / "engine.py"
            source.write_text("ENGINE = 1\n")
            lock = root / "dispatch.lock"
            lock.write_text(json.dumps({
                "schema_version": "dispatch-lock/v1",
                "vendored_path": "vendor/shared_execution",
                "source_digest": source_digest(package),
            }))
            self.assertEqual(verify_dispatch_lock(lock)["schema_version"], "dispatch-lock/v1")
            source.write_text("ENGINE = 2\n")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_dispatch_lock(lock)


class ProviderFailoverTests(unittest.TestCase):
    def setUp(self):
        command_digest = harness_command_digest(["opencode", "run", "-m", "{model}", "{prompt}"])
        common = {
            "role_id": "worker",
            "harness_id": "opencode",
            "eligibility_ref": "owner-snapshot:eligible",
            "role_qualification_ref": "evidence:role-equivalence",
            "data_policy_ref": "evidence:data-scope",
            "billing_mode": "api",
            "billing_ref": "evidence:billing-binding",
            "harness_qualification_ref": "evidence:harness-command",
            "worker_command_sha256": command_digest,
            "allowed_data_classes": ["public"],
        }
        self.policy = {
            "schema_version": "provider-failover/v1",
            "enabled": True,
            "source_ref": "operator-snapshot:bindings",
            "billing_snapshot_ref": "owner-snapshot:billing",
            "budget_enforcement_ref": "coordinator-budget:task-1",
            "allow_paid_overage": False,
            "ordered_bindings": [
                dict(common, binding_id="binding-a", provider_id="provider-a",
                     model_id="model-a", max_cost_per_attempt_usd=0.25),
                dict(common, binding_id="binding-b", provider_id="provider-b",
                     model_id="model-b", max_cost_per_attempt_usd=0.20),
            ],
        }
        self.arguments = dict(
            current_binding_id="binding-a", current_provider_id="provider-a",
            current_model_id="model-a", role_id="worker", data_class="public",
            harness_id="opencode", worker_command_sha256=command_digest,
            failure_kind="transport_error", quota_reset_at=None,
            expected_attempt_ref="attempt:1",
            usage={"state": "known", "complete": True, "observer": "coordinator",
                   "billing_snapshot_ref": "owner-snapshot:billing", "attempt_ref": "attempt:1",
                   "evidence_ref": "evidence:usage", "source_ref": "coordinator-usage:1",
                   "attempt_cost_usd": 0.05,
                   "remaining_budget_usd": 0.20}, now=100.0)

    def test_disabled_by_default(self):
        decision = decide_failover(None, **self.arguments)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "disabled")

    def test_next_explicit_qualified_binding_is_returned_in_operator_order(self):
        decision = decide_failover(self.policy, **self.arguments)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.binding["binding_id"], "binding-b")
        self.assertEqual(decision.reason, "binding_snapshot_constraints_passed")
        self.assertEqual(decision.usage_ref, "evidence:usage")

    def test_unknown_usage_and_quota_reset_pause(self):
        unknown_usage = dict(self.arguments, usage=None)
        self.assertEqual(decide_failover(self.policy, **unknown_usage).reason, "usage_unknown")
        quota = dict(self.arguments, failure_kind="quota_exhausted", quota_reset_at=None)
        self.assertEqual(decide_failover(self.policy, **quota).reason, "quota_reset_unknown_or_elapsed")

    def test_role_data_and_cost_constraints_deny_binding(self):
        self.assertEqual(decide_failover(self.policy, **dict(self.arguments, role_id="review"))
                         .reason, "current_role_or_harness_unqualified")
        self.assertEqual(decide_failover(self.policy, **dict(self.arguments, data_class="restricted"))
                         .reason, "current_data_policy_unqualified")
        expensive = [dict(self.policy["ordered_bindings"][0]), dict(self.policy["ordered_bindings"][1])]
        expensive[1]["max_cost_per_attempt_usd"] = 0.30
        policy = dict(self.policy, ordered_bindings=expensive)
        self.assertEqual(decide_failover(policy, **self.arguments).reason,
                         "candidate_cost_exceeds_current_ceiling")

    def test_timeout_is_not_a_qualified_failover_outcome(self):
        decision = decide_failover(self.policy, **dict(self.arguments, failure_kind="timeout"))
        self.assertEqual(decision.reason, "failure_kind_not_qualified")

    def test_worker_report_and_paid_overage_cannot_authorize_fallback(self):
        worker_usage = dict(self.arguments["usage"], observer="worker")
        decision = decide_failover(self.policy, **dict(self.arguments, usage=worker_usage))
        self.assertEqual(decision.reason, "usage_observer_untrusted")
        paid = dict(self.policy, allow_paid_overage=True)
        self.assertIn("allow_paid_overage must be false",
                      decide_failover(paid, **self.arguments).reason)


class ProcessTests(unittest.TestCase):
    def test_v21_child_supervisor_runs_command_and_records_child(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executions"
            command = (sys.executable, "-c",
                       "from pathlib import Path; import os; p=Path(os.environ['MARKER']); "
                       "p.write_text((p.read_text() if p.exists() else '')+'x')")
            attempt = Path(directory) / "attempt"
            attempt.mkdir()
            with (attempt / "output.log").open("ab") as output:
                result = run_child(list(command), output,
                                   spec={"cwd": directory, "timeout": 3},
                                   attempt_dir=attempt,
                                   env={**os.environ, "MARKER": str(marker)},
                                   started_at=time.time())
            self.assertEqual(result, 0)
            self.assertEqual(marker.read_text(), "x")
            child = json.loads((attempt / "child.json").read_text())
            self.assertEqual(child["pgid"], child["pid"])

    def test_v21_timeout_returns_124(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory) / "attempt"
            attempt.mkdir()
            with (attempt / "output.log").open("ab") as output:
                result = run_child([sys.executable, "-c", "import time; time.sleep(30)"], output,
                                   spec={"cwd": directory, "timeout": .1},
                                   attempt_dir=attempt, env=os.environ.copy(),
                                   started_at=time.time())
            self.assertEqual(result, 124)

if __name__ == "__main__":
    unittest.main()
