from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


DISPATCH_ROOT = Path(__file__).parents[1]
SCRIPT = DISPATCH_ROOT / "scripts" / "validate_maintenance_envelope.py"
EXAMPLE = DISPATCH_ROOT / "maintenance-envelope" / "example.json"
SCHEMA = DISPATCH_ROOT / "maintenance-envelope" / "maintenance-envelope.v1.schema.json"
SPEC = importlib.util.spec_from_file_location("maintenance_envelope_validator", SCRIPT)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def schema_accepts(schema: dict, instance, root: dict) -> bool:
    """Evaluate the dependency-free Draft 2020-12 subset used by this schema."""
    if "$ref" in schema:
        target = root
        for part in schema["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return schema_accepts(target, instance, root)
    if "const" in schema and instance != schema["const"]:
        return False
    if "enum" in schema and instance not in schema["enum"]:
        return False
    if "oneOf" in schema and sum(schema_accepts(item, instance, root) for item in schema["oneOf"]) != 1:
        return False
    if "allOf" in schema and not all(schema_accepts(item, instance, root) for item in schema["allOf"]):
        return False
    expected = schema.get("type")
    type_matches = {
        "object": isinstance(instance, dict),
        "array": isinstance(instance, list),
        "string": isinstance(instance, str),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
    }
    if expected in type_matches and not type_matches[expected]:
        return False
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0) or len(instance) > schema.get("maxLength", sys.maxsize):
            return False
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            return False
    if isinstance(instance, dict):
        if any(field not in instance for field in schema.get("required", [])):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and any(field not in properties for field in instance):
            return False
        if any(field in instance and not schema_accepts(child, instance[field], root) for field, child in properties.items()):
            return False
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0) or len(instance) > schema.get("maxItems", sys.maxsize):
            return False
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in instance}) != len(instance):
            return False
        prefixes = schema.get("prefixItems", [])
        if any(not schema_accepts(child, instance[index], root) for index, child in enumerate(prefixes) if index < len(instance)):
            return False
        items = schema.get("items")
        if items is False and len(instance) > len(prefixes):
            return False
        if isinstance(items, dict) and any(not schema_accepts(items, item, root) for item in instance[len(prefixes):]):
            return False
        if "contains" in schema:
            count = sum(schema_accepts(schema["contains"], item, root) for item in instance)
            if count < schema.get("minContains", 1) or count > schema.get("maxContains", sys.maxsize):
                return False
    if isinstance(instance, int) and instance < schema.get("minimum", instance):
        return False
    return True


class MaintenanceEnvelopeValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.envelope = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.path = Path("envelope.json")
        self.evaluation_time = datetime.fromisoformat("2026-08-02T20:00:00+00:00")
        self.evaluation_step = "attest-backup"

    def assert_invalid(self, mutation, message: str) -> None:
        envelope = copy.deepcopy(self.envelope)
        mutation(envelope)
        with self.assertRaisesRegex(ValueError, message):
            VALIDATOR.validate_envelope(
                envelope,
                self.path,
                evaluation_time=self.evaluation_time,
                evaluation_step_id=self.evaluation_step,
            )

    def test_example_and_schema_identity(self) -> None:
        VALIDATOR.validate_envelope(
            self.envelope,
            EXAMPLE,
            evaluation_time=self.evaluation_time,
            evaluation_step_id=self.evaluation_step,
        )
        self.assertEqual(self.schema["properties"]["contract_id"]["const"], VALIDATOR.CONTRACT_ID)
        self.assertEqual(set(self.schema["required"]), VALIDATOR.TOP_FIELDS)
        self.assertEqual(self.schema["$id"], "https://agentops.kotona.app/schemas/maintenance-envelope/v1")
        self.assertEqual(self.schema["properties"]["abort"]["$ref"], "#/$defs/abort")
        self.assertEqual(self.schema["$defs"]["abort"]["properties"]["forbidden"]["const"], sorted(VALIDATOR.ABORT_FORBIDDEN))
        self.assertEqual(self.schema["$defs"]["recoveryPolicy"]["properties"]["forbidden_uses"]["const"], sorted(VALIDATOR.RECOVERY_FORBIDDEN))
        audit_properties = self.schema["$defs"]["auditReconciliation"]["properties"]
        self.assertEqual(audit_properties["immutable_receipts"]["const"], sorted(VALIDATOR.AUDIT_RECEIPTS))
        self.assertEqual(audit_properties["required_outcomes"]["const"], sorted(VALIDATOR.AUDIT_OUTCOMES))
        self.assertEqual(audit_properties["redact"]["const"], sorted(VALIDATOR.AUDIT_REDACT))
        jit_prefix = self.schema["properties"]["jit_fields"]["prefixItems"]
        self.assertEqual([entry["$ref"] for entry in jit_prefix], ["#/$defs/backupNameField", "#/$defs/backupUidField", "#/$defs/drainBoundaryField"])

    def test_base_and_full_commit_binding_is_exact(self) -> None:
        self.assert_invalid(lambda e: e["repositories"][0].__setitem__("commit", "main"), "mutable ref")
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("base_commit", "f" * 40), "preceding repository head")
        self.assert_invalid(lambda e: e["steps"][1].__setitem__("base_commit", "c" * 40), "preceding repository head")
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("commit", "abc123"), "full base and candidate")

    def test_step_order_and_dependencies_are_deterministic(self) -> None:
        self.assert_invalid(lambda e: e["steps"][1].__setitem__("sequence", 3), "contiguous")
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("depends_on", ["attest-backup"]), "only earlier")
        self.assert_invalid(lambda e: e["steps"][1].__setitem__("depends_on", ["create-backup", "create-backup"]), "sorted and unique")
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("phase", "post-migration"), "non-decreasing")

    def test_operation_paths_and_commands_are_closed_allowlists(self) -> None:
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("paths", ["clusters/main/kubernetes/other"]), "operation allowlist")
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("commands", ["kubectl-apply-arbitrary"]), "operation allowlist")
        self.assert_invalid(lambda e: e["operations"][0]["allowed_paths"].append("../escape"), "sorted and unique|traversal-free")
        self.assert_invalid(lambda e: e["operations"][0].__setitem__("allowed_commands", list(reversed(e["operations"][0]["allowed_commands"]))), "sorted and unique")
        self.assert_invalid(lambda e: e["operations"][0].__setitem__("command_id", "unregistered"), "registered commands")
        def shell_control(envelope) -> None:
            envelope["command_registry"][0]["argv"].append("; reboot")
            canonical = json.dumps(envelope["command_registry"], sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
            envelope["command_registry_ref"] = "artifact:sha256:" + hashlib.sha256(canonical).hexdigest()

        self.assert_invalid(shell_control, "shell control")
        self.assert_invalid(lambda e: e.__setitem__("command_registry_ref", "artifact:sha256:" + "0" * 64), "canonical command registry")

    def test_jit_fields_are_fixed_bounded_observations(self) -> None:
        self.assert_invalid(lambda e: e["jit_fields"][0].__setitem__("name", "commit"), "fixed v1 JIT")
        self.assert_invalid(lambda e: e["jit_fields"][0].__setitem__("source", "operator-input"), "backup-observation")
        self.assert_invalid(lambda e: e["jit_fields"][0].__setitem__("pattern", "^.*$"), "wildcard")
        self.assert_invalid(lambda e: e["jit_fields"][0].__setitem__("bind_before_step", "missing"), "exact step")
        self.assert_invalid(lambda e: e["jit_fields"].pop(), "exactly")
        self.assert_invalid(lambda e: e["jit_bindings"][0].__setitem__("value", "wrong"), "frozen JIT pattern")
        self.assert_invalid(lambda e: e["jit_bindings"][0].__setitem__("observed_at", "2026-08-02T20:01:00Z"), "after activation")
        self.assert_invalid(lambda e: e["jit_bindings"].pop(), "must bind drain_boundary_utc")

    def test_jit_bindings_are_sequence_aware(self) -> None:
        before = copy.deepcopy(self.envelope)
        before["jit_bindings"] = []
        VALIDATOR.validate_envelope(
            before,
            self.path,
            evaluation_time=self.evaluation_time,
            evaluation_step_id="create-backup",
        )
        VALIDATOR.validate_envelope(
            self.envelope,
            self.path,
            evaluation_time=self.evaluation_time,
            evaluation_step_id="attest-backup",
        )
        after = copy.deepcopy(self.envelope)
        after["steps"].append({
            **copy.deepcopy(after["steps"][1]),
            "id": "begin-migration",
            "sequence": 3,
            "base_commit": "b" * 40,
            "commit": "c" * 40,
            "depends_on": ["attest-backup"],
            "phase": "migration",
        })
        VALIDATOR.validate_envelope(
            after,
            self.path,
            evaluation_time=self.evaluation_time,
            evaluation_step_id="begin-migration",
        )

    def test_schema_acceptance_matches_adversarial_validator_shapes(self) -> None:
        self.assertTrue(schema_accepts(self.schema, self.envelope, self.schema))
        mutations = []

        def duplicate_jit(envelope) -> None:
            envelope["jit_bindings"][1]["name"] = "backup_name"

        mutations.append(duplicate_jit)
        mutations.append(lambda envelope: envelope["command_registry"][0]["argv"].append("; reboot"))
        mutations.append(lambda envelope: envelope["operator"]["decision_ref"].update(kind="git-commit", revision="sha256:" + "1" * 64))
        mutations.append(lambda envelope: envelope["abort"]["forbidden"].pop())
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(self.envelope)
                mutation(candidate)
                self.assertFalse(schema_accepts(self.schema, candidate, self.schema))

    def test_plan_one_requires_evidenced_zero_sessions_and_claims(self) -> None:
        self.assert_invalid(lambda e: e["start_gate"].__setitem__("plan", "plan-2"), "plan-1")
        self.assert_invalid(lambda e: e["start_gate"]["dependent_implementation_sessions"].__setitem__("expected_count", 1), "evidenced count zero")
        self.assert_invalid(lambda e: e["start_gate"]["active_normal_claims"].__setitem__("observed_at", "2026-08-02T19:50:00Z"), "fresh within five minutes")
        self.assert_invalid(lambda e: e["start_gate"]["active_normal_claims"].__setitem__("receipt_ref", {"kind": "sprint-event", "source": "x", "revision": "event:1"}), "must be one of")

    def test_every_step_requires_independent_review_and_verification(self) -> None:
        self.assert_invalid(lambda e: e["steps"][0]["reviews"][0].__setitem__("reviewer", "maintenance-author"), "independent passing")
        self.assert_invalid(lambda e: e["steps"][0]["reviews"][0].__setitem__("verdict", "comment"), "independent passing")
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("reviews", []), "non-empty")
        self.assert_invalid(lambda e: e["steps"][0].__setitem__("verification_refs", []), "non-empty")
        self.assert_invalid(lambda e: e["steps"][0].pop("publication_ref"), "missing fields")

    def test_window_is_bounded_and_expiring(self) -> None:
        self.assert_invalid(lambda e: e["window"].__setitem__("expires_at", e["window"]["not_before"]), "must be after")
        self.assert_invalid(lambda e: e["window"].__setitem__("expires_at", "2026-08-04T19:00:00Z"), "24 hours")
        self.assert_invalid(lambda e: e.__setitem__("issued_at", "2026-08-02T20:00:00Z"), "must not be after")
        envelope = copy.deepcopy(self.envelope)
        with self.assertRaisesRegex(ValueError, "at or after window.expires_at"):
            VALIDATOR.validate_envelope(envelope, self.path, evaluation_time=datetime.fromisoformat("2026-08-03T00:00:00+00:00"), evaluation_step_id=self.evaluation_step)
        with self.assertRaisesRegex(ValueError, "before window.not_before"):
            VALIDATOR.validate_envelope(envelope, self.path, evaluation_time=datetime.fromisoformat("2026-08-02T18:59:59+00:00"), evaluation_step_id=self.evaluation_step)

    def test_abort_is_forward_only_and_rejects_unreviewed_repair(self) -> None:
        self.assert_invalid(lambda e: e["abort"].__setitem__("after_migration", "delete-ledger"), "reviewed forward recovery")
        self.assert_invalid(lambda e: e["abort"].__setitem__("forbidden", ["delete-migration-ledger"]), "must contain exactly")

    def test_recovery_requested_commands_never_supply_authority(self) -> None:
        self.assert_invalid(lambda e: e["recovery_policy"].__setitem__("authority", "grant"), "non-authoritative")
        self.assert_invalid(lambda e: e["recovery_policy"].__setitem__("record_kinds", ["authority-command"]), "non-authoritative")
        self.assert_invalid(lambda e: e["recovery_policy"]["forbidden_uses"].remove("approve"), "must contain exactly")

    def test_audit_reconciliation_is_complete_and_redacted(self) -> None:
        self.assert_invalid(lambda e: e["audit_reconciliation"].__setitem__("export_required", False), "correlation, export")
        self.assert_invalid(lambda e: e["audit_reconciliation"]["immutable_receipts"].remove("effect"), "must contain exactly")
        self.assert_invalid(lambda e: e["audit_reconciliation"]["required_outcomes"].remove("rejected"), "must contain exactly")
        self.assert_invalid(lambda e: e["audit_reconciliation"]["redact"].remove("claim-tokens"), "must contain exactly")

    def test_credentials_placeholders_and_unknown_fields_fail_closed(self) -> None:
        self.assert_invalid(lambda e: e.__setitem__("claim_token", "secret"), "unexpected fields")
        self.assert_invalid(lambda e: e["operator"].__setitem__("identity", "credential=oops"), "authority credentials")
        self.assert_invalid(lambda e: e["repositories"][0].__setitem__("url", "https://user:pass@example.test/repo.git"), "credential-free")
        self.assert_invalid(lambda e: e["repositories"][0].__setitem__("commit", "REPLACE_AT_ACTIVATION"), "placeholder")

    def test_cli_emits_digest_only_after_complete_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            valid = Path(temp_dir) / "valid.json"
            invalid = Path(temp_dir) / "invalid.json"
            valid.write_text(json.dumps(self.envelope) + "\n", encoding="utf-8")
            bad = copy.deepcopy(self.envelope)
            bad["recovery_policy"]["authority"] = "grant"
            invalid.write_text(json.dumps(bad) + "\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "--at", "2026-08-02T20:00:00Z", "--step", self.evaluation_step, str(valid)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["contract_id"], VALIDATOR.CONTRACT_ID)
            self.assertRegex(output["sha256"], r"^[0-9a-f]{64}$")
            result = subprocess.run([sys.executable, str(SCRIPT), "--at", "2026-08-02T20:00:00Z", "--step", self.evaluation_step, str(valid), str(invalid)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")

    def test_cli_requires_explicit_structural_or_activation_mode(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT), str(EXAMPLE)], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        result = subprocess.run([sys.executable, str(SCRIPT), "--structural", str(EXAMPLE)], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
