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
import math
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from datetime import UTC, datetime
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
OTHER = "sha256:" + "1" * 64


def k(value):
    return estate.known(value, "artifact", "test", T)


def u(reason="not observed"):
    return estate.unknown(reason, "cluster", "test", T)


def replay(envs=None, directory=FIXTURES):
    probe = estate.Probe(replay=directory)
    return estate.build_report(probe, envs or list(estate.ENVIRONMENTS), fetch=False)


def by_id(report):
    return {env["id"]: env for env in report["environments"]}


def replay_edited(envs, edits):
    """Replay with some fixtures edited: ``edits`` maps fixture file name -> fn(fixture dict)."""
    with tempfile.TemporaryDirectory() as tmp:
        for path in FIXTURES.iterdir():
            fixture = json.loads(path.read_text())
            if path.name in edits:
                edits[path.name](fixture)
            (Path(tmp) / path.name).write_text(json.dumps(fixture))
        return replay(envs, directory=Path(tmp))


_ENVS = None


def env_copy(env_id):
    global _ENVS
    if _ENVS is None:
        _ENVS = by_id(replay())
    return copy.deepcopy(_ENVS[env_id])


def gate_of(derive, env):
    return derive(env)["next_blocking_gate"]


def recovery_of(env):
    derive = {"vuoro-shared": estate.derive_vuoro_shared_recovery,
              "vuoro-cloud": estate.derive_vuoro_cloud_recovery}[env["id"]]
    return derive(env)


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

    def test_git_content_is_stamped_with_remote_observation_not_command_time(self):
        d = self.envs["vuoro-shared"]["desired"]
        self.assertEqual(d["image"]["observed_at"], d["deploying_repo_main_sha"]["observed_at"])

    def test_vuoro_shared_numeric_schema_stays_unknown(self):
        fact = self.envs["vuoro-shared"]["usable"]["work_schema_version"]
        self.assertEqual(fact["status"], "unknown")
        self.assertIn("database role", fact["reason"])

    def test_vuoro_shared_gate_and_forward_only_recovery(self):
        env = self.envs["vuoro-shared"]
        self.assertEqual(env["gate"]["next_blocking_gate"]["value"]["gate"], "none")
        self.assertTrue(env["document"]["schema_forward_only"]["value"])
        self.assertIn("(forward only)", env["document"]["schema_forward_only"]["evidence"])
        self.assertEqual(env["gate"]["recovery_class"]["value"]["class"], "forward-fix-or-restore")

    def test_vuoro_shared_receipts_summarised(self):
        receipts = self.envs["vuoro-shared"]["receipts"]
        contexts = [row["context_id"] for row in receipts["appservice"]["value"]]
        self.assertIn("appservice.vuoro.work-schema25-cutover", contexts)
        self.assertTrue(receipts["vuoro"]["value"])

    def test_vuoro_cloud_tunnel_down_leaves_gate_and_recovery_unknown(self):
        env = self.envs["vuoro-cloud"]
        for name in ("deployments", "pod_images", "kustomizations"):
            self.assertEqual(env["running"][name]["status"], "unknown")
            self.assertIn("vuoro-cloud-wg is down", env["running"][name]["reason"])
        gate = env["gate"]["next_blocking_gate"]
        self.assertEqual(gate["status"], "unknown")
        self.assertIn("'holds'", gate["reason"])
        recovery = env["gate"]["recovery_class"]
        self.assertEqual(recovery["status"], "unknown")
        self.assertIn("running.kustomizations", recovery["reason"])
        self.assertIn("held.tenants_in_maintenance", recovery["reason"])

    def test_vuoro_cloud_desired_from_watched_remote_and_tag_tree(self):
        d = self.envs["vuoro-cloud"]["desired"]
        self.assertEqual(d["flux_watched_remote"]["value"]["remote"], "github")
        self.assertEqual(d["flux_watched_remote"]["value"]["canonical_remote"], "origin")
        self.assertEqual(d["predicted_release_tag"]["value"], "v0.1.0-poc.76")
        self.assertIn("selected (predicted)", d["predicted_release_tag"]["evidence"])
        self.assertTrue(d["predicted_release_tag_tree_current"]["value"])
        self.assertEqual(d["previous_release_tag"]["value"], "v0.1.0-poc.75")
        self.assertIs(d["compatibility_discriminates"]["value"], False)
        self.assertIs(d["compatibility_mirror_agrees"]["value"], True)
        self.assertEqual(d["release_report_card"]["value"]["schema_version"], "vuoro-release-report-card/v1")
        self.assertIn("vuoro-cloud@v0.1.0-poc.76:src/vuoro_cloud/release.py", d["release_report_card"]["evidence"])
        pin = self.envs["vuoro-cloud"]["running"]["tenant_runtime_pin"]
        self.assertEqual(pin["status"], "unknown")
        self.assertIn("SOPS", pin["reason"])
        self.assertIn("runtime_image", pin["reason"])

    def test_no_secret_decryption_probe_was_recorded(self):
        names = {p.name for p in FIXTURES.iterdir()}
        self.assertFalse([n for n in names if "pin" in n])
        for path in FIXTURES.iterdir():
            self.assertNotIn("sops -d", path.read_text())

    def test_hosts(self):
        for host in ("workstation", "devbox"):
            env = self.envs[host]
            doctor = env["usable"]["served_doctor"]["value"]
            self.assertEqual((doctor["status"], doctor["compatible"]), ("ok", True))
            self.assertEqual(doctor["endpoint"], "https://vuoro-shared.apps.kotona.app")
            self.assertEqual(env["running"]["installed_profile"]["value"]["revision"],
                             env["desired"]["client_profile"]["value"]["revision"])
            self.assertEqual(env["gate"]["recovery_class"]["value"]["class"], "image-revert")
            # Recorded after `holds: []` reached agentops main: declared, known, empty.
            holds = env["held"]["declared_host_holds"]
            self.assertEqual((holds["status"], holds["value"]), ("known", []))
            self.assertTrue(holds["evidence"].startswith("declared (from the agentops record):"))
            self.assertEqual([f["fact"] for f in env["summary"]["unknown"]],
                             ["held.inbox_launches_disabled"] if host == "devbox" else
                             ["running.maintenance_health", "gate.next_blocking_gate"])
        # Historical fixtures predate persistent maintenance reporting; it is
        # unknown, rather than invented as healthy. Devbox's checkout was old.
        self.assertEqual(self.envs["workstation"]["gate"]["next_blocking_gate"]["status"], "unknown")
        self.assertEqual(self.envs["devbox"]["gate"]["next_blocking_gate"]["value"]["gate"],
                         "agentops-current")

    def test_markdown_lists_every_unknown_with_reason(self):
        text = estate.render_markdown(self.report)
        self.assertIn("| vuoro-shared | none | forward-fix-or-restore |", text)
        for env in self.report["environments"]:
            for item in env["summary"]["unknown"]:
                self.assertIn(f"`{item['fact']}`", text)


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
        self.env = env_copy("vuoro-shared")
        self.job = self.env["running"]["jobs"]["value"]["vuoro-work-migrate-v25"]

    def recovery(self):
        return recovery_of(self.env)

    def gate(self):
        return gate_of(estate.derive_vuoro_shared_gate, self.env)

    def test_not_started_migration_is_cancel(self):
        self.job.update(complete=False, started=False, active=0)
        self.assertEqual(self.recovery()["value"]["class"], "cancel")
        self.assertEqual(self.gate()["value"]["gate"], "schema-migration")

    def test_running_migration_is_unknown(self):
        self.job.update(complete=False, started=True, active=1)
        self.assertEqual(self.recovery()["status"], "unknown")
        self.assertIn("may commit", self.recovery()["reason"])
        self.assertEqual(self.gate()["value"]["gate"], "schema-migration")

    def test_failed_migration_is_unknown_and_blocks(self):
        self.job.update(complete=False, failed=True)
        self.assertEqual(self.recovery()["status"], "unknown")
        self.assertIn("partially applied", self.recovery()["reason"])
        self.assertIn("partially applied", self.gate()["value"]["detail"])

    def test_ttl_deleted_job_uses_handshake_evidence(self):
        del self.env["running"]["jobs"]["value"]["vuoro-work-migrate-v25"]
        self.assertEqual(self.recovery()["value"]["class"], "forward-fix-or-restore")
        self.assertIn("handshake", self.recovery()["value"]["basis"])

    def test_ttl_deleted_job_without_evidence_is_unknown(self):
        del self.env["running"]["jobs"]["value"]["vuoro-work-migrate-v25"]
        self.env["usable"]["handshake"]["value"]["domains"]["work"]["state"] = "incompatible"
        self.assertEqual(self.recovery()["status"], "unknown")
        self.assertIn("TTL", self.recovery()["reason"])
        self.assertEqual(self.gate()["status"], "unknown")

    def test_rollout_in_flight_after_forward_only_migration(self):
        self.env["desired"]["image_digest"] = k(OTHER)
        self.assertEqual(self.recovery()["value"]["class"], "forward-fix-or-restore")
        self.assertEqual(self.gate()["value"]["gate"], "image-rollout")

    def test_rollout_in_flight_with_reversible_schema_is_cancel(self):
        self.env["document"]["schema_forward_only"] = estate.known(False, "document", "t", T)
        self.env["desired"]["image_digest"] = k(OTHER)
        self.assertEqual(self.recovery()["value"]["class"], "cancel")

    def test_reversible_schema_is_image_revert(self):
        self.env["document"]["schema_forward_only"] = estate.known(False, "document", "t", T)
        self.assertEqual(self.recovery()["value"]["class"], "image-revert")

    def test_later_image_than_migration_is_image_revert(self):
        self.env["desired"]["image_digest"] = k(OTHER)
        self.env["running"]["image_digests"] = k([OTHER])
        self.assertEqual(self.recovery()["value"]["class"], "image-revert")

    def test_unknown_forward_only_is_unknown_not_assumed(self):
        self.env["document"]["schema_forward_only"] = estate.unknown("no marker", "document", "t", T)
        result = self.recovery()
        self.assertEqual((result["status"], result["reason"]), ("unknown", "no marker"))

    def test_holds(self):
        cases = [
            ("suspended_kustomizations", k(["vuoro-shared"]), "holds"),
            ("suspended_cronjobs", k([{"name": "cnpg-pgdump-age", "declared_suspend": False}]), "holds"),
            ("scaled_below_declared", k([{"name": "vuoro-shared", "replicas": 0, "declared": 1}]), "holds"),
            ("suspended_cronjobs", k([{"name": "break-glass", "declared_suspend": True}]), "none"),
        ]
        for name, value, expected in cases:
            with self.subTest(name=name, expected=expected):
                env = env_copy("vuoro-shared")
                env["held"][name] = value
                self.assertEqual(gate_of(estate.derive_vuoro_shared_gate, env)["value"]["gate"], expected)

    def test_unknown_hold_stops_the_gate(self):
        self.env["held"]["suspended_cronjobs"] = u("kubectl timed out")
        gate = self.gate()
        self.assertEqual(gate["status"], "unknown")
        self.assertIn("kubectl timed out", gate["reason"])

    def test_stale_or_unknown_manifest_ref_is_unknown(self):
        for fact in (k(False), u("ls-remote failed")):
            with self.subTest(fact=fact["status"]):
                self.env["desired"]["manifest_ref_is_remote_main"] = fact
                gate = self.gate()
                self.assertEqual(gate["status"], "unknown")
                self.assertIn("desired-current", gate["reason"])
                recovery = self.recovery()
                self.assertEqual(recovery["status"], "unknown")
                self.assertIn("origin/main", recovery["reason"])

    def test_unapplied_main_blocks(self):
        self.env["desired"]["deploying_repo_main_sha"] = k("f" * 40)
        self.assertEqual(self.gate()["value"]["gate"], "flux-applied")


