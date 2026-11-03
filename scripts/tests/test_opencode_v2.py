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


@pytest.mark.parametrize("mode", ["lost", "redirect", "html", "oversize", "empty204"])
def test_rejects_untrusted_responses_without_retry(mode):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            if mode == "lost":
                self.connection.close()
                return
            self.send_response(302 if mode == "redirect" else 204 if mode == "empty204" else 200)
            self.send_header("Content-Type", "text/html" if mode == "html" else "application/json")
            if mode == "redirect":
                self.send_header("Location", "/diverted")
            self.end_headers()
            if mode != "empty204":
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


def test_cancellation_requests_acknowledge_without_claiming_effect(monkeypatch):
    c = client()
    calls = []
    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"interrupted": True} if method == "POST" else {}
    monkeypatch.setattr(c, "_request", request)
    assert c.interrupt_session("ses_1") == {"status": "acknowledged", "interrupted": True}
    assert c.request_pending_deletion("ses_1", "msg_input") == {"status": "acknowledged"}
    assert calls == [("POST", "/api/session/ses_1/interrupt", {"query": {"resume": "false"}}),
                     ("DELETE", "/api/session/ses_1/inbox/msg_input", {"empty_ok": True})]
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"interrupted": False})
    assert c.interrupt_session("ses_1") == {"status": "acknowledged", "interrupted": False}
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"interrupted": "false"})
    with pytest.raises(v2.V2Error, match="interrupt acknowledgement"):
        c.interrupt_session("ses_1")
    monkeypatch.setattr(c, "_request", lambda *a, **k: {})
    with pytest.raises(v2.V2Error, match="interrupt acknowledgement"):
        c.interrupt_session("ses_1")


@pytest.mark.parametrize("operation", ["interrupt", "delete"])
def test_lost_cancellation_response_is_not_retried(monkeypatch, operation):
    c = client()
    calls = []
    def lost(method, path, **kwargs):
        calls.append((method, path))
        raise v2.V2Error("server request failed")
    monkeypatch.setattr(c, "_request", lost)
    with pytest.raises(v2.V2Error):
        if operation == "interrupt":
            c.interrupt_session("ses_1")
        else:
            c.request_pending_deletion("ses_1", "msg_input")
    assert len(calls) == 1


