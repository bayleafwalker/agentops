from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
PROFILES = ROOT / "templates/dispatch/harness-profiles"
SCRIPT = ROOT / "templates/dispatch/scripts/validate_harness_profiles.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_harness_profiles", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


validator = _load_module()


class HarnessProfileValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = PROFILES / "opencode-nixpkgs-devbox-1.18.4.json"
        self.profile = json.loads(self.path.read_text(encoding="utf-8"))

    def test_devbox_profile_remains_preflight_only_until_contained_provider_evidence(self) -> None:
        validator.validate_profile(self.profile, self.path)
        self.assertEqual(self.profile["qualification"]["state"], "preflight_observed")
        self.assertEqual(
            self.profile["qualification"]["blocking_probes"],
            ["contained-identity", "provider-qualification"],
        )
        self.assertEqual(self.profile["worker_identity"], "agentworker")

    def test_schema_requires_lifecycle_contract(self) -> None:
        schema = json.loads((PROFILES / "harness-profile.schema.json").read_text(encoding="utf-8"))
        self.assertIn("lifecycle", schema["required"])
        self.assertEqual(
            schema["properties"]["lifecycle"]["properties"]["session_id_field"]["const"],
            "sessionID",
        )
        self.assertEqual(
            schema["properties"]["lifecycle"]["properties"]["finalizer"]["properties"]["agent"]["const"],
            "ao-finalizer",
        )

    def test_qualified_profile_cannot_retain_blocking_probes(self) -> None:
        self.profile["qualification"] = {"state": "qualified", "blocking_probes": ["still-blocked"]}
        with self.assertRaisesRegex(ValueError, "must be empty when qualified"):
            validator.validate_profile(self.profile, self.path)

    def test_profile_requires_receipt_identity_and_fingerprints(self) -> None:
        self.profile["receipt_fields"].remove("executable_fingerprint")
        with self.assertRaisesRegex(ValueError, "missing required evidence: executable_fingerprint"):
            validator.validate_profile(self.profile, self.path)

    def test_profile_requires_a_safe_contained_worker_identity(self) -> None:
        self.profile["worker_identity"] = "root user"
        with self.assertRaisesRegex(ValueError, "must be a safe local username"):
            validator.validate_profile(self.profile, self.path)

    def test_profile_binds_lifecycle_contract_to_contained_finalizer(self) -> None:
        validator.validate_profile(self.profile, self.path)
        self.assertEqual(
            set(self.profile["required_probes"]),
            {
                "cli-version",
                "run-help",
                "contained-worktree-model-list",
                "explicit-tool-enumeration",
                "message-before-file",
                "json-events",
                "stable-session-identity",
                "session-continuation",
                "contained-identity",
                "no-tools-finalizer",
            },
        )
        self.assertIn("capability_probe_results", self.profile["receipt_fields"])
        self.assertIn("lifecycle_probe_results", self.profile["receipt_fields"])
        self.assertEqual(self.profile["lifecycle"]["event_format"], "json")
        self.assertEqual(self.profile["lifecycle"]["session_id_field"], "sessionID")
        self.assertEqual(self.profile["lifecycle"]["continuation"]["mode"], "same-session")
        self.assertEqual(self.profile["lifecycle"]["finalizer"]["tools"], [])

    def test_profile_rejects_forking_or_toolful_finalization(self) -> None:
        self.profile["lifecycle"]["continuation"]["fork"] = True
        with self.assertRaisesRegex(ValueError, "same-session continuation"):
            validator.validate_profile(self.profile, self.path)

    def test_profile_rejects_preflight_without_contained_provider_blockers(self) -> None:
        self.profile["qualification"] = {
            "state": "preflight_observed",
            "blocking_probes": ["provider-qualification"],
        }
        with self.assertRaisesRegex(ValueError, "contained/provider evidence"):
            validator.validate_profile(self.profile, self.path)
