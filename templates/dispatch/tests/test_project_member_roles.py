from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "templates" / "dispatch" / "scripts" / "render_project.py"
SCHEMA = ROOT / "docs" / "project" / "schemas" / "project.schema.json"
SPEC = importlib.util.spec_from_file_location("project_member_roles_render", SCRIPT)
assert SPEC and SPEC.loader
RENDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RENDER
SPEC.loader.exec_module(RENDER)


class ProjectMemberRoleTests(unittest.TestCase):
    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _project(self, root: Path, member_fields: str = "") -> Path:
        workspace = root / "workspace"
        for repo_id in ("home", "member"):
            self._write(workspace / repo_id / "AGENTS.md", f"# {repo_id}\n")
        self._write(
            workspace / "home" / "project.toml",
            f'''schema_version = 1
project_id = "31d5cdbd-063a-46ef-a27b-dfb1de9669d8"
display_name = "roles-fixture"
home_repo = "home"

[[members]]
repo_id = "home"
backlog = true
render = "none"

[[members]]
repo_id = "member"
backlog = false
render = "none"
{member_fields}''',
        )
        return workspace / "home" / "project.toml"

    def test_omitted_member_role_fields_preserve_write_implementation_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = RENDER.load_project(self._project(Path(temporary)))

            member = next(member for member in project.members if member.repo_id == "member")
            self.assertEqual(member.relationship, "implementation")
            self.assertEqual(member.access, "write")

    def test_explicit_member_role_fields_are_exposed_on_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = RENDER.load_project(
                self._project(
                    Path(temporary),
                    'relationship = "execution-authority"\naccess = "reference"\n',
                )
            )

            member = next(member for member in project.members if member.repo_id == "member")
            self.assertEqual(member.relationship, "execution-authority")
            self.assertEqual(member.access, "reference")

    def test_parser_rejects_invalid_member_role_or_access(self) -> None:
        for field, value in (("relationship", "not-a-role"), ("access", "admin")):
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as temporary:
                    project_path = self._project(
                        Path(temporary), f'{field} = "{value}"\n'
                    )
                    with self.assertRaisesRegex(RENDER.ProjectRenderError, field):
                        RENDER.load_project(project_path)

    def test_schema_declares_role_and_access_enums_with_compatible_defaults(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        member = schema["properties"]["members"]["items"]
        relationship = member["properties"]["relationship"]
        access = member["properties"]["access"]

        self.assertEqual(relationship["default"], "implementation")
        self.assertEqual(access["default"], "write")
        self.assertEqual(
            relationship["enum"],
            [
                "implementation",
                "planning-authority",
                "execution-authority",
                "deployment-owner",
                "governance",
                "tooling",
                "reference",
            ],
        )
        self.assertEqual(access["enum"], ["write", "reference"])


if __name__ == "__main__":
    unittest.main()
