#!/usr/bin/env python3
"""Codex launch path for handoff/v1 (phase 4 of the context economy plan).

The Claude Code path launches a successor with `claude -p "$(agentops handoff
prompt <file>)"` and relies on a `SessionStart` hook for the interactive case.
Codex has no SessionStart equivalent — its hooks are deny-only — so the launch
is always explicit, through `codex app-server`'s JSON-RPC protocol.

Three subcommands, one per lifecycle step the plan names:

  launch <handoff.json>   thread/start + turn/start with the rendered handoff
                          as the first user message. Prints the thread id.
                          Records `successor.harness = "codex"` once the
                          successor has acked.
  read <thread-id>        thread/read. Prints the stored history *without*
                          resuming the thread, so a successor (or an auditor)
                          can see what a parked predecessor did without waking
                          it and without paying for its context.
  consult <thread-id> <q> thread/resume + turn/start. This DOES wake the
                          thread: the question is answered against the parked
                          session's *full* context and is billed accordingly.
                          That is the intended cost shape (the plan's "billed
                          against its full context"), but it is the expensive
                          door — prefer `read` when the answer is already in
                          the transcript.

Transport
---------
app-server speaks newline-delimited JSON-RPC 2.0. `--listen stdio://` is the
default, so no daemon is required: we spawn `codex app-server --stdio` as a
subprocess and talk to its stdin/stdout. `StdioTransport` is the only
production transport; every request is built by a pure function so the tests
can drive `AppServerClient` through a fake transport with no subprocess and no
network.

No third-party dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import handoff as handoff_mod  # noqa: E402  (path shim above)

CLIENT_NAME = "agentops-handoff"
CLIENT_VERSION = "1"

# app-server methods this module uses. Named here so the tests assert against
# one list and a protocol rename shows up as one diff.
M_INITIALIZE = "initialize"
N_INITIALIZED = "initialized"
M_THREAD_START = "thread/start"
M_THREAD_RESUME = "thread/resume"
M_THREAD_READ = "thread/read"
M_TURN_START = "turn/start"

N_TURN_COMPLETED = "turn/completed"
N_ITEM_COMPLETED = "item/completed"
N_THREAD_ERROR = "thread/status/changed"

DEFAULT_TURN_TIMEOUT = 600.0


class CodexError(Exception):
    """Anything that should end the command with a message, not a traceback."""


# ---------------------------------------------------------------------------
# request construction (pure — this is what the tests pin)


def initialize_request(request_id: int,
                       name: str = CLIENT_NAME,
                       version: str = CLIENT_VERSION) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": M_INITIALIZE,
        "params": {"clientInfo": {"name": name, "version": version}},
    }


def initialized_notification() -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": N_INITIALIZED}


def thread_start_request(request_id: int,
                         cwd: str,
                         *,
                         sandbox: str = "workspace-write",
                         approval_policy: str = "never",
                         model: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "cwd": cwd,
        "sandbox": sandbox,
        "approvalPolicy": approval_policy,
    }
    if model:
        params["model"] = model
    return {"jsonrpc": "2.0", "id": request_id,
            "method": M_THREAD_START, "params": params}


def thread_resume_request(request_id: int,
                          thread_id: str,
                          *,
                          cwd: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"threadId": thread_id}
    if cwd:
        params["cwd"] = cwd
    return {"jsonrpc": "2.0", "id": request_id,
            "method": M_THREAD_RESUME, "params": params}


def thread_read_request(request_id: int,
                        thread_id: str,
                        *,
                        include_turns: bool = False) -> dict[str, Any]:
    """thread/read.

    `includeTurns` is deprecated upstream and, on codex-cli 0.153.4, answers
    `-32601 list_turns is not supported yet`; the paginated replacements
    (`thread/turns/list`, `thread/items/list`) answer the same. So the default
    is a metadata-only read and the history comes from the rollout file whose
    path the metadata carries. Kept as a parameter so the day the server grows
    the capability the caller is one flag away.
    """
    params: dict[str, Any] = {"threadId": thread_id}
    if include_turns:
        params["includeTurns"] = True
    return {"jsonrpc": "2.0", "id": request_id,
            "method": M_THREAD_READ, "params": params}


def turn_start_request(request_id: int,
                       thread_id: str,
                       text: str,
                       *,
                       cwd: str | None = None,
                       sandbox_policy: dict[str, Any] | None = None,
                       approval_policy: str | None = None,
                       model: str | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {
        "threadId": thread_id,
        "input": [{"type": "text", "text": text}],
    }
    if cwd:
        params["cwd"] = cwd
    if sandbox_policy:
        params["sandboxPolicy"] = sandbox_policy
    if approval_policy:
        params["approvalPolicy"] = approval_policy
    if model:
        params["model"] = model
    return {"jsonrpc": "2.0", "id": request_id,
            "method": M_TURN_START, "params": params}


def workspace_write_policy(writable_roots: Iterable[str],
                           *, network: bool = False) -> dict[str, Any]:
    return {
        "type": "workspaceWrite",
        "writableRoots": [str(Path(r).resolve()) for r in writable_roots],
        "networkAccess": network,
    }


# ---------------------------------------------------------------------------
# transport


class StdioTransport:
    """`codex app-server --stdio` as a subprocess, one JSON object per line."""

    def __init__(self, argv: list[str] | None = None,
                 stderr_sink: Callable[[str], None] | None = None) -> None:
        self.argv = argv or ["codex", "app-server", "--stdio"]
        self._stderr_sink = stderr_sink or (lambda line: None)
        try:
            self.proc = subprocess.Popen(
                self.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, bufsize=1)
        except FileNotFoundError as exc:
            raise CodexError(
                f"{self.argv[0]} not found on PATH; codex-cli must be "
                f"installed to use the Codex handoff path") from exc
        self._err = threading.Thread(target=self._drain_stderr, daemon=True)
        self._err.start()

    def _drain_stderr(self) -> None:
        assert self.proc.stderr is not None
        for line in self.proc.stderr:
            self._stderr_sink(line.rstrip("\n"))

    def send(self, message: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def recv(self) -> dict[str, Any] | None:
        assert self.proc.stdout is not None
        while True:
            line = self.proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# client


class AppServerClient:
    """JSON-RPC client over any transport with `send` / `recv` / `close`."""

    def __init__(self, transport: Any,
                 on_notification: Callable[[dict[str, Any]], None] | None = None,
                 deadline: float | None = None) -> None:
        self.transport = transport
        self.on_notification = on_notification or (lambda msg: None)
        self._id = 0
        self.deadline = deadline

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    # -- plumbing ----------------------------------------------------------

    def _pump(self, request_id: int) -> dict[str, Any]:
        """Read until the response to `request_id`, dispatching what passes."""
        while True:
            if self.deadline is not None and time.monotonic() > self.deadline:
                raise CodexError("timed out waiting for app-server")
            msg = self.transport.recv()
            if msg is None:
                raise CodexError("app-server closed the connection")
            if msg.get("id") == request_id and ("result" in msg or "error" in msg):
                if "error" in msg:
                    err = msg["error"]
                    raise CodexError(
                        f"app-server error {err.get('code')}: {err.get('message')}")
                return msg["result"]
            if "method" in msg and "id" in msg:
                self._answer_server_request(msg)
                continue
            if "method" in msg:
                self.on_notification(msg)

    def _answer_server_request(self, msg: dict[str, Any]) -> None:
        """Server-initiated requests (approvals, elicitations).

        We launch with `approvalPolicy: never`, so an approval request means
        the sandbox policy and the task disagree. Denying is the honest answer:
        a successor that needs an approval nobody is there to grant should stop
        and say so, not hang.
        """
        self.transport.send({
            "jsonrpc": "2.0",
            "id": msg["id"],
            "error": {"code": -32000,
                      "message": "no interactive reviewer: launched with "
                                 "approvalPolicy=never"},
        })

    def call(self, build: Callable[[int], dict[str, Any]]) -> dict[str, Any]:
        request_id = self._next_id()
        message = build(request_id)
        self.transport.send(message)
        return self._pump(request_id)

    def notify(self, message: dict[str, Any]) -> None:
        self.transport.send(message)

    # -- protocol ----------------------------------------------------------

    def initialize(self) -> dict[str, Any]:
        result = self.call(initialize_request)
        self.notify(initialized_notification())
        return result

    def thread_start(self, cwd: str, **kw: Any) -> dict[str, Any]:
        return self.call(lambda i: thread_start_request(i, cwd, **kw))

    def thread_resume(self, thread_id: str, **kw: Any) -> dict[str, Any]:
        return self.call(lambda i: thread_resume_request(i, thread_id, **kw))

    def thread_read(self, thread_id: str, **kw: Any) -> dict[str, Any]:
        return self.call(lambda i: thread_read_request(i, thread_id, **kw))

    def turn_start(self, thread_id: str, text: str, **kw: Any) -> dict[str, Any]:
        return self.call(lambda i: turn_start_request(i, thread_id, text, **kw))


def thread_id_of(start_result: dict[str, Any]) -> str:
    """thread/start answers `{"thread": {"id": ...}, ...}`."""
    thread = start_result.get("thread") or {}
    tid = thread.get("id") or thread.get("sessionId") or start_result.get("threadId")
    if not tid:
        raise CodexError(
            f"thread/start returned no thread id: {json.dumps(start_result)[:400]}")
    return str(tid)


# ---------------------------------------------------------------------------
# turn observation


class TurnWatcher:
    """Collects the notifications that say a turn is over and what it said."""

    def __init__(self, echo: bool = True) -> None:
        self.echo = echo
        self.done = False
        self.messages: list[str] = []
        self.commands: list[str] = []
        self.error: str | None = None

    def __call__(self, msg: dict[str, Any]) -> None:
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == N_ITEM_COMPLETED:
            item = params.get("item") or {}
            kind = item.get("type") or item.get("itemType")
            if kind in ("agentMessage", "assistantMessage"):
                text = item.get("text") or ""
                if text:
                    self.messages.append(text)
                    if self.echo:
                        print(text, flush=True)
            elif kind == "commandExecution":
                cmd = item.get("command") or ""
                if cmd:
                    self.commands.append(cmd if isinstance(cmd, str) else " ".join(cmd))
                    if self.echo:
                        print(f"  $ {self.commands[-1]}", file=sys.stderr, flush=True)
        elif method == N_TURN_COMPLETED:
            turn = params.get("turn") or {}
            if turn.get("error"):
                self.error = json.dumps(turn["error"])
            self.done = True


def wait_for_turn(client: AppServerClient, watcher: TurnWatcher,
                  timeout: float) -> None:
    """Pump notifications until `turn/completed` or the timeout."""
    end = time.monotonic() + timeout
    while not watcher.done:
        if time.monotonic() > end:
            raise CodexError(f"turn did not complete within {timeout:.0f}s")
        msg = client.transport.recv()
        if msg is None:
            raise CodexError("app-server closed the connection mid-turn")
        if "method" in msg and "id" in msg:
            client._answer_server_request(msg)
            continue
        if "method" in msg:
            watcher(msg)


# ---------------------------------------------------------------------------
# rollout transcript (the `read` fallback)


def rollout_path(read_result: dict[str, Any]) -> Path | None:
    thread = read_result.get("thread") or {}
    path = thread.get("path")
    return Path(path) if path else None


def rollout_history(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Parse a rollout .jsonl into `{role, kind, text}` records.

    Reading the file the server names is not resuming the thread: nothing is
    sent to the model and the parked session is not woken.
    """
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = rec.get("payload") if isinstance(rec, dict) else None
            if not isinstance(payload, dict):
                continue
            kind = payload.get("type") or rec.get("type") or ""
            role = payload.get("role") or ""
            text = _payload_text(payload)
            if not text:
                continue
            out.append({"kind": str(kind), "role": str(role), "text": text})
    if limit is not None:
        out = out[-limit:]
    return out


