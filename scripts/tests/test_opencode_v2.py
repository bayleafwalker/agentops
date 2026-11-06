import importlib.machinery
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
    inbox = [{"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": "input"},
              "delivery": "queue", "time": {"created": 1}}]
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


@pytest.mark.parametrize("mode,expected", [("queued", "queued"), ("running", "running"),
                                           ("foreign", "unknown"), ("active_queue", "unknown"),
                                           ("terminal", "unknown"), ("changed", "unknown"),
                                           ("foreign_assistant", "unknown"), ("end_active", "unknown")])
def test_cancellation_target_requires_stable_sole_input(monkeypatch, mode, expected):
    c = client()
    digest = hashlib.sha256(b"input").hexdigest()
    inbox = [{"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": "input"},
              "delivery": "queue", "time": {"created": 1}}]
    rows = [{"id": "msg_input", "type": "user", "text": "input", "time": {"created": 1}}]
    inbox_reads = 0
    active_reads = 0
    def request(method, path, **kwargs):
        nonlocal inbox_reads, active_reads
        if path == "/api/session/ses_1": return {"data": ROW}
        if path == "/api/session/active":
            active_reads += 1
            return {"data": {"ses_1": {"type": "running"}} if mode in ("running", "foreign", "active_queue", "foreign_assistant") or (mode == "end_active" and active_reads > 1) else {}}
        if path.endswith("/inbox"):
            inbox_reads += 1
            present = mode in ("queued", "active_queue") or (mode == "changed" and inbox_reads > 1)
            return {"data": inbox if present else []}
        batch = list(rows) if mode in ("running", "foreign", "terminal", "foreign_assistant") else []
        if mode == "foreign": batch.append({"id": "msg_other", "type": "user", "text": "other", "time": {"created": 2}})
        if mode == "terminal": batch.append({"id": "msg_idle", "type": "idle", "outcome": "succeeded", "time": {"created": 2}})
        if mode == "foreign_assistant": batch.append({"id": "msg_reply", "type": "assistant", "agent": "build", "content": [],
            "time": {"created": 2}, "model": {"providerID": "other", "id": "model"}})
        return {"data": batch, "cursor": {"next": None}}
    monkeypatch.setattr(c, "_request", request)
    assert c.inspect_cancellation_target("ses_1", "msg_input", digest, "/work", "local/model", PERMISSIONS)["status"] == expected


@pytest.mark.parametrize("field,value", [("delivery", None), ("time", {"created": True}),
                                        ("payload", {"text": "input", "files": ["extra"]})])
def test_cancellation_target_rejects_malformed_pending_input(monkeypatch, field, value):
    c = client()
    item = {"id": "msg_input", "sessionID": "ses_1", "type": "user", "payload": {"text": "input"},
            "delivery": "queue", "time": {"created": 1}, field: value}
    def request(method, path, **kwargs):
        if path == "/api/session/ses_1": return {"data": ROW}
        if path == "/api/session/active": return {"data": {}}
        if path.endswith("/inbox"): return {"data": [item]}
        return {"data": [], "cursor": {"next": None}}
    monkeypatch.setattr(c, "_request", request)
    assert c.inspect_cancellation_target("ses_1", "msg_input", hashlib.sha256(b"input").hexdigest(),
                                         "/work", "local/model", PERMISSIONS)["status"] == "unknown"


def test_cancellation_target_rejects_cyclic_pagination(monkeypatch):
    c = client()
    def request(method, path, **kwargs):
        if path == "/api/session/ses_1": return {"data": ROW}
        if path == "/api/session/active": return {"data": {}}
        if path.endswith("/inbox"): return {"data": []}
        return {"data": [], "cursor": {"next": "cycle"}}
    monkeypatch.setattr(c, "_request", request)
    with pytest.raises(v2.V2Error, match="cursor"):
        c.inspect_cancellation_target("ses_1", "msg_input", hashlib.sha256(b"input").hexdigest(),
                                       "/work", "local/model", PERMISSIONS)


@pytest.mark.parametrize("url", ["http://example.com:80", "http://127.0.0.1:99/path", "http://user:pass@127.0.0.1:99", "https://127.0.0.1:99"])
def test_rejects_nonlocal_or_ambiguous_origins(url):
    with pytest.raises(v2.V2Error):
        v2.OpenCodeV2(url, "user", "secret")


