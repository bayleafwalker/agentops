from __future__ import annotations

import unittest

from volatile_context.authority import InMemoryRevisionedTaskStore, MissingPrecondition
from volatile_context.model import RevisionConflict


class AuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryRevisionedTaskStore()

    def test_missing_revision_is_rejected(self) -> None:
        with self.assertRaises(MissingPrecondition):
            self.store.mutate(
                expected_revision=None,
                patch={"state": "done"},
                actor="agent:a1",
                idempotency_key="k1",
            )

    def test_stale_revision_is_rejected_without_hooks(self) -> None:
        first = self.store.mutate(
            expected_revision="task:1",
            patch={"state": "review"},
            actor="agent:a1",
            idempotency_key="k1",
        )
        self.assertEqual(first.new_revision, "task:2")
        with self.assertRaises(RevisionConflict):
            self.store.mutate(
                expected_revision="task:1",
                patch={"state": "done"},
                actor="agent:a2",
                idempotency_key="k2",
            )
        self.assertEqual(self.store.revision(), "task:2")

    def test_idempotency_replay_does_not_advance_revision(self) -> None:
        first = self.store.mutate(
            expected_revision="task:1",
            patch={"state": "review"},
            actor="agent:a1",
            idempotency_key="k1",
        )
        replay = self.store.mutate(
            expected_revision="task:1",
            patch={"state": "different"},
            actor="agent:a1",
            idempotency_key="k1",
        )
        self.assertEqual(first.event_id, replay.event_id)
        self.assertTrue(replay.idempotent_replay)
        self.assertEqual(self.store.revision(), "task:2")


if __name__ == "__main__":
    unittest.main()
