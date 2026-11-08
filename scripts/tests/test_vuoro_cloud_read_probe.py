import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request

from scripts.vuoro_cloud_read_probe import RefuseRedirects, probe


class ReadProbeTests(unittest.TestCase):
    def test_metadata_and_invoke_are_stubbed_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            credential = Path(directory) / "token"
            credential.write_text("secret-pat\n", encoding="utf-8")
            requests = []

            def open_request(request: Request):
                requests.append(request)
                if request.full_url.endswith("handshake"):
                    return {"environment": {"name": "kotona"}}
                if request.full_url.endswith("catalog/v1"):
                    return {
                        "revision": "catalog-rev",
                        "operations": [
                            {"name": "work.read.sprints", "execution_semantics": "read"},
                            {"name": "work.write.sprint", "execution_semantics": "write"},
                        ],
                    }
                return {
                    "status": "accepted",
                    "result": {"repo_id": "vuoro", "sprints": [
                        {"name": "m1-4-scenario-20260929T082145Z"},
                        {"name": "restore-drill-2026-09-25"},
                    ]},
                }

            result = probe(
                credential, "vuoro", open_request=open_request,
                request_id_factory=lambda: "request-123",
            )

            self.assertEqual([request.get_method() for request in requests], ["GET", "GET", "POST"])
            invoke = requests[-1]
            body = json.loads(invoke.data)
            self.assertEqual(invoke.get_header("X-request-id"), body["request_id"])
            self.assertEqual(body["request_id"], "request-123")
            self.assertEqual(body["catalog_revision"], "catalog-rev")
            self.assertEqual(body["operation"], "work.read.sprints")
            self.assertEqual(body["repo_id"], "vuoro")
            self.assertEqual(invoke.get_header("User-agent"), "agentops-operator")
            self.assertEqual(result, {
                "sprint_count": 2,
                "sprint_names": [
                    "m1-4-scenario-20260929T082145Z", "restore-drill-2026-09-25",
                ],
            })
            self.assertNotIn("secret-pat", json.dumps(result))

    def test_redirect_handler_raises_instead_of_following(self):
        with self.assertRaises(HTTPError) as raised:
            RefuseRedirects().redirect_request(
                Request("https://api.vuoro.cloud/api/catalog/v1"), None,
                302, "Found", {}, "https://elsewhere.invalid/collect",
            )
        raised.exception.close()
        self.assertEqual(raised.exception.code, 302)
        self.assertEqual(raised.exception.reason, "redirect refused")

    def test_rejects_catalog_operation_without_read_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            credential = Path(directory) / "token"
            credential.write_text("secret-pat\n", encoding="utf-8")

            def open_request(request):
                if request.full_url.endswith("handshake"):
                    return {}
                return {"revision": "r", "operations": [
                    {"name": "work.read.sprints", "execution_semantics": "write"},
                ]}

            with self.assertRaisesRegex(ValueError, "read-only"):
                probe(credential, "vuoro", open_request=open_request)


if __name__ == "__main__":
    unittest.main()
