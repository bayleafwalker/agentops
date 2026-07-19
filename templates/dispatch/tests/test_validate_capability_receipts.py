from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


DISPATCH_ROOT = Path(__file__).parents[1]
SCRIPT = DISPATCH_ROOT / "scripts" / "validate_capability_receipts.py"
EXAMPLE = DISPATCH_ROOT / "capability-receipt" / "example.json"
SCHEMA = DISPATCH_ROOT / "capability-receipt" / "capability-receipt.schema.json"
SPEC = importlib.util.spec_from_file_location("capability_receipt_validator", SCRIPT)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def _human_attestation() -> dict[str, object]:
    return {
        "authority": "human",
        "ratifier": "example-operator",
        "at": "2026-07-13T17:00:00+03:00",
        "decision_ref": {
            "kind": "sprint-event",
            "source": "sprintctl:example:sprint:17",
            "revision": "event:83",
        },
    }


class CapabilityReceiptValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.receipt = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.path = Path("receipt.json")

    def _successor(
        self,
        *,
        status: str = "ratified",
        publication: str = "private",
        predecessor_id: str | None = None,
        predecessor_digest: str = "a" * 64,
    ) -> dict[str, object]:
        receipt = copy.deepcopy(self.receipt)
        receipt["id"] = f"example.2026-07-13.{status}.{publication}"
        receipt["status"] = status
        receipt["publication"] = publication
        receipt["ratification"] = _human_attestation()
        receipt["supersedes"] = {
            "id": predecessor_id or self.receipt["id"],
            "sha256": predecessor_digest,
        }
        return receipt

    @staticmethod
    def _write_receipt(path: Path, receipt: dict[str, object]) -> str:
        path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_example_is_a_valid_safe_draft(self) -> None:
        VALIDATOR.validate_receipt(self.receipt, EXAMPLE)

        self.assertEqual(self.receipt["status"], "draft")
        self.assertEqual(self.receipt["publication"], "private")
        self.assertTrue(self.receipt["id"].startswith(f"{self.receipt['project']}."))
        self.assertNotIn("ratification", self.receipt)

    def test_receipt_id_must_use_the_exact_project_prefix(self) -> None:
        receipt_id_pattern = self.schema["$defs"]["receiptIdentifier"]["allOf"][1][
            "pattern"
        ]
        self.assertIsNotNone(re.fullmatch(receipt_id_pattern, self.receipt["id"]))

        for receipt_id in ("other.receipt", "example", "example.", "example_receipt"):
            with self.subTest(receipt_id=receipt_id):
                receipt = copy.deepcopy(self.receipt)
                receipt["id"] = receipt_id
                with self.assertRaisesRegex(ValueError, r"must start with 'example\.'"):
                    VALIDATOR.validate_receipt(receipt, self.path)

        receipt = copy.deepcopy(self.receipt)
        receipt["project"] = "example.project"
        receipt["id"] = "example.project.release-boundary"
        VALIDATOR.validate_receipt(receipt, self.path)

    def test_schema_and_validator_fields_and_enums_stay_in_parity(self) -> None:
        properties = self.schema["properties"]
        self.assertEqual(set(self.schema["required"]), VALIDATOR.REQUIRED_FIELDS)
        self.assertEqual(
            set(properties),
            VALIDATOR.REQUIRED_FIELDS | VALIDATOR.OPTIONAL_FIELDS,
        )

        nested_fields = (
            (properties["boundary"], VALIDATOR.BOUNDARY_REQUIRED_FIELDS),
            (properties["evidence"]["items"], VALIDATOR.EVIDENCE_REQUIRED_FIELDS),
            (properties["unknowns"]["items"], VALIDATOR.UNKNOWN_REQUIRED_FIELDS),
            (properties["ratification"], VALIDATOR.RATIFICATION_REQUIRED_FIELDS),
            (self.schema["$defs"]["immutableRef"], VALIDATOR.IMMUTABLE_REF_REQUIRED_FIELDS),
            (self.schema["$defs"]["receiptRef"], VALIDATOR.RECEIPT_REF_REQUIRED_FIELDS),
        )
        for schema_fragment, validator_fields in nested_fields:
            with self.subTest(fragment=schema_fragment.get("description", "fields")):
                self.assertEqual(set(schema_fragment["required"]), validator_fields)

        enum_pairs = (
            (properties["status"]["enum"], VALIDATOR.STATUSES),
            (properties["boundary"]["properties"]["kind"]["enum"], VALIDATOR.BOUNDARY_KINDS),
            (properties["locus"]["enum"], VALIDATOR.LOCI),
            (properties["publication"]["enum"], VALIDATOR.PUBLICATIONS),
            (
                self.schema["$defs"]["immutableRef"]["properties"]["kind"]["enum"],
                VALIDATOR.REFERENCE_KINDS,
            ),
        )
        for schema_values, validator_values in enum_pairs:
            self.assertEqual(set(schema_values), validator_values)

        revision_branches = self.schema["$defs"]["immutableRef"]["oneOf"]
        self.assertEqual(
            {
                branch["properties"]["kind"]["const"]
                for branch in revision_branches
            },
            VALIDATOR.REFERENCE_KINDS,
        )

    def test_schema_lifecycle_conditions_mirror_normative_validator(self) -> None:
        conditions = self.schema["allOf"]
        by_status = {
            condition["if"]["properties"]["status"]["const"]: condition["then"]
            for condition in conditions
            if "status" in condition["if"]["properties"]
        }
        self.assertEqual(set(by_status), VALIDATOR.STATUSES)
        self.assertEqual(by_status["draft"], {"not": {"required": ["ratification"]}})
        for status in VALIDATOR.SUCCESSOR_STATUSES:
            self.assertEqual(
                set(by_status[status]["required"]),
                {"ratification", "supersedes"},
            )

        publication_condition = next(
            condition
            for condition in conditions
            if "publication" in condition["if"]["properties"]
        )
        self.assertEqual(
            set(publication_condition["if"]["properties"]["publication"]["enum"]),
            VALIDATOR.PUBLICATION_SUCCESSOR_STATES,
        )
        self.assertEqual(
            set(publication_condition["then"]["properties"]["status"]["enum"]),
            VALIDATOR.SUCCESSOR_STATUSES,
        )
        self.assertEqual(
            set(publication_condition["then"]["required"]),
            {"ratification", "supersedes"},
        )

    def test_revision_vectors_match_validator_and_schema_patterns(self) -> None:
        vectors = (
            ("git-commit", "a" * 40, True),
            ("git-commit", "b" * 64, True),
            ("git-commit", "A" * 40, False),
            ("git-commit", "git:" + "a" * 40, False),
            ("git-commit", "main", False),
            ("sprint-event", "event:1", True),
            ("sprint-event", "event:902", True),
            ("sprint-event", "event:0", False),
            ("sprint-event", "event:-1", False),
            ("sprint-event", "latest", False),
            ("artifact", "sha256:" + "c" * 64, True),
            ("artifact", "c" * 64, False),
            ("artifact", "sha256:" + "C" * 64, False),
            ("verification-result", "sha256:" + "d" * 64, True),
            ("verification-result", "sha256:" + "d" * 63, False),
            ("document", "e" * 40, True),
            ("document", "e" * 64, True),
            ("document", "sha256:" + "e" * 64, True),
            ("document", "event:1", False),
            ("release", "f" * 40, True),
            ("release", "sha256:" + "f" * 64, True),
            ("release", "HEAD", False),
        )
        branch_patterns = {
            branch["properties"]["kind"]["const"]: branch["properties"]["revision"]["pattern"]
            for branch in self.schema["$defs"]["immutableRef"]["oneOf"]
        }

        for kind, revision, expected in vectors:
            with self.subTest(kind=kind, revision=revision):
                try:
                    VALIDATOR._validate_revision(revision, kind, "ref.revision", self.path)
                except ValueError:
                    validator_accepts = False
                else:
                    validator_accepts = True
                schema_pattern_accepts = re.fullmatch(branch_patterns[kind], revision) is not None
                self.assertEqual(validator_accepts, expected)
                self.assertEqual(schema_pattern_accepts, expected)

    def test_ratified_and_superseded_receipts_require_procedural_attestation(self) -> None:
        for status in VALIDATOR.SUCCESSOR_STATUSES:
            with self.subTest(status=status):
                receipt = copy.deepcopy(self.receipt)
                receipt["status"] = status
                with self.assertRaisesRegex(ValueError, "ratification is required"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["ratification"] = {
                    "authority": "human",
                    "ratifier": "example-operator",
                    "at": "2026-07-13T17:00:00Z",
                }
                with self.assertRaisesRegex(ValueError, "missing fields: decision_ref"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["ratification"] = _human_attestation()
                receipt["ratification"]["authority"] = "model"
                with self.assertRaisesRegex(ValueError, "procedural assertion human"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["ratification"] = _human_attestation()
                receipt["ratification"]["decision_ref"]["revision"] = "latest"
                with self.assertRaisesRegex(ValueError, "event:<positive integer>"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["ratification"] = _human_attestation()
                with self.assertRaisesRegex(ValueError, "supersedes is required"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["id"] = f"example.2026-07-13.{status}"
                receipt["supersedes"] = {
                    "id": self.receipt["id"],
                    "sha256": "a" * 64,
                }
                VALIDATOR.validate_receipt(receipt, self.path)

    def test_candidate_and_published_require_an_attested_successor(self) -> None:
        for publication in VALIDATOR.PUBLICATION_SUCCESSOR_STATES:
            with self.subTest(publication=publication):
                receipt = copy.deepcopy(self.receipt)
                receipt["publication"] = publication
                with self.assertRaisesRegex(
                    ValueError,
                    "requires a ratified or superseded procedurally attested successor",
                ):
                    VALIDATOR.validate_receipt(receipt, self.path)

                for status in VALIDATOR.SUCCESSOR_STATUSES:
                    VALIDATOR.validate_receipt(
                        self._successor(status=status, publication=publication),
                        self.path,
                    )

    def test_sprint_close_boundary_uses_exact_event_reference_shape(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["boundary"] = {
            "kind": "sprint-close",
            "ref": {
                "kind": "sprint-event",
                "source": "sprintctl:example:sprint:17",
                "revision": "event:83",
            },
        }
        VALIDATOR.validate_receipt(receipt, self.path)

        receipt["boundary"]["ref"]["source"] = "sprintctl:other:sprint:17"
        with self.assertRaisesRegex(ValueError, "sprintctl:example:sprint:<id>"):
            VALIDATOR.validate_receipt(receipt, self.path)

        receipt["boundary"]["ref"] = {
            "kind": "artifact",
            "source": "sprintctl:example:sprint:17",
            "revision": "sha256:" + "a" * 64,
        }
        with self.assertRaisesRegex(ValueError, "must be sprint-event"):
            VALIDATOR.validate_receipt(receipt, self.path)

    def test_rejects_unstructured_refs_unknown_loss_scoring_and_wrong_enums(self) -> None:
        receipt = copy.deepcopy(self.receipt)
        receipt["evidence"][0]["ref"] = "sha:0123456"
        with self.assertRaisesRegex(ValueError, r"evidence\[0\]\.ref must be an object"):
            VALIDATOR.validate_receipt(receipt, self.path)

        receipt = copy.deepcopy(self.receipt)
        del receipt["expectation_ref"]
        VALIDATOR.validate_receipt(receipt, self.path)
        del receipt["unknowns"]
        with self.assertRaisesRegex(ValueError, "missing fields: unknowns"):
            VALIDATOR.validate_receipt(receipt, self.path)

        for field, value in (("score", 9), ("activity", ["ran tests"])):
            with self.subTest(field=field):
                receipt = copy.deepcopy(self.receipt)
                receipt[field] = value
                with self.assertRaisesRegex(ValueError, f"unexpected fields: {field}"):
                    VALIDATOR.validate_receipt(receipt, self.path)

        cases = (
            ("locus", "assisted", "locus must be one of"),
            ("status", "complete", "status must be one of"),
            ("publication", "public", "publication must be one of"),
            ("transfer", "another-project", "transfer must be an array"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                receipt = copy.deepcopy(self.receipt)
                receipt[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    VALIDATOR.validate_receipt(receipt, self.path)

    def test_cli_resolves_exact_lineage_across_a_directory_before_printing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            predecessor = root / "01-draft.json"
            predecessor_digest = self._write_receipt(predecessor, self.receipt)
            successor = root / "02-ratified.json"
            successor_receipt = self._successor(predecessor_digest=predecessor_digest)
            successor_digest = self._write_receipt(successor, successor_receipt)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--expected-project", "example"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                result.stdout.strip().splitlines(),
                [
                    f"ok {predecessor} receipt_sha256={predecessor_digest}",
                    f"ok {successor} receipt_sha256={successor_digest}",
                ],
            )
            self.assertNotIn(self.receipt["before"], result.stdout)

    def test_cli_rejects_missing_or_forged_lineage_without_partial_output(self) -> None:
        cases = ("missing", "wrong-digest", "wrong-project")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                predecessor_receipt = copy.deepcopy(self.receipt)
                predecessor = root / "01-draft.json"
                predecessor_digest = self._write_receipt(predecessor, predecessor_receipt)

                successor_receipt = self._successor(
                    predecessor_digest=predecessor_digest,
                )
                expected_message: str
                if case == "missing":
                    successor_receipt["supersedes"]["id"] = "example.missing"
                    expected_message = "does not resolve 'example.missing'"
                    predecessor.unlink()
                elif case == "wrong-digest":
                    successor_receipt["supersedes"]["sha256"] = "b" * 64
                    expected_message = "does not match the exact bytes"
                else:
                    predecessor_receipt["project"] = "other"
                    predecessor_receipt["id"] = "other.prior"
                    predecessor_digest = self._write_receipt(predecessor, predecessor_receipt)
                    successor_receipt["supersedes"]["id"] = predecessor_receipt["id"]
                    successor_receipt["supersedes"]["sha256"] = predecessor_digest
                    expected_message = "predecessor from the same project"

                successor = root / "02-successor.json"
                self._write_receipt(successor, successor_receipt)
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), str(root)],
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertEqual(result.returncode, 1)
                self.assertIn(expected_message, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_cli_rejects_duplicate_receipt_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.json"
            second = root / "second.json"
            self._write_receipt(first, self.receipt)
            self._write_receipt(second, self.receipt)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("duplicates", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_cli_can_enforce_expected_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = Path(tmp) / "receipt.json"
            self._write_receipt(receipt_path, self.receipt)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(receipt_path),
                    "--expected-project",
                    "different-project",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("project must be 'different-project'", result.stderr)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