# --- Stateful fake server, restart recovery and negative controls -----------------------------

DIGEST = hashlib.sha256(b"input").hexdigest()
BIND = ("/work", "local/model", PERMISSIONS)


class FakeServer:
    """In-memory v2 server state; clients are disposable, like a restarted owner process."""

    def __init__(self):
        self.sessions, self.inbox, self.messages, self.running = {}, {}, {}, set()
        self.posts = []
        self.lose = set()  # POST paths whose response is lost after the effect happened
        self.page = 50
        self.clock = 0

    def tick(self):
        self.clock += 1
        return {"created": self.clock}

    def attach(self, c):
        c._request = self.request
        self.error = c.__init__.__globals__["V2Error"]  # mutants define their own class
        return c

    def request(self, method, path, query=None, body=None, empty_ok=False):
        if method == "POST":
            self.posts.append(path)
        result = self._route(method, path, query or {}, body)
        if method == "POST" and path in self.lose:
            raise self.error("server request failed")
        return result

    def _paged(self, rows, query):
        start = int(query.get("cursor", 0))
        end = start + self.page
        return {"data": rows[start:end], "cursor": {"next": str(end) if end < len(rows) else None}}

    def _route(self, method, path, query, body):
        parts = path.strip("/").split("/")
        if path == "/api/session" and method == "POST":
            sid = f"ses_{len(self.sessions) + 1}"
            row = {"id": sid, **body}
            self.sessions[sid] = row
            self.inbox[sid], self.messages[sid] = [], []
            return {"data": dict(row)}
        if path == "/api/session":
            rows = [r for r in self.sessions.values() if query["search"] in r["title"]
                    and r["location"]["directory"] == query["directory"]]
            return self._paged(rows, query)
        if path == "/api/session/active":
            return {"data": {s: {"type": "running"} for s in self.running}}
        sid = parts[2]
        if len(parts) == 3:
            return {"data": dict(self.sessions[sid])}
        if parts[3] == "prompt":
            item = {"id": body["id"], "sessionID": sid, "type": "user", "payload": {"text": body["text"]},
                    "delivery": "queue", "time": self.tick()}
            self.inbox[sid].append(item)
            return {"data": dict(item)}
        if parts[3] == "inbox":
            return {"data": list(self.inbox[sid])}
        if parts[3] == "message":
            return self._paged(self.messages[sid], query)
        if parts[3] == "interrupt":
            return {"interrupted": sid in self.running}
        raise AssertionError(path)

    def start(self, sid):
        """Move the queued input into history and mark the session running."""
        for item in self.inbox[sid]:
            self.messages[sid].append({"id": item["id"], "type": "user", "text": item["payload"]["text"],
                                       "time": self.tick()})
        self.inbox[sid] = []
        self.running.add(sid)

    def assistant(self, sid, n):
        self.messages[sid].append({"id": f"msg_a{n}", "type": "assistant", "agent": "build", "content": [],
                                   "model": ROW["model"], "time": self.tick()})

    def finish(self, sid, outcome):
        self.running.discard(sid)
        self.messages[sid].append({"id": "msg_idle", "type": "idle", "outcome": outcome, "time": self.tick()})


def fresh(server, module=None):
    return server.attach((module or v2).OpenCodeV2("http://127.0.0.1:1234", "user", "secret"))


def seeded(sid="ses_1"):
    server = FakeServer()
    server.sessions[sid] = {**ROW, "id": sid}
    server.inbox[sid], server.messages[sid] = [], []
    return server


def test_restart_after_lost_create_response_recovers_the_one_session():
    server = FakeServer()
    server.lose.add("/api/session")
    with pytest.raises(v2.V2Error):
        fresh(server).create_session("test", "/work", "local/model", PERMISSIONS)
    restarted = fresh(server)  # no memory of the first client
    assert restarted.find_sessions("test", "/work") == ["ses_1"]
    restarted.validate_session("ses_1", *BIND)
    assert server.posts == ["/api/session"]


def test_restart_after_lost_prompt_response_reconciles_without_resubmitting():
    server = seeded()
    server.lose.add("/api/session/ses_1/prompt")
    with pytest.raises(v2.V2Error):
        fresh(server).submit_prompt("ses_1", "msg_input", "input")
    restarted = fresh(server)
    assert restarted.observe_admission("ses_1", "msg_input", DIGEST)["sources"] == ["inbox"]
    server.start("ses_1")  # admission moves from the inbox projection to message history
    assert restarted.observe_admission("ses_1", "msg_input", DIGEST)["sources"] == ["message"]
    assert server.posts == ["/api/session/ses_1/prompt"]


