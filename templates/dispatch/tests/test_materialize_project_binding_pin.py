from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import materialize_project as MATERIALIZE  # noqa: E402
import render_project as RENDER  # noqa: E402


class ProjectBindingPinTests(unittest.TestCase):
    def _git(self, repo: Path, *arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *arguments],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def test_setup_pins_home_to_selected_binding_when_origin_is_newer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            subprocess.run(
                ["git", "init", "--bare", "--initial-branch=main", str(remote)],
                check=True,
                capture_output=True,
            )
            home = root / "workspace" / "home"
            subprocess.run(
                ["git", "clone", str(remote), str(home)],
                check=True,
                capture_output=True,
            )
            self._git(home, "config", "user.email", "tests@example.invalid")
            self._git(home, "config", "user.name", "Binding Pin Tests")
            (home / "AGENTS.md").write_text("# home\n", encoding="utf-8")
            binding = home / "project.toml"
            binding.write_text(
                '''schema_version = 1
project_id = "f46fc856-7f25-48eb-9e48-cf795c1c8a41"
display_name = "binding-pin"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"
''',
                encoding="utf-8",
            )
            self._git(home, "add", ".")
            self._git(home, "commit", "-m", "selected binding")
            self._git(home, "push", "origin", "main")
            selected_commit = self._git(home, "rev-parse", "HEAD")
            project = RENDER.load_project(binding)

            publisher = root / "publisher"
            subprocess.run(
                ["git", "clone", str(remote), str(publisher)],
                check=True,
                capture_output=True,
            )
            self._git(publisher, "config", "user.email", "tests@example.invalid")
            self._git(publisher, "config", "user.name", "Binding Publisher")
            (publisher / "later.txt").write_text("later\n", encoding="utf-8")
            self._git(publisher, "add", ".")
            self._git(publisher, "commit", "-m", "newer remote")
            self._git(publisher, "push", "origin", "main")

            folder = root / "instances" / "read"
            result = MATERIALIZE.materialize(
                project,
                folder,
                command="setup",
                instance="binding-pin",
                mode="shared-read",
                environment_records_dir=root / "no-environment",
            )

            state = result.members[0]
            self.assertEqual(state.repo_id, "home")
            self.assertEqual(state.head, selected_commit)
            self.assertEqual(state.status, "behind")
            self.assertEqual(
                self._git(folder / "members" / "home", "rev-parse", "HEAD"),
                selected_commit,
            )


if __name__ == "__main__":
    unittest.main()
