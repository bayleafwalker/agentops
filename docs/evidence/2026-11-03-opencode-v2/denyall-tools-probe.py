#!/usr/bin/env python3
"""Compare tool exposure under deny-all and allow-all in a local fake provider.

Run from this repository with:
  ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc \
    --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' \
    < docs/evidence/2026-11-03-opencode-v2/denyall-tools-probe.py

Only a synthetic OpenAI-compatible endpoint bound to loopback is used. The
session server and fake endpoint share a no-egress network namespace. All
sessions/config/files are temporary. The Basic-auth password is generated and
never printed. No real inference or provider credentials are used.
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


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-tool-policy-", dir="/tmp"))
    mock = None
    server = None
    try:
        for name in ("home", "config", "data", "state", "cache", "work"):
            (root / name).mkdir(mode=0o700)

        requests = []
        sentinels = {label: root / "work" / f"{label}-sentinel" for label in ("deny", "allow")}

        class FakeProvider(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", "0")))
                body = json.loads(raw)
                names = [
                    (tool.get("function") or {}).get("name")
                    for tool in body.get("tools", [])
                    if isinstance(tool, dict)
                ]
                user_text = " ".join(
                    str(message.get("content", ""))
                    for message in body.get("messages", [])
                    if message.get("role") == "user"
                )
                label = "allow" if "ALLOW-SHELL" in user_text else "deny"
                requests.append({"case": label, "tool_names": names})
                has_tool_result = any(
                    message.get("role") == "tool" or message.get("tool_call_id")
                    for message in body.get("messages", [])
                )

                chunks = []
                if label == "allow" and "shell" in names and not has_tool_result:
                    arguments = json.dumps({"command": f"touch {sentinels['allow']}"})
                    delta = {
                        "role": "assistant",
                        "tool_calls": [{
                            "index": 0,
                            "id": "synthetic-call",
                            "type": "function",
                            "function": {"name": "shell", "arguments": arguments},
                        }],
                    }
                    chunks.append({
                        "id": "local-chat", "object": "chat.completion.chunk",
                        "created": 1, "model": "fake",
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    })
                    finish = "tool_calls"
                else:
                    chunks.append({
                        "id": "local-chat", "object": "chat.completion.chunk",
                        "created": 1, "model": "fake",
                        "choices": [{
                            "index": 0,
                            "delta": {"role": "assistant", "content": "Synthetic no-op result."},
                            "finish_reason": None,
                        }],
                    })
                    finish = "stop"
                chunks.append({
                    "id": "local-chat", "object": "chat.completion.chunk",
                    "created": 1, "model": "fake",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": finish}],
                })
                payload = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                payload += "data: [DONE]\n\n"
                encoded = payload.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                self.wfile.flush()

            def log_message(self, *_args):
                pass

        mock = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), FakeProvider)
        threading.Thread(target=mock.serve_forever, daemon=True).start()
        work = root / "work"
        config = {
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
                        "fake": {
                            "name": "Fake",
                            "tool_call": True,
                            "limit": {"context": 4096, "output": 1024},
                        }
                    },
                }
            },
        }
        (work / "opencode.json").write_text(json.dumps(config), encoding="utf-8")

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
                with urllib.request.urlopen(request, timeout=6) as response:
                    raw = response.read()
                    return response.status, json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                try:
                    return error.code, json.loads(error.read())
                except Exception:
                    return error.code, None

        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError("OpenCode exited before readiness")
            try:
                if call("GET", "/openapi.json")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(0.1)

        cases = []
        for label, effect in (("deny", "deny"), ("allow", "allow")):
            created_status, created = call("POST", "/api/session", {
                "title": f"{label}-synthetic-tool-policy",
                "location": {"directory": str(work)},
                "model": {"id": "fake", "providerID": "mock"},
                "agent": "build",
                "permissions": [{"action": "*", "resource": "*", "effect": effect}],
            })
            if created_status != 200:
                raise RuntimeError(f"synthetic session create returned {created_status}")
            session_id = created["data"]["id"]
            before = len(requests)
            call("POST", f"/api/session/{session_id}/prompt", {
                "text": f"{label.upper()}-SHELL: invoke shell to touch the temporary sentinel."
            })
            deadline = time.time() + 8
            while time.time() < deadline and not any(row["case"] == label for row in requests[before:]):
                time.sleep(0.1)
            time.sleep(0.5)
            cases.append({
                "case": label,
                "model_tool_names": [row["tool_names"] for row in requests[before:] if row["case"] == label],
                "sentinel_created": sentinels[label].exists(),
            })
            sentinels[label].unlink(missing_ok=True)

        denied, allowed = cases
        if (not denied["model_tool_names"] or any(denied["model_tool_names"])
                or denied["sentinel_created"]):
            raise RuntimeError("deny-all tool exposure control failed")
        if not allowed["model_tool_names"] or not any(
            "shell" in names for names in allowed["model_tool_names"]
        ):
            raise RuntimeError("allow control did not expose shell")
        print(json.dumps({
            "version": "2.0.32",
            "external_network": False,
            "provider": "local loopback synthetic OpenAI-compatible endpoint",
            "cases": cases,
            "assessment": "deny-all tool filtering can be compared with allow control; synthetic tool execution was not established by this fixture",
        }, sort_keys=True, indent=2))
    finally:
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
