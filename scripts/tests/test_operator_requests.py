"""Focused tests for the local operator-request transport boundary."""
from __future__ import annotations

import sys
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import operator_requests as requests


class RequestContentBoundaryTests(unittest.TestCase):
    def test_refuses_sensitive_aliases_recursively(self) -> None:
        for payload in (
            {"conversation_transcript": "private words"},
            {"nested": [{"apiKey": "not-a-real-key"}]},
            {"claimed_authority": "can approve"},
            {"session": {"credential_reference": "file:secret"}},
            {"context": {"raw_transcript": "private words"}},
        ):
            with self.subTest(payload=payload), self.assertRaises(requests.RequestClientError) as caught:
                requests._check_content(payload)
            self.assertEqual(caught.exception.code, "sensitive-content-refused")

    def test_sensitive_content_is_refused_before_owner_initialization(self) -> None:
        owner = requests.VuoroRequestOwner(Path("/missing/profile"))
        with self.assertRaises(requests.RequestClientError) as caught:
            owner.invoke("publish", "repo", {"packet": {"private_key": "x"}})
        self.assertEqual(caught.exception.code, "sensitive-content-refused")
        self.assertIsNone(owner._client)

    def test_mcp_returns_bounded_error_without_calling_owner(self) -> None:
        owner = Mock()
        server = requests.MCPServer(lambda: owner)
        reply = server.call_tool("report-performed", {
            "repo_id": "repo",
            "arguments": {"report": {"rawTranscript": "private words"}},
        })
        self.assertTrue(reply["isError"])
        self.assertEqual(reply["structuredContent"]["code"], "sensitive-content-refused")
        owner.invoke.assert_not_called()

    def test_owner_refusal_for_stale_or_revoked_access_is_not_rewritten(self) -> None:
        class Owner:
            def invoke(self, suffix, repo_id, arguments):
                raise requests.RequestClientError("request-stale")

        reply = requests.MCPServer(Owner).call_tool("operator_request_attest".replace("operator_request_", "attest"), {
            "repo_id": "repo", "arguments": {"request_id": "req_example"},
        })
        self.assertTrue(reply["isError"])
        self.assertEqual(reply["structuredContent"]["code"], "request-stale")


class LocalRequestOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "private-outbox"
        self.store = requests.LocalRequestOutbox(self.directory)
        self.repo = "sprintctl"
        self.arguments = {
            "request_id": "req_01JZZZZZZZZZZZZZZZZZZZZZZZ",
            "idempotency_key": "publish-req-01JZZZZZZZZZZZZZZZZZZZZZZZ",
            "request": {"summary": "Restart a test service", "procedure": ["Check health", "Restart"]},
        }

    def test_stage_is_non_authoritative_and_duplicate_preserves_identity(self):
        first = self.store.stage_publish(self.repo, self.arguments)
        second = self.store.stage_publish(self.repo, self.arguments)
        self.assertEqual(first["state"], "pending")
        self.assertEqual(first, second)
        self.assertEqual(self.store.list_entries(), [{
            "request_id": self.arguments["request_id"], "repo_id": self.repo, "state": "pending",
        }])

    def test_conflicting_request_id_is_refused(self):
        self.store.stage_publish(self.repo, self.arguments)
        changed = {**self.arguments, "request": {"summary": "different"}}
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.stage_publish(self.repo, changed)
        self.assertEqual(caught.exception.code, "outbox-identity-conflict")

    def test_sensitive_content_is_rejected_before_directory_creation(self):
        bad = {**self.arguments, "request": {"rawTranscript": "private"}}
        with self.assertRaises(requests.RequestClientError):
            self.store.stage_publish(self.repo, bad)
        self.assertFalse(self.directory.exists())

    def test_failed_delivery_remains_pending_then_acknowledges_same_payload(self):
        self.store.stage_publish(self.repo, self.arguments)
        observed = []
        def unavailable(suffix, repo, payload):
            observed.append((suffix, repo, payload))
            raise requests.RequestClientError("owner-transport-failed")
        result = self.store.deliver(unavailable)
        self.assertEqual(result[0]["state"], "pending")
        self.assertEqual(self.store.list_entries()[0]["state"], "pending")

        def acknowledged(suffix, repo, payload):
            observed.append((suffix, repo, payload))
            return {"request_id": payload["request_id"], "revision": 1}
        result = self.store.deliver(acknowledged)
        self.assertEqual(result, [{"request_id": self.arguments["request_id"], "state": "acknowledged"}])
        self.assertEqual(self.store.list_entries()[0]["state"], "acknowledged")
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[0][0], "publish")
        self.assertEqual(observed[0][2]["idempotency_key"], self.arguments["idempotency_key"])

    def test_symlink_and_hardlink_storage_are_refused(self):
        self.store.stage_publish(self.repo, self.arguments)
        data = self.directory / "outbox.json"
        linked = self.directory / "linked.json"
        os.link(data, linked)
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-refused")

        data.unlink()
        target = self.directory / "target.json"
        target.write_text('{"schema":"operator-request-outbox/v1","entries":[]}')
        data.symlink_to(target)
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.list_entries()
        self.assertEqual(caught.exception.code, "outbox-storage-refused")

    def test_capacity_is_bounded(self):
        self.store.MAX_ENTRIES = 1
        self.store.stage_publish(self.repo, self.arguments)
        second = {**self.arguments, "request_id": "req_second", "idempotency_key": "publish-second"}
        with self.assertRaises(requests.RequestClientError) as caught:
            self.store.stage_publish(self.repo, second)
        self.assertEqual(caught.exception.code, "outbox-capacity-exceeded")

    def test_empty_owner_response_does_not_mark_acknowledged(self):
        self.store.stage_publish(self.repo, self.arguments)
        result = self.store.deliver(lambda *args: None)
        self.assertEqual(result[0]["state"], "pending")
        self.assertEqual(result[0]["error"], "owner-acknowledgement-missing")
        self.assertEqual(self.store.list_entries()[0]["state"], "pending")

    def test_only_acknowledged_rows_can_be_pruned(self):
        self.store.stage_publish(self.repo, self.arguments)
        self.assertEqual(self.store.prune_acknowledged(), 0)
        self.store.deliver(lambda *args: {"accepted": True})
        self.assertEqual(self.store.prune_acknowledged(), 1)
        self.assertEqual(self.store.list_entries(), [])


if __name__ == "__main__":
    unittest.main()
