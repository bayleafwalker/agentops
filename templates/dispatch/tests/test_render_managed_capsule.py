from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "render_managed_capsule.py"
SPEC = importlib.util.spec_from_file_location("managed_capsule", SCRIPT)
assert SPEC and SPEC.loader
CAPSULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CAPSULE)
FIXTURE = ROOT / "managed-capsule" / "source.fixture.json"


class ManagedCapsuleTests(unittest.TestCase):
    def source(self) -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_render_is_byte_stable_and_self_verifying(self) -> None:
        first, first_prompt = CAPSULE.render(self.source())
        second, second_prompt = CAPSULE.render(self.source())
        self.assertEqual(CAPSULE.canonical(first), CAPSULE.canonical(second))
        self.assertEqual(first_prompt, second_prompt)
        self.assertEqual(
            hashlib.sha256(CAPSULE.canonical(first)).hexdigest(),
            "25846c55d1ec903580608fb1df39c338d65671bd89da0d44251d1b72613ae399",
        )
        self.assertEqual(
            hashlib.sha256(first_prompt).hexdigest(),
            "dff8e5979d6ccf9435244b609b6ac35dd890a9edd3bbb8d47bb8c1e186420b0e",
        )
        CAPSULE.verify(first, first_prompt)

    def test_all_provenance_digests_are_recorded(self) -> None:
        capsule, prompt = CAPSULE.render(self.source())
        self.assertEqual(capsule["renderer_version"], CAPSULE.RENDERER_VERSION)
        self.assertEqual(len(capsule["role_preset_digest"]), 64)
        self.assertEqual(len(capsule["capsule_digest"]), 64)
        self.assertEqual(capsule["rendered_prompt_digest"], hashlib.sha256(prompt).hexdigest())

    def test_tamper_is_rejected(self) -> None:
        capsule, prompt = CAPSULE.render(self.source())
        capsule["intent"] = "changed"
        with self.assertRaisesRegex(CAPSULE.CapsuleError, "capsule digest mismatch"):
            CAPSULE.verify(capsule, prompt)

    def test_model_visible_secret_fields_and_values_are_rejected(self) -> None:
        for key, value in (("claim_token", "raw"), ("capability_handle", "abc"), ("broker_path", "/run/private"), ("provider_secret", "raw")):
            source = self.source()
            source["role_preset"][key] = value
            with self.subTest(key=key), self.assertRaises(CAPSULE.CapsuleError):
                CAPSULE.render(source)
        source = self.source()
        source["intent"] = "use Bearer abc.def"
        with self.assertRaises(CAPSULE.CapsuleError):
            CAPSULE.render(source)

    def test_dependency_selection_reason_is_mandatory(self) -> None:
        source = self.source()
        del source["dependency_context"][0]["selection_reason"]
        with self.assertRaisesRegex(CAPSULE.CapsuleError, "selection_reason"):
            CAPSULE.render(source)


if __name__ == "__main__":
    unittest.main()
