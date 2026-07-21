from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "sync_skills.py"
SPEC = importlib.util.spec_from_file_location("skill_sync", SCRIPT)
assert SPEC and SPEC.loader
SYNC = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SYNC
SPEC.loader.exec_module(SYNC)


class SkillSyncTests(unittest.TestCase):
    def test_canonical_skills_have_discoverable_frontmatter(self) -> None:
        malformed = [
            path.parent.name
            for path in sorted(SYNC.TEMPLATE_ROOT.glob("*/SKILL.md"))
            if not path.read_text(encoding="utf-8").startswith("---\n")
        ]
        self.assertEqual(malformed, [])

    def _write_skill(self, root: Path, name: str, content: str = "canonical\n") -> Path:
        skill = root / name
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(content, encoding="utf-8")
        return skill

    def _write_manifest(self, repo: Path, skills: list[str]) -> None:
        (repo / "example.dispatch.json").write_text(
            json.dumps({"skills": {"selected": skills}}), encoding="utf-8"
        )

    def _write_expected_link(self, repo: Path, name: str) -> None:
        link = repo / ".claude" / "skills" / name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(f"../../.agents/skills/{name}")

    def _init_clean_git_repo(self, repo: Path) -> None:
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "Skill Sync Tests"], check=True)
        (repo / ".gitkeep").write_text("\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", "baseline"], check=True)

    def test_in_sync_uses_manifest_selected_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            self._write_skill(template, "shared")
            self._write_skill(repo / ".agents" / "skills", "shared")
            self._write_manifest(repo, ["shared"])
            self._write_expected_link(repo, "shared")

            names = SYNC.resolve_skills(repo, None)
            statuses = SYNC.inspect_skills(repo, names, template_root=template)

            self.assertEqual([status.content for status in statuses], ["in-sync"])
            self.assertEqual(statuses[0].symlink, "in-sync")

    def test_reports_drift_with_unified_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            self._write_skill(template, "shared", "canonical\n")
            self._write_skill(repo / ".agents" / "skills", "shared", "local\n")

            status = SYNC.inspect_skills(repo, ["shared"], template_root=template)[0]

            self.assertEqual(status.content, "drifted")
            self.assertIn("-canonical", status.diff)
            self.assertIn("+local", status.diff)

    def test_reports_missing_canonical_skill(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            self._write_skill(template, "shared")

            status = SYNC.inspect_skills(repo, ["shared"], template_root=template)[0]

            self.assertEqual(status.content, "missing")
            self.assertEqual(status.symlink, "missing")

    def test_apply_copies_missing_skill_and_creates_expected_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            self._write_skill(template, "shared")
            self._init_clean_git_repo(repo)

            statuses = SYNC.apply_sync(repo, ["shared"], template_root=template)

            self.assertEqual(statuses[0].content, "in-sync")
            link = repo / ".claude" / "skills" / "shared"
            self.assertTrue(link.is_symlink())
            self.assertEqual(os_readlink(link), "../../.agents/skills/shared")

    def test_canonical_repository_links_directly_without_self_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            template = repo / "templates" / "skills"
            self._write_skill(template, "shared")
            self._init_clean_git_repo(repo)

            before = SYNC.inspect_skills(repo, ["shared"], template_root=template)
            self.assertEqual(before[0].content, "canonical")
            self.assertEqual(before[0].symlink, "missing")

            statuses = SYNC.apply_sync(repo, ["shared"], template_root=template)

            self.assertEqual(statuses[0].content, "canonical")
            self.assertEqual(statuses[0].symlink, "in-sync")
            link = repo / ".claude" / "skills" / "shared"
            self.assertEqual(os_readlink(link), "../../templates/skills/shared")
            self.assertFalse((repo / ".agents" / "skills" / "shared").exists())

    def test_repo_local_skill_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            local = self._write_skill(repo / ".agents" / "skills", "local-only", "keep me\n")
            self._init_clean_git_repo(repo)

            statuses = SYNC.apply_sync(repo, ["local-only"], template_root=template)

            self.assertEqual(statuses[0].content, "repo-local")
            self.assertEqual((local / "SKILL.md").read_text(encoding="utf-8"), "keep me\n")
            self.assertFalse((repo / ".claude" / "skills" / "local-only").exists())

    def test_apply_repairs_wrong_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            self._write_skill(template, "shared")
            self._write_skill(repo / ".agents" / "skills", "shared")
            link = repo / ".claude" / "skills" / "shared"
            link.parent.mkdir(parents=True)
            link.symlink_to("wrong-target")
            self._init_clean_git_repo(repo)

            statuses = SYNC.apply_sync(repo, ["shared"], template_root=template)

            self.assertEqual(statuses[0].symlink, "in-sync")
            self.assertEqual(os_readlink(link), "../../.agents/skills/shared")

    def test_apply_refuses_dirty_managed_skill_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            self._write_skill(template, "shared")
            self._write_skill(repo / ".agents" / "skills", "shared", "local\n")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)

            with self.assertRaisesRegex(SYNC.DirtyWorktreeError, "refusing --apply"):
                SYNC.apply_sync(repo, ["shared"], template_root=template)

    def test_apply_allows_dirty_repo_local_skill_documentation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            template = root / "template"
            repo = root / "repo"
            repo.mkdir()
            self._write_skill(template, "shared")
            readme = repo / ".agents" / "skills" / "README.md"
            readme.parent.mkdir(parents=True)
            readme.write_text("repository guidance\n", encoding="utf-8")
            self._init_clean_git_repo(repo)
            readme.write_text("updated repository guidance\n", encoding="utf-8")

            statuses = SYNC.apply_sync(repo, ["shared"], template_root=template)

            self.assertEqual(statuses[0].content, "in-sync")
            self.assertEqual(readme.read_text(encoding="utf-8"), "updated repository guidance\n")


def os_readlink(path: Path) -> str:
    return str(path.readlink())


if __name__ == "__main__":
    unittest.main()
