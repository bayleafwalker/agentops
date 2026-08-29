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


AT = "2026-07-13T17:00:00+03:00"


def _established_by(actor_type: str = "human") -> dict[str, object]:
    """Provenance for an established receipt.

    `actor_type` records who did it. It is not an approval and no value of it is a
    workflow stage -- an agent-established receipt is as current as a human one.
    """

    return {
        "actor": "example-operator",
        "actor_type": actor_type,
        "at": AT,
        "authority_basis": "delegated",
        "decision_ref": {
            "kind": "sprint-event",
            "source": "sprintctl:example:sprint:17",
            "revision": "event:83",
        },
    }


def _validity(status: str) -> dict[str, object]:
    validity: dict[str, object] = {"effective_from": AT}
    if status == "superseded":
        validity["effective_to"] = "2026-08-29T09:00:00+03:00"
    return validity


def _legacy_ratification() -> dict[str, object]:
    return {
        "authority": "human",
        "ratifier": "example-operator",
        "at": AT,
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
        status: str = "current",
        publication: str = "private",
        predecessor_id: str | None = None,
        predecessor_digest: str = "a" * 64,
    ) -> dict[str, object]:
        receipt = copy.deepcopy(self.receipt)
        receipt["id"] = f"example.2026-07-13.{status}.{publication}"
        receipt["status"] = status
        receipt["publication"] = publication
        receipt["established_by"] = _established_by()
        receipt["validity"] = _validity(status)
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
        self.assertNotIn("established_by", self.receipt)

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
            (properties["established_by"], VALIDATOR.ESTABLISHED_BY_REQUIRED_FIELDS),
            (properties["validity"], VALIDATOR.VALIDITY_REQUIRED_FIELDS),
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
                properties["established_by"]["properties"]["actor_type"]["enum"],
                VALIDATOR.ACTOR_TYPES,
            ),
            (
                properties["established_by"]["properties"]["authority_basis"]["enum"],
                VALIDATOR.AUTHORITY_BASES,
            ),
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
        self.assertEqual(
            by_status["draft"],
            {
                "not": {
                    "anyOf": [
                        {"required": ["established_by"]},
                        {"required": ["validity"]},
                    ]
                }
            },
        )
        for status in VALIDATOR.ESTABLISHED_STATUSES:
            self.assertEqual(
                set(by_status[status]["required"]),
                {"established_by", "validity", "supersedes"},
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
            VALIDATOR.ESTABLISHED_STATUSES,
        )
        self.assertEqual(
            set(publication_condition["then"]["required"]),
            {"established_by", "validity", "supersedes"},
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

    def test_established_receipts_require_provenance_and_validity(self) -> None:
        for status in VALIDATOR.ESTABLISHED_STATUSES:
            with self.subTest(status=status):
                receipt = copy.deepcopy(self.receipt)
                receipt["status"] = status
                with self.assertRaisesRegex(ValueError, "established_by is required"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["established_by"] = _established_by()
                with self.assertRaisesRegex(ValueError, "validity is required"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                # Presence is settled; the rest of the subtest probes shape.
                receipt["validity"] = _validity(status)
                receipt["established_by"] = {
                    "actor": "example-operator",
                    "actor_type": "human",
                    "at": "2026-07-13T17:00:00Z",
                }
                with self.assertRaisesRegex(
                    ValueError, "missing fields: authority_basis, decision_ref"
                ):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["established_by"] = _established_by()
                receipt["established_by"]["actor_type"] = "committee"
                with self.assertRaisesRegex(ValueError, "actor_type must be one of"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["established_by"] = _established_by()
                receipt["established_by"]["authority_basis"] = "approved"
                with self.assertRaisesRegex(ValueError, "authority_basis must be one of"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["established_by"] = _established_by()
                receipt["established_by"]["decision_ref"]["revision"] = "latest"
                with self.assertRaisesRegex(ValueError, "event:<positive integer>"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["established_by"] = _established_by()
                with self.assertRaisesRegex(ValueError, "supersedes is required"):
                    VALIDATOR.validate_receipt(receipt, self.path)

                receipt["id"] = f"example.2026-07-13.{status}"
                receipt["supersedes"] = {
                    "id": self.receipt["id"],
                    "sha256": "a" * 64,
                }
                VALIDATOR.validate_receipt(receipt, self.path)

    def test_any_actor_type_can_establish_a_current_receipt(self) -> None:
        # The point of the v2 model: provenance is recorded, not gated. An agent- or
        # automation-established receipt is exactly as current as a human-established
        # one, so no workflow can require a human merely because a human exists.
        for actor_type in sorted(VALIDATOR.ACTOR_TYPES):
            with self.subTest(actor_type=actor_type):
                receipt = self._successor()
                receipt["established_by"] = _established_by(actor_type)
                VALIDATOR.validate_receipt(receipt, self.path)

    def test_superseded_requires_a_closed_validity_interval(self) -> None:
        receipt = self._successor(status="superseded")
        del receipt["validity"]["effective_to"]
        with self.assertRaisesRegex(ValueError, "effective_to is required"):
            VALIDATOR.validate_receipt(receipt, self.path)

        receipt["validity"]["effective_to"] = "2020-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "must not precede"):
            VALIDATOR.validate_receipt(receipt, self.path)

    def test_ratified_is_gone_from_the_lifecycle(self) -> None:
        self.assertNotIn("ratified", VALIDATOR.STATUSES)
        self.assertNotIn("ratified", self.schema["properties"]["status"]["enum"])
        self.assertNotIn("ratification", self.schema["properties"])

        receipt = self._successor()
        receipt["status"] = "ratified"
        with self.assertRaisesRegex(ValueError, "status must be one of"):
            VALIDATOR.validate_receipt(receipt, self.path)

    def test_v1_receipts_still_validate_by_migration(self) -> None:
        # Compatibility: an unmigrated v1 file on disk keeps validating. `ratified`
        # maps to `current`, and the literal `authority: human` assertion becomes
        # `authority_basis: owner-reserved`, which is what it was used to mean.
        legacy = copy.deepcopy(self.receipt)
        legacy["schema_version"] = "capability-receipt/v1"
        legacy["id"] = "example.2026-07-13.legacy"
        legacy["status"] = "ratified"
        legacy["ratification"] = _legacy_ratification()
        legacy["supersedes"] = {"id": self.receipt["id"], "sha256": "a" * 64}
        VALIDATOR.validate_receipt(legacy, self.path)

        migrated = VALIDATOR.migrate_v1(legacy)
        self.assertEqual(migrated["schema_version"], "capability-receipt/v2")
        self.assertEqual(migrated["status"], "current")
        self.assertNotIn("ratification", migrated)
        self.assertEqual(migrated["established_by"]["actor"], "example-operator")
        self.assertEqual(migrated["established_by"]["actor_type"], "human")
        # The v1 assertion recorded that a person acted, not a basis; no basis is
        # owner-reserved, so it lands as the ordinary one.
        self.assertEqual(migrated["established_by"]["authority_basis"], "delegated")
        self.assertEqual(migrated["validity"]["effective_from"], AT)

    def test_basis_for_is_a_dependency_relation(self) -> None:
        # Canonicality is what a receipt is the basis for, not a grade of approval.
        receipt = self._successor()
        receipt["basis_for"] = ["sprintctl-design", "composition-v4"]
        VALIDATOR.validate_receipt(receipt, self.path)

        receipt["basis_for"] = ["not a bare identifier"]
        with self.assertRaises(ValueError):
            VALIDATOR.validate_receipt(receipt, self.path)

    def test_candidate_and_published_require_an_attested_successor(self) -> None:
        for publication in VALIDATOR.PUBLICATION_SUCCESSOR_STATES:
            with self.subTest(publication=publication):
                receipt = copy.deepcopy(self.receipt)
                receipt["publication"] = publication
                with self.assertRaisesRegex(
                    ValueError,
                    "requires a current or superseded established successor",
                ):
                    VALIDATOR.validate_receipt(receipt, self.path)

                for status in VALIDATOR.ESTABLISHED_STATUSES:
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
            successor = root / "02-current.json"
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
