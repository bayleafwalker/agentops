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
if not args or args[0] != "run":
    print("fake OpenCode only supports run", file=sys.stderr)
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

for event in (
    {"type": "message.updated", "properties": {"sessionID": session, "info": {"role": "assistant", "agent": agent}}},
    {"type": "session.status", "properties": {"sessionID": session, "status": {"type": "idle"}}},
):
    print(json.dumps(event, separators=(",", ":")))
'''


def _events(stdout: str, *, label: str, session_id_field: str = "properties.sessionID") -> list[dict[str, Any]]:
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
        properties = event.get("properties")
        if not isinstance(properties, dict):
            raise ProbeError(f"{label}: event has no properties envelope")
        if "sessionID" in event:
            raise ProbeError(f"{label}: multiple session IDs in event envelope")
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


def _effective_agent(events: list[dict[str, Any]], expected: str, *, label: str) -> None:
    agents = {
        event["properties"]["info"].get("agent")
        for event in events
        if event["type"] == "message.updated"
        and isinstance(event["properties"].get("info"), dict)
        and event["properties"]["info"].get("role") == "assistant"
    }
    if agents != {expected}:
        observed = sorted(str(agent) for agent in agents)
        raise ProbeError(f"{label}: effective agent {observed!r}, expected {expected!r}")


def _assert_no_tool_events(events: list[dict[str, Any]], *, label: str) -> None:
    for event in events:
        properties = event.get("properties", {})
        part = properties.get("part", {}) if isinstance(properties, dict) else {}
        event_type = _normalise_terminal_value(event.get("type"))
        part_type = _normalise_terminal_value(part.get("type")) if isinstance(part, dict) else None
        info = properties.get("info", {}) if isinstance(properties, dict) else {}
        roles = {
            properties.get("role") if isinstance(properties, dict) else None,
            info.get("role") if isinstance(info, dict) else None,
        }
        if (
            event_type == "tool"
            or (event_type and event_type.startswith("tool-"))
            or part_type == "tool"
            or (part_type and part_type.startswith("tool-"))
            or "tool" in roles
        ):
            raise ProbeError(f"{label}: finalizer emitted a tool event")


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


def _run_fake(fake_path: Path, args: list[str], config: dict[str, Any]) -> tuple[int, str, str]:
    env = {**os.environ, "OPENCODE_CONFIG_CONTENT": json.dumps(config)}
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
        fake_path.write_text(FAKE_OPENCODE, encoding="utf-8")

        base_args = ["run", "probe", "--agent", "ao-mechanical-bulk", "--format", "json"]
        code, stdout, stderr = _run_fake(fake_path, base_args, config)
        if code != 0:
            raise ProbeError(f"initial fake session failed ({code}): {stderr.strip()}")
        initial = _events(stdout, label="initial session")
        session_ids = _session_ids(initial, lifecycle["session_id_field"])
        if len(session_ids) != 1:
            raise ProbeError(f"initial session changed identity: {sorted(session_ids)}")
        session_id = next(iter(session_ids))

        continuation_args = [
            "run", "continue", "--continue", lifecycle["continuation"]["session_flag"],
            session_id, "--agent", "ao-mechanical-bulk", "--format", "json",
        ]
        code, stdout, stderr = _run_fake(fake_path, continuation_args, config)
        if code != 0:
            raise ProbeError(f"same-session continuation failed ({code}): {stderr.strip()}")
        continued = _events(stdout, label="continued session")
        if _session_ids(continued, lifecycle["session_id_field"]) != {session_id}:
            raise ProbeError("continuation created a different session identity")

        finalizer_args = _finalizer_args(profile, session_id)
        code, stdout, stderr = _run_fake(fake_path, finalizer_args, config)
        if code != 0:
            raise ProbeError(f"no-tools finalizer failed ({code}): {stderr.strip()}")
        finalized = _events(stdout, label="finalizer")
        if _session_ids(finalized, lifecycle["session_id_field"]) != {session_id}:
            raise ProbeError("finalizer did not continue the same session")
        _effective_agent(finalized, finalizer_name, label="finalizer")
        _assert_no_tool_events(finalized, label="finalizer")

        fallback_args = [
            arg for index, arg in enumerate(finalizer_args)
            if not (arg == "--agent" or (index and finalizer_args[index - 1] == "--agent"))
        ]
        code, stdout, stderr = _run_fake(fake_path, fallback_args, config)
        if code != 0:
            raise ProbeError(f"default-agent fallback probe failed ({code}): {stderr.strip()}")
        fallback = _events(stdout, label="default-agent fallback")
        try:
            _effective_agent(fallback, finalizer_name, label="default-agent fallback")
        except ProbeError:
            pass
        else:
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
    _effective_agent(initial, "ao-mechanical-bulk", label="contained initial session")
    session_id = next(iter(initial_ids))

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
    _effective_agent(continued, "ao-mechanical-bulk", label="contained same-session continuation")

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
    try:
        _effective_agent(fallback, FINALIZER_AGENT, label="contained default-agent fallback")
    except ProbeError:
        pass
    else:
        raise ProbeError("CLI default-agent fallback was accepted as ao-finalizer")

    finalizer_args = _finalizer_args(profile, session_id)
    if finalizer_args[finalizer_args.index("--agent") + 1] != FINALIZER_AGENT:
        raise ProbeError("contained finalizer did not use the exact ao-finalizer agent")
    finalized = real_run(finalizer_args, "contained ao-finalizer")
    if _session_ids(finalized, lifecycle["session_id_field"]) != {session_id}:
        raise ProbeError("contained finalizer did not continue the same session")
    _effective_agent(finalized, FINALIZER_AGENT, label="contained ao-finalizer")
    _assert_no_tool_events(finalized, label="contained ao-finalizer")

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
            "initial": initial,
            "continuation": continued,
            "default_agent_fallback": fallback,
            "finalizer": finalized,
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
