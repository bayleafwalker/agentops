from __future__ import annotations

import json
from pathlib import Path
import unittest


ROUTING = Path(__file__).parents[1] / "model-routing.json"


class ModelRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.routing = json.loads(ROUTING.read_text(encoding="utf-8"))

    def test_caller_harnesses_select_provider_families(self) -> None:
        self.assertEqual(
            self.routing["caller_harness_providers"],
            {"claude": "anthropic", "codex": "codex", "kimi": "kimi"},
        )

    def test_live_aliases_cover_claude_and_codex_callers(self) -> None:
        for alias in self.routing["aliases"]:
            with self.subTest(alias=alias):
                self.assertIn("anthropic", self.routing["aliases"][alias])
                self.assertIn("codex", self.routing["aliases"][alias])

    def test_fast_codex_build_uses_cli_only_spark_with_same_provider_fallback(self) -> None:
        route = self.routing["aliases"]["fast-build"]["codex"]

        self.assertEqual(route["model"], "gpt-5.3-codex-spark")
        self.assertEqual(route["fallback"], "gpt-5.6-luna")
        self.assertEqual(route["transport"], "chatgpt")
        self.assertIn("codex-cli", route["surfaces"])
        self.assertTrue(route["verified"])

    def test_kimi_remains_fail_closed_until_model_routes_exist(self) -> None:
        for alias, providers in self.routing["aliases"].items():
            with self.subTest(alias=alias):
                self.assertNotIn("kimi", providers)


if __name__ == "__main__":
    unittest.main()
