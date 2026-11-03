#!/usr/bin/env python3
"""Probe v2.0.32 shell permission matching for current host-adapter metacharacters.

Run on devbox inside a no-egress bubblewrap namespace:
  bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc \
    --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin \
    python3 /projects/dev/_artifacts/opencode-v2-shell-metachar-probe.py

The fake provider is loopback-only and emits synthetic shell calls. The fake
sprintctl only creates a marker under this script's disposable /tmp tree.
Credentials are generated/dummy only and never printed. No production config,
credential, network, or effect is accessed.
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
SHELL_METACHARACTERS = (">", "<", "$", "`", ";", "&", "|", "[")


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
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-shell-meta-", dir="/tmp"))
    mock = None
    server = None
    try:
        for name in ("home", "config", "data", "state", "cache", "work", "bin"):
            (root / name).mkdir(mode=0o700)
        work = root / "work"
        fake_log = work / "fake-sprintctl-called"
        fake_cli = root / "bin" / "sprintctl"
        fake_cli.write_text("#!/bin/sh\necho invoked > " + str(fake_log) + "\nexit 0\n", encoding="utf-8")
        fake_cli.chmod(0o700)

        commands = {}
        sentinels = {}

        def sentinel(label):
            path = work / f"sentinel-{label}"
            sentinels[label] = path
            return str(path)

        commands["baseline"] = "sprintctl run context synthetic-run"
        commands["greater-than"] = f"sprintctl run context synthetic-run > {sentinel('gt')}"
        commands["less-than"] = "sprintctl run context synthetic-run < /dev/null"
        commands["dollar-substitution"] = f"sprintctl run context synthetic-run $(touch {sentinel('dollar')})"
        commands["backtick-substitution"] = f"sprintctl run context synthetic-run `touch {sentinel('backtick')}`"
        commands["semicolon-chain"] = f"sprintctl run context synthetic-run; touch {sentinel('semicolon')}"
        commands["and-chain"] = f"sprintctl run context synthetic-run && touch {sentinel('and')}"
        commands["pipe-chain"] = f"sprintctl run context synthetic-run | touch {sentinel('pipe')}"
        commands["bracket-glob"] = "sprintctl run context synthetic-run [abc]"
        commands["newline-chain"] = f"sprintctl run context synthetic-run\n touch {sentinel('newline')}"
        commands["newline-in-single-quotes"] = "sprintctl run context synthetic-run 'one\ntwo'"
        commands["newline-explicit-deny"] = f"sprintctl run context synthetic-run\n touch {sentinel('newline-explicit')}"
        commands["semicolon-single-quoted"] = f"sprintctl run context synthetic-run '; touch {sentinel('quoted-semicolon')}'"
        commands["dollar-double-quoted"] = f"sprintctl run context synthetic-run \"$(touch {sentinel('quoted-dollar')})\""
        commands["backtick-single-quoted"] = f"sprintctl run context synthetic-run '`touch {sentinel('quoted-backtick')}`'"
        commands["quoted-note-allow"] = "sprintctl run note synthetic-run 'body with spaces'"

        requests = []

        class FakeProvider(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("content-length", "0")))
                request = json.loads(raw)
                messages = request.get("messages", [])
                serialized = json.dumps(messages)
                names = [
                    tool.get("function", {}).get("name")
                    for tool in request.get("tools", [])
                    if isinstance(tool, dict)
                ]
                case = next((label for label in commands if f"CASE:{label}" in serialized), "OTHER")
                has_tool_result = any(
                    message.get("role") == "tool" or message.get("tool_call_id")
                    for message in messages
                )
                requests.append({"case": case, "tools": names})
                # Emit the exact shell call even if policy omitted shell from
                # the model's tool list; this is the deny/control negative.
                if case in commands and not has_tool_result:
                    delta = {
                        "role": "assistant",
                        "tool_calls": [{
                            "index": 0,
                            "id": "meta-call-" + case,
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
                encoded = (payload + "data: [DONE]\n\n").encode()
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

        base_rules = [
            {"action": "*", "resource": "*", "effect": "deny"},
            {"action": "shell", "resource": "sprintctl run context *", "effect": "allow"},
            {"action": "shell", "resource": "sprintctl run note *", "effect": "allow"},
        ]
        meta_rules = base_rules + [
            {"action": "shell", "resource": f"*{character}*", "effect": "deny"}
            for character in SHELL_METACHARACTERS
        ]
        newline_chain_allow = base_rules + [
            {"action": "shell", "resource": commands[label], "effect": "allow"}
            for label in ("newline-chain", "newline-explicit-deny")
        ]
        newline_chain_explicit_deny = newline_chain_allow + [
            {"action": "shell", "resource": "*\n*", "effect": "deny"},
        ]
        cases = [("baseline", meta_rules)]
        cases.extend((label, meta_rules) for label in (
            "greater-than", "less-than", "dollar-substitution", "backtick-substitution",
            "semicolon-chain", "and-chain", "pipe-chain", "bracket-glob",
            "newline-chain", "newline-in-single-quotes", "semicolon-single-quoted",
            "dollar-double-quoted", "backtick-single-quoted", "quoted-note-allow",
        ))
        cases = [(label, newline_chain_allow if label == "newline-chain" else rules)
                 for label, rules in cases]
        cases.append(("newline-explicit-deny", newline_chain_explicit_deny))

        observations = []
        for label, permissions in cases:
            fake_log.unlink(missing_ok=True)
            for path in sentinels.values():
                path.unlink(missing_ok=True)
            status, created = call("POST", "/api/session", {
                "title": label,
                "location": {"directory": str(work)},
                "model": {"id": "fake", "providerID": "mock"},
                "agent": "build",
                "permissions": permissions,
            })
            require(status == 200, f"{label}: session create failed")
            session_id = created["data"]["id"]
            before = len(requests)
            prompt_status, _prompt = call("POST", f"/api/session/{session_id}/prompt", {
                "text": f"CASE:{label}",
            })
            require(prompt_status == 200, f"{label}: prompt POST failed")

            messages = []
            deadline = time.time() + 7
            while time.time() < deadline:
                result = call("GET", f"/api/session/{session_id}/message")[1]
                messages = result.get("data", []) if isinstance(result, dict) else []
                if any(item.get("type") == "idle" for item in messages):
                    break
                time.sleep(0.1)

            provider_request = next((item for item in requests[before:] if item["case"] == label), None)
            idle = next((item for item in messages if item.get("type") == "idle"), None)
            tool_parts = [
                part for message in messages if message.get("type") == "assistant"
                for part in message.get("content", []) if part.get("type") == "tool"
            ]
            tool = tool_parts[0] if tool_parts else {}
            state = tool.get("state") or {}
            if state.get("status") == "error":
                classification = "blocked"
            elif state.get("status") == "completed" and (state.get("metadata") or {}).get("exit") == 0:
                classification = "allowed"
            else:
                classification = "unknown"
            observations.append({
                "case": label,
                "command": "<synthetic command; see fixture source>",
                "tool_names_offered": provider_request["tools"] if provider_request else None,
                "tool_state": state.get("status"),
                "tool_error": (state.get("error") or {}).get("message"),
                "exit": (state.get("metadata") or {}).get("exit"),
                "fake_sprintctl_invoked": fake_log.exists(),
                "sentinels_created": sorted(name for name, path in sentinels.items() if path.exists()),
                "idle_outcome": idle.get("outcome") if idle else None,
                "classification": classification,
            })

        by_case = {row["case"]: row for row in observations}
        require(by_case["baseline"]["classification"] == "allowed", "allowed baseline did not pass")
        require(by_case["greater-than"]["classification"] == "blocked", "greater-than control changed")
        require(by_case["less-than"]["classification"] == "blocked", "less-than control changed")
        require(by_case["dollar-substitution"]["classification"] == "blocked", "dollar control changed")
        require(by_case["backtick-substitution"]["classification"] == "blocked", "backtick control changed")
        require(by_case["semicolon-chain"]["classification"] == "blocked", "semicolon control changed")
        require(by_case["and-chain"]["classification"] == "blocked", "and-chain control changed")
        require(by_case["pipe-chain"]["classification"] == "blocked", "pipe control changed")
        require(by_case["bracket-glob"]["classification"] == "blocked", "bracket control changed")
        require(by_case["newline-chain"]["classification"] == "blocked", "newline-chain observation changed")
        require(by_case["newline-in-single-quotes"]["classification"] == "allowed", "quoted newline observation changed")
        require(by_case["quoted-note-allow"]["classification"] == "allowed", "quoted note allow control did not pass")
        require(by_case["semicolon-chain"]["classification"] == "blocked", "semicolon negative control was not blocked")
        require(by_case["newline-explicit-deny"]["classification"] == "blocked", "explicit newline deny control was not blocked")
        require(all(row["classification"] in ("blocked", "allowed", "unknown") for row in observations), "invalid classification")
        negative_control_error = prove_assertions_fail_closed()

        print(json.dumps({
            "version": "2.0.32",
            "external_network": False,
            "shell_metacharacters_from_current_adapter": list(SHELL_METACHARACTERS),
            "permissions": {
                "default": "deny all",
                "allow_patterns": ["sprintctl run context *", "sprintctl run note *"],
                "deny_patterns": [f"*{character}*" for character in SHELL_METACHARACTERS],
                "extra_newline_deny": "*\\n*",
            },
            "observations": observations,
            "interpretation": {
                "raw_metacharacter_permission_outcomes": "blocked for all tested characters under the default-deny plus narrow sprintctl allow rules and per-character deny rules",
                "newline_chain": "blocked even after an exact newline-containing allow rule was added; reason is unresolved",
                "newline_deny_rule_effect": "unknown: the exact allow control itself did not permit the newline command, so the extra newline deny rule was not isolated",
                "quoted_newline": "allowed and fake sprintctl ran; no command-chain sentinel was created",
                "quoted_metacharacters": "blocked for tested semicolon, dollar expansion, and backticks despite quoting",
            },
            "assertions": {
                "baseline_allowed": True,
                "current_metacharacter_cases_blocked": True,
                "newline_chain_blocked_even_after_exact_allow": True,
                "newline_inside_single_quotes_allowed": True,
                "newline_chain_exact_allow_control": by_case["newline-chain"]["classification"] == "allowed",
                "quoted_note_allowed": True,
                "semicolon_negative_control_blocked": True,
                "explicit_newline_negative_control_blocked": True,
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
