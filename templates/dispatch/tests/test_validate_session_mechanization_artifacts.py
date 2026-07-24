from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_session_mechanization_artifacts.py"
SPEC = importlib.util.spec_from_file_location("session_mechanization_validator", SCRIPT)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

EXAMPLES_DIR = Path(__file__).parents[1] / "session-mechanization"


def _load_example(name: str) -> dict:
    return json.loads((EXAMPLES_DIR / f"{name}.example.json").read_text(encoding="utf-8"))


class SessionCapsuleValidatorTests(unittest.TestCase):
    def test_shipped_example_is_valid(self) -> None:
        capsule = _load_example("session-capsule")
        VALIDATOR.validate_session_capsule(capsule, Path("session-capsule.example.json"))

    def test_dirty_worktree_requires_patch_digest(self) -> None:
        capsule = copy.deepcopy(_load_example("session-capsule"))
        capsule["git"]["dirty"] = True
        capsule["git"]["patch_digest"] = None
        with self.assertRaisesRegex(ValueError, "patch_digest is required"):
            VALIDATOR.validate_session_capsule(capsule, Path("bad"))

    def test_automatic_claim_requires_explicit_target(self) -> None:
        capsule = copy.deepcopy(_load_example("session-capsule"))
        capsule["target"] = {"rank": "candidate", "ref": "wi:1"}
        capsule["claim"] = {
            "claim_id": "c1",
            "work_item_id": "wi:1",
            "claim_type": "exclusive",
            "acquired_automatically": True,
        }
        with self.assertRaisesRegex(ValueError, "requires target.rank == explicit"):
            VALIDATOR.validate_session_capsule(capsule, Path("bad"))

    def test_raw_transcript_ref_requires_capture_flag(self) -> None:
        capsule = copy.deepcopy(_load_example("session-capsule"))
        capsule["privacy"] = {
            "raw_transcript_captured": False,
            "raw_transcript_ref": {
                "kind": "artifact",
                "source": "agentops:_artifacts/agentops/transcripts/x.json",
                "revision": "sha256:" + "0" * 64,
            },
        }
        with self.assertRaisesRegex(ValueError, "raw_transcript_ref must be null"):
            VALIDATOR.validate_session_capsule(capsule, Path("bad"))

    def test_unknown_schema_version_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "artifact.json"
            path.write_text(json.dumps({"schema_version": "unknown/v9"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown schema_version"):
                VALIDATOR.validate(path)


class ReconciliationProposalValidatorTests(unittest.TestCase):
    def test_shipped_example_is_valid(self) -> None:
        proposal = _load_example("reconciliation-proposal")
        VALIDATOR.validate_reconciliation_proposal(proposal, Path("reconciliation-proposal.example.json"))

    def test_incidental_classification_forbids_target_and_commands(self) -> None:
        proposal = copy.deepcopy(_load_example("reconciliation-proposal"))
        proposal["classification"] = "incidental-no-change"
        with self.assertRaisesRegex(ValueError, "target must be null"):
            VALIDATOR.validate_reconciliation_proposal(proposal, Path("bad"))

    def test_actionable_classification_requires_commands(self) -> None:
        proposal = copy.deepcopy(_load_example("reconciliation-proposal"))
        proposal["proposed_commands"] = []
        with self.assertRaisesRegex(ValueError, "proposed_commands must be non-empty"):
            VALIDATOR.validate_reconciliation_proposal(proposal, Path("bad"))

    def test_rejected_requires_reason(self) -> None:
        proposal = copy.deepcopy(_load_example("reconciliation-proposal"))
        proposal["lifecycle"] = {
            "state": "rejected",
            "decided_at": "2026-07-14T21:00:00Z",
            "decided_by": "dev",
            "rejection_reason": None,
            "superseded_by": None,
        }
        with self.assertRaisesRegex(ValueError, "requires lifecycle.rejection_reason"):
            VALIDATOR.validate_reconciliation_proposal(proposal, Path("bad"))

    def test_superseded_requires_pointer(self) -> None:
        proposal = copy.deepcopy(_load_example("reconciliation-proposal"))
        proposal["lifecycle"] = {
            "state": "superseded",
            "decided_at": "2026-07-14T21:00:00Z",
            "decided_by": "dev",
            "rejection_reason": None,
            "superseded_by": None,
        }
        with self.assertRaisesRegex(ValueError, "requires lifecycle.superseded_by"):
            VALIDATOR.validate_reconciliation_proposal(proposal, Path("bad"))

    def test_pending_forbids_decision_fields(self) -> None:
        proposal = copy.deepcopy(_load_example("reconciliation-proposal"))
        proposal["lifecycle"] = {
            "state": "pending",
            "decided_at": "2026-07-14T21:00:00Z",
            "decided_by": "dev",
            "rejection_reason": None,
            "superseded_by": None,
        }
        with self.assertRaisesRegex(ValueError, "must not carry a decision"):
            VALIDATOR.validate_reconciliation_proposal(proposal, Path("bad"))


class SessionNoteValidatorTests(unittest.TestCase):
    def test_shipped_example_is_valid(self) -> None:
        note = _load_example("session-note")
        VALIDATOR.validate_session_note(note, Path("session-note.example.json"))

    def test_idempotent_revalidation(self) -> None:
        note = _load_example("session-note")
        VALIDATOR.validate_session_note(note, Path("session-note.example.json"))
        VALIDATOR.validate_session_note(note, Path("session-note.example.json"))

    def test_unknown_note_kind_rejected(self) -> None:
        note = copy.deepcopy(_load_example("session-note"))
        note["note_kind"] = "governance"
        with self.assertRaisesRegex(ValueError, "not a recognized kind"):
            VALIDATOR.validate_session_note(note, Path("bad"))

    def test_oversize_body_rejected(self) -> None:
        note = copy.deepcopy(_load_example("session-note"))
        note["body"] = "x" * (VALIDATOR.NOTE_BODY_MAX_BYTES + 1)
        with self.assertRaisesRegex(ValueError, "exceeds .* bytes"):
            VALIDATOR.validate_session_note(note, Path("bad"))

    def test_raw_transcript_ref_requires_capture_flag(self) -> None:
        note = copy.deepcopy(_load_example("session-note"))
        note["privacy"] = {
            "raw_transcript_captured": False,
            "raw_transcript_ref": {
                "kind": "artifact",
                "source": "agentops:_artifacts/agentops/transcripts/x.json",
                "revision": "sha256:" + "0" * 64,
            },
        }
        with self.assertRaisesRegex(ValueError, "raw_transcript_ref must be null"):
            VALIDATOR.validate_session_note(note, Path("bad"))

    def test_via_schema_version_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.json"
            path.write_text(json.dumps(_load_example("session-note")), encoding="utf-8")
            VALIDATOR.validate(path)


class DiscoveryAndMainTests(unittest.TestCase):
    def test_discovers_and_rejects_duplicate_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "session-capsules").mkdir()
            capsule = _load_example("session-capsule")
            (root / "session-capsules" / "a.json").write_text(json.dumps(capsule), encoding="utf-8")
            (root / "session-capsules" / "b.json").write_text(json.dumps(capsule), encoding="utf-8")
            paths = VALIDATOR.discover(root)
            self.assertEqual(len(paths), 2)
            seen: set[str] = set()
            with self.assertRaisesRegex(ValueError, "duplicate artifact id"):
                for path in paths:
                    value = VALIDATOR.validate(path)
                    artifact_id = value["capsule_id"]
                    if artifact_id in seen:
                        raise ValueError(f"{path}: duplicate artifact id {artifact_id!r}")
                    seen.add(artifact_id)


if __name__ == "__main__":
    unittest.main()
