from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .model import ContextServiceError, MutationValidation
from .policy import detect_mutation, extract_new_revision, fail_open_mutations
from .protocol import ContextServiceClient, HttpContextServiceClient


class BindingResolutionError(RuntimeError):
    pass


def _load_fallback(cwd: str) -> Mapping[str, Any] | None:
    configured = os.environ.get("VUORO_CONTEXT_BINDING_FILE")
    path = Path(configured) if configured else Path(cwd) / ".agent-context-binding.json"
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None
    expires = value.get("expires_at")
    if not isinstance(expires, str):
        return None
    try:
        expiry = datetime.fromisoformat(expires.replace("Z", "+00:00"))
    except ValueError:
        return None
    if expiry <= datetime.now(timezone.utc):
        return None
    return value


def resolve_binding(event: Mapping[str, Any]) -> tuple[str, str | None]:
    dispatch_id = os.environ.get("VUORO_DISPATCH_ID")
    repo_id = os.environ.get("VUORO_REPO_ID") or None
    if dispatch_id:
        return dispatch_id, repo_id
    fallback = _load_fallback(str(event.get("cwd", ".")))
    if fallback:
        return str(fallback["dispatch_id"]), str(fallback.get("repo_id") or "") or None
    raise BindingResolutionError("no dispatcher binding environment or valid fallback binding")


def _base_payload(
    event: Mapping[str, Any], harness: str, dispatch_id: str, repo_id: str | None
) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "harness": harness,
        "dispatch_id": dispatch_id,
        "repo_id": repo_id,
        "session_id": str(event.get("session_id", "unknown")),
        "agent_id": (
            str(event["agent_id"]) if event.get("agent_id") is not None else None
        ),
        "cwd": str(event.get("cwd", ".")),
    }


def _context_output(event_name: str, context: str | None) -> Mapping[str, Any] | None:
    if not context:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": context,
        }
    }


def _deny_output(reason: str, context: str | None) -> Mapping[str, Any]:
    output: dict[str, Any] = {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }
    if context:
        output["additionalContext"] = context
    return {"hookSpecificOutput": output}


class HookAdapter:
    def __init__(self, harness: str, client: ContextServiceClient) -> None:
        self.harness = harness
        self.client = client

    def handle(self, event: Mapping[str, Any]) -> Mapping[str, Any] | None:
        event_name = str(event.get("hook_event_name", ""))
        dispatch_id, repo_id = resolve_binding(event)
        base = _base_payload(event, self.harness, dispatch_id, repo_id)

        if event_name in {"SessionStart", "SubagentStart", "UserPromptSubmit"}:
            mode = "full" if event_name in {"SessionStart", "SubagentStart"} else "delta"
            request = {
                **base,
                "event": event_name,
                "mode": mode,
            }
            response = self.client.project(request)
            context = response.get("context")
            return _context_output(event_name, str(context) if context else None)

        if event_name == "PreToolUse":
            tool_name = str(event.get("tool_name", ""))
            tool_input = event.get("tool_input", {})
            intent = detect_mutation(tool_name, tool_input)
            if intent is None or not intent.confident:
                return None
            response = self.client.validate_mutation(
                {
                    **base,
                    "provider_id": intent.provider_id,
                    "resource_id": intent.resource_id,
                    "expected_revision": intent.expected_revision,
                    "tool_name": intent.tool_name,
                    "tool_input": intent.tool_input,
                }
            )
            validation = MutationValidation.from_mapping(response)
            if validation.allowed:
                return None
            return _deny_output(
                validation.reason or "mutation revision precondition rejected",
                validation.context,
            )

        if event_name in {"PostToolUse", "PostToolUseFailure"}:
            tool_name = str(event.get("tool_name", ""))
            tool_input = event.get("tool_input", {})
            intent = detect_mutation(tool_name, tool_input)
            if intent is None:
                return None
            tool_response = event.get("tool_response")
            response = self.client.observe_mutation(
                {
                    **base,
                    "provider_id": intent.provider_id,
                    "resource_id": intent.resource_id,
                    "new_revision": extract_new_revision(tool_response),
                    "tool_name": intent.tool_name,
                    "tool_input": intent.tool_input,
                    "tool_response": tool_response,
                }
            )
            context = response.get("context")
            return _context_output(event_name, str(context) if context else None)

        if event_name == "CwdChanged":
            self.client.invalidate(
                {
                    **base,
                    "provider_ids": ["workspace"],
                }
            )
            return None

        if event_name == "FileChanged":
            self.client.invalidate(
                {
                    **base,
                    "provider_ids": ["binding", "task", "workspace"],
                }
            )
            return None

        # PostCompact is intentionally not used for reinjection. Both harnesses
        # provide SessionStart(source=compact) for that path.
        return None


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Internal volatile-context hook adapter")
    parser.add_argument("--harness", required=True, choices=("claude-code", "codex", "reference"))
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("VUORO_CONTEXT_ENDPOINT", "http://127.0.0.1:8765"),
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"volatile-context hook: invalid event JSON: {exc}", file=sys.stderr)
        return 0
    if not isinstance(event, Mapping):
        print("volatile-context hook: event must be an object", file=sys.stderr)
        return 0

    client = HttpContextServiceClient(args.endpoint, timeout=args.timeout)
    adapter = HookAdapter(args.harness, client)
    try:
        output = adapter.handle(event)
    except BindingResolutionError as exc:
        print(f"volatile-context hook: {exc}", file=sys.stderr)
        return 0
    except ContextServiceError as exc:
        event_name = str(event.get("hook_event_name", ""))
        intent = detect_mutation(
            str(event.get("tool_name", "")), event.get("tool_input", {})
        )
        if (
            event_name == "PreToolUse"
            and intent is not None
            and intent.confident
            and not fail_open_mutations()
        ):
            output = _deny_output(
                "revision validation unavailable; recognized mutation blocked",
                None,
            )
        else:
            print(f"volatile-context hook: {exc}", file=sys.stderr)
            return 0
    except Exception as exc:  # Last-resort adapter containment.
        print(f"volatile-context hook: unexpected error: {exc}", file=sys.stderr)
        return 0

    if output is not None:
        sys.stdout.write(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
