from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("audit_model_routing", Path(__file__).parents[1] / "audit_model_routing.py")
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class NativeRoutingAuditTests(unittest.TestCase):
    def test_catalogue_rejects_malformed_model_ids_including_hidden_rows(self):
        for bad in (None, 1, "", "  "):
            for visibility in ("list", "hide"):
                with self.subTest(bad=bad, visibility=visibility), self.assertRaises(ValueError):
                    audit_module.observed_models({"models": [
                        {"slug": "valid"}, {"slug": bad, "visibility": visibility}]})
        with self.assertRaises(ValueError):
            audit_module.observed_models({"models": [{"visibility": "hide"}]})
        for bad in ("", "  ", 1):
            with self.subTest(probe=bad), self.assertRaises(ValueError):
                audit_module.observed_models([{"success": True, "observed_models": [bad]}])

    def test_unconfigured_primary_is_distinct_from_unobserved(self):
        for primary in (None, "", "  ", 1, [], {}):
            with self.subTest(primary=primary):
                policy = {"aliases": {"build": {"codex": {
                    "model": primary, "fallback": "missing", "verified": False}}}}
                row = audit_module.audit(policy, {"codex": {"available"}})[0]
                self.assertEqual(row["primary"], primary)
                self.assertEqual(row["issues"], ["primary-unverified", "primary-unconfigured",
                                                "same-provider-fallback-not-observed"])
        for primary, expected in (("available", []), ("missing", ["primary-not-observed"])):
            policy = {"aliases": {"build": {"codex": {"model": primary, "verified": True}}}}
            self.assertEqual(audit_module.audit(policy, {"codex": {"available"}})[0]["issues"], expected)

    def test_cli_distinguishes_invalid_catalogue_from_invalid_primary(self):
        script = Path(audit_module.__file__)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = root / "policy.json"
            catalogue = root / "catalogue.json"
            policy.write_text(json.dumps({"aliases": {"build": {"codex": {"model": "", "verified": True}}}}))
            catalogue.write_text(json.dumps({"models": [{"slug": ""}]}))
            command = [sys.executable, str(script), "--policy", str(policy), "--catalogue", f"codex={catalogue}"]
            bad_catalogue = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(bad_catalogue.returncode, 2)
            self.assertIn("could not check", bad_catalogue.stderr)
            catalogue.write_text(json.dumps({"models": [{"slug": "available"}]}))
            bad_primary = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(bad_primary.returncode, 1)
            self.assertIn("primary-unconfigured", bad_primary.stdout)

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
