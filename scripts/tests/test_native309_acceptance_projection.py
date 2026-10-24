from __future__ import annotations

import hashlib
import json
import unittest

from scripts.project_native309_acceptance import (
    MUTATIONS,
    PINNED_IMAGE,
    ReceiptError,
    project,
)


COMMIT = "7fabc910445292eb7dd5acbac636f5fd572ebf43"


def receipt() -> dict:
    return {
        "credentials_loaded": False,
        "external_exporters": False,
        "full_matrix": {"cases": 62, "exported": 54, "passed": True, "refused": 8},
        "image": PINNED_IMAGE,
        "mutations": [
            {
                "mutant_expected_drop": should_drop,
                "mutant_export_count": count,
                "mutant_input_sent_after_control": True,
                "name": name,
                "passed": True,
                "positive_control_exported": True,
            }
            for name, (should_drop, count) in MUTATIONS.items()
        ],
        "production_access": False,
        "rendered_sha256": "4" * 64,
        "schema": "native309-alloy-acceptance/v1",
        "synthetic_inputs_only": True,
    }


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.dumps(receipt(), sort_keys=True).encode()

    def test_projection_keeps_only_metadata_and_hashes(self) -> None:
        result = project(self.raw, source_commit=COMMIT)
        self.assertEqual(result["source"]["commit"], COMMIT)
        self.assertEqual(result["receipt_sha256"], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(result["full_matrix"]["exported_records"], 54)
        self.assertEqual(len(result["mutations"]), 7)
        self.assertFalse(result["credentials_included"])
        self.assertFalse(result["telemetry_payloads_included"])
        self.assertNotIn("requests", json.dumps(result))

    def test_wrong_image_is_refused(self) -> None:
        doc = receipt()
        doc["image"] = "docker.io/grafana/alloy:latest"
        with self.assertRaisesRegex(ReceiptError, "pinned Alloy digest"):
            project(json.dumps(doc).encode(), source_commit=COMMIT)

    def test_unknown_input_fields_are_not_projected(self) -> None:
        doc = receipt()
        doc["exports"] = [{"body": "synthetic-but-still-not-for-projection"}]
        with self.assertRaisesRegex(ReceiptError, "unexpected shape"):
            project(json.dumps(doc).encode(), source_commit=COMMIT)

    def test_mutation_mismatch_is_refused(self) -> None:
        doc = receipt()
        doc["mutations"][0]["mutant_export_count"] += 1
        with self.assertRaisesRegex(ReceiptError, "did not match its passing oracle"):
            project(json.dumps(doc).encode(), source_commit=COMMIT)

    def test_source_commit_must_be_full_sha(self) -> None:
        with self.assertRaisesRegex(ReceiptError, "full lowercase Git SHA"):
            project(self.raw, source_commit="7fabc910")

    def test_oversized_receipt_is_refused_before_parsing(self) -> None:
        with self.assertRaisesRegex(ReceiptError, "32 KiB metadata limit"):
            project(b" " * (32 * 1024 + 1), source_commit=COMMIT)


if __name__ == "__main__":
    unittest.main()
