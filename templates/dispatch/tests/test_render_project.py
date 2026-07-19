from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "render_project.py"
SPEC = importlib.util.spec_from_file_location("project_render", SCRIPT)
assert SPEC and SPEC.loader
RENDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RENDER
SPEC.loader.exec_module(RENDER)


class ProjectRenderTests(unittest.TestCase):
    def _write(self, path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def _init_repo(self, path: Path) -> None:
        subprocess.run(["git", "init", "-q", str(path)], check=True)
        subprocess.run(
            ["git", "-C", str(path), "config", "user.email", "tests@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(path), "config", "user.name", "Project Render Tests"],
            check=True,
        )
        subprocess.run(["git", "-C", str(path), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(path), "commit", "-qm", "baseline"], check=True
        )

    def _fixture(
        self, root: Path, *, initialize_git: bool = True
    ) -> tuple[Path, dict[str, Path]]:
        workspace = root / "workspace"
        repos = {
            name: workspace / name
            for name in ("home", "full-member", "baseline-member")
        }
        for repo in repos.values():
            repo.mkdir(parents=True)
            self._write(repo / "AGENTS.md", f"# {repo.name}\n")

        self._write(
            repos["home"] / "project.toml",
            """schema_version = 1
project_id = "31d5cdbd-063a-46ef-a27b-dfb1de9669d8"
display_name = "fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"

[[members]]
repo_id = "full-member"
backlog = true
render = "full"

[[members]]
repo_id = "baseline-member"
backlog = false
render = "baseline"
""",
        )
        self._write(
            repos["home"] / ".project" / "sources" / "10-shared.md",
            """---
render_levels: [baseline, full]
---
# Shared
""",
        )
        self._write(
            repos["home"] / ".project" / "sources" / "20-full.md",
            """---
render_levels: [full]
---
# Full only
""",
        )
        self._write(
            repos["full-member"]
            / ".agents"
            / "overlays"
            / "full-member.project-overrides.md",
            "# Full override\n",
        )
        if initialize_git:
            for repo in repos.values():
                self._init_repo(repo)
        return repos["home"] / "project.toml", repos

    def _commit_all(self, repos: dict[str, Path], message: str) -> None:
        for repo in repos.values():
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            diff = subprocess.run(
                ["git", "-C", str(repo), "diff", "--cached", "--quiet"], check=False
            )
            if diff.returncode == 1:
                subprocess.run(
                    ["git", "-C", str(repo), "commit", "-qm", message], check=True
                )

    def test_render_levels_override_order_and_determinism(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, _repos = self._fixture(Path(temporary), initialize_git=False)
            project = RENDER.load_project(project_path)
            fragments = RENDER.load_fragments(project)
            members = {member.repo_id: member for member in project.members}

            full_first = RENDER.expected_render(
                project, members["full-member"], fragments
            )
            full_second = RENDER.expected_render(
                project, members["full-member"], fragments
            )
            baseline = RENDER.expected_render(
                project, members["baseline-member"], fragments
            )

            self.assertEqual(full_first.content, full_second.content)
            self.assertIn(
                b"# Shared\n# Full only\n# Full override\n", full_first.content
            )
            self.assertIn(b"# Shared\n", baseline.content)
            self.assertNotIn(b"# Full only", baseline.content)
            self.assertNotIn(b"# Full override", baseline.content)

    def test_apply_is_idempotent_and_preserves_agents_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            project = RENDER.load_project(project_path)

            first = RENDER.apply_project(project)
            full_output = (
                repos["full-member"] / ".agents" / "project.generated.md"
            ).read_bytes()
            full_agents = (repos["full-member"] / "AGENTS.md").read_bytes()
            self._commit_all(repos, "render")
            second = RENDER.apply_project(project)

            self.assertFalse(any(status.needs_sync for status in first))
            self.assertFalse(any(status.needs_sync for status in second))
            self.assertEqual(
                (
                    repos["full-member"] / ".agents" / "project.generated.md"
                ).read_bytes(),
                full_output,
            )
            self.assertEqual(
                (repos["full-member"] / "AGENTS.md").read_bytes(), full_agents
            )
            self.assertTrue(full_agents.startswith(b"# full-member\n"))
            self.assertEqual(full_agents.count(RENDER.POINTER_START), 1)

    def test_check_distinguishes_stale_source_from_hand_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            project = RENDER.load_project(project_path)
            RENDER.apply_project(project)
            self._commit_all(repos, "render")

            generated = repos["full-member"] / ".agents" / "project.generated.md"
            generated.write_bytes(generated.read_bytes() + b"manual edit\n")
            statuses = {
                status.repo_id: status for status in RENDER.inspect_project(project)
            }
            self.assertEqual(statuses["full-member"].generated, "hand-edited")

            subprocess.run(
                ["git", "-C", str(repos["full-member"]), "restore", str(generated)],
                check=True,
            )
            source = repos["home"] / ".project" / "sources" / "10-shared.md"
            source.write_bytes(source.read_bytes() + b"source edit\n")
            statuses = {
                status.repo_id: status for status in RENDER.inspect_project(project)
            }
            self.assertEqual(statuses["full-member"].generated, "stale")
            self.assertEqual(statuses["baseline-member"].generated, "stale")

    def test_project_metadata_change_is_stale_not_hand_edited(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            project = RENDER.load_project(project_path)
            RENDER.apply_project(project)
            self._commit_all(repos, "render")
            project_path.write_text(
                project_path.read_text(encoding="utf-8").replace(
                    'display_name = "fixture"', 'display_name = "renamed"'
                ),
                encoding="utf-8",
            )

            statuses = {
                status.repo_id: status
                for status in RENDER.inspect_project(RENDER.load_project(project_path))
            }

            self.assertEqual(statuses["full-member"].generated, "stale")
            self.assertIn("binding metadata", statuses["full-member"].detail)

    def test_apply_refuses_dirty_source_or_managed_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            project = RENDER.load_project(project_path)
            source = repos["home"] / ".project" / "sources" / "10-shared.md"
            source.write_bytes(source.read_bytes() + b"dirty\n")

            with self.assertRaisesRegex(RENDER.DirtyProjectError, "refusing --apply"):
                RENDER.apply_project(project)

    def test_render_none_removes_only_managed_output_and_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            home = repos["home"]
            generated = home / ".agents" / "project.generated.md"
            self._write(generated, RENDER.RENDER_PREFIX.decode() + "-->\n")
            original = (home / "AGENTS.md").read_bytes()
            (home / "AGENTS.md").write_bytes(RENDER._with_pointer(original))
            self._commit_all(repos, "stale managed output")

            statuses = RENDER.apply_project(RENDER.load_project(project_path))

            self.assertFalse(generated.exists())
            self.assertEqual(
                (home / "AGENTS.md").read_bytes(),
                RENDER._without_pointer(RENDER._with_pointer(original)),
            )
            home_status = next(
                status for status in statuses if status.repo_id == "home"
            )
            self.assertEqual(home_status.generated, "not-applicable")
            self.assertEqual(home_status.pointer, "not-applicable")

    def test_invalid_source_frontmatter_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary), initialize_git=False)
            self._write(
                repos["home"] / ".project" / "sources" / "30-invalid.md",
                "---\nrender_levels: [secret]\n---\nnope\n",
            )
            project = RENDER.load_project(project_path)

            with self.assertRaisesRegex(RENDER.ProjectRenderError, "render_levels"):
                RENDER.load_fragments(project)

    def test_out_of_order_pointer_is_reported_without_partial_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            agents = repos["baseline-member"] / "AGENTS.md"
            agents.write_bytes(
                RENDER.POINTER_END + b"\n" + RENDER.POINTER_START + b"\n"
            )
            self._commit_all(repos, "malformed pointer")
            project = RENDER.load_project(project_path)

            statuses = {
                status.repo_id: status for status in RENDER.inspect_project(project)
            }
            self.assertEqual(statuses["baseline-member"].pointer, "invalid")
            with self.assertRaisesRegex(RENDER.ProjectRenderError, "out of order"):
                RENDER.apply_project(project)
            self.assertFalse(
                (repos["full-member"] / ".agents" / "project.generated.md").exists()
            )

    def test_cli_check_apply_and_drift_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            command = [
                sys.executable,
                str(SCRIPT),
                "check",
                "--project",
                str(project_path),
            ]

            missing = subprocess.run(
                command, check=False, capture_output=True, text=True
            )
            applied = subprocess.run(
                [*command, "--apply"], check=False, capture_output=True, text=True
            )
            clean = subprocess.run(command, check=False, capture_output=True, text=True)
            generated = repos["full-member"] / ".agents" / "project.generated.md"
            generated.write_bytes(generated.read_bytes() + b"manual\n")
            drifted = subprocess.run(
                command, check=False, capture_output=True, text=True
            )

            self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)
            self.assertIn("generated=missing", missing.stdout)
            self.assertEqual(applied.returncode, 0, applied.stdout + applied.stderr)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            self.assertEqual(drifted.returncode, 1, drifted.stdout + drifted.stderr)
            self.assertIn("generated=hand-edited", drifted.stdout)


if __name__ == "__main__":
    unittest.main()
