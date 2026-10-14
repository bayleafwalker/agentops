#!/usr/bin/env python3
"""Read-only stdio MCP server for the estate status report: `agentops estate mcp`.

It exposes one tool, ``estate_status``, which returns the same ``estate-status/v1`` JSON as
`agentops estate status --json`. It calls the same ``build_report`` and ``Probe`` path, so
the read-only guarantees and the redaction are the CLI's own: kubectl ``get``/``version``
only, HTTP GET only, and output redacted before anything is returned. The server never
records fixtures and never takes ``--record``.

Transport: MCP stdio, which is newline-delimited JSON-RPC 2.0 on stdin and stdout. The
official ``mcp`` SDK is not available through any agentops tooling (agentops has no
pyproject, uv or nix Python environment, and scripts/ are stdlib plus PyYAML), so this is a
small stdlib implementation of the subset a tools-only server needs: ``initialize``,
``notifications/initialized``, ``ping``, ``tools/list`` and ``tools/call``. Diagnostics go
to stderr; stdout carries protocol messages only.

The tool is named ``estate_status`` rather than ``estate.status``: Claude's tool-name
pattern (``^[a-zA-Z0-9_-]{1,64}$``) has no dot, and Claude Code exposes MCP tools as
``mcp__<server>__<tool>``.

Registration: see docs/runbooks/estate-status.md and mcp/agentops-estate.mcp.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

_SPEC = importlib.util.spec_from_file_location(
    "estate_status", Path(__file__).resolve().parent / "estate_status.py")
assert _SPEC and _SPEC.loader
estate = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("estate_status", estate)
_SPEC.loader.exec_module(estate)

SERVER_NAME = "agentops-estate"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first
TOOL_NAME = "estate_status"

TOOL = {
    "name": TOOL_NAME,
    "title": "Estate status (read-only)",
    "description": (
        "Read-only estate status report (estate-status/v1). For each environment it reports "
        "what is desired, running, usable and held, the next blocking gate and the recovery "
        "class (cancel / image-revert / forward-fix-or-restore). Every fact has a value, "
        "source, observed_at and evidence. 'unknown' is a valid result and carries a reason. "
        "Probes run kubectl get, HTTP GET, git ls-remote/show, and sprintctl doctor; no cluster, "
        "host or service is mutated. With fetch:true it also runs `git fetch`, which updates "
        "remote-tracking refs and FETCH_HEAD in the local clones (never a working tree); that is "
        "the only local write, and why readOnlyHint is false. A full run takes about 10 seconds."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "env": {
                "description": "Environment(s) to report; omit for all.",
                "oneOf": [
                    {"type": "string", "enum": list(estate.ENVIRONMENTS)},
                    {"type": "array", "items": {"type": "string", "enum": list(estate.ENVIRONMENTS)},
                     "minItems": 1, "uniqueItems": True},
                ],
            },
            "fetch": {
                "type": "boolean", "default": False,
                "description": "Side effect when true: `git fetch` updates remote-tracking refs "
                               "and FETCH_HEAD in the local clones of the deploying repos "
                               "(no working-tree change) so desired state is current.",
            },
        },
        "additionalProperties": False,
    },
    # fetch:true writes remote-tracking refs locally, so the tool as a whole is not read-only
    # in the MCP sense; nothing it does is destructive.
    "annotations": {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True,
                    "openWorldHint": True},
}


class ToolArgumentError(ValueError):
    pass


def parse_arguments(arguments: Any) -> tuple[list[str], bool]:
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolArgumentError("arguments must be an object")
    extra = set(arguments) - {"env", "fetch"}
    if extra:
        raise ToolArgumentError(f"unknown argument(s): {', '.join(sorted(extra))}")
    env = arguments.get("env")
    if env is None:
        envs = list(estate.ENVIRONMENTS)
    elif isinstance(env, str):
        envs = [env]
    elif isinstance(env, list) and env and all(isinstance(e, str) for e in env):
        envs = list(dict.fromkeys(env))
    else:
        raise ToolArgumentError("env must be an environment name or a non-empty list of names")
    bad = [e for e in envs if e not in estate.ENVIRONMENTS]
    if bad:
        raise ToolArgumentError(f"unknown environment(s) {bad}; expected {list(estate.ENVIRONMENTS)}")
    fetch = arguments.get("fetch", False)
    if not isinstance(fetch, bool):
        raise ToolArgumentError("fetch must be a boolean")
    return envs, fetch


class Server:
    """JSON-RPC dispatcher. ``probe_factory`` builds a fresh Probe per call; it never records."""

    def __init__(self, probe_factory: Callable[[], Any] | None = None) -> None:
        self.probe_factory = probe_factory or (lambda: estate.Probe())

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
            return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
        method, msg_id = message["method"], message.get("id")
        if "id" not in message:  # notification: never answered
            return None
        if msg_id is None or isinstance(msg_id, bool) or not isinstance(msg_id, (str, int, float)):
            # JSON-RPC ids are strings or numbers; MCP additionally forbids null.
            return _error(None, -32600, "Invalid Request: id must be a string or number")
        params = message.get("params") or {}
        if method == "initialize":
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            version = requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return _result(msg_id, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Estate status. Call estate_status, optionally with env; "
                                "fetch:true also updates local remote-tracking refs.",
            })
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(msg_id, {"tools": [TOOL]})
        if method == "tools/call":
            if not isinstance(params, dict) or params.get("name") != TOOL_NAME:
                return _error(msg_id, -32602, f"unknown tool {params.get('name') if isinstance(params, dict) else None!r}")
            return _result(msg_id, self.call_tool(params.get("arguments")))
        return _error(msg_id, -32601, f"Method not found: {method}")

    def call_tool(self, arguments: Any) -> dict[str, Any]:
        try:
            envs, fetch = parse_arguments(arguments)
        except ToolArgumentError as error:
            return {"content": [{"type": "text", "text": f"invalid arguments: {error}"}], "isError": True}
        probe = self.probe_factory()
        if getattr(probe, "record", None):
            raise RuntimeError("the MCP server never records fixtures")
        try:
            report = estate.build_report(probe, envs, fetch=fetch and not probe.replay)
        except Exception as error:  # noqa: BLE001 - surface as a tool error, keep serving
            text = estate.redact(f"estate status failed: {type(error).__name__}: {error}")
            return {"content": [{"type": "text", "text": text}], "isError": True}
        report = estate.guard_report(report)  # same emit guard as the CLI
        return {"content": [{"type": "text", "text": json.dumps(report, indent=1)}],
                "structuredContent": report, "isError": False}


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def serve(server: Server, stdin: TextIO, stdout: TextIO) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response = _error(None, -32700, "Parse error")
        else:
            if isinstance(message, list):  # batches were removed from MCP; reject explicitly
                response = _error(None, -32600, "JSON-RPC batches are not supported")
            else:
                response = server.handle(message)
        if response is not None:
            stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            stdout.flush()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["mcp"]:  # `agentops estate mcp` arrives as `mcp ...`
        args = args[1:]
    parser = argparse.ArgumentParser(
        prog="agentops estate mcp",
        description="Read-only stdio MCP server exposing the estate_status tool.")
    parser.add_argument("--replay", type=Path,
                        help="(tests) answer every probe from recorded fixtures in DIR")
    ns = parser.parse_args(args)
    factory = (lambda: estate.Probe(replay=ns.replay)) if ns.replay else None
    print(f"{SERVER_NAME} {SERVER_VERSION}: stdio MCP server ready", file=sys.stderr)
    serve(Server(factory), sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
