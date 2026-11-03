#!/usr/bin/env python3
"""Disposable OpenCode 2.0.32 info/session/list probe.

Run from this repository with:
  ssh devbox-agent 'bwrap --unshare-net --ro-bind / / --tmpfs /tmp --dev /dev --proc /proc \
    --clearenv --setenv PATH /run/current-system/sw/bin:/usr/bin:/bin python3 -' \
    < docs/evidence/2026-11-03-opencode-v2/info-session-list-probe.py

The caller must use the pinned devbox binary path below. The probe only creates
temporary data, uses a generated Basic-auth password, never prompts a model,
and emits redacted/sanitized results. No provider credentials/config are read.
"""

import base64
import json
import pathlib
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


BINARY = "/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-info-probe-", dir="/tmp"))
    try:
        for name in ("home", "config", "data", "state", "cache", "work"):
            (root / name).mkdir(mode=0o700)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        password = secrets.token_urlsafe(32)
        auth = "Basic " + base64.b64encode(f"opencode:{password}".encode()).decode()
        env = {
            "PATH": "/run/current-system/sw/bin:/usr/bin:/bin",
            "HOME": str(root / "home"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "OPENCODE_SERVER_PASSWORD": password,
            "OPENCODE_SERVER_USERNAME": "opencode",
        }
        server = subprocess.Popen(
            [BINARY, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
            cwd=str(root / "work"), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        base = f"http://127.0.0.1:{port}"

        def call(method, path, query=None, body=None, authenticated=True):
            url = base + path
            if query:
                url += "?" + urllib.parse.urlencode(query)
            headers = {"content-type": "application/json"}
            if authenticated:
                headers["authorization"] = auth
            request = urllib.request.Request(
                url, method=method,
                data=None if body is None else json.dumps(body).encode(),
                headers=headers,
            )
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    raw = response.read()
                    return response.status, json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                raw = error.read()
                try:
                    payload = json.loads(raw)
                except Exception:
                    payload = None
                return error.code, payload

        try:
            openapi = None
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError("OpenCode exited before readiness")
                try:
                    status, openapi = call("GET", "/openapi.json")
                    if status == 200:
                        break
                except Exception:
                    pass
                time.sleep(0.2)
            if not openapi:
                raise RuntimeError("OpenAPI document unavailable")

            info_status, info = call("GET", "/api/info")
            unauth_status, _ = call("GET", "/api/info", authenticated=False)
            server_info_schema = openapi["components"]["schemas"]["ServerInfo"]

            sessions = []
            for index in range(3):
                directory = root / f"work-{index}"
                directory.mkdir(mode=0o700)
                created_status, created = call("POST", "/api/session", body={
                    "title": f"v2-page-{index}",
                    "location": {"directory": str(directory)},
                    "model": {"id": "never-connect", "providerID": "local-fake"},
                    "permissions": [{"action": "*", "resource": "*", "effect": "deny"}],
                })
                data = created.get("data", {}) if isinstance(created, dict) else {}
                sessions.append({
                    "status": created_status,
                    "id": data.get("id"),
                    "location": data.get("location", {}).get("directory"),
                    "model": data.get("model"),
                    "permissions": data.get("permissions"),
                    "title": data.get("title"),
                })

            first_status, first = call("GET", "/api/session", {
                "search": "v2-page-", "limit": 1, "order": "asc",
            })
            first_data = first.get("data", []) if isinstance(first, dict) else []
            cursor = (first.get("cursor") or {}).get("next") if isinstance(first, dict) else None
            next_status, next_page = call("GET", "/api/session", {
                "search": "v2-page-", "limit": 1, "cursor": cursor,
            }) if cursor else (None, None)
            directory_status, directory_result = call("GET", "/api/session", {
                "directory": str(root / "work-1"), "limit": 10,
            })
            exact_status, exact_result = call("GET", "/api/session", {
                "search": "v2-page-1", "limit": 10,
            })

            if info_status != 200 or unauth_status != 401 or info.get("version") != "2.0.32":
                raise RuntimeError("server identity or authentication control failed")
            for index, row in enumerate(sessions):
                if (row["status"] != 200 or not row["id"]
                        or row["location"] != str(root / f"work-{index}")
                        or row["model"].get("id") != "never-connect"
                        or row["model"].get("providerID") != "local-fake"
                        or row["permissions"] != [{"action": "*", "resource": "*", "effect": "deny"}]):
                    raise RuntimeError("session binding or permissions did not round-trip")
            if (first_status != 200 or len(first_data) != 1 or not cursor
                    or next_status != 200 or len((next_page or {}).get("data", [])) != 1
                    or directory_status != 200 or len((directory_result or {}).get("data", [])) != 1
                    or exact_status != 200 or len((exact_result or {}).get("data", [])) != 1):
                raise RuntimeError("session listing or pagination control failed")

            output = {
                "version": "2.0.32",
                "server_info": {
                    "authenticated_status": info_status,
                    "unauthenticated_status": unauth_status,
                    "schema": server_info_schema,
                    "safe_values": {
                        "version": info.get("version"),
                        "capabilities": info.get("capabilities"),
                    },
                    "redacted_fields_present": {
                        "pid": "pid" in info,
                        "urls": "urls" in info,
                        "paths": sorted((info.get("paths") or {}).keys()),
                    },
                },
                "session_create": {
                    "location_schema": openapi["components"]["schemas"]["Location.PublicRef"],
                    "create_fields": sorted(openapi["paths"]["/api/session"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"].keys()),
                    "results": [
                        {**row, "id": "<session-id-redacted>", "location": "<temporary-directory-redacted>"}
                        for row in sessions
                    ],
                },
                "session_listing": {
                    "search_limit_order": {"status": first_status, "count": len(first_data), "has_next_cursor": bool(cursor)},
                    "search_limit_cursor": {"status": next_status, "count": len((next_page or {}).get("data", [])), "has_next_cursor": bool(((next_page or {}).get("cursor") or {}).get("next"))},
                    "directory_filter": {"status": directory_status, "count": len((directory_result or {}).get("data", []))},
                    "exact_title_search": {"status": exact_status, "count": len((exact_result or {}).get("data", []))},
                    "cursor_value": "omitted; opaque token",
                },
                "isolation": {
                    "loopback_only": True,
                    "network_namespace_isolated": True,
                    "temporary_home_xdg_and_sessions": True,
                    "provider_credential_or_config_read": False,
                    "prompt_or_model_inference_requested": False,
                    "generated_password_recorded": False,
                },
            }
            print(json.dumps(output, sort_keys=True, indent=2))
        finally:
            server.terminate()
            try:
                server.wait(timeout=4)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
