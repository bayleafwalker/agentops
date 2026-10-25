"""Deterministic tests for the shared quota pause ledger mechanics."""

import json
from pathlib import Path
import tempfile
import unittest

from scripts.shared_execution.quota import QuotaLedger


class QuotaLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "quota.json"
        self.now = 1_000.0
        self.ledger = QuotaLedger(
            self.path,
            "fixture-host",
            {"provider-a": ["short", "long"], "provider-b": ["daily"]},
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_initial_shape_uses_adapter_windows_plus_unknown(self):
        data = json.loads(self.path.read_text())
        self.assertEqual(data, {
            "host": "fixture-host",
            "providers": {
                "provider-a": {
                    "short": {"blocked": False, "reset_at": None},
                    "long": {"blocked": False, "reset_at": None},
                    "unknown": {"blocked": False, "reset_at": None},
                },
                "provider-b": {
                    "daily": {"blocked": False, "reset_at": None},
                    "unknown": {"blocked": False, "reset_at": None},
                },
            },
        })

    def test_block_persists_exact_observation_and_clock_time(self):
        observation = {
            "provider": "provider-a",
            "window": "short",
            "reset_at": 1_500.0,
            "source": "adapter receipt",
        }
        self.ledger.block(observation)
        self.assertEqual(json.loads(self.path.read_text())["providers"]["provider-a"]["short"], {
            **observation,
            "blocked": True,
            "observed_at": 1_000.0,
        })
        self.assertEqual(self.ledger.blocked("provider-a"), [{
            **observation,
            "blocked": True,
            "observed_at": 1_000.0,
        }])
        reopened = QuotaLedger(
            self.path,
            "fixture-host",
            {"provider-a": ["short", "long"]},
            clock=lambda: self.now,
        )
        self.assertEqual(reopened.blocked("provider-a"), self.ledger.blocked("provider-a"))

    def test_known_reset_expiry_does_not_sleep(self):
        self.ledger.block({"provider": "provider-a", "window": "short", "reset_at": 1_100.0})
        self.assertEqual(len(self.ledger.blocked("provider-a")), 1)
        self.now = 1_100.0
        self.assertEqual(self.ledger.blocked("provider-a"), [])

    def test_unknown_reset_remains_blocked_at_any_time(self):
        self.ledger.block({"provider": "provider-a", "window": "unknown", "reset_at": None})
        self.now = 9_999_999.0
        blocked = self.ledger.blocked("provider-a")
        self.assertEqual([item["window"] for item in blocked], ["unknown"])

    def test_overlapping_windows_and_providers_remain_independent(self):
        self.ledger.block({"provider": "provider-a", "window": "short", "reset_at": 2_000.0})
        self.ledger.block({"provider": "provider-a", "window": "long", "reset_at": 3_000.0})
        self.ledger.block({"provider": "provider-b", "window": "daily", "reset_at": 2_500.0})
        self.assertEqual({item["window"] for item in self.ledger.blocked("provider-a")},
                         {"short", "long"})
        self.assertEqual({item["window"] for item in self.ledger.blocked("provider-b")},
                         {"daily"})
        self.assertEqual(self.ledger.blocked("provider-unknown"), [])


if __name__ == "__main__":
    unittest.main()
