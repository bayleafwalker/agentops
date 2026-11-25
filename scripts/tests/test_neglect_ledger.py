"""Distinguish observed deadlines from predictions and unknown prerequisites."""

from copy import deepcopy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "neglect_ledger.py"
SPEC = importlib.util.spec_from_file_location("neglect_ledger", SCRIPT)
ledger = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ledger)
FIXTURE = Path(__file__).parent / "fixtures/neglect/renewal-observations.json"


class LedgerFixtureCase(unittest.TestCase):
    def setUp(self):
        fixture = json.loads(FIXTURE.read_text())
        self.inventory = fixture["inventory"]
        self.at = ledger.timestamp(fixture["observed_at"])
        self.expected = fixture["expected"]
        self.snapshot = {
            "schema_version": 1, "inventory_id": self.inventory["inventory_id"],
            "inventory_digest": ledger.digest(self.inventory), "collected_at": fixture["observed_at"],
            "collector_host": "synthetic-fixture", "collector_digest": "0" * 64,
            "observations": fixture["observations"],
        }

    def evaluate(self):
        self.snapshot["inventory_digest"] = ledger.digest(self.inventory)
        return ledger.evaluate(self.inventory, self.snapshot, self.at)

    def row(self, report, identifier):
        return next(row for row in report["obligations"] if row["id"] == identifier)


