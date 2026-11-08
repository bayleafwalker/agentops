import json
import tempfile
import unittest
from pathlib import Path

from scripts.vuoro_cloud_read_probe import probe


class ReadProbeTests(unittest.TestCase):
    def test_only_get_metadata_and_redacted_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            credential = Path(directory) / "token"
            credential.write_text("secret-pat\n", encoding="utf-8")
            calls = []

            def get_json(path):
                calls.append(path)
                if path.endswith("handshake"):
                    return {"environment": {"name": "vuoro-cloud-ws-01m3abjs1qw0"}, "private": "hidden"}
                return {"operations": [
                    {"name": "work.item.list-v1", "summary": "Items", "secret": "hidden"},
                    {"name": "knowledge.item.read-v1", "summary": "Other"},
                ]}

            result = probe(credential, get_json=get_json)
            self.assertEqual(calls, ["/api/meta/v1/handshake", "/api/catalog/v1"])
            self.assertEqual(result["work_operation_count"], 1)
            self.assertEqual(result["work_operations"], [{"id": "work.item.list-v1", "title": "Items"}])
            self.assertNotIn("secret-pat", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
