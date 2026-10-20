from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("audit_model_routing", Path(__file__).parents[1] / "audit_model_routing.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class NativeRoutingAuditTests(unittest.TestCase):
    def test_supported_fallback_does_not_hide_an_unobserved_primary(self):
        policy = {"aliases": {"build": {"codex": {
            "model": "missing", "fallback": "available", "verified": True}}}}
        rows = audit_module.audit(policy, {"codex": {"available"}})
        self.assertEqual(rows[0]["issues"], ["primary-not-observed"])

    def test_other_provider_access_cannot_qualify_fallback(self):
        policy = {"aliases": {"build": {
            "codex": {"model": "available", "fallback": "other-family", "verified": True},
            "anthropic": {"model": "other-family", "verified": True}}}}
        rows = audit_module.audit(policy, {"codex": {"available"}, "anthropic": {"other-family"}})
        codex = next(row for row in rows if row["provider"] == "codex")
        self.assertEqual(codex["issues"], ["same-provider-fallback-not-observed"])

    def test_failed_and_hidden_models_are_not_availability_proof(self):
        with self.assertRaisesRegex(ValueError, "inconclusive"):
            audit_module.observed_models([
                {"success": False, "observed_models": ["failed"]},
                {"success": True, "observed_models": ["actual"]}])
        self.assertEqual(audit_module.observed_models([
            {"success": True, "observed_models": ["actual"]}]), {"actual"})
        self.assertEqual(audit_module.observed_models({"models": [
            {"slug": "hidden", "visibility": "hide"}, {"slug": "actual", "visibility": "list"}]}), {"actual"})

    def test_invalid_catalogue_is_could_not_check(self):
        for value in ({}, [], {"models": []}, [{"success": True}]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                audit_module.observed_models(value)

    def test_unknown_provider_cannot_silently_pass_empty_audit(self):
        with self.assertRaises(ValueError):
            audit_module.audit({"aliases": {}}, {"unknown": {"model"}})
