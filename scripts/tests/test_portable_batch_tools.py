"""Failure-first qualification for the proposed local portable-batch tools.

These tests use only disposable local Git repositories and synthetic receipts.
They do not exercise an owner API or claim the caller-supplied evidence is
authentic.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prepare_portable_batch as prepare_tool
import review_portable_candidate as review_tool
import verify_portable_batch_pins as pins_tool
import schema_check


OID = "a" * 40
TREE = "b" * 40
DIGEST = "c" * 64


def run_request() -> dict:
    return {
        "schema": "portable-programme-run-request/v1",
        "request_id": "batch-1",
        "goal": "Prepare a local candidate packet.",
        "completion_evidence": ["A digest-bound packet is produced."],
        "repositories": [{
            "owner": "agentops",
            "repository_id": "github.com/bayleafwalker/agentops",
            "source_branch": "main",
            "source_commit": OID,
            "target_branch": "main",
            "permitted_paths": ["scripts/example.py"],
            "access_class": "source-read",
            "requested_harness": "codex",
            "requested_model": "test-model",
        }],
        "dependencies": [],
        "bounds": {
            "deadline_utc": "2026-10-25T12:00:00Z",
            "spend_limit_usd": "0",
            "aggregate_concurrency": 1,
            "replanning_limit": 0,
            "checkpoint_interval_seconds": 60,
            "stop_conditions": ["Stop when source observations are stale."],
            "escalation_route": "manual review",
        },
        "readiness_observations": [],
        "review_policy": "independent-exact-head-review",
        "landing_policy": "candidate-only",
    }


def review_request() -> dict:
    return {
        "schema": "portable-candidate-review-request/v1",
        "request_id": "review-1",
        "candidate": {
            "owner": "agentops",
            "repository_id": "github.com/bayleafwalker/agentops",
            "branch": "candidate",
            "commit": OID,
            "target_branch": "main",
            "author_id": "author@example.invalid",
        },
        "evaluated_at": "2026-10-25T12:00:00Z",
        "max_receipt_age_seconds": 3600,
        "required_checks": ["unit"],
        "receipts": [{
            "receipt_id": "receipt-1",
            "kind": "check",
            "check_name": "unit",
            "subject_commit": OID,
            "subject_tree": TREE,
            "result": "passed",
            "observed_at": "2026-10-25T11:30:00Z",
            "valid_until": "2026-10-25T13:00:00Z",
            "evidence_sha256": DIGEST,
        }, {
            "receipt_id": "review-1",
            "kind": "independent-review",
            "reviewer_id": "reviewer@example.invalid",
            "subject_commit": OID,
            "subject_tree": TREE,
            "result": "passed",
            "observed_at": "2026-10-25T11:30:00Z",
            "valid_until": "2026-10-25T13:00:00Z",
            "evidence_sha256": DIGEST,
        }],
    }


class PortableRequestBoundaryTests(unittest.TestCase):
    def load_text(self, text: str) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "request.json"
            path.write_text(text, encoding="utf-8")
            return prepare_tool._load_request(path)

    def test_strict_json_refuses_duplicate_nonfinite_depth_and_oversize(self) -> None:
        invalid = [
            '{"schema":"a","schema":"b"}',
            '{"value":NaN}',
            "{" + '"x":' * 0 + "[" * 65 + "0" + "]" * 65 + "}",
        ]
        for text in invalid:
            with self.subTest(text=text[:40]), self.assertRaises(prepare_tool.PacketError):
                self.load_text(text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversize.json"
            path.write_bytes(b" " * (prepare_tool.MAX_REQUEST_BYTES + 1))
            with self.assertRaisesRegex(prepare_tool.PacketError, "exceeds 1 MiB"):
                prepare_tool._load_request(path)

    def test_request_schema_profile_refuses_unknown_scope_and_unsafe_paths(self) -> None:
        valid = prepare_tool._validate_request(run_request())
        self.assertEqual(valid["repositories"][0]["permitted_paths"], ["scripts/example.py"])
        for mutate in (
            lambda value: value.update(extra_authority="dispatch"),
            lambda value: value["repositories"][0].update(permitted_paths=["../outside"]),
            lambda value: value["repositories"][0].update(access_class="credential-write"),
            lambda value: value["bounds"].update(aggregate_concurrency=True),
        ):
            candidate = copy.deepcopy(run_request())
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(prepare_tool.PacketError):
                prepare_tool._validate_request(candidate)

    def test_published_json_schemas_match_runtime_required_shape_and_bounds(self) -> None:
        schema_root = Path(__file__).resolve().parents[2] / "schemas"
        run_schema = json.loads((schema_root / "portable-programme-run-request.v1.schema.json").read_text())
        repository_schema = run_schema["$defs"]["repository"]
        request_required = {
            "schema", "request_id", "goal", "completion_evidence", "repositories",
            "dependencies", "bounds", "readiness_observations", "review_policy", "landing_policy",
        }
        repository_required = {
            "owner", "repository_id", "source_branch", "source_commit", "target_branch",
            "permitted_paths", "access_class", "requested_harness", "requested_model",
        }
        self.assertEqual(set(run_schema["required"]), request_required)
        self.assertEqual(set(repository_schema["required"]), repository_required)
        self.assertIs(run_schema["additionalProperties"], False)
        self.assertIs(repository_schema["additionalProperties"], False)
        self.assertEqual(run_schema["$defs"]["text160"]["maxLength"], 160)
        self.assertEqual(run_schema["$defs"]["bounds"]["properties"]["aggregate_concurrency"]["maximum"], 32)
        self.assertEqual(schema_check.validate(run_request(), run_schema), [])
        unsafe_scope = run_request()
        unsafe_scope["repositories"][0]["permitted_paths"] = ["../outside"]
        self.assertTrue(schema_check.validate(unsafe_scope, run_schema))

        review_schema = json.loads((schema_root / "portable-candidate-review-request.v1.schema.json").read_text())
        self.assertIs(review_schema["additionalProperties"], False)
        self.assertEqual(review_schema["properties"]["receipts"]["maxItems"], review_tool.MAX_RECEIPTS)
        self.assertEqual(review_schema["properties"]["required_checks"]["maxItems"], review_tool.MAX_CHECKS)
        self.assertEqual(schema_check.validate(review_request(), review_schema), [])
        unsafe_review = review_request()
        unsafe_review["receipts"][0]["check_name"] = "invalid value"
        self.assertTrue(schema_check.validate(unsafe_review, review_schema))

    def test_dry_run_is_blocked_without_local_source_and_never_grants_authority(self) -> None:
        request = prepare_tool._validate_request(run_request())
        packet = prepare_tool.prepare(request, {}, [])
        self.assertEqual(packet["status"], "blocked")
        self.assertEqual(packet["authority"]["dispatch"], "not-authorized-by-packet")
        self.assertEqual(packet["authority"]["grant_changes"], "none")
        self.assertEqual(packet["authority"]["deployment"], "excluded")
        self.assertNotIn("/tmp/", json.dumps(packet))
        self.assertEqual(
            hashlib.sha256(
                json.dumps(
                    {key: value for key, value in packet.items() if key != "packet_sha256"},
                    ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode("utf-8")
            ).hexdigest(),
            packet["packet_sha256"],
        )

    def test_manual_prompt_stops_before_echoing_path_or_credential_shaped_text(self) -> None:
        raw = run_request()
        raw["goal"] = "Inspect token=do-not-echo-this-value"
        request = prepare_tool._validate_request(raw)
        packet = prepare_tool.prepare(request, {}, [])
        prompt, permitted = prepare_tool.render_manual_prompt(packet)
        self.assertFalse(permitted)
        self.assertIn("BLOCKED-CONTEXT", prompt)
        self.assertNotIn("do-not-echo-this-value", prompt)


class LocalSnapshotObservationTests(unittest.TestCase):
    def test_source_snapshot_changes_from_clean_to_dirty_and_identity_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            self.git(repo, "init", "-b", "main")
            self.git(repo, "config", "user.name", "Test")
            self.git(repo, "config", "user.email", "test@example.invalid")
            self.git(repo, "config", "remote.origin.url", "https://github.com/bayleafwalker/agentops.git")
            (repo / "source.txt").write_text("source\n", encoding="utf-8")
            self.git(repo, "add", "source.txt")
            self.git(repo, "commit", "-m", "source")
            commit = self.git(repo, "rev-parse", "HEAD")
            row = {
                "owner": "agentops",
                "repository_id": "github.com/bayleafwalker/agentops",
                "source_branch": "main",
                "source_commit": commit,
                "target_branch": "main",
            }
            before = prepare_tool._source_observation(str(repo), row)
            self.assertEqual(before["checks"]["canonical_identity"], "passed")
            self.assertEqual(before["checks"]["working_tree"], "passed")
            (repo / "untracked.txt").write_text("post-snapshot change\n", encoding="utf-8")
            after = prepare_tool._source_observation(str(repo), row)
            self.assertEqual(after["checks"]["working_tree"], "failed")
            self.assertEqual(after["working_tree_state"], "dirty")
            wrong_identity = {**row, "repository_id": "github.com/other/agentops"}
            mismatch = prepare_tool._source_observation(str(repo), wrong_identity)
            self.assertEqual(mismatch["checks"]["canonical_identity"], "mismatch")

    @staticmethod
    def git(repo: Path, *args: str) -> str:
        process = subprocess.run(
            ["git", "-C", str(repo), *args], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return process.stdout.strip()


class CandidateReviewBoundaryTests(unittest.TestCase):
    def test_review_parser_refuses_duplicates_nonfinite_and_deep_json(self) -> None:
        for text in (
            '{"schema":"x","schema":"y"}',
            '{"value":Infinity}',
            "{" + "[" * 65 + "0" + "]" * 65 + "}",
        ):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "review.json"
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text[:30]), self.assertRaises(review_tool.ReviewPacketError):
                    review_tool._load_request(path)

    def test_unknown_fields_duplicate_receipts_and_same_reviewer_refuse(self) -> None:
        value = review_request()
        valid = review_tool._validate_request(value)
        self.assertEqual(valid["candidate"]["commit"], OID)
        candidate = copy.deepcopy(value)
        candidate["surprise"] = True
        with self.assertRaises(prepare_tool.PacketError):
            review_tool._validate_request(candidate)
        candidate = copy.deepcopy(value)
        candidate["receipts"].append(copy.deepcopy(candidate["receipts"][0]))
        with self.assertRaisesRegex(review_tool.ReviewPacketError, "unique"):
            review_tool._validate_request(candidate)
        candidate = copy.deepcopy(value)
        candidate["receipts"][1]["reviewer_id"] = candidate["candidate"]["author_id"]
        request = review_tool._validate_request(candidate)
        observation = {"tree": TREE, **request["candidate"]}
        self.assertEqual(
            review_tool._receipt_status(request["receipts"][1], observation,
                                        request["evaluated_at"], request["max_receipt_age_seconds"]),
            "not-independent",
        )

    def test_review_packet_never_authenticates_or_lands(self) -> None:
        request = review_tool._validate_request(review_request())
        candidate = {"tree": TREE, **request["candidate"]}
        evaluated, evidence = review_tool._evaluate_receipts(request, candidate)
        self.assertTrue(all(row["evidence_authenticity"] == "caller-supplied-unverified" for row in evaluated))
        self.assertTrue(all(row["status"] == "matches-exact-head-unverified" for row in evidence))
        packet = review_tool._prepare(request, None)
        self.assertEqual(packet["packet_state"], "blocked")
        self.assertEqual(packet["authority"]["merge"], "not-performed-and-not-available")
        self.assertEqual(packet["authority"]["dispatch"], "not-performed-and-not-available")


class SourcePinVerifierTests(unittest.TestCase):
    def test_manifest_parser_is_bounded_strict_and_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pins.json"
            for text in (
                '{"schema_version":1,"schema_version":1,"owners":[]}',
                '{"schema_version":1,"owners":[],"x":NaN}',
                "{" + '"x":' * 0 + "[" * 65 + "0" + "]" * 65 + "}",
            ):
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text[:30]), self.assertRaises(pins_tool.PinError):
                    pins_tool.load_manifest(path)
            path.write_bytes(b" " * (pins_tool.MAX_MANIFEST_BYTES + 1))
            with self.assertRaisesRegex(pins_tool.PinError, "exceeds 1 MiB"):
                pins_tool.load_manifest(path)
            path.write_text(json.dumps({"schema_version": 1, "owners": [{
                "owner": "vuoro", "branch": "main", "commit": OID,
                "draft_path": "../../secret", "draft_sha256": DIGEST,
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(pins_tool.PinError, "draft_path is invalid"):
                pins_tool.load_manifest(path)

    def test_pin_verification_refuses_stale_branch_and_detects_changed_blob(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / "repo"
            repo.mkdir()
            self.git(repo, "init", "-b", "candidate")
            self.git(repo, "config", "user.name", "Test")
            self.git(repo, "config", "user.email", "test@example.invalid")
            draft = repo / "draft.md"
            draft.write_text("pinned draft\n", encoding="utf-8")
            self.git(repo, "add", "draft.md")
            self.git(repo, "commit", "-m", "pin")
            commit = self.git(repo, "rev-parse", "HEAD").strip()
            row = {
                "owner": "vuoro", "branch": "candidate", "commit": commit,
                "draft_path": "draft.md",
                "draft_sha256": hashlib.sha256(b"pinned draft\n").hexdigest(),
            }
            state = pins_tool.state_for_repo(row, str(repo))
            self.assertTrue(all(value == "passed" for value in state["checks"].values()))
            wrong_digest = {**row, "draft_sha256": "d" * 64}
            self.assertEqual(pins_tool.state_for_repo(wrong_digest, str(repo))["checks"]["draft_sha256"], "stale")
            draft.write_text("mutated after pin\n", encoding="utf-8")
            self.git(repo, "add", "draft.md")
            self.git(repo, "commit", "-m", "mutate pinned branch")
            self.git(repo, "checkout", "-b", "candidate-next")
            self.git(repo, "commit", "--allow-empty", "-m", "move branch")
            self.git(repo, "branch", "-f", "candidate", "HEAD")
            stale = pins_tool.state_for_repo(row, str(repo))
            self.assertEqual(stale["checks"]["branch_tip"], "stale")

    @staticmethod
    def git(repo: Path, *args: str) -> str:
        process = subprocess.run(
            ["git", "-C", str(repo), *args], check=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        return process.stdout.strip()


if __name__ == "__main__":
    unittest.main()
