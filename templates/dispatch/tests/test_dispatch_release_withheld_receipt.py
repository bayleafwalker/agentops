"""A withheld transcript must still leave a countable receipt.

The scorecard reads receipts. When the secret scan fired, `_capture_receipt`
wrote nothing at all, so `worker_totals` could not count the run: a tract with
a withheld receipt was silently short, while every receipt it *did* find had
reported its cost -- leaving `cost_reported: true` over a corpus with a hole in
it. That is worse than a loud failure, because the number looks trustworthy.

The stub closes it. It carries numbers and stable pattern names only, never the
text the scan objected to, and it is shaped so `worker_totals` reads it exactly
as it reads a full receipt.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load("dispatch_release_withheld_subject", SCRIPTS / "dispatch_release.py")
scorecard = _load("release_scorecard_withheld_subject", SCRIPTS / "release_scorecard.py")

SECRET = "ghp_abcdefghijklmnopqrstuvwxyz"


def _payload(task_id="T-1", cost=0.25, tokens=1000):
    return {
        "schema_version": "agentops-dispatch-release/v1",
        "task_id": task_id,
        "attempt": 1,
        "starting_commit": "0" * 40,
        "disposition": "candidate",
        "driver_steps": [
            {"step": "run", "receipt": {"spend": {
                "cost_usd": cost, "tokens": tokens, "cost_reported": True}}},
            {"step": "gate", "receipt": {"evidence": {"passed": True}}},
        ],
        "gate": {"evidence": {"passed": True}},
    }


class WithheldReceiptTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.worktree = Path(self._tmp.name)

    def _capture(self, payload, transcript):
        return driver.capture_receipt(self.worktree, payload["task_id"], payload, transcript)

    def _written(self, task_id="T-1"):
        return self.worktree / driver.CAPTURE_ROOT / task_id / "receipt.json"

    def test_a_withheld_transcript_still_writes_a_receipt(self):
        result = self._capture(_payload(), f"the worker printed {SECRET} once")
        self.assertFalse(result["captured"])
        self.assertIn("github_token", result["findings"])
        self.assertTrue(self._written().is_file())

    def test_the_stub_never_contains_the_transcript(self):
        transcript = f"the worker printed {SECRET} once"
        self._capture(_payload(), transcript)
        written = self._written().read_text()
        self.assertNotIn(SECRET, written)
        self.assertNotIn("the worker printed", written)

    def test_the_stub_scans_clean(self):
        self._capture(_payload(), f"the worker printed {SECRET} once")
        self.assertEqual(driver.scan_for_secrets(self._written().read_text()), [])

    def test_the_stub_names_the_shapes_that_matched(self):
        self._capture(_payload(), f"the worker printed {SECRET} once")
        stub = json.loads(self._written().read_text())
        self.assertEqual(stub["transcript_withheld"]["captured"], False)
        self.assertIn("github_token", stub["transcript_withheld"]["findings"])

    def test_no_sidecar_is_written(self):
        self._capture(_payload(), f"the worker printed {SECRET} once")
        self.assertFalse((self._written().parent / driver.SIDECAR_NAME).exists())

    def test_the_scorecard_counts_the_withheld_run(self):
        # THE defect. Before the stub this was a corpus of zero receipts
        # reporting nothing, indistinguishable from a tract that never ran.
        self._capture(_payload(cost=0.25, tokens=1000), f"printed {SECRET}")
        stub = json.loads(self._written().read_text())
        totals = scorecard.worker_totals([stub])
        self.assertEqual(totals["attempts"], 1)
        self.assertEqual(totals["tasks"], 1)
        self.assertEqual(totals["billed_usd"], 0.25)
        self.assertEqual(totals["tokens"], 1000)

    def test_a_withheld_first_pass_is_still_a_first_pass(self):
        self._capture(_payload(), f"printed {SECRET}")
        stub = json.loads(self._written().read_text())
        self.assertEqual(scorecard.worker_totals([stub])["first_pass_tasks"], 1)

    def test_a_clean_transcript_is_captured_as_before(self):
        result = self._capture(_payload(), "nothing secret here at all")
        self.assertTrue(result["captured"])
        self.assertTrue((self._written().parent / driver.SIDECAR_NAME).is_file())
        self.assertIn("nothing secret here", self._written().parent.joinpath(
            driver.SIDECAR_NAME).read_text())

    def test_the_withheld_and_captured_paths_agree_on_where_the_receipt_lives(self):
        withheld = self._capture(_payload(task_id="A"), f"printed {SECRET}")
        captured = self._capture(_payload(task_id="B"), "clean")
        self.assertTrue(withheld["path"].endswith("A/receipt.json"))
        self.assertTrue(captured["path"].endswith("B/receipt.json"))


if __name__ == "__main__":
    unittest.main()
