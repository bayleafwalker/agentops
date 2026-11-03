#!/usr/bin/env python3
"""Sanitized, no-turn Codex app-server model selection probe.

Uses a temporary CODEX_HOME with a one-line model config and a fresh temporary
workspace. The child environment excludes ambient auth/provider variables.
Only whitelisted response fields and JSON-RPC error codes are emitted.
"""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import select
import subprocess
import tempfile
import time
from typing import Any


CLI_VERSION = "0.166.0"
DEFAULT_MODEL = "gpt-6.1-terra"
EXPLICIT_MODEL = "gpt-6-luna"
UNSUPPORTED_MODEL = "codex-routing-probe-model-does-not-exist-20261103"


class AppServer:
    def __init__(self, root: Path, workspace: Path, codex_home: Path) -> None:
        env = {
            "PATH": os.environ.get("PATH", "/run/current-system/sw/bin:/usr/bin:/bin"),
            "HOME": str(root),
            "CODEX_HOME": str(codex_home),
            "LANG": "C.UTF-8",
        }
        self.proc = subprocess.Popen(
            ["codex", "app-server", "--listen", "stdio://"],
            cwd=workspace,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    def send(self, value: dict[str, Any]) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def response(self, request_id: int, timeout: float = 12.0) -> dict[str, Any] | None:
        assert self.proc.stdout is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            ready, _, _ = select.select(
                [self.proc.stdout], [], [], max(0.0, deadline - time.monotonic())
            )
            if not ready:
                break
            line = self.proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                return message
        return None

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)


def summarize(message: dict[str, Any] | None) -> dict[str, Any]:
    if message is None:
        return {"response": "timeout_or_closed"}
    if "error" in message:
        return {"response": "error", "jsonrpc_error_code": message["error"].get("code")}
    result = message.get("result", {})
    thread = result.get("thread") or {}
    return {
        "response": "success",
        "model": result.get("model"),
        "modelProvider": result.get("modelProvider"),
        "serviceTier": result.get("serviceTier"),
        "threadStatus": thread.get("status"),
    }


def run() -> dict[str, Any]:
    version = subprocess.run(
        ["codex", "--version"], check=True, text=True, capture_output=True
    ).stdout.strip()
    if version != f"codex-cli {CLI_VERSION}":
        raise RuntimeError("pinned CLI version mismatch")

    with tempfile.TemporaryDirectory(prefix="codex-routing-probe-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        codex_home = root / "codex-home"
        protocol_dir = root / "protocol"
        workspace.mkdir()
        codex_home.mkdir()
        protocol_dir.mkdir()
        (codex_home / "config.toml").write_text(
            f'model = "{DEFAULT_MODEL}"\n', encoding="utf-8"
        )
        protocol_env = {
            "PATH": os.environ.get("PATH", "/run/current-system/sw/bin:/usr/bin:/bin"),
            "HOME": str(root),
            "CODEX_HOME": str(codex_home),
            "LANG": "C.UTF-8",
        }
        subprocess.run(
            [
                "codex",
                "app-server",
                "generate-ts",
                "--experimental",
                "--out",
                str(protocol_dir),
            ],
            check=True,
            env=protocol_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        schema_files = (
            "v2/ThreadStartParams.ts",
            "v2/ThreadStartResponse.ts",
            "v2/ThreadResumeParams.ts",
            "v2/ThreadResumeResponse.ts",
        )
        protocol_schema_sha256 = {
            filename: hashlib.sha256((protocol_dir / filename).read_bytes()).hexdigest()
            for filename in schema_files
        }
        server = AppServer(root, workspace, codex_home)
        try:
            server.send(
                {
                    "method": "initialize",
                    "id": 1,
                    "params": {
                        "clientInfo": {
                            "name": "codex-routing-probe",
                            "title": "Codex routing probe",
                            "version": "1.0.0",
                        },
                        "capabilities": None,
                    },
                }
            )
            initialized = server.response(1)
            if initialized is None or "error" in initialized:
                return {"initialize": "failed"}
            server.send({"method": "initialized", "params": {}})

            common = {
                "cwd": str(workspace),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "ephemeral": True,
            }
            cases = [
                (2, "configured_default", common),
                (
                    3,
                    "explicit_model",
                    {**common, "model": EXPLICIT_MODEL, "modelProvider": "openai"},
                ),
                (
                    4,
                    "unsupported_model_negative_control",
                    {
                        **common,
                        "model": UNSUPPORTED_MODEL,
                        "modelProvider": "openai",
                        "allowProviderModelFallback": False,
                    },
                ),
            ]
            observations: dict[str, Any] = {}
            ephemeral_id = None
            for request_id, label, params in cases:
                server.send(
                    {"method": "thread/start", "id": request_id, "params": params}
                )
                response = server.response(request_id)
                observations[label] = summarize(response)
                if label == "explicit_model" and response and "result" in response:
                    ephemeral_id = (response["result"].get("thread") or {}).get("id")

            if ephemeral_id:
                server.send(
                    {
                        "method": "thread/resume",
                        "id": 5,
                        "params": {
                            "threadId": ephemeral_id,
                            "cwd": str(workspace),
                            "approvalPolicy": "never",
                            "sandbox": "read-only",
                        },
                    }
                )
                observations["ephemeral_resume_without_model_override"] = summarize(
                    server.response(5)
                )
            else:
                observations["ephemeral_resume_without_model_override"] = {
                    "response": "not_attempted_start_failed"
                }

            return {
                "cli_version": CLI_VERSION,
                "protocol_schema_sha256": protocol_schema_sha256,
                "initialize": "success",
                "isolation": {
                    "temporary_workspace": True,
                    "temporary_codex_home_contains_only_model_config": True,
                    "ambient_credentials_in_child_environment": False,
                    "provider_calls": False,
                    "turn_start_sent": False,
                    "raw_protocol_messages_recorded": False,
                },
                "requests": {
                    "all_threads_ephemeral": True,
                    "sandbox": "read-only",
                    "approval_policy": "never",
                    "unsupported_model": UNSUPPORTED_MODEL,
                    "unsupported_model_fallback": False,
                },
                "observations": observations,
                "assurance": "app-server-reported selected thread configuration only",
                "limits": [
                    "No inference turn was started; no provider serving or billing claim is established.",
                    "A returned model string is not proof of model catalog entitlement or backend identity.",
                    "An explicit request echoed in the response does not show provider-side availability.",
                    "Resume error details are limited to the JSON-RPC code; message text is omitted.",
                ],
            }
        finally:
            server.close()


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
