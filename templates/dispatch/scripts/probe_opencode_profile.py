#!/usr/bin/env python3
"""Run deterministic probes for the preflight OpenCode implementation profile.

The default ``fake`` mode exercises the adapter contract without contacting a
provider.  ``contained`` is an explicit host probe: it checks the installed
1.18.4 binary as the configured worker identity and checks that identity's
write boundary outside the worker worktree.  Neither mode is model
qualification or a settlement decision.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).parents[3]
SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_PROFILE = ROOT / "templates/dispatch/harness-profiles/opencode-nixpkgs-devbox-1.18.4.json"
DEFAULT_CONFIG = ROOT / "templates/dispatch/hybrid/opencode.hybrid.json"
PROBES = (
    "json-events",
    "stable-session-identity",
    "session-continuation",
    "contained-identity",
    "no-tools-finalizer",
)
FINALIZER_AGENT = "ao-finalizer"
ERROR_TERMINAL_VALUES = frozenset({
    "error", "failed", "failure", "aborted", "cancelled", "canceled",
    "timed-out", "timed_out", "timeout", "terminated",
})
ERROR_EVENT_SUFFIXES = frozenset({
    "error", "failed", "failure", "aborted", "cancelled", "canceled",
    "timeout", "timed-out", "terminated",
})
ERROR_FIELDS = frozenset({
    "error", "errors", "failure", "failures",
})
ERROR_STATUS_FIELDS = frozenset({
    "status", "state", "outcome", "result", "phase", "type",
})
TOOL_KEYS = (
    "read", "glob", "grep", "list", "todowrite", "todoread", "edit", "write",
    "patch", "bash", "task", "external_directory", "webfetch", "websearch",
)
PINNED_EVENT_TYPES = frozenset({"step_start", "text", "step_finish"})


class ProbeError(ValueError):
    """A failed probe is a qualification failure, never an inferred pass."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProbeError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProbeError(f"{path} must contain a JSON object")
    return value


