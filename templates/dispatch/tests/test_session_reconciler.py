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

SCRIPT = Path(__file__).parents[1] / "scripts" / "session_reconciler.py"
SPEC = importlib.util.spec_from_file_location("session_reconciler", SCRIPT)
assert SPEC and SPEC.loader
RECONCILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECONCILER)

SCRIBE = RECONCILER.SCRIBE

EXAMPLES_DIR = Path(__file__).parents[1] / "session-mechanization"
BASE_CAPSULE = json.loads((EXAMPLES_DIR / "session-capsule.example.json").read_text(encoding="utf-8"))

CAPSULE_A = "0f1e2d3c-4b5a-4978-8b6c-1a2b3c4d5e6f"
CAPSULE_B = "1a2b3c4d-5e6f-4788-9a0b-1c2d3e4f5061"
CAPSULE_C = "2b3c4d5e-6f70-4819-9a0b-2c3d4e5f6071"


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


def _proposal_for(capsule_id: str, runtime_session_id: str = "sess-a", **overrides) -> dict:
    proposal = {
        "schema_version": "reconciliation-proposal/v1",
        "dedup_key": f"agentops:wi:1108:session-reconciler",
        "source_capsules": [
            {
                "runtime_session_id": runtime_session_id,
                "capsule_ref": {
                    "kind": "artifact",
                    "source": f"agentops:_artifacts/agentops/session-capsules/{capsule_id}.json",
                    "revision": "sha256:" + "0" * 64,
                },
            }
        ],
        "evidence_refs": [],
        "basis": {"observed_revision": "event:1", "current_revision": "event:1"},
        "target": {"kind": "work-item", "ref": "wi:1108"},
        "classification": "mark-item-advanced",
        "proposed_commands": [{"command_type": "work.completed", "params": {"item_id": 1108}}],
        "confidence": {"level": "medium", "rationale": "Explicit target, verification passed."},
    }
    proposal.update(overrides)
    return proposal


class ContextCommandTests(unittest.TestCase):
    def _run_context(self, root: Path, capsule_id: str) -> tuple[int, dict]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = RECONCILER.cmd_context(
                argparse.Namespace(root=root, project="agentops", capsule_id=capsule_id)
            )
        return rc, json.loads(buf.getvalue()) if buf.getvalue().strip() else {}

    def test_context_ready_includes_evidence_and_capsule_ref(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", {"rank": "explicit", "ref": "wi:1108"}))
            rc, out = self._run_context(root, CAPSULE_A)
            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "ready")
            self.assertEqual(out["target"], {"rank": "explicit", "ref": "wi:1108"})
            self.assertIn("git", out)
            self.assertIn("verification", out)
            self.assertEqual(out["capsule_ref"]["kind"], "artifact")
            self.assertTrue(out["capsule_ref"]["revision"].startswith("sha256:"))
            self.assertEqual(out["related_unconsumed_same_target"], [])
            self.assertEqual(out["existing_proposals"], [])

    def test_context_already_consumed_is_clean_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            SCRIBE.save_cursor(root, {"schema_version": "session-scribe-cursor/v1", "consumed_capsule_ids": [CAPSULE_A], "last_advanced_at": "2026-07-14T20:00:00Z"})
            rc, out = self._run_context(root, CAPSULE_A)
            self.assertEqual(rc, 0)
            self.assertEqual(out["status"], "already-consumed")

    def test_context_unknown_capsule_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rc = RECONCILER.cmd_context(
                argparse.Namespace(root=Path(tmp), project="agentops", capsule_id="does-not-exist")
            )
            self.assertEqual(rc, 1)

    def test_context_reports_unconsumed_siblings_sharing_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = {"rank": "explicit", "ref": "wi:1108"}
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", target))
            _write_capsule(root, _make_capsule(CAPSULE_B, "sess-b", "2026-07-14T19:05:00Z", target))
            _write_capsule(root, _make_capsule(CAPSULE_C, "sess-c", "2026-07-14T19:10:00Z", None))
            rc, out = self._run_context(root, CAPSULE_A)
            self.assertEqual(rc, 0)
            self.assertEqual(
                [entry["capsule_id"] for entry in out["related_unconsumed_same_target"]],
                [CAPSULE_B],
            )

    def test_context_reports_existing_proposals_referencing_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", {"rank": "explicit", "ref": "wi:1108"}))
            proposal = _proposal_for(CAPSULE_A)
            proposal["proposal_id"] = "3c4d5e6f-7081-4920-9a0b-3d4e5f607182"
            proposal["created_at"] = "2026-07-14T19:30:00Z"
            proposal["lifecycle"] = {
                "state": "rejected",
                "decided_at": "2026-07-14T19:40:00Z",
                "decided_by": "operator:reviewer",
                "rejection_reason": "not actually done",
                "superseded_by": None,
            }
            proposals_dir = root / "reconciliation-proposals"
            proposals_dir.mkdir(parents=True)
            (proposals_dir / f"{proposal['proposal_id']}.json").write_text(json.dumps(proposal), encoding="utf-8")
            rc, out = self._run_context(root, CAPSULE_A)
            self.assertEqual(rc, 0)
            self.assertEqual(len(out["existing_proposals"]), 1)
            self.assertEqual(out["existing_proposals"][0]["lifecycle_state"], "rejected")


