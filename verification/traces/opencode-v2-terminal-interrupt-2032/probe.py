#!/usr/bin/env python3
"""Disposable terminal/interruption/queue/restart probe for OpenCode 2.0.32.

Run on devbox from stdin in bwrap --unshare-net. All sessions, config, auth,
and sentinels are synthetic and temporary; inference is loopback-only.
"""

import base64
import hashlib
import json
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


BINARY = "/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
DENY = [{"action": "*", "resource": "*", "effect": "deny"}]
QUEUE_HOLD = "QUEUE-HOLD"
FOREIGN_HOLD = "FOREIGN-HOLD"
INTERRUPT_HOLD = "INTERRUPT-HOLD"
INTERRUPT_QUEUE_HOLD = "INTERRUPT-QUEUE-HOLD"
CANCEL_HOLD = "CANCEL-HOLD"
MARKERS = [QUEUE_HOLD, FOREIGN_HOLD, INTERRUPT_HOLD, INTERRUPT_QUEUE_HOLD, CANCEL_HOLD,
           "QUEUE-ONE", "QUEUE-TWO", "FOREIGN-QUEUED", "INTERRUPT-QUEUED", "CANCEL-QUEUED"]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def text_of(value):
    found = []
    def visit(node):
        if isinstance(node, dict):
            if isinstance(node.get("text"), str):
                found.append(node["text"])
            for key, child in node.items():
                if key != "text":
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(value)
    return " ".join(found)


