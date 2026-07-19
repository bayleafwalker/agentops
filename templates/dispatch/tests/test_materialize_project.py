from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import materialize_project as MATERIALIZE  # noqa: E402
import render_project as RENDER  # noqa: E402


class ProjectMaterializationTests(unittest.TestCase):
    def _git(self, repo: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _write(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def _commit_push(self, repo: Path, message: str) -> str:
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", message)
        self._git(repo, "push", "origin", "main")
        return self._git(repo, "rev-parse", "HEAD")

    def _clone(self, root: Path, name: str) -> Path:
        remote = root / "remotes" / f"{name}.git"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(remote)],
            check=True,
            capture_output=True,
        )
        repo = root / "workspace" / name
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", str(remote), str(repo)],
            check=True,
            capture_output=True,
        )
        self._git(repo, "config", "user.email", "tests@example.invalid")
        self._git(repo, "config", "user.name", "Project Folder Tests")
        return repo

    def _fixture(self, root: Path) -> tuple[Path, dict[str, Path]]:
        repos = {name: self._clone(root, name) for name in ("home", "child")}
        for name, repo in repos.items():
            self._write(repo / "AGENTS.md", f"# {name}\n")

        self._write(
            repos["home"] / "project.toml",
            """schema_version = 1
project_id = "f46fc856-7f25-48eb-9e48-cf795c1c8a41"
display_name = "fixture-project"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"

[[members]]
repo_id = "child"
backlog = true
render = "full"
path_notes = ["Child boundary note."]
""",
        )
        self._write(
            repos["home"] / ".project" / "sources" / "10-shared.md",
            """---
render_levels: [baseline, full]
---
# Shared context
""",
        )
        self._write(
            repos["child"] / ".agents" / "overlays" / "child.project-overrides.md",
            "# Child override\n",
        )
        for repo in repos.values():
            self._commit_push(repo, "initial")

        project_path = repos["home"] / "project.toml"
        RENDER.apply_project(RENDER.load_project(project_path))
        self._commit_push(repos["child"], "chore(render): initial project context")
        return project_path, repos

    def _snapshot(self, folder: Path, repos: dict[str, Path]) -> dict[str, object]:
        return {
            "agents": (folder / "AGENTS.md").read_bytes(),
            "context": (folder / MATERIALIZE.CONTEXT_NAME).read_bytes(),
            "generated": (
                folder
                / MATERIALIZE.MEMBERS_DIRECTORY
                / "child"
                / ".agents"
                / "project.generated.md"
            ).read_bytes(),
            "heads": {
                name: self._git(
                    folder / MATERIALIZE.MEMBERS_DIRECTORY / name,
                    "rev-parse",
                    "HEAD",
                )
                for name in repos
            },
        }

    def test_setup_delete_rebuild_is_identical_and_prunes_stale_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            folder = root / "project-folders" / "fixture"

            first = MATERIALIZE.materialize(project, folder, command="setup")
            first_snapshot = self._snapshot(folder, repos)
            self.assertFalse((folder / ".git").exists())
            self.assertFalse(first.blocked)
            self.assertTrue(
                all(
                    status.generated in {"in-sync", "not-applicable"}
                    for status in first.render_statuses
                )
            )
            for name in repos:
                worktree = folder / MATERIALIZE.MEMBERS_DIRECTORY / name
                self.assertEqual(
                    self._git(
                        worktree,
                        "rev-parse",
                        "--abbrev-ref",
                        "--symbolic-full-name",
                        "@{u}",
                    ),
                    "origin/main",
                )

            shutil.rmtree(folder)
            second = MATERIALIZE.materialize(project, folder, command="setup")

            self.assertFalse(second.blocked)
            self.assertEqual(self._snapshot(folder, repos), first_snapshot)
            for name, repo in repos.items():
                worktrees = self._git(repo, "worktree", "list", "--porcelain")
                expected_path = folder / MATERIALIZE.MEMBERS_DIRECTORY / name
                self.assertEqual(worktrees.count(f"worktree {expected_path}"), 1)
                self.assertNotIn("prunable", worktrees)

    def test_sync_fast_forwards_upstream_and_rerenders_source_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            folder = root / "project-folders" / "fixture"
            MATERIALIZE.materialize(project, folder, command="setup")

            self._write(repos["child"] / "upstream.txt", "upstream\n")
            child_head = self._commit_push(repos["child"], "upstream child change")
            source = repos["home"] / ".project" / "sources" / "10-shared.md"
            source.write_text(
                source.read_text(encoding="utf-8") + "# Source update\n",
                encoding="utf-8",
            )
            home_head = self._commit_push(repos["home"], "project source update")

            result = MATERIALIZE.materialize(project, folder, command="sync")
            states = {state.repo_id: state for state in result.members}
            generated = (
                folder
                / MATERIALIZE.MEMBERS_DIRECTORY
                / "child"
                / ".agents"
                / "project.generated.md"
            )
            context = json.loads(
                (folder / MATERIALIZE.CONTEXT_NAME).read_text(encoding="utf-8")
            )

            self.assertFalse(result.blocked)
            self.assertEqual(states["home"].head, home_head)
            self.assertEqual(states["child"].head, child_head)
            self.assertEqual(states["home"].status, "updated")
            self.assertEqual(states["child"].status, "updated")
            self.assertTrue(
                (
                    folder / MATERIALIZE.MEMBERS_DIRECTORY / "child" / "upstream.txt"
                ).exists()
            )
            self.assertIn("# Source update", generated.read_text(encoding="utf-8"))
            self.assertEqual(context["command"], "sync")
            child_context = next(
                member for member in context["members"] if member["repo_id"] == "child"
            )
            self.assertTrue(child_context["dirty_after_render"])

    def test_sync_reports_non_fast_forward_without_resolving(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            folder = root / "project-folders" / "fixture"
            MATERIALIZE.materialize(project, folder, command="setup")
            child_worktree = folder / MATERIALIZE.MEMBERS_DIRECTORY / "child"

            self._write(child_worktree / "local.txt", "local\n")
            self._git(child_worktree, "add", "local.txt")
            self._git(child_worktree, "commit", "-m", "local project commit")
            local_head = self._git(child_worktree, "rev-parse", "HEAD")
            self._write(repos["child"] / "remote.txt", "remote\n")
            self._commit_push(repos["child"], "independent upstream commit")

            result = MATERIALIZE.materialize(project, folder, command="sync")
            state = next(
                member for member in result.members if member.repo_id == "child"
            )

            self.assertTrue(result.blocked)
            self.assertEqual(state.status, "non-fast-forward")
            self.assertEqual(self._git(child_worktree, "rev-parse", "HEAD"), local_head)
            self.assertFalse((child_worktree / "remote.txt").exists())
            self.assertEqual(result.render_statuses, ())

    def test_setup_refuses_non_derived_or_nested_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            occupied = root / "occupied"
            self._write(occupied / "keep.txt", "keep\n")

            with self.assertRaisesRegex(
                MATERIALIZE.ProjectFolderError, "non-empty folder"
            ):
                MATERIALIZE.materialize(project, occupied, command="setup")
            with self.assertRaisesRegex(
                MATERIALIZE.ProjectFolderError, "inside member"
            ):
                MATERIALIZE.materialize(
                    project, repos["home"] / "nested", command="setup"
                )

    def test_cli_setup_and_sync_exit_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            folder = root / "project-folders" / "fixture"
            base = [sys.executable, str(SCRIPTS / "materialize_project.py")]

            setup = subprocess.run(
                [
                    *base,
                    "setup",
                    "--project",
                    str(project_path),
                    "--folder",
                    str(folder),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            sync = subprocess.run(
                [
                    *base,
                    "sync",
                    "--project",
                    str(project_path),
                    "--folder",
                    str(folder),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            self.assertEqual(sync.returncode, 0, sync.stdout + sync.stderr)
            self.assertIn("setup:", setup.stdout)
            self.assertIn("sync:", sync.stdout)


if __name__ == "__main__":
    unittest.main()