def test_discovery_paginates_across_pages_and_finds_late_duplicate():
    server = FakeServer()
    server.page = 2
    for i in range(5):
        server.sessions[f"ses_{i}"] = {**ROW, "id": f"ses_{i}", "title": f"other-{i}"}
    server.sessions["ses_a"] = {**ROW, "id": "ses_a", "title": "test"}
    assert fresh(server).find_sessions("test", "/work") == ["ses_a"]
    server.sessions["ses_b"] = {**ROW, "id": "ses_b", "title": "test"}
    with pytest.raises(v2.V2Error, match="ambiguous"):
        fresh(server).find_sessions("test", "/work")


def observe(server, module=None, pid="msg_input", digest=DIGEST):
    return fresh(server, module).observe_terminal("ses_1", pid, digest, *BIND)


def test_terminal_over_pages_with_intermediate_tool_turns():
    server = seeded()
    server.page = 2
    fresh(server).submit_prompt("ses_1", "msg_input", "input")
    server.start("ses_1")
    for n in range(3):  # assistant tool turns are not terminal
        server.assistant("ses_1", n)
        assert observe(server) == {"status": "active"}
    server.running.discard("ses_1")  # absence from the active map alone is not outcome proof
    assert observe(server)["status"] == "unknown"
    server.finish("ses_1", "succeeded")
    result = observe(server)
    assert (result["status"], result["outcome"], result["prompt_id"]) == ("terminal-observed", "succeeded", "msg_input")


def test_terminal_is_bound_to_the_admitted_input_not_an_earlier_turn():
    server = seeded()
    server.messages["ses_1"] = [{"id": "msg_old_idle", "type": "idle", "outcome": "succeeded", "time": server.tick()},
                                {"id": "msg_input", "type": "user", "text": "input", "time": server.tick()}]
    assert observe(server)["status"] == "unknown"  # only an earlier turn has finished
    # evidence for a different prompt identity never settles this one
    server.messages["ses_1"] = [{"id": "msg_other", "type": "user", "text": "input", "time": server.tick()},
                                {"id": "msg_idle", "type": "idle", "outcome": "succeeded", "time": server.tick()}]
    assert observe(server)["status"] == "unknown"


def test_cancellation_race_ack_is_not_terminal_and_outcome_comes_from_history():
    server = seeded()
    fresh(server).submit_prompt("ses_1", "msg_input", "input")
    server.start("ses_1")
    c = fresh(server)
    assert c.interrupt_session("ses_1") == {"status": "acknowledged", "interrupted": True}
    assert observe(server) == {"status": "active"}
    # the interrupt lost the race: the turn completed successfully; acknowledgement must not relabel it
    server.finish("ses_1", "succeeded")
    assert c.interrupt_session("ses_1") == {"status": "acknowledged", "interrupted": False}
    assert observe(server)["outcome"] == "succeeded"


def test_cancellation_not_observed_until_interrupted_history_exists():
    server = seeded()
    fresh(server).submit_prompt("ses_1", "msg_input", "input")
    server.start("ses_1")
    fresh(server).interrupt_session("ses_1")
    server.running.discard("ses_1")  # left the active map but no interrupted idle exists yet
    assert observe(server)["status"] == "unknown"
    server.finish("ses_1", "interrupted")
    assert observe(server)["outcome"] == "interrupted"


# Each control disables one protection in a copy of the module source. The scenario must pass
# on the real module and fail on the mutant, so the protection is what the test depends on.

SOURCE = (Path(__file__).parents[1] / "opencode_v2.py").read_text()


def mutated(old, new):
    assert SOURCE.count(old) == 1, old
    module = importlib.util.module_from_spec(importlib.machinery.ModuleSpec("opencode_v2_mutant", None))
    exec(compile(SOURCE.replace(old, new), "opencode_v2_mutant", "exec"), module.__dict__)
    return module


def sc_ambiguous(m):
    server = FakeServer()
    for sid in ("ses_1", "ses_2"):
        server.sessions[sid] = {**ROW, "id": sid}
    with pytest.raises(m.V2Error, match="ambiguous"):
        fresh(server, m).find_sessions("test", "/work")


