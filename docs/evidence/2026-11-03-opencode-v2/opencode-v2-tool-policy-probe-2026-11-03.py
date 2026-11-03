#!/usr/bin/env python3
"""Disposable OpenCode 2.0.32 tool-policy controls; run only inside bwrap --unshare-net.

Uses a loopback fake model, a loopback HTTP canary, temporary HOME/XDG state,
and a throwaway project. No real provider, credential, or external endpoint is used.
"""
import base64
import http.server
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

BINARY = "/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
DENY_ALL = [{"action": "*", "resource": "*", "effect": "deny"}]

def require(ok, message):
    if not ok:
        raise AssertionError(message)

def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    value = sock.getsockname()[1]
    sock.close()
    return value

root = pathlib.Path(tempfile.mkdtemp(prefix="oc-v2-policy-", dir="/tmp"))
server = provider = web = None
try:
    for name in ("home", "config", "data", "state", "cache", "work"):
        (root / name).mkdir(mode=0o700)
    work = root / "work"
    canary = work / "read-canary"
    canary.write_text("synthetic-canary-42", encoding="utf-8")
    write_target = work / "write-target"
    (work / ".opencode" / "skills" / "probe-skill").mkdir(parents=True)
    (work / ".opencode" / "skills" / "probe-skill" / "SKILL.md").write_text(
        "---\nname: probe-skill\ndescription: synthetic qualification fixture\n---\n"
        "Synthetic only.\n", encoding="utf-8")

    web_hits = []
    class Web(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            web_hits.append(self.path)
            body = b"loopback synthetic response"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args):
            pass
    web = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), Web)
    threading.Thread(target=web.serve_forever, daemon=True).start()

    cases = {
        "read-deny": ("read", {"path": str(canary)}, "deny"),
        "read-allow": ("read", {"path": str(canary)}, "read"),
        "read-mutated-control": ("read", {"path": str(canary)}, "mutated"),
        "write-deny": ("write", {"path": str(write_target), "content": "synthetic-write"}, "deny"),
        "write-allow": ("write", {"path": str(write_target), "content": "synthetic-write"}, "edit"),
        "webfetch-deny": ("webfetch", {"url": f"http://127.0.0.1:{web.server_address[1]}/probe"}, "deny"),
        "webfetch-allow": ("webfetch", {"url": f"http://127.0.0.1:{web.server_address[1]}/probe"}, "webfetch"),
        "subagent-deny": ("subagent", {"agent": "general", "description": "synthetic task", "prompt": "reply synthetic"}, "deny"),
        "subagent-allow": ("subagent", {"agent": "general", "description": "synthetic task", "prompt": "reply synthetic"}, "subagent"),
        "skill-deny": ("skill", {"id": "probe-skill"}, "deny"),
        "skill-allow": ("skill", {"id": "probe-skill"}, "skill"),
    }
    provider_requests = []
    class FakeProvider(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
            messages = request.get("messages", [])
            serial = json.dumps(messages)
            label = next((name for name in cases if "CASE:" + name in serial), "other")
            tools = [tool.get("function", {}).get("name") for tool in request.get("tools", [])
                     if isinstance(tool, dict)]
            calls = [message for message in messages
                     if message.get("role") == "tool" or message.get("tool_call_id")]
            provider_requests.append({"case": label, "tools": tools,
                                      "skill_fixture_in_transcript": any(
                                          "Synthetic only." in json.dumps(message) for message in messages)})
            if label in cases and not calls:
                tool_name, arguments, _ = cases[label]
                delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "call-" + label,
                    "type": "function", "function": {"name": tool_name,
                    "arguments": json.dumps(arguments)}}]}
                finish = "tool_calls"
            else:
                delta = {"role": "assistant", "content": "synthetic done"}
                finish = "stop"
            chunks = []
            for part, reason in ((delta, None), ({}, finish)):
                event = {"id": "synthetic", "object": "chat.completion.chunk", "created": 1,
                         "model": "fake", "choices": [{"index": 0, "delta": part,
                         "finish_reason": reason}]}
                chunks.append("data: " + json.dumps(event) + "\n\n")
            body = ("".join(chunks) + "data: [DONE]\n\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args):
            pass
    provider = http.server.ThreadingHTTPServer(("127.0.0.1", free_port()), FakeProvider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()

    (work / "opencode.json").write_text(json.dumps({"model": "mock/fake", "provider": {
        "mock": {"npm": "@ai-sdk/openai-compatible", "name": "Loopback synthetic provider",
        "options": {"baseURL": f"http://127.0.0.1:{provider.server_address[1]}/v1",
                    "apiKey": "synthetic-only"},
        "models": {"fake": {"name": "Fake", "tool_call": True,
                              "limit": {"context": 128000, "output": 4096}}}}}}), encoding="utf-8")
    password = secrets.token_urlsafe(32)
    authorization = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
    base = f"http://127.0.0.1:{free_port()}"
    env = {"PATH": "/run/current-system/sw/bin:/usr/bin:/bin", "HOME": str(root / "home"),
           "XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data"),
           "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"),
           "OPENCODE_SERVER_PASSWORD": password}
    def start_server():
        return subprocess.Popen([BINARY, "serve", "--hostname", "127.0.0.1",
                                 "--port", str(urllib.parse.urlsplit(base).port)], cwd=work, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def call(method, path, body=None):
        req = urllib.request.Request(base + path, method=method,
            data=None if body is None else json.dumps(body).encode(),
            headers={"content-type": "application/json", "authorization": authorization})
        try:
            with urllib.request.urlopen(req, timeout=8) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read())
            except Exception:
                return error.code, None
    server = start_server()
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError("OpenCode exited before readiness")
        try:
            if call("GET", "/openapi.json")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.1)
    version = call("GET", "/api/info")[1].get("version")
    require(version == "2.0.32", "pinned OpenCode version mismatch")

    results = []
    sessions = {}
    for label, (tool_name, arguments, action) in cases.items():
        if action == "mutated":
            permissions = [{"action": "*", "resource": "*", "effect": "allow"}]
        else:
            permissions = list(DENY_ALL)
            if action not in ("deny",):
                permissions.append({"action": action, "resource": "*", "effect": "allow"})
        _, created = call("POST", "/api/session", {"title": label,
            "location": {"directory": str(work)}, "model": {"id": "fake", "providerID": "mock"},
            "agent": "build", "permissions": permissions})
        session_id = created["data"]["id"]
        sessions[label] = (session_id, permissions)
        before_requests = len(provider_requests)
        before_hits = len(web_hits)
        prompt_status, prompt = call("POST", f"/api/session/{session_id}/prompt", {"text": "CASE:" + label})
        require(prompt_status == 200 and prompt["data"].get("id"), f"{label}: prompt failed")
        messages = []
        for _ in range(100):
            _, response = call("GET", f"/api/session/{session_id}/message")
            messages = (response or {}).get("data", [])
            if any(message.get("type") == "idle" for message in messages):
                break
            time.sleep(0.1)
        parts = [part for message in messages if message.get("type") == "assistant"
                 for part in message.get("content", []) if part.get("type") == "tool"]
        tool_result = next((part for part in parts if part.get("name") == tool_name), {})
        state = tool_result.get("state") or {}
        first_request = next((item for item in provider_requests[before_requests:]
                              if item["case"] == label), {})
        result = {"case": label, "tool_offered": tool_name in first_request.get("tools", []),
            "tool_status": state.get("status"),
            "tool_error": "tool-not-available" if "No tool named" in str((state.get("error") or {}).get("message", "")) else None,
            "read_canary_returned": any("synthetic-canary-42" in json.dumps(part) for part in parts),
            "write_target_created": write_target.exists(), "loopback_http_hits": len(web_hits) - before_hits,
            "skill_marker_in_tool_output": any("Synthetic only." in json.dumps(part) for part in parts),
            "fake_provider_requests": len(provider_requests) - before_requests,
            "terminal_idle_observed": any(message.get("type") == "idle" for message in messages)}
        results.append(result)
        if label == "write-allow":
            write_target.unlink(missing_ok=True)

    # Assert ordinary controls and their corresponding positive controls.
    by_case = {item["case"]: item for item in results}
    for label in ("read-deny", "write-deny", "webfetch-deny", "subagent-deny", "skill-deny"):
        result = by_case[label]
        require(not result["tool_offered"] and result["tool_status"] == "error",
                f"{label}: denied tool was offered or not rejected")
    require(not by_case["read-deny"]["read_canary_returned"], "read deny leaked the canary")
    require(not by_case["write-deny"]["write_target_created"], "write deny created the canary file")
    require(by_case["webfetch-deny"]["loopback_http_hits"] == 0, "webfetch deny reached local HTTP server")
    require(by_case["read-allow"]["tool_offered"] and by_case["read-allow"]["read_canary_returned"],
            "read positive control failed")
    require(by_case["write-allow"]["tool_offered"] and by_case["write-allow"]["tool_status"] == "completed"
            and by_case["write-allow"]["write_target_created"], "write positive control failed")
    require(by_case["webfetch-allow"]["tool_offered"] and by_case["webfetch-allow"]["loopback_http_hits"] == 1,
            "webfetch positive control failed")
    require(by_case["subagent-allow"]["tool_offered"] and by_case["subagent-allow"]["tool_status"] == "completed"
            and by_case["subagent-allow"]["fake_provider_requests"] >= 3, "subagent positive control failed")
    require(by_case["skill-allow"]["tool_offered"] and by_case["skill-allow"]["tool_status"] == "completed"
            and by_case["skill-allow"]["skill_marker_in_tool_output"], "skill positive control failed")

    # Forced mutation: changing the wildcard deny to allow must make the read-denial assertion fail.
    mutated = by_case["read-mutated-control"]
    try:
        require(not mutated["read_canary_returned"], "mutated denial did not protect the file")
    except AssertionError as error:
        mutated_check = {"rule_mutation": "wildcard deny changed to wildcard allow",
                         "observed_canary_read": mutated["read_canary_returned"],
                         "denial_assertion_failed_as_expected": True,
                         "caught_failure": str(error)}
    else:
        raise AssertionError("mutated-rule negative control unexpectedly passed")
    require(mutated["read_canary_returned"], "mutated rule did not expose the positive control")

    # Restart with the same disposable XDG/DB roots, then repeat a denied read on the same session.
    session_id, expected_permissions = sessions["read-deny"]
    server.terminate()
    server.wait(timeout=5)
    server = start_server()
    for _ in range(100):
        if server.poll() is not None:
            raise RuntimeError("OpenCode exited during restart")
        try:
            if call("GET", "/openapi.json")[0] == 200:
                break
        except Exception:
            pass
        time.sleep(0.1)
    status, session_response = call("GET", "/api/session/" + session_id)
    recovered = (session_response or {}).get("data", {})
    require(status == 200 and recovered.get("id") == session_id, "same session not recovered")
    require(recovered.get("permissions") == expected_permissions, "ordered permission list drifted after restart")
    before_requests = len(provider_requests)
    _, prompt = call("POST", f"/api/session/{session_id}/prompt", {"text": "CASE:read-deny"})
    restarted_messages = []
    for _ in range(100):
        _, response = call("GET", f"/api/session/{session_id}/message")
        restarted_messages = (response or {}).get("data", [])
        restarted_parts = [part for message in restarted_messages if message.get("type") == "assistant"
                           for part in message.get("content", []) if part.get("type") == "tool"]
        if sum(message.get("type") == "user" for message in restarted_messages) >= 2 and restarted_parts:
            break
        time.sleep(0.1)
    restarted_parts = [part for message in restarted_messages if message.get("type") == "assistant"
                       for part in message.get("content", []) if part.get("type") == "tool"]
    restarted_read = next((part for part in restarted_parts if part.get("name") == "read"), {})
    restarted_tool_list = next((item["tools"] for item in provider_requests[before_requests:]
                                if item["case"] == "read-deny"), [])
    restart_evidence = {"same_session_id": recovered.get("id") == session_id,
        "ordered_permissions_exact": recovered.get("permissions") == expected_permissions,
        "read_tool_offered": "read" in restarted_tool_list,
        "read_tool_rejected": (restarted_read.get("state") or {}).get("status") == "error",
        "read_canary_returned": any("synthetic-canary-42" in json.dumps(part) for part in restarted_parts)}
    require(not restart_evidence["read_tool_offered"] and restart_evidence["read_tool_rejected"]
            and not restart_evidence["read_canary_returned"], "recovered session did not retain deny behavior")

    print(json.dumps({"schema": "opencode-v2-tool-policy-probe/v1", "version": version,
        "binary": BINARY,
        "isolation": {"network": "bubblewrap --unshare-net; local fake provider and local HTTP canary only",
            "filesystem": "temporary HOME/XDG/project; removed after probe",
            "credentials": "generated synthetic-only provider key and server password; neither recorded",
            "production_effects": "none"},
        "ordered_policy": "wildcard deny first; single action allow appended for positive controls",
        "results": results, "mutated_negative_control": mutated_check,
        "restart_recovery": restart_evidence,
        "action_mapping": {"file_read": "read", "file_write": "edit (exposes write)",
            "network_fetch": "webfetch", "subagent": "subagent", "skill": "skill"},
        "mcp": {"status": "untested", "reason": "no local MCP endpoint was provisioned in this probe"},
        "limits": ["These controls exercise only the listed tool calls and temporary paths.",
            "No general OS/filesystem, kernel, network-policy, or deployed-service containment claim.",
            "Subagent positive control used the fake local provider; it does not qualify arbitrary agents.",
            "MCP behavior remains untested."]}, sort_keys=True, indent=2))
finally:
    if server:
        server.terminate()
        server.wait(timeout=5)
    for service in (provider, web):
        if service:
            service.shutdown()
            service.server_close()
    shutil.rmtree(root, ignore_errors=True)
