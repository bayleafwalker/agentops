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

    def test_devbox_profile_is_a_preflight_observation_not_a_qualification(self) -> None:
        validator.validate_profile(self.profile, self.path)
        self.assertEqual(self.profile["qualification"]["state"], "preflight_observed")
        self.assertIn("contained-disposable-no-override-smoke", self.profile["qualification"]["blocking_probes"])

    def test_qualified_profile_cannot_retain_blocking_probes(self) -> None:
        self.profile["qualification"] = {"state": "qualified", "blocking_probes": ["still-blocked"]}
        with self.assertRaisesRegex(ValueError, "must be empty when qualified"):
            validator.validate_profile(self.profile, self.path)

    def test_profile_requires_receipt_identity_and_fingerprints(self) -> None:
        self.profile["receipt_fields"].remove("executable_fingerprint")
        with self.assertRaisesRegex(ValueError, "missing required evidence: executable_fingerprint"):
            validator.validate_profile(self.profile, self.path)
