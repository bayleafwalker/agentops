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


class ProjectMaterializationLeaseTests(unittest.TestCase):
    def _git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments], check=True, capture_output=True, text=True
        ).stdout.strip()

    def _fixture(self, root: Path) -> tuple[RENDER.ProjectBinding, Path, Path]:
        remote = root / "remote.git"
        subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
        home = root / "workspace" / "home"
        subprocess.run(["git", "clone", str(remote), str(home)], check=True, capture_output=True)
        self._git(home, "config", "user.email", "tests@example.invalid")
        self._git(home, "config", "user.name", "Lease Tests")
        (home / "AGENTS.md").write_text("# home\n", encoding="utf-8")
        (home / "project.toml").write_text(
            """schema_version = 1
project_id = "f46fc856-7f25-48eb-9e48-cf795c1c8a41"
display_name = "lease-fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = false
render = "none"
""",
            encoding="utf-8",
        )
        self._git(home, "add", ".")
        self._git(home, "commit", "-m", "initial")
        self._git(home, "push", "origin", "main")
        project = RENDER.load_project(home / "project.toml")
        folder = root / "instances" / "lease-fixture"
        no_env = root / "no-environment-records"
        no_env.mkdir()
        MATERIALIZE.materialize(project, folder, command="setup", environment_records_dir=no_env)
        return project, folder, no_env

    def test_acquire_heartbeat_release_uses_private_local_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, folder, _ = self._fixture(Path(temporary))
            record = MATERIALIZE.lease(
                project, folder, action="acquire", host="test-host", pid="123", runtime_session_id="session-a"
            )
            self.assertEqual(record["schema"], MATERIALIZE.LEASE_SCHEMA)
            self.assertEqual(record["scope"], "local-only")
            path = folder / MATERIALIZE.LEASE_NAME
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(MATERIALIZE.lease(project, folder, action="status"), record)
            heartbeat = MATERIALIZE.lease(
                project, folder, action="heartbeat", host="test-host", pid="123", runtime_session_id="session-a"
            )
            self.assertEqual(heartbeat["acquired_at"], record["acquired_at"])
            self.assertIn("heartbeat_at", heartbeat)
            self.assertIsNone(MATERIALIZE.lease(
                project, folder, action="release", host="test-host", pid="123", runtime_session_id="session-a"
            ))
            self.assertIsNone(MATERIALIZE.lease(project, folder, action="status"))

    def test_lease_never_steals_and_requires_exact_holder_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, folder, _ = self._fixture(Path(temporary))
            MATERIALIZE.lease(project, folder, action="acquire", host="test-host", pid="123", runtime_session_id="one")
            with self.assertRaisesRegex(MATERIALIZE.ProjectFolderError, "already has a local lease"):
                MATERIALIZE.lease(project, folder, action="acquire", host="other", pid="456", runtime_session_id="two")
            for action in ("heartbeat", "release"):
                with self.assertRaisesRegex(MATERIALIZE.ProjectFolderError, "identity does not match"):
                    MATERIALIZE.lease(project, folder, action=action, host="test-host", pid="123", runtime_session_id="two")
            self.assertIsNotNone(MATERIALIZE.lease(project, folder, action="status"))

    def test_destroy_refuses_existing_lease_and_cli_status_is_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, folder, _ = self._fixture(Path(temporary))
            MATERIALIZE.lease(project, folder, action="acquire", host="test-host", pid="123")
            with self.assertRaisesRegex(MATERIALIZE.ProjectFolderError, "refusing to destroy leased"):
                MATERIALIZE.destroy(project, folder)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "materialize_project.py"), "lease", "status",
                 "--project", str(project.project_path), "--folder", str(folder), "--host", "unused"],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["host"], "test-host")

    def test_active_lease_blocks_context_and_git_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project, folder, no_env = self._fixture(Path(temporary))
            MATERIALIZE.lease(
                project, folder, action="acquire", host="test-host", pid="123"
            )

            # Status remains a non-mutating observation while all projection
            # and Git-moving operations require the lease to be released.
            result = MATERIALIZE.materialize(project, folder, command="status")
            self.assertFalse(result.blocked)
            for command in ("refresh-context", "sync"):
                with self.subTest(command=command):
                    with self.assertRaisesRegex(
                        MATERIALIZE.ProjectFolderError, "actively leased"
                    ):
                        MATERIALIZE.materialize(
                            project,
                            folder,
                            command=command,
                            environment_records_dir=no_env,
                        )


if __name__ == "__main__":
    unittest.main()
