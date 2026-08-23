"""Coordinator-authored oracle for spec row M-6b — the driver reads the
artifacts-root default from templates/dispatch/artifacts-root.default.

M-6a moved the bash half (hooks/log-session-cost.sh) onto that data file; this
pins the Python half onto the same file, resolved relative to the driver's own
location. Written against the M-6b spec only: the driver still carries the
literal today, so every test here fails.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding, so the
# cache is switched off before anything is imported.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
DRIVER_SRC = SCRIPTS / "dispatch_release.py"
DEFAULT_FILE = ROOT / "templates/dispatch/artifacts-root.default"

ENV_VAR = "AUDITCTL_ARTIFACTS_ROOT"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_artifacts_root_subject", DRIVER_SRC)


class FakeRunner:
    """Scripted stand-in for subprocess: records every command and its cwd."""

    def __init__(self, auditctl_bin: str):
        self.auditctl_bin = auditctl_bin
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        return subprocess.CompletedProcess(cmd, 0, "", "")


class ArtifactsRootDefaultTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        # A path that exists is all write_escalation needs to treat the sink as
        # reachable; the runner is fake, so nothing is ever executed.
        self.auditctl = self.tmp / "auditctl"
        self.auditctl.write_text("", encoding="utf-8")
        # The variable is process-global. Leaking it would let a later fixture
        # take the "already set" branch and pass for the wrong reason.
        self._saved_env = os.environ.get(ENV_VAR)
        self.addCleanup(self._restore_env)
        os.environ.pop(ENV_VAR, None)

    def tearDown(self):
        self._tmp.cleanup()

    def _restore_env(self):
        if self._saved_env is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._saved_env

    def _packet(self) -> dict:
        return {
            "task_id": "T-DRIVER",
            "repo_id": "repo-x",
            "starting_commit": "0" * 40,
            "worktree": {"root": str(self.tmp / "wt"), "branch": "hybrid/t-driver"},
        }

    def _relocated_driver(self, name: str, default_contents: str | None) -> object:
        """A copy of the driver in a temp dir, so its ``HERE`` is that dir.

        This is how a missing or unusual data file is exercised without editing
        the repository's own artifacts-root.default, and it is also what makes
        a sentinel value possible: the real file's contents cannot double as
        proof that the resolver read the file rather than a literal.
        """
        home = self.tmp / name
        (home / "scripts").mkdir(parents=True)
        shutil.copy(DRIVER_SRC, home / "scripts" / "dispatch_release.py")
        if default_contents is not None:
            (home / "artifacts-root.default").write_text(default_contents, encoding="utf-8")
        return _load_module(name, home / "scripts" / "dispatch_release.py")

    def _escalate(self, module, runner) -> dict:
        return module.write_escalation(
            self._packet(), "gate", 3, "boom", runner, str(self.auditctl),
        )

    # Fixture 1 — the resolver exists and reads the shipped data file
    def test_resolver_returns_stripped_contents_of_the_data_file(self):
        # Compared against the file, never against a hardcoded path: pinning
        # "/projects/dev" here would re-create in the oracle the very literal
        # this row removes from the driver, and the two would drift together.
        expected = DEFAULT_FILE.read_text(encoding="utf-8").strip()
        self.assertEqual(driver.default_artifacts_root(), expected)

    # Fixture 2 — resolution is relative to the driver, not to $PWD
    def test_resolver_is_relative_to_the_driver_not_the_working_directory(self):
        # Run from a temp cwd: a resolver written against a relative path or
        # Path.cwd() finds nothing there, while HERE-based resolution is
        # indifferent to where the process happens to stand.
        program = (
            "import importlib.util,sys;"
            "sys.dont_write_bytecode=True;"
            f"spec=importlib.util.spec_from_file_location('d',{str(DRIVER_SRC)!r});"
            "m=importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(m);"
            "print(m.default_artifacts_root())"
        )
        completed = subprocess.run(
            [sys.executable, "-B", "-c", program],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            completed.stdout.strip(),
            DEFAULT_FILE.read_text(encoding="utf-8").strip(),
        )

    # Fixture 3 — setdefault semantics: an inherited root still wins
    def test_write_escalation_leaves_an_already_set_root_untouched(self):
        module = self._relocated_driver("relocated_preset", "/sentinel/root\n")
        os.environ[ENV_VAR] = "/inherited/root"
        record = self._escalate(module, FakeRunner(str(self.auditctl)))
        # The sentinel makes the check discriminating: without it the assertion
        # would also hold for a driver that resolves nothing at all.
        self.assertEqual(module.default_artifacts_root(), "/sentinel/root")
        self.assertEqual(os.environ[ENV_VAR], "/inherited/root")
        self.assertEqual(record["sink"], "auditctl")

    # Fixture 4 — the resolved value is what fills an absent root
    def test_write_escalation_fills_an_absent_root_from_the_resolver(self):
        module = self._relocated_driver("relocated_absent", "/sentinel/root\n")
        self._escalate(module, FakeRunner(str(self.auditctl)))
        self.assertEqual(os.environ[ENV_VAR], "/sentinel/root")

    # Fixture 5 — one source of truth, so the literal is gone
    def test_driver_source_no_longer_carries_the_literal_root(self):
        # Reported line by line: a whole-source assertion message buries the one
        # line a reader has to change under the other 594.
        hits = [
            line.strip() for line in DRIVER_SRC.read_text(encoding="utf-8").splitlines()
            if "/projects/dev" in line
        ]
        self.assertEqual(hits, [], "dispatch_release.py still hardcodes the root")

    # Fixture 6 — a missing or empty data file must not cost an escalation
    def test_missing_or_empty_data_file_neither_raises_nor_blocks_the_record(self):
        for name, contents in (("relocated_missing", None), ("relocated_empty", "")):
            with self.subTest(data_file=name):
                os.environ.pop(ENV_VAR, None)
                module = self._relocated_driver(name, contents)
                # An escalation that cannot be recorded because a defaults file
                # went missing is worse than one recorded against a wrong root.
                self.assertIsInstance(module.default_artifacts_root(), str)
                runner = FakeRunner(str(self.auditctl))
                record = self._escalate(module, runner)
                self.assertEqual(record["sink"], "auditctl")
                self.assertEqual(json.loads(runner.calls[0][0][-1])["step"], "gate")


if __name__ == "__main__":
    unittest.main()
