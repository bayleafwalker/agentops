"""Maintenance reports and infra status never infer health from missing evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("estate_maintenance", ROOT / "scripts/estate_status.py")
estate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = estate
spec.loader.exec_module(estate)
NOW = "2026-10-31T12:00:00+00:00"


def report(host="infra"):
    return {"schema_version": "maintenance-health/v1", "host": host, "checked_at": NOW,
            "status": "healthy", "probe_error": None,
            "jobs": {unit: {"status": "healthy", "problems": [], "last_success_at": NOW,
                            "last_success_age_seconds": 0, "max_age_hours": 36,
                            "last_attempt": {"result": "success"}}
                     for unit in estate.HOSTS[host]["maintenance_units"]}}


def probe(data):
    return {"ok": True, "stdout": json.dumps(data), "observed_at": NOW, "evidence": "host:health.json"}


class MaintenanceFacts(unittest.TestCase):
    def test_fresh_complete_report_is_known_at_collection_time(self):
        fact = estate.maintenance_fact(probe(report()), "infra")
        self.assertEqual(fact["status"], "known")
        self.assertEqual(fact["observed_at"], NOW)
        self.assertTrue(estate.maintenance_check(fact)[0])

    def test_stale_missing_future_or_foreign_reports_are_unknown(self):
        for field, value in [("checked_at", "2026-10-31T10:00:00Z"),
                             ("checked_at", "2026-10-31T13:00:00Z"),
                             ("host", "workstation"), ("jobs", {})]:
            data = report(); data[field] = value
            self.assertEqual(estate.maintenance_fact(probe(data), "infra")["status"], "unknown")
        self.assertEqual(estate.maintenance_fact({"ok": False, "error": "unavailable", "evidence": "ssh"}, "infra")["status"], "unknown")

    def test_incomplete_or_inconsistent_reports_cannot_pass(self):
        data = report()
        data["probe_error"] = "probe-unavailable"
        self.assertEqual(estate.maintenance_fact(probe(data), "infra")["status"], "unknown")
        data = report()
        data["jobs"]["talos-etcd-backup.service"]["last_attempt"]["result"] = "failed"
        self.assertEqual(estate.maintenance_fact(probe(data), "infra")["status"], "unknown")

    def test_stale_success_is_not_accepted_under_a_healthy_label(self):
        data = report()
        data["jobs"]["talos-etcd-backup.service"]["last_success_at"] = "2026-10-28T12:00:00Z"
        self.assertEqual(estate.maintenance_fact(probe(data), "infra")["status"], "unknown")

    def test_genuine_incident_is_known_and_blocks_readiness(self):
        data = report()
        data["status"] = "degraded"
        job = data["jobs"]["talos-etcd-backup.service"]
        job.update(status="degraded", problems=["last-run-failed"])
        fact = estate.maintenance_fact(probe(data), "infra")
        self.assertEqual(fact["status"], "known")
        self.assertFalse(estate.maintenance_check(fact)[0])

    def test_only_summary_fields_are_exposed(self):
        data = report()
        data["private"] = "sensitive CANARY"
        data["jobs"]["talos-etcd-backup.service"]["private"] = "sensitive CANARY"
        fact = estate.maintenance_fact(probe(data), "infra")
        self.assertNotIn("CANARY", json.dumps(fact))

    def test_infra_does_not_require_agent_tools_or_credentials(self):
        calls = []
        class Fake:
            def run(self, key, args, **kwargs):
                calls.append(args)
                if key == "infra.hostname":
                    return {**probe({}), "stdout": "infra\n"}
                return probe(report() if key.endswith("maintenance-health") else {"nixosVersion": "test"})
        source = estate.known("abc", "artifact", "observer source", NOW)
        env = estate.collect_infra(Fake(), source)
        self.assertEqual(env["gate"]["next_blocking_gate"]["value"]["gate"], "none")
        self.assertNotIn("client_profile", env["desired"])
        self.assertFalse(any("sprintctl" in str(call) or "credential" in str(call) for call in calls))
        self.assertEqual(env["gate"]["recovery_class"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
