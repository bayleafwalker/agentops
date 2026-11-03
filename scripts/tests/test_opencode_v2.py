import importlib.util
import hashlib
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


def test_submit_validates_acknowledged_identity_and_payload(monkeypatch):
    c = client()
    text = "synthetic input"
    ack = {"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": text},
           "delivery": "steer", "time": {"created": 1}}
    calls = []
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"data": ack}
    monkeypatch.setattr(c, "_request", request)
    result = c.submit_prompt("ses_1", "msg_input", text)
    assert result["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert calls[0][2]["body"] == {"id": "msg_input", "text": text}
    ack["payload"]["text"] = "other"
    with pytest.raises(v2.V2Error, match="acknowledgement"):
        c.submit_prompt("ses_1", "msg_input", text)


def test_admission_observes_inbox_and_paginated_messages_or_unknown(monkeypatch):
    c = client()
    digest = hashlib.sha256(b"synthetic").hexdigest()
    inbox = {"data": [{"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": "synthetic"}}]}
    pages = [{"data": [{"id": "assistant_1", "type": "assistant"}], "cursor": {"next": "next"}},
             {"data": [{"id": "msg_input", "type": "user", "text": "synthetic"}], "cursor": {"next": None}}]
    def request(method, path, **kwargs):
        return inbox if path.endswith("/inbox") else pages.pop(0)
    monkeypatch.setattr(c, "_request", request)
    assert c.observe_admission("ses_1", "msg_input", digest)["sources"] == ["inbox", "message"]
    monkeypatch.setattr(c, "_request", lambda method, path, **kw: {"data": []} if path.endswith("/inbox")
                        else {"data": [], "cursor": {"next": None}})
    assert c.observe_admission("ses_1", "msg_input", digest)["status"] == "unknown"


@pytest.mark.parametrize("source", ["inbox", "message"])
def test_admission_accepts_either_projection_when_other_is_empty(monkeypatch, source):
    c = client()
    digest = hashlib.sha256(b"input").hexdigest()
    inbox = [{"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": "input"}}]
    messages = [{"id": "msg_input", "type": "user", "text": "input"}]
    monkeypatch.setattr(c, "_request", lambda method, path, **kw:
        {"data": inbox if source == "inbox" else []} if path.endswith("/inbox") else
        {"data": messages if source == "message" else [], "cursor": {"next": None}})
    assert c.observe_admission("ses_1", "msg_input", digest)["sources"] == [source]


def test_admission_rejects_conflict_and_incomplete_pagination(monkeypatch):
    c = client()
    digest = hashlib.sha256(b"synthetic").hexdigest()
    inbox = {"data": [{"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": "other"}}]}
    monkeypatch.setattr(c, "_request", lambda method, path, **kw: inbox if path.endswith("/inbox")
                        else {"data": [], "cursor": {"next": None}})
    with pytest.raises(v2.V2Error, match="conflicting input payload"):
        c.observe_admission("ses_1", "msg_input", digest)
    monkeypatch.setattr(c, "_request", lambda method, path, **kw: {"data": []} if path.endswith("/inbox")
                        else {"data": [], "cursor": {"next": "cycle"}})
    with pytest.raises(v2.V2Error, match="cursor"):
        c.observe_admission("ses_1", "msg_input", digest)


@pytest.mark.parametrize("field,value", [("delivery", None), ("time", {"created": True}),
                                        ("payload", {"text": "input", "files": ["extra"]}),
                                        ("sessionID", "ses_other")])
def test_submit_rejects_malformed_ack(monkeypatch, field, value):
    c = client()
    ack = {"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": "input"},
           "delivery": "steer", "time": {"created": 1}, field: value}
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"data": ack})
    with pytest.raises(v2.V2Error, match="acknowledgement"):
        c.submit_prompt("ses_1", "msg_input", "input")


def test_admission_rejects_duplicate_and_missing_pages(monkeypatch):
    c = client()
    digest = hashlib.sha256(b"input").hexdigest()
    row = {"id": "msg_input", "type": "user", "text": "input"}
    pages = iter([{"data": [row], "cursor": {"next": "next"}},
                  {"data": [row], "cursor": {"next": None}}])
    monkeypatch.setattr(c, "_request", lambda method, path, **kw: {"data": []} if path.endswith("/inbox") else next(pages))
    with pytest.raises(v2.V2Error, match="duplicate"):
        c.observe_admission("ses_1", "msg_input", digest)
    monkeypatch.setattr(c, "_request", lambda method, path, **kw: {"data": []})
    with pytest.raises(v2.V2Error, match="message page"):
        c.observe_admission("ses_1", "msg_input", digest)


def test_lost_prompt_response_does_not_retry(monkeypatch):
    c = client()
    calls = []
    def lost(method, path, **kwargs):
        calls.append((method, path))
        raise v2.V2Error("server request failed")
    monkeypatch.setattr(c, "_request", lost)
    with pytest.raises(v2.V2Error):
        c.submit_prompt("ses_1", "msg_input", "input")
    assert calls == [("POST", "/api/session/ses_1/prompt")]


@pytest.mark.parametrize("url", ["http://example.com:80", "http://127.0.0.1:99/path", "http://user:pass@127.0.0.1:99", "https://127.0.0.1:99"])
def test_rejects_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(v2.V2Error):
        v2.OpenCodeV2(url, "user", "secret")
