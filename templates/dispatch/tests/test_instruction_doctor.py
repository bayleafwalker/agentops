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


def _manifest(source: Path, *, handling: str = "none", digest: str | None = None) -> dict:
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
            }],
        },
    }


class InstructionDoctorTests(unittest.TestCase):
    def _root(self, *, source: str = "<!-- agentops: rule rule_id=mechanical.line-budget scope=fixture -->\n<!-- agentops: hook verify:unit -->\nwi:123\n", digest: str | None = None) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source_path = root / "AGENTS.md"
        source_path.write_text(source, encoding="utf-8")
        (root / "fixture.dispatch.json").write_text(json.dumps(_manifest(source_path, digest=digest)), encoding="utf-8")
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
        root = self._root()
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
        self.assertEqual(report["effective_files"], ["AGENTS.md"])
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


if __name__ == "__main__":
    unittest.main()
