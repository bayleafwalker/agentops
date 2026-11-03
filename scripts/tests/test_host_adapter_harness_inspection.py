"""Read-only harness diagnosis must not qualify or contact a redirected server."""
import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_adapter as ha  # noqa: E402


@pytest.fixture
def server():
    replies = {}
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            seen.append((self.path, self.headers.get("Authorization")))
            status, content_type, body, extra = replies.get(
                self.path, (404, "text/plain", b"", {}))
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for key, value in extra.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

    instance = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance, replies, seen
    instance.shutdown()
    instance.server_close()
    thread.join()


def response(value):
    return 200, "application/json; charset=utf-8", json.dumps(value).encode(), {}


def v2_info(version="2.0.32"):
    return {"version": version, "pid": 123, "urls": ["http://127.0.0.1"],
            "paths": {"tmp": "/tmp/private"}, "capabilities": {"persistentPty": True}}


def inspect(server):
    instance, _, _ = server
    return ha.OpenCodeServe(f"http://127.0.0.1:{instance.server_address[1]}", password="synthetic-secret").inspect_harness()


def test_v2_identity_is_explicitly_unsupported_and_redacted(server):
    _, replies, seen = server
    replies["/api/info"] = response(v2_info())
    replies["/global/health"] = (200, "text/html", b"<html>frontend</html>", {})
    report = inspect(server)
    assert report == {"status": "unsupported-harness-api", "version": "2.0.32", "launch_qualified": False}
    assert {p for p, _ in seen} == {"/api/info", "/global/health"}
    assert all(auth and auth.startswith("Basic ") for _, auth in seen)
    assert "synthetic-secret" not in json.dumps(report)
    assert "/tmp/private" not in json.dumps(report)


def test_legacy_health_is_observation_not_qualification(server):
    _, replies, _ = server
    replies["/global/health"] = response({"healthy": True, "version": "1.19.0"})
    assert inspect(server) == {"status": "legacy-api-observed", "version": "1.19.0", "launch_qualified": False}


def test_unknown_future_major_is_unsupported(server):
    _, replies, _ = server
    replies["/api/info"] = response(v2_info("3.0.0"))
    assert inspect(server) == {"status": "unsupported-harness-api", "version": "3.0.0", "launch_qualified": False}


@pytest.mark.parametrize("info", [None, {}, {"version": "2.0.32"}, v2_info("not-a-version"),
                                  v2_info("1.19.0"), {**v2_info(), "pid": True},
                                  {**v2_info(), "pid": -1}, v2_info("9" * 5000 + ".0.0")])
def test_invalid_v2_identity_never_qualifies(server, info):
    _, replies, _ = server
    replies["/api/info"] = response(info)
    assert inspect(server)["status"] == "unavailable"


def test_conflicting_v1_and_v2_identities_are_ambiguous(server):
    _, replies, _ = server
    replies["/api/info"] = response(v2_info())
    replies["/global/health"] = response({"healthy": True, "version": "1.19.0"})
    assert inspect(server) == {"status": "unavailable", "reason": "ambiguous-server", "launch_qualified": False}


def test_malformed_v2_identity_does_not_become_legacy(server):
    _, replies, _ = server
    replies["/api/info"] = response({"version": "2.0.32"})
    replies["/global/health"] = response({"healthy": True, "version": "1.19.0"})
    assert inspect(server)["status"] == "unavailable"


def test_redirect_is_not_followed_and_credentials_are_not_forwarded(server):
    instance, replies, seen = server
    replies["/api/info"] = (302, "text/plain", b"", {"Location": f"http://127.0.0.1:{instance.server_address[1]}/sink"})
    assert inspect(server)["status"] == "unavailable"
    assert "/sink" not in [path for path, _ in seen]


def test_proxy_environment_does_not_divert_loopback_credentials(server, monkeypatch):
    _, replies, seen = server
    replies["/api/info"] = response(v2_info())
    for key in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    assert inspect(server)["status"] == "unsupported-harness-api"
    assert [path for path, _ in seen] == ["/api/info", "/global/health"]


def test_oversized_body_and_html_are_unavailable(server):
    _, replies, _ = server
    replies["/api/info"] = (200, "application/json", b'"' + b'x' * 40000 + b'"', {})
    replies["/global/health"] = (200, "text/html", b"<html>not-json</html>", {})
    assert inspect(server)["status"] == "unavailable"


def test_authentication_failure_and_malformed_json_are_unavailable(server):
    _, replies, _ = server
    replies["/api/info"] = (401, "application/json", b'{"error":"private"}', {})
    replies["/global/health"] = (200, "application/json", b'{broken', {})
    report = inspect(server)
    assert report["status"] == "unavailable"
    assert "private" not in json.dumps(report)


@pytest.mark.parametrize("suffix", ["/prefix", "?query=secret", "#fragment"])
def test_non_origin_url_is_not_used(server, suffix):
    instance, _, seen = server
    harness = ha.OpenCodeServe(f"http://127.0.0.1:{instance.server_address[1]}{suffix}", password="synthetic")
    assert harness.inspect_harness()["reason"] == "configuration"
    assert seen == []


def test_userinfo_in_url_is_not_used(server):
    instance, _, seen = server
    harness = ha.OpenCodeServe(f"http://user:secret@127.0.0.1:{instance.server_address[1]}")
    assert harness.inspect_harness()["reason"] == "configuration"
    assert seen == []


def test_cli_is_read_only_without_owner_profile(server, monkeypatch, capsys, tmp_path):
    instance, replies, _ = server
    replies["/api/info"] = response(v2_info())
    monkeypatch.setattr(ha, "_serve_password", lambda: "synthetic-secret")
    status = ha.main(["--state-dir", str(tmp_path / "unused"), "--serve-url",
                      f"http://127.0.0.1:{instance.server_address[1]}", "inspect-harness"])
    captured = capsys.readouterr()
    assert status == 2
    assert json.loads(captured.out)["status"] == "unsupported-harness-api"
    assert "synthetic-secret" not in captured.out + captured.err
    assert not (tmp_path / "unused").exists()


def test_missing_credential_is_reported_without_exception(monkeypatch, capsys):
    monkeypatch.setattr(ha, "_serve_password", lambda: None)
    assert ha.main(["inspect-harness"]) == 2
    assert json.loads(capsys.readouterr().out)["reason"] == "configuration"
