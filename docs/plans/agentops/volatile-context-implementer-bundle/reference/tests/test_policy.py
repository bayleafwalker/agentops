from __future__ import annotations

import unittest

from volatile_context.policy import detect_mutation, extract_new_revision


class PolicyTests(unittest.TestCase):
    def test_structured_mcp_mutation(self) -> None:
        intent = detect_mutation(
            "mcp__sprintctl__append_claim",
            {"task_id": "T-1", "if_revision": "task:4", "claim": "done"},
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertTrue(intent.confident)
        self.assertEqual(intent.expected_revision, "task:4")
        self.assertEqual(intent.resource_id, "T-1")

    def test_simple_cli_mutation(self) -> None:
        intent = detect_mutation(
            "Bash",
            {"command": "sprintctl task update --task-id T-1 --if-revision task:4"},
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertTrue(intent.confident)
        self.assertEqual(intent.expected_revision, "task:4")

    def test_complex_shell_is_not_treated_as_confident_control(self) -> None:
        intent = detect_mutation(
            "Bash",
            {"command": "sprintctl task update --task-id T-1 | tee /tmp/result"},
        )
        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertFalse(intent.confident)

    def test_read_command_is_not_mutation(self) -> None:
        self.assertIsNone(
            detect_mutation("Bash", {"command": "sprintctl task show --id T-1"})
        )

    def test_extract_new_revision_recurses(self) -> None:
        response = {"result": {"event": {"new_revision": "task:5"}}}
        self.assertEqual(extract_new_revision(response), "task:5")


if __name__ == "__main__":
    unittest.main()
