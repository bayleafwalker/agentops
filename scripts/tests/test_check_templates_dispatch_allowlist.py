from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load("check_templates_dispatch_allowlist_subject", SCRIPTS / "check_templates_dispatch_allowlist.py")


class IsAllowedTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(checker.is_allowed("AGENTS.md", ["AGENTS.md"]))
        self.assertFalse(checker.is_allowed("AGENTS.md.bak", ["AGENTS.md"]))

    def test_directory_prefix(self):
        allowlist = ["docs/plans/"]
        self.assertTrue(checker.is_allowed("docs/plans/foo.md", allowlist))
        self.assertTrue(checker.is_allowed("docs/plans/", allowlist))
        self.assertFalse(checker.is_allowed("docs/plans.md", allowlist))
        self.assertFalse(checker.is_allowed("docs/other/plans/foo.md", allowlist))

    def test_glob(self):
        allowlist = ["docs/dispatch/handover-*"]
        self.assertTrue(checker.is_allowed("docs/dispatch/handover-2026-01-01.md", allowlist))
        self.assertFalse(checker.is_allowed("docs/dispatch/handoff.md", allowlist))

    def test_unmatched_path_is_not_allowed(self):
        self.assertFalse(checker.is_allowed("scripts/anything.py", ["docs/plans/"]))


class GitGrepIntegrationTests(unittest.TestCase):
    """The real fixture: an unlisted path with the string must fail the guard."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t.invalid")
        self._git("config", "user.name", "t")

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True,
        ).stdout

    def _write(self, rel: str, text: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _commit(self) -> None:
        self._git("add", "-A")
        self._git("commit", "-qm", "commit")

    def test_unlisted_reference_fails(self):
        self._write("notes.md", "see templates/dispatch/scripts/gone.py\n")
        self._write("allowlist.txt", "\n")
        self._commit()
        self.assertEqual(
            checker.main(["--root", str(self.repo), "--allowlist", str(self.repo / "allowlist.txt")]),
            1,
        )

    def test_listed_reference_passes(self):
        self._write("notes.md", "see templates/dispatch/scripts/gone.py\n")
        self._write("allowlist.txt", "notes.md\n")
        self._commit()
        self.assertEqual(
            checker.main(["--root", str(self.repo), "--allowlist", str(self.repo / "allowlist.txt")]),
            0,
        )

    def test_no_references_passes(self):
        self._write("notes.md", "nothing to see here\n")
        self._write("allowlist.txt", "\n")
        self._commit()
        self.assertEqual(
            checker.main(["--root", str(self.repo), "--allowlist", str(self.repo / "allowlist.txt")]),
            0,
        )


if __name__ == "__main__":
    unittest.main()
