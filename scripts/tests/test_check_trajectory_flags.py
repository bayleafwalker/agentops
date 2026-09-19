"""Advisory trajectory signals read by the maintenance-lane review step.

Nothing at verify read the gate log or the branch diff for test/gate-file
weakening or rework churn (agentops#2440). This is a local instrument, not a
gate: it always exits 0 and only ever buys one extra Sonnet review-synthesis
pass (docs/runbooks/maintenance-lane.md, "The loop" step 3).
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).parent / "fixtures" / "trajectory_flags"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load("check_trajectory_flags_subject", SCRIPTS / "check_trajectory_flags.py")


class WeakeningDiffTests(unittest.TestCase):
    """(a) a diff under a watched path that removes/loosens an assertion."""

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

    def _write(self, rel: str, content: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _commit(self, message: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-qm", message)
        return self._git("rev-parse", "HEAD").strip()

    def _run(self, base: str, head: str) -> dict:
        import os
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            argv = ["--base", base, "--head", head,
                    "--gate-file", str(FIXTURES / "does-not-exist.jsonl")]
            stdout_path = self.repo / "_stdout.json"
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = checker.main(argv)
            return code, json.loads(buf.getvalue())
        finally:
            os.chdir(cwd)

    def test_weakened_assertion_is_flagged(self):
        self._write("tests/test_thing.py",
                     "def test_x():\n    assert compute() == 4\n")
        base = self._commit("base")
        self._write("tests/test_thing.py",
                     "def test_x():\n    pass\n")
        head = self._commit("weaken")

        code, result = self._run(base, head)
        self.assertEqual(code, 0)
        kinds = [f for f in result["flags"] if f["kind"] == "weakening"]
        self.assertTrue(kinds, result)
        self.assertEqual(result["review_passes"], 1)

    def test_added_test_is_not_flagged(self):
        self._write("tests/test_thing.py",
                     "def test_x():\n    assert compute() == 4\n")
        base = self._commit("base")
        self._write("tests/test_thing.py",
                     "def test_x():\n    assert compute() == 4\n\n\n"
                     "def test_y():\n    assert compute() == 5\n")
        head = self._commit("add test")

        code, result = self._run(base, head)
        self.assertEqual(code, 0)
        self.assertEqual(result["flags"], [])
        self.assertEqual(result["review_passes"], 0)

    def test_skip_marker_added_is_flagged(self):
        self._write("tests/test_thing.py",
                     "def test_x():\n    assert compute() == 4\n")
        base = self._commit("base")
        self._write("tests/test_thing.py",
                     "@pytest.mark.skip\ndef test_x():\n    assert compute() == 4\n")
        head = self._commit("skip")

        code, result = self._run(base, head)
        self.assertEqual(code, 0)
        self.assertTrue(any(f["kind"] == "weakening" for f in result["flags"]))

    def test_relaxed_threshold_is_flagged(self):
        self._write("hooks/gate-check.sh", "MIN_COVERAGE=90\n")
        base = self._commit("base")
        self._write("hooks/gate-check.sh", "MIN_COVERAGE=50\n")
        head = self._commit("relax")

        code, result = self._run(base, head)
        self.assertEqual(code, 0)
        self.assertTrue(any(f["kind"] == "weakening" for f in result["flags"]))

    def test_weakening_outside_watched_paths_is_ignored(self):
        self._write("src/thing.py", "def f():\n    assert True\n")
        base = self._commit("base")
        self._write("src/thing.py", "def f():\n    pass\n")
        head = self._commit("weaken elsewhere")

        code, result = self._run(base, head)
        self.assertEqual(code, 0)
        self.assertEqual(result["flags"], [])


class ReworkGateLogTests(unittest.TestCase):
    """(b) rework_rounds >= 3, matching hooks/log-session-cost.sh's rule."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t.invalid")
        self._git("config", "user.name", "t")
        self._write("README.md", "x\n")
        self.sha = self._commit("base")

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True,
        ).stdout

    def _write(self, rel: str, content: str) -> None:
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _commit(self, message: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-qm", message)
        return self._git("rev-parse", "HEAD").strip()

    def _run(self, gate_file: Path) -> tuple:
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = checker.main([
                "--base", self.sha, "--head", self.sha,
                "--gate-file", str(gate_file),
            ])
        return code, json.loads(buf.getvalue())

    def test_three_failed_then_retried_is_flagged(self):
        code, result = self._run(FIXTURES / "gate_log_three_failures.jsonl")
        self.assertEqual(code, 0)
        self.assertTrue(any(f["kind"] == "rework" for f in result["flags"]), result)
        self.assertEqual(result["review_passes"], 1)

    def test_two_failed_then_retried_is_not_flagged(self):
        code, result = self._run(FIXTURES / "gate_log_two_failures.jsonl")
        self.assertEqual(code, 0)
        self.assertEqual(result["flags"], [])
        self.assertEqual(result["review_passes"], 0)

    def test_decision_rows_do_not_change_the_count(self):
        code_a, result_a = self._run(FIXTURES / "gate_log_three_failures.jsonl")
        code_b, result_b = self._run(
            FIXTURES / "gate_log_three_failures_with_decisions.jsonl")
        self.assertEqual(code_a, 0)
        self.assertEqual(code_b, 0)
        rows_a = checker.load_gate_rows(str(FIXTURES / "gate_log_three_failures.jsonl"))
        rows_b = checker.load_gate_rows(
            str(FIXTURES / "gate_log_three_failures_with_decisions.jsonl"))
        rounds_a, _ = checker.rework_findings(rows_a)
        rounds_b, _ = checker.rework_findings(rows_b)
        self.assertEqual(rounds_a, rounds_b)
        self.assertTrue(any(f["kind"] == "rework" for f in result_b["flags"]))

    def test_missing_gate_file_exits_zero_with_no_flags(self):
        code, result = self._run(FIXTURES / "does-not-exist.jsonl")
        self.assertEqual(code, 0)
        self.assertEqual(result["flags"], [])
        self.assertEqual(result["review_passes"], 0)


if __name__ == "__main__":
    unittest.main()