def _validate_profile(path: Path, profile: dict[str, Any]) -> None:
    validator_path = SCRIPT_PATH.parent / "validate_harness_profiles.py"
    spec = importlib.util.spec_from_file_location("agentops_profile_validator", validator_path)
    if spec is None or spec.loader is None:
        raise ProbeError(f"cannot load profile validator {validator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.validate_profile(profile, path)
    except ValueError as exc:
        raise ProbeError(str(exc)) from exc


def _profile_and_config(profile_path: Path, config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = _load_json(profile_path)
    _validate_profile(profile_path, profile)
    config = _load_json(config_path)
    finalizer_name = profile["lifecycle"]["finalizer"]["agent"]
    if finalizer_name != FINALIZER_AGENT:
        raise ProbeError(f"lifecycle finalizer must be {FINALIZER_AGENT}")
    agents = config.get("agent")
    if not isinstance(agents, dict):
        raise ProbeError("OpenCode agent map is missing")
    finalizer = agents.get(FINALIZER_AGENT)
    if not isinstance(finalizer, dict):
        raise ProbeError("ao-finalizer is missing; refusing CLI default-agent fallback")
    if finalizer.get("mode") != "primary":
        raise ProbeError("ao-finalizer must be a primary agent")
    permissions = finalizer.get("permission")
    if not isinstance(permissions, dict):
        raise ProbeError("finalizer permission map is missing")
    if permissions.get("*") != "deny" or any(value != "deny" for value in permissions.values()):
        raise ProbeError("finalizer has an allowed or unspecified tool, including MCP")
    if finalizer.get("tools") not in (None, {}):
        raise ProbeError("finalizer declares tools")
    if finalizer.get("mcp") not in (None, {}):
        raise ProbeError("finalizer declares MCP tools")
    if any(permissions.get(key) != "deny" for key in TOOL_KEYS):
        raise ProbeError("finalizer has an allowed or unspecified tool")
    return profile, config


FAKE_OPENCODE = r'''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
state_path = os.environ["FAKE_OPENCODE_STATE"]
if args and args[0] == "export":
    with open(state_path, encoding="utf-8") as stream:
        state = json.loads(stream.read())
    session = args[1]
    if session != state["sessionID"] or "--sanitize" not in args:
        raise SystemExit(6)
    messages = [
        {"info": {"role": "user", "agent": state["agent"]}, "parts": [{"type": "text"}]},
        {"info": {"role": "assistant", "agent": state["agent"],
                  "providerID": "opencode-go", "modelID": "deepseek-v4-flash",
                  "finish": "stop"},
         "parts": [{"type": "step-start"}, {"type": "text"}, {"type": "step-finish"}]},
    ]
    print(json.dumps({"info": {"id": session}, "messages": messages}, separators=(",", ":")))
    raise SystemExit(0)
if not args or args[0] != "run":
    print("fake OpenCode only supports run and export", file=sys.stderr)
    raise SystemExit(2)
if "--format" not in args or args[args.index("--format") + 1] != "json":
    print("json format is required", file=sys.stderr)
    raise SystemExit(3)

session = "ses_fake_0001"
if "--session" in args:
    session = args[args.index("--session") + 1]
if "--continue" in args and "--session" not in args:
    print("continuation requires an explicit session", file=sys.stderr)
    raise SystemExit(4)

config = json.loads(os.environ["OPENCODE_CONFIG_CONTENT"])
requested_agent = args[args.index("--agent") + 1] if "--agent" in args else ""
agent = requested_agent if requested_agent in config.get("agent", {}) else "ao-mechanical-bulk"
if agent == "ao-finalizer":
    permission = config["agent"][agent]["permission"]
    if permission.get("*") != "deny" or any(value != "deny" for value in permission.values()):
        print("finalizer received a tool", file=sys.stderr)
        raise SystemExit(5)

with open(state_path, "w", encoding="utf-8") as stream:
    stream.write(json.dumps({"sessionID": session, "agent": agent}))
for event in (
    {"type": "step_start", "sessionID": session, "timestamp": 1, "part": {"type": "step-start"}},
    {"type": "text", "sessionID": session, "timestamp": 2, "part": {"type": "text"}},
    {"type": "step_finish", "sessionID": session, "timestamp": 3, "part": {"type": "step-finish"}},
):
    print(json.dumps(event, separators=(",", ":")))
'''


def _events(stdout: str, *, label: str, session_id_field: str = "sessionID") -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    session_ids: set[str] = set()
    for line_number, line in enumerate(stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"{label}: line {line_number} is not JSON: {exc}") from exc
        if not isinstance(event, dict):
            raise ProbeError(f"{label}: line {line_number} is not an event object")
        if not isinstance(event.get("type"), str) or not event["type"]:
            raise ProbeError(f"{label}: event has no type")
        _reject_error_terminal(event, label=label)
        if "properties" in event:
            raise ProbeError(f"{label}: event uses unsupported properties envelope")
        if event["type"] not in PINNED_EVENT_TYPES:
            raise ProbeError(f"{label}: unsupported event type {event['type']!r}")
        if not isinstance(event.get("part"), dict):
            raise ProbeError(f"{label}: event has no part object")
        if not isinstance(event.get("timestamp"), (int, float)):
            raise ProbeError(f"{label}: event has no numeric timestamp")
        cursor: Any = event
        for component in session_id_field.split("."):
            if not isinstance(cursor, dict) or component not in cursor:
                raise ProbeError(f"{label}: event has no {session_id_field}")
            cursor = cursor[component]
        if not isinstance(cursor, str) or not cursor:
            raise ProbeError(f"{label}: event has no stable {session_id_field}")
        session_ids.add(cursor)
        if len(session_ids) > 1:
            raise ProbeError(f"{label}: multiple session IDs observed: {sorted(session_ids)}")
        events.append(event)
    if not events:
        raise ProbeError(f"{label}: no JSON events observed")
    return events


def _normalise_terminal_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return "-".join(value.strip().lower().replace("_", "-").split())


def _is_error_event_type(value: Any) -> bool:
    normalised = _normalise_terminal_value(value)
    if normalised is None:
        return False
    return normalised.split(".")[-1] in ERROR_EVENT_SUFFIXES


def _is_error_status(value: Any) -> bool:
    normalised = _normalise_terminal_value(value)
    return normalised in ERROR_TERMINAL_VALUES or normalised in ERROR_EVENT_SUFFIXES


def _reject_error_terminal(event: dict[str, Any], *, label: str) -> None:
    event_type = event.get("type")
    if _is_error_event_type(event_type):
        raise ProbeError(f"{label}: error event is not acceptable")

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else key
                field = key.strip().lower().replace("_", "-") if isinstance(key, str) else key
                if field in ERROR_FIELDS:
                    raise ProbeError(f"{label}: error event is not acceptable at {child_path}")
                if field in ERROR_STATUS_FIELDS and _is_error_status(child):
                    raise ProbeError(f"{label}: error terminal status is not acceptable at {child_path}")
                visit(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    visit(event, "")


def _session_ids(events: list[dict[str, Any]], session_id_field: str) -> set[str]:
    ids: set[str] = set()
    for event in events:
        cursor: Any = event
        for component in session_id_field.split("."):
            cursor = cursor[component]
        ids.add(cursor)
    return ids


def _assert_no_tool_events(events: list[dict[str, Any]], *, label: str) -> None:
    for event in events:
        part = event.get("part", {})
        event_type = _normalise_terminal_value(event.get("type"))
        part_type = _normalise_terminal_value(part.get("type")) if isinstance(part, dict) else None
        if (
            event_type == "tool"
            or (event_type and event_type.startswith("tool-"))
            or part_type == "tool"
            or (part_type and part_type.startswith("tool-"))
        ):
            raise ProbeError(f"{label}: finalizer emitted a tool event")


def _export_evidence(
    stdout: str,
    *,
    label: str,
    session_id: str,
    expected_agent: str | None,
    expected_model: str,
    require_no_tools: bool = False,
    forbidden_agent: str | None = None,
) -> dict[str, Any]:
    try:
        exported = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"{label}: sanitized export is not JSON: {exc}") from exc
    if not isinstance(exported, dict) or not isinstance(exported.get("info"), dict):
        raise ProbeError(f"{label}: sanitized export has no info object")
    if exported["info"].get("id") != session_id:
        raise ProbeError(f"{label}: sanitized export changed session identity")
    messages = exported.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ProbeError(f"{label}: sanitized export has no messages")
    assistants = [
        message for message in messages
        if isinstance(message, dict)
        and isinstance(message.get("info"), dict)
        and message["info"].get("role") == "assistant"
    ]
    if not assistants:
        raise ProbeError(f"{label}: sanitized export has no assistant message")
    latest = assistants[-1]
    info = latest["info"]
    if expected_agent is not None and info.get("agent") != expected_agent:
        raise ProbeError(
            f"{label}: effective agent {info.get('agent')!r}, expected {expected_agent!r}"
        )
    if forbidden_agent is not None and info.get("agent") == forbidden_agent:
        raise ProbeError(f"{label}: forbidden effective agent {forbidden_agent!r}")
    provider, model = expected_model.split("/", 1)
    if info.get("providerID") != provider or info.get("modelID") != model:
        raise ProbeError(f"{label}: sanitized export provider/model mismatch")
    if _is_error_status(info.get("finish")) or not isinstance(info.get("finish"), str):
        raise ProbeError(f"{label}: sanitized export has invalid finish state")
    parts = latest.get("parts")
    if not isinstance(parts, list):
        raise ProbeError(f"{label}: sanitized export has no assistant parts")
    part_types = [part.get("type") for part in parts if isinstance(part, dict)]
    if len(part_types) != len(parts) or any(not isinstance(value, str) for value in part_types):
        raise ProbeError(f"{label}: sanitized export has malformed assistant parts")
    if require_no_tools and any(
        _normalise_terminal_value(value) == "tool"
        or (_normalise_terminal_value(value) or "").startswith("tool-")
        for value in part_types
    ):
        raise ProbeError(f"{label}: finalizer emitted a tool part")
    return {
        "session_id": session_id,
        "agent": info.get("agent"),
        "provider_model": expected_model,
        "finish": info["finish"],
        "part_types": part_types,
        "assistant_message_count": len(assistants),
    }


def _finalizer_args(profile: dict[str, Any], session_id: str) -> list[str]:
    lifecycle = profile["lifecycle"]
    finalizer = lifecycle["finalizer"]["agent"]
    if finalizer != FINALIZER_AGENT:
        raise ProbeError(f"finalizer selection must be {FINALIZER_AGENT}")
    return [
        "run", "synthesize", lifecycle["continuation"]["continue_flag"],
        lifecycle["continuation"]["session_flag"], session_id,
        "--agent", finalizer, "--format", "json",
    ]


def _run_fake(
    fake_path: Path,
    args: list[str],
    config: dict[str, Any],
    state_path: Path,
) -> tuple[int, str, str]:
    env = {
        **os.environ,
        "OPENCODE_CONFIG_CONTENT": json.dumps(config),
        "FAKE_OPENCODE_STATE": str(state_path),
    }
    completed = subprocess.run(
        [sys.executable, str(fake_path), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def run_fake_probes(profile_path: Path = DEFAULT_PROFILE, config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Exercise event, identity, continuation, and finalizer contracts offline."""
    profile, config = _profile_and_config(profile_path, config_path)
    lifecycle = profile["lifecycle"]
    finalizer_name = lifecycle["finalizer"]["agent"]

    with tempfile.TemporaryDirectory(prefix="agentops-opencode-probe-") as temporary:
        fake_path = Path(temporary) / "opencode-fake.py"
        state_path = Path(temporary) / "state.json"
        fake_path.write_text(FAKE_OPENCODE, encoding="utf-8")

        def fake_export(session_id: str, expected_agent: str, label: str, *, no_tools: bool = False) -> dict[str, Any]:
            code, stdout, stderr = _run_fake(
                fake_path, ["export", session_id, "--sanitize"], config, state_path
            )
            if code != 0:
                raise ProbeError(f"{label}: sanitized export failed ({code}): {stderr.strip()}")
            return _export_evidence(
                stdout,
                label=label,
                session_id=session_id,
                expected_agent=expected_agent,
                expected_model="opencode-go/deepseek-v4-flash",
                require_no_tools=no_tools,
            )

        base_args = ["run", "probe", "--agent", "ao-mechanical-bulk", "--format", "json"]
        code, stdout, stderr = _run_fake(fake_path, base_args, config, state_path)
        if code != 0:
            raise ProbeError(f"initial fake session failed ({code}): {stderr.strip()}")
        initial = _events(stdout, label="initial session")
        session_ids = _session_ids(initial, lifecycle["session_id_field"])
        if len(session_ids) != 1:
            raise ProbeError(f"initial session changed identity: {sorted(session_ids)}")
        session_id = next(iter(session_ids))
        fake_export(session_id, "ao-mechanical-bulk", "initial session")

        continuation_args = [
            "run", "continue", "--continue", lifecycle["continuation"]["session_flag"],
            session_id, "--agent", "ao-mechanical-bulk", "--format", "json",
        ]
        code, stdout, stderr = _run_fake(fake_path, continuation_args, config, state_path)
        if code != 0:
            raise ProbeError(f"same-session continuation failed ({code}): {stderr.strip()}")
        continued = _events(stdout, label="continued session")
        if _session_ids(continued, lifecycle["session_id_field"]) != {session_id}:
            raise ProbeError("continuation created a different session identity")
        fake_export(session_id, "ao-mechanical-bulk", "continued session")

        finalizer_args = _finalizer_args(profile, session_id)
        code, stdout, stderr = _run_fake(fake_path, finalizer_args, config, state_path)
        if code != 0:
            raise ProbeError(f"no-tools finalizer failed ({code}): {stderr.strip()}")
        finalized = _events(stdout, label="finalizer")
        if _session_ids(finalized, lifecycle["session_id_field"]) != {session_id}:
            raise ProbeError("finalizer did not continue the same session")
        _assert_no_tool_events(finalized, label="finalizer")
        fake_export(session_id, finalizer_name, "finalizer", no_tools=True)

        fallback_args = [
            arg for index, arg in enumerate(finalizer_args)
            if not (arg == "--agent" or (index and finalizer_args[index - 1] == "--agent"))
        ]
        code, stdout, stderr = _run_fake(fake_path, fallback_args, config, state_path)
        if code != 0:
            raise ProbeError(f"default-agent fallback probe failed ({code}): {stderr.strip()}")
        fallback = _events(stdout, label="default-agent fallback")
        fallback_evidence = fake_export(
            session_id, "ao-mechanical-bulk", "default-agent fallback"
        )
        if fallback_evidence["agent"] == finalizer_name:
            raise ProbeError("CLI fallback/default agent was accepted as ao-finalizer")

    return {
        "mode": "fake",
        "qualification_eligible": False,
        "provider_contacted": False,
        "profile_id": profile["profile_id"],
        "probes": {name: "pass" for name in PROBES if name != "contained-identity"},
        "outstanding_evidence": ["contained-identity", "provider-qualification"],
        "note": "offline contract evidence only; contained identity and provider qualification remain outstanding",
    }


def _sudo(
    worker_user: str,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int | None = None,
    preserve_config: bool = False,
) -> subprocess.CompletedProcess[str]:
    sudo_args = ["sudo", "--non-interactive", "--user", worker_user]
    if preserve_config:
        sudo_args.append("--preserve-env=OPENCODE_CONFIG_CONTENT")
    return subprocess.run(
        [*sudo_args, *command],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def run_contained_probe(
    profile_path: Path = DEFAULT_PROFILE,
    *,
    config_path: Path = DEFAULT_CONFIG,
    worker_user: str | None = None,
    coordinator_root: Path = Path.cwd(),
    opencode_bin: str = "opencode",
) -> dict[str, Any]:
    """Exercise the real CLI and boundary using only the host's sudo allowlist."""
    profile, config = _profile_and_config(profile_path, config_path)
    expected_user = worker_user or profile["worker_identity"]
    if expected_user != profile["worker_identity"]:
        raise ProbeError(
            f"contained worker must be the profile identity {profile['worker_identity']!r}, got {expected_user!r}"
        )
    root = coordinator_root.resolve()
    if not root.is_dir():
        raise ProbeError(f"coordinator root is not a directory: {root}")

    # The devbox sudo policy authorizes only `test` and the pinned OpenCode
    # executable for agentworker. `test -w` asks the kernel under that uid and
    # is the containment proof; identity/Python probes are intentionally not
    # attempted because they are unauthorized commands.
    accessible = _sudo(expected_user, ["test", "-d", str(root)])
    if accessible.returncode != 0:
        raise ProbeError(
            f"contained worker cannot access coordinator root: "
            f"{accessible.stderr.strip() or accessible.stdout.strip() or f'test exited {accessible.returncode}'}"
        )
    boundary = _sudo(expected_user, ["test", "-w", str(root)])
    if boundary.returncode == 0:
        raise ProbeError("contained identity can write the coordinator root")
    if boundary.returncode != 1:
        raise ProbeError(
            f"contained write boundary could not be established: "
            f"{boundary.stderr.strip() or boundary.stdout.strip() or f'test exited {boundary.returncode}'}"
        )
    version = _sudo(expected_user, [opencode_bin, "--version"])
    expected_version = profile["implementation"]["cli_version"]
    if version.returncode != 0 or version.stdout.strip() != expected_version:
        raise ProbeError(
            f"OpenCode version mismatch: expected {expected_version}, got "
            f"{version.stdout.strip() or version.stderr.strip()}"
        )
    help_result = _sudo(expected_user, [opencode_bin, "run", "--help"])
    if help_result.returncode != 0:
        raise ProbeError(f"OpenCode run help failed: {help_result.stderr.strip()}")
    help_text = f"{help_result.stdout}\n{help_result.stderr}"
    for marker in ("--format", "--continue", "--session", "--agent"):
        if marker not in help_text:
            raise ProbeError(f"OpenCode run help does not advertise {marker}")

    env = {**os.environ, "OPENCODE_CONFIG_CONTENT": json.dumps(config, separators=(",", ":"))}

    def sanitized_export(
        session_id: str,
        *,
        label: str,
        expected_agent: str | None,
        expected_model: str,
        require_no_tools: bool = False,
        forbidden_agent: str | None = None,
    ) -> dict[str, Any]:
        completed = _sudo(
            expected_user,
            [opencode_bin, "export", session_id, "--sanitize"],
            cwd=root,
            env=env,
            timeout=30,
            preserve_config=True,
        )
        if completed.returncode != 0:
            raise ProbeError(
                f"{label}: sanitized export failed ({completed.returncode}): "
                f"{completed.stderr.strip()[-500:]}"
            )
        return _export_evidence(
            completed.stdout,
            label=label,
            session_id=session_id,
            expected_agent=expected_agent,
            expected_model=expected_model,
            require_no_tools=require_no_tools,
            forbidden_agent=forbidden_agent,
        )

    def real_run(args: list[str], label: str) -> list[dict[str, Any]]:
        completed = _sudo(
            expected_user,
            [opencode_bin, *args],
            cwd=root,
            env=env,
            timeout=120,
            preserve_config=True,
        )
        if completed.stdout.strip():
            try:
                events = _events(
                    completed.stdout,
                    label=label,
                    session_id_field=profile["lifecycle"]["session_id_field"],
                )
            except ProbeError as event_error:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise ProbeError(
                    f"{label} failed ({completed.returncode}): {event_error}; {detail[-1000:]}"
                ) from event_error
            if completed.returncode != 0:
                raise ProbeError(f"{label} failed ({completed.returncode}): command emitted non-terminal JSON")
            return events
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "no stdout/stderr evidence"
            raise ProbeError(f"{label} failed ({completed.returncode}): {detail[-1000:]}")
        raise ProbeError(f"{label} produced no JSON events")

    lifecycle = profile["lifecycle"]
    initial = real_run(
        ["run", "Reply with the word READY. Do not use tools.", "--agent", "ao-mechanical-bulk", "--format", "json"],
        "contained initial session",
    )
    initial_ids = _session_ids(initial, lifecycle["session_id_field"])
    if len(initial_ids) != 1:
        raise ProbeError(f"contained initial session changed identity: {sorted(initial_ids)}")
    session_id = next(iter(initial_ids))
    mechanical_model = config["agent"]["ao-mechanical-bulk"]["model"]
    initial_evidence = sanitized_export(
        session_id,
        label="contained initial session",
        expected_agent="ao-mechanical-bulk",
        expected_model=mechanical_model,
    )

    continued = real_run(
        [
            "run", "Reply with the word CONTINUED. Do not use tools.",
            lifecycle["continuation"]["continue_flag"], lifecycle["continuation"]["session_flag"],
            session_id, "--agent", "ao-mechanical-bulk", "--format", "json",
        ],
        "contained same-session continuation",
    )
    if _session_ids(continued, lifecycle["session_id_field"]) != {session_id}:
        raise ProbeError("contained continuation created a different session identity")
    continued_evidence = sanitized_export(
        session_id,
        label="contained same-session continuation",
        expected_agent="ao-mechanical-bulk",
        expected_model=mechanical_model,
    )

    fallback = real_run(
        [
            "run", "Reply with the word FALLBACK. Do not use tools.",
            lifecycle["continuation"]["continue_flag"], lifecycle["continuation"]["session_flag"],
            session_id, "--format", "json",
        ],
        "contained default-agent fallback",
    )
    if _session_ids(fallback, lifecycle["session_id_field"]) != {session_id}:
        raise ProbeError("contained default-agent fallback changed session identity")
    fallback_evidence = sanitized_export(
        session_id,
        label="contained default-agent fallback",
        expected_agent=None,
        expected_model=config["model"],
        forbidden_agent=FINALIZER_AGENT,
    )

    finalizer_args = _finalizer_args(profile, session_id)
    if finalizer_args[finalizer_args.index("--agent") + 1] != FINALIZER_AGENT:
        raise ProbeError("contained finalizer did not use the exact ao-finalizer agent")
    finalized = real_run(finalizer_args, "contained ao-finalizer")
    if _session_ids(finalized, lifecycle["session_id_field"]) != {session_id}:
        raise ProbeError("contained finalizer did not continue the same session")
    _assert_no_tool_events(finalized, label="contained ao-finalizer")
    finalizer_evidence = sanitized_export(
        session_id,
        label="contained ao-finalizer",
        expected_agent=FINALIZER_AGENT,
        expected_model=config["agent"][FINALIZER_AGENT]["model"],
        require_no_tools=True,
    )

    return {
        "mode": "contained",
        "qualification_eligible": False,
        "provider_contacted": True,
        "profile_id": profile["profile_id"],
        "worker_identity": expected_user,
        "cli_version": version.stdout.strip(),
        "probes": {
            "contained-identity": "pass",
            "cli-version": "pass",
            "run-help": "pass",
            "json-events": "pass",
            "stable-session-identity": "pass",
            "session-continuation": "pass",
            "no-tools-finalizer": "pass",
        },
        "outstanding_evidence": ["provider-qualification"],
        "lifecycle_probe_results": {
            "session_id": session_id,
            "initial": initial_evidence,
            "continuation": continued_evidence,
            "default_agent_fallback": fallback_evidence,
            "finalizer": finalizer_evidence,
            "finalizer_agent": FINALIZER_AGENT,
            "finalizer_args": finalizer_args,
        },
        "note": "real host containment and CLI lifecycle evidence only; provider qualification remains outstanding",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fake", "contained", "all"), default="fake")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--worker-user")
    parser.add_argument("--coordinator-root", type=Path, default=Path.cwd())
    parser.add_argument("--opencode-bin", default="opencode")
    args = parser.parse_args(argv)
    try:
        results = [run_fake_probes(args.profile, args.config)] if args.mode in ("fake", "all") else []
        if args.mode in ("contained", "all"):
            results.append(run_contained_probe(
                args.profile,
                config_path=args.config,
                worker_user=args.worker_user,
                coordinator_root=args.coordinator_root,
                opencode_bin=args.opencode_bin,
            ))
    except (OSError, ProbeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "failed", "qualification_eligible": False, "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "passed", "qualification_eligible": False, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
