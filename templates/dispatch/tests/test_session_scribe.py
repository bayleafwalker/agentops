from __future__ import annotations

import argparse
import copy
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / "scripts" / "session_scribe.py"
SPEC = importlib.util.spec_from_file_location("session_scribe", SCRIPT)
assert SPEC and SPEC.loader
SCRIBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIBE)

EXAMPLES_DIR = Path(__file__).parents[1] / "session-mechanization"
BASE_CAPSULE = json.loads((EXAMPLES_DIR / "session-capsule.example.json").read_text(encoding="utf-8"))


def _make_capsule(capsule_id: str, runtime_session_id: str, ended_at: str, target=None) -> dict:
    capsule = copy.deepcopy(BASE_CAPSULE)
    capsule["capsule_id"] = capsule_id
    capsule["runtime_session_id"] = runtime_session_id
    capsule["ended_at"] = ended_at
    capsule["target"] = target
    capsule["claim"] = None
    return capsule


def _write_capsule(root: Path, capsule: dict) -> Path:
    capsules_dir = root / "session-capsules"
    capsules_dir.mkdir(parents=True, exist_ok=True)
    path = capsules_dir / f"{capsule['capsule_id']}.json"
    path.write_text(json.dumps(capsule), encoding="utf-8")
    return path


CAPSULE_A = "0f1e2d3c-4b5a-4978-8b6c-1a2b3c4d5e6f"
CAPSULE_B = "1a2b3c4d-5e6f-4788-9a0b-1c2d3e4f5061"
CAPSULE_C = "2b3c4d5e-6f70-4819-9a0b-2c3d4e5f6071"


class CursorTests(unittest.TestCase):
    def test_load_cursor_defaults_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cursor = SCRIBE.load_cursor(Path(tmp))
            self.assertEqual(cursor["consumed_capsule_ids"], [])
            self.assertIsNone(cursor["last_advanced_at"])

    def test_save_and_load_cursor_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            SCRIBE.save_cursor(root, {"schema_version": "session-scribe-cursor/v1", "consumed_capsule_ids": [CAPSULE_A], "last_advanced_at": "2026-07-14T20:00:00Z"})
            cursor = SCRIBE.load_cursor(root)
            self.assertEqual(cursor["consumed_capsule_ids"], [CAPSULE_A])
            self.assertEqual(cursor["last_advanced_at"], "2026-07-14T20:00:00Z")


class DiscoveryAndGroupingTests(unittest.TestCase):
    def test_unconsumed_filters_by_cursor_and_sorts_by_ended_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_B, "sess-b", "2026-07-14T20:00:00Z"))
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z"))
            cursor = {"consumed_capsule_ids": [CAPSULE_B]}
            entries = SCRIBE.unconsumed(root, cursor)
            self.assertEqual([capsule["capsule_id"] for _, capsule in entries], [CAPSULE_A])

    def test_group_by_target_groups_explicit_refs_and_singles_out_untargeted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", {"rank": "explicit", "ref": "wi:1107"}))
            _write_capsule(root, _make_capsule(CAPSULE_B, "sess-b", "2026-07-14T19:05:00Z", {"rank": "explicit", "ref": "wi:1107"}))
            _write_capsule(root, _make_capsule(CAPSULE_C, "sess-c", "2026-07-14T19:10:00Z", None))
            entries = SCRIBE.unconsumed(root, {"consumed_capsule_ids": []})
            groups = SCRIBE.group_by_target(entries)
            self.assertEqual(sorted(groups.keys()), sorted(["wi:1107", f"capsule:{CAPSULE_C}"]))
            self.assertEqual(len(groups["wi:1107"]), 2)
            self.assertEqual(len(groups[f"capsule:{CAPSULE_C}"]), 1)


class PlanCommandTests(unittest.TestCase):
    def test_plan_reports_unconsumed_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", {"rank": "explicit", "ref": "wi:1107"}))
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = SCRIBE.cmd_plan(argparse.Namespace(root=root))
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["unconsumed_count"], 1)
            self.assertEqual(out["groups"][0]["group_key"], "wi:1107")


