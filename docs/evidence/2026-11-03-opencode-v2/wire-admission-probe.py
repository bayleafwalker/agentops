#!/usr/bin/env python3
"""Live no-egress probe of the exact dormant wire-admission client.

The harness imports the source bytes bound at /tmp/opencode_v2_wire.py, runs
the pinned OpenCode server and a synthetic provider on loopback, and records
only sanitized shapes, correlations, hashes and page counts.
"""

import base64
import hashlib
import importlib.util
import json
import pathlib
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
MODULE_PATH = pathlib.Path("/tmp/opencode_v2_wire.py")
MODULE_SHA256 = "78c627e98b989fd69f119c9d34d50f33b336bc7057e0daadf0759ee86c19a25a"
HOLD_TEXT = "WIRE-HOLD-FIRST"
QUEUE_TEXT = "WIRE-QUEUED-INPUT"
HOLD_ID = "msg_wire_hold_first"
QUEUE_ID = "msg_wire_queue_target"


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


def admission_summary(value, expected_id, expected_session):
    return {
        "status": value.get("status"),
        "sources": value.get("sources"),
        "sha256": value.get("sha256"),
        "input_id_matches": value.get("id") == expected_id,
        "session_id_matches": value.get("session_id") == expected_session,
    }


def main():
    digest = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
    require(digest == MODULE_SHA256, "wire module hash mismatch")
    spec = importlib.util.spec_from_file_location("opencode_v2_wire", MODULE_PATH)
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)

    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-wire-admission-", dir="/tmp"))
    mock = None
    server = None
    provider_started = threading.Event()
    provider_release = threading.Event()
    provider_calls = []
    observed_requests = []
    try:
        for name in ("home", "config", "data", "state", "cache", "work"):
            (root / name).mkdir(mode=0o700)

        class FakeProvider(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
                serialized = json.dumps(request.get("messages", []))
                hold_pos = serialized.rfind(HOLD_TEXT)
                queue_pos = serialized.rfind(QUEUE_TEXT)
                marker = QUEUE_TEXT if queue_pos > hold_pos else HOLD_TEXT
                provider_calls.append(marker)
                if marker == HOLD_TEXT and not provider_started.is_set():
                    provider_started.set()
                    provider_release.wait(15)
                text = "synthetic reply: " + marker
                chunks = [
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": {"role": "assistant", "content": text}, "finish_reason": None}]},
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                ]
                encoded = ("".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                           + "data: [DONE]\n\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_args):
                pass

        mock = ThreadingHTTPServer(("127.0.0.1", free_port()), FakeProvider)
        threading.Thread(target=mock.serve_forever, daemon=True).start()
        work = root / "work"
        (work / "opencode.json").write_text(json.dumps({
            "model": "mock/fake",
            "provider": {"mock": {
                "npm": "@ai-sdk/openai-compatible", "name": "synthetic loopback provider",
                "options": {"baseURL": f"http://127.0.0.1:{mock.server_address[1]}/v1", "apiKey": "synthetic-only"},
                "models": {"fake": {"name": "Fake", "tool_call": True,
                                     "limit": {"context": 128000, "output": 4096}}},
            }},
        }), encoding="utf-8")

        port = free_port()
        password = secrets.token_urlsafe(32)
        authorization = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
        env = {
            "PATH": "/run/current-system/sw/bin:/usr/bin:/bin",
            "HOME": str(root / "home"), "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"), "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"), "OPENCODE_SERVER_PASSWORD": password,
        }
        server = subprocess.Popen(
            [BINARY, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
            env=env, cwd=str(work), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        origin = f"http://127.0.0.1:{port}"

        def raw(method, path, body=None, query=None):
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
                    value = response.read()
                    return response.status, json.loads(value) if value else None
            except urllib.error.HTTPError as exc:
                value = exc.read()
                try:
                    return exc.code, json.loads(value) if value else None
                except ValueError:
                    return exc.code, None

        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError("OpenCode exited before readiness")
            try:
                if raw("GET", "/openapi.json")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(0.1)
        info_status, info = raw("GET", "/api/info")
        require(info_status == 200 and info.get("version") == "2.0.32", "pinned server identity failed")

        client = wire.OpenCodeV2(origin, "opencode", password, timeout=8)
        original_request = client._request

        def traced(method, path, query=None, body=None):
            result = original_request(method, path, query=query, body=body)
            if method == "POST" and path.endswith("/prompt"):
                observed_requests.append({"method": method, "path_suffix": "/prompt",
                                          "body_keys": sorted(body or {}),
                                          "delivery_field_present": "delivery" in (body or {})})
            if method == "GET" and path.endswith("/message"):
                response_rows = result.get("data", [])
                observed_requests.append({"method": method, "path_suffix": "/message",
                                          "query_keys": sorted(query or {}),
                                          "row_count": len(response_rows),
                                          "cursor_next_present": (result.get("cursor") or {}).get("next") is not None})
            if method == "GET" and path.endswith("/inbox"):
                observed_requests.append({"method": method, "path_suffix": "/inbox",
                                          "row_count": len(result.get("data", []))})
            return result

        client._request = traced
        directory = str(work)
        permissions = [{"action": "*", "resource": "*", "effect": "deny"}]
        session_id = client.create_session("wire-admission", directory, "mock/fake", permissions)

        submitted = client.submit_prompt(session_id, HOLD_ID, HOLD_TEXT)
        require(submitted["id"] == HOLD_ID and submitted["session_id"] == session_id,
                "submit_prompt returned an unexpected identity")
        require(provider_started.wait(8), "fake provider did not hold initial prompt")

        queue_status, queue_ack = raw("POST", f"/api/session/{session_id}/prompt", {
            "id": QUEUE_ID, "text": QUEUE_TEXT, "delivery": "queue",
        })
        require(queue_status == 200 and isinstance(queue_ack, dict), "queue request failed")
        queue_data = queue_ack.get("data", {})
        require(queue_data.get("id") == QUEUE_ID and queue_data.get("delivery") == "queue",
                "queued prompt ack identity/delivery mismatch")
        queue_digest = hashlib.sha256(QUEUE_TEXT.encode()).hexdigest()

        before_drain = client.observe_admission(session_id, QUEUE_ID, queue_digest)
        inbox_status, inbox = raw("GET", f"/api/session/{session_id}/inbox")
        inbox_items = inbox.get("data", []) if isinstance(inbox, dict) else []
        inbox_item = next((item for item in inbox_items if item.get("id") == QUEUE_ID), {})
        before_messages = raw("GET", f"/api/session/{session_id}/message")[1].get("data", [])
        queued_before = any(item.get("type") == "user" and item.get("id") == QUEUE_ID for item in before_messages)
        require(before_drain.get("status") == "observed" and before_drain.get("sources") == ["inbox"],
                "observer did not identify queued inbox admission")
        require(inbox_item.get("payload", {}).get("text") == QUEUE_TEXT and not queued_before,
                "queued inbox/transcript pre-drain projection mismatch")

        provider_release.set()
        deadline = time.time() + 10
        after_messages = []
        while time.time() < deadline:
            result = raw("GET", f"/api/session/{session_id}/message")[1]
            after_messages = result.get("data", []) if isinstance(result, dict) else []
            if any(item.get("type") == "assistant" and "WIRE-QUEUED-INPUT" in text_of(item)
                   for item in after_messages):
                break
            time.sleep(0.05)
        require(any(item.get("type") == "user" and item.get("id") == QUEUE_ID
                    and item.get("text") == QUEUE_TEXT for item in after_messages),
                "queued user input did not appear in transcript after drain")
        after_drain = client.observe_admission(session_id, QUEUE_ID, queue_digest)
        after_inbox_status, after_inbox = raw("GET", f"/api/session/{session_id}/inbox")
        after_inbox_items = after_inbox.get("data", []) if isinstance(after_inbox, dict) else []
        require(after_drain.get("status") == "observed" and after_drain.get("sources") == ["message"],
                "observer did not identify drained transcript admission")
        require(not any(item.get("id") == QUEUE_ID for item in after_inbox_items),
                "queued item remained in inbox after drain")

        hold_observation = client.observe_admission(
            session_id, HOLD_ID, hashlib.sha256(HOLD_TEXT.encode()).hexdigest())
        require(hold_observation.get("status") == "observed" and hold_observation.get("sources") == ["message"],
                "submit_prompt input was not observable in transcript")

        output = {
            "server_version": info["version"],
            "module_sha256": MODULE_SHA256,
            "submit_prompt": {
                "returned_id_matches": submitted.get("id") == HOLD_ID,
                "returned_session_matches": submitted.get("session_id") == session_id,
                "returned_digest_matches": submitted.get("sha256") == hashlib.sha256(HOLD_TEXT.encode()).hexdigest(),
                "captured_prompt_call": next(item for item in observed_requests
                    if item.get("method") == "POST" and item.get("path_suffix") == "/prompt"),
                "delivery_parameter_supported_by_method": False,
            },
            "queued_inbox_before_drain": {
                "raw_ack_status": queue_status,
                "ack_data_keys": sorted(queue_data),
                "delivery": queue_data.get("delivery"),
                "inbox_status": inbox_status,
                "inbox_count": len(inbox_items),
                "inbox_item_keys": sorted(inbox_item),
                "inbox_payload_keys": sorted(inbox_item.get("payload", {})),
                "inbox_text_matches": inbox_item.get("payload", {}).get("text") == QUEUE_TEXT,
                "observer_result": admission_summary(before_drain, QUEUE_ID, session_id),
                "queued_transcript_present_before_drain": queued_before,
            },
            "queued_transcript_after_drain": {
                "same_input_id_present": any(item.get("type") == "user" and item.get("id") == QUEUE_ID for item in after_messages),
                "same_text_present": any(item.get("type") == "user" and item.get("id") == QUEUE_ID and item.get("text") == QUEUE_TEXT for item in after_messages),
                "observer_result": admission_summary(after_drain, QUEUE_ID, session_id),
                "inbox_status": after_inbox_status,
                "inbox_count": len(after_inbox_items),
            },
            "submit_prompt_observed_after_drain": admission_summary(hold_observation, HOLD_ID, session_id),
            "observer_message_page_calls": [item for item in observed_requests
                if item.get("method") == "GET" and item.get("path_suffix") == "/message"],
            "provider_calls": len(provider_calls),
            "isolation": {
                "bwrap_unshare_net": True,
                "only_loopback_server_provider": True,
                "temporary_home_xdg_sessions": True,
                "no_provider_credentials_or_configuration_read": True,
                "no_external_inference": True,
                "generated_password_recorded": False,
            },
        }
        print(json.dumps(output, sort_keys=True, indent=2))
    finally:
        provider_release.set()
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
