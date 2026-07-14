from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_verification_artifacts.py"
SPEC = importlib.util.spec_from_file_location("contract_validator", SCRIPT)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class RepositoryContractValidatorTests(unittest.TestCase):
    def test_selects_required_surface_and_resolves_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".agents/overlays").mkdir(parents=True)
            (root / "verification/contexts").mkdir(parents=True)
            (root / ".agents/overlays/example.md").write_text("# overlay\n", encoding="utf-8")
            context = {
                "schema_version": "test-context/v1",
                "id": "example.claim",
                "owner_repo": "example",
                "subject": "claim",
                "contract_ref": {"doc_id": "example.claim", "revision": "git:abc"},
                "source_of_truth": "claims-row",
                "depth": 1,
                "backends": ["sqlite"],
                "actors": ["a"],
                "initial_state": [],
                "operations": [{"name": "claim"}],
                "consistency": {"target": "documented-only", "object": "claim"},
                "invariants": ["one-owner"],
                "faults": [],
                "oracles": ["targeted-test"],
                "implementation_anchors": ["src/claims.py:claim"],
            }
            (root / "verification/contexts/claim.json").write_text(json.dumps(context), encoding="utf-8")
            manifest = {
                "schema_version": 1,
                "repo_id": "example",
                "adoption_level": "guidance-only",
                "routing": {"action_classes": {"verify": {"enabled": True}}},
                "skills": {
                    "selected": ["verify-state-protocols"],
                    "overlays": [".agents/overlays/example.md"],
                },
                "risk_surfaces": [{
                    "id": "claim",
                    "paths": ["src/claims/**"],
                    "skills": ["verify-state-protocols"],
                    "context_ids": ["example.claim"],
                    "required_on_change": True,
                }],
                "verification": {"command_families": ["unit"]},
                "hooks": {"publishers": []},
            }
            manifest_path = root / "example.dispatch.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            contexts = {context["id"]: VALIDATOR.validate(root / "verification/contexts/claim.json")}
            surfaces = VALIDATOR.validate_manifest(manifest, manifest_path, root)
            self.assertIn(surfaces[0]["context_ids"][0], contexts)
            selected = VALIDATOR.select_surfaces(surfaces, ["src/claims/store.py"])
            self.assertEqual([surface["id"] for surface in selected], ["claim"])

    def test_rejects_missing_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = {
                "schema_version": 1,
                "repo_id": "example",
                "adoption_level": "guidance-only",
                "routing": {"action_classes": {}},
                "skills": {"selected": ["verify-state-protocols"], "overlays": ["missing.md"]},
                "verification": {"command_families": ["unit"]},
                "hooks": {"publishers": []},
            }
            with self.assertRaisesRegex(ValueError, "overlay does not exist"):
                VALIDATOR.validate_manifest(manifest, root / "example.dispatch.json", root)


if __name__ == "__main__":
    unittest.main()
