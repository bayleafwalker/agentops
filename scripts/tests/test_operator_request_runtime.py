"""The normal frontend must isolate its transport dependency before owner I/O."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]


class OperatorRequestRuntimeTests(unittest.TestCase):
    def call(self, arguments, *, uv=True, uv_exit=0):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "bin"
            tools.mkdir()
            for executable in ("bash", "dirname"):
                (tools / executable).symlink_to(shutil.which(executable))
            capture = root / "capture"
            for executable, code in (("python3", 0), *(([("uv", uv_exit)]) if uv else [])):
                path = tools / executable
                path.write_text("#!/usr/bin/env bash\nprintf '%s\\0' " + executable + ' "$@" > "$CAPTURE_PATH"\nexit ' + str(code) + "\n")
                path.chmod(0o700)
            # A caller project must not select or override the dependency graph.
            (root / "pyproject.toml").write_text('[tool.uv]\noverride-dependencies=["vuoro-client==0.0.0"]\n')
            result = subprocess.run(
                [str(ROOT / "bin/agentops"), *arguments], cwd=root,
                env=os.environ | {"PATH": str(tools), "CAPTURE_PATH": str(capture)},
                text=True, capture_output=True,
            )
            values = capture.read_bytes().decode().split("\0")[:-1] if capture.exists() else []
            return result, values

    def test_transport_uses_lock_and_preserves_stdio_arguments_for_both_spellings(self):
        for topic in ("operator-requests", "operator_requests"):
            with self.subTest(topic=topic):
                result, values = self.call([topic, "mcp", "--profile", "/fixture/path with spaces.json"])
                self.assertEqual(result.returncode, 0)
                self.assertEqual(values, ["uv", "run", "--no-config", "--no-project", "--locked", "--script", str(ROOT / "scripts/operator_requests.py"), "mcp", "--profile", "/fixture/path with spaces.json"])

    def test_missing_uv_does_not_fall_back_to_an_unqualified_python(self):
        result, values = self.call(["operator-requests", "mcp"], uv=False)
        self.assertEqual(result.returncode, 127)
        self.assertEqual(values, [])
        self.assertIn("uv is required", result.stderr)

    def test_runtime_failure_is_returned_without_retrying_the_owner(self):
        result, values = self.call(["operator-requests", "invoke", "publish"], uv_exit=37)
        self.assertEqual(result.returncode, 37)
        self.assertEqual(values[0], "uv")

    def test_other_frontend_commands_keep_their_standard_python(self):
        result, values = self.call(["estate", "status", "--replay", "/fixture"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(values[0], "python3")
        self.assertIn(str(ROOT / "scripts/estate_status.py"), values)

    def test_lock_contains_only_the_published_transport_closure(self):
        value = tomllib.loads((ROOT / "scripts/operator_requests.py.lock").read_text())
        packages = {item["name"]: item for item in value["package"]}
        self.assertFalse(set(packages) & {"sprintctl", "psycopg", "sqlalchemy", "asyncpg", "vuoro-service"})
        client = packages["vuoro-client"]
        self.assertEqual(client["version"], "0.1.6")
        self.assertIn("vuoro-client-v0.1.6", str(client["source"]))
        self.assertIn("b2267290ed28e89e522c94616e46e1167d155334888cbe6bc0bc287b14fcb59d", str(client))


if __name__ == "__main__":
    unittest.main()