def safe_status(snapshot):
    if snapshot is None:
        return None
    return {
        "http_status": snapshot.get("http_status"),
        "record_present": snapshot.get("record_present"),
        "record_type": snapshot.get("record_type"),
        "record_keys": snapshot.get("record_keys"),
        "record_value": snapshot.get("record_value"),
        "envelope_keys": snapshot.get("envelope_keys"),
    }


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-terminal-probe-", dir="/tmp"))
    mock = None
    server = None
    proxy = None
    provider_calls = []
    hold_started = {}
    hold_release = {}
    observations = {}
    try:
        for name in ("home", "config", "data", "state", "cache", "work"):
            (root / name).mkdir(mode=0o700)
        for marker in (QUEUE_HOLD, FOREIGN_HOLD, INTERRUPT_HOLD, INTERRUPT_QUEUE_HOLD, CANCEL_HOLD):
            hold_started[marker] = threading.Event()
            hold_release[marker] = threading.Event()

        class FakeProvider(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
                serialized = json.dumps(request.get("messages", []))
                positions = [(serialized.rfind(marker) + len(marker), len(marker), marker)
                             for marker in MARKERS if marker in serialized]
                page_markers = [(match.end(), len(match.group(0)), match.group(0))
                                for match in re.finditer(r"PAGINATION-TURN-[0-9]{2}", serialized)]
                positions.extend(page_markers)
                marker = max(positions)[2] if positions else "OTHER"
                provider_calls.append(marker)
                if marker in hold_started and not hold_started[marker].is_set():
                    hold_started[marker].set()
                    hold_release[marker].wait(20)
                content = "synthetic reply: " + marker
                if marker == "NO-ROUTE":
                    content = "unexpected synthetic route"
                chunks = [
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]},
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                ]
                encoded = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                           + "data: [DONE]\n\n").encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_args):
                pass

        mock = ThreadingHTTPServer(("127.0.0.1", free_port()), FakeProvider)
        threading.Thread(target=mock.serve_forever, daemon=True).start()
        work = root / "work"
        config_path = work / "opencode.json"
        config_path.write_text(json.dumps({
            "model": "mock/fake",
            "provider": {"mock": {
                "npm": "@ai-sdk/openai-compatible", "name": "synthetic loopback provider",
                "options": {"baseURL": f"http://127.0.0.1:{mock.server_address[1]}/v1", "apiKey": "synthetic-only"},
                "models": {"fake": {"name": "Fake", "tool_call": True,
                                     "limit": {"context": 128000, "output": 4096}}},
            }},
        }), encoding="utf-8")

        username = "opencode"
        password = secrets.token_urlsafe(32)
        authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        env = {
            "PATH": "/run/current-system/sw/bin:/usr/bin:/bin",
            "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"), "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"), "OPENCODE_SERVER_PASSWORD": password,
        }
        port = free_port()
        origin = f"http://127.0.0.1:{port}"

        def start_server(next_port):
            nonlocal server, origin
            if server is not None:
                server.terminate()
                try:
                    server.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
            port_value = next_port or free_port()
            server = subprocess.Popen(
                [BINARY, "serve", "--hostname", "127.0.0.1", "--port", str(port_value)],
                env=env, cwd=str(work), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            origin = f"http://127.0.0.1:{port_value}"
            for _ in range(120):
                if server.poll() is not None:
                    raise RuntimeError("OpenCode exited before readiness")
                try:
                    status, value = call("GET", "/api/info")
                    if status == 200 and isinstance(value, dict):
                        return value
                except Exception:
                    pass
                time.sleep(0.1)
            raise RuntimeError("OpenCode did not become ready")

        def call(method, path, body=None, query=None):
            url = origin + path
            if query:
                url += "?" + urllib.parse.urlencode(query)
            request = urllib.request.Request(
                url, method=method,
                data=None if body is None else json.dumps(body).encode(),
                headers={"Authorization": authorization, "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    raw = response.read()
                    return response.status, json.loads(raw) if raw else None
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                try:
                    return exc.code, json.loads(raw) if raw else None
                except ValueError:
                    return exc.code, None

        info = start_server(port)
        require(info.get("version") == "2.0.32", "pinned server version mismatch")
        openapi = call("GET", "/openapi.json")[1]
        paths = openapi["paths"]
        status_candidates = [path for path, methods in paths.items()
                             if "session" in path.lower() and "status" in path.lower() and "get" in methods]
        status_path = status_candidates[0] if status_candidates else None
        interrupt_candidates = [path for path, methods in paths.items()
                                if "session" in path.lower() and "interrupt" in path.lower() and "post" in methods]
        interrupt_template = interrupt_candidates[0] if interrupt_candidates else None
        delete_candidates = [(path, method) for path, methods in paths.items()
                             for method in methods if method.lower() == "delete" and "inbox" in path.lower()]
        delete_template = delete_candidates[0][0] if delete_candidates else None
        observations["route_discovery"] = {
            "session_status_get_paths": status_candidates,
            "interrupt_post_paths": interrupt_candidates,
            "inbox_delete_paths": [path for path, _ in delete_candidates],
        }

        def create(title, model="mock/fake"):
            status, payload = call("POST", "/api/session", {
                "title": title, "location": {"directory": str(work)},
                "model": {"providerID": model.split("/")[0], "id": model.split("/")[1]},
                "permissions": DENY,
            })
            require(status == 200 and isinstance(payload, dict), "session create failed")
            return payload["data"]["id"]

        def prompt(sid, mid, text, delivery=None):
            body = {"id": mid, "text": text}
            if delivery:
                body["delivery"] = delivery
            return call("POST", f"/api/session/{sid}/prompt", body)

        def get_messages(sid, query=None):
            status, payload = call("GET", f"/api/session/{sid}/message", query=query)
            require(status == 200 and isinstance(payload, dict), "message read failed")
            return payload

        def wait_messages(sid, predicate, timeout=8):
            deadline = time.time() + timeout
            rows = []
            while time.time() < deadline:
                rows = get_messages(sid).get("data", [])
                if predicate(rows):
                    return rows
                time.sleep(0.04)
            return rows

        def status_snapshot(sid):
            if not status_path:
                return None
            status, payload = call("GET", status_path)
            values = payload.get("data", payload) if isinstance(payload, dict) else None
            row = values.get(sid) if isinstance(values, dict) else None
            return {
                "http_status": status,
                "envelope_keys": sorted(payload) if isinstance(payload, dict) else [],
                "record_present": row is not None,
                "record_type": row.get("type") if isinstance(row, dict) else (row if isinstance(row, str) else None),
                "record_keys": sorted(row) if isinstance(row, dict) else [],
                "record_value": row if isinstance(row, str) else None,
            }

        def make_path(template, sid, inbox_id):
            value = template.replace("{sessionID}", sid).replace("{sessionId}", sid)
            for token in ("{messageID}", "{messageId}", "{inboxID}", "{inboxId}", "{id}"):
                value = value.replace(token, inbox_id)
            return value

        # Terminal success + status busy -> idle while provider is held.
        queue_sid = create("queue-duplicates")
        qhold_id, qhold_text = "msg_queue_hold", QUEUE_HOLD
        hold_status, hold_ack = prompt(queue_sid, qhold_id, qhold_text)
        require(hold_status == 200 and hold_started[QUEUE_HOLD].wait(8), "queue hold did not start")
        queue_busy = status_snapshot(queue_sid)
        q1_id, q1_text = "msg_queue_one", "QUEUE-ONE"
        q2_id, q2_text = "msg_queue_two", "QUEUE-TWO"
        q1_status, q1_ack = prompt(queue_sid, q1_id, q1_text, "queue")
        q1dup_status, q1dup_ack = prompt(queue_sid, q1_id, q1_text, "queue")
        q1conflict_status, q1conflict_ack = prompt(queue_sid, q1_id, "QUEUE-ONE-CONFLICT", "queue")
        q2_status, q2_ack = prompt(queue_sid, q2_id, q2_text, "queue")
        queue_inbox_status, queue_inbox = call("GET", f"/api/session/{queue_sid}/inbox")
        queue_inbox_rows = queue_inbox.get("data", []) if isinstance(queue_inbox, dict) else []
        queue_before_release = [{"id": row.get("id"), "text": (row.get("payload") or {}).get("text"),
                                "delivery": row.get("delivery"), "session_matches": row.get("sessionID") == queue_sid}
                               for row in queue_inbox_rows]

        # Same ID belonging to a different live session is foreign to queue_sid.
        foreign_sid = create("foreign-queue")
        foreign_status, _foreign_hold_ack = prompt(foreign_sid, "msg_foreign_hold", FOREIGN_HOLD)
        require(foreign_status == 200 and hold_started[FOREIGN_HOLD].wait(8), "foreign hold did not start")
        foreign_id, foreign_text = "msg_foreign_queued", "FOREIGN-QUEUED"
        foreign_queue_status, foreign_queue_ack = prompt(foreign_sid, foreign_id, foreign_text, "queue")
        foreign_inbox_status, foreign_inbox = call("GET", f"/api/session/{foreign_sid}/inbox")
        foreign_inbox_rows = foreign_inbox.get("data", []) if isinstance(foreign_inbox, dict) else []
        queue_inbox_after_foreign_status, queue_inbox_after_foreign = call("GET", f"/api/session/{queue_sid}/inbox")
        queue_rows_after_foreign = (queue_inbox_after_foreign or {}).get("data", [])
        queue_does_not_contain_foreign = not any(row.get("id") == foreign_id for row in queue_rows_after_foreign)

        foreign_delete = None
        if delete_template:
            foreign_delete = call("DELETE", make_path(delete_template, queue_sid, foreign_id))[0]
        foreign_still_present = any(row.get("id") == foreign_id for row in
                                    ((call("GET", f"/api/session/{foreign_sid}/inbox")[1] or {}).get("data", [])))

        hold_release[QUEUE_HOLD].set()
        hold_release[FOREIGN_HOLD].set()
        queue_drained = wait_messages(queue_sid, lambda rows: (
            all(any(row.get("type") == "user" and row.get("id") == qid for row in rows)
                for qid in (q1_id, q2_id))
            and all(any(row.get("type") == "assistant" and marker in text_of(row) for row in rows)
                    for marker in ("QUEUE-ONE", "QUEUE-TWO"))
            and any(row.get("type") == "idle" for row in rows)), timeout=18)
        foreign_drained = wait_messages(foreign_sid, lambda rows: any(
            row.get("type") == "user" and row.get("id") == foreign_id for row in rows), timeout=12)
        queue_terminal_rows = [row for row in queue_drained if row.get("type") == "idle"]
        queue_status_idle = status_snapshot(queue_sid)
        foreign_status_idle = status_snapshot(foreign_sid)
        # Captures transcript order as returned, without asserting linkage to idle.
        queue_order = [{"type": row.get("type"),
                        "id": row.get("id") if row.get("type") == "user" else None,
                        "non_input_message_id_present": bool(row.get("id")) if row.get("type") != "user" else None,
                        "text": row.get("text") if row.get("type") == "user" else text_of(row) if row.get("type") == "assistant" else None,
                        "outcome": row.get("outcome") if row.get("type") == "idle" else None,
                        "finish": row.get("finish") if row.get("type") == "assistant" else None}
                       for row in reversed(queue_drained)]
        observations["queue_duplicate_foreign"] = {
            "status_busy": safe_status(queue_busy),
            "prompt_ack_statuses": {"first": q1_status, "same_id_same_text": q1dup_status,
                                     "same_id_different_text": q1conflict_status, "second_id": q2_status},
            "first_ack_id_matches": (q1_ack or {}).get("data", {}).get("id") == q1_id,
            "duplicate_ack_id_matches": (q1dup_ack or {}).get("data", {}).get("id") == q1_id,
            "conflict_ack_text": ((q1conflict_ack or {}).get("data", {}).get("payload") or {}).get("text"),
            "inbox_status": queue_inbox_status,
            "inbox_rows_before_release": queue_before_release,
            "same_id_count_in_inbox": sum(row.get("id") == q1_id for row in queue_inbox_rows),
            "foreign_session_queue_status": foreign_queue_status,
            "foreign_session_inbox_status": foreign_inbox_status,
            "foreign_session_inbox_count": len(foreign_inbox_rows),
            "foreign_input_absent_from_other_session_inbox": queue_does_not_contain_foreign,
            "cross_session_delete_status": foreign_delete,
            "foreign_item_still_in_own_inbox": foreign_still_present,
            "queue_terminal_idle_count": len(queue_terminal_rows),
            "queue_drain_assertion": bool(queue_terminal_rows) and all(
                any(row.get("type") == "assistant" and marker in text_of(row) for row in queue_drained)
                for marker in ("QUEUE-ONE", "QUEUE-TWO")),
            "queue_terminal_outcomes": [row.get("outcome") for row in queue_terminal_rows],
            "queue_transcript_order_oldest_to_newest": queue_order,
            "status_after_drain": safe_status(queue_status_idle),
            "foreign_status_after_drain": safe_status(foreign_status_idle),
            "foreign_user_present_after_drain": any(row.get("type") == "user" and row.get("id") == foreign_id
                                                      for row in foreign_drained),
        }

        # Interrupt an active turn with a queued successor; inspect inbox and
        # transcript after the acknowledgement instead of inferring removal.
        interrupt_sid = create("interrupt-with-queue")
        int_hold_status, int_hold_ack = prompt(interrupt_sid, "msg_interrupt_hold", INTERRUPT_QUEUE_HOLD)
        int_hold_seen = hold_started[INTERRUPT_QUEUE_HOLD].wait(8)
        if int_hold_status != 200 or not int_hold_seen:
            raise RuntimeError(json.dumps({
                "case": "interrupt queue hold",
                "http_status": int_hold_status,
                "ack_keys": sorted(int_hold_ack) if isinstance(int_hold_ack, dict) else None,
                "provider_calls": provider_calls,
                "provider_events": {key: value.is_set() for key, value in hold_started.items()},
                "message_types": [row.get("type") for row in get_messages(interrupt_sid).get("data", [])],
            }, sort_keys=True))
        int_queue_id = "msg_interrupt_queued"
        int_queue_status, int_queue_ack = prompt(interrupt_sid, int_queue_id, "INTERRUPT-QUEUED", "queue")
        int_busy = status_snapshot(interrupt_sid)
        interrupt_status, interrupt_payload = call("POST", f"/api/session/{interrupt_sid}/interrupt")
        int_inbox_status_after_ack, int_inbox_after_ack = call("GET", f"/api/session/{interrupt_sid}/inbox")
        int_inbox_after_ack_rows = (int_inbox_after_ack or {}).get("data", [])
        int_messages_after_ack = get_messages(interrupt_sid).get("data", [])
        hold_release[INTERRUPT_QUEUE_HOLD].set()
        int_terminal_messages = wait_messages(interrupt_sid, lambda rows: (
            any(row.get("type") == "user" and row.get("id") == int_queue_id for row in rows)
            and any(row.get("type") == "idle" for row in rows)), timeout=12)
        int_inbox_after_drain_status, int_inbox_after_drain = call("GET", f"/api/session/{interrupt_sid}/inbox")
        int_status_after = status_snapshot(interrupt_sid)
        observations["interrupt_with_queued_input"] = {
            "queued_prompt_status": int_queue_status,
            "interrupt_http_status": interrupt_status,
            "interrupt_response": interrupt_payload,
            "status_before_interrupt": safe_status(int_busy),
            "inbox_status_immediately_after_ack": int_inbox_status_after_ack,
            "queued_id_still_in_inbox_immediately": any(row.get("id") == int_queue_id for row in int_inbox_after_ack_rows),
            "queued_id_in_transcript_immediately": any(row.get("type") == "user" and row.get("id") == int_queue_id
                                                       for row in int_messages_after_ack),
            "idle_outcomes_after_interrupt": [row.get("outcome") for row in int_terminal_messages if row.get("type") == "idle"],
            "assistant_finishes_after_interrupt": [row.get("finish") for row in int_terminal_messages if row.get("type") == "assistant"],
            "queued_id_in_transcript_after_wait": any(row.get("type") == "user" and row.get("id") == int_queue_id
                                                       for row in int_terminal_messages),
            "inbox_status_after_wait": int_inbox_after_drain_status,
            "queued_id_in_inbox_after_wait": any(row.get("id") == int_queue_id
                                                  for row in (int_inbox_after_drain or {}).get("data", [])),
            "status_after_wait": safe_status(int_status_after),
        }

        # Test explicit inbox DELETE with the caller response lost after an
        # upstream success, then observe actual queue/transcript state.
        cancel_sid = create("queue-cancellation")
        cancel_hold_status, _cancel_hold_ack = prompt(cancel_sid, "msg_cancel_hold", CANCEL_HOLD)
        require(cancel_hold_status == 200 and hold_started[CANCEL_HOLD].wait(8), "cancel hold did not start")
        cancel_id, cancel_text = "msg_cancel_queued", "CANCEL-QUEUED"
        cancel_queue_status, _cancel_queue_ack = prompt(cancel_sid, cancel_id, cancel_text, "queue")
        cancel_pre_inbox_status, cancel_pre_inbox = call("GET", f"/api/session/{cancel_sid}/inbox")
        cancel_pre_rows = (cancel_pre_inbox or {}).get("data", [])
        cancel_proxy_observation = {}
        cancel_client_error = None
        if delete_template:
            proxy_port = free_port()

            class DropDeleteProxy(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"

                def do_DELETE(self):
                    body = self.rfile.read(int(self.headers.get("content-length", "0")))
                    headers = {key: value for key, value in self.headers.items()
                               if key.lower() not in ("host", "content-length", "connection")}
                    upstream = urllib.request.Request(origin + self.path, data=body or None,
                                                      headers=headers, method="DELETE")
                    try:
                        with urllib.request.urlopen(upstream, timeout=8) as response:
                            content = response.read()
                            status = response.status
                    except urllib.error.HTTPError as error:
                        content = error.read()
                        status = error.code
                    cancel_proxy_observation.update({"upstream_status": status, "body_bytes": len(content),
                                                     "response_dropped": True})
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()

                def log_message(self, *_args):
                    pass

            proxy = ThreadingHTTPServer(("127.0.0.1", proxy_port), DropDeleteProxy)
            threading.Thread(target=proxy.serve_forever, daemon=True).start()
            delete_path = make_path(delete_template, cancel_sid, cancel_id)
            request = urllib.request.Request(
                f"http://127.0.0.1:{proxy_port}" + delete_path, method="DELETE",
                headers={"Authorization": authorization},
            )
            try:
                urllib.request.urlopen(request, timeout=5).read()
                cancel_client_error = "response unexpectedly delivered"
            except (urllib.error.URLError, OSError) as exc:
                cancel_client_error = type(exc).__name__
            proxy.shutdown()
            proxy.server_close()
            proxy = None
        cancel_post_inbox_status, cancel_post_inbox = call("GET", f"/api/session/{cancel_sid}/inbox")
        cancel_post_rows = (cancel_post_inbox or {}).get("data", [])
        hold_release[CANCEL_HOLD].set()
        cancel_messages = wait_messages(cancel_sid, lambda rows: any(
            row.get("type") == "idle" for row in rows), timeout=12)
        cancel_provider_called = CANCEL_HOLD in provider_calls and cancel_text in provider_calls
        observations["queue_delete_lost_response"] = {
            "delete_route_template": delete_template,
            "queued_prompt_status": cancel_queue_status,
            "inbox_status_before_delete": cancel_pre_inbox_status,
            "queued_id_before_delete": any(row.get("id") == cancel_id for row in cancel_pre_rows),
            "proxy_upstream_status": cancel_proxy_observation.get("upstream_status"),
            "proxy_response_body_bytes": cancel_proxy_observation.get("body_bytes"),
            "proxy_response_was_dropped": cancel_proxy_observation.get("response_dropped"),
            "caller_error_class": cancel_client_error,
            "inbox_status_after_delete": cancel_post_inbox_status,
            "queued_id_after_delete": any(row.get("id") == cancel_id for row in cancel_post_rows),
            "cancelled_id_in_transcript_after_drain": any(row.get("type") == "user" and row.get("id") == cancel_id
                                                          for row in cancel_messages),
            "cancelled_id_provider_inference": cancel_provider_called,
            "terminal_idle_outcomes": [row.get("outcome") for row in cancel_messages if row.get("type") == "idle"],
        }

        # Isolated interruption with no queued successor: record assistant
        # abort/error and terminal idle independently of the interrupt response.
        solo_sid = create("interrupt-alone")
        solo_status, solo_ack = prompt(solo_sid, "msg_solo_interrupt", INTERRUPT_HOLD)
        require(solo_status == 200 and hold_started[INTERRUPT_HOLD].wait(8), "solo interrupt provider did not hold")
        solo_busy = status_snapshot(solo_sid)
        solo_interrupt_status, solo_interrupt = call("POST", f"/api/session/{solo_sid}/interrupt")
        hold_release[INTERRUPT_HOLD].set()
        solo_messages = wait_messages(solo_sid, lambda rows: any(
            row.get("type") == "idle" and row.get("outcome") == "interrupted" for row in rows), timeout=10)
        solo_idle = next((row for row in solo_messages if row.get("type") == "idle"), {})
        solo_assistant = next((row for row in solo_messages if row.get("type") == "assistant"), {})
        observations["interrupt_terminal"] = {
            "prompt_status": solo_status,
            "prompt_id_matches_user": any(row.get("type") == "user" and row.get("id") == solo_ack.get("data", {}).get("id")
                                           for row in solo_messages),
            "status_while_provider_held": safe_status(solo_busy),
            "interrupt_http_status": solo_interrupt_status,
            "interrupt_response": solo_interrupt,
            "assistant_finish": solo_assistant.get("finish"),
            "assistant_error_type": (solo_assistant.get("error") or {}).get("type"),
            "idle_shape_keys": sorted(solo_idle),
            "idle_outcome": solo_idle.get("outcome"),
            "idle_id_equals_prompt_id": solo_idle.get("id") == solo_ack.get("data", {}).get("id"),
            "status_after_terminal": safe_status(status_snapshot(solo_sid)),
        }

        # Missing provider route yields a terminal failure without external
        # inference. Keep it separate from synthetic provider failures/retries.
        error_sid = create("no-route", "missing-provider/not-configured")
        error_status, error_ack = prompt(error_sid, "msg_no_route", "NO-ROUTE")
        error_messages = wait_messages(error_sid, lambda rows: any(
            row.get("type") == "idle" for row in rows), timeout=8)
        error_assistant = next((row for row in error_messages if row.get("type") == "assistant"), {})
        error_idle = next((row for row in error_messages if row.get("type") == "idle"), {})
        observations["no_route_terminal"] = {
            "prompt_status": error_status,
            "prompt_id_matches_user": any(row.get("type") == "user" and row.get("id") == error_ack.get("data", {}).get("id")
                                           for row in error_messages),
            "assistant_finish": error_assistant.get("finish"),
            "assistant_error_type": (error_assistant.get("error") or {}).get("type"),
            "idle_outcome": error_idle.get("outcome"),
            "idle_error_type": (error_idle.get("error") or {}).get("type"),
            "status_after_terminal": safe_status(status_snapshot(error_sid)),
        }

        # Create >50 transcript rows, paginate, then restart the exact server
        # process with the same temp XDG/data roots and verify persisted IDs.
        page_sid = create("pagination-restart")
        page_ids = []
        page_prompts = []
        for index in range(18):
            mid = f"msg_page_{index:02d}"
            text = f"PAGINATION-TURN-{index:02d}"
            status, ack = prompt(page_sid, mid, text)
            require(status == 200 and (ack or {}).get("data", {}).get("id") == mid,
                    f"pagination prompt {index} not acknowledged")
            page_ids.append(mid)
            page_prompts.append(text)
            rows = wait_messages(page_sid, lambda values, marker=text: any(
                row.get("type") == "assistant" and marker in text_of(row) for row in values), timeout=6)
            require(any(row.get("type") == "assistant" and text in text_of(row) for row in rows),
                    f"pagination reply {index} missing")

        def read_pages(sid):
            all_rows = []
            pages = []
            cursor = None
            seen = set()
            for _ in range(15):
                query = {"limit": 50}
                if cursor is not None:
                    query["cursor"] = cursor
                status, payload = call("GET", f"/api/session/{sid}/message", query=query)
                if status != 200 or not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                    pages.append({"status": status, "invalid": True})
                    break
                rows = payload["data"]
                all_rows.extend(rows)
                page_cursor = (payload.get("cursor") or {}).get("next")
                pages.append({"status": status, "row_count": len(rows), "cursor_next_present": page_cursor is not None,
                              "types": [row.get("type") for row in rows],
                              "user_ids_from_test_set": [row.get("id") for row in rows
                                  if row.get("type") == "user" and row.get("id") in page_ids]})
                if page_cursor is None:
                    break
                if not isinstance(page_cursor, str) or page_cursor in seen:
                    pages.append({"cursor_error": True})
                    break
                seen.add(page_cursor)
                cursor = page_cursor
            return pages, all_rows

        before_pages, before_rows = read_pages(page_sid)
        full_before = get_messages(page_sid).get("data", [])
        before_set = {row.get("id") for row in before_rows}
        require(all(mid in before_set for mid in page_ids), "pagination scan missed test inputs")
        before_target_page = next((page_index + 1 for page_index, page in enumerate(before_pages)
                                   if page_ids[0] in page.get("user_ids_from_test_set", [])), None)
        restart_old_port = port
        restart_info = start_server(free_port())
        require(restart_info.get("version") == "2.0.32", "restart server version mismatch")
        session_status_after_restart, session_after_restart = call("GET", f"/api/session/{page_sid}")
        after_pages, after_rows = read_pages(page_sid)
        after_full = get_messages(page_sid).get("data", [])
        after_ids = {row.get("id") for row in after_rows}
        observations["pagination_restart"] = {
            "prompt_count": len(page_ids),
            "unpaged_before_restart_count": len(full_before),
            "pages_before_restart": before_pages,
            "oldest_prompt_page_before_restart": before_target_page,
            "paged_before_count": len(before_rows),
            "paged_before_ids_unique": len(before_set) == len(before_rows),
            "unpaged_after_restart_count": len(after_full),
            "pages_after_restart": after_pages,
            "paged_after_count": len(after_rows),
            "paged_after_ids_unique": len(after_ids) == len(after_rows),
            "paged_identity_set_survived_restart": after_ids == before_set,
            "all_prompt_ids_survived_restart": all(mid in after_ids for mid in page_ids),
            "session_get_after_restart_status": session_status_after_restart,
            "session_get_envelope_keys": sorted(session_after_restart) if isinstance(session_after_restart, dict) else [],
            "status_after_restart": safe_status(status_snapshot(page_sid)),
        }

        output = {
            "server_version": info["version"],
            "status_path": status_path,
            "delete_path_template": delete_template,
            "interrupt_path_template": interrupt_template,
            "observations": observations,
            "limits": [
                "Status endpoint has session-level state only; no assertion links a busy or idle record to one specific prompt.",
                "Page and restart checks cover this temporary local data root and this server build only.",
                "Interrupt and queue-delete responses are reported separately from inbox/transcript readback.",
            ],
            "isolation": {
                "bwrap_unshare_net": True,
                "loopback_only_fake_provider": True,
                "temporary_home_xdg_sessions": True,
                "no_provider_credentials_or_real_config_read": True,
                "no_external_inference": True,
                "generated_password_recorded": False,
            },
            "provider_calls": provider_calls,
        }
        print(json.dumps(output, sort_keys=True, indent=2))
    finally:
        for event in hold_release.values():
            event.set()
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=4)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        if mock is not None:
            mock.shutdown()
            mock.server_close()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
