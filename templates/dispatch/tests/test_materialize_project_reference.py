from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import materialize_project as MATERIALIZE  # noqa: E402
import render_project as RENDER  # noqa: E402


class ReferenceMemberMaterializationTests(unittest.TestCase):
    def _git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def _clone(self, root: Path, name: str) -> Path:
        remote = root / "remotes" / f"{name}.git"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(remote)],
            check=True, capture_output=True,
        )
        repo = root / "workspace" / name
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True)
        self._git(repo, "config", "user.email", "tests@example.invalid")
        self._git(repo, "config", "user.name", "Reference Member Tests")
        return repo

    def _commit_push(self, repo: Path, message: str) -> str:
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", message)
        self._git(repo, "push", "origin", "main")
        return self._git(repo, "rev-parse", "HEAD")

    def _fixture(self, root: Path) -> tuple[RENDER.ProjectBinding, dict[str, Path]]:
        repos = {name: self._clone(root, name) for name in ("home", "reference")}
        (repos["home"] / "AGENTS.md").write_text("# home\n", encoding="utf-8")
        (repos["reference"] / "AGENTS.md").write_text("# reference\n", encoding="utf-8")
        (repos["home"] / "project.toml").write_text(
            """schema_version = 1
project_id = "f46fc856-7f25-48eb-9e48-cf795c1c8a41"
display_name = "reference-fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"

[[members]]
repo_id = "reference"
backlog = false
render = "full"
relationship = "reference"
access = "reference"
""",
            encoding="utf-8",
        )
        source = repos["home"] / ".project" / "sources" / "10-shared.md"
        source.parent.mkdir(parents=True)
        source.write_text("---\nrender_levels: [full]\n---\n# Shared\n", encoding="utf-8")
        for repo in repos.values():
            self._commit_push(repo, "initial")
        return RENDER.load_project(repos["home"] / "project.toml"), repos

    def test_reference_member_is_detached_unrendered_and_never_advanced_by_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, repos = self._fixture(root)
            folder = root / "instances" / "exclusive"
            no_environment = root / "no-environment"

            initial = MATERIALIZE.materialize(
                project, folder, command="setup", instance="task-1",
                mode="exclusive-write", environment_records_dir=no_environment,
            )
            reference = folder / MATERIALIZE.MEMBERS_DIRECTORY / "reference"
            original_head = self._git(reference, "rev-parse", "HEAD")
            self.assertEqual(
                self._git(reference, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD"
            )
            self.assertFalse((reference / ".agents" / "project.generated.md").exists())
            self.assertEqual((reference / "AGENTS.md").read_text(encoding="utf-8"), "# reference\n")
            self.assertEqual((reference / "AGENTS.md").stat().st_mode & 0o222, 0)
            reference_state = next(state for state in initial.members if state.repo_id == "reference")
            self.assertEqual(reference_state.effective_mode, "shared-read")

            (repos["reference"] / "new.txt").write_text("new\n", encoding="utf-8")
            updated_head = self._commit_push(repos["reference"], "advance reference")
            self.assertNotEqual(updated_head, original_head)

            synced = MATERIALIZE.materialize(
                project, folder, command="sync", instance="task-1",
                mode="exclusive-write", environment_records_dir=no_environment,
            )
            state = next(item for item in synced.members if item.repo_id == "reference")
            self.assertEqual(state.status, "behind")
            self.assertEqual(state.effective_mode, "shared-read")
            self.assertEqual(self._git(reference, "rev-parse", "HEAD"), original_head)
            self.assertEqual(
                self._git(reference, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD"
            )
            self.assertFalse((reference / ".agents" / "project.generated.md").exists())

            context = json.loads((folder / MATERIALIZE.CONTEXT_NAME).read_text(encoding="utf-8"))
            member = next(item for item in context["members"] if item["repo_id"] == "reference")
            self.assertEqual(member["effective_mode"], "shared-read")
            self.assertTrue(member["reference"])
            self.assertEqual(member["sync_status"], "behind")

            checked = MATERIALIZE.destroy(
                project, folder, instance="task-1", mode="exclusive-write", check_only=True
            )
            self.assertEqual(next(item for item in checked.members if item.repo_id == "reference").status, "behind")
            MATERIALIZE.destroy(project, folder, instance="task-1", mode="exclusive-write")
            self.assertFalse(folder.exists())


if __name__ == "__main__":
    unittest.main()
