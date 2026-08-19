from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from volatile_context.fake_service import FakeContextService, Handler
from volatile_context.protocol import HttpContextServiceClient


class HttpRoundtripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        Handler.service = FakeContextService()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        host, port = cls.server.server_address
        cls.endpoint = f"http://{host}:{port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def base(self) -> dict[str, object]:
        return {
            "schema_version": "1",
            "harness": "reference",
            "dispatch_id": "d-http",
            "repo_id": "r-http",
            "session_id": "s-http",
            "agent_id": None,
            "cwd": "/repo",
        }

    def post(self, path: str, value: dict[str, object]) -> dict[str, object]:
        request = urllib.request.Request(
            self.endpoint + path,
            data=json.dumps(value).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            result = json.loads(response.read().decode("utf-8"))
        assert isinstance(result, dict)
        return result

    def test_projection_mutation_and_post_mutation_context(self) -> None:
        client = HttpContextServiceClient(self.endpoint)
        full = client.project({**self.base(), "event": "SessionStart", "mode": "full"})
        self.assertIsNotNone(full["context"])

        unchanged = client.project(
            {**self.base(), "event": "UserPromptSubmit", "mode": "delta"}
        )
        self.assertIsNone(unchanged["context"])

        mutation = self.post(
            "/demo/task/mutate",
            {
                "if_revision": "task:1",
                "actor": "agent:http",
                "idempotency_key": "http-k1",
                "patch": {"state": "review"},
            },
        )
        self.assertEqual(mutation["new_revision"], "task:2")

        observed = client.observe_mutation(
            {
                **self.base(),
                "provider_id": "task",
                "resource_id": "TASK-42",
                "new_revision": "task:2",
                "tool_name": "mcp__sprintctl__update_task",
                "tool_input": {"if_revision": "task:1"},
                "tool_response": mutation,
            }
        )
        self.assertIn("task:2", str(observed["context"]))

        with self.assertRaises(urllib.error.HTTPError) as error:
            self.post(
                "/demo/task/mutate",
                {
                    "if_revision": "task:1",
                    "actor": "agent:http",
                    "idempotency_key": "http-k2",
                    "patch": {"state": "done"},
                },
            )
        self.assertEqual(error.exception.code, 409)


if __name__ == "__main__":
    unittest.main()
