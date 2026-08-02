from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import materialize_project as MATERIALIZE  # noqa: E402
import render_project as RENDER  # noqa: E402


class SharedReadFilesystemEnforcementTests(unittest.TestCase):
    def _git(self, repo: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True,
            text=True,
        ).stdout.strip()

    def _fixture(self, root: Path) -> tuple[RENDER.ProjectBinding, dict[str, Path]]:
        repos: dict[str, Path] = {}
        for name in ("home", "child"):
            remote = root / "remotes" / f"{name}.git"
            remote.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
            repo = root / "workspace" / name
            subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True)
            self._git(repo, "config", "user.email", "tests@example.invalid")
            self._git(repo, "config", "user.name", "Read-only tests")
            (repo / "AGENTS.md").write_text(f"# {name}\n", encoding="utf-8")
            (repo / "tracked.txt").write_text(f"{name}\n", encoding="utf-8")
            self._git(repo, "add", ".")
            self._git(repo, "commit", "-m", "initial")
            self._git(repo, "push", "origin", "main")
            repos[name] = repo
        (repos["home"] / "project.toml").write_text(
            """schema_version = 1
project_id = "f46fc856-7f25-48eb-9e48-cf795c1c8a41"
display_name = "readonly-fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"

[[members]]
repo_id = "child"
backlog = true
render = "none"
""",
            encoding="utf-8",
        )
        (repos["home"] / ".project" / "sources").mkdir(parents=True)
        (repos["home"] / ".project" / "sources" / "10-shared.md").write_text(
            "---\nrender_levels: [baseline, full]\n---\n# shared\n", encoding="utf-8"
        )
        target = root / "symlink-target.txt"
        target.write_text("outside\n", encoding="utf-8")
        os.symlink(target, repos["child"] / "outside-link")
        self._git(repos["home"], "add", ".")
        self._git(repos["home"], "commit", "-m", "project")
        self._git(repos["home"], "push", "origin", "main")
        self._git(repos["child"], "add", ".")
        self._git(repos["child"], "commit", "-m", "link")
        self._git(repos["child"], "push", "origin", "main")
        return RENDER.load_project(repos["home"] / "project.toml"), repos

    def test_opt_in_freezes_members_persists_state_refreshes_and_destroys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, repos = self._fixture(root)
            folder = root / "instances" / "read"
            anchor_config = repos["child"] / ".git" / "config"
            anchor_mode = stat.S_IMODE(anchor_config.stat().st_mode)
            result = MATERIALIZE.materialize(
                project, folder, command="setup", mode="shared-read", enforce_readonly=True,
            )
            self.assertFalse(result.blocked)
            marker = json.loads((folder / MATERIALIZE.MARKER_NAME).read_text(encoding="utf-8"))
            context = json.loads((folder / MATERIALIZE.CONTEXT_NAME).read_text(encoding="utf-8"))
            self.assertTrue(marker["readonly_enforced"])
            self.assertTrue(context["readonly_enforced"])
            child = folder / MATERIALIZE.MEMBERS_DIRECTORY / "child"
            self.assertFalse(stat.S_IMODE(child.stat().st_mode) & 0o222)
            self.assertFalse(stat.S_IMODE((child / "tracked.txt").stat().st_mode) & 0o222)
            self.assertEqual((root / "symlink-target.txt").read_text(encoding="utf-8"), "outside\n")
            self.assertEqual(stat.S_IMODE(anchor_config.stat().st_mode), anchor_mode)

            refreshed = MATERIALIZE.materialize(
                project, folder, command="refresh-context", mode="shared-read"
            )
            self.assertFalse(refreshed.blocked)
            self.assertFalse(stat.S_IMODE((child / "tracked.txt").stat().st_mode) & 0o222)

            checked = MATERIALIZE.destroy(project, folder, mode="shared-read", check_only=True)
            self.assertEqual(checked.command, "destroy-check")
            MATERIALIZE.destroy(project, folder, mode="shared-read")
            self.assertFalse(folder.exists())

    def test_enforcement_refuses_dirty_member_before_chmod(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _ = self._fixture(root)
            folder = root / "instances" / "read"
            result = MATERIALIZE.materialize(project, folder, command="setup", mode="shared-read")
            child = folder / MATERIALIZE.MEMBERS_DIRECTORY / "child"
            (child / "tracked.txt").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(MATERIALIZE.ProjectFolderError, "dirty child"):
                MATERIALIZE._enforce_shared_read_worktrees(result.members)
            self.assertTrue(stat.S_IMODE((child / "tracked.txt").stat().st_mode) & stat.S_IWUSR)

    def test_enforcement_is_rejected_outside_shared_read_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _ = self._fixture(root)
            with self.assertRaisesRegex(MATERIALIZE.ProjectFolderError, "only with shared-read setup"):
                MATERIALIZE.materialize(
                    project, root / "instances" / "write", command="setup",
                    mode="exclusive-write", enforce_readonly=True,
                )


if __name__ == "__main__":
    unittest.main()
