#!/usr/bin/env python3
"""Capture prompt, inbox, assistant, idle, failure, and interrupt shapes.

Run on devbox with:
  bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc \
    --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin \
    python3 /projects/dev/_artifacts/opencode-v2-message-shapes-probe.py

OpenCode and the synthetic OpenAI-compatible provider share a loopback-only
network namespace. A generated password and dummy local API key are not
printed. All XDG/home/session data is temporary. No credentials are read and
no real or external inference is used.
"""

import base64
import json
import pathlib
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import http.server
import urllib.error
import urllib.request


BINARY = "/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def prove_assertions_fail_closed():
    try:
        require(False, "forced negative control")
    except AssertionError as error:
        return str(error)
    raise AssertionError("forced negative control unexpectedly passed")


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def text_of(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(text_of(item) for item in value)
    if isinstance(value, dict):
        return " ".join(text_of(item) for item in value.values())
    return ""


def redact_message(message):
    if not isinstance(message, dict):
        return message
    safe = dict(message)
    if "id" in safe:
        safe["id"] = "<msg-id>"
    if "sessionID" in safe:
        safe["sessionID"] = "<session-id>"
    if "time" in safe and isinstance(safe["time"], dict):
        safe["time"] = {key: "<timestamp>" for key in safe["time"]}
    if "content" in safe and isinstance(safe["content"], list):
        safe["content"] = [redact_message(part) for part in safe["content"]]
    if "payload" in safe and isinstance(safe["payload"], dict):
        safe["payload"] = dict(safe["payload"])
    return safe


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-message-probe-", dir="/tmp"))
    mock = None
    server = None
    queue_started = threading.Event()
    queue_release = threading.Event()
    interrupt_started = threading.Event()
    interrupt_release = threading.Event()
    requests = []
    held = {"QUEUE-FIRST": False, "INTERRUPT-ME": False}
    try:
        for name in ("home", "config", "data", "state", "cache", "work"):
            (root / name).mkdir(mode=0o700)

        class FakeProvider(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", "0")))
                request = json.loads(raw)
                messages = request.get("messages", [])
                text = text_of(messages)
                case = next((
                    marker for marker in ("QUEUE-FIRST", "INTERRUPT-ME", "FAIL-503", "SUCCESS-ME")
                    if marker in text
                ), "OTHER")
                requests.append(case)
                if case == "QUEUE-FIRST" and not held[case]:
                    held[case] = True
                    queue_started.set()
                    queue_release.wait(8)
                if case == "INTERRUPT-ME" and not held[case]:
                    held[case] = True
                    interrupt_started.set()
                    interrupt_release.wait(8)
                if case == "FAIL-503":
                    body = json.dumps({"error": {"message": "synthetic provider failure"}}).encode()
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                chunks = [
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0,
                         "delta": {"role": "assistant", "content": "Synthetic response."},
                         "finish_reason": None}]},
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

        mock = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), FakeProvider)
        threading.Thread(target=mock.serve_forever, daemon=True).start()
        work = root / "work"
        (work / "opencode.json").write_text(json.dumps({
            "model": "mock/fake",
            "provider": {
                "mock": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Loopback synthetic provider",
                    "options": {
                        "baseURL": f"http://127.0.0.1:{mock.server_address[1]}/v1",
                        "apiKey": "synthetic-only",
                    },
                    "models": {
                        "fake": {"name": "Fake", "tool_call": True,
                                 "limit": {"context": 128000, "output": 4096}}
                    },
                }
            },
        }), encoding="utf-8")

        port = free_port()
        password = secrets.token_urlsafe(32)
        authorization = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
        env = {
            "PATH": "/run/current-system/sw/bin:/usr/bin:/bin",
            "HOME": str(root / "home"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "OPENCODE_SERVER_PASSWORD": password,
        }
        server = subprocess.Popen(
            [BINARY, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
            env=env, cwd=str(work), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"

        def call(method, path, body=None):
            request = urllib.request.Request(
                base + path, method=method,
                data=None if body is None else json.dumps(body).encode(),
                headers={"content-type": "application/json", "authorization": authorization},
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    raw = response.read()
                    return response.status, json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                try:
                    return error.code, json.loads(error.read())
                except Exception:
                    return error.code, None

        def wait_idle(session_id, count=1, timeout=8):
            deadline = time.time() + timeout
            messages = []
            while time.time() < deadline:
                result = call("GET", f"/api/session/{session_id}/message")[1]
                messages = result.get("data", []) if isinstance(result, dict) else []
                if sum(item.get("type") == "idle" for item in messages) >= count:
                    break
                time.sleep(0.1)
            return messages

        def create_session(title, model=None):
            status, result = call("POST", "/api/session", {
                "title": title,
                "location": {"directory": str(work)},
                "model": model or {"id": "fake", "providerID": "mock"},
                "agent": "build",
                "permissions": [{"action": "*", "resource": "*", "effect": "allow"}],
            })
            if status != 200:
                raise RuntimeError(f"session create returned {status}")
            return result["data"]["id"]

        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError("OpenCode exited before readiness")
            try:
                if call("GET", "/openapi.json")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(0.1)
        openapi = call("GET", "/openapi.json")[1]
        schemas = openapi["components"]["schemas"]

        # Successful input with assistant text and terminal idle.
        sid = create_session("success")
        prompt_status, prompt = call("POST", f"/api/session/{sid}/prompt", {"text": "SUCCESS-ME"})
        prompt_id = prompt["data"]["id"]
        messages = wait_idle(sid)
        user = next(item for item in messages if item.get("type") == "user")
        assistant = next(item for item in messages if item.get("type") == "assistant")
        idle = next(item for item in messages if item.get("type") == "idle")
        success_idle_linkage = {
            "user_id_matches_prompt": user.get("id") == prompt_id,
            "idle_id_equals_prompt": idle.get("id") == prompt_id,
            "idle_fields": sorted(idle.keys()),
        }
        success = {
            "prompt_status": prompt_status,
            "prompt_response": redact_message(prompt["data"]),
            "transcript_user": redact_message(user),
            "assistant": redact_message(assistant),
            "idle": redact_message(idle),
            **success_idle_linkage,
            "idle_keys": sorted(idle.keys()),
        }
        require(prompt_status == 200, "success prompt POST was not accepted")
        require(success_idle_linkage["user_id_matches_prompt"], "success transcript user ID differed from prompt response")
        require(idle.get("outcome") == "succeeded", "success control did not reach succeeded idle")
        require(success_idle_linkage["idle_id_equals_prompt"] is False, "idle unexpectedly reused prompt ID")

        # Hold first provider response, queue a second message, and read inbox.
        queue_sid = create_session("queue")
        first_status, _first = call("POST", f"/api/session/{queue_sid}/prompt", {"text": "QUEUE-FIRST"})
        queue_model_started = queue_started.wait(5)
        require(queue_model_started, "queue first model request did not reach the local fake provider")
        queued_status, queued = call("POST", f"/api/session/{queue_sid}/prompt", {
            "text": "queued-next", "delivery": "queue",
        })
        inbox_status, inbox = call("GET", f"/api/session/{queue_sid}/inbox")
        queue_release.set()
        queue_messages = wait_idle(queue_sid, timeout=8)
        queued_id = queued.get("data", {}).get("id")
        inbox_data = inbox.get("data", []) if isinstance(inbox, dict) else []
        queue_observation = {
            "first_prompt_status": first_status,
            "queued_prompt_status": queued_status,
            "queued_prompt": redact_message(queued["data"]),
            "inbox_status_while_active": inbox_status,
            "inbox_while_active": [redact_message(item) for item in inbox_data],
            "queued_id_matches_inbox_entry": bool(inbox_data and inbox_data[0].get("id") == queued_id),
            "queued_id_matches_transcript_user": any(
                item.get("type") == "user" and item.get("id") == queued_id for item in queue_messages
            ),
            "message_types_after_drain": [item.get("type") for item in queue_messages],
            "idle_count_after_drain": sum(item.get("type") == "idle" for item in queue_messages),
            "idle_id_equals_queued_prompt_id": any(
                item.get("type") == "idle" and item.get("id") == queued_id for item in queue_messages
            ),
        }
        require(first_status == 200 and queued_status == 200, "queue prompt POST failed")
        require(inbox_status == 200 and len(inbox_data) == 1, "busy inbox did not contain exactly the queued item")
        require(queue_observation["queued_id_matches_inbox_entry"], "queued prompt and inbox IDs differ")
        require(queue_observation["queued_id_matches_transcript_user"], "queued prompt and transcript user IDs differ")
        require(queue_observation["idle_count_after_drain"] == 1, "queued sequence did not emit the observed single idle event")

        # Interrupt while a synthetic local model response is held.
        interrupt_sid = create_session("interrupt")
        interrupt_status, interrupt_prompt = call("POST", f"/api/session/{interrupt_sid}/prompt", {
            "text": "INTERRUPT-ME",
        })
        interrupt_model_started = interrupt_started.wait(5)
        require(interrupt_model_started, "interrupt model request did not reach the local fake provider")
        active_before = call("GET", "/api/session/active")
        interrupt_response = call("POST", f"/api/session/{interrupt_sid}/interrupt")
        interrupt_release.set()
        interrupt_messages = wait_idle(interrupt_sid, timeout=8)
        interrupt_prompt_id = interrupt_prompt["data"]["id"]
        interrupted_idle = next(item for item in interrupt_messages if item.get("type") == "idle")
        interrupted_assistant = next(item for item in interrupt_messages if item.get("type") == "assistant")
        interruption = {
            "prompt_status": interrupt_status,
            "active_before": {"status": active_before[0], "contains_session": interrupt_sid in active_before[1].get("data", {})},
            "interrupt_response": interrupt_response[1],
            "assistant": redact_message(interrupted_assistant),
            "idle": redact_message(interrupted_idle),
            "idle_id_equals_prompt_response_id": interrupted_idle.get("id") == interrupt_prompt_id,
        }
        require(interrupt_status == 200, "interrupt prompt POST was not accepted")
        require(interruption["active_before"]["contains_session"], "session was not active before interrupt")
        require(interruption["interrupt_response"].get("interrupted") is True, "interrupt endpoint did not interrupt")
        require(interrupted_assistant.get("error", {}).get("type") == "aborted", "interrupted assistant lacked aborted error")
        require(interrupted_idle.get("outcome") == "interrupted", "interrupt control did not emit interrupted idle")
        require(interruption["idle_id_equals_prompt_response_id"] is False, "interrupted idle reused prompt ID")

        # Unknown model route produces a terminal failure without any provider network.
        failure_sid = create_session("no-route", {"id": "not-configured", "providerID": "missing-provider"})
        failure_status, failure_prompt = call("POST", f"/api/session/{failure_sid}/prompt", {"text": "NO-ROUTE"})
        failure_messages = wait_idle(failure_sid, timeout=6)
        failure_idle = next(item for item in failure_messages if item.get("type") == "idle")
        failure = {
            "prompt_status": failure_status,
            "transcript_user_id_matches_prompt_response": any(
                item.get("type") == "user" and item.get("id") == failure_prompt["data"]["id"]
                for item in failure_messages
            ),
            "idle": redact_message(failure_idle),
            "idle_id_equals_prompt_response_id": failure_idle.get("id") == failure_prompt["data"]["id"],
        }
        require(failure_status == 200, "no-route prompt POST was not accepted")
        require(failure["transcript_user_id_matches_prompt_response"], "no-route transcript user ID differed from prompt response")
        require(failure_idle.get("outcome") == "failed", "no-route model did not emit failed idle")
        require(failure_idle.get("error", {}).get("type") == "provider.no-route", "failure was not the expected no-route error")
        require(failure["idle_id_equals_prompt_response_id"] is False, "failed idle reused prompt ID")

        # A transient provider 503 is not necessarily terminal within the first poll window.
        retry_sid = create_session("retry")
        retry_status, _retry_prompt = call("POST", f"/api/session/{retry_sid}/prompt", {"text": "FAIL-503"})
        retry_messages = wait_idle(retry_sid, timeout=8)
        retry_assistant = next((item for item in retry_messages if item.get("type") == "assistant"), {})
        retry_idle = next((item for item in retry_messages if item.get("type") == "idle"), None)
        retry_observation = {
            "prompt_status": retry_status,
            "provider_requests": requests.count("FAIL-503"),
            "terminal_idle_seen_within_8s": retry_idle is not None,
            "assistant_retry": redact_message(retry_assistant),
        }
        require(retry_status == 200, "503 retry prompt POST was not accepted")
        require(retry_observation["provider_requests"] > 0, "fake provider did not receive the 503 case")
        require(retry_idle is None, "503 was expected to remain retrying during the bounded observation window")
        require(retry_assistant.get("retry", {}).get("attempt", 0) > 0, "503 retry assistant event missing retry attempt")

        selected_schemas = {
            name: schemas[name] for name in (
                "Session.Message.User", "Session.Message.Assistant", "Session.Message.Idle",
                "Session.Inbox.User", "Session.Inbox.UserPayload", "Session.StructuredError",
                "Session.Message.Assistant.Tool", "Session.Message.ToolState.Completed",
                "Session.Message.ToolState.Error",
            ) if name in schemas
        }
        idle_schema_keys = set(schemas["Session.Message.Idle"].get("properties", {}))
        linkage_names = {"inputid", "messageid", "promptid"}
        observed_idle_link_keys = sorted(
            key for key in idle.keys() if key.lower() in linkage_names
        )
        schema_idle_link_keys = sorted(key for key in idle_schema_keys if key.lower() in linkage_names)
        input_linkage = {
            "success_user_id_matches_prompt_response": success_idle_linkage["user_id_matches_prompt"],
            "queued_user_id_matches_prompt_and_inbox": (
                queue_observation["queued_id_matches_transcript_user"]
                and queue_observation["queued_id_matches_inbox_entry"]
            ),
            "interrupted_idle_id_equals_prompt_response": interruption["idle_id_equals_prompt_response_id"],
            "failed_idle_id_equals_prompt_response": failure["idle_id_equals_prompt_response_id"],
            "observed_idle_prompt_link_fields": observed_idle_link_keys,
            "schema_idle_prompt_link_fields": schema_idle_link_keys,
            "sampled_idle_ids_distinct_from_inputs": all((
                success_idle_linkage["idle_id_equals_prompt"] is False,
                queue_observation["idle_id_equals_queued_prompt_id"] is False,
                interruption["idle_id_equals_prompt_response_id"] is False,
                failure["idle_id_equals_prompt_response_id"] is False,
            )),
        }
        require(input_linkage["success_user_id_matches_prompt_response"], "success prompt ID linkage failed")
        require(input_linkage["queued_user_id_matches_prompt_and_inbox"], "queued prompt/inbox/transcript linkage failed")
        require(input_linkage["sampled_idle_ids_distinct_from_inputs"], "one idle reused an input ID")
        require(not input_linkage["observed_idle_prompt_link_fields"], "unexpected observed idle input-link field")
        require(not input_linkage["schema_idle_prompt_link_fields"], "unexpected typed idle input-link field in schema")
        negative_control_error = prove_assertions_fail_closed()

        print(json.dumps({
            "version": "2.0.32",
            "external_network": False,
            "schemas": selected_schemas,
            "success": success,
            "queue": queue_observation,
            "interruption": interruption,
            "no_route_failure": failure,
            "provider_503_retry": retry_observation,
            "input_linkage": input_linkage,
            "assertions": {
                "all_expected_controls_passed": True,
                "forced_negative_control": negative_control_error,
            },
        }, sort_keys=True, indent=2))
    finally:
        queue_release.set()
        interrupt_release.set()
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