class NoChangeCommandTests(unittest.TestCase):
    def test_no_change_writes_valid_proposal_and_advances_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            rc = SCRIBE.cmd_no_change(
                argparse.Namespace(
                    root=root,
                    project="agentops",
                    capsule_id=CAPSULE_A,
                    confidence="high",
                    rationale="Docs-only session, nothing backlog-worthy.",
                )
            )
            self.assertEqual(rc, 0)
            proposals = list((root / "reconciliation-proposals").glob("*.json"))
            self.assertEqual(len(proposals), 1)
            proposal = json.loads(proposals[0].read_text(encoding="utf-8"))
            self.assertEqual(proposal["classification"], "incidental-no-change")
            self.assertIsNone(proposal["target"])
            self.assertEqual(proposal["proposed_commands"], [])
            self.assertEqual(proposal["dedup_key"], f"agentops:capsule:{CAPSULE_A}:no-change")
            cursor = SCRIBE.load_cursor(root)
            self.assertIn(CAPSULE_A, cursor["consumed_capsule_ids"])

    def test_no_change_unknown_capsule_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc = SCRIBE.cmd_no_change(
                argparse.Namespace(
                    root=root,
                    project="agentops",
                    capsule_id="does-not-exist",
                    confidence="low",
                    rationale="n/a",
                )
            )
            self.assertEqual(rc, 1)
            self.assertFalse((root / "reconciliation-proposals").exists())


class EmitCommandTests(unittest.TestCase):
    def _proposal_path(self, tmp: str, **overrides) -> Path:
        proposal = {
            "schema_version": "reconciliation-proposal/v1",
            "dedup_key": "agentops:wi:1107:session-scribe",
            "source_capsules": [
                {
                    "runtime_session_id": "sess-a",
                    "capsule_ref": {
                        "kind": "artifact",
                        "source": f"agentops:_artifacts/agentops/session-capsules/{CAPSULE_A}.json",
                        "revision": "sha256:" + "0" * 64,
                    },
                }
            ],
            "evidence_refs": [],
            "basis": {"observed_revision": "event:1", "current_revision": "event:1"},
            "target": {"kind": "work-item", "ref": "wi:1107"},
            "classification": "mark-item-advanced",
            "proposed_commands": [{"command_type": "work.completed", "params": {"item_id": 1107}}],
            "confidence": {"level": "medium", "rationale": "Explicit target, verification passed."},
        }
        proposal.update(overrides)
        path = Path(tmp) / "proposal.json"
        path.write_text(json.dumps(proposal), encoding="utf-8")
        return path

    def test_emit_writes_proposal_and_advances_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", {"rank": "explicit", "ref": "wi:1107"}))
            proposal_path = self._proposal_path(tmp)
            rc = SCRIBE.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, consumes=[CAPSULE_A]))
            self.assertEqual(rc, 0)
            proposals = list((root / "reconciliation-proposals").glob("*.json"))
            self.assertEqual(len(proposals), 1)
            written = json.loads(proposals[0].read_text(encoding="utf-8"))
            self.assertEqual(written["lifecycle"]["state"], "pending")
            self.assertTrue(written["proposal_id"])
            cursor = SCRIBE.load_cursor(root)
            self.assertIn(CAPSULE_A, cursor["consumed_capsule_ids"])

    def test_emit_rejects_invalid_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            proposal_path = self._proposal_path(tmp, classification="incidental-no-change")
            with self.assertRaises(ValueError):
                SCRIBE.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, consumes=[CAPSULE_A]))

    def test_emit_rejects_unknown_capsule_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            proposal_path = self._proposal_path(tmp)
            rc = SCRIBE.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, consumes=["missing-id"]))
            self.assertEqual(rc, 1)
            self.assertFalse((root / "reconciliation-proposals").exists())


class StatusCommandTests(unittest.TestCase):
    def test_status_reports_unreconciled_capsules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-01-01T00:00:00Z", None))
            _write_capsule(root, _make_capsule(CAPSULE_B, "sess-b", "2026-01-02T00:00:00Z", None))
            SCRIBE.save_cursor(root, {"consumed_capsule_ids": [CAPSULE_B], "last_advanced_at": "2026-01-02T01:00:00Z"})
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = SCRIBE.cmd_status(argparse.Namespace(root=root))
            self.assertEqual(rc, 0)
            summary = json.loads(buf.getvalue())
            self.assertEqual(summary["total_capsules"], 2)
            self.assertEqual(summary["reconciled_count"], 1)
            self.assertEqual(summary["unreconciled_count"], 1)
            self.assertEqual(summary["unreconciled"][0]["capsule_id"], CAPSULE_A)
            self.assertGreater(summary["oldest_unreconciled_age_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
