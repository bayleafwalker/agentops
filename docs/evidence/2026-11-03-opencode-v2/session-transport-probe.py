#!/usr/bin/env python3
"""Live disposable qualification of the dormant OpenCodeV2 transport.

Run on devbox with the pinned 2.0.32 binary in bwrap --unshare-net. The exact
module bytes are bound read-only at /tmp/opencode_v2.py; this probe imports
that module and creates only synthetic local sessions. No prompts are sent.
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
import time
import urllib.error
import urllib.parse
import urllib.request


BINARY = "/nix/store/9ysv2ynpka84idp745mcd8l0ayc2f102-opencode-2.0.32/bin/opencode"
MODULE_PATH = pathlib.Path("/tmp/opencode_v2.py")
MODULE_SHA256 = "13bbcf6f74e41670d7de32dbf3c7a199ef19b42d444577012dbf8c67343990f0"
PERMISSIONS = [{"action": "*", "resource": "*", "effect": "deny"}]
ALT_PERMISSIONS = [{"action": "shell", "resource": "*", "effect": "deny"}]


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def load_transport():
    digest = hashlib.sha256(MODULE_PATH.read_bytes()).hexdigest()
    require(digest == MODULE_SHA256, "imported module hash mismatch")
    spec = importlib.util.spec_from_file_location("opencode_v2", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    value = sock.getsockname()[1]
    sock.close()
    return value


def main():
    v2 = load_transport()
    root = pathlib.Path(tempfile.mkdtemp(prefix="opencode-v2-live-", dir="/tmp"))
    server = None
    try:
        for name in ("home", "config", "data", "state", "cache", "work"):
            (root / name).mkdir(mode=0o700)
        work = root / "work"
        (work / "opencode.json").write_text(json.dumps({
            "model": "mock/fake",
            "provider": {
                "mock": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "loopback-only synthetic provider",
                    "options": {"baseURL": "http://127.0.0.1:1/v1", "apiKey": "synthetic-only"},
                    "models": {
                        "fake": {"name": "Fake", "tool_call": True,
                                 "limit": {"context": 128000, "output": 4096}},
                        "changed-never-connect": {"name": "Changed fake", "tool_call": True,
                                                  "limit": {"context": 128000, "output": 4096}},
                    },
                }
            },
        }), encoding="utf-8")
        port = free_port()
        username = "opencode"
        password = secrets.token_urlsafe(32)
        auth = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
        env = {
            "PATH": "/run/current-system/sw/bin:/usr/bin:/bin",
            "HOME": str(root / "home"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(root / "data"),
            "XDG_STATE_HOME": str(root / "state"),
            "XDG_CACHE_HOME": str(root / "cache"),
            "OPENCODE_SERVER_USERNAME": username,
            "OPENCODE_SERVER_PASSWORD": password,
        }
        server = subprocess.Popen(
            [BINARY, "serve", "--hostname", "127.0.0.1", "--port", str(port)],
            env=env, cwd=str(work), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        origin = f"http://127.0.0.1:{port}"
        client = v2.OpenCodeV2(origin, username, password, timeout=8)
        raw_calls = []

        def raw(method, path, body=None):
            payload = None if body is None else json.dumps(body).encode()
            request = urllib.request.Request(
                origin + path, method=method, data=payload,
                headers={"Authorization": auth, "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=8) as response:
                    data = response.read()
                    return response.status, json.loads(data) if data else None
            except urllib.error.HTTPError as exc:
                data = exc.read()
                try:
                    parsed = json.loads(data) if data else None
                except ValueError:
                    parsed = None
                return exc.code, parsed

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
        require(info_status == 200 and info.get("version") == "2.0.32", "pinned server identity check failed")
        server_version = info["version"]

        original_request = client._request

        def traced(method, path, query=None, body=None):
            result = original_request(method, path, query=query, body=body)
            if method == "POST" and path == "/api/session":
                data = result.get("data")
                raw_calls.append({
                    "kind": "create",
                    "envelope_keys": sorted(result),
                    "data_keys": sorted(data) if isinstance(data, dict) else None,
                })
            elif method == "GET" and path == "/api/session":
                rows = result.get("data", [])
                q = query or {}
                paging = result.get("cursor") or {}
                raw_calls.append({
                    "kind": "list", "page": len([call for call in raw_calls
                                                       if call["kind"] == "list"
                                                       and call.get("search_value") == q.get("search")
                                                       and call.get("directory_matches_expected") == (q.get("directory") == directory)]) + 1,
                    "query_keys": sorted(q), "limit": q.get("limit"),
                    "search_present": bool(q.get("search")),
                    "search_value": q.get("search"),
                    "directory_present": bool(q.get("directory")),
                    "directory_matches_expected": q.get("directory") == directory,
                    "cursor_present": bool(q.get("cursor")),
                    "row_count": len(rows),
                    "row_keys": sorted(rows[0]) if rows else [],
                    "cursor_keys": sorted(paging),
                    "exact_title_count": sum(row.get("title") == q.get("search") for row in rows),
                    "next_cursor_present": paging.get("next") is not None,
                })
            elif method == "GET" and path.startswith("/api/session/"):
                data = result.get("data")
                if isinstance(data, dict):
                    raw_calls.append({
                        "kind": "get",
                        "envelope_keys": sorted(result),
                        "data_keys": sorted(data),
                    })
            return result

        client._request = traced
        directory = str(work)
        model_id = "mock/fake"

        # Actual create + get response shape + exact binding check.
        basic_id = client.create_session("binding-check", directory, model_id, PERMISSIONS)
        basic = client.get_session(basic_id)
        client.validate_session(basic_id, directory, model_id, PERMISSIONS)
        require(basic.get("title") == "binding-check", "created title did not round-trip")
        require(basic.get("location", {}).get("directory") == directory, "location did not round-trip")
        actual_model = basic.get("model")
        model_round_trip = (isinstance(actual_model, dict)
                            and actual_model.get("providerID") == "mock"
                            and actual_model.get("id") == "fake"
                            and actual_model.get("variant", "default") == "default")
        require(model_round_trip, "model did not round-trip")
        require(basic.get("permissions") == PERMISSIONS, "permissions did not round-trip")

        # Directory mismatch validation is real readback, but not server-side mutation.
        try:
            client.validate_session(basic_id, directory + "/wrong", model_id, PERMISSIONS)
            wrong_directory_rejected = False
            wrong_directory_failure = None
        except v2.V2Error as exc:
            wrong_directory_failure = str(exc)
            wrong_directory_rejected = wrong_directory_failure == "session binding mismatch"
        require(wrong_directory_rejected, "wrong expected directory was not rejected")

        # Exact filtering and full page exhaustion: 111 search hits, one exact
        # title. The exact row is surrounded by >50 hits on both sides.
        exact_title = "v2-full-target"
        for index in range(55):
            client.create_session(f"{exact_title}-before-{index:02d}", directory, model_id, PERMISSIONS)
        exact_id = client.create_session(exact_title, directory, model_id, PERMISSIONS)
        for index in range(55):
            client.create_session(f"{exact_title}-after-{index:02d}", directory, model_id, PERMISSIONS)
        list_start = len(raw_calls)
        found = client.find_sessions(exact_title, directory)
        pages = [call for call in raw_calls[list_start:] if call["kind"] == "list"]
        require(found == [exact_id], "exact-title discovery returned unexpected identity")
        require(sum(call["row_count"] for call in pages) >= 111, "search did not expose all synthetic hits")
        require(len(pages) >= 3, "find_sessions did not exhaust pages past PAGE_SIZE")
        require(sum(call["exact_title_count"] for call in pages) == 1, "exact-title match count changed")
        require(pages[-1]["next_cursor_present"] is False, "last discovery page retained a cursor")
        wrong_directory_start = len(raw_calls)
        wrong_directory_matches = client.find_sessions(exact_title, directory + "/wrong")
        wrong_directory_pages = [call for call in raw_calls[wrong_directory_start:] if call["kind"] == "list"]
        require(wrong_directory_matches == [], "wrong directory discovery returned a session")

        # Duplicate exact identities separated by more than a full page.
        duplicate_title = "v2-duplicate-target"
        duplicate_ids = [client.create_session(duplicate_title, directory, model_id, PERMISSIONS)]
        for index in range(60):
            client.create_session(f"{duplicate_title}-near-{index:02d}", directory, model_id, PERMISSIONS)
        duplicate_ids.append(client.create_session(duplicate_title, directory, model_id, PERMISSIONS))
        duplicate_start = len(raw_calls)
        try:
            client.find_sessions(duplicate_title, directory)
            duplicate_error = None
        except v2.V2Error as exc:
            duplicate_error = str(exc)
        duplicate_pages = [call for call in raw_calls[duplicate_start:] if call["kind"] == "list"]
        require(duplicate_error == "ambiguous session identity", "duplicate exact titles were not rejected as ambiguous")
        require(len(duplicate_pages) >= 2, "duplicate discovery did not traverse multiple pages")
        require(sum(call["exact_title_count"] for call in duplicate_pages) == 2, "two duplicate identities were not observed")

        # Permission drift through actual PATCH, then model drift through actual
        # model route. Both are read back through the imported transport.
        patch_status, _ = raw("PATCH", "/api/session/" + basic_id, {"permissions": ALT_PERMISSIONS})
        after_permission = client.get_session(basic_id)
        try:
            client.validate_session(basic_id, directory, model_id, PERMISSIONS)
            old_permissions_rejected = False
            old_permissions_failure = None
        except v2.V2Error as exc:
            old_permissions_failure = str(exc)
            old_permissions_rejected = old_permissions_failure == "session binding mismatch"
        client.validate_session(basic_id, directory, model_id, ALT_PERMISSIONS)
        permissions_read_back = after_permission.get("permissions") == ALT_PERMISSIONS
        require(patch_status == 204, "permissions PATCH did not return 204")
        require(permissions_read_back, "permissions PATCH did not persist")
        require(old_permissions_rejected, "stale permissions binding was accepted")

        next_model = {"providerID": "mock", "id": "changed-never-connect"}
        model_status, _ = raw("POST", "/api/session/" + basic_id + "/model", {"model": next_model})
        after_model = client.get_session(basic_id)
        try:
            client.validate_session(basic_id, directory, model_id, ALT_PERMISSIONS)
            old_model_rejected = False
            old_model_failure = None
        except v2.V2Error as exc:
            old_model_failure = str(exc)
            old_model_rejected = old_model_failure == "session binding mismatch"
        model_read_back = (isinstance(after_model.get("model"), dict)
                           and after_model["model"].get("providerID") == next_model["providerID"]
                           and after_model["model"].get("id") == next_model["id"])
        require(model_status == 204, "model update did not return 204")
        require(model_read_back, "model update did not persist")
        require(old_model_rejected, "stale model binding was accepted")
        client.validate_session(basic_id, directory, "mock/changed-never-connect", ALT_PERMISSIONS)

        output = {
            "server_version": server_version,
            "imported_module_sha256": MODULE_SHA256,
            "transport_observations": {
                "create_session": {
                    "created": True,
                    "create_envelope_keys": next(call["envelope_keys"] for call in raw_calls if call["kind"] == "create"),
                    "create_data_keys": next(call["data_keys"] for call in raw_calls if call["kind"] == "create"),
                    "get_session_keys": sorted(basic),
                    "session_shape": {
                        "model": {key: basic.get("model", {}).get(key)
                                  for key in ("providerID", "id", "variant")
                                  if key in basic.get("model", {})},
                        "location_keys": sorted(basic.get("location", {})),
                        "permissions_rule_keys": sorted(basic.get("permissions", [{}])[0]),
                        "permissions_effect": basic.get("permissions", [{}])[0].get("effect"),
                        "time_keys": sorted(basic.get("time", {})),
                        "tokens_keys": sorted(basic.get("tokens", {})),
                        "project_id_type": type(basic.get("projectID")).__name__,
                    },
                    "get_envelope_keys": next(call["envelope_keys"] for call in raw_calls if call["kind"] == "get"),
                    "binding_round_trip": True,
                    "id_redacted": True,
                    "directory_redacted": True,
                },
                "discovery": {
                    "page_size": client.PAGE_SIZE,
                    "expected_search_hits": 111,
                    "pages_observed": pages,
                    "returned_exact_identity": found == [exact_id],
                    "wrong_directory_result_count": len(wrong_directory_matches),
                    "wrong_directory_pages": wrong_directory_pages,
                    "duplicate_title_pages": duplicate_pages,
                    "duplicate_result": duplicate_error,
                    "duplicate_ids_redacted": True,
                },
                "binding_drift": {
                    "wrong_expected_directory_rejected": wrong_directory_rejected,
                    "wrong_directory_failure": wrong_directory_failure,
                    "permissions_patch_status": patch_status,
                    "permissions_read_back": permissions_read_back,
                    "old_permissions_rejected": old_permissions_rejected,
                    "old_permissions_failure": old_permissions_failure,
                    "new_permissions_validated": True,
                    "model_route_status": model_status,
                    "model_read_back": model_read_back,
                    "model_variant": actual_model.get("variant"),
                    "changed_model_variant": (after_model.get("model") or {}).get("variant"),
                    "old_model_rejected": old_model_rejected,
                    "old_model_failure": old_model_failure,
                    "directory_server_side_mutation": "not available in tested API; only mismatched expected binding was checked",
                },
            },
            "isolation": {
                "network_namespace_unshared": True,
                "only_loopback_server": True,
                "temporary_home_xdg_and_sessions": True,
                "provider_credentials_or_config_read": False,
                "prompts_sent": False,
                "generated_auth_secret_recorded": False,
            },
        }
        print(json.dumps(output, sort_keys=True, indent=2))
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=4)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
