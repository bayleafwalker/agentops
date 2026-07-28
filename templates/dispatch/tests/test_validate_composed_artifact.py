from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_composed_artifact.py"
SPEC = importlib.util.spec_from_file_location("composed_artifact_validator", SCRIPT)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


REVISION = "a" * 40
ARTIFACT_SHA = "b" * 64
PIN_SHA = "c" * 64
IMAGE_SHA = "d" * 64


def evidence() -> dict:
    operations = ["work.read.item", "work.read.items"]
    digest = VALIDATOR.operation_digest(operations)
    return {
        "schema_version": "composed-artifact/v1",
        "domain": "work",
        "cli": {
            "source_revision": REVISION,
            "commands": [
                {
                    "command": "item show",
                    "disposition": "catalog",
                    "operations": ["work.read.item"],
                },
                {
                    "command": "item list",
                    "disposition": "catalog",
                    "operations": ["work.read.items"],
                },
                {
                    "command": "item list --fzf",
                    "disposition": "unavailable",
                    "operations": [],
                },
            ],
        },
        "served_facade": {
            "source_revision": REVISION,
            "routes": [
                {"command": "item show", "operation": "work.read.item"},
                {"command": "item list", "operation": "work.read.items"},
            ],
        },
        "released_adapter": {
            "source_revision": REVISION,
            "distribution": "sprintctl",
            "distribution_version": "0.2.10",
            "artifact_sha256": ARTIFACT_SHA,
            "operations": operations,
            "operations_sha256": digest,
        },
        "composition": {
            "source_revision": REVISION,
            "distribution": "sprintctl",
            "distribution_version": "0.2.10",
            "artifact_sha256": ARTIFACT_SHA,
            "pin_manifest_sha256": PIN_SHA,
            "operations": operations,
            "operations_sha256": digest,
        },
        "deployment": {
            "environment": "vuoro-shared",
            "image_digest": f"sha256:{IMAGE_SHA}",
            "observed_at": "2026-07-28T00:00:00Z",
            "operations": operations,
            "operations_sha256": digest,
        },
    }


class ComposedArtifactValidatorTests(unittest.TestCase):
    def test_accepts_continuous_composition_evidence(self) -> None:
        VALIDATOR.validate(evidence())

    def test_rejects_cli_facade_drift(self) -> None:
        value = evidence()
        value["served_facade"]["routes"].pop()
        with self.assertRaisesRegex(ValueError, "CLI/facade route mismatch"):
            VALIDATOR.validate(value)

    def test_rejects_unavailable_fallback_route(self) -> None:
        value = evidence()
        value["cli"]["commands"][2]["operations"] = ["work.read.items"]
        with self.assertRaisesRegex(ValueError, "must not name a served operation"):
            VALIDATOR.validate(value)

    def test_rejects_released_adapter_omission(self) -> None:
        value = evidence()
        value["released_adapter"]["operations"] = ["work.read.item"]
        value["released_adapter"]["operations_sha256"] = VALIDATOR.operation_digest(
            ["work.read.item"]
        )
        with self.assertRaisesRegex(ValueError, "missing served facade operations"):
            VALIDATOR.validate(value)

    def test_rejects_composition_artifact_substitution(self) -> None:
        value = evidence()
        value["composition"]["artifact_sha256"] = "e" * 64
        with self.assertRaisesRegex(ValueError, "does not pin"):
            VALIDATOR.validate(value)

    def test_rejects_deployed_catalog_drift(self) -> None:
        value = evidence()
        value["deployment"]["operations"] = ["work.read.item"]
        value["deployment"]["operations_sha256"] = VALIDATOR.operation_digest(
            ["work.read.item"]
        )
        with self.assertRaisesRegex(ValueError, "deployed operation catalogs differ"):
            VALIDATOR.validate(value)


if __name__ == "__main__":
    unittest.main()
