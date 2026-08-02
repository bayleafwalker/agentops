from __future__ import annotations

import hashlib
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


class MaterializedContextProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment_records = self.root / "no-environment-record"
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        (self.workspace / "AGENTS.md").write_text("# Workspace environment\n", encoding="utf-8")
        self.repos = {name: self._clone(name) for name in ("home", "child")}
        self._write_fixture()
        self.project_path = self.repos["home"] / "project.toml"
        self.project = RENDER.load_project(self.project_path)
        RENDER.apply_project(self.project, environment_records_dir=self.environment_records)
        self._commit_push(self.repos["child"], "chore(render): generated guidance")

    def _git(self, repo: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    def _clone(self, name: str) -> Path:
        remote = self.root / "remotes" / f"{name}.git"
        remote.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
        repo = self.workspace / name
        subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True)
        self._git(repo, "config", "user.email", "tests@example.invalid")
        self._git(repo, "config", "user.name", "Context Tests")
        return repo

    def _commit_push(self, repo: Path, message: str) -> None:
        self._git(repo, "add", ".")
        self._git(repo, "commit", "-m", message)
        self._git(repo, "push", "origin", "main")

    def _write(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def _write_fixture(self) -> None:
        for name, repo in self.repos.items():
            self._write(repo / "AGENTS.md", f"# {name} repository\n")
        self._write(
            self.repos["home"] / "project.toml",
            """schema_version = 1
project_id = "f46fc856-7f25-48eb-9e48-cf795c1c8a41"
display_name = "context fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"

[[members]]
repo_id = "child"
backlog = true
render = "full"
""",
        )
        self._write(
            self.repos["home"] / ".project" / "sources" / "10-baseline.md",
            "---\nrender_levels: [baseline, full]\n---\n# Baseline\n",
        )
        self._write(
            self.repos["home"] / ".project" / "sources" / "20-full.md",
            "---\nrender_levels: [full]\n---\n# Full\n",
        )
        self._write(
            self.repos["child"] / ".agents" / "overlays" / "child.project-overrides.md",
            "# Child overlay\n",
        )
        for repo in self.repos.values():
            self._commit_push(repo, "initial")

    def _materialize(self, folder: Path, *, command: str, mode: str = "exclusive-write"):
        return MATERIALIZE.materialize(
            self.project, folder, command=command, mode=mode,
            environment_records_dir=self.environment_records,
        )

    def test_context_records_actual_sources_and_marker_bundle(self) -> None:
        folder = self.root / "instances" / "context"
        self._materialize(folder, command="setup")
        context = json.loads((folder / MATERIALIZE.CONTEXT_NAME).read_text(encoding="utf-8"))
        marker = json.loads((folder / MATERIALIZE.MARKER_NAME).read_text(encoding="utf-8"))
        sources = context["context_sources"]
        self.assertEqual(marker["context_bundle_sha256"], context["context_bundle_sha256"])
        self.assertEqual(
            context["context_bundle_sha256"],
            hashlib.sha256(json.dumps(sources, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        )
        expected = {
            ("environment", "agents", str(self.workspace / "AGENTS.md")),
            ("project", "binding", "members/home/project.toml"),
            ("project", "project-source", "members/home/.project/sources/10-baseline.md"),
            ("project", "project-source", "members/home/.project/sources/20-full.md"),
            ("repository", "agents", "members/home/AGENTS.md"),
            ("repository", "agents", "members/child/AGENTS.md"),
            ("repository", "generated-project-guidance", "members/child/.agents/project.generated.md"),
            ("repository", "member-overlay", "members/child/.agents/overlays/child.project-overrides.md"),
        }
        actual = {(row["scope"], row["kind"], row["path"]) for row in sources}
        self.assertTrue(expected <= actual)
        for row in sources:
            self.assertRegex(row["sha256"], r"^[0-9a-f]{64}$")
            if row["scope"] != "environment":
                self.assertRegex(row["source_commit"], r"^[0-9a-f]{40}$")

    def test_shared_read_uses_detached_member_files_and_explain_is_persisted(self) -> None:
        folder = self.root / "instances" / "read"
        self._materialize(folder, command="setup", mode="shared-read")
        before = (folder / MATERIALIZE.CONTEXT_NAME).read_bytes()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "materialize_project.py"), "context",
             "--project", str(self.project_path), "--folder", str(folder),
             "--mode", "shared-read", "--environment-records-dir", str(self.environment_records), "--explain"],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((folder / MATERIALIZE.CONTEXT_NAME).read_bytes(), before)
        self.assertIn("Context bundle sha256:", result.stdout)
        self.assertIn("kind=member-overlay", result.stdout)
        self.assertIn("members/child/.agents/overlays/child.project-overrides.md", result.stdout)
        child = folder / MATERIALIZE.MEMBERS_DIRECTORY / "child"
        self.assertEqual(self._git(child, "rev-parse", "--abbrev-ref", "HEAD"), "HEAD")

    def test_status_missing_instance_does_not_create_its_folder(self) -> None:
        folder = self.root / "instances" / "missing"
        with self.assertRaisesRegex(MATERIALIZE.ProjectFolderError, "does not exist"):
            self._materialize(folder, command="status")
        self.assertFalse(folder.exists())