class EmitCommandTests(unittest.TestCase):
    def test_emit_writes_single_capsule_proposal_and_advances_shared_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", {"rank": "explicit", "ref": "wi:1108"}))
            proposal_path = Path(tmp) / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal_for(CAPSULE_A)), encoding="utf-8")
            rc = RECONCILER.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, capsule_id=CAPSULE_A))
            self.assertEqual(rc, 0)
            proposals = list((root / "reconciliation-proposals").glob("*.json"))
            self.assertEqual(len(proposals), 1)
            cursor = SCRIBE.load_cursor(root)
            self.assertIn(CAPSULE_A, cursor["consumed_capsule_ids"])
            entries = SCRIBE.unconsumed(root, cursor)
            self.assertEqual(entries, [])

    def test_emit_already_consumed_is_idempotent_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            SCRIBE.save_cursor(root, {"schema_version": "session-scribe-cursor/v1", "consumed_capsule_ids": [CAPSULE_A], "last_advanced_at": "2026-07-14T20:00:00Z"})
            proposal_path = Path(tmp) / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal_for(CAPSULE_A)), encoding="utf-8")
            rc = RECONCILER.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, capsule_id=CAPSULE_A))
            self.assertEqual(rc, 0)
            self.assertFalse((root / "reconciliation-proposals").exists())

    def test_emit_rejects_multi_capsule_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            proposal = _proposal_for(CAPSULE_A)
            proposal["source_capsules"].append(
                {
                    "runtime_session_id": "sess-b",
                    "capsule_ref": {
                        "kind": "artifact",
                        "source": f"agentops:_artifacts/agentops/session-capsules/{CAPSULE_B}.json",
                        "revision": "sha256:" + "1" * 64,
                    },
                }
            )
            proposal_path = Path(tmp) / "proposal.json"
            proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
            rc = RECONCILER.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, capsule_id=CAPSULE_A))
            self.assertEqual(rc, 1)
            self.assertFalse((root / "reconciliation-proposals").exists())

    def test_emit_rejects_proposal_for_different_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            proposal_path = Path(tmp) / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal_for(CAPSULE_B)), encoding="utf-8")
            rc = RECONCILER.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, capsule_id=CAPSULE_A))
            self.assertEqual(rc, 1)

    def test_emit_unknown_capsule_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            proposal_path = Path(tmp) / "proposal.json"
            proposal_path.write_text(json.dumps(_proposal_for(CAPSULE_A)), encoding="utf-8")
            rc = RECONCILER.cmd_emit(argparse.Namespace(root=root, proposal=proposal_path, capsule_id=CAPSULE_A))
            self.assertEqual(rc, 1)


class NoChangeCommandTests(unittest.TestCase):
    def test_no_change_delegates_and_advances_shared_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            rc = RECONCILER.cmd_no_change(
                argparse.Namespace(
                    root=root,
                    project="agentops",
                    capsule_id=CAPSULE_A,
                    confidence="high",
                    rationale="Exploratory session, no code-bearing change.",
                )
            )
            self.assertEqual(rc, 0)
            proposals = list((root / "reconciliation-proposals").glob("*.json"))
            self.assertEqual(len(proposals), 1)
            written = json.loads(proposals[0].read_text(encoding="utf-8"))
            self.assertEqual(written["classification"], "incidental-no-change")
            self.assertIn(CAPSULE_A, SCRIBE.load_cursor(root)["consumed_capsule_ids"])

    def test_no_change_already_consumed_is_idempotent_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            SCRIBE.save_cursor(root, {"schema_version": "session-scribe-cursor/v1", "consumed_capsule_ids": [CAPSULE_A], "last_advanced_at": "2026-07-14T20:00:00Z"})
            rc = RECONCILER.cmd_no_change(
                argparse.Namespace(
                    root=root,
                    project="agentops",
                    capsule_id=CAPSULE_A,
                    confidence="high",
                    rationale="retry after success",
                )
            )
            self.assertEqual(rc, 0)
            self.assertFalse((root / "reconciliation-proposals").exists())


class SharedCursorCoexistenceTests(unittest.TestCase):
    def test_scribe_plan_does_not_see_reconciler_consumed_capsule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_capsule(root, _make_capsule(CAPSULE_A, "sess-a", "2026-07-14T19:00:00Z", None))
            _write_capsule(root, _make_capsule(CAPSULE_B, "sess-b", "2026-07-14T19:05:00Z", None))
            rc = RECONCILER.cmd_no_change(
                argparse.Namespace(
                    root=root,
                    project="agentops",
                    capsule_id=CAPSULE_A,
                    confidence="high",
                    rationale="reconciled immediately",
                )
            )
            self.assertEqual(rc, 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = SCRIBE.cmd_plan(argparse.Namespace(root=root))
            self.assertEqual(rc, 0)
            out = json.loads(buf.getvalue())
            self.assertEqual(out["unconsumed_count"], 1)
            remaining = [c["capsule_id"] for g in out["groups"] for c in g["capsules"]]
            self.assertEqual(remaining, [CAPSULE_B])


if __name__ == "__main__":
    unittest.main()
