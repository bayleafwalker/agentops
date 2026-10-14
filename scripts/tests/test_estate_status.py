"""Tests for scripts/estate_status.py (`agentops estate status`).

Everything replays recorded, redacted probe fixtures
(fixtures/estate_status/live-2026-10-14, captured with `--record` from a read-only
live run) or synthetic fact dictionaries; nothing here touches the network, a
cluster or a remote host.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures/estate_status/live-2026-10-14"

SPEC = importlib.util.spec_from_file_location("estate_status", SCRIPTS / "estate_status.py")
assert SPEC and SPEC.loader
estate = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = estate
SPEC.loader.exec_module(estate)

sys.path.insert(0, str(SCRIPTS))
import schema_check  # noqa: E402

SCHEMA = json.loads((ROOT / "environment-record/estate-status-v1.schema.json").read_text())
T = "2026-10-14T00:00:00Z"


def k(value):
    return estate.known(value, "artifact", "test", T)


def u(reason="not observed"):
    return estate.unknown(reason, "cluster", "test", T)


def replay(envs=None, directory=FIXTURES):
    probe = estate.Probe(replay=directory)
    return estate.build_report(probe, envs or list(estate.ENVIRONMENTS), fetch=False)


def by_id(report):
    return {env["id"]: env for env in report["environments"]}


class ReplayedLiveRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = replay()
        cls.envs = by_id(cls.report)

    def test_report_validates_against_schema(self):
        self.assertEqual(schema_check.validate(self.report, SCHEMA), [])
        self.assertEqual(self.report["mode"], "replay")
        self.assertEqual([e["id"] for e in self.report["environments"]], list(estate.ENVIRONMENTS))

    def test_replay_is_reproducible(self):
        self.assertEqual(json.dumps(replay(), sort_keys=True), json.dumps(self.report, sort_keys=True))

    def test_every_fact_has_value_source_time_and_evidence(self):
        for env in self.report["environments"]:
            for path, fact in estate._walk_facts(env):
                with self.subTest(env=env["id"], fact=path):
                    self.assertIn(fact["source"], estate.SOURCES)
                    self.assertTrue(fact["observed_at"])
                    self.assertTrue(fact["evidence"])
                    if fact["status"] == "unknown":
                        self.assertIsNone(fact["value"])
                        self.assertTrue(fact["reason"])

    def test_vuoro_shared_desired_matches_running_and_is_usable(self):
        env = self.envs["vuoro-shared"]
        d, r, us = env["desired"], env["running"], env["usable"]
        self.assertEqual(d["work_schema_pin"]["value"], 25)
        self.assertEqual(d["migration_job"]["value"], "vuoro-work-migrate-v25")
        self.assertTrue(d["manifest_ref_is_remote_main"]["value"])
        self.assertEqual(r["image_digests"]["value"], [d["image_digest"]["value"]])
        self.assertTrue(r["jobs"]["value"]["vuoro-work-migrate-v25"]["complete"])
        for ks in r["kustomizations"]["value"].values():
            self.assertFalse(ks["suspend"])
            self.assertIn(d["deploying_repo_main_sha"]["value"], ks["last_applied_revision"])
        self.assertEqual(us["handshake"]["value"]["compatibility"], "compatible")
        self.assertEqual(us["catalog"]["value"]["operation_count"], 102)
        self.assertEqual(us["catalog"]["value"]["revision"], us["handshake"]["value"]["catalog_revision"])
        self.assertEqual(env["held"]["suspended_kustomizations"]["value"], [])

    def test_vuoro_shared_numeric_schema_stays_unknown(self):
        fact = self.envs["vuoro-shared"]["usable"]["work_schema_version"]
        self.assertEqual(fact["status"], "unknown")
        self.assertIn("database role", fact["reason"])

    def test_vuoro_shared_gate_and_forward_only_recovery(self):
        env = self.envs["vuoro-shared"]
        self.assertEqual(env["gate"]["next_blocking_gate"]["value"]["gate"], "none")
        self.assertTrue(env["document"]["schema_forward_only"]["value"])
        self.assertIn("forward only", env["document"]["schema_forward_only"]["evidence"])
        self.assertEqual(env["gate"]["recovery_class"]["value"]["class"], "forward-fix-or-restore")

    def test_vuoro_shared_receipts_summarised(self):
        receipts = self.envs["vuoro-shared"]["receipts"]
        contexts = [row["context_id"] for row in receipts["appservice"]["value"]]
        self.assertIn("appservice.vuoro.work-schema25-cutover", contexts)
        self.assertTrue(receipts["vuoro"]["value"])

    def test_vuoro_cloud_tunnel_down_is_unknown_not_error(self):
        env = self.envs["vuoro-cloud"]
        for name in ("deployments", "pod_images", "kustomizations"):
            self.assertEqual(env["running"][name]["status"], "unknown")
            self.assertIn("vuoro-cloud-wg is down", env["running"][name]["reason"])
        gate = env["gate"]["next_blocking_gate"]
        self.assertEqual(gate["status"], "unknown")
        self.assertIn("'held'", gate["reason"])
        self.assertEqual(env["held"]["tenants_in_maintenance"]["status"], "unknown")
        self.assertEqual(env["usable"]["handshake"]["status"], "unknown")

    def test_vuoro_cloud_reuses_release_tooling(self):
        d = self.envs["vuoro-cloud"]["desired"]
        self.assertEqual(d["release_tag"]["value"], "v0.1.0-poc.76")
        self.assertEqual(d["previous_release_tag"]["value"], "v0.1.0-poc.75")
        self.assertIs(d["runtime_pin_agrees"]["value"], True)
        self.assertIn("verify-runtime-pin.py", d["runtime_pin_agrees"]["evidence"])
        self.assertEqual(d["release_report_card"]["value"]["schema_version"], "vuoro-release-report-card/v1")
        served = self.envs["vuoro-cloud"]["running"]["served_compatibility"]["value"]
        self.assertEqual(served["runtime"], d["compatibility"]["value"]["runtime"])
        self.assertEqual(self.envs["vuoro-cloud"]["gate"]["recovery_class"]["value"]["class"], "image-revert")

    def test_hosts_served_doctor(self):
        for host in ("workstation", "devbox"):
            env = self.envs[host]
            doctor = env["usable"]["served_doctor"]["value"]
            self.assertEqual((doctor["status"], doctor["compatible"]), ("ok", True))
            self.assertEqual(doctor["endpoint"], "https://vuoro-shared.apps.kotona.app")
            self.assertEqual(env["gate"]["next_blocking_gate"]["value"]["gate"], "none")
            self.assertEqual(env["gate"]["recovery_class"]["value"]["class"], "image-revert")
            self.assertEqual(env["held"]["host_holds"]["status"], "unknown")
        devbox = self.envs["devbox"]["running"]
        self.assertEqual(devbox["installed_profile"]["value"]["revision"],
                         self.envs["devbox"]["desired"]["client_profile"]["value"]["revision"])

    def test_markdown_lists_every_unknown_with_reason(self):
        text = estate.render_markdown(self.report)
        self.assertIn("| vuoro-shared | none | forward-fix-or-restore |", text)
        for env in self.report["environments"]:
            for item in env["summary"]["unknown"]:
                self.assertIn(f"`{item['fact']}`", text)

    def test_fixtures_carry_no_credentials(self):
        for path in FIXTURES.iterdir():
            text = path.read_text()
            with self.subTest(path=path.name):
                self.assertEqual(estate.redact(text), text)


class EmptyReplayTests(unittest.TestCase):
    def test_nothing_observable_is_all_unknown_and_still_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = replay(directory=Path(tmp))
        self.assertEqual(schema_check.validate(report, SCHEMA), [])
        for env in report["environments"]:
            with self.subTest(env=env["id"]):
                self.assertEqual(env["gate"]["recovery_class"]["status"], "unknown")
                self.assertEqual(env["gate"]["next_blocking_gate"]["status"], "unknown")
                self.assertIn("no recorded fixture", json.dumps(env["summary"]["unknown"]))


class VuoroSharedDerivationTests(unittest.TestCase):
    def setUp(self):
        self.env = copy.deepcopy(by_id(replay(["vuoro-shared"]))["vuoro-shared"])

    def recovery(self):
        return estate.derive_vuoro_shared_recovery(self.env)["value"]["class"]

    def test_pending_migration_is_cancel(self):
        self.env["running"]["jobs"]["value"]["vuoro-work-migrate-v25"]["complete"] = False
        self.assertEqual(self.recovery(), "cancel")
        gate = estate.derive_vuoro_shared_gate(self.env)["next_blocking_gate"]["value"]
        self.assertEqual(gate["gate"], "schema-migration")

    def test_rollout_in_flight_is_cancel(self):
        self.env["running"]["image_digests"] = k(["sha256:" + "0" * 64])
        self.assertEqual(self.recovery(), "cancel")
        gate = estate.derive_vuoro_shared_gate(self.env)["next_blocking_gate"]["value"]
        self.assertEqual(gate["gate"], "image-rollout")

    def test_reversible_schema_is_image_revert(self):
        self.env["document"]["schema_forward_only"] = estate.known(False, "document", "t", T)
        self.assertEqual(self.recovery(), "image-revert")

    def test_later_image_than_migration_is_image_revert(self):
        later = "sha256:" + "1" * 64
        self.env["desired"]["image_digest"] = k(later)
        self.env["running"]["image_digests"] = k([later])
        self.assertEqual(self.recovery(), "image-revert")

    def test_unknown_forward_only_is_unknown_not_assumed(self):
        self.env["document"]["schema_forward_only"] = estate.unknown("runbook missing", "document", "t", T)
        result = estate.derive_vuoro_shared_recovery(self.env)
        self.assertEqual((result["status"], result["reason"]), ("unknown", "runbook missing"))

    def test_suspended_kustomization_is_the_first_gate(self):
        self.env["held"]["suspended_kustomizations"] = k(["vuoro-shared"])
        gate = estate.derive_vuoro_shared_gate(self.env)["next_blocking_gate"]["value"]
        self.assertEqual(gate["gate"], "held")

    def test_unapplied_main_blocks(self):
        self.env["desired"]["deploying_repo_main_sha"] = k("f" * 40)
        gate = estate.derive_vuoro_shared_gate(self.env)["next_blocking_gate"]["value"]
        self.assertEqual(gate["gate"], "flux-applied")

    def test_cluster_unknown_stops_gate_evaluation(self):
        self.env["held"]["suspended_kustomizations"] = u("kubectl timed out")
        gate = estate.derive_vuoro_shared_gate(self.env)["next_blocking_gate"]
        self.assertEqual(gate["status"], "unknown")
        self.assertIn("kubectl timed out", gate["reason"])


class VuoroCloudDerivationTests(unittest.TestCase):
    def setUp(self):
        self.env = copy.deepcopy(by_id(replay(["vuoro-cloud"]))["vuoro-cloud"])

    def test_unserved_release_is_cancel(self):
        self.env["running"]["served_compatibility"]["value"]["runtime"] = {"generation": 2,
                                                                          "coexist_with_generations": []}
        gate = estate.derive_vuoro_cloud_gate(self.env)
        self.assertEqual(gate["recovery_class"]["value"]["class"], "cancel")
        self.assertEqual(gate["next_blocking_gate"]["value"]["gate"], "served-compatibility")

    def test_raised_tenant_schema_floor_is_forward_fix(self):
        self.env["desired"]["release_report_card"]["value"]["maintenance_required"] = True
        gate = estate.derive_vuoro_cloud_gate(self.env)
        self.assertEqual(gate["recovery_class"]["value"]["class"], "forward-fix-or-restore")

    def test_pin_disagreement_blocks(self):
        self.env["desired"]["runtime_pin_agrees"] = k(False)
        gate = estate.derive_vuoro_cloud_gate(self.env)["next_blocking_gate"]["value"]
        self.assertEqual(gate["gate"], "runtime-pin")


class HostDerivationTests(unittest.TestCase):
    def test_incompatible_client_is_forward_fix(self):
        env = copy.deepcopy(by_id(replay(["devbox"]))["devbox"])
        env["usable"]["served_doctor"]["value"].update(status="error", compatible=False)
        gate = estate.derive_host_gate(env)
        self.assertEqual(gate["recovery_class"]["value"]["class"], "forward-fix-or-restore")
        self.assertEqual(gate["next_blocking_gate"]["value"]["gate"], "served-doctor")

    def test_profile_revision_drift_blocks(self):
        env = copy.deepcopy(by_id(replay(["devbox"]))["devbox"])
        env["running"]["installed_profile"]["value"]["revision"] = 1
        gate = estate.derive_host_gate(env)["next_blocking_gate"]["value"]
        self.assertEqual(gate["gate"], "client-profile")


class SafetyAndHelperTests(unittest.TestCase):
    def test_redaction(self):
        raw = ("Authorization: Bearer abcdef0123456789 vuo_operator_abcdefgh "
               "postgresql://u:p@h/db password=hunter2 ghp_" + "a" * 30)
        text = estate.redact(raw)
        for secret in ("abcdef0123456789", "vuo_operator_abcdefgh", "u:p@h", "hunter2", "a" * 30):
            self.assertNotIn(secret, text)

    def test_kubectl_mutation_is_refused(self):
        probe = estate.Probe()
        for verb in ("apply", "patch", "delete", "scale", "annotate"):
            with self.assertRaises(ValueError):
                probe.run("x", ["kubectl", verb, "deploy/x"])

    def test_semver_selection_matches_flux_range(self):
        tags = ["v0.1.0-poc.9", "v0.1.0-poc.76", "v0.1.0-poc.75", "v0.2.0", "vuoro-service-v0.1.95"]
        eligible = sorted((t for t in tags if estate.semver_in_range(t, ">=0.1.0-0 <0.2.0-0")),
                          key=estate._semver_key)
        self.assertEqual(eligible, ["v0.1.0-poc.9", "v0.1.0-poc.75", "v0.1.0-poc.76"])

    def test_secret_headers_are_not_echoed(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = estate.Probe(record=Path(tmp))
            result = probe.http("h", "http://127.0.0.1:9/never", secret_headers={"Authorization": "Bearer s3cr3t-value"},
                                timeout=1)
            self.assertNotIn("s3cr3t-value", json.dumps(result))
            self.assertNotIn("s3cr3t-value", (Path(tmp) / "h.json").read_text())


class CliTests(unittest.TestCase):
    def test_two_word_cli_replays_and_renders(self):
        done = subprocess.run([str(ROOT / "bin/agentops"), "estate", "status", "--replay", str(FIXTURES),
                               "--json", "--env", "vuoro-shared"], capture_output=True, text=True, check=True)
        report = json.loads(done.stdout)
        self.assertEqual(schema_check.validate(report, SCHEMA), [])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write(done.stdout)
        rendered = subprocess.run([str(ROOT / "bin/agentops"), "estate", "status", "--from", handle.name],
                                  capture_output=True, text=True, check=True).stdout
        Path(handle.name).unlink()
        self.assertIn("## vuoro-shared (cluster)", rendered)
        self.assertIn("forward-fix-or-restore", rendered)


if __name__ == "__main__":
    unittest.main()