def sc_discovery_cycle(m):
    server = seeded()
    server._paged = lambda rows, query: {"data": [], "cursor": {"next": "cycle"}}
    with pytest.raises(m.V2Error, match="invalid discovery cursor"):
        fresh(server, m).find_sessions("test", "/work")


def sc_permission_drift(m):
    server = seeded()
    server.sessions["ses_1"]["permissions"] = PERMISSIONS + [{"action": "shell", "resource": "*", "effect": "allow"}]
    with pytest.raises(m.V2Error, match="binding mismatch"):
        fresh(server, m).validate_session("ses_1", *BIND)


def sc_directory_drift(m):
    server = seeded()
    server.sessions["ses_1"]["location"] = {"directory": "/other"}
    with pytest.raises(m.V2Error, match="binding mismatch"):
        fresh(server, m).validate_session("ses_1", *BIND)


def sc_create_not_retried(m):
    server = FakeServer()
    server.lose.add("/api/session")
    with pytest.raises(m.V2Error):
        fresh(server, m).create_session("test", "/work", "local/model", PERMISSIONS)
    assert server.posts == ["/api/session"]


def sc_prompt_not_retried(m):
    server = seeded()
    server.lose.add("/api/session/ses_1/prompt")
    with pytest.raises(m.V2Error):
        fresh(server, m).submit_prompt("ses_1", "msg_input", "input")
    assert server.posts == ["/api/session/ses_1/prompt"] and len(server.inbox["ses_1"]) == 1


def sc_empty_projection_is_unknown(m):
    assert fresh(seeded(), m).observe_admission("ses_1", "msg_input", DIGEST)["status"] == "unknown"


def sc_admission_digest(m):
    server = seeded()
    server.inbox["ses_1"].append({"id": "msg_input", "sessionID": "ses_1", "type": "user",
                                  "payload": {"text": "other"}, "delivery": "queue", "time": {"created": 1}})
    with pytest.raises(m.V2Error, match="conflicting"):
        fresh(server, m).observe_admission("ses_1", "msg_input", DIGEST)


def terminal_server(rows):
    server = seeded()
    server.messages["ses_1"] = rows
    return server


USER = {"id": "msg_input", "type": "user", "text": "input", "time": {"created": 1}}
IDLE = {"id": "msg_idle", "type": "idle", "outcome": "succeeded", "time": {"created": 2}}


def sc_wrong_prompt_identity(m):
    assert observe(terminal_server([{**USER, "id": "msg_other"}, IDLE]), m)["status"] == "unknown"


def sc_stale_idle(m):
    old = {**IDLE, "id": "msg_old_idle", "time": {"created": 0}}
    assert observe(terminal_server([old, USER]), m)["status"] == "unknown"


def sc_no_idle_after_assistant(m):
    reply = {"id": "msg_a", "type": "assistant", "agent": "build", "content": [],
             "model": ROW["model"], "time": {"created": 2}}
    assert observe(terminal_server([USER, reply]), m)["status"] == "unknown"


def sc_active_is_not_terminal(m):
    server = terminal_server([USER, IDLE])
    server.running.add("ses_1")
    assert observe(server, m) == {"status": "active"}


def sc_snapshot_stability(m):
    server = terminal_server([USER, {**IDLE, "outcome": "failed"}])
    reads = 0
    route = server._route
    def route_changing(method, path, query, body):
        nonlocal reads
        if path.endswith("/message"):
            reads += 1
            if reads == 2:
                server.messages["ses_1"] = server.messages["ses_1"] + [{**IDLE, "id": "msg_late", "time": {"created": 3}}]
        return route(method, path, query, body)
    server._route = route_changing
    assert observe(server, m)["status"] == "unknown"


def sc_assistant_model_drift(m):
    reply = {"id": "msg_a", "type": "assistant", "agent": "build", "content": [],
             "model": {"providerID": "local", "id": "other"}, "time": {"created": 2}}
    with pytest.raises(m.V2Error):
        observe(terminal_server([USER, reply, {**IDLE, "time": {"created": 3}}]), m)


def sc_terminal_cursor_cycle(m):
    server = seeded()
    server._paged = lambda rows, query: {"data": [], "cursor": {"next": "cycle"}}
    with pytest.raises(m.V2Error, match="invalid message cursor"):
        observe(server, m)


