"""Oracle for the Codex launch path (context-economy plan, phase 4).

`handoff_codex.py` is a JSON-RPC client. What can go wrong that a live run
would catch late and expensively:

1. **The wire shape.** app-server rejects a malformed request with
   `-32601`/`-32602` after a thread already exists and a turn may already have
   been billed. Every request is built by a pure function here, and the tests
   assert the exact method names and param keys the protocol schema
   (`codex app-server generate-json-schema`) declares -- so a protocol rename
   fails in CI rather than mid-handoff.
2. **The pump.** Notifications, server-initiated approval requests and the
   response to our own id all arrive interleaved on one stdout. A pump that
   mistakes a notification for a response, or that blocks on an approval
   request nobody will answer, hangs a launch.
3. **The harness stamp.** `successor.harness` must be written only onto a
   handoff that was really acked, only by the thread that acked it, and only
   if the result still validates against the schema.

The transport is mocked throughout: the point of these tests is the messages,
not codex-cli. The live behaviour is recorded in
`docs/verification/handoff-v1-successor-isolation.md`.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


codex = _load_module("handoff_codex_subject", SCRIPTS / "handoff_codex.py")
handoff = codex.handoff_mod


class FakeTransport:
    """Records what was sent; replays a scripted stream of inbound messages.

    `replies` maps a method name to a callable taking the request and
    returning the JSON-RPC response object; `pushes` maps a method name to a
    list of extra messages (notifications, server requests) emitted *before*
    that response, which is how the real server interleaves them.
    """

    def __init__(self, replies=None, pushes=None) -> None:
        self.sent: list[dict] = []
        self.replies = replies or {}
        self.pushes = pushes or {}
        self.inbox: list[dict] = []
        self.closed = False

    def send(self, message: dict) -> None:
        self.sent.append(message)
        method = message.get("method")
        if method is None or "id" not in message:
            return  # a notification from us, or our answer to a server request
        for extra in self.pushes.get(method, []):
            self.inbox.append(extra)
        reply = self.replies.get(method)
        if reply is None:
            self.inbox.append({"id": message["id"], "result": {}})
        else:
            self.inbox.append(reply(message))

    def recv(self):
        if not self.inbox:
            return None
        return self.inbox.pop(0)

    def close(self) -> None:
        self.closed = True

    def requests(self, method: str) -> list[dict]:
        return [m for m in self.sent if m.get("method") == method and "id" in m]


def _ok(result):
    return lambda msg: {"id": msg["id"], "result": result}


THREAD = {
    "thread": {
        "id": "01a09572-4671-7e52-b808-ace737659ed9",
        "sessionId": "01a09572-4671-7e52-b808-ace737659ed9",
        "model": "gpt-6-astra",
        "modelProvider": "openai",
        "cwd": "/projects/dev/outctl",
        "status": {"type": "idle"},
        "path": "/home/u/.codex/sessions/rollout-x.jsonl",
        "turns": [],
    },
    "model": "gpt-6-astra",
}


class TestRequestConstruction(unittest.TestCase):
    """The four methods the plan names, built exactly as the schema declares."""

    def test_method_names_match_the_protocol(self) -> None:
        self.assertEqual(codex.M_INITIALIZE, "initialize")
        self.assertEqual(codex.N_INITIALIZED, "initialized")
        self.assertEqual(codex.M_THREAD_START, "thread/start")
        self.assertEqual(codex.M_THREAD_RESUME, "thread/resume")
        self.assertEqual(codex.M_THREAD_READ, "thread/read")
        self.assertEqual(codex.M_TURN_START, "turn/start")

    def test_initialize_carries_clientinfo(self) -> None:
        req = codex.initialize_request(1)
        self.assertEqual(req["jsonrpc"], "2.0")
        self.assertEqual(req["method"], "initialize")
        # InitializeParams requires clientInfo{name, version}.
        self.assertEqual(set(req["params"]["clientInfo"]), {"name", "version"})

    def test_initialized_is_a_notification_with_no_id(self) -> None:
        note = codex.initialized_notification()
        self.assertNotIn("id", note)
        self.assertEqual(note["method"], "initialized")

    def test_thread_start_params(self) -> None:
        req = codex.thread_start_request(7, "/projects/dev/outctl")
        self.assertEqual(req["id"], 7)
        params = req["params"]
        self.assertEqual(params["cwd"], "/projects/dev/outctl")
        self.assertEqual(params["sandbox"], "workspace-write")
        self.assertEqual(params["approvalPolicy"], "never")
        self.assertNotIn("model", params)  # omitted, not sent as null

    def test_thread_start_model_override_is_opt_in(self) -> None:
        req = codex.thread_start_request(1, "/tmp", model="gpt-6-astra")
        self.assertEqual(req["params"]["model"], "gpt-6-astra")

    def test_turn_start_input_is_a_list_of_typed_user_input(self) -> None:
        req = codex.turn_start_request(3, "t1", "hello")
        params = req["params"]
        self.assertEqual(params["threadId"], "t1")
        # UserInput's text variant requires both keys, and `input` is a list.
        self.assertEqual(params["input"], [{"type": "text", "text": "hello"}])

    def test_turn_start_optional_overrides_are_omitted_when_unset(self) -> None:
        params = codex.turn_start_request(3, "t1", "hi")["params"]
        self.assertEqual(set(params), {"threadId", "input"})

    def test_turn_start_carries_the_sandbox_policy_verbatim(self) -> None:
        policy = codex.workspace_write_policy(["/projects/dev/outctl"])
        params = codex.turn_start_request(
            3, "t1", "hi", sandbox_policy=policy, approval_policy="never",
            cwd="/projects/dev/outctl")["params"]
        self.assertEqual(params["sandboxPolicy"]["type"], "workspaceWrite")
        self.assertEqual(params["sandboxPolicy"]["writableRoots"],
                         ["/projects/dev/outctl"])
        self.assertIs(params["sandboxPolicy"]["networkAccess"], False)
        self.assertEqual(params["approvalPolicy"], "never")

    def test_workspace_write_policy_absolutises_roots(self) -> None:
        policy = codex.workspace_write_policy(["/projects/dev/outctl/../outctl"])
        self.assertEqual(policy["writableRoots"], ["/projects/dev/outctl"])

    def test_thread_read_is_metadata_only_by_default(self) -> None:
        # includeTurns answers -32601 on codex-cli 0.153.4, so the default must
        # not send it; a regression here turns every `read` into an error.
        req = codex.thread_read_request(4, "t1")
        self.assertEqual(req["params"], {"threadId": "t1"})
        req = codex.thread_read_request(4, "t1", include_turns=True)
        self.assertIs(req["params"]["includeTurns"], True)

    def test_thread_resume_params(self) -> None:
        req = codex.thread_resume_request(5, "t1", cwd="/x")
        self.assertEqual(req["params"], {"threadId": "t1", "cwd": "/x"})
        self.assertEqual(codex.thread_resume_request(5, "t1")["params"],
                         {"threadId": "t1"})


class TestClientPump(unittest.TestCase):
    """One stdout carries responses, notifications and server requests."""

    def test_initialize_sends_the_initialized_notification_after(self) -> None:
        t = FakeTransport(replies={"initialize": _ok({"codexHome": "/h"})})
        codex.AppServerClient(t).initialize()
        self.assertEqual([m.get("method") for m in t.sent],
                         ["initialize", "initialized"])

    def test_ids_are_monotonic_and_matched(self) -> None:
        t = FakeTransport(replies={
            "initialize": _ok({}),
            "thread/start": _ok(THREAD),
            "thread/read": _ok(THREAD),
        })
        client = codex.AppServerClient(t)
        client.initialize()
        client.thread_start("/tmp")
        client.thread_read("t1")
        ids = [m["id"] for m in t.sent if "id" in m and "method" in m]
        self.assertEqual(ids, [1, 2, 3])

    def test_notifications_before_the_response_do_not_confuse_the_pump(self) -> None:
        t = FakeTransport(
            replies={"thread/start": _ok(THREAD)},
            pushes={"thread/start": [
                {"method": "remoteControl/status/changed", "params": {}},
                {"method": "thread/started", "params": {"thread": {}}},
            ]})
        seen: list[str] = []
        client = codex.AppServerClient(t, on_notification=lambda m: seen.append(m["method"]))
        result = client.thread_start("/tmp")
        self.assertEqual(codex.thread_id_of(result), THREAD["thread"]["id"])
        self.assertEqual(seen, ["remoteControl/status/changed", "thread/started"])

    def test_a_server_request_is_answered_not_awaited(self) -> None:
        # Launched with approvalPolicy=never, an approval request means nobody
        # can say yes. Answering with an error keeps the launch from hanging.
        t = FakeTransport(
            replies={"thread/start": _ok(THREAD)},
            pushes={"thread/start": [
                {"id": 99, "method": "item/commandExecution/requestApproval",
                 "params": {"command": "rm -rf /"}},
            ]})
        codex.AppServerClient(t).thread_start("/tmp")
        answers = [m for m in t.sent if m.get("id") == 99]
        self.assertEqual(len(answers), 1)
        self.assertIn("error", answers[0])
        self.assertIn("approvalPolicy=never", answers[0]["error"]["message"])

    def test_an_error_response_becomes_a_codex_error(self) -> None:
        t = FakeTransport(replies={
            "thread/read": lambda m: {"id": m["id"], "error": {
                "code": -32601, "message": "list_turns is not supported yet"}}})
        with self.assertRaises(codex.CodexError) as ctx:
            codex.AppServerClient(t).thread_read("t1", include_turns=True)
        self.assertIn("list_turns is not supported yet", str(ctx.exception))

    def test_a_closed_connection_is_reported_not_hung(self) -> None:
        t = FakeTransport()
        t.send = lambda m: t.sent.append(m)  # swallow: never reply
        with self.assertRaises(codex.CodexError) as ctx:
            codex.AppServerClient(t).thread_read("t1")
        self.assertIn("closed the connection", str(ctx.exception))

    def test_thread_id_of_rejects_a_response_without_one(self) -> None:
        with self.assertRaises(codex.CodexError):
            codex.thread_id_of({"thread": {}})


class TestTurnWatcher(unittest.TestCase):
    """Turn completion arrives as a notification, not as the turn/start result."""

    def test_turn_start_returns_before_the_turn_is_done(self) -> None:
        t = FakeTransport(replies={"turn/start": _ok(
            {"turn": {"id": "turn-1", "status": "inProgress", "items": []}})})
        result = codex.AppServerClient(t).turn_start("t1", "hi")
        self.assertEqual(result["turn"]["status"], "inProgress")

    def test_watcher_collects_messages_and_stops_on_turn_completed(self) -> None:
        watcher = codex.TurnWatcher(echo=False)
        for msg in [
            {"method": "item/completed",
             "params": {"item": {"type": "agentMessage", "text": "PROBE-OK"}}},
            {"method": "item/completed",
             "params": {"item": {"type": "commandExecution", "command": "git status"}}},
            {"method": "turn/completed", "params": {"turn": {"id": "t", "error": None}}},
        ]:
            watcher(msg)
        self.assertEqual(watcher.messages, ["PROBE-OK"])
        self.assertEqual(watcher.commands, ["git status"])
        self.assertTrue(watcher.done)
        self.assertIsNone(watcher.error)

    def test_a_failed_turn_is_recorded_not_swallowed(self) -> None:
        watcher = codex.TurnWatcher(echo=False)
        watcher({"method": "turn/completed",
                 "params": {"turn": {"error": {"message": "boom"}}}})
        self.assertTrue(watcher.done)
        self.assertIn("boom", watcher.error or "")

    def test_wait_for_turn_pumps_until_completed(self) -> None:
        t = FakeTransport()
        t.inbox = [
            {"method": "item/started", "params": {}},
            {"id": 42, "method": "item/fileChange/requestApproval", "params": {}},
            {"method": "item/completed",
             "params": {"item": {"type": "agentMessage", "text": "done"}}},
            {"method": "turn/completed", "params": {"turn": {}}},
        ]
        client = codex.AppServerClient(t)
        watcher = codex.TurnWatcher(echo=False)
        codex.wait_for_turn(client, watcher, timeout=5)
        self.assertEqual(watcher.messages, ["done"])
        self.assertTrue(any(m.get("id") == 42 for m in t.sent))

    def test_wait_for_turn_reports_a_dropped_connection(self) -> None:
        client = codex.AppServerClient(FakeTransport())
        with self.assertRaises(codex.CodexError) as ctx:
            codex.wait_for_turn(client, codex.TurnWatcher(echo=False), timeout=5)
        self.assertIn("mid-turn", str(ctx.exception))


class TestRolloutHistory(unittest.TestCase):
    """`read` must not resume; on 0.153.4 that means parsing the rollout file."""

    def test_rollout_path_comes_from_the_metadata(self) -> None:
        self.assertEqual(str(codex.rollout_path(THREAD)),
                         "/home/u/.codex/sessions/rollout-x.jsonl")
        self.assertIsNone(codex.rollout_path({"thread": {}}))

    def test_history_extracts_text_from_both_payload_shapes(self) -> None:
        path = Path(self.tmp) / "rollout.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in [
            {"payload": {"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": "the handoff"}]}},
            {"payload": {"type": "agent_message", "role": "assistant",
                         "text": "acked"}},
            {"payload": {"type": "turn_context"}},
            {"not_a_payload": True},
        ]) + "\n")
        history = codex.rollout_history(path)
        self.assertEqual([r["text"] for r in history], ["the handoff", "acked"])
        self.assertEqual([r["role"] for r in history], ["user", "assistant"])

    def test_history_tolerates_a_truncated_line(self) -> None:
        path = Path(self.tmp) / "partial.jsonl"
        path.write_text(
            json.dumps({"payload": {"role": "user", "text": "a"}}) + "\n{\"pay")
        self.assertEqual([r["text"] for r in codex.rollout_history(path)], ["a"])

    def test_history_of_a_missing_file_is_empty_not_an_error(self) -> None:
        self.assertEqual(codex.rollout_history(Path(self.tmp) / "nope.jsonl"), [])

    def test_limit_keeps_the_tail(self) -> None:
        path = Path(self.tmp) / "many.jsonl"
        path.write_text("\n".join(
            json.dumps({"payload": {"role": "assistant", "text": str(i)}})
            for i in range(5)))
        self.assertEqual([r["text"] for r in codex.rollout_history(path, limit=2)],
                         ["3", "4"])

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.addCleanup(self._tmp.cleanup)


def _handoff_fixture(**successor) -> dict:
    return {
        "schema_version": "handoff/v1",
        "handoff_id": "2026-09-12-codex.v1",
        "version": 1,
        "created_at": "2026-09-12T00:00:00Z",
        "predecessor": {"harness": "claude-code", "session_id": "s1",
                        "transcript_path": None, "model": "claude-opus-5",
                        "context_used_pct": 60.0},
        "objective": "land the codex path",
        "constraints": ["do not push"],
        "decisions": [],
        "rejected": [],
        "state": {"repos": [{"path": "/projects/dev/outctl", "head": "0" * 40,
                             "branch": "main", "dirty": True,
                             "diff_sha256": "a" * 64, "unpushed": 3}],
                  "running": []},
        "unresolved": [],
        "evidence": [],
        "sprintctl_bundle_ref": None,
        "next_action": "append the acceptance line",
        "successor": successor or {"session_id": None, "acknowledged_at": None},
    }


class TestHarnessStamp(unittest.TestCase):
    """`successor.harness` is written after the ack, or not at all."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "2026-09-12-codex.v1.json"

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2) + "\n")

    def test_the_schema_accepts_the_optional_harness_field(self) -> None:
        data = _handoff_fixture(session_id="t1", acknowledged_at="2026-09-12T00:00:01Z",
                                harness="codex")
        self.assertEqual(handoff.schema_errors(data), [])

    def test_the_schema_still_accepts_a_handoff_without_it(self) -> None:
        # Handoffs acked before phase 4 must not become invalid.
        self.assertEqual(handoff.schema_errors(_handoff_fixture()), [])

    def test_no_stamp_on_an_unacked_handoff(self) -> None:
        self._write(_handoff_fixture())
        self.assertEqual(codex.record_harness(self.path, "codex"), "")
        self.assertNotIn("harness", json.loads(self.path.read_text())["successor"])

    def test_stamp_records_the_harness_on_an_acked_handoff(self) -> None:
        self._write(_handoff_fixture(session_id="t1",
                                     acknowledged_at="2026-09-12T00:00:01Z"))
        self.assertEqual(codex.record_harness(self.path, "codex", "t1"), "t1")
        successor = json.loads(self.path.read_text())["successor"]
        self.assertEqual(successor["harness"], "codex")
        self.assertEqual(successor["session_id"], "t1")

    def test_stamp_refuses_when_another_thread_acked(self) -> None:
        # A second launcher must not relabel a handoff someone else claimed.
        self._write(_handoff_fixture(session_id="other",
                                     acknowledged_at="2026-09-12T00:00:01Z"))
        with self.assertRaises(codex.CodexError) as ctx:
            codex.record_harness(self.path, "codex", expect_session_id="t1")
        self.assertIn("other", str(ctx.exception))
        self.assertNotIn("harness", json.loads(self.path.read_text())["successor"])

    def test_stamp_is_idempotent(self) -> None:
        self._write(_handoff_fixture(session_id="t1",
                                     acknowledged_at="2026-09-12T00:00:01Z"))
        codex.record_harness(self.path, "codex", "t1")
        before = self.path.read_bytes()
        codex.record_harness(self.path, "codex", "t1")
        self.assertEqual(self.path.read_bytes(), before)


