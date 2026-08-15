from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/materialize_skill_lock.py"
SPEC = importlib.util.spec_from_file_location("skill_lock", SCRIPT)
assert SPEC and SPEC.loader
LOCK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK)


class SkillLockTests(unittest.TestCase):
    def fixture(self, mandatory: bool = True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source/demo"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
        observed = LOCK.tree_digest(source)
        tree = hashlib.sha256(json.dumps([["demo", observed]], separators=(",", ":")).encode()).hexdigest()
        lock = {"schema_version": "skill-lock/v1", "canonical_commit": "abcdef0", "tree_digest": tree, "selected": [{"id": "demo", "version": "1", "path": "demo", "digest": observed, "mandatory": mandatory}], "overlays": [], "provider_materialization_targets": {"codex": ".codex/skills", "claude": ".claude/skills"}}
        return root, lock

    def test_materialization_is_deterministic_and_provider_bytes_match(self) -> None:
        root, lock = self.fixture()
        codex = LOCK.materialize(lock, root / "source", root / "codex-target", "codex")
        claude = LOCK.materialize(lock, root / "source", root / "claude-target", "claude")
        self.assertEqual(
            LOCK.tree_digest(root / "codex-target/.codex/skills/demo"),
            LOCK.tree_digest(root / "claude-target/.claude/skills/demo"),
        )
        LOCK.rollback(codex, root / "codex-target", lock["tree_digest"])
        self.assertFalse((root / "codex-target/.codex/skills").exists())
        self.assertTrue((root / "claude-target/.claude/skills").exists())

    def test_tamper_is_fatal(self) -> None:
        root, lock = self.fixture()
        (root / "source/demo/SKILL.md").write_text("tampered\n", encoding="utf-8")
        self.assertEqual(LOCK.inspect(lock, root / "source")["handling"], "fatal")

    def test_nested_symlink_is_fatal_and_never_materialized(self) -> None:
        root, lock = self.fixture()
        (root / "source/demo/unhashed").symlink_to("/etc/hostname")
        self.assertEqual(LOCK.inspect(lock, root / "source")["handling"], "fatal")
        with self.assertRaises(LOCK.SkillLockError):
            LOCK.materialize(lock, root / "source", root / "target", "codex")
        self.assertFalse((root / "target/.codex/skills").exists())

    def test_missing_mandatory_is_repair_only_and_optional_is_degraded(self) -> None:
        root, lock = self.fixture(mandatory=True)
        (root / "source/demo/SKILL.md").unlink()
        (root / "source/demo").rmdir()
        self.assertEqual(LOCK.inspect(lock, root / "source")["handling"], "repair-only")
        lock["selected"][0]["mandatory"] = False
        self.assertEqual(LOCK.inspect(lock, root / "source")["handling"], "degraded")


class HookMappingTests(unittest.TestCase):
    def test_hooks_are_advisory_and_authoritative_guards_remain(self) -> None:
        value = json.loads((ROOT / "hooks/lifecycle-adapters.v1.json").read_text())
        levels = set(value["support_levels"])
        self.assertEqual(levels, {"native", "partial", "approximated", "unsupported"})
        self.assertGreaterEqual(set(value["authoritative_denial"]), {"actionq-admission", "git-ci", "deployment-boundary"})
        self.assertIn("hook absence never grants authority", value["hook_semantics"])


if __name__ == "__main__":
    unittest.main()