class RollbackMarkerTests(unittest.TestCase):
    def test_markers(self):
        cases = {
            "# T\n\n## Failure and rollback (forward only)\n": True,
            "## Rollback (forward-only)\n": True,
            "## Rollback (reversible)\n": False,
            "---\nrollback: forward-only\n---\n# T\n": True,
            "---\nrollback: reversible\n---\n": False,
            "## Rollback (not forward only)\n": None,
            "This cutover is not forward only.\n": None,
            "Forward-only migrations are dangerous.\n": None,
            "```\n## Rollback (forward only)\n```\n": None,
            "## Rollback\n\nRestore the dump.\n": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertIs(estate.parse_rollback_marker(text)[0], expected)


def cloud_full_env(**overrides):
    """vuoro-cloud with the cluster, holds and fleet observed and Flux on the predicted tag."""
    env = env_copy("vuoro-cloud")
    d, r, h, us = env["desired"], env["running"], env["held"], env["usable"]
    tag, sha = d["predicted_release_tag"]["value"], d["predicted_release_tag_sha"]["value"]
    r["kustomizations"] = k({n: {"suspend": False, "ready": "True", "reason": "ReconciliationSucceeded",
                                 "last_applied_revision": f"{tag}@sha1:{sha}"}
                             for n in estate.VUORO_CLOUD["kustomizations"]})
    r["deployments"] = k({n: {"replicas": v["replicas"], "ready": v["replicas"]}
                          for n, v in d["deployments"]["value"].items()})
    r["pod_images"] = k([{"pod": f"{n}-abc", "container": "c", "ready": True, "phase": "Running",
                          "image_id": estate.digest_of(next(iter(v["images"].values())))}
                         for n, v in d["deployments"]["value"].items()])
    h["suspended_kustomizations"] = k([])
    h["suspended_cronjobs"] = k([{"name": "vuoro-admin-enrol", "declared_suspend": True}])
    h["scaled_below_declared"] = k([])
    h["tenants_in_maintenance"] = k([])
    r["tenant_runtime_pin"] = k(estate.digest_of(d["compatibility"]["value"]["packages"]["vuoro-service"]))
    us["fleet_rollout"]["value"]["converged"] = True
    return env


class VuoroCloudDerivationTests(unittest.TestCase):
    def test_fully_observed_applied_release_is_image_revert_and_none(self):
        env = cloud_full_env()
        self.assertEqual(gate_of(estate.derive_vuoro_cloud_gate, env)["value"]["gate"], "none")
        self.assertEqual(recovery_of(env)["value"]["class"], "image-revert")

    def test_unapplied_predicted_tag_is_cancel(self):
        env = cloud_full_env()
        for v in env["running"]["kustomizations"]["value"].values():
            v["last_applied_revision"] = "v0.1.0-poc.75@sha1:" + "e" * 40
        self.assertEqual(recovery_of(env)["value"]["class"], "cancel")
        self.assertEqual(gate_of(estate.derive_vuoro_cloud_gate, env)["value"]["gate"], "flux-applied")

    def test_raised_tenant_schema_floor_is_forward_fix(self):
        env = cloud_full_env()
        env["desired"]["release_report_card"]["value"]["maintenance_required"] = True
        self.assertEqual(recovery_of(env)["value"]["class"], "forward-fix-or-restore")

    def test_every_recovery_input_must_be_known(self):
        for section, name in (("desired", "previous_compatibility"), ("held", "tenants_in_maintenance"),
                              ("usable", "fleet_rollout"), ("running", "pod_images"),
                              ("held", "suspended_cronjobs"), ("desired", "release_ready")):
            with self.subTest(fact=f"{section}.{name}"):
                env = cloud_full_env()
                env[section][name] = u("unobserved")
                result = recovery_of(env)
                self.assertEqual(result["status"], "unknown")
                self.assertIn(f"{section}.{name}", result["reason"])

    def test_report_card_is_never_built_without_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in FIXTURES.iterdir():
                if "previous-tag" not in path.name and "compat-previous" not in path.name:
                    (Path(tmp) / path.name).write_text(path.read_text())
            env = by_id(replay(["vuoro-cloud"], directory=Path(tmp)))["vuoro-cloud"]
        self.assertEqual(env["desired"]["previous_compatibility"]["status"], "unknown")
        self.assertEqual(env["desired"]["release_report_card"]["status"], "unknown")

    def test_moved_tag_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in FIXTURES.iterdir():
                (Path(tmp) / path.name).write_text(path.read_text())
            local = Path(tmp) / "vuoro-cloud.tag.local.json"
            doc = json.loads(local.read_text())
            doc["stdout"] = "f" * 40 + "\n"
            local.write_text(json.dumps(doc))
            env = by_id(replay(["vuoro-cloud"], directory=Path(tmp)))["vuoro-cloud"]
        tree = env["desired"]["predicted_release_tag_tree_current"]
        self.assertEqual(tree["status"], "unknown")
        self.assertIn("moved or re-signed", tree["reason"])
        self.assertEqual(env["desired"]["compatibility"]["status"], "unknown")
        self.assertIn("desired-current", env["gate"]["next_blocking_gate"]["reason"])

    def test_served_compatibility_difference_blocks(self):
        env = cloud_full_env()
        env["running"]["served_compatibility"]["value"]["runtime"] = {"generation": 2, "coexist_with_generations": []}
        self.assertEqual(gate_of(estate.derive_vuoro_cloud_gate, env)["value"]["gate"], "served-compatibility")

    def test_undeclared_suspended_cronjob_blocks(self):
        env = cloud_full_env()
        env["held"]["suspended_cronjobs"] = k([{"name": "backup", "declared_suspend": False}])
        self.assertEqual(gate_of(estate.derive_vuoro_cloud_gate, env)["value"]["gate"], "holds")

    def test_mirror_disagreement_blocks(self):
        env = cloud_full_env()
        env["desired"]["compatibility_mirror_agrees"] = k(False)
        self.assertEqual(gate_of(estate.derive_vuoro_cloud_gate, env)["value"]["gate"], "compatibility-mirror")

    def test_unverifiable_tenant_pin_keeps_gate_unknown(self):
        env = cloud_full_env()
        env["running"]["tenant_runtime_pin"] = u("SOPS")
        gate = gate_of(estate.derive_vuoro_cloud_gate, env)
        self.assertEqual(gate["status"], "unknown")
        self.assertIn("tenant-runtime-pin", gate["reason"])

    def test_pin_mismatch_blocks(self):
        env = cloud_full_env()
        env["running"]["tenant_runtime_pin"] = k("sha256:" + "3" * 64)
        self.assertEqual(gate_of(estate.derive_vuoro_cloud_gate, env)["value"]["gate"], "tenant-runtime-pin")

    def test_requested_rollout_fields_make_both_facts_observable(self):
        want = None

        def edit(fixture):
            body = json.loads(fixture["body"])
            body["maintenance_workspaces"] = [{"id": "ws1", "state": "MAINTENANCE", "maintenance_mode": True}]
            body["runtime_image"] = {"digest": want, "source": "VUORO_CLOUD_RUNTIME_IMAGE"}
            fixture["body"] = json.dumps(body)

        base = env_copy("vuoro-cloud")
        want = estate.digest_of(base["desired"]["compatibility"]["value"]["packages"]["vuoro-service"])
        env = by_id(replay_edited(["vuoro-cloud"], {"vuoro-cloud.rollout-status.json": edit}))["vuoro-cloud"]
        self.assertEqual(env["held"]["tenants_in_maintenance"]["value"], ["ws1"])
        self.assertEqual(env["running"]["tenant_runtime_pin"]["value"], want)

    def test_malformed_runtime_image_is_unknown(self):
        def edit(fixture):
            body = json.loads(fixture["body"])
            body["runtime_image"] = {"digest": "latest"}
            fixture["body"] = json.dumps(body)

        env = by_id(replay_edited(["vuoro-cloud"], {"vuoro-cloud.rollout-status.json": edit}))["vuoro-cloud"]
        self.assertIn("malformed", env["running"]["tenant_runtime_pin"]["reason"])

    def test_tag_match_is_anchored(self):
        sha = "a" * 40
        self.assertTrue(estate.revision_is(f"v0.1.0-poc.7@sha1:{sha}", "v0.1.0-poc.7", sha))
        self.assertFalse(estate.revision_is(f"v0.1.0-poc.76@sha1:{'b' * 40}", "v0.1.0-poc.7", sha))
        self.assertFalse(estate.revision_is(f"v0.1.0-poc.7-rc@sha1:{'b' * 40}", "v0.1.0-poc.7", sha))
        self.assertTrue(estate.revision_is(f"refs/tags/v0.1.0-poc.7@sha1:{sha}", "v0.1.0-poc.7", sha))
        self.assertTrue(estate.revision_is(sha, "v0.1.0-poc.7", sha))
        self.assertFalse(estate.revision_is(f"main@sha1:{sha}xx", "main", sha))
        self.assertFalse(estate.revision_is(None, "main", sha))
        env = cloud_full_env()
        tag = env["desired"]["predicted_release_tag"]["value"]
        for v in env["running"]["kustomizations"]["value"].values():
            v["last_applied_revision"] = f"{tag}6@sha1:{'c' * 40}"  # e.g. poc.766, not poc.76
        self.assertEqual(recovery_of(env)["value"]["class"], "cancel")


class HostDerivationTests(unittest.TestCase):
    def current(self, host="devbox"):
        env = env_copy(host)
        env["running"]["agentops_head"] = k(env["desired"]["agentops_main_sha"]["value"])
        if host == "workstation":
            env["running"]["maintenance_health"] = k({"status": "healthy", "jobs": {}})
        if host == "devbox":
            env["held"]["inbox_launches_disabled"] = k(False)
        return env

    def test_current_host_with_declared_empty_holds_is_none(self):
        env = self.current()
        gate = gate_of(estate.derive_host_gate, env)
        self.assertEqual(gate["value"]["gate"], "none")
        env["held"]["inbox_launches_disabled"] = k(True)
        self.assertEqual(gate_of(estate.derive_host_gate, env)["value"]["gate"], "holds")

    def test_observed_inbox_policy_controls_hold_without_claiming_qualification(self):
        for enabled in (True, False, None, "false", 0):
            with self.subTest(enabled=enabled):
                def edit(fixture):
                    envelope = json.loads(fixture["stdout"])
                    envelope["inbox_launches_enabled"] = enabled
                    envelope["agentops_head"] = env_copy("devbox")["desired"]["agentops_main_sha"]["value"]
                    fixture["stdout"] = json.dumps(envelope)
                env = by_id(replay_edited(["devbox"], {"devbox.ssh.json": edit}))["devbox"]
                self.assertEqual(schema_check.validate(replay_edited(
                    ["devbox"], {"devbox.ssh.json": edit}), SCHEMA), [])
                hold = env["held"]["inbox_launches_disabled"]
                gate = env["gate"]["next_blocking_gate"]
                self.assertEqual(env["held"]["declared_host_holds"]["value"], [])
                self.assertEqual(env["usable"]["served_doctor"]["value"]["status"], "ok")
                if isinstance(enabled, bool):
                    self.assertEqual(hold["value"], not enabled)
                    self.assertEqual(gate["value"]["gate"], "none" if enabled else "holds")
                    if enabled:
                        self.assertIn("inbox launch qualification is not evaluated", gate["value"]["detail"])
                else:
                    self.assertEqual(hold["status"], "unknown")
                    self.assertEqual(gate["status"], "unknown")
                self.assertTrue(hold["evidence"].startswith("observed on host:"))

    def test_remote_policy_probe_emits_only_boolean_or_null(self):
        code = estate._DEVBOX_SCRIPT.split("<<'PY_POLICY'\n", 1)[1].split("\nPY_POLICY", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.json"
            for body, expected in ((None, "null"), ("broken", "null"),
                                   ('{"launches_enabled":false,"private":"do-not-emit"}', "false"),
                                   ('{"launches_enabled":true,"private":"do-not-emit"}', "true"),
                                   ('{"launches_enabled":"false"}', "null"), ('{}', "null")):
                with self.subTest(body=body):
                    if body is not None:
                        policy.write_text(body)
                    result = subprocess.run([sys.executable, "-c", code.replace("{inbox_policy}", str(policy))],
                                            capture_output=True, text=True, check=True)
                    self.assertEqual(result.stdout, expected)
                    self.assertEqual(result.stderr, "")

    def test_failed_ssh_leaves_observed_hold_unknown(self):
        def edit(fixture):
            fixture.update(ok=False, stdout="", error="ssh unavailable")
        env = by_id(replay_edited(["devbox"], {"devbox.ssh.json": edit}))["devbox"]
        self.assertEqual(env["held"]["inbox_launches_disabled"]["status"], "unknown")
        self.assertIn("ssh unavailable", env["held"]["inbox_launches_disabled"]["reason"])

    def test_historical_missing_policy_is_unknown_when_host_otherwise_current(self):
        env = self.current()
        env["held"]["inbox_launches_disabled"] = env_copy("devbox")["held"]["inbox_launches_disabled"]
        self.assertEqual(gate_of(estate.derive_host_gate, env)["status"], "unknown")

    def test_workstation_needs_no_inbox_adapter(self):
        env = self.current("workstation")
        self.assertNotIn("inbox_launches_disabled", env["held"])
        self.assertEqual(gate_of(estate.derive_host_gate, env)["value"]["gate"], "none")

    def test_undeclared_holds_stop_the_gate(self):
        env = self.current()
        env["held"]["declared_host_holds"] = u("the environment record declares no `holds` field")
        gate = gate_of(estate.derive_host_gate, env)
        self.assertEqual(gate["status"], "unknown")
        self.assertIn("'holds'", gate["reason"])

    def test_incompatible_client_is_forward_fix(self):
        env = self.current()
        env["usable"]["served_doctor"]["value"].update(status="error", compatible=False)
        result = estate.derive_host_gate(env)
        self.assertEqual(result["recovery_class"]["value"]["class"], "forward-fix-or-restore")
        self.assertEqual(result["next_blocking_gate"]["value"]["gate"], "served-doctor")

    def test_declared_holds_make_host_holds_known(self):
        def with_holds(holds):
            def edit(fixture):
                record = json.loads(fixture["stdout"])
                record["holds"] = holds
                fixture["stdout"] = json.dumps(record)
            return by_id(replay_edited(["workstation"], {"workstation.environment_record.json": edit}))["workstation"]

        clear = with_holds([])
        self.assertEqual(clear["held"]["declared_host_holds"]["value"], [])
        self.assertEqual(clear["gate"]["next_blocking_gate"]["status"], "unknown")
        self.assertIn("maintenance-health", clear["gate"]["next_blocking_gate"]["reason"])
        held = with_holds([{"id": "out-of-dispatch", "reason": "kernel upgrade"}])
        self.assertEqual(held["held"]["declared_host_holds"]["value"], ["out-of-dispatch"])
        self.assertEqual(held["gate"]["next_blocking_gate"]["value"]["gate"], "holds")

    def test_malformed_holds_are_unknown_not_a_crash(self):
        for bad in (["x"], [{"id": "a"}], [{"id": "Bad Id", "reason": "r"}], "none", [None]):
            with self.subTest(holds=bad):
                def edit(fixture, bad=bad):
                    record = json.loads(fixture["stdout"])
                    record["holds"] = bad
                    fixture["stdout"] = json.dumps(record)
                report = replay_edited(["workstation"], {"workstation.environment_record.json": edit})
                self.assertEqual(schema_check.validate(report, SCHEMA), [])
                env = by_id(report)["workstation"]
                self.assertEqual(env["held"]["declared_host_holds"]["status"], "unknown")
                self.assertIn("malformed", env["held"]["declared_host_holds"]["reason"])
                gate = env["gate"]["next_blocking_gate"]
                self.assertEqual(gate["status"], "unknown")
                self.assertIn("'holds'", gate["reason"])

    def test_profile_revision_drift_blocks_on_both_hosts(self):
        for host in ("workstation", "devbox"):
            with self.subTest(host=host):
                env = self.current(host)
                env["running"]["installed_profile"]["value"]["revision"] = 1
                self.assertEqual(gate_of(estate.derive_host_gate, env)["value"]["gate"], "client-profile")


class FakeProbe(estate.Probe):
    def __init__(self, answers):
        super().__init__()
        self.answers = answers

    def run(self, key, argv, **kwargs):
        stdout = self.answers.get(key)
        if stdout is None:
            return {"ok": False, "error": "nope", "evidence": key, "observed_at": None}
        return {"ok": True, "rc": 0, "stdout": stdout, "stderr": "", "evidence": key, "observed_at": T}


class FreshnessTests(unittest.TestCase):
    def test_behind_remote_uses_fetch_time(self):
        probe = FakeProbe({"r.local": "a" * 40 + "\n",
                           "r.fetch-time": "reflog=origin/main@{2026-10-01T10:00:00+03:00}\n"})
        remote = estate.known("b" * 40, "live-api", "ls-remote", "2026-10-14T12:00:00Z")
        _, current, at = estate.ref_current(probe, "r", Path("/x"), "origin/main", remote)
        self.assertIs(current["value"], False)
        self.assertEqual(at, "2026-10-01T07:00:00Z")

    def test_fetch_head_newer_than_reflog_wins(self):
        probe = FakeProbe({"f": "reflog=origin/main@{2026-10-01T10:00:00+00:00}\nfetch_head_mtime=1791990448\n"})
        self.assertEqual(estate.ref_fetch_time(probe, "f", Path("/x"), "origin/main"), "2026-10-14T15:07:28Z")

    def test_equal_to_remote_uses_ls_remote_time(self):
        probe = FakeProbe({"r.local": "a" * 40 + "\n"})
        remote = estate.known("a" * 40, "live-api", "ls-remote", "2026-10-14T12:00:00Z")
        _, current, at = estate.ref_current(probe, "r", Path("/x"), "origin/main", remote)
        self.assertIs(current["value"], True)
        self.assertEqual(at, "2026-10-14T12:00:00Z")

    def test_ls_remote_failure_is_unknown_not_dropped(self):
        probe = FakeProbe({"r.local": "a" * 40 + "\n"})
        _, current, _ = estate.ref_current(probe, "r", Path("/x"), "origin/main", u("network down"))
        self.assertEqual(current["status"], "unknown")
        self.assertIn("network down", current["reason"])

    def test_saved_report_renders_an_age_warning(self):
        report = {"generated_at": "2026-10-14T10:00:00Z"}
        text = estate.report_age_warning(report, now=datetime(2026, 10, 14, 13, 30, tzinfo=UTC))
        self.assertIn("3h 30m ago", text)


# An independent secret detector: it must not share logic with estate.redact().
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_DSN = re.compile(r"\b[A-Za-z0-9_.-]+:[^@\s/:\"']{3,}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_SECRET_KEYS = re.compile(r"\"(password|passwd|secret|token|api_key|apikey|access_token|private_key)\"\s*:\s*\"([^\"]+)\"",
                          re.I)
_TOKEN = re.compile(r"[A-Za-z0-9+/_=-]{24,}")


def _entropy(text):
    counts = Counter(text)
    return -sum(c / len(text) * math.log2(c / len(text)) for c in counts.values())


def find_secrets(text):
    hits = [m.group(0) for m in _JWT.finditer(text)]
    hits += [m.group(0) for m in _DSN.finditer(text)]
    hits += [m.group(0) for m in _SECRET_KEYS.finditer(text) if "REDACTED" not in m.group(2)]
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        if re.fullmatch(r"[0-9a-f]+", token) or re.fullmatch(r"[a-z0-9-]+", token):
            continue  # hex shas/digests and lower-case slugs (names, uids)
        if re.fullmatch(r"[A-Za-z0-9_-]+", token) and "_" in token and not re.search(r"\d{3}", token):
            continue  # identifiers such as SPRINTCTL_VUORO_PROFILE or dotted op names
        if (re.search(r"[A-Z]", token) and re.search(r"[a-z]", token) and re.search(r"\d", token)
                and _entropy(token) > 4.2):
            hits.append(token)
    return hits


class SecretTests(unittest.TestCase):
    def test_detector_catches_planted_secrets(self):
        # Planted, fake values; the JWT is assembled at runtime so no literal token is committed.
        fake_jwt = ".".join(["eyJ" + "hbGciOiJub25lIn0", "eyJ" + "zdWIiOiJmYWtlIn0", "abcDEF123456"])
        planted = ['"password": "hunter2-hunter2"', fake_jwt,
                   "app:s3cretpw@db.example.com", "Zx9Qw7Lm3Rt8Yp2Kd6Vn4Bh1Jc5Gf0Ts"]
        for secret in planted:
            with self.subTest(secret=secret):
                self.assertTrue(find_secrets(secret))

    def test_fixtures_carry_no_credentials(self):
        for path in sorted(FIXTURES.iterdir()):
            with self.subTest(path=path.name):
                self.assertEqual(find_secrets(path.read_text()), [])


class SafetyAndHelperTests(unittest.TestCase):
    def test_redaction(self):
        raw = ("Authorization: Bearer abcdef0123456789 vuo_operator_abcdefgh "
               "postgresql://u:p@h/db https://x/cb?access_token=tok123&x=1 "
               "export DB_PASSWORD=hunter2 VUORO_TOKEN=abc host=h user=u password=pw42 ghp_" + "a" * 30)
        text = estate.redact(raw)
        for secret in ("abcdef0123456789", "vuo_operator_abcdefgh", "u:p@h", "tok123", "hunter2", "=abc ",
                       "pw42", "a" * 30):
            self.assertNotIn(secret, text)

    def test_json_credential_keys_are_redacted(self):
        doc = {"password": "hunter2", "db_password": "pw", "client_secret": "cs", "access_token": "at",
               "api_key": "ak", "privateKey": "pk", "Authorization": "Basic xyz", "nested": {"token": "t1"}}
        text = estate.redact(json.dumps(doc))
        parsed = json.loads(text)
        for value in ("hunter2", "\"pw\"", "\"cs\"", "\"at\"", "\"ak\"", "\"pk\"", "Basic xyz", "\"t1\""):
            self.assertNotIn(value, text)
        self.assertEqual(parsed["nested"]["token"], "[REDACTED]")

    def test_json_redaction_keeps_references_and_non_strings(self):
        doc = {"credential_ref": "file:~/.config/x", "secretName": "vuoro-identities", "token_file": "/p",
               "credential_resolved": True, "tokens": 3, "authenticated_actor": "workstation-vuoro"}
        self.assertEqual(json.loads(estate.redact(json.dumps(doc))), doc)

    def test_guard_redactions_survive_re_emission(self):
        first = estate.guard_report({"a": "token Zx9Qw7Lm3Rt8Yp2Kd6Vn4Bh1Jc5Gf0Ts", "b": "ok"})
        self.assertEqual(first["guard_redactions"], ["$.a"])
        again = estate.guard_report(json.loads(json.dumps(first)))
        self.assertEqual(again["guard_redactions"], ["$.a"])
        again["c"] = "user:hunter22@db.example.com"
        self.assertEqual(estate.guard_report(again)["guard_redactions"], ["$.a", "$.c"])

    def test_from_preserves_guard_redactions(self):
        saved = replay(["devbox"])
        saved["environments"][0]["desired"]["environment_record"]["evidence"] = "Zx9Qw7Lm3Rt8Yp2Kd6Vn4Bh1Jc5Gf0Ts"
        saved = estate.guard_report(saved)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(saved, handle)
        done = subprocess.run([str(ROOT / "bin/agentops"), "estate", "status", "--from", handle.name, "--json"],
                              capture_output=True, text=True, check=True)
        Path(handle.name).unlink()
        report = json.loads(done.stdout)
        self.assertEqual(report["guard_redactions"], saved["guard_redactions"])
        self.assertEqual(schema_check.validate(report, SCHEMA), [])

    def _from_json(self, saved, *extra):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(saved, handle)
        done = subprocess.run([str(ROOT / "bin/agentops"), "estate", "status", "--from", handle.name,
                               "--json", *extra], capture_output=True, text=True, check=True)
        Path(handle.name).unlink()
        return done.stdout

    def test_untrusted_earlier_redactions_are_never_emitted(self):
        token = "ghp_" + "ABCDEFGHIJ" + "0123456789" + "abcdefghij" + "0123456789"  # fake, assembled
        path_shaped_secret = "$.Zx9Qw7Lm3Rt8Yp2Kd6Vn4Bh1Jc5Gf0Ts"
        saved = replay(["devbox"])
        saved["x"] = estate.GUARD_PLACEHOLDER
        saved["guard_redactions"] = ["$.x", token, 5, "$.x", path_shaped_secret, "$.y z", {"p": 1}]
        out = self._from_json(saved)
        self.assertNotIn(token, out)
        self.assertNotIn("Zx9Qw7Lm3Rt8Yp2Kd6Vn4Bh1Jc5Gf0Ts", out)
        self.assertEqual(json.loads(out)["guard_redactions"], ["$.x"])

    def test_smuggled_path_segments_are_dropped(self):
        smuggle = "$." + "Zx9QwErTy7UiOpAs" + "." + "DfGh2JkLmNbVcX4z"  # fake, assembled at runtime
        saved = replay(["devbox"])
        saved["guard_redactions"] = [smuggle]
        out = self._from_json(saved)
        self.assertNotIn("DfGh2JkLmNbVcX4z", out)
        self.assertNotIn("guard_redactions", json.loads(out))

    def test_from_keeps_genuine_placeholder_path_and_drops_non_placeholder(self):
        saved = replay(["devbox"])
        saved["environments"][0]["desired"]["environment_record"]["evidence"] = estate.GUARD_PLACEHOLDER
        genuine = "$.environments[0].desired.environment_record.evidence"
        saved["guard_redactions"] = [genuine, "$.generator.tool", "$.environments[9].x", genuine]
        out = json.loads(self._from_json(saved))
        self.assertEqual(out["guard_redactions"], [genuine])

    def test_secret_dict_keys_are_replaced(self):
        token = "ghp_" + "ABCDEFGHIJ" + "0123456789" + "abcdefghij" + "0123456789"  # fake, assembled
        token2 = "ghp_" + "KLMNOPQRST" + "0123456789" + "abcdefghij" + "0123456789"
        saved = replay(["devbox"])
        saved[token] = "top"
        saved["generator"][token2] = {"nested": "x"}
        saved["generator"][estate.GUARD_PLACEHOLDER + "#1"] = "sibling"
        out = self._from_json(saved)
        self.assertNotIn(token, out)
        self.assertNotIn(token2, out)
        report = json.loads(out)
        ph = estate.GUARD_PLACEHOLDER
        self.assertEqual(report[ph + "#1"], ph)
        self.assertEqual(report["generator"][ph + "#1"], "sibling")
        self.assertEqual(report["generator"][ph + "#2"], ph)
        self.assertIn(f'$["{ph}#1"]', report["guard_redactions"])
        self.assertIn(f'$.generator["{ph}#2"]', report["guard_redactions"])
        self.assertEqual(json.loads(self._from_json(report))["guard_redactions"], report["guard_redactions"])

    def test_redaction_under_dotted_key_round_trips(self):
        saved = replay(["devbox"])
        saved["labels"] = {"app.kubernetes.io/name": "Zx9Qw7Lm3Rt8Yp2Kd6Vn4Bh1Jc5Gf0Ts", 'we"ird]': "ok"}
        first = estate.guard_report(saved)
        path = '$.labels["app.kubernetes.io/name"]'
        self.assertEqual(first["guard_redactions"], [path])
        out = json.loads(self._from_json(first))
        self.assertEqual(out["guard_redactions"], [path])

    def test_quoted_segment_escaping_and_smuggling(self):
        saved = replay(["devbox"])
        saved["labels"] = {'a"]b.c': estate.GUARD_PLACEHOLDER, "k.v": "plain"}
        genuine = '$.labels["a\\"]b.c"]'
        saved["guard_redactions"] = [genuine, '$.labels["k.v"]', '$.labels["missing.key"]',
                                     '$.labels["a\\"]b.c"]["x"]', '$.labels["bad\\q"]', '$["labels"]x']
        self.assertEqual(json.loads(self._from_json(saved))["guard_redactions"], [genuine])

    def test_env_filter_remaps_redaction_paths(self):
        saved = replay()
        ids = [e["id"] for e in saved["environments"]]
        devbox = ids.index("devbox")
        saved["environments"][devbox]["desired"]["a"] = estate.GUARD_PLACEHOLDER
        saved["environments"][0]["desired"]["b"] = estate.GUARD_PLACEHOLDER
        saved["generator"]["tool"] = estate.GUARD_PLACEHOLDER
        saved["guard_redactions"] = [f"$.environments[{devbox}].desired.a", "$.environments[0].desired.b",
                                     "$.generator.tool"]
        report = json.loads(self._from_json(saved, "--env", "devbox"))
        self.assertEqual([e["id"] for e in report["environments"]], ["devbox"])
        self.assertEqual(report["guard_redactions"], ["$.environments[0].desired.a", "$.generator.tool"])
        self.assertEqual(estate.remap_guard_paths(["$.environments[2].x", "$.environments[1]"], [1, 2]),
                         ["$.environments[1].x", "$.environments[0]"])

    def test_emit_guard_fails_closed_per_field(self):
        report = {"a": {"evidence": "token Zx9Qw7Lm3Rt8Yp2Kd6Vn4Bh1Jc5Gf0Ts here", "ok": "sha256:" + "a" * 64},
                  "b": ["fine", "user:hunter22@db.example.com"]}
        clean = estate.guard_report(report)
        self.assertEqual(clean["a"]["evidence"], estate.GUARD_PLACEHOLDER)
        self.assertEqual(clean["a"]["ok"], report["a"]["ok"])
        self.assertEqual(clean["b"], ["fine", estate.GUARD_PLACEHOLDER])
        self.assertEqual(clean["guard_redactions"], ["$.a.evidence", "$.b[1]"])

    def test_live_report_needs_no_guard_redaction(self):
        self.assertNotIn("guard_redactions", estate.guard_report(replay()))

    def test_redaction_leaves_code_alone(self):
        for code in ("const token=readToken();", "if (secret=== null) {}", "let password=input.value"):
            with self.subTest(code=code):
                self.assertEqual(estate.redact(code), code)

    def test_kubectl_mutation_is_refused(self):
        probe = estate.Probe()
        for verb in ("apply", "patch", "delete", "scale", "annotate"):
            with self.assertRaises(ValueError):
                probe.run("x", ["kubectl", verb, "deploy/x"])

    def test_kubectl_names_are_validated_and_after_double_dash(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = estate.Probe(replay=Path(tmp))
            for bad in ("--all-namespaces", "Bad_Name", "a" * 300, "x;rm"):
                with self.subTest(bad=bad):
                    result = estate.kget(probe, "k", Path("/kc"), "kustomizations", "flux-system", (bad,))
                    self.assertFalse(result["ok"])
                    self.assertIn("non-DNS-1123", result["error"])
        seen = []

        class Recorder(estate.Probe):
            def run(self, key, argv, **kwargs):
                seen.append(argv)
                return {"ok": False, "error": "x", "evidence": key, "observed_at": None}

        estate.kget(Recorder(), "k", Path("/kc"), "kustomizations", "flux-system", ("vuoro-shared",))
        self.assertEqual(seen[0][-2:], ["--", "vuoro-shared"])
        self.assertEqual(seen[0][:2], ["kubectl", "get"])

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
    def run_cli(self, *args):
        return subprocess.run([str(ROOT / "bin/agentops"), *args], capture_output=True, text=True)

    def test_two_word_cli_replays_and_renders(self):
        done = self.run_cli("estate", "status", "--replay", str(FIXTURES), "--json", "--env", "vuoro-shared")
        self.assertEqual(done.returncode, 0, done.stderr)
        report = json.loads(done.stdout)
        self.assertEqual(schema_check.validate(report, SCHEMA), [])
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write(done.stdout)
        rendered = self.run_cli("estate", "status", "--from", handle.name).stdout
        Path(handle.name).unlink()
        self.assertIn("## vuoro-shared (cluster)", rendered)
        self.assertIn("rendered from a saved report", rendered)

    def test_from_json_carries_its_age(self):
        saved = self.run_cli("estate", "status", "--replay", str(FIXTURES), "--json", "--env", "devbox").stdout
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            handle.write(saved)
        done = self.run_cli("estate", "status", "--from", handle.name, "--json")
        Path(handle.name).unlink()
        report = json.loads(done.stdout)
        self.assertEqual(schema_check.validate(report, SCHEMA), [])
        age = report["saved_report_age"]
        self.assertGreater(age["age_seconds"], 0)
        self.assertIn("saved report", age["warning"])
        self.assertNotIn("saved_report_age", json.loads(saved))

    def test_two_word_resolution_is_allowlisted(self):
        done = self.run_cli("render", "project", "--help")  # scripts/render_project.py exists
        self.assertEqual(done.returncode, 2)
        self.assertIn("no such topic", done.stderr)


if __name__ == "__main__":
    unittest.main()