class TestCodexPrompt(unittest.TestCase):
    """The prompt is the shared rendering plus the thread id."""

    def test_prompt_is_the_shared_render_plus_the_thread_id(self) -> None:
        data = _handoff_fixture()
        path = Path("/tmp/2026-09-12-codex.v1.json")
        base = handoff.render_prompt(data, path)
        prompt = codex.codex_prompt(data, path, "01a09572-thread")
        self.assertTrue(prompt.startswith(base))
        # Claude-run finding 3: a successor cannot cheaply learn its own id, and
        # the ack is its mandated first action. On Codex the launcher knows it.
        self.assertIn("YOUR SESSION ID is 01a09572-thread", prompt)
        self.assertIn(f"agentops handoff ack {path} --session-id 01a09572-thread",
                      prompt)

    def test_constraints_survive_into_the_prompt(self) -> None:
        data = _handoff_fixture()
        prompt = codex.codex_prompt(data, Path("/tmp/h.json"), "t")
        self.assertIn("do not push", prompt)
        self.assertIn("append the acceptance line", prompt)

    def test_writable_roots_cover_the_repos_and_the_handoff_directory(self) -> None:
        data = _handoff_fixture()
        roots = codex.writable_roots_for(
            data, Path("/projects/dev/agentops/docs/dispatch/handoffs/h.json"))
        # The successor must be able to write the ack, which lives outside the
        # repo it is editing.
        self.assertIn("/projects/dev/agentops/docs/dispatch/handoffs", roots)
        self.assertIn("/projects/dev/outctl", roots)