def _payload_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("text"), str):
        return payload["text"]
    content = payload.get("content")
    parts: list[str] = []
    if isinstance(content, list):
        for chunk in content:
            if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                parts.append(chunk["text"])
            elif isinstance(chunk, str):
                parts.append(chunk)
    elif isinstance(content, str):
        parts.append(content)
    if isinstance(payload.get("message"), str):
        parts.append(payload["message"])
    return "\n".join(p for p in parts if p).strip()


# ---------------------------------------------------------------------------
# handoff glue


def codex_prompt(handoff: dict[str, Any], path: Path, thread_id: str) -> str:
    """The shared rendered prompt plus the one thing Codex can supply cheaply.

    Finding 3 of the Claude Code runs: a successor cannot cheaply learn its own
    session id, and the ack is its mandated first action, so every successor
    burns tool calls guessing. On Codex the launcher knows the thread id before
    the first turn exists, so it just says so.
    """
    base = handoff_mod.render_prompt(handoff, path)
    return base + (
        f"\n\nYOUR SESSION ID is {thread_id} (the Codex thread id). Use it "
        f"verbatim in the ack:\n"
        f"  agentops handoff ack {path} --session-id {thread_id}\n"
        f"Do not go looking for it; do not infer it from a transcript file.")


def record_harness(path: Path, harness: str = "codex",
                   expect_session_id: str | None = None) -> str:
    """Set `successor.harness` once the successor has acked.

    `ack` writes `successor` wholesale, so the harness is stamped after the
    fact rather than reserved before it — which also means the field is only
    ever present on a handoff that really was claimed.
    """
    data = handoff_mod.read_handoff(path)
    successor = data.get("successor") or {}
    session_id = successor.get("session_id")
    if not session_id:
        return ""
    if expect_session_id and session_id != expect_session_id:
        raise CodexError(
            f"handoff {path} was acked by {session_id}, not the thread we "
            f"launched ({expect_session_id}); refusing to stamp harness")
    if successor.get("harness") == harness:
        return session_id
    successor["harness"] = harness
    data["successor"] = successor
    errors = handoff_mod.schema_errors(data)
    if errors:
        raise CodexError(
            "refusing to write a handoff the schema rejects: " + "; ".join(errors))
    handoff_mod.write_atomic(path, json.dumps(data, indent=2) + "\n")
    md = path.with_suffix(".md")
    if md.exists():
        handoff_mod.write_atomic(md, handoff_mod.render_markdown(data))
    return session_id


