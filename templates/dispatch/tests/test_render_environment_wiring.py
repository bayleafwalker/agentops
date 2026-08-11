from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "render_project.py"
SPEC = importlib.util.spec_from_file_location("project_render_env", SCRIPT)
assert SPEC and SPEC.loader
RENDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RENDER
SPEC.loader.exec_module(RENDER)


class EnvironmentWiringTests(unittest.TestCase):
    """Covers render_project.py's environment-context wiring: resolution,
    injection into .agents/environment.generated.md + AGENTS.md, staleness
    detection, and correct no-op behavior when no record resolves -- the two
    sub-scopes item #1190 deferred (see evidence note #1407)."""

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
            ["git", "-C", str(path), "config", "user.name", "Env Wiring Tests"],
            check=True,
        )
        subprocess.run(["git", "-C", str(path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(path), "commit", "-qm", "baseline"], check=True)

    def _fixture(self, root: Path) -> tuple[Path, dict[str, Path]]:
        workspace = root / "workspace"
        repos = {name: workspace / name for name in ("home", "member")}
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
repo_id = "member"
backlog = true
render = "baseline"
""",
        )
        self._write(
            repos["home"] / ".project" / "sources" / "10-shared.md",
            "---\nrender_levels: [baseline]\n---\n# Shared\n",
        )
        for repo in repos.values():
            self._init_repo(repo)
        return repos["home"] / "project.toml", repos

    def _record(self, root: Path, *, record_id: str = "testhost") -> Path:
        records_dir = root / "records"
        records_dir.mkdir(parents=True, exist_ok=True)
        path = records_dir / f"{record_id}.vuoro-shared.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "environment-record/v1",
                    "id": record_id,
                    "environment_class": "local",
                    "revision": 1,
                    "roles": ["secret-role"],
                    "constraints": ["some-constraint"],
                    "capabilities": ["secret-capability"],
                    "runbook_refs": ["/docs/runbook.md"],
                    "identity_bindings": [
                        {"principal": "secret-principal", "roles": ["r"]}
                    ],
                }
            )
        )
        return records_dir

    def test_no_matching_record_is_not_applicable_and_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            empty_records = Path(temporary) / "empty-records"
            empty_records.mkdir()
            project = RENDER.load_project(project_path)

            statuses = RENDER.apply_project(
                project, environment_records_dir=empty_records
            )

            for status in statuses:
                self.assertEqual(status.environment, "not-applicable")
                self.assertEqual(status.environment_pointer, "not-applicable")
            for repo in repos.values():
                self.assertFalse((repo / ".agents" / "environment.generated.md").exists())

    def test_resolved_record_injects_bounded_block_and_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            records_dir = self._record(Path(temporary))
            project = RENDER.load_project(project_path)

            # apply_project has no hostname override of its own -- it always
            # resolves against the real host via resolve_environment_record's
            # socket.gethostname() default, so tests patch that directly
            # rather than threading a test-only parameter through the CLI's
            # public surface.
            import socket

            original = socket.gethostname
            socket.gethostname = lambda: "testhost"  # type: ignore[assignment]
            try:
                statuses = RENDER.apply_project(
                    project, environment_records_dir=records_dir
                )
            finally:
                socket.gethostname = original  # type: ignore[assignment]

            for repo_id, repo in repos.items():
                env_file = repo / ".agents" / "environment.generated.md"
                self.assertTrue(env_file.exists(), f"{repo_id} missing environment file")
                content = env_file.read_text()
                self.assertIn("testhost", content)
                self.assertIn("some-constraint", content)
                self.assertIn("/docs/runbook.md", content)
                self.assertNotIn("secret-role", content)
                self.assertNotIn("secret-capability", content)
                self.assertNotIn("secret-principal", content)

                agents = (repo / "AGENTS.md").read_text()
                self.assertIn("environment.generated.md", agents)

            for status in statuses:
                self.assertEqual(status.environment, "in-sync")
                self.assertEqual(status.environment_pointer, "in-sync")

    def test_reference_member_is_read_only_for_active_environment_render(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            project_path.write_text(
                project_path.read_text(encoding="utf-8").replace(
                    'repo_id = "member"\nbacklog = true\nrender = "baseline"',
                    'repo_id = "member"\nbacklog = true\nrender = "baseline"\naccess = "reference"',
                ),
                encoding="utf-8",
            )
            subprocess.run(["git", "-C", str(repos["home"]), "add", "project.toml"], check=True)
            subprocess.run(["git", "-C", str(repos["home"]), "commit", "-qm", "reference role"], check=True)
            records_dir = self._record(Path(temporary))
            project = RENDER.load_project(project_path)
            import socket

            original = socket.gethostname
            socket.gethostname = lambda: "testhost"  # type: ignore[assignment]
            try:
                statuses = RENDER.apply_project(project, environment_records_dir=records_dir)
            finally:
                socket.gethostname = original  # type: ignore[assignment]

            self.assertTrue((repos["home"] / ".agents" / "environment.generated.md").exists())
            self.assertFalse((repos["member"] / ".agents" / "environment.generated.md").exists())
            self.assertNotIn("environment.generated.md", (repos["member"] / "AGENTS.md").read_text())
            member_status = next(item for item in statuses if item.repo_id == "member")
            self.assertEqual(member_status.environment, "not-applicable")
            self.assertEqual(member_status.environment_pointer, "not-applicable")

    def test_stale_record_content_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            records_dir = self._record(Path(temporary))
            project = RENDER.load_project(project_path)

            import socket

            original = socket.gethostname
            socket.gethostname = lambda: "testhost"  # type: ignore[assignment]
            try:
                RENDER.apply_project(project, environment_records_dir=records_dir)

                record_path = records_dir / "testhost.vuoro-shared.json"
                data = json.loads(record_path.read_text())
                data["constraints"] = ["a-new-constraint"]
                record_path.write_text(json.dumps(data))

                statuses = {
                    status.repo_id: status
                    for status in RENDER.inspect_project(
                        project, environment_records_dir=records_dir
                    )
                }
            finally:
                socket.gethostname = original  # type: ignore[assignment]

            self.assertEqual(statuses["home"].environment, "stale")

    def test_record_no_longer_resolving_marks_stale_not_deleted_silently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project_path, repos = self._fixture(Path(temporary))
            records_dir = self._record(Path(temporary))
            project = RENDER.load_project(project_path)

            import socket

            original = socket.gethostname
            socket.gethostname = lambda: "testhost"  # type: ignore[assignment]
            try:
                RENDER.apply_project(project, environment_records_dir=records_dir)
            finally:
                socket.gethostname = original  # type: ignore[assignment]

            # Simulate the host no longer having a resolvable record (e.g. the
            # record was removed) without deleting the previously-rendered file.
            (records_dir / "testhost.vuoro-shared.json").unlink()
            statuses = {
                status.repo_id: status
                for status in RENDER.inspect_project(
                    project, environment_records_dir=records_dir
                )
            }
            self.assertEqual(statuses["home"].environment, "stale")
            self.assertTrue(
                (repos["home"] / ".agents" / "environment.generated.md").exists()
            )


if __name__ == "__main__":
    unittest.main()