class TestLaunchRefusals(unittest.TestCase):
    """A launch that should not happen must cost no thread and no turn."""

    def setUp(self) -> None:
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "2026-09-12-codex.v1.json"

    def test_launch_refuses_a_handoff_that_already_has_a_successor(self) -> None:
        self.path.write_text(json.dumps(_handoff_fixture(
            session_id="live-one", acknowledged_at="2026-09-12T00:00:01Z")))
        spawned: list[str] = []
        original = codex.StdioTransport
        codex.StdioTransport = lambda *a, **k: spawned.append("spawn")  # type: ignore
        try:
            rc = codex.main(["launch", str(self.path), "--no-verify"])
        finally:
            codex.StdioTransport = original
        self.assertEqual(rc, 1)
        self.assertEqual(spawned, [], "no app-server should be started")

    def test_launch_refuses_an_invalid_handoff(self) -> None:
        broken = _handoff_fixture()
        broken["next_action"] = ""
        self.path.write_text(json.dumps(broken))
        spawned: list[str] = []
        original = codex.StdioTransport
        codex.StdioTransport = lambda *a, **k: spawned.append("spawn")  # type: ignore
        try:
            rc = codex.main(["launch", str(self.path), "--no-verify"])
        finally:
            codex.StdioTransport = original
        self.assertEqual(rc, 1)
        self.assertEqual(spawned, [])

    def test_launch_refuses_a_missing_handoff(self) -> None:
        self.assertEqual(
            codex.main(["launch", str(self.path / "nope.json"), "--no-verify"]), 1)


if __name__ == "__main__":
    unittest.main()
