from __future__ import annotations

import importlib.util
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


render_mod = _load("render_disposition_fragment_subject", SCRIPTS / "render_disposition_fragment.py")


def _register(items: list[dict]) -> dict:
    return {"items": items}


class RetiringAndOpenTests(unittest.TestCase):
    def test_retiring_row_states_its_retire_step(self):
        register = _register(
            [
                {
                    "key": "actionq",
                    "role": "PostgreSQL-backed action queue.",
                    "status": "retiring",
                    "goal_state": {
                        "note": (
                            "Decided by the goal state, not by current usage. "
                            "actionq-db and actionq-db-proxy drop in S2 item 7 once the dump holds."
                        )
                    },
                }
            ]
        )
        out = render_mod.render(register)
        self.assertIn("### retiring", out)
        self.assertIn("`actionq`", out)
        self.assertIn("Retires: actionq-db and actionq-db-proxy drop in S2 item 7", out)

    def test_retiring_row_without_stage_marker_falls_back_to_first_sentence(self):
        register = _register(
            [
                {
                    "key": "vuoro-dev",
                    "role": "The development deployment.",
                    "status": "retiring",
                    "goal_state": {"note": "New row: previously unenumerated."},
                }
            ]
        )
        out = render_mod.render(register)
        self.assertIn("Retires: New row: previously unenumerated.", out)

    def test_retiring_row_without_note_omits_retires_clause(self):
        register = _register(
            [
                {
                    "key": "bare-retiring",
                    "role": "No goal_state note at all.",
                    "status": "retiring",
                    "goal_state": {},
                }
            ]
        )
        out = render_mod.render(register)
        self.assertIn("`bare-retiring`", out)
        self.assertNotIn("Retires:", out)

    def test_open_row_states_its_question(self):
        register = _register(
            [
                {
                    "key": "acceptance-lab",
                    "role": "Deterministic offline settlement evaluator.",
                    "status": "open",
                    "goal_state": {
                        "open_question": "Is a separate scenario evaluator part of the target?"
                    },
                }
            ]
        )
        out = render_mod.render(register)
        self.assertIn("### open", out)
        self.assertIn("Open question: Is a separate scenario evaluator part of the target", out)

    def test_open_row_without_question_omits_clause(self):
        register = _register(
            [
                {
                    "key": "bare-open",
                    "role": "No open_question given.",
                    "status": "open",
                    "goal_state": {},
                }
            ]
        )
        out = render_mod.render(register)
        self.assertIn("`bare-open`", out)
        self.assertNotIn("Open question:", out)

    def test_status_order_places_new_statuses_alongside_related_ones(self):
        statuses = ["retiring", "retired", "unknown", "open", "hold"]
        register = _register(
            [
                {"key": f"item-{s}", "role": f"role {s}.", "status": s, "goal_state": {}}
                for s in statuses
            ]
        )
        out = render_mod.render(register)
        order = [line[4:] for line in out.splitlines() if line.startswith("### ")]
        self.assertEqual(order, ["retired", "retiring", "hold", "open", "unknown"])

    def test_retire_step_prefers_sentence_naming_stage_and_action(self):
        item = {
            "key": "auditctl",
            "goal_state": {
                "note": (
                    "Until S4, repo shards are authoritative and append-only. "
                    "At S4 authored records import into the evidence schema, and the "
                    "central release line retires after a 90-day read-only soak."
                )
            },
        }
        step = render_mod._retire_step(item)
        self.assertTrue(step.startswith("At S4 authored records import"))


if __name__ == "__main__":
    unittest.main()
