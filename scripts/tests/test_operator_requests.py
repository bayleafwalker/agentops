"""Focused tests for the local operator-request transport boundary."""
from __future__ import annotations

import sys
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


if __name__ == "__main__":
    unittest.main()
