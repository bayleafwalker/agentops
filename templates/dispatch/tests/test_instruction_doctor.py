from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "instruction_doctor.py"
SPEC = importlib.util.spec_from_file_location("instruction_doctor", SCRIPT)
assert SPEC and SPEC.loader
DOCTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DOCTOR)


def _manifest(source: Path, *, handling: str = "none", digest: str | None = None, extra_sources: list | None = None) -> dict:
    raw = source.read_bytes()
    return {
        "schema_version": 2,
        "repo_id": "fixture",
        "adoption_level": "guidance-only",
        "routing": {"default_harness": "codex", "default_model_alias": "fast-build", "action_classes": {"plan": {"enabled": True}}},
        "skills": {"selected": ["dispatch-plan"]},
        "verification": {"command_families": ["unit"]},
        "hooks": {"level": "none", "publishers": []},
        "instruction_set": {
            "schema_version": 1,
            "discovery": "native",
            "sources": [{
                "id": "root-agents",
                "path": "AGENTS.md",
                "kind": "AGENTS.md",
                "digest": digest or hashlib.sha256(raw).hexdigest(),
                "source_rev": "fixture:unknown",
                "refs": ["wi:123"],
                "rules": [{"rule_id": "mechanical.line-budget", "scope": "fixture", "kind": "mechanical"}],
                "hooks": ["verify:unit"],
                "line_budget": 20,
            }] + list(extra_sources or []),
        },
    }


FORGE_COMPLIANT_CLAUDE_MD = (
    "# fixture\n\nNetwork calls through agent tools return exit 0 with empty output "
    "unless escalated; pass `dangerouslyDisableSandbox: true`.\n"
)
FORGE_COMPLIANT_GATES = {"default": "routine", "gated": []}


