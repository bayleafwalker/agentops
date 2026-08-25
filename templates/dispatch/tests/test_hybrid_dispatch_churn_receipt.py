"""Coordinator hand-pass oracle: the run receipt carries the churn counters.

``agentops#2046`` asks receipts to "record enough ... to detect repeated reads
and long no-mutation loops". ``churn_verdict`` alone cannot: it says only
whether a worker was stopped, so a healthy run and one that stopped a single
read short of the limit leave the same trace. ``churn_metrics`` supplies the
counters; this file pins that the coordinator actually puts them on the receipt
and that the two never disagree about whether a limit was crossed.

Rule 11: this file's subject is ``hybrid_dispatch.py`` and its sibling
``churn_metrics.py``. It runs no git and no foreign subprocess.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch_churn_receipt_subject", SCRIPTS / "hybrid_dispatch.py")

#: A non-mutating tool that is not ``read``, so a step fixture is never also a
#: repeated-read fixture.
STEP_TOOL = "glob"


def _tool(tool: str, status: str = "completed", path: str | None = None) -> dict:
    state: dict = {"status": status}
    if path:
        state["input"] = {"filePath": path}
    return {"type": "tool_use", "part": {"tool": tool, "state": state}}


class WiringTests(unittest.TestCase):
    """The counters must reach the coordinator through the module it already
    loads, not through a second copy of the counting rules."""

    def test_the_coordinator_exposes_the_counters(self):
        self.assertTrue(hasattr(dispatch, "churn_metrics_for"))

    def test_every_documented_key_is_present(self):
        metrics = dispatch.churn_metrics_for([_tool("read", path="a.py")])
        self.assertEqual(
            set(metrics),
            {
                "tool_events",
                "max_steps_without_mutation",
                "max_repeated_reads",
                "most_read_path",
                "distinct_paths_read",
                "completed_mutations",
                "failed_mutation_runs",
                "incomplete_tool_events",
            },
        )

    def test_the_mutation_set_has_exactly_one_definition(self):
        # churn_metrics.py imports MUTATION_TOOLS from hybrid_dispatch rather
        # than restating it. If that ever becomes a copy, the counters and the
        # verdict can disagree about what a mutation is while both look right.
        metrics = _load_module("churn_metrics_identity", SCRIPTS / "churn_metrics.py")
        self.assertEqual(metrics.MUTATION_TOOLS, dispatch.MUTATION_TOOLS)

    def test_the_run_stage_puts_the_counters_on_the_worker_record(self):
        # The run receipt's `worker` field is dispatch_worker's return value.
        # Pinning the key here is what makes the receipt legible to a later
        # corpus read; a metric computed and dropped is the defect this row
        # exists to close.
        source = (SCRIPTS / "hybrid_dispatch.py").read_text()
        self.assertIn('"churn_metrics": churn_metrics_for(events),', source)

    def test_the_counters_survive_a_one_shot_iterator(self):
        # dispatch_worker accumulates a list, but a caller streaming a
        # transcript must not silently get zeros.
        events = iter([_tool(STEP_TOOL), _tool("read", path="a.py")])
        self.assertEqual(dispatch.churn_metrics_for(events)["tool_events"], 2)


class AgreementTests(unittest.TestCase):
    """The verdict and the counters read the same stream. Where the verdict
    fires, the counters must already show the limit crossed -- otherwise the
    receipt would exonerate a run the coordinator stopped."""

    def _limits(self) -> dict:
        return {"max_reasoning_steps_without_mutation": 3, "max_repeated_reads_per_path": 3}

    def test_a_repeated_read_verdict_is_backed_by_the_read_counter(self):
        limits = self._limits()
        # The verdict trips on *exceeding* the limit, so four reads against a
        # limit of three is the first stream it stops.
        events = [_tool("read", path="a.py")] * 4
        self.assertIsNotNone(dispatch.churn_verdict(events, limits))
        metrics = dispatch.churn_metrics_for(events)
        self.assertGreaterEqual(metrics["max_repeated_reads"], limits["max_repeated_reads_per_path"])
        self.assertEqual(metrics["most_read_path"], "a.py")

    def test_a_step_verdict_is_backed_by_the_step_counter(self):
        limits = self._limits()
        events = [_tool(STEP_TOOL)] * 4
        self.assertIsNotNone(dispatch.churn_verdict(events, limits))
        metrics = dispatch.churn_metrics_for(events)
        self.assertGreater(
            metrics["max_steps_without_mutation"],
            limits["max_reasoning_steps_without_mutation"],
        )

    def test_no_verdict_means_no_counter_crossed_its_limit(self):
        # The other direction. A stream the coordinator let run must not be
        # reported as having exceeded anything.
        limits = self._limits()
        events = [_tool(STEP_TOOL), _tool("read", path="a.py"), _tool("write"), _tool(STEP_TOOL)]
        self.assertIsNone(dispatch.churn_verdict(events, limits))
        metrics = dispatch.churn_metrics_for(events)
        self.assertLess(metrics["max_repeated_reads"], limits["max_repeated_reads_per_path"])
        self.assertLessEqual(
            metrics["max_steps_without_mutation"],
            limits["max_reasoning_steps_without_mutation"],
        )

    def test_the_healthy_run_is_no_longer_indistinguishable_from_the_near_miss(self):
        # The whole point of the row. Both streams stop with churn_stop None;
        # only the counters tell them apart.
        limits = self._limits()
        healthy = [_tool("read", path="a.py"), _tool("write")]
        # Three reads against a limit of three: the most a worker may repeat
        # without being stopped, and previously indistinguishable from one.
        near_miss = [_tool("read", path="a.py")] * 3 + [_tool("write")]
        self.assertIsNone(dispatch.churn_verdict(healthy, limits))
        self.assertIsNone(dispatch.churn_verdict(near_miss, limits))
        self.assertNotEqual(
            dispatch.churn_metrics_for(healthy)["max_repeated_reads"],
            dispatch.churn_metrics_for(near_miss)["max_repeated_reads"],
        )


if __name__ == "__main__":
    unittest.main()
