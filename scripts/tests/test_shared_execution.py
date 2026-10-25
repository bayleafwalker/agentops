"""Regression tests for the portable V2.1 execution extraction."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared_execution.runtime import Store  # noqa: E402
from shared_execution.process import run_child  # noqa: E402
from shared_execution.lock import source_digest, verify_dispatch_lock  # noqa: E402
from shared_execution.protocol import AttemptEnvelope, EventEnvelope, EvidenceRef, RunEnvelope  # noqa: E402

class ProtocolTests(unittest.TestCase):
    def test_envelopes_are_versioned_and_evidence_refs_are_serializable(self):
        run = RunEnvelope("run-1", "project-1", "repo", "abc123", "adapter-1")
        attempt = AttemptEnvelope("run-1", "task-1", "attempt-1", 1, ("true",), "/tmp", 5,
                                  evidence_refs=(EvidenceRef("sha256:abc", "sha256:abc"),))
        event = EventEnvelope("run-1", "task-1", "attempt-1", 1, 1.0, "attempt.started",
                              evidence_refs=(EvidenceRef("file:attempt.json"),))
        self.assertEqual(run.to_json()["schema_version"], "agentops-execution/v1")
        self.assertEqual(attempt.to_json()["evidence_refs"][0]["uri"], "sha256:abc")
        self.assertEqual(event.to_json()["kind"], "attempt.started")

    def test_unsupported_protocol_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported schema_version"):
            RunEnvelope("run-1", "project-1", "repo", "abc123", "adapter-1", "v9")

    def test_envelope_payloads_are_snapshotted_immutably(self):
        budget = {"spend": {"max": 3}}
        run = RunEnvelope("run-1", "project-1", "repo", "abc123", "adapter-1", budget=budget)
        budget["spend"]["max"] = 99
        self.assertEqual(run.to_json()["budget"]["spend"]["max"], 3)
        with self.assertRaises(TypeError):
            run.budget["spend"]["max"] = 1


class RuntimeTests(unittest.TestCase):
    def test_v21_event_table_keeps_row_shape_and_monotonic_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Store(directory)
            journal.event("attempt.started", "task-1", run_id="run-1", attempt_id="a1")
            journal.event("attempt.finished", "task-1", run_id="run-1", attempt_id="a1")
            rows = journal.events()
            self.assertEqual((rows[0]["seq"], rows[1]["seq"]), (1, 2))
            self.assertEqual(rows[0]["kind"], "attempt.started")
            self.assertEqual(rows[0]["attempt_id"], "a1")
            journal.close()

    def test_vendored_lock_digest_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "vendor" / "shared_execution"
            package.mkdir(parents=True)
            source = package / "engine.py"
            source.write_text("ENGINE = 1\n")
            lock = root / "dispatch.lock"
            lock.write_text(json.dumps({
                "schema_version": "dispatch-lock/v1",
                "vendored_path": "vendor/shared_execution",
                "source_digest": source_digest(package),
            }))
            self.assertEqual(verify_dispatch_lock(lock)["schema_version"], "dispatch-lock/v1")
            source.write_text("ENGINE = 2\n")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_dispatch_lock(lock)


class ProcessTests(unittest.TestCase):
    def test_v21_child_supervisor_runs_command_and_records_child(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "executions"
            command = (sys.executable, "-c",
                       "from pathlib import Path; import os; p=Path(os.environ['MARKER']); "
                       "p.write_text((p.read_text() if p.exists() else '')+'x')")
            attempt = Path(directory) / "attempt"
            attempt.mkdir()
            with (attempt / "output.log").open("ab") as output:
                result = run_child(list(command), output,
                                   spec={"cwd": directory, "timeout": 3},
                                   attempt_dir=attempt,
                                   env={**os.environ, "MARKER": str(marker)},
                                   started_at=time.time())
            self.assertEqual(result, 0)
            self.assertEqual(marker.read_text(), "x")
            child = json.loads((attempt / "child.json").read_text())
            self.assertEqual(child["pgid"], child["pid"])

    def test_v21_timeout_returns_124(self):
        with tempfile.TemporaryDirectory() as directory:
            attempt = Path(directory) / "attempt"
            attempt.mkdir()
            with (attempt / "output.log").open("ab") as output:
                result = run_child([sys.executable, "-c", "import time; time.sleep(30)"], output,
                                   spec={"cwd": directory, "timeout": .1},
                                   attempt_dir=attempt, env=os.environ.copy(),
                                   started_at=time.time())
            self.assertEqual(result, 124)

if __name__ == "__main__":
    unittest.main()