class NeglectLedgerTests(LedgerFixtureCase):
    def test_independent_fixture_expectations(self):
        report = self.evaluate()
        self.assertEqual(report["coverage"], self.expected["coverage"])
        self.assertEqual(report["first_failure"]["status"], self.expected["first_failure_status"])
        self.assertEqual(report["earliest_known_conditional_limit"], self.expected["conditional_limit"])
        self.assertEqual(self.row(report, "certificate")["renewal"]["status"], self.expected["certificate_renewal_status"])
        self.assertEqual(self.row(report, "drill")["due_at"], self.expected["drill_due_at"])
        self.assertEqual(self.row(report, "drill")["deadline_type"], self.expected["drill_deadline_type"])

    def test_blocked_renewal_discriminates_from_working_automation(self):
        self.snapshot["observations"][1].update(state="blocked", reason="timer_inactive")
        report = self.evaluate()
        limit = report["earliest_known_conditional_limit"]
        self.assertEqual(limit["subject_id"], "certificate")
        self.assertEqual(limit["at"], "2026-11-14T10:00:00Z")
        self.assertFalse(limit["outage_prediction"])
        self.assertEqual(report["first_failure"]["status"], "unknown")

    def test_active_timer_without_success_is_not_proven_renewal(self):
        del self.snapshot["observations"][1]["last_success_at"]
        report = self.evaluate()
        self.assertEqual(self.row(report, "renewal")["observation"]["reason"], "renewal_success_unknown")
        self.assertEqual(self.row(report, "certificate")["renewal"]["status"], "unknown")

    def test_source_configuration_does_not_become_current_observation(self):
        self.snapshot["observations"][0]["basis"] = "source"
        report = self.evaluate()
        self.assertEqual(self.row(report, "certificate")["observation"]["reason"], "source_only_evidence")
        self.assertIsNone(self.row(report, "certificate")["due_at"])

    def test_stale_and_future_receipts_do_not_count_as_observed(self):
        for value, reason in ((self.at - timedelta(hours=2), "stale_receipt"), (self.at + timedelta(seconds=1), "future_receipt")):
            with self.subTest(reason=reason):
                self.snapshot["observations"][0]["observed_at"] = ledger.iso(value)
                report = self.evaluate()
                self.assertEqual(self.row(report, "certificate")["observation"]["reason"], reason)
                self.assertIsNone(self.row(report, "certificate")["due_at"])

    def test_future_renewal_fact_does_not_prove_success(self):
        self.snapshot["observations"][1]["last_success_at"] = "2026-11-14T09:55:00Z"
        report = self.evaluate()
        self.assertEqual(self.row(report, "renewal")["observation"]["state"], "unknown")

    def test_expiry_crossed_after_observation_is_blocked_at_cutoff(self):
        self.snapshot["observations"][0]["due_at"] = "2026-11-13T10:00:00Z"
        report = self.evaluate()
        self.assertEqual(self.row(report, "certificate")["observation"]["reason"], "expiry_reached_at_cutoff")

    def test_recovery_stops_at_first_unresolved_prerequisite(self):
        self.snapshot["observations"] = self.snapshot["observations"][:2]
        report = self.evaluate()
        recovery = self.row(report, "certificate")["recovery"]
        self.assertEqual(recovery["path"], ["certificate", "network"])
        self.assertEqual(recovery["first_unresolved_prerequisite"], "network")
        self.assertEqual(recovery["status"], "unknown")

    def test_missing_edge_evidence_stops_before_healthy_node(self):
        self.inventory["obligations"][0]["recovery_path"][0].pop("evidence_ref")
        report = self.evaluate()
        self.assertEqual(self.row(report, "certificate")["recovery"]["reason"], "dependency_evidence_missing")

    def test_dependency_cycle_requires_each_edge_to_be_evidenced(self):
        self.inventory["obligations"][2]["prerequisites"] = [{"id": "renewal", "basis": "source", "evidence_ref": "fixture:reverse-dependency"}]
        report = self.evaluate()
        cycle = self.row(report, "certificate")["renewal"]
        self.assertEqual(cycle["status"], "cycle")
        self.assertEqual(cycle["path"], ["certificate", "renewal", "network", "renewal"])
        self.assertTrue(all(edge["evidence_ref"] for edge in cycle["edges"]))
        self.assertFalse(cycle["runtime_deadlock_proven"])
        del self.inventory["obligations"][2]["prerequisites"][0]["evidence_ref"]
        report = self.evaluate()
        self.assertEqual(self.row(report, "certificate")["renewal"]["status"], "unknown")

    def test_retention_is_derived_from_actual_recovery_point(self):
        item = self.inventory["obligations"][0]
        item.update(kind="retention", retention_seconds=7 * 86400)
        del item["renewer_id"]
        receipt = self.snapshot["observations"][0]
        receipt.pop("due_at")
        receipt["latest_recovery_point_at"] = "2026-11-12T08:00:00Z"
        report = self.evaluate()
        row = self.row(report, "certificate")
        self.assertEqual(row["due_at"], "2026-11-19T08:00:00Z")
        self.assertEqual(row["due_basis"], "derived")
        self.assertEqual(row["deadline_type"], "retention_boundary")
        self.assertFalse(report["earliest_known_conditional_limit"]["outage_prediction"])

    def test_configured_expiry_does_not_create_a_failure_limit(self):
        self.inventory["obligations"][0]["due"] = {"at": "2026-11-14T10:00:00Z", "basis": "configured", "evidence_ref": "fixture:configuration"}
        self.snapshot["observations"] = []
        report = self.evaluate()
        self.assertEqual(self.row(report, "certificate")["due_basis"], "configured")
        self.assertIsNone(report["earliest_known_conditional_limit"])

    def test_overdue_drill_is_not_an_outage(self):
        self.inventory["obligations"][3]["due"]["at"] = "2026-11-12T00:00:00Z"
        report = self.evaluate()
        self.assertTrue(self.row(report, "drill")["overdue"])
        self.assertIsNone(report["earliest_known_conditional_limit"])

    def test_complete_snapshot_is_still_not_a_future_failure_forecast(self):
        self.snapshot["observations"].append({"subject_id": "drill", "observed_at": ledger.iso(self.at), "evidence_ref": "fixture:drill-observation", "basis": "runtime", "state": "available"})
        report = self.evaluate()
        self.assertEqual(report["coverage"]["unknown"], 0)
        self.assertEqual(report["first_failure"]["reason"], "future_automation_outcomes_are_not_predictions")

    def test_inventory_revision_mismatch_is_rejected(self):
        self.inventory["obligations"][0]["max_age_seconds"] = 1
        with self.assertRaises(ledger.InvalidInput):
            ledger.evaluate(self.inventory, self.snapshot, self.at)

    def test_missing_dependency_must_be_explicit_in_inventory(self):
        self.inventory["obligations"][0]["renewer_id"] = "unlisted"
        with self.assertRaises(ledger.InvalidInput):
            ledger.validate_inventory(self.inventory)

    def test_arbitrary_probe_command_is_rejected(self):
        self.inventory["obligations"][0]["probe"] = {"kind": "command", "command": "echo invalid"}
        with self.assertRaises(ledger.InvalidInput):
            ledger.validate_inventory(self.inventory)

    def test_duplicate_ids_and_receipts_are_rejected(self):
        self.snapshot["observations"].append(deepcopy(self.snapshot["observations"][0]))
        with self.assertRaises(ledger.InvalidInput):
            self.evaluate()
        self.inventory["obligations"].append(deepcopy(self.inventory["obligations"][0]))
        with self.assertRaises(ledger.InvalidInput):
            ledger.validate_inventory(self.inventory)

    def test_dates_need_an_offset(self):
        with self.assertRaises(ledger.InvalidInput):
            ledger.timestamp("2026-11-13T10:00:00")

    def test_markdown_reports_uncertainty(self):
        rendered = ledger.markdown(self.evaluate())
        self.assertIn("3/4 observed; 1 unknown", rendered)
        self.assertIn("proof_obligation / configured", rendered)
        self.assertIn("First failure: unknown", rendered)