def writable_roots_for(handoff: dict[str, Any], path: Path) -> list[str]:
    roots = {str(path.resolve().parent)}
    for repo in handoff["state"]["repos"]:
        roots.add(str(Path(repo["path"]).resolve()))
    return sorted(roots)


# ---------------------------------------------------------------------------
# commands


def _connect(timeout: float, quiet: bool = False) -> tuple[StdioTransport, AppServerClient]:
    sink = (lambda line: None) if quiet else (
        lambda line: print(f"app-server| {line}", file=sys.stderr))
    transport = StdioTransport(stderr_sink=sink)
    client = AppServerClient(transport, deadline=time.monotonic() + timeout)
    client.initialize()
    return transport, client


def cmd_launch(args: argparse.Namespace) -> int:
    path = Path(args.handoff).resolve()
    data = handoff_mod.read_handoff(path)

    errors = handoff_mod.validate_handoff(data, check_tree=not args.no_verify)
    if errors:
        for err in errors:
            print(f"handoff invalid: {err}", file=sys.stderr)
        print("Refusing to launch a successor on a handoff that does not "
              "describe reality.", file=sys.stderr)
        return 1

    live = (data.get("successor") or {}).get("session_id")
    if live:
        print(f"handoff {data['handoff_id']} already has a live successor: "
              f"{live}. Refusing: exactly one successor may be active.",
              file=sys.stderr)
        return 1

    cwd = args.cwd or (data["state"]["repos"][0]["path"] if data["state"]["repos"]
                       else str(Path.cwd()))
    roots = writable_roots_for(data, path)

    transport, client = _connect(args.timeout, quiet=args.quiet)
    try:
        started = client.thread_start(
            cwd, sandbox=args.sandbox, approval_policy="never", model=args.model)
        thread_id = thread_id_of(started)
        print(f"thread_id: {thread_id}", flush=True)
        print(f"rollout:   {(started.get('thread') or {}).get('path', '?')}",
              flush=True)
        if args.print_prompt:
            print("--- prompt ---")
            print(codex_prompt(data, path, thread_id))
            print("--- end prompt ---")
        if args.dry_run:
            return 0

        watcher = TurnWatcher(echo=not args.quiet)
        client.on_notification = watcher
        client.deadline = None
        client.turn_start(
            thread_id,
            codex_prompt(data, path, thread_id),
            cwd=cwd,
            sandbox_policy=workspace_write_policy(roots),
            approval_policy="never")
        wait_for_turn(client, watcher, args.timeout)
        if watcher.error:
            print(f"turn ended with an error: {watcher.error}", file=sys.stderr)
    finally:
        transport.close()

    acked = record_harness(path, "codex", expect_session_id=thread_id)
    if acked:
        print(f"acked by {acked}; successor.harness = codex")
        return 0
    print("successor.session_id is still null: the successor did not ack. "
          "That is a run failure, not a tooling error — see the transcript "
          f"with: handoff_codex.py read {thread_id}", file=sys.stderr)
    return 2


