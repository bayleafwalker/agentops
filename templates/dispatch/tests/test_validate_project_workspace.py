from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
PREFLIGHT = SCRIPTS / "validate_project_workspace.py"
MATERIALIZE = SCRIPTS / "materialize_project.py"
RENDER = SCRIPTS / "render_project.py"


class ProjectWorkspacePreflightTests(unittest.TestCase):
    def _run(self, script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(script), *arguments],
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

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _commit_push(self, repo: Path, message: str) -> None:
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", message)
        self._git(repo, "push", "origin", "main")

    def _fixture(self, root: Path) -> tuple[Path, dict[str, Path]]:
        repos: dict[str, Path] = {}
        for name in ("home", "child"):
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
            self._git(repo, "config", "user.name", "Workspace Preflight Tests")
            self._write(repo / "AGENTS.md", f"# {name}\n")
            repos[name] = repo

        project_path = repos["home"] / "project.toml"
        self._write(
            project_path,
            '''schema_version = 1
project_id = "31d5cdbd-063a-46ef-a27b-dfb1de9669d8"
display_name = "preflight-fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"
relationship = "governance"

[[members]]
repo_id = "child"
backlog = false
render = "full"
relationship = "implementation"
access = "write"
''',
        )
        self._write(
            repos["home"] / ".project" / "sources" / "10-shared.md",
            "---\nrender_levels: [baseline, full]\n---\n# Shared\n",
        )
        for repo in repos.values():
            self._commit_push(repo, "initial")
        rendered = self._run(RENDER, "check", "--project", str(project_path), "--apply")
        self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
        self._commit_push(repos["child"], "chore(render): project context")
        return project_path, repos

    def _materialize(self, root: Path, project: Path) -> Path:
        folder = root / "project-folders" / "fixture"
        result = self._run(
            MATERIALIZE,
            "setup",
            "--project",
            str(project),
            "--folder",
            str(folder),
            "--instance",
            "preflight",
            "--mode",
            "exclusive-write",
            "--environment-records-dir",
            str(root / "no-environment-records"),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return folder

    def test_json_preflight_proves_clean_canonical_and_materialized_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _repos = self._fixture(root)
            folder = self._materialize(root, project)

            result = self._run(
                PREFLIGHT,
                "--project",
                str(project),
                "--folder",
                str(folder),
                "--json",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["ok"])
            checks = {item["id"]: item for item in report["checks"]}
            self.assertEqual(checks["canonical-sources-clean"]["status"], "pass")
            self.assertEqual(checks["materialization-provenance"]["status"], "pass")
            self.assertEqual(checks["member-worktree:child"]["status"], "pass")
            self.assertEqual(checks["member-policy:child"]["status"], "pass")
            self.assertTrue(any("harness" in note for note in report["limitations"]))

    def test_tampered_provenance_and_root_direnv_are_validation_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _repos = self._fixture(root)
            folder = self._materialize(root, project)
            marker_path = folder / ".agentops-project-folder.json"
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["source_binding_sha256"] = "0" * 64
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            self._write(folder / ".envrc", "# unsafe aggregation signal\n")

            result = self._run(
                PREFLIGHT, "--project", str(project), "--folder", str(folder), "--json"
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            checks = {item["id"]: item for item in json.loads(result.stdout)["checks"]}
            self.assertEqual(checks["materialization-provenance"]["status"], "fail")
            self.assertEqual(checks["root-direnv-aggregation"]["status"], "fail")

    def test_supplied_projects_root_policy_is_inspected_with_explicit_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _repos = self._fixture(root)
            projects_root = root / "workspace" / "_projects"
            policy = root / "backup.exclude"
            self._write(policy, f"{projects_root}/**\n")

            result = self._run(
                PREFLIGHT,
                "--project",
                str(project),
                "--projects-root",
                str(projects_root),
                "--exclusion-policy",
                str(policy),
                "--json",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            check = next(
                item
                for item in json.loads(result.stdout)["checks"]
                if item["id"] == "projects-root-exclusion-policy"
            )
            self.assertEqual(check["status"], "pass")
            self.assertIn("does not validate backup", check["evidence"]["limitation"])

    def test_configuration_errors_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, _repos = self._fixture(root)
            policy = root / "backup.exclude"
            self._write(policy, "_projects/**\n")

            result = self._run(
                PREFLIGHT,
                "--project",
                str(project),
                "--exclusion-policy",
                str(policy),
                "--json",
            )

            self.assertEqual(result.returncode, 2)
            self.assertFalse(json.loads(result.stdout)["ok"])


if __name__ == "__main__":
    unittest.main()
