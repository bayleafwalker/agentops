from __future__ import annotations

import os
import unittest
from typing import Any, Mapping
from unittest.mock import patch

from volatile_context.hook_adapter import HookAdapter
from volatile_context.model import ContextServiceError


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, Any]]] = []
        self.project_response: Mapping[str, Any] = {"context": "CURRENT"}
        self.validate_response: Mapping[str, Any] = {
            "allowed": True,
            "reason": None,
            "current_revision": "task:1",
            "context": None,
        }
        self.observe_response: Mapping[str, Any] = {"context": "UPDATED"}

    def project(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(("project", payload))
        return self.project_response

    def validate_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(("validate", payload))
        return self.validate_response

    def observe_mutation(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(("observe", payload))
        return self.observe_response

    def invalidate(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(("invalidate", payload))
        return {"invalidated": True}


class HookAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = FakeClient()
        self.adapter = HookAdapter("codex", self.client)
        self.env = patch.dict(
            os.environ,
            {
                "VUORO_DISPATCH_ID": "d1",
                "VUORO_REPO_ID": "r1",
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def base(self, event: str) -> dict[str, Any]:
        return {
            "session_id": "s1",
            "cwd": "/repo",
            "hook_event_name": event,
        }

    def test_session_start_injects_full_context(self) -> None:
        output = self.adapter.handle({**self.base("SessionStart"), "source": "startup"})
        self.assertEqual(
            output,
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "CURRENT",
                }
            },
        )
        self.assertEqual(self.client.calls[0][1]["mode"], "full")

    def test_unchanged_user_prompt_prints_nothing(self) -> None:
        self.client.project_response = {"context": None}
        output = self.adapter.handle(self.base("UserPromptSubmit"))
        self.assertIsNone(output)
        self.assertEqual(self.client.calls[0][1]["mode"], "delta")

    def test_stale_mutation_is_denied_with_current_context(self) -> None:
        self.client.validate_response = {
            "allowed": False,
            "reason": "expected task:1, current task:2",
            "current_revision": "task:2",
            "context": "TASK AT 2",
        }
        event = {
            **self.base("PreToolUse"),
            "tool_name": "mcp__sprintctl__append_claim",
            "tool_input": {"task_id": "T-1", "if_revision": "task:1"},
        }
        output = self.adapter.handle(event)
        assert output is not None
        hook = output["hookSpecificOutput"]
        self.assertEqual(hook["permissionDecision"], "deny")
        self.assertEqual(hook["additionalContext"], "TASK AT 2")

    def test_successful_mutation_reinjects_provider(self) -> None:
        event = {
            **self.base("PostToolUse"),
            "tool_name": "mcp__sprintctl__append_claim",
            "tool_input": {"task_id": "T-1", "if_revision": "task:1"},
            "tool_response": {"new_revision": "task:2"},
        }
        output = self.adapter.handle(event)
        self.assertEqual(
            output,
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "additionalContext": "UPDATED",
                }
            },
        )
        self.assertEqual(self.client.calls[0][1]["new_revision"], "task:2")

    def test_postcompact_does_not_attempt_injection(self) -> None:
        output = self.adapter.handle(self.base("PostCompact"))
        self.assertIsNone(output)
        self.assertEqual(self.client.calls, [])

    def test_cwd_change_invalidates_workspace(self) -> None:
        output = self.adapter.handle(
            {**self.base("CwdChanged"), "old_cwd": "/repo", "new_cwd": "/repo/sub"}
        )
        self.assertIsNone(output)
        self.assertEqual(self.client.calls[0][0], "invalidate")
        self.assertEqual(self.client.calls[0][1]["provider_ids"], ["workspace"])


if __name__ == "__main__":
    unittest.main()
