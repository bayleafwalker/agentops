from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


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


class SessionCompletionObservedValidatorTests(unittest.TestCase):
    def test_shipped_example_is_valid(self) -> None:
        event = _load_example("session-completion-observed")
        VALIDATOR.validate_session_completion_observed(event, Path("completion.example.json"))

    def test_dispatch_correlations_are_atomic(self) -> None:
        event = copy.deepcopy(_load_example("session-completion-observed"))
        event["attempt_id"] = None
        with self.assertRaisesRegex(ValueError, "must both be null or both be present"):
            VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_stream_position_must_be_positive_integer(self) -> None:
        for invalid in (0, -1, True, "1"):
            with self.subTest(invalid=invalid):
                event = copy.deepcopy(_load_example("session-completion-observed"))
                event["origin_sequence"] = invalid
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_invalid_terminal_combinations_are_rejected(self) -> None:
        cases = [
            ({"kind": "succeeded", "exit_code": 1, "reason_code": "completed", "retryable": False}, "succeeded requires"),
            ({"kind": "failed", "exit_code": 0, "reason_code": "process-exit", "retryable": True}, "non-zero exit_code"),
            ({"kind": "timed-out", "exit_code": None, "reason_code": "cancelled", "retryable": True}, "invalid for terminal.kind"),
            ({"kind": "end-inferred", "exit_code": 9, "reason_code": "crash-inferred", "retryable": True}, "requires a null exit_code"),
        ]
        for terminal, message in cases:
            with self.subTest(terminal=terminal):
                event = copy.deepcopy(_load_example("session-completion-observed"))
                event["terminal"] = terminal
                with self.assertRaisesRegex(ValueError, message):
                    VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_unstable_identities_are_rejected(self) -> None:
        event = copy.deepcopy(_load_example("session-completion-observed"))
        event["event_id"] = "session-42"
        with self.assertRaisesRegex(ValueError, "lowercase UUID"):
            VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_prohibited_content_fields_are_rejected_at_any_depth(self) -> None:
        for key in (
            "prompt", "transcript", "raw_output", "environment", "claim_token",
            "api_key", "api-key", "apiKey", "command_output", "commandOutput",
            "failure_details", "failureDetails", "raw_output", "raw-output", "rawOutput",
            "claim_proof", "claim-proof", "claimProof", "request_snapshot",
            "request-snapshot", "requestSnapshot", "access_token", "access-token",
            "accessToken", "client_secret", "client-secret", "clientSecret",
        ):
            with self.subTest(key=key):
                event = copy.deepcopy(_load_example("session-completion-observed"))
                event["additive"] = {key: "must never appear"}
                with self.assertRaisesRegex(ValueError, "prohibited completion field"):
                    VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_privacy_assertions_must_all_be_true(self) -> None:
        event = copy.deepcopy(_load_example("session-completion-observed"))
        event["privacy"]["raw_output_absent"] = False
        with self.assertRaisesRegex(ValueError, "every completion privacy assertion"):
            VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_secret_like_additive_value_is_rejected(self) -> None:
        event = copy.deepcopy(_load_example("session-completion-observed"))
        event["future_safe_scalar"] = "Bearer abcdefghijklmnop"
        with self.assertRaisesRegex(ValueError, "secret-like content"):
            VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_additive_unknown_field_is_accepted(self) -> None:
        event = copy.deepcopy(_load_example("session-completion-observed"))
        event["future_safe_scalar"] = "value"
        VALIDATOR.validate_session_completion_observed(event, Path("event"))

    def test_observation_cannot_precede_completion(self) -> None:
        event = copy.deepcopy(_load_example("session-completion-observed"))
        event["observed_at"] = "2026-08-09T11:00:01Z"
        with self.assertRaisesRegex(ValueError, "started_at <= completed_at <= observed_at"):
            VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_absolute_ref_is_rejected(self) -> None:
        event = copy.deepcopy(_load_example("session-completion-observed"))
        event["refs"][0]["source"] = "/projects/dev/secret/capsule.json"
        with self.assertRaisesRegex(ValueError, "absolute path is prohibited"):
            VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_absolute_paths_are_rejected_recursively(self) -> None:
        for absolute in ("/projects/dev/private", "C:\\Users\\operator\\secret", "\\\\server\\share\\secret"):
            with self.subTest(absolute=absolute):
                event = copy.deepcopy(_load_example("session-completion-observed"))
                event["future_safe"] = {"nested": [absolute]}
                with self.assertRaisesRegex(ValueError, "absolute path is prohibited"):
                    VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_schema_shape_and_scalar_types_are_enforced(self) -> None:
        mutations = [
            (lambda event: event["terminal"].update(retryable=1), "terminal.retryable must be a boolean"),
            (lambda event: event["terminal"].update(exit_code=True), "terminal.exit_code must be null or an integer"),
            (lambda event: event["evidence"].update(dirty=0), "evidence.dirty must be a boolean"),
            (lambda event: event.update(model="opencode-go"), "model must be null or an object"),
            (lambda event: event.update(model={"name": "x", "version": 1}), "model.version must be a string"),
            (lambda event: event["repo"].update(repo_id="repo-1"), "repo.repo_id must be a lowercase UUID"),
            (lambda event: event.update(refs={}), "refs must be an array"),
            (lambda event: event.update(evidence=[]), "evidence must be an object"),
            (lambda event: event["evidence"].update(verification=[]), "evidence.verification must be an object"),
            (lambda event: event.update(privacy=[]), "privacy must be an object"),
        ]
        for mutate, message in mutations:
            with self.subTest(message=message):
                event = copy.deepcopy(_load_example("session-completion-observed"))
                mutate(event)
                with self.assertRaisesRegex(ValueError, message):
                    VALIDATOR.validate_session_completion_observed(event, Path("bad"))

    def test_via_schema_version_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "completion.json"
            path.write_text(json.dumps(_load_example("session-completion-observed")), encoding="utf-8")
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

    def test_main_rejects_duplicate_completion_stream_positions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            completions = root / "session-completions"
            completions.mkdir()
            first = _load_example("session-completion-observed")
            second = copy.deepcopy(first)
            second["event_id"] = "5e6f7081-92a3-4b4c-8d0e-4f5061728394"
            (completions / "a.json").write_text(json.dumps(first), encoding="utf-8")
            (completions / "b.json").write_text(json.dumps(second), encoding="utf-8")
            with mock.patch("sys.argv", [str(SCRIPT), "--root", str(root)]):
                with self.assertRaisesRegex(ValueError, "duplicate origin stream position"):
                    VALIDATOR.main()


if __name__ == "__main__":
    unittest.main()
