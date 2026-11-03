#!/usr/bin/env python3
"""Probe prompt admission and projections against disposable OpenCode 2.0.32.

Run on devbox with this script on stdin inside bwrap --unshare-net. The fake
provider and server bind only loopback; all credentials/config are generated in
a temporary tree. No prompt invokes tools and no external inference is used.
"""

import base64
import http.client
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
MARKERS = ["PROMPT-SUCCESS", "DELAY-HOLD", "DELAY-QUEUED", "PAGE-0", "PAGE-1", "PAGE-2", "PAGE-3", "LOSS-ACK"]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def message_text(message):
    parts = message.get("content", [])
    if isinstance(parts, str):
        return parts
    found = []
    def visit(value):
        if isinstance(value, dict):
            if isinstance(value.get("text"), str):
                found.append(value["text"])
            for key, nested in value.items():
                if key != "text":
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)
    visit(parts)
    if message.get("type") == "user" and isinstance(message.get("text"), str):
        found.append(message["text"])
    if message.get("type") == "user" and isinstance((message.get("payload") or {}).get("text"), str):
        found.append(message["payload"]["text"])
    return " ".join(found)


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-prompt-admission-", dir="/tmp"))
    mock = None
    server = None
    proxy = None
    hold_started = {"DELAY-HOLD": threading.Event(), "LOSS-ACK": threading.Event()}
    hold_release = {"DELAY-HOLD": threading.Event(), "LOSS-ACK": threading.Event()}
    provider_calls = []
    proxy_observation = {}
    try:
        for name in ("home", "config", "data", "state", "cache", "work"):
            (root / name).mkdir(mode=0o700)

        class FakeProvider(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
                serialized = json.dumps(request.get("messages", []))
                positions = [(serialized.rfind(marker), marker) for marker in MARKERS if marker in serialized]
                marker = max(positions)[1] if positions else "OTHER"
                provider_calls.append(marker)
                if marker in hold_started and not hold_started[marker].is_set():
                    hold_started[marker].set()
                    hold_release[marker].wait(15)
                content = "synthetic reply: " + marker
                chunks = [
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": {"role": "assistant", "content": content}, "finish_reason": None}]},
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
                ]
                body = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                encoded = (body + "data: [DONE]\n\n").encode()
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
        auth = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
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

        def call_at(base, method, path, body=None, query=None):
            url = base + path
            if query:
                url += "?" + urllib.parse.urlencode(query)
            request = urllib.request.Request(
                url, method=method,
                data=None if body is None else json.dumps(body).encode(),
                headers={"Authorization": auth, "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    raw = response.read()
                    return response.status, json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                try:
                    raw = error.read()
                    return error.code, json.loads(raw) if raw else None
                except Exception:
                    return error.code, None

        def call(method, path, body=None, query=None):
            return call_at(origin, method, path, body, query)

        def create(title):
            status, response = call("POST", "/api/session", {
                "title": title, "location": {"directory": str(work)},
                "model": {"providerID": "mock", "id": "fake"},
                "agent": "build", "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
            })
            require(status == 200, "synthetic session create failed")
            return response["data"]["id"]

        def messages(sid, query=None):
            status, response = call("GET", f"/api/session/{sid}/message", query=query)
            require(status == 200 and isinstance(response, dict), "message read failed")
            return response

        def wait_for(sid, predicate, timeout=8):
            deadline = time.time() + timeout
            latest = []
            while time.time() < deadline:
                latest = messages(sid).get("data", [])
                if predicate(latest):
                    return latest
                time.sleep(0.04)
            return latest

        def prompt(sid, text, extra=None):
            body = {"text": text}
            if extra:
                body.update(extra)
            status, response = call("POST", f"/api/session/{sid}/prompt", body)
            return status, response

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
        require(openapi is not None, "OpenAPI unavailable")
        info_status, info = call("GET", "/api/info")
        require(info_status == 200 and info.get("version") == "2.0.32", "pinned server version check failed")
        server_version = info["version"]
        paths = openapi["paths"]
        prompt_schema = paths["/api/session/{sessionID}/prompt"]["post"]
        prompt_body_schema = prompt_schema["requestBody"]["content"]["application/json"]["schema"]
        prompt_fields = sorted(prompt_body_schema.get("properties", {}))
        prompt_response_schema = prompt_schema["responses"]["200"]["content"]["application/json"]["schema"]
        inbox_response_schema = paths["/api/session/{sessionID}/inbox"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        message_response_schema = paths["/api/session/{sessionID}/message"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        message_parameters = [parameter.get("name") for parameter in paths["/api/session/{sessionID}/message"]["get"].get("parameters", [])]

        # Basic prompt request/ack and transcript projection.
        success_sid = create("prompt-success")
        success_status, success_ack = prompt(success_sid, "PROMPT-SUCCESS")
        success_data = success_ack.get("data", {})
        success_id = success_data.get("id")
        success_messages = wait_for(success_sid, lambda rows: any(
            item.get("type") == "assistant" and "PROMPT-SUCCESS" in message_text(item)
            for item in rows))
        success_user = next((item for item in success_messages if item.get("type") == "user" and item.get("id") == success_id), {})
        success_inbox_status, success_inbox = call("GET", f"/api/session/{success_sid}/inbox")

        # Meaningful negative control: omit required text and prove rejection
        # did not add any transcript row.
        before_invalid_ids = [item.get("id") for item in success_messages]
        invalid_status, invalid_response = call(
            "POST", f"/api/session/{success_sid}/prompt", {"delivery": "steer"})
        after_invalid_messages = messages(success_sid).get("data", [])
        invalid_no_admission = [item.get("id") for item in after_invalid_messages] == before_invalid_ids
        require(400 <= invalid_status < 500, "missing-text prompt was not rejected")
        require(invalid_no_admission, "rejected prompt changed the transcript")

        # Hold model inference to sample projections before drain and after drain.
        delayed_sid = create("delayed-projection")
        first_status, first_ack = prompt(delayed_sid, "DELAY-HOLD")
        require(hold_started["DELAY-HOLD"].wait(8), "fake provider did not hold first turn")
        queued_status, queued_ack = prompt(delayed_sid, "DELAY-QUEUED", {"delivery": "queue"})
        queued_data = queued_ack.get("data", {})
        immediate_inbox_status, immediate_inbox = call("GET", f"/api/session/{delayed_sid}/inbox")
        immediate_messages = messages(delayed_sid).get("data", [])
        queued_id = queued_data.get("id")
        inbox_items = immediate_inbox.get("data", []) if isinstance(immediate_inbox, dict) else []
        immediate_queued_transcript = any(item.get("type") == "user" and item.get("id") == queued_id for item in immediate_messages)
        immediate_queued_inbox = any(item.get("id") == queued_id for item in inbox_items)
        projection_started = time.monotonic()
        queued_transcript_first_seen_ms = 0 if immediate_queued_transcript else None
        queued_inbox_first_seen_ms = 0 if immediate_queued_inbox else None
        while time.monotonic() - projection_started < 1.0:
            current_messages = messages(delayed_sid).get("data", [])
            current_inbox = call("GET", f"/api/session/{delayed_sid}/inbox")[1]
            elapsed_ms = round((time.monotonic() - projection_started) * 1000, 1)
            if queued_transcript_first_seen_ms is None and any(
                    item.get("type") == "user" and item.get("id") == queued_id for item in current_messages):
                queued_transcript_first_seen_ms = elapsed_ms
            current_inbox_items = current_inbox.get("data", []) if isinstance(current_inbox, dict) else []
            if queued_inbox_first_seen_ms is None and any(item.get("id") == queued_id for item in current_inbox_items):
                queued_inbox_first_seen_ms = elapsed_ms
            if queued_transcript_first_seen_ms is not None and queued_inbox_first_seen_ms is not None:
                break
            time.sleep(0.03)
        hold_release["DELAY-HOLD"].set()
        drained_messages = wait_for(delayed_sid, lambda rows: any(
            item.get("type") == "assistant" and "DELAY-QUEUED" in message_text(item)
            for item in rows))
        drained_user = next((item for item in drained_messages if item.get("type") == "user" and item.get("id") == queued_id), {})
        drained_inbox_status, drained_inbox = call("GET", f"/api/session/{delayed_sid}/inbox")
        inbox_after = (immediate_inbox or {}).get("data", [])
        inbox_item = next((item for item in inbox_after if item.get("id") == queued_id), {})

        # Several turns create >2 transcript rows for pagination observations.
        page_sid = create("message-pagination")
        page_ack_ids = {}
        for marker in ("PAGE-0", "PAGE-1", "PAGE-2", "PAGE-3"):
            status, ack = prompt(page_sid, marker)
            require(status == 200 and isinstance(ack, dict), "pagination prompt was not acknowledged")
            page_ack_ids[marker] = ack["data"]["id"]
            rows = wait_for(page_sid, lambda all_rows, m=marker: any(
                item.get("type") == "assistant" and ("synthetic reply: " + m) in message_text(item)
                for item in all_rows))
            require(any(item.get("type") == "assistant" and ("synthetic reply: " + marker) in message_text(item) for item in rows),
                    "fake provider reply did not appear")
        full_page_read = messages(page_sid)
        full_rows = full_page_read.get("data", [])
        paged_rows = []
        page_summaries = []
        page_cursor = None
        cursor_seen = set()
        for _ in range(30):
            query = {"limit": 2}
            if page_cursor is not None:
                query["cursor"] = page_cursor
            status, response = call("GET", f"/api/session/{page_sid}/message", query=query)
            if status != 200 or not isinstance(response, dict) or not isinstance(response.get("data"), list):
                page_summaries.append({"status": status, "invalid_page": True})
                break
            batch = response["data"]
            paged_rows.extend(batch)
            cursor = response.get("cursor") or {}
            page_summaries.append({
                "status": status, "count": len(batch),
                "types": [item.get("type") for item in batch],
                "user_texts": [message_text(item) for item in batch if item.get("type") == "user"],
                "ack_id_matches": [any(item.get("type") == "user" and item.get("id") == input_id for item in batch)
                                   for input_id in page_ack_ids.values()],
                "cursor_keys": sorted(cursor),
                "next_present": cursor.get("next") is not None,
            })
            page_cursor = cursor.get("next")
            if page_cursor is None:
                break
            if not isinstance(page_cursor, str) or page_cursor in cursor_seen:
                page_summaries.append({"cursor_error": "missing or repeated next cursor"})
                break
            cursor_seen.add(page_cursor)
        full_ids = [item.get("id") for item in full_rows]
        paged_ids = [item.get("id") for item in paged_rows]
        pagination = {
            "unpaged_count": len(full_rows),
            "unpaged_types": [item.get("type") for item in full_rows],
            "unpaged_user_texts": [message_text(item) for item in full_rows if item.get("type") == "user"],
            "message_shape_keys_by_type": {
                kind: sorted(next(item for item in full_rows if item.get("type") == kind))
                for kind in sorted({item.get("type") for item in full_rows})
                if any(item.get("type") == kind for item in full_rows)
            },
            "prompt_ack_user_id_matches": {
                marker: any(item.get("type") == "user" and item.get("id") == input_id for item in full_rows)
                for marker, input_id in page_ack_ids.items()
            },
            "pages": page_summaries,
            "paged_count": len(paged_rows),
            "unpaged_envelope_keys": sorted(full_page_read),
            "unpaged_cursor_keys": sorted(full_page_read.get("cursor", {})),
            "paged_ids_unique": len(set(paged_ids)) == len(paged_ids),
            "paged_identity_set_matches_unpaged": set(paged_ids) == set(full_ids),
            "pagination_param_names": message_parameters,
        }

        # Drop the client response only after upstream accepted it. Preassign an
        # optional input ID so we can observe correlation despite lost ack.
        loss_sid = create("lost-ack")
        proxy_port = free_port()

        class DropAckProxy(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _forward(self):
                method = self.command
                path = self.path
                body = self.rfile.read(int(self.headers.get("content-length", "0")))
                headers = {key: value for key, value in self.headers.items()
                           if key.lower() not in ("host", "content-length", "connection")}
                upstream = urllib.request.Request(origin + path, data=body or None, headers=headers, method=method)
                try:
                    with urllib.request.urlopen(upstream, timeout=8) as response:
                        upstream_body = response.read()
                        status = response.status
                        content_type = response.headers.get("Content-Type", "application/json")
                except urllib.error.HTTPError as error:
                    upstream_body = error.read()
                    status = error.code
                    content_type = error.headers.get("Content-Type", "application/json")
                if path.endswith("/prompt"):
                    try:
                        ack_data = json.loads(upstream_body).get("data", {})
                    except Exception:
                        ack_data = {}
                    proxy_observation.update({"request_count": proxy_observation.get("request_count", 0) + 1,
                                              "upstream_status": status,
                                              "upstream_body_bytes": len(upstream_body),
                                              "upstream_ack_data_keys": sorted(ack_data),
                                              "upstream_ack_delivery": ack_data.get("delivery"),
                                              "upstream_ack_id_matches_supplied": ack_data.get("id") == lost_input_id,
                                              "upstream_ack_payload_text": (ack_data.get("payload") or {}).get("text"),
                                              "response_dropped": True})
                    self.close_connection = True
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.connection.close()
                    return
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(upstream_body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(upstream_body)

            def do_GET(self):
                self._forward()

            def do_POST(self):
                self._forward()

            def log_message(self, *_args):
                pass

        proxy = ThreadingHTTPServer(("127.0.0.1", proxy_port), DropAckProxy)
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        lost_input_id = "msg_probe_response_loss"
        try:
            call_at(f"http://127.0.0.1:{proxy_port}", "POST", f"/api/session/{loss_sid}/prompt",
                    {"id": lost_input_id, "text": "LOSS-ACK"})
            loss_client_failure = "unexpected response returned"
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            loss_client_failure = type(exc).__name__
        require(hold_started["LOSS-ACK"].wait(8), "lost-ack prompt did not reach fake provider")
        immediate_loss_messages = messages(loss_sid).get("data", [])
        immediate_loss_user = next((item for item in immediate_loss_messages
                                    if item.get("type") == "user" and item.get("id") == lost_input_id), {})
        hold_release["LOSS-ACK"].set()
        drained_loss_messages = wait_for(loss_sid, lambda rows: any(
            item.get("type") == "assistant" and "LOSS-ACK" in message_text(item)
            for item in rows))
        lost_user_count = sum(item.get("type") == "user" and item.get("id") == lost_input_id
                              for item in drained_loss_messages)

        provider_calls_before_retry = len(provider_calls)
        retry_status, retry_ack = prompt(loss_sid, "LOSS-ACK", {"id": lost_input_id})
        retry_data = retry_ack.get("data", {}) if isinstance(retry_ack, dict) else {}
        retry_messages = wait_for(loss_sid, lambda rows: sum(
            item.get("type") == "user" and item.get("id") == lost_input_id for item in rows) >= 2,
            timeout=2)
        retry_user_count = sum(item.get("type") == "user" and item.get("id") == lost_input_id
                               for item in retry_messages)
        provider_calls_after_retry = len(provider_calls)
        conflict_status, conflict_ack = prompt(loss_sid, "LOSS-CONFLICT", {"id": lost_input_id})
        conflict_data = conflict_ack.get("data", {}) if isinstance(conflict_ack, dict) else {}
        conflict_messages = messages(loss_sid).get("data", [])
        conflict_user_texts = [message_text(item) for item in conflict_messages
                               if item.get("type") == "user" and item.get("id") == lost_input_id]

        prompt_ack = success_data
        output = {
            "server_version": server_version,
            "openapi": {
                "prompt_request_fields": prompt_fields,
                "prompt_request_required": sorted(prompt_body_schema.get("required", [])),
                "prompt_200_schema_keys": sorted(prompt_response_schema),
                "prompt_200_required": sorted(prompt_response_schema.get("required", [])),
                "prompt_200_properties": sorted(prompt_response_schema.get("properties", {})),
                "inbox_200_schema_keys": sorted(inbox_response_schema),
                "inbox_200_required": sorted(inbox_response_schema.get("required", [])),
                "inbox_200_properties": sorted(inbox_response_schema.get("properties", {})),
                "message_200_schema_keys": sorted(message_response_schema),
                "message_200_schema_ref": message_response_schema.get("$ref"),
                "message_get_query_parameter_names": message_parameters,
            },
            "prompt_ack": {
                "status": success_status,
                "envelope_keys": sorted(success_ack),
                "data_keys": sorted(prompt_ack),
                "id_format_prefix": str(prompt_ack.get("id", ""))[:4],
                "delivery": prompt_ack.get("delivery"),
                "payload_keys": sorted(prompt_ack.get("payload", {})),
                "payload_text": (prompt_ack.get("payload") or {}).get("text"),
                "type": prompt_ack.get("type"),
                "time_keys": sorted(prompt_ack.get("time", {})),
                "session_id_matches_request": prompt_ack.get("sessionID") == success_sid,
                "transcript_user_id_matches_ack": bool(success_user and success_user.get("id") == success_id),
                "transcript_user_text": message_text(success_user),
                "inbox_status_after_completion": success_inbox_status,
                "inbox_item_count_after_completion": len((success_inbox or {}).get("data", [])),
            },
            "negative_control": {
                "case": "POST prompt with required text omitted",
                "status": invalid_status,
                "response_keys": sorted(invalid_response) if isinstance(invalid_response, dict) else None,
                "transcript_unchanged": invalid_no_admission,
                "asserted_rejected_without_admission": True,
            },
            "delayed_projection": {
                "first_prompt_status": first_status,
                "first_ack_delivery": (first_ack.get("data") or {}).get("delivery"),
                "queued_prompt_status": queued_status,
                "queued_ack_delivery": queued_data.get("delivery"),
                "queued_ack_data_keys": sorted(queued_data),
                "immediate_inbox_status": immediate_inbox_status,
                "immediate_inbox_count": len(inbox_items),
                "queued_ack_id_matches_inbox": any(item.get("id") == queued_id for item in inbox_items),
                "inbox_envelope_keys": sorted(immediate_inbox),
                "inbox_item_keys": sorted(inbox_item),
                "inbox_item_delivery": inbox_item.get("delivery"),
                "inbox_item_payload_keys": sorted(inbox_item.get("payload", {})),
                "inbox_item_text": (inbox_item.get("payload") or {}).get("text"),
                "immediate_transcript_count": len(immediate_messages),
                "queued_ack_id_in_transcript_before_release": immediate_queued_transcript,
                "projection_observation_window_ms": 1000,
                "queued_transcript_first_seen_ms_after_ack": queued_transcript_first_seen_ms,
                "queued_inbox_first_seen_ms_after_ack": queued_inbox_first_seen_ms,
                "queued_user_text_before_release": message_text(next((item for item in immediate_messages
                    if item.get("type") == "user" and item.get("id") == queued_id), {})),
                "queued_ack_id_in_transcript_after_drain": bool(drained_user and drained_user.get("id") == queued_id),
                "queued_user_text_after_drain": message_text(drained_user),
                "inbox_status_after_drain": drained_inbox_status,
                "inbox_count_after_drain": len((drained_inbox or {}).get("data", [])),
            },
            "pagination": pagination,
            "response_loss": {
                "proxy_upstream_status": proxy_observation.get("upstream_status"),
                "proxy_response_body_bytes_received": proxy_observation.get("upstream_body_bytes"),
                "proxy_upstream_ack_data_keys": proxy_observation.get("upstream_ack_data_keys"),
                "proxy_upstream_ack_delivery": proxy_observation.get("upstream_ack_delivery"),
                "proxy_upstream_ack_id_matches_supplied": proxy_observation.get("upstream_ack_id_matches_supplied"),
                "proxy_upstream_ack_payload_text": proxy_observation.get("upstream_ack_payload_text"),
                "proxy_dropped_response": proxy_observation.get("response_dropped"),
                "proxy_request_count": proxy_observation.get("request_count"),
                "caller_error_class": loss_client_failure,
                "client_supplied_input_id": lost_input_id,
                "input_id_seen_in_transcript_before_release": bool(immediate_loss_user),
                "input_id_count_after_drain": lost_user_count,
                "same_id_retry_status": retry_status,
                "same_id_retry_ack_keys": sorted(retry_data),
                "same_id_retry_ack_matches_supplied_id": retry_data.get("id") == lost_input_id,
                "same_id_retry_transcript_count": retry_user_count,
                "provider_call_delta_during_retry_window": provider_calls_after_retry - provider_calls_before_retry,
                "same_id_different_text_status": conflict_status,
                "same_id_different_text_ack_text": (conflict_data.get("payload") or {}).get("text"),
                "same_id_different_text_transcript_texts": conflict_user_texts,
                "retry_deduplicated": (retry_status == 200 and retry_data.get("id") == lost_input_id
                                       and retry_user_count == 1
                                       and provider_calls_after_retry == provider_calls_before_retry),
            },
            "synthetic_provider_requests": len(provider_calls),
            "isolation": {
                "loopback_only": True,
                "bwrap_unshare_net": True,
                "temporary_home_xdg_and_sessions": True,
                "no_provider_credentials_or_config_read": True,
                "no_external_inference": True,
                "generated_password_recorded": False,
            },
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
        if proxy is not None:
            proxy.shutdown()
            proxy.server_close()
        if mock is not None:
            mock.shutdown()
            mock.server_close()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
