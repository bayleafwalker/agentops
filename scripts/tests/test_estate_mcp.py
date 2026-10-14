"""Tests for scripts/estate_mcp.py (`agentops estate mcp`), the read-only stdio MCP server.

Probes are replayed from the estate_status fixtures; no network, cluster or host is touched.
"""

from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures/estate_status/live-2026-10-14"

SPEC = importlib.util.spec_from_file_location("estate_mcp", SCRIPTS / "estate_mcp.py")
assert SPEC and SPEC.loader
mcp = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mcp
SPEC.loader.exec_module(mcp)
estate = mcp.estate

sys.path.insert(0, str(SCRIPTS))
import schema_check  # noqa: E402

SCHEMA = json.loads((ROOT / "environment-record/estate-status-v1.schema.json").read_text())

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "0"}}}


def call(msg_id, arguments=None, name="estate_status"):
    params = {"name": name}
    if arguments is not None:
        params["arguments"] = arguments
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call", "params": params}


def replay_server():
    return mcp.Server(lambda: estate.Probe(replay=FIXTURES))


class StdioRoundTripTests(unittest.TestCase):
    """Drive the real CLI entry point over pipes, the way an MCP client does."""

    @classmethod
    def setUpClass(cls):
        messages = [
            INIT,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            call(3, {"env": "vuoro-shared"}),
            {"jsonrpc": "2.0", "id": 4, "method": "ping"},
            {"jsonrpc": "2.0", "id": 5, "method": "resources/list"},
        ]
        stdin = "\n".join(json.dumps(m) for m in messages) + "\nnot json\n"
        done = subprocess.run([str(ROOT / "bin/agentops"), "estate", "mcp", "--replay", str(FIXTURES)],
                              input=stdin, capture_output=True, text=True, timeout=120, check=True)
        cls.responses = [json.loads(line) for line in done.stdout.splitlines()]
        cls.by_id = {r.get("id"): r for r in cls.responses}

    def test_one_response_per_request_and_none_for_notifications(self):
        self.assertEqual([r.get("id") for r in self.responses], [1, 2, 3, 4, 5, None])

    def test_initialize_negotiates_tools_capability(self):
        result = self.by_id[1]["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "agentops-estate")

    def test_tools_list_advertises_read_only_estate_status(self):
        tools = self.by_id[2]["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], ["estate_status"])
        self.assertTrue(tools[0]["annotations"]["readOnlyHint"])
        self.assertFalse(tools[0]["inputSchema"]["properties"]["fetch"]["default"])

    def test_tool_call_returns_the_cli_report(self):
        result = self.by_id[3]["result"]
        self.assertFalse(result["isError"])
        report = result["structuredContent"]
        self.assertEqual(schema_check.validate(report, SCHEMA), [])
        self.assertEqual(json.loads(result["content"][0]["text"]), report)
        cli = subprocess.run([str(ROOT / "bin/agentops"), "estate", "status", "--replay", str(FIXTURES),
                              "--env", "vuoro-shared", "--json"],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(report, json.loads(cli))

    def test_ping_unknown_method_and_parse_error(self):
        self.assertEqual(self.by_id[4]["result"], {})
        self.assertEqual(self.by_id[5]["error"]["code"], -32601)
        self.assertEqual(self.by_id[None]["error"]["code"], -32700)


class ServerTests(unittest.TestCase):
    def test_unsupported_protocol_version_gets_the_newest(self):
        message = json.loads(json.dumps(INIT))
        message["params"]["protocolVersion"] = "1999-01-01"
        result = replay_server().handle(message)["result"]
        self.assertEqual(result["protocolVersion"], mcp.PROTOCOL_VERSIONS[0])

    def test_invalid_arguments_are_tool_errors(self):
        server = replay_server()
        for arguments in ({"env": "prod"}, {"env": []}, {"fetch": "yes"}, {"record": "/tmp/x"}, ["x"]):
            with self.subTest(arguments=arguments):
                result = server.handle(call(9, arguments))["result"]
                self.assertTrue(result["isError"])
                self.assertIn("invalid arguments", result["content"][0]["text"])

    def test_env_list_and_default_all(self):
        server = replay_server()
        report = server.handle(call(1, {"env": ["devbox", "workstation"]}))["result"]["structuredContent"]
        self.assertEqual([e["id"] for e in report["environments"]], ["devbox", "workstation"])
        report = server.handle(call(2))["result"]["structuredContent"]
        self.assertEqual([e["id"] for e in report["environments"]], list(estate.ENVIRONMENTS))

    def test_unknown_tool_is_invalid_params(self):
        response = replay_server().handle(call(1, {}, name="estate.mutate"))
        self.assertEqual(response["error"]["code"], -32602)

    def test_unknown_notification_is_silent(self):
        self.assertIsNone(replay_server().handle({"jsonrpc": "2.0", "method": "notifications/whatever"}))

    def test_server_refuses_a_recording_probe(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = mcp.Server(lambda: estate.Probe(record=Path(tmp)))
            with self.assertRaises(RuntimeError):
                server.call_tool({})
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_fetch_is_off_by_default(self):
        seen = {}
        original = estate.build_report

        def spy(probe, envs, *, fetch):
            seen["fetch"] = fetch
            return original(probe, envs, fetch=fetch)

        estate.build_report = spy
        try:
            replay_server().handle(call(1, {"env": "devbox"}))
        finally:
            estate.build_report = original
        self.assertIs(seen["fetch"], False)

    def test_batches_rejected(self):
        out = io.StringIO()
        mcp.serve(replay_server(), io.StringIO(json.dumps([INIT]) + "\n"), out)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], -32600)


class ProbeStdinTests(unittest.TestCase):
    def test_children_do_not_inherit_the_protocol_stdin(self):
        # `cat` would block on (or consume) an inherited stdin; with DEVNULL it ends at once.
        result = estate.Probe().run("cat", ["cat"], timeout=5)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["stdout"], "")


if __name__ == "__main__":
    unittest.main()