STAMP = "or len(idles) != 1 or not rows or rows[0] is not users[0] or rows[-1] is not idles[0]"
RETRY_CREATE = 'data = self._request("POST", "/api/session", body={"title": title, **binding}).get("data")'
RETRY_PROMPT = ('data = self._request("POST", f"/api/session/{sid}/prompt",\n'
                '                             body={"id": pid, "text": text}).get("data")')
MODEL_ID = 'or model.get("id") != binding["model"]["id"]\n                            or model.get("variant"'
# name: (old, new, scenario, exception the mutant must raise, regex it must match)
# Scenarios use pytest.raises internally, so a mutant that stops raising yields pytest's
# Failed "DID NOT RAISE"; a regex mismatch yields AssertionError.
CONTROLS = {
    "ambiguous-session": ("if len(matches) > 1:", "if False:", sc_ambiguous, pytest.fail.Exception, "DID NOT RAISE"),
    # without the seen-cursor check only the page-limit backstop stops the loop
    "discovery-cursor-cycle": ('if not isinstance(cursor, str) or not cursor or cursor in seen:\n'
                               '                raise V2Error("invalid discovery cursor")',
                               'if False:\n                raise V2Error("invalid discovery cursor")',
                               sc_discovery_cycle, AssertionError, "page limit exceeded"),
    "permission-drift": ('\n                or data.get("permissions") != binding["permissions"]):', "):",
                         sc_permission_drift, pytest.fail.Exception, "DID NOT RAISE"),
    "directory-drift": ('or data.get("location") != binding["location"]', "or False",
                        sc_directory_drift, pytest.fail.Exception, "DID NOT RAISE"),
    "create-no-retry": (RETRY_CREATE,
                        'try:\n            ' + RETRY_CREATE + '\n        except V2Error:\n            ' + RETRY_CREATE,
                        sc_create_not_retried, AssertionError, "one more item"),
    "prompt-no-retry": (RETRY_PROMPT,
                        'try:\n            ' + RETRY_PROMPT + '\n        except V2Error:\n            ' + RETRY_PROMPT,
                        sc_prompt_not_retried, AssertionError, "one more item"),
    "empty-projection-unknown": ('"observed" if found else "unknown"', '"observed" if found else "absent"',
                                 sc_empty_projection_is_unknown, AssertionError, "unknown"),
    "admission-digest": ("if any(hashlib.sha256(text.encode()).hexdigest() != text_sha256 for _, text in found):",
                         "if False:", sc_admission_digest, pytest.fail.Exception, "DID NOT RAISE"),
    "terminal-prompt-identity": ('or users[0].get("id") != pid', "", sc_wrong_prompt_identity, AssertionError, "terminal-observed"),
    "terminal-stale-idle": (STAMP, "", sc_stale_idle, AssertionError, "terminal-observed"),
    # idles[0] on an empty list: the guard is what keeps a missing idle row from being read as an outcome
    "terminal-needs-idle": ("or len(idles) != 1 or not rows", "or len(idles) > 1 or not rows",
                            sc_no_idle_after_assistant, IndexError, "list index out of range"),
    "active-map": ("        if sid not in data:\n            return False", "        return False",
                   sc_active_is_not_terminal, AssertionError, "terminal-observed"),
    "two-snapshot-stability": ('if rows != second["rows"]:', "if False:", sc_snapshot_stability, AssertionError, "terminal-observed"),
    "assistant-model-binding": (MODEL_ID, 'or False\n                            or model.get("variant"',
                                sc_assistant_model_drift, pytest.fail.Exception, "DID NOT RAISE"),
    # without the seen-cursor check only the page-limit backstop stops the loop
    "terminal-cursor-cycle": ('if not isinstance(cursor, str) or not cursor or cursor in cursors:\n'
                              '                raise V2Error("invalid message cursor")',
                              'if False:\n                raise V2Error("invalid message cursor")',
                              sc_terminal_cursor_cycle, AssertionError, "page limit exceeded"),
}


@pytest.mark.parametrize("name", list(CONTROLS))
def test_negative_control_fails_without_its_protection(name):
    old, new, scenario, exception, reason = CONTROLS[name]
    mutant = mutated(old, new)  # built outside raises: a non-matching pattern must error, not pass
    scenario(v2)  # the real module satisfies the scenario
    with pytest.raises(exception, match=reason):
        scenario(mutant)