class CollectionTests(LedgerFixtureCase):
    def collect_item(self, probe, responses=(), kind="expiry", host="fixture-host"):
        item = deepcopy(self.inventory["obligations"][0])
        item.update(probe=probe, kind=kind)
        calls = []
        queue = list(responses)
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return queue.pop(0)
        result = ledger.collect_one(item, Path("/nonexistent-fixture-root"), self.at, host, runner)
        return result, calls

    def test_wrong_host_never_reads_certificate(self):
        result, calls = self.collect_item({"kind": "certificate", "path": "client.crt", "collect_on": "other-host"})
        self.assertEqual(result["reason"], "wrong_collection_host")
        self.assertEqual(calls, [])

    def test_certificate_probe_retains_only_expiry(self):
        result, calls = self.collect_item({"kind": "certificate", "path": "client.crt", "collect_on": "fixture-host"}, [subprocess.CompletedProcess([], 0, "notAfter=Nov 14 10:00:00 2026 GMT\n", "DO NOT COPY STDERR")])
        self.assertEqual(result["due_at"], "2026-11-14T10:00:00Z")
        self.assertEqual(result["state"], "available")
        self.assertNotIn("DO NOT COPY", json.dumps(result))
        self.assertEqual(calls[0][0][0:2], ["openssl", "x509"])
        self.assertFalse(calls[0][1].get("shell", False))

    def test_expired_certificate_is_observed_blocked(self):
        result, _ = self.collect_item({"kind": "certificate", "path": "client.crt", "collect_on": "fixture-host"}, [subprocess.CompletedProcess([], 0, "notAfter=Nov 12 10:00:00 2026 GMT\n", "")])
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["reason"], "certificate_expired")

    def test_timer_probe_failure_is_not_an_absent_timer(self):
        probe = {"kind": "systemd_timer", "unit": "fixture.timer", "scope": "user", "collect_on": "fixture-host"}
        result, _ = self.collect_item(probe, [subprocess.CompletedProcess([], 1, "", "bus inaccessible")], kind="renewal")
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["reason"], "timer_probe_failed")
        result, _ = self.collect_item(probe, [subprocess.CompletedProcess([], 0, "LoadState=not-found\nActiveState=inactive\nUnitFileState=\n", "")], kind="renewal")
        self.assertEqual(result["state"], "blocked")
        self.assertEqual(result["reason"], "timer_not_installed")

    def test_empty_success_is_not_an_observed_timer(self):
        result, _ = self.collect_item({"kind": "systemd_timer", "unit": "fixture.timer", "scope": "user", "collect_on": "fixture-host"}, [subprocess.CompletedProcess([], 0, "", "")], kind="renewal")
        self.assertEqual(result["state"], "unknown")

    def test_timer_collects_last_success_without_executing_service(self):
        result, calls = self.collect_item({"kind": "systemd_timer", "unit": "fixture.timer", "service": "fixture.service", "scope": "user", "collect_on": "fixture-host"}, [
            subprocess.CompletedProcess([], 0, "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n", ""),
            subprocess.CompletedProcess([], 0, "Result=success\nExecMainStatus=0\nExecMainExitTimestamp=Fri 2026-11-13 09:55:00 UTC\n", ""),
        ], kind="renewal")
        self.assertEqual(result["last_success_at"], "2026-11-13T09:55:00Z")
        self.assertTrue(all(call[0][0:3] == ["systemctl", "--user", "show"] for call in calls))

    def test_relative_path_cannot_escape_inventory(self):
        with self.assertRaises(ledger.InvalidInput):
            ledger.resolve_input("../secret.json", Path("/tmp/inventory"))

    def test_receipt_extra_fields_are_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = deepcopy(self.snapshot["observations"][0])
            receipt["private_key"] = "SECRET_SENTINEL"
            (root / "receipt.json").write_text(json.dumps(receipt))
            item = deepcopy(self.inventory["obligations"][0])
            item["probe"] = {"kind": "receipt", "path": "receipt.json"}
            result = ledger.collect_one(item, root, self.at, "fixture-host", lambda *a, **k: None)
            self.assertEqual(result["state"], "unknown")
            self.assertNotIn("SECRET_SENTINEL", json.dumps(result))

    def test_cli_writes_private_outputs_and_incomplete_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inventory = root / "inventory.json"
            observations = root / "observations.json"
            output = root / "ledger.json"
            readable = root / "ledger.md"
            inventory.write_text(json.dumps(self.inventory))
            observations.write_text(json.dumps(self.snapshot))
            result = subprocess.run([sys.executable, str(SCRIPT), "evaluate", "--inventory", str(inventory), "--observations", str(observations), "--at", ledger.iso(self.at), "--output", str(output), "--markdown", str(readable), "--require-complete"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(readable.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(output.read_text())["coverage"]["unknown"], 1)
            result = subprocess.run([sys.executable, str(SCRIPT), "collect", "--inventory", str(inventory), "--output", str(inventory)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(inventory.read_text()), self.inventory)

    def test_cli_refuses_to_replace_certificate_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.inventory["obligations"][0]["probe"] = {"kind": "certificate", "path": "public.crt", "collect_on": "fixture-host"}
            (root / "inventory.json").write_text(json.dumps(self.inventory))
            (root / "public.crt").write_text("PUBLIC_CERTIFICATE_SENTINEL")
            result = subprocess.run([sys.executable, str(SCRIPT), "collect", "--inventory", str(root / "inventory.json"), "--output", str(root / "public.crt")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual((root / "public.crt").read_text(), "PUBLIC_CERTIFICATE_SENTINEL")


if __name__ == "__main__":
    unittest.main()
