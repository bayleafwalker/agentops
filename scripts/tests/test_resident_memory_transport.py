"""Exercise real HTTP serialization and the narrow unprivileged facade."""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resident_memory.client import HindsightClient, UpstreamError
from resident_memory.policy import Policy, Principal, Scope, canonical, digest
from resident_memory_cli import handler_for


@pytest.fixture
def policy(tmp_path):
    token = tmp_path / "engine-token"
    token.write_text("engine-secret")
    scope = Scope("story", "story-bank", "r01", "story", "main", tmp_path / "source", ("canon.md",))
    return Policy(tmp_path / "state", "http://127.0.0.1:8888", token, {"story": scope},
                  (Principal("reader", digest(b"a" * 32), ("story",)),), "0" * 64)


def start(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, "http://127.0.0.1:" + str(server.server_port)


class Service:
    def __init__(self):
        self.calls = []

    def search(self, scope, query):
        self.calls.append((scope, query))
        return {"entries": [], "authorizes_effects": False}


def test_facade_only_permits_scoped_search_and_no_authority_fields(policy):
    service = Service()
    server, url = start(handler_for(policy, service))
    try:
        def request(body, token="a" * 32, path="/v1/search"):
            return urllib.request.urlopen(urllib.request.Request(url + path, data=canonical(body),
                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}), timeout=2)
        with request({"scope_id": "story", "query": "city"}) as reply:
            assert json.load(reply)["authorizes_effects"] is False
        for body, token, path, code in [
            ({"scope_id": "other", "query": "city"}, "a" * 32, "/v1/search", 403),
            ({"scope_id": "story", "query": "city"}, "b" * 32, "/v1/search", 403),
            ({"scope_id": "story", "query": "city", "bank": "other"}, "a" * 32, "/v1/search", 400),
            ({"scope_id": "story", "query": "city"}, "a" * 32, "/v1/retract", 404),
        ]:
            with pytest.raises(urllib.error.HTTPError) as exc:
                request(body, token, path)
            assert exc.value.code == code
        assert service.calls == [("story", "city")]
    finally:
        server.shutdown()
        server.server_close()


def test_engine_redirect_never_leaks_token(policy):
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            calls.append(self.path)
            self.send_response(307)
            self.send_header("Location", "/credential-trap")
            self.end_headers()
    server, url = start(Handler)
    try:
        client = HindsightClient(replace(policy, upstream_url=url))
        with pytest.raises(UpstreamError):
            client.recall("story-bank", "x", ["scope"])
        assert calls == ["/v1/default/banks/story-bank/memories/recall"]
    finally:
        server.shutdown()
        server.server_close()


def test_published_engine_wire_contract_contains_strict_tags_and_source_facts(policy, monkeypatch):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            body = b'{"results":[],"source_facts":{}}'
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server, url = start(Handler)
    try:
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
        monkeypatch.setenv("https_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        client = HindsightClient(replace(policy, upstream_url=url))
        client.recall("story-bank", "what happened?", ["resident:r01", "project:story", "branch:main"])
        path, body = received[0]
        assert path.endswith("/story-bank/memories/recall")
        assert body["tags_match"] == "all_strict"
        assert body["include"]["entities"] is None
        assert body["include"]["source_facts"]["max_tokens"] == 8192
    finally:
        server.shutdown()
        server.server_close()