def cmd_read(args: argparse.Namespace) -> int:
    transport, client = _connect(args.timeout, quiet=True)
    try:
        result = client.thread_read(args.thread_id, include_turns=args.include_turns)
    finally:
        transport.close()

    thread = result.get("thread") or {}
    print(f"thread:  {thread.get('id')}")
    print(f"model:   {thread.get('model')} ({thread.get('modelProvider')})")
    print(f"cwd:     {thread.get('cwd')}")
    print(f"status:  {(thread.get('status') or {}).get('type')}")
    print(f"rollout: {thread.get('path')}")
    print()

    turns = thread.get("turns") or []
    if turns:
        print(json.dumps(turns, indent=2))
        return 0

    path = rollout_path(result)
    if path is None:
        print("no rollout path in the thread metadata and no turns returned.",
              file=sys.stderr)
        return 1
    history = rollout_history(path, limit=args.limit)
    if not history:
        print(f"(no readable history in {path})")
        return 0
    print(f"# history from the rollout file ({len(history)} records); "
          f"the thread was not resumed")
    for rec in history:
        label = rec["role"] or rec["kind"]
        print(f"\n--- {label} ---")
        print(rec["text"])
    return 0


def cmd_consult(args: argparse.Namespace) -> int:
    print("NOTE: consulting resumes the thread and starts a turn. The answer "
          "is produced against the parked session's FULL context and is "
          "billed against it. Prefer `read` when the answer is already in the "
          "transcript.", file=sys.stderr)
    question = " ".join(args.question)
    framing = (
        "You are being consulted as a parked predecessor session. You are "
        "READ-ONLY: make no edits and take no external actions. Answer from "
        "what you already know, then stop.\n\nQuestion: " + question)

    transport, client = _connect(args.timeout, quiet=args.quiet)
    try:
        client.thread_resume(args.thread_id, cwd=args.cwd)
        watcher = TurnWatcher(echo=not args.quiet)
        client.on_notification = watcher
        client.deadline = None
        client.turn_start(
            args.thread_id, framing,
            sandbox_policy={"type": "readOnly", "networkAccess": False},
            approval_policy="never")
        wait_for_turn(client, watcher, args.timeout)
        if watcher.error:
            print(f"turn ended with an error: {watcher.error}", file=sys.stderr)
            return 1
    finally:
        transport.close()
    if args.quiet:
        print("\n\n".join(watcher.messages))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="handoff_codex.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    launch = sub.add_parser("launch", help="Start a Codex successor on a handoff")
    launch.add_argument("handoff")
    launch.add_argument("--cwd", default=None,
                        help="Working directory for the thread "
                             "(default: the handoff's first repo)")
    launch.add_argument("--model", default=None)
    launch.add_argument("--sandbox", default="workspace-write",
                        choices=["read-only", "workspace-write", "danger-full-access"])
    launch.add_argument("--timeout", type=float, default=DEFAULT_TURN_TIMEOUT,
                        help="Seconds to wait for the first turn (default 600)")
    launch.add_argument("--no-verify", action="store_true",
                        help="Skip the tree check (for testing the launch path "
                             "itself; never for a real handoff)")
    launch.add_argument("--dry-run", action="store_true",
                        help="Start the thread, print the id and prompt, send no turn")
    launch.add_argument("--print-prompt", action="store_true")
    launch.add_argument("--quiet", action="store_true")
    launch.set_defaults(func=cmd_launch)

    read = sub.add_parser(
        "read", help="Print a thread's stored history without resuming it")
    read.add_argument("thread_id")
    read.add_argument("--limit", type=int, default=None,
                      help="Only the last N records")
    read.add_argument("--include-turns", action="store_true",
                      help="Ask the server to hydrate turns "
                           "(unsupported on codex-cli 0.153.4)")
    read.add_argument("--timeout", type=float, default=60.0)
    read.set_defaults(func=cmd_read)

    consult = sub.add_parser(
        "consult",
        help="Ask a parked thread a question (resumes it; billed against its "
             "full context)")
    consult.add_argument("thread_id")
    consult.add_argument("question", nargs="+")
    consult.add_argument("--cwd", default=None)
    consult.add_argument("--timeout", type=float, default=DEFAULT_TURN_TIMEOUT)
    consult.add_argument("--quiet", action="store_true")
    consult.set_defaults(func=cmd_consult)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (CodexError, handoff_mod.HandoffError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
