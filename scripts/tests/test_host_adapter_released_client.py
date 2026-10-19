"""HTTP-boundary replay with the installed released vuoro-client (optional locally).

Run explicitly with the packaged Sprintctl interpreter using unittest. The main
stdlib/pytest suite also exercises lifecycle and report failures without this dependency.
No real endpoint or credential is used here.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha

try:
    import httpx
    from vuoro_client import AsyncVuoroClient
    from vuoro_client.profile import Profile
except ImportError:
    AsyncVuoroClient = None


@unittest.skipIf(AsyncVuoroClient is None, "released vuoro-client is not installed")
class ReleasedClientBoundary(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.clients = []
        self.handshake = {
            "client_protocol": {"minimum": 1, "maximum": 1},
            "service_release": {"distribution": "vuoro-service", "version": "fixture"},
            "environment": {"name": "expected", "environment_class": "development"},
        }
        self.catalog = {"revision": "fixture", "operations": [{
            "name": "work.agent.retire-v1", "input_schema": {}, "result_schema": {},
        }]}
        self.fail_status = None
        self.catalog_status = 200
        def handle(request):
            self.requests.append((request.method, request.url.path))
            if request.url.path == "/api/meta/v1/handshake":
                return httpx.Response(self.fail_status or 200, json=self.handshake)
            if request.url.path == "/api/catalog/v1":
                return httpx.Response(self.catalog_status, json=self.catalog)
            return httpx.Response(200, json={"status": "accepted", "result": {"retired": True}})
        def make_client(profile, resolver):
            client = AsyncVuoroClient(profile, lambda _: "fixture-only", transport=httpx.MockTransport(handle))
            self.clients.append(client)
            return client
        self.patch_client = patch("vuoro_client.AsyncVuoroClient", side_effect=make_client)
        self.patch_profile = patch("vuoro_client.profile.load_profile", return_value=Profile(
            "fixture", "http://fixture.invalid", "fixture", "expected"))
        self.patch_client.start()
        self.patch_profile.start()
        self.owner = ha.VuoroOwner("unused-fixture-profile")
        self.addCleanup(self.patch_client.stop)
        self.addCleanup(self.patch_profile.stop)
        self.addCleanup(self.owner.close)

    def retire(self):
        return self.owner.agent_retire("fixture", instance_id="fixture", reason="fixture", idempotency_key="fixture-key")

    def test_wrong_environment_refuses_before_invoke(self):
        self.handshake["environment"]["name"] = "wrong-secret-environment"
        with self.assertRaises(ha.OwnerError):
            self.retire()
        self.assertEqual(self.requests, [("GET", "/api/meta/v1/handshake")])
        self.assertIsNone(self.owner._client)
        self.assertIsNone(self.owner._loop)
        self.assertTrue(self.clients[0]._http.is_closed)

    def test_wrong_protocol_refuses_before_invoke(self):
        self.handshake["client_protocol"] = {"minimum": 2, "maximum": 3}
        with self.assertRaises(ha.OwnerError):
            self.retire()
        self.assertEqual(self.requests, [("GET", "/api/meta/v1/handshake")])

    def test_wrong_release_refuses_before_invoke(self):
        self.handshake["service_release"]["distribution"] = "other-service"
        with self.assertRaises(ha.OwnerError):
            self.retire()
        self.assertEqual(self.requests, [("GET", "/api/meta/v1/handshake")])

    def test_failed_handshake_retry_uses_fresh_client_and_closes_old(self):
        self.fail_status = 503
        with self.assertRaises(ha.OwnerError):
            self.retire()
        self.assertTrue(self.clients[0]._http.is_closed)
        self.fail_status = None
        self.assertEqual(self.retire(), {"retired": True})
        self.assertEqual(len(self.clients), 2)
        self.assertEqual(self.requests, [
            ("GET", "/api/meta/v1/handshake"), ("GET", "/api/meta/v1/handshake"),
            ("GET", "/api/catalog/v1"), ("POST", "/api/invoke/v1")])

    def test_success_handshakes_once_and_preserves_invocation(self):
        self.retire()
        self.retire()
        self.assertEqual(self.requests.count(("GET", "/api/meta/v1/handshake")), 1)
        self.assertEqual(self.requests.count(("POST", "/api/invoke/v1")), 2)
        self.owner.close()
        self.assertTrue(self.clients[0]._http.is_closed)

    def test_inspection_uses_only_handshake_and_catalog(self):
        expected, _ = ha._owner_inventory(ha._declared_owner_operations())
        self.catalog["operations"] = list(copy.deepcopy(expected).values())
        report = ha.inspect_owner("unused-fixture-profile")
        self.assertEqual(report["status"], "exact-match")
        self.assertEqual(len(report["operations"]), 14)
        self.assertEqual(self.requests, [("GET", "/api/meta/v1/handshake"), ("GET", "/api/catalog/v1")])
        self.assertTrue(self.clients[0]._http.is_closed)

    def test_inspection_refused_handshake_never_fetches_catalog(self):
        self.handshake["environment"]["name"] = "wrong-secret-environment"
        report = ha.inspect_owner("unused-fixture-profile")
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(self.requests, [("GET", "/api/meta/v1/handshake")])
        self.assertEqual(len(report["operations"]), 14)
        self.assertNotIn("wrong-secret-environment", str(report))
        self.assertTrue(self.clients[0]._http.is_closed)

    def test_inspection_catalog_authorization_refusal_is_unknown(self):
        self.catalog_status = 403
        report = ha.inspect_owner("unused-fixture-profile")
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["reason"], "catalog-unavailable")
        self.assertEqual(report["effective_authority"], "unknown")
        self.assertEqual(self.requests, [("GET", "/api/meta/v1/handshake"), ("GET", "/api/catalog/v1")])
        self.assertTrue(self.clients[0]._http.is_closed)


if __name__ == "__main__":
    unittest.main()
