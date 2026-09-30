"""The saved-workflow harness must fail, not skip, when node is missing (#2562, event 4049 finding 3).

test_saved_workflows.py runs the dispatch workflows in a node harness. Without node on PATH its
harness tests used to skip while pytest still reported success, so a verifier that ran the suite
outside the manifest's nix shell reported a pass over tests that never ran.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
HARNESS_TESTS = ROOT / "scripts" / "tests" / "test_saved_workflows.py"


class SavedWorkflowHarnessRequiresNodeTests(unittest.TestCase):
    def test_harness_tests_fail_without_node_on_path(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            env = {key: value for key, value in os.environ.items() if not key.startswith("PYTEST_")}
            env["PATH"] = empty
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(HARNESS_TESTS)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=600,
            )
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, f"pytest passed without node:\n{output[-2000:]}")
        summary = output.strip().splitlines()[-1] if output.strip() else ""
        self.assertIsNone(re.search(r"\bskipped\b", summary), f"harness tests were skipped, not failed: {summary}")
        self.assertRegex(summary, r"\bfailed\b|\berrors?\b")
        self.assertIn("node", output)


if __name__ == "__main__":
    unittest.main()
