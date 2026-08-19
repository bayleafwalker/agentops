from __future__ import annotations

import os
import re
import shlex
from pathlib import PurePath
from typing import Any, Mapping

from .model import MutationIntent

_MUTATION_WORDS = {
    "append",
    "assign",
    "cancel",
    "claim",
    "close",
    "complete",
    "create",
    "delete",
    "finish",
    "mutate",
    "set",
    "start",
    "transition",
    "update",
}
_REVISION_KEYS = ("if_revision", "expected_revision", "revision")
_RESOURCE_KEYS = ("task_id", "resource_id", "id")
_COMPLEX_SHELL = re.compile(r"[;&|<>`$()\n]")


def _mapping_value(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return str(value)
    return None


def _looks_like_structured_mutation(tool_name: str) -> bool:
    if not (tool_name.startswith("mcp__sprintctl__") or tool_name.startswith("mcp__vuoro__")):
        return False
    lowered = tool_name.lower()
    return any(word in lowered for word in _MUTATION_WORDS)


def _extract_cli_option(tokens: list[str], name: str) -> str | None:
    flag = f"--{name}"
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return tokens[index + 1]
        if token.startswith(flag + "="):
            return token.split("=", 1)[1]
    return None


def detect_mutation(tool_name: str, tool_input: Any) -> MutationIntent | None:
    if isinstance(tool_input, Mapping) and _looks_like_structured_mutation(tool_name):
        return MutationIntent(
            provider_id="task",
            resource_id=_mapping_value(tool_input, _RESOURCE_KEYS),
            expected_revision=_mapping_value(tool_input, _REVISION_KEYS),
            tool_name=tool_name,
            tool_input=tool_input,
            confident=True,
        )

    if tool_name != "Bash" or not isinstance(tool_input, Mapping):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str):
        return None
    if "sprintctl" not in command and "vuoro" not in command:
        return None

    confident = _COMPLEX_SHELL.search(command) is None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return MutationIntent(
            provider_id="task",
            resource_id=None,
            expected_revision=None,
            tool_name=tool_name,
            tool_input=tool_input,
            confident=False,
        )

    executable_index = None
    for index, token in enumerate(tokens):
        if PurePath(token).name in {"sprintctl", "vuoro"}:
            executable_index = index
            break
    if executable_index is None:
        return None

    tail = [token.lower() for token in tokens[executable_index + 1 :]]
    if not any(token in _MUTATION_WORDS for token in tail):
        return None

    expected = (
        _extract_cli_option(tokens, "if-revision")
        or _extract_cli_option(tokens, "expected-revision")
    )
    resource_id = (
        _extract_cli_option(tokens, "task-id")
        or _extract_cli_option(tokens, "id")
    )
    return MutationIntent(
        provider_id="task",
        resource_id=resource_id,
        expected_revision=expected,
        tool_name=tool_name,
        tool_input=tool_input,
        confident=confident,
    )


def extract_new_revision(tool_response: Any) -> str | None:
    if isinstance(tool_response, Mapping):
        for key in ("new_revision", "current_revision", "revision"):
            value = tool_response.get(key)
            if value is not None:
                return str(value)
        for value in tool_response.values():
            found = extract_new_revision(value)
            if found:
                return found
    elif isinstance(tool_response, (list, tuple)):
        for value in tool_response:
            found = extract_new_revision(value)
            if found:
                return found
    return None


def fail_open_mutations() -> bool:
    return os.environ.get("VUORO_CONTEXT_FAIL_OPEN_MUTATIONS", "0") == "1"
