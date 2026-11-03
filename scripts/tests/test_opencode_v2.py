import importlib.util
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

spec = importlib.util.spec_from_file_location("opencode_v2", Path(__file__).parents[1] / "opencode_v2.py")
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)

PERMISSIONS = [{"action": "*", "resource": "*", "effect": "deny"}]
ROW = {"id": "ses_1", "title": "test", "location": {"directory": "/work"},
       "model": {"providerID": "local", "id": "model"}, "permissions": PERMISSIONS}


def client():
    return v2.OpenCodeV2("http://127.0.0.1:1234", "user", "secret")


def test_create_read_and_validate_binding(monkeypatch):
    c = client()
    calls = []
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"data": dict(ROW)}
    monkeypatch.setattr(c, "_request", request)
    assert c.create_session("test", "/work", "local/model", PERMISSIONS) == "ses_1"
    c.validate_session("ses_1", "/work", "local/model", PERMISSIONS)
    assert calls[0][0:2] == ("POST", "/api/session")
    assert calls[0][2]["body"]["permissions"] == PERMISSIONS
    assert calls[1][0:2] == ("GET", "/api/session/ses_1")


@pytest.mark.parametrize("field,value", [("location", {"directory": "/other"}),
                                        ("model", {"providerID": "local", "id": "other"}),
                                        ("permissions", list(reversed(PERMISSIONS + [{"action": "shell", "resource": "*", "effect": "allow"}])) )])
def test_binding_drift_fails(monkeypatch, field, value):
    c = client()
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": {**ROW, field: value}})
    with pytest.raises(v2.V2Error, match="binding mismatch"):
        c.validate_session("ses_1", "/work", "local/model", PERMISSIONS)


def test_default_variant_is_equivalent_but_other_variant_is_not(monkeypatch):
    c = client()
    row = {**ROW, "model": {**ROW["model"], "variant": "default"}}
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": row})
    c.validate_session("ses_1", "/work", "local/model", PERMISSIONS)
    row["model"]["variant"] = "other"
    with pytest.raises(v2.V2Error, match="binding mismatch"):
        c.validate_session("ses_1", "/work", "local/model", PERMISSIONS)


def test_empty_permissions_are_wire_valid(monkeypatch):
    c = client()
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": {**ROW, "permissions": []}})
    assert c.create_session("test", "/work", "local/model", []) == "ses_1"


@pytest.mark.parametrize("directory,model,permissions", [
    ("/work/../other", "local/model", PERMISSIONS),
    ("/work\0x", "local/model", PERMISSIONS),
    ("/work", "local/ model", PERMISSIONS),
    ("/work", "local/model", [{"effect": "allow"}]),
])
def test_invalid_binding_never_creates(monkeypatch, directory, model, permissions):
    c = client()
    monkeypatch.setattr(c, "_request", lambda *a, **k: pytest.fail("unexpected request"))
    with pytest.raises(v2.V2Error, match="invalid session binding"):
        c.create_session("test", directory, model, permissions)


def test_discovery_requires_complete_noncyclic_pages(monkeypatch):
    c = client()
    calls = []
    def request(method, path, query):
        calls.append(query)
        if len(calls) == 1:
            return {"data": [{**ROW, "title": "test-other"}], "cursor": {"next": "next"}}
        return {"data": [ROW], "cursor": {"next": None}}
    monkeypatch.setattr(c, "_request", request)
    assert c.find_sessions("test", "/work") == ["ses_1"]
    assert calls[1]["search"] == "test" and calls[1]["directory"] == "/work"
    assert calls[1]["cursor"] == "next" and "order" not in calls[1]
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": [], "cursor": {"next": "cycle"}})
    with pytest.raises(v2.V2Error, match="cursor"):
        c.find_sessions("test", "/work")
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": [ROW, {**ROW, "id": "ses_2"}], "cursor": {"next": None}})
    with pytest.raises(v2.V2Error, match="ambiguous"):
        c.find_sessions("test", "/work")
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": [], "cursor": {}})
    with pytest.raises(v2.V2Error, match="page"):
        c.find_sessions("test", "/work")


def test_network_failures_are_sanitized_and_never_retried(monkeypatch):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"secret server response")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        c = v2.OpenCodeV2(f"http://127.0.0.1:{server.server_port}", "user", "secret")
        with pytest.raises(v2.V2Error) as failure:
            c.create_session("test", "/work", "local/model", PERMISSIONS)
        assert "secret" not in str(failure.value)
        assert calls == ["/api/session"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("mode", ["lost", "redirect", "html", "oversize"])
def test_rejects_untrusted_responses_without_retry(mode):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            if mode == "lost":
                self.connection.close()
                return
            self.send_response(302 if mode == "redirect" else 200)
            self.send_header("Content-Type", "text/html" if mode == "html" else "application/json")
            if mode == "redirect":
                self.send_header("Location", "/diverted")
            self.end_headers()
            self.wfile.write(b"x" * (v2.OpenCodeV2.MAX_RESPONSE + 1) if mode == "oversize" else b"{}")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        c = v2.OpenCodeV2(f"http://127.0.0.1:{server.server_port}", "user", "secret")
        with pytest.raises(v2.V2Error):
            c.create_session("test", "/work", "local/model", PERMISSIONS)
        assert calls == ["/api/session"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_bad_session_and_page_limit_fail_closed(monkeypatch):
    c = client()
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": {**ROW, "id": "ses_other"}})
    with pytest.raises(v2.V2Error, match="session response"):
        c.get_session("ses_1")
    monkeypatch.setattr(c, "MAX_PAGES", 2)
    pages = iter([{"data": [], "cursor": {"next": "one"}},
                  {"data": [], "cursor": {"next": "two"}}])
    monkeypatch.setattr(c, "_request", lambda *a, **k: next(pages))
    with pytest.raises(v2.V2Error, match="page limit"):
        c.find_sessions("test", "/work")
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": [{**ROW, "location": None}], "cursor": {"next": None}})
    with pytest.raises(v2.V2Error, match="page"):
        c.find_sessions("test", "/work")
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": [{**ROW, "location": {}}], "cursor": {"next": None}})
    with pytest.raises(v2.V2Error, match="page"):
        c.find_sessions("test", "/work")


@pytest.mark.parametrize("url", ["http://example.com:80", "http://127.0.0.1:99/path", "http://user:pass@127.0.0.1:99", "https://127.0.0.1:99"])
def test_rejects_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(v2.V2Error):
        v2.OpenCodeV2(url, "user", "secret")