@pytest.mark.parametrize("status", [200, 204])
def test_pending_delete_accepts_only_empty_204(status):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def do_DELETE(self):
            calls.append(self.path)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if status == 200:
                self.wfile.write(b"{}")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        c = v2.OpenCodeV2(f"http://127.0.0.1:{server.server_port}", "user", "secret")
        if status == 204:
            assert c.request_pending_deletion("ses_1", "msg_input") == {"status": "acknowledged"}
        else:
            with pytest.raises(v2.V2Error):
                c.request_pending_deletion("ses_1", "msg_input")
        assert calls == ["/api/session/ses_1/inbox/msg_input"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("outcome", ["succeeded", "failed", "interrupted"])
def test_terminal_observation_requires_two_stable_single_input_snapshots(monkeypatch, outcome):
    c = client()
    digest = hashlib.sha256(b"input").hexdigest()
    rows = [{"id": "msg_input", "type": "user", "text": "input", "time": {"created": 1}},
            {"id": "msg_reply", "type": "assistant", "time": {"created": 2}, "agent": "build",
             "model": ROW["model"], "content": []},
            {"id": "msg_idle", "type": "idle", "outcome": outcome, "time": {"created": 3}}]
    calls = []
    def request(method, path, **kwargs):
        calls.append((path, kwargs))
        if path == "/api/session/ses_1": return {"data": ROW}
        if path == "/api/session/active": return {"data": {}}
        if path.endswith("/inbox"): return {"data": []}
        if path.endswith("/message"): return {"data": rows, "cursor": {"next": None}}
        pytest.fail("unexpected request")
    monkeypatch.setattr(c, "_request", request)
    result = c.observe_terminal("ses_1", "msg_input", digest, "/work", "local/model", PERMISSIONS)
    interval = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    assert result == {"status": "terminal-observed", "outcome": outcome, "terminal_id": "msg_idle",
                      "session_id": "ses_1", "prompt_id": "msg_input", "text_sha256": digest,
                      "interval_sha256": hashlib.sha256(interval.encode()).hexdigest(),
                      "correlation": "single-input-two-snapshot", "atomicity": "not-established"}
    assert len([p for p, _ in calls if p.endswith("/message")]) == 2
    assert all(k["query"]["order"] == "asc" for p, k in calls if p.endswith("/message"))


@pytest.mark.parametrize("mode", ["active", "inbox", "foreign", "digest", "stale", "changed", "binding", "queued_during_read", "model_drift", "attachment"])
def test_terminal_observation_refuses_ambiguous_state(monkeypatch, mode):
    c = client()
    digest = hashlib.sha256(b"input").hexdigest()
    rows = [{"id": "msg_input", "type": "user", "text": "input", "time": {"created": 1}},
            {"id": "msg_idle", "type": "idle", "outcome": "succeeded", "time": {"created": 2}}]
    if mode == "foreign": rows.insert(1, {"id": "msg_foreign", "type": "user", "text": "other", "time": {"created": 1}})
    if mode == "stale": rows.insert(0, {"id": "msg_old_idle", "type": "idle", "outcome": "succeeded", "time": {"created": 0}})
    if mode == "digest": rows[0]["text"] = "other"
    if mode == "attachment": rows[0]["files"] = ["extra"]
    if mode == "model_drift": rows.insert(1, {"id": "msg_reply", "type": "assistant", "time": {"created": 1},
                                               "agent": "build", "model": {"providerID": "local", "id": "other"}, "content": []})
    pages = 0
    inbox_reads = 0
    def request(method, path, **kwargs):
        nonlocal pages, inbox_reads
        if path == "/api/session/ses_1":
            return {"data": {**ROW, "permissions": []} if mode == "binding" else ROW}
        if path == "/api/session/active": return {"data": {"ses_1": {"type": "running"}} if mode == "active" else {}}
        if path.endswith("/inbox"):
            inbox_reads += 1
            return {"data": [{"id": "queued"}] if mode == "inbox" or (mode == "queued_during_read" and inbox_reads == 2) else []}
        if path.endswith("/message"):
            pages += 1
            return {"data": rows + ([{"id": "msg_new", "type": "idle", "outcome": "succeeded", "time": {"created": 3}}] if mode == "changed" and pages == 2 else []),
                    "cursor": {"next": None}}
        pytest.fail("unexpected request")
    monkeypatch.setattr(c, "_request", request)
    if mode in ("binding", "model_drift", "attachment"):
        with pytest.raises(v2.V2Error):
            c.observe_terminal("ses_1", "msg_input", digest, "/work", "local/model", PERMISSIONS)
    else:
        result = c.observe_terminal("ses_1", "msg_input", digest, "/work", "local/model", PERMISSIONS)
        assert result["status"] == ("active" if mode == "active" else "unknown")


def test_terminal_cursor_cycle_is_uncertainty(monkeypatch):
    c = client()
    def request(method, path, **kwargs):
        if path == "/api/session/ses_1": return {"data": ROW}
        if path == "/api/session/active": return {"data": {}}
        if path.endswith("/inbox"): return {"data": []}
        return {"data": [], "cursor": {"next": "cycle"}}
    monkeypatch.setattr(c, "_request", request)
    with pytest.raises(v2.V2Error, match="cursor"):
        c.observe_terminal("ses_1", "msg_input", hashlib.sha256(b"input").hexdigest(), "/work", "local/model", PERMISSIONS)


def test_terminal_active_after_history_is_not_terminal(monkeypatch):
    c = client()
    calls = 0
    def request(method, path, **kwargs):
        nonlocal calls
        if path == "/api/session/ses_1": return {"data": ROW}
        if path == "/api/session/active":
            calls += 1
            return {"data": {"ses_1": {"type": "running"}} if calls == 2 else {}}
        if path.endswith("/inbox"): return {"data": []}
        return {"data": [{"id": "msg_input", "type": "user", "text": "input", "time": {"created": 1}},
                         {"id": "msg_idle", "type": "idle", "outcome": "succeeded", "time": {"created": 2}}],
                "cursor": {"next": None}}
    monkeypatch.setattr(c, "_request", request)
    assert c.observe_terminal("ses_1", "msg_input", hashlib.sha256(b"input").hexdigest(), "/work", "local/model", PERMISSIONS) == {"status": "active"}


@pytest.mark.parametrize("mode", ["empty", "active", "inbox", "history", "late_queue", "cycle"])
def test_empty_session_observation_fails_closed(monkeypatch, mode):
    c = client()
    inbox_reads = 0
    def request(method, path, **kwargs):
        nonlocal inbox_reads
        if path == "/api/session/active": return {"data": {"ses_1": {"type": "running"}} if mode == "active" else {}}
        if path.endswith("/inbox"):
            inbox_reads += 1
            return {"data": [{"id": "queued"}] if mode == "inbox" or (mode == "late_queue" and inbox_reads == 2) else []}
        return {"data": [{"id": "input"}] if mode == "history" else [],
                "cursor": {"next": "cycle" if mode == "cycle" else None}}
    monkeypatch.setattr(c, "_request", request)
    if mode == "cycle":
        with pytest.raises(v2.V2Error, match="cursor"):
            c.empty_session_observed("ses_1")
    else:
        assert c.empty_session_observed("ses_1") is (mode == "empty")


@pytest.mark.parametrize("url", ["http://example.com:80", "http://127.0.0.1:99/path", "http://user:pass@127.0.0.1:99", "https://127.0.0.1:99"])
def test_rejects_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(v2.V2Error):
        v2.OpenCodeV2(url, "user", "secret")
