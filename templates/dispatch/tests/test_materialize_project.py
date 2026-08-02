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
    def setUp(self) -> None:
        # Isolate from whatever environment record (if any) resolves for the
        # real host running the suite; environment-context wiring is covered
        # separately in test_render_environment_wiring.py.
        no_env = tempfile.TemporaryDirectory()
        self.addCleanup(no_env.cleanup)
        self.no_env_dir = Path(no_env.name)

    def _materialize(self, project, folder: Path, *, command: str, **kwargs):
        return MATERIALIZE.materialize(
            project,
            folder,
            command=command,
            environment_records_dir=self.no_env_dir,
            **kwargs,
        )

    def _cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "materialize_project.py"), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

    def _git(self, repo: Path, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _git_result(self, repo: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )

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
        RENDER.apply_project(
            RENDER.load_project(project_path), environment_records_dir=self.no_env_dir
        )
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

    def test_setup_recovers_after_legacy_external_folder_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            folder = root / "project-folders" / "fixture"

            first = self._materialize(project, folder, command="setup")
            first_snapshot = self._snapshot(folder, repos)
            self.assertFalse((folder / ".git").exists())
            self.assertFalse(first.blocked)
            self.assertIn(
                "cd members/home && sprintctl usage --context --project --json",
                first_snapshot["agents"].decode("utf-8"),
            )
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

            # This models a pre-v2 folder removed outside the lifecycle tool;
            # normal cleanup is covered by the checked `destroy` command below.
            shutil.rmtree(folder)
            second = self._materialize(project, folder, command="setup")

            self.assertFalse(second.blocked)
            self.assertEqual(self._snapshot(folder, repos), first_snapshot)
            for name, repo in repos.items():
                worktrees = self._git(repo, "worktree", "list", "--porcelain")
                expected_path = folder / MATERIALIZE.MEMBERS_DIRECTORY / name
                self.assertEqual(worktrees.count(f"worktree {expected_path}"), 1)
                self.assertNotIn("prunable", worktrees)

    def test_sync_fast_forwards_members_but_keeps_home_binding_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            folder = root / "project-folders" / "fixture"
            self._materialize(project, folder, command="setup")

            self._write(repos["child"] / "upstream.txt", "upstream\n")
            child_head = self._commit_push(repos["child"], "upstream child change")
            source = repos["home"] / ".project" / "sources" / "10-shared.md"
            source.write_text(
                source.read_text(encoding="utf-8") + "# Source update\n",
                encoding="utf-8",
            )
            home_head = self._commit_push(repos["home"], "project source update")

            result = self._materialize(project, folder, command="sync")
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
            self.assertNotEqual(states["home"].head, home_head)
            self.assertEqual(states["child"].head, child_head)
            self.assertEqual(states["home"].status, "behind")
            self.assertEqual(states["child"].status, "updated")
            self.assertTrue(
                (
                    folder / MATERIALIZE.MEMBERS_DIRECTORY / "child" / "upstream.txt"
                ).exists()
            )
            self.assertNotIn("# Source update", generated.read_text(encoding="utf-8"))
            self.assertEqual(context["command"], "sync")
            child_context = next(
                member for member in context["members"] if member["repo_id"] == "child"
            )
            self.assertFalse(child_context["dirty_after_render"])

    def test_sync_reports_non_fast_forward_without_resolving(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            folder = root / "project-folders" / "fixture"
            self._materialize(project, folder, command="setup")
            child_worktree = folder / MATERIALIZE.MEMBERS_DIRECTORY / "child"

            self._write(child_worktree / "local.txt", "local\n")
            self._git(child_worktree, "add", "local.txt")
            self._git(child_worktree, "commit", "-m", "local project commit")
            local_head = self._git(child_worktree, "rev-parse", "HEAD")
            self._write(repos["child"] / "remote.txt", "remote\n")
            self._commit_push(repos["child"], "independent upstream commit")

            result = self._materialize(project, folder, command="sync")
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
                self._materialize(project, occupied, command="setup")
            with self.assertRaisesRegex(
                MATERIALIZE.ProjectFolderError, "inside member"
            ):
                self._materialize(
                    project, repos["home"] / "nested", command="setup"
                )

    def test_exclusive_instances_have_unique_branches_and_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            alpha = root / "project-folders" / "fixture--alpha"
            beta = root / "project-folders" / "fixture--beta"

            first = self._materialize(
                project, alpha, command="setup", instance="alpha", mode="exclusive-write"
            )
            second = self._materialize(
                project, beta, command="setup", instance="beta", mode="exclusive-write"
            )

            self.assertFalse(first.blocked)
            self.assertFalse(second.blocked)
            alpha_marker = json.loads((alpha / MATERIALIZE.MARKER_NAME).read_text())
            beta_marker = json.loads((beta / MATERIALIZE.MARKER_NAME).read_text())
            for marker, instance in ((alpha_marker, "alpha"), (beta_marker, "beta")):
                self.assertEqual(marker["schema_version"], 2)
                self.assertEqual(marker["instance_id"], instance)
                self.assertEqual(marker["mode"], "exclusive-write")
                self.assertEqual(marker["source_binding_commit"], self._git(repos["home"], "rev-parse", "HEAD"))
                self.assertEqual(len(marker["source_binding_sha256"]), 64)
            self.assertNotEqual(alpha_marker["source_binding_sha256"], "")
            alpha_branches = {member.repo_id: member.branch for member in first.members}
            beta_branches = {member.repo_id: member.branch for member in second.members}
            self.assertNotEqual(alpha_branches, beta_branches)
            self.assertTrue(all("/alpha/" in branch for branch in alpha_branches.values()))
            self.assertTrue(all("/beta/" in branch for branch in beta_branches.values()))

            context = json.loads((alpha / MATERIALIZE.CONTEXT_NAME).read_text())
            self.assertEqual(context["instance_id"], "alpha")
            self.assertEqual(context["mode"], "exclusive-write")
            self.assertEqual(context["source_binding_commit"], alpha_marker["source_binding_commit"])
            self.assertEqual(context["source_binding_sha256"], alpha_marker["source_binding_sha256"])

    def test_shared_read_instance_is_detached_at_recorded_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            project = RENDER.load_project(project_path)
            folder = root / "project-folders" / "fixture-read"

            result = self._materialize(
                project, folder, command="setup", instance="read", mode="shared-read"
            )

            self.assertFalse(result.blocked)
            marker = json.loads((folder / MATERIALIZE.MARKER_NAME).read_text())
            self.assertEqual(marker["mode"], "shared-read")
            for state in result.members:
                worktree = folder / MATERIALIZE.MEMBERS_DIRECTORY / state.repo_id
                self.assertEqual(
                    self._git_result(worktree, "symbolic-ref", "--quiet", "--short", "HEAD").returncode,
                    1,
                )
                self.assertEqual(
                    self._git(worktree, "rev-parse", "HEAD"),
                    self._git(repos[state.repo_id], "rev-parse", "origin/main"),
                )

    def test_setup_rejects_instance_names_that_are_not_branch_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, _repos = self._fixture(root)
            project = RENDER.load_project(project_path)

            for instance in ("nested/name", "has space", "-option", "bad~ref"):
                with self.subTest(instance=instance):
                    with self.assertRaisesRegex(
                        MATERIALIZE.ProjectFolderError, "instance must match"
                    ):
                        self._materialize(
                            project,
                            root / "project-folders" / "invalid",
                            command="setup",
                            instance=instance,
                        )

    def test_status_and_refresh_context_do_not_advance_member_heads(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)
            folder = root / "project-folders" / "fixture"
            setup = self._cli(
                "setup", "--project", str(project_path), "--folder", str(folder),
                "--instance", "default", "--mode", "exclusive-write",
                "--environment-records-dir", str(self.no_env_dir),
            )
            self.assertEqual(setup.returncode, 0, setup.stdout + setup.stderr)
            before = {
                name: self._git(folder / MATERIALIZE.MEMBERS_DIRECTORY / name, "rev-parse", "HEAD")
                for name in repos
            }
            child_tracking_before = self._git(repos["child"], "rev-parse", "origin/main")
            # Give origin new commits through an independent clone.  A status or
            # context refresh must not fetch them or move the checked-out heads.
            publisher = root / "publisher"
            subprocess.run(["git", "clone", str(root / "remotes" / "child.git"), str(publisher)], check=True, capture_output=True, text=True)
            self._git(publisher, "config", "user.email", "tests@example.invalid")
            self._git(publisher, "config", "user.name", "Publisher")
            self._write(publisher / "published.txt", "later\n")
            self._git(publisher, "add", "published.txt")
            self._git(publisher, "commit", "-m", "later upstream")
            self._git(publisher, "push", "origin", "main")

            for command in ("status", "refresh-context"):
                result = self._cli(
                    command, "--project", str(project_path), "--folder", str(folder),
                    "--instance", "default", "--mode", "exclusive-write",
                    "--environment-records-dir", str(self.no_env_dir),
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            after = {
                name: self._git(folder / MATERIALIZE.MEMBERS_DIRECTORY / name, "rev-parse", "HEAD")
                for name in repos
            }
            self.assertEqual(after, before)
            self.assertEqual(
                self._git(repos["child"], "rev-parse", "origin/main"),
                child_tracking_before,
            )
            self.assertFalse((folder / MATERIALIZE.MEMBERS_DIRECTORY / "child" / "published.txt").exists())

    def test_destroy_refuses_live_or_unprotected_state_and_removes_clean_worktrees(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_path, repos = self._fixture(root)

            def setup(instance: str) -> Path:
                folder = root / "project-folders" / f"fixture--{instance}"
                result = self._cli(
                    "setup", "--project", str(project_path), "--folder", str(folder),
                    "--instance", instance, "--mode", "exclusive-write",
                    "--environment-records-dir", str(self.no_env_dir),
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return folder

            def destroy(folder: Path, instance: str) -> subprocess.CompletedProcess[str]:
                return self._cli(
                    "destroy", "--project", str(project_path), "--folder", str(folder),
                    "--instance", instance, "--mode", "exclusive-write",
                    "--environment-records-dir", str(self.no_env_dir),
                )

            dirty = setup("dirty")
            self._write(dirty / MATERIALIZE.MEMBERS_DIRECTORY / "child" / "untracked.txt", "nope\n")
            refused = destroy(dirty, "dirty")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("dirty", refused.stderr)
            self.assertTrue(dirty.exists())

            ahead = setup("ahead")
            child = ahead / MATERIALIZE.MEMBERS_DIRECTORY / "child"
            self._write(child / "local.txt", "local\n")
            self._git(child, "add", "local.txt")
            self._git(child, "commit", "-m", "unprotected local change")
            refused = destroy(ahead, "ahead")
            self.assertEqual(refused.returncode, 2)
            self.assertRegex(refused.stderr, "non-fast-forward|ahead|current")
            self.assertTrue(ahead.exists())

            leased = setup("leased")
            self._write(leased / ".agentops-project-folder.lease", "active\n")
            refused = destroy(leased, "leased")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("leased", refused.stderr)

            session = setup("session")
            self._write(session / ".session" / "handoff.md", "keep this\n")
            refused = destroy(session, "session")
            self.assertEqual(refused.returncode, 2)
            self.assertIn("non-empty .session", refused.stderr)

            clean = setup("clean")
            removed = destroy(clean, "clean")
            self.assertEqual(removed.returncode, 0, removed.stdout + removed.stderr)
            self.assertFalse(clean.exists())
            for repo in repos.values():
                self.assertNotIn(str(clean / MATERIALIZE.MEMBERS_DIRECTORY), self._git(repo, "worktree", "list", "--porcelain"))

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
                    "--environment-records-dir",
                    str(self.no_env_dir),
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
                    "--environment-records-dir",
                    str(self.no_env_dir),
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
