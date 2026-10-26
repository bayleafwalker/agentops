from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.harness_evidence.coverage_replay import ReplayError, build_coverage_report


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "scripts" / "tests" / "fixtures" / "harness_evidence" / "ae01-coverage.json"


def _packet() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class SourceCoverageReplay(unittest.TestCase):
    def test_fixture_reports_full_denominator_and_keeps_missing_hook_unknown(self) -> None:
        report = build_coverage_report(_packet())

        self.assertEqual(report["qualification"], "synthetic-fixture-only")
        self.assertEqual(report["authority"], "non-authoritative")
        self.assertFalse(report["source_bytes_verified"])
        self.assertEqual(report["case_count"], 3)
        self.assertEqual(report["expected_slots"], 9)
        self.assertEqual(report["observed_slots"], 8)
        self.assertEqual(report["unknown_slots"], 1)
        self.assertEqual(report["coverage_status"], "incomplete")

        matrix = {
            (row["harness"], row["source_kind"]): row
            for row in report["coverage_matrix"]
        }
        self.assertEqual(len(matrix), 6)
        self.assertEqual(matrix[("claude-code", "native-stop")]["unknown"], 1)
        self.assertEqual(matrix[("claude-code", "native-stop")]["observed"], 1)
        self.assertEqual(matrix[("codex", "native-stop")]["observed"], 1)
        self.assertEqual(matrix[("claude-code", "git-commit")]["observed"], 2)
        self.assertEqual(matrix[("codex", "test-result")]["observed"], 1)

    def test_exact_redelivery_is_idempotent_and_report_is_deterministic(self) -> None:
        packet = _packet()
        first = build_coverage_report(packet)
        second = build_coverage_report(packet)

        self.assertEqual(first, second)
        self.assertEqual(first["unique_observations"], 8)
        self.assertEqual(first["duplicate_deliveries"], 1)

    def test_conflicting_replay_for_same_origin_sequence_is_refused(self) -> None:
        packet = _packet()
        duplicate = packet["cases"][0]["observations"][1]
        duplicate["source_digest"] = "sha256:" + "0" * 64

        with self.assertRaisesRegex(ReplayError, "conflicting event"):
            build_coverage_report(packet)

    def test_unknown_source_fields_and_host_paths_are_rejected(self) -> None:
        packet = _packet()
        packet["cases"][0]["observations"][0]["prompt"] = "sensitive marker"
        with self.assertRaises(ReplayError) as caught:
            build_coverage_report(packet)
        self.assertNotIn("sensitive marker", str(caught.exception))

        packet = _packet()
        packet["cases"][0]["observations"][0]["source_ref"] = "fixture:/home/user/transcript.jsonl"
        with self.assertRaisesRegex(ReplayError, "non-path reference"):
            build_coverage_report(packet)

    def test_every_case_must_declare_native_git_and_test_slots(self) -> None:
        packet = _packet()
        packet["cases"][0]["expected_sources"].remove("test-result")

        with self.assertRaisesRegex(ReplayError, "full source denominator"):
            build_coverage_report(packet)

    def test_cli_prints_count_only_report_without_exporting(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.harness_evidence",
                "--coverage-replay",
                str(FIXTURE),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["unknown_slots"], 1)
        self.assertEqual(report["duplicate_deliveries"], 1)
        self.assertNotIn("fixture-claude", result.stdout)
        self.assertNotIn("source_ref", result.stdout)


if __name__ == "__main__":
    unittest.main()
