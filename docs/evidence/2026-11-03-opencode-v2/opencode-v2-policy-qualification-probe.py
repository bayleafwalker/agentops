#!/usr/bin/env python3
"""Disposable OpenCode 2.0.32 tool policy probe with a local fake provider.

Run on devbox inside this no-egress bubblewrap namespace:
  bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc \
    --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin \
    python3 /projects/dev/_artifacts/opencode-v2-policy-qualification-probe.py

The synthetic provider is a local OpenAI-compatible HTTP server. The fake
sprintctl only writes a marker in this disposable directory. The server runs
with temporary HOME/XDG state, an allowlisted environment and generated Basic
auth password. It performs no external inference and never reads credentials.
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


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-policy-probe-", dir="/tmp"))
    mock = None
    server = None
    try:
        for name in ("home", "config", "data", "state", "cache", "work", "bin"):
            (root / name).mkdir(mode=0o700)
        work = root / "work"
        fake_log = work / "fake-sprintctl-called"
        fake_sprintctl = root / "bin" / "sprintctl"
        fake_sprintctl.write_text(
            "#!/bin/sh\necho invoked > " + str(fake_log) + "\nexit 0\n",
            encoding="utf-8",
        )
        fake_sprintctl.chmod(0o700)

        same_command_sentinel = work / "same-command-sentinel"
        injection_sentinel = work / "injection-sentinel"
        commands = {
            "CASE:SAME": f"touch {same_command_sentinel}",
            "CASE:CONTEXT": "sprintctl run context synthetic-run",
            "CASE:NOTE": "sprintctl run note synthetic-run synthetic-note",
            "CASE:PUBLISH": "sprintctl run publish synthetic-run",
            "CASE:INJECT": f"sprintctl run context synthetic-run; touch {injection_sentinel}",
        }
        requests = []

        class FakeProvider(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", "0")))
                request = json.loads(raw)
                names = [
                    tool.get("function", {}).get("name")
                    for tool in request.get("tools", [])
                    if isinstance(tool, dict)
                ]
                messages = request.get("messages", [])
                serialized = json.dumps(messages)
                case = next((key for key in commands if key in serialized), "OTHER")
                has_tool_result = any(
                    message.get("role") == "tool" or message.get("tool_call_id")
                    for message in messages
                )
                requests.append({"case": case, "tools": names})
                # Deliberately return a shell call even in the deny-all case,
                # where the tool is absent from the provider's advertised list.
                if case in commands and not has_tool_result:
                    delta = {
                        "role": "assistant",
                        "tool_calls": [{
                            "index": 0,
                            "id": "synthetic-call-" + case.split(":")[1].lower(),
                            "type": "function",
                            "function": {
                                "name": "shell",
                                "arguments": json.dumps({"command": commands[case]}),
                            },
                        }],
                    }
                    finish = "tool_calls"
                else:
                    delta = {"role": "assistant", "content": "Synthetic complete."}
                    finish = "stop"
                chunks = [
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                    {"id": "local", "object": "chat.completion.chunk", "created": 1,
                     "model": "fake", "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]},
                ]
                payload = "".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                payload += "data: [DONE]\n\n"
                encoded = payload.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                pass

        mock = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), FakeProvider)
        threading.Thread(target=mock.serve_forever, daemon=True).start()
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
                        "fake": {
                            "name": "Fake",
                            "tool_call": True,
                            "limit": {"context": 128000, "output": 4096},
                        }
                    },
                }
            },
        }), encoding="utf-8")

        port = free_port()
        password = secrets.token_urlsafe(32)
        authorization = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
        env = {
            "PATH": str(root / "bin") + ":/run/current-system/sw/bin:/usr/bin:/bin",
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

        for _ in range(100):
            if server.poll() is not None:
                raise RuntimeError("OpenCode exited before readiness")
            try:
                if call("GET", "/openapi.json")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(0.1)

        deny = [{"action": "*", "resource": "*", "effect": "deny"}]
        narrow = deny + [
            {"action": "shell", "resource": "sprintctl run context *", "effect": "allow"},
            {"action": "shell", "resource": "sprintctl run note *", "effect": "allow"},
        ]
        narrow_with_meta_deny = narrow + [
            {"action": "shell", "resource": "*;*", "effect": "deny"},
        ]
        wildcard_allow = [{"action": "*", "resource": "*", "effect": "allow"}]
        cases = [
            ("same-allow", "CASE:SAME", wildcard_allow),
            ("same-deny", "CASE:SAME", deny),
            ("reversed-rule-order", "CASE:CONTEXT", [
                {"action": "shell", "resource": "sprintctl run context *", "effect": "allow"},
                {"action": "*", "resource": "*", "effect": "deny"},
            ]),
            ("context-allow", "CASE:CONTEXT", narrow),
            ("note-allow", "CASE:NOTE", narrow),
            ("publish-deny", "CASE:PUBLISH", narrow),
            ("semicolon-deny", "CASE:INJECT", narrow_with_meta_deny),
        ]
        observations = []
        for label, marker, permissions in cases:
            fake_log.unlink(missing_ok=True)
            same_command_sentinel.unlink(missing_ok=True)
            injection_sentinel.unlink(missing_ok=True)
            status, created = call("POST", "/api/session", {
                "title": label,
                "location": {"directory": str(work)},
                "model": {"id": "fake", "providerID": "mock"},
                "agent": "build",
                "permissions": permissions,
            })
            if status != 200:
                raise RuntimeError(f"synthetic session create returned {status}")
            session_id = created["data"]["id"]
            before = len(requests)
            prompt_status, prompt = call("POST", f"/api/session/{session_id}/prompt", {"text": marker})
            input_id = (prompt or {}).get("data", {}).get("id")
            require(prompt_status == 200 and input_id, f"{label}: prompt POST did not return user message ID")

            messages = []
            deadline = time.time() + 7
            while time.time() < deadline:
                result = call("GET", f"/api/session/{session_id}/message")[1]
                messages = result.get("data", []) if isinstance(result, dict) else []
                if any(message.get("type") == "idle" for message in messages):
                    break
                time.sleep(0.1)
            user = next((message for message in messages if message.get("type") == "user"), {})
            idle = next((message for message in messages if message.get("type") == "idle"), {})
            tool_parts = [
                part for message in messages if message.get("type") == "assistant"
                for part in message.get("content", []) if part.get("type") == "tool"
            ]
            model_tools = next((row["tools"] for row in requests[before:] if row["case"] == marker), [])
            require(idle, f"{label}: terminal idle was not observed")
            require(user.get("id") == input_id, f"{label}: prompt/transcript user ID mismatch")
            observations.append({
                "case": label,
                "prompt_status": prompt_status,
                "user_id_matches_prompt_response": user.get("id") == input_id,
                "idle_outcome": idle.get("outcome"),
                "idle_id_differs_from_input": bool(idle and idle.get("id") != input_id),
                "idle_has_input_id_key": bool(idle and any(
                    key.lower() in ("inputid", "messageid", "promptid") for key in idle
                )),
                "model_saw_shell": "shell" in model_tools,
                "tool_parts": [{
                    "name": part.get("name"),
                    "executed": part.get("executed"),
                    "state": (part.get("state") or {}).get("status"),
                    "error": ((part.get("state") or {}).get("error") or {}).get("message"),
                    "exit": ((part.get("state") or {}).get("metadata") or {}).get("exit"),
                } for part in tool_parts],
                "same_command_sentinel_created": same_command_sentinel.exists() if marker == "CASE:SAME" else None,
                "fake_sprintctl_invoked": fake_log.exists(),
                "injection_sentinel_created": injection_sentinel.exists() if marker == "CASE:INJECT" else None,
            })

        by_case = {item["case"]: item for item in observations}
        require(by_case["same-allow"]["model_saw_shell"], "wildcard allow did not advertise shell")
        require(by_case["same-allow"]["same_command_sentinel_created"], "wildcard-allow shell call did not execute")
        require(by_case["same-allow"]["tool_parts"][0]["state"] == "completed", "wildcard-allow tool did not complete")
        require(not by_case["same-deny"]["model_saw_shell"], "deny-all unexpectedly advertised shell")
        require(not by_case["same-deny"]["same_command_sentinel_created"], "deny-all shell call created the sentinel")
        require(by_case["same-deny"]["tool_parts"][0]["state"] == "error", "deny-all synthetic call was not rejected")
        require(not by_case["reversed-rule-order"]["model_saw_shell"], "reversed rule order unexpectedly advertised shell")
        require(by_case["reversed-rule-order"]["tool_parts"][0]["state"] == "error", "reversed-order control did not reject tool")
        for label in ("context-allow", "note-allow"):
            require(by_case[label]["fake_sprintctl_invoked"], f"{label} did not invoke fake sprintctl")
            require(by_case[label]["tool_parts"][0]["state"] == "completed", f"{label} did not complete")
            require(by_case[label]["tool_parts"][0]["exit"] == 0, f"{label} returned nonzero exit")
        for label in ("publish-deny", "semicolon-deny"):
            require(not by_case[label]["fake_sprintctl_invoked"], f"{label} invoked fake sprintctl")
            require(by_case[label]["tool_parts"][0]["state"] == "error", f"{label} was not denied")
        require(not by_case["semicolon-deny"]["injection_sentinel_created"], "semicolon injection created its sentinel")
        negative_control_error = prove_assertions_fail_closed()

        print(json.dumps({
            "version": "2.0.32",
            "external_network": False,
            "fake_cli_effects": "temporary marker writes only",
            "permission_rule_order": "wildcard deny first; specific allow exceptions after; metacharacter deny last",
            "cases": observations,
            "assertions": {
                "all_expected_controls_passed": True,
                "forced_negative_control": negative_control_error,
            },
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