class InstructionDoctorTests(unittest.TestCase):
    def _root(
        self,
        *,
        source: str = "<!-- agentops: rule rule_id=mechanical.line-budget scope=fixture -->\n<!-- agentops: hook verify:unit -->\nwi:123\n",
        digest: str | None = None,
        claude_md: str | None = FORGE_COMPLIANT_CLAUDE_MD,
        gates: dict | str | None = FORGE_COMPLIANT_GATES,
    ) -> Path:
        """Build a fixture repo that satisfies the forge contract by default.

        The forge/gates checks are repo-wide propagation requirements, so a
        fixture that ignores them is not a neutral baseline -- it is a
        non-compliant repo, and every unrelated assertion about `handling` picks
        up its findings. Tests that exercise those checks pass `claude_md=None`
        or `gates=None` explicitly.
        """
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source_path = root / "AGENTS.md"
        source_path.write_text(source, encoding="utf-8")
        extra_sources = []
        if claude_md is not None:
            claude_path = root / "CLAUDE.md"
            claude_path.write_text(claude_md, encoding="utf-8")
            # Catalogue it too: native discovery finds every effective instruction
            # source, so writing one without cataloguing it would make the fixture
            # non-compliant for a second, unrelated reason.
            extra_sources.append({
                "id": "root-claude",
                "path": "CLAUDE.md",
                "kind": "CLAUDE.md",
                "digest": hashlib.sha256(claude_path.read_bytes()).hexdigest(),
                "source_rev": "fixture:unknown",
                "refs": [],
                "rules": [],
                "hooks": [],
                "line_budget": 20,
            })
        (root / "fixture.dispatch.json").write_text(
            json.dumps(_manifest(source_path, digest=digest, extra_sources=extra_sources)), encoding="utf-8"
        )
        if gates is not None:
            gates_dir = root / ".claude"
            gates_dir.mkdir(exist_ok=True)
            body = gates if isinstance(gates, str) else json.dumps(gates)
            (gates_dir / "gates.json").write_text(body, encoding="utf-8")
        return root

    def test_native_discovery_is_root_to_cwd_and_keeps_provider_files_separate(self) -> None:
        root = self._root()
        nested = root / "src" / "child"
        nested.mkdir(parents=True)
        (root / "CLAUDE.md").write_text("provider\n", encoding="utf-8")
        (root / "src" / "AGENTS.md").write_text("nested\n", encoding="utf-8")
        self.assertEqual(
            [path.relative_to(root).as_posix() for path in DOCTOR.discover_native_sources(root, nested)],
            ["AGENTS.md", "CLAUDE.md", "src/AGENTS.md"],
        )

    def test_validated_and_managed_eligible_only_for_none_handling(self) -> None:
        root = self._root()
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["status"], "validated")
        self.assertEqual(report["handling"], "none")
        self.assertTrue(report["managed_eligible"])

    def test_v1_is_backward_compatible_but_degraded_and_not_managed(self) -> None:
        root = self._root()
        manifest = json.loads((root / "fixture.dispatch.json").read_text())
        manifest["schema_version"] = 1
        manifest.pop("instruction_set")
        (root / "fixture.dispatch.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["binding_status"], "degraded")
        self.assertEqual(report["handling"], "degraded")
        self.assertFalse(report["managed_eligible"])

    def test_degraded_digest_is_not_eligible(self) -> None:
        root = self._root(digest="0" * 64)
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["status"], "degraded")
        self.assertEqual(report["handling"], "degraded")
        self.assertFalse(report["managed_eligible"])

    def test_effective_native_source_must_be_catalogued(self) -> None:
        # Start without a catalogued CLAUDE.md so the one written below is
        # genuinely absent from the catalog rather than merely stale.
        root = self._root(claude_md=None)
        (root / "CLAUDE.md").write_text("provider\n", encoding="utf-8")
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["binding_status"], "degraded")
        self.assertIn(
            "source-not-catalogued",
            {finding["code"] for finding in report["findings"]},
        )

    def test_source_revision_is_validated_by_content_not_current_head(self) -> None:
        root = self._root()
        manifest_path = root / "fixture.dispatch.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["instruction_set"]["sources"][0]["source_rev"] = "git:base"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        original = DOCTOR._git_source_digest
        self.addCleanup(setattr, DOCTOR, "_git_source_digest", original)
        DOCTOR._git_source_digest = lambda _root, _revision, _path: hashlib.sha256(
            (root / "AGENTS.md").read_bytes()
        ).hexdigest()
        report = DOCTOR.inspect(root, root)
        self.assertNotIn(
            "source-revision-mismatch",
            {finding["code"] for finding in report["findings"]},
        )

    def test_line_budget_is_advisory_and_does_not_change_eligibility(self) -> None:
        root = self._root()
        manifest = json.loads((root / "fixture.dispatch.json").read_text())
        manifest["instruction_set"]["sources"][0]["line_budget"] = 1
        (root / "fixture.dispatch.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["handling"], "none")
        self.assertEqual(report["binding_status"], "validated")
        self.assertTrue(report["managed_eligible"])

    def test_report_exposes_measurement_provenance(self) -> None:
        root = self._root()
        report = DOCTOR.inspect(root, root)
        self.assertIn("bytes", report)
        self.assertEqual(report["effective_files"], ["AGENTS.md", "CLAUDE.md"])
        self.assertIn("AGENTS.md", report["effective_files"])
        self.assertEqual(report["broken_refs"], [])

    def test_duplicate_provider_adapters_and_escaping_sources_are_mechanical_findings(self) -> None:
        root = self._root()
        manifest = json.loads((root / "fixture.dispatch.json").read_text())
        manifest["instruction_set"]["provider_adapters"] = [
            {"provider": "codex", "path": ".codex/agents/planner.toml"},
            {"provider": "codex", "path": ".codex/agents/reviewer.toml"},
            {"provider": "claude", "path": "../outside.md"},
        ]
        manifest["instruction_set"]["sources"].append({
            "id": "escape",
            "path": "../outside.md",
            "kind": "other",
            "digest": "0" * 64,
            "source_rev": "git:unknown",
        })
        (root / "fixture.dispatch.json").write_text(json.dumps(manifest), encoding="utf-8")
        report = DOCTOR.inspect(root, root)
        codes = {item["code"] for item in report["findings"]}
        self.assertIn("duplicate-provider-adapter", codes)
        self.assertIn("source-path-escape", codes)

    def test_invalid_manifest_exposes_fatal_handling_without_writing(self) -> None:
        root = self._root()
        (root / "fixture.dispatch.json").write_text("{not json", encoding="utf-8")
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["handling"], "fatal")
        self.assertFalse(report["managed_eligible"])

    def test_role_preset_cannot_carry_authority(self) -> None:
        root = self._root()
        manifest_path = root / "fixture.dispatch.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["instruction_set"]["role_presets"] = {
            "worker": {
                "model": "Luna",
                "behavior": "high",
                "tool_mode": "write",
                "authority": "release",
            }
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["handling"], "fatal")
        self.assertFalse(report["managed_eligible"])

    def test_missing_mandatory_skill_lock_is_repair_only(self) -> None:
        root = self._root()
        manifest_path = root / "fixture.dispatch.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["instruction_set"]["skill_lock_ref"] = {
            "path": ".agents/skill-lock.json",
            "digest": "0" * 64,
            "mandatory": True,
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report = DOCTOR.inspect(root, root)
        self.assertEqual(report["handling"], "repair-only")
        self.assertFalse(report["managed_eligible"])


    # --- forge contract -------------------------------------------------
    # These checks shipped in af71e20 with no coverage, and broke three tests
    # in this file that were left red. They are propagation requirements, so
    # they are asserted on the finding code, not on the aggregate handling.

    def test_absent_claude_md_is_reported_because_agents_md_is_not_auto_loaded(self) -> None:
        report = DOCTOR.inspect(*(2 * (self._root(claude_md=None),)))
        codes = {finding["code"] for finding in report["findings"]}
        self.assertIn("forge-contract-missing", codes)

    def test_claude_md_without_the_forge_block_is_reported(self) -> None:
        root = self._root(claude_md="# fixture\n\nnothing about the sandbox here\n")
        report = DOCTOR.inspect(root, root)
        finding = next(
            item for item in report["findings"] if item["code"] == "forge-contract-missing"
        )
        # A present-but-silent CLAUDE.md is the more dangerous case: it looks
        # like the contract is satisfied.
        self.assertEqual(finding.get("path"), "CLAUDE.md")
        self.assertEqual(finding["handling"], "degraded")

    def test_absent_gates_json_is_reported_but_does_not_imply_gating(self) -> None:
        root = self._root(gates=None)
        report = DOCTOR.inspect(root, root)
        codes = {finding["code"] for finding in report["findings"]}
        self.assertIn("gates-undeclared", codes)
        # Absence means routine. It must never be reported as if it gated.
        self.assertNotIn("gates-default-not-routine", codes)

    def test_gates_default_other_than_routine_is_repair_only(self) -> None:
        root = self._root(gates={"default": "operator-approved", "gated": []})
        report = DOCTOR.inspect(root, root)
        finding = next(
            item for item in report["findings"] if item["code"] == "gates-default-not-routine"
        )
        self.assertEqual(finding["handling"], "repair-only")

    def test_gated_entry_without_a_valid_tier_is_repair_only(self) -> None:
        root = self._root(
            gates={"default": "routine", "gated": [{"match": "deploy", "tier": "sometimes"}]}
        )
        report = DOCTOR.inspect(root, root)
        finding = next(
            item for item in report["findings"] if item["code"] == "gates-tier-invalid"
        )
        self.assertEqual(finding["handling"], "repair-only")

    def test_unparseable_gates_json_is_repair_only_not_silently_ignored(self) -> None:
        root = self._root(gates="{not json")
        report = DOCTOR.inspect(root, root)
        finding = next(item for item in report["findings"] if item["code"] == "gates-invalid")
        self.assertEqual(finding["handling"], "repair-only")

if __name__ == "__main__":
    unittest.main()
