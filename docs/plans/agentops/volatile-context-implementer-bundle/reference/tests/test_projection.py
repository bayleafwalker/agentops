from __future__ import annotations

import json
import unittest

from volatile_context.cursor import InMemoryCursorStore
from volatile_context.model import Binding, ProjectionRequest, ProviderSnapshot, RevisionConflict
from volatile_context.projection import Projector


class MutableProvider:
    provider_id = "task"
    priority = 90
    budget_bytes = 1200

    def __init__(self) -> None:
        self.revision = 1
        self.render_calls = 0
        self.data = {"title": "task", "state": "ready"}

    def validate(self, binding: Binding) -> str:
        return f"task:{self.revision}"

    def render(self, binding: Binding, expected_revision: str) -> ProviderSnapshot:
        self.render_calls += 1
        current = self.validate(binding)
        if current != expected_revision:
            raise RevisionConflict("changed")
        return ProviderSnapshot(
            provider_id=self.provider_id,
            revision=current,
            source_uri="sprintctl://task/T-1",
            data=dict(self.data),
        )


class ProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = MutableProvider()
        self.cursors = InMemoryCursorStore()
        self.projector = Projector([self.provider], self.cursors, global_budget_bytes=2000)
        self.binding = Binding(dispatch_id="d1", repo_id="r1", task_id="T-1")

    @staticmethod
    def request(*, session: str = "s1", agent: str | None = None, mode: str = "delta") -> ProjectionRequest:
        return ProjectionRequest(
            harness="reference",
            event="UserPromptSubmit",
            mode=mode,
            dispatch_id="d1",
            session_id=session,
            agent_id=agent,
            cwd="/repo",
            repo_id="r1",
        )

    def test_unchanged_delta_renders_once_then_emits_nothing(self) -> None:
        first = self.projector.project(self.request(), self.binding)
        second = self.projector.project(self.request(), self.binding)
        self.assertIsNotNone(first.context)
        self.assertIsNone(second.context)
        self.assertEqual(self.provider.render_calls, 1)

    def test_changed_revision_emits_delta(self) -> None:
        self.projector.project(self.request(), self.binding)
        self.provider.revision += 1
        result = self.projector.project(self.request(), self.binding)
        self.assertIsNotNone(result.context)
        envelope = json.loads(result.context or "{}")
        self.assertEqual(envelope["providers"][0]["revision"], "task:2")

    def test_full_projection_ignores_cursor(self) -> None:
        self.projector.project(self.request(), self.binding)
        result = self.projector.project(self.request(mode="full"), self.binding)
        self.assertIsNotNone(result.context)
        self.assertEqual(self.provider.render_calls, 2)

    def test_sessions_and_subagents_are_cursor_isolated(self) -> None:
        self.projector.project(self.request(session="s1"), self.binding)
        root_second = self.projector.project(self.request(session="s1"), self.binding)
        subagent = self.projector.project(self.request(session="s1", agent="a1"), self.binding)
        other_session = self.projector.project(self.request(session="s2"), self.binding)
        self.assertIsNone(root_second.context)
        self.assertIsNotNone(subagent.context)
        self.assertIsNotNone(other_session.context)

    def test_provider_and_global_budget_are_enforced(self) -> None:
        self.provider.data = {"long": "x" * 10000, "items": list(range(1000))}
        result = self.projector.project(self.request(), self.binding)
        self.assertLessEqual(result.total_bytes, 2000)
        envelope = json.loads(result.context or "{}")
        provider = envelope["providers"][0]
        self.assertIsNotNone(provider["truncation"])
        self.assertNotIn("x" * 5000, result.context or "")


if __name__ == "__main__":
    unittest.main()
