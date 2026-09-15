"""serve: GET only, /healthz 503 until a first document exists; cli text over a recorded document."""

import http.client
import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

import pytest

from fakes import FakeAuthorityClient
from operator_projection import cli
from operator_projection.generate import generate
from operator_projection.serve import ARCHIVE_KEEP_S, Latest, archive, handler, loop
from operator_projection.sources import Authority, stamp
from world import NOW, REGISTRY, TAGS, estate


@pytest.fixture
def server():
    latest = Latest()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler(latest))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield latest, httpd.server_address[1]
    httpd.shutdown()


def request(port, method, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path)
    response = connection.getresponse()
    return response.status, response.getheader("Content-Type"), response.read().decode()


def document():
    return generate(estate(), Authority(FakeAuthorityClient(), lambda: False), REGISTRY, NOW, tags=lambda: TAGS)


def test_healthz_is_503_until_a_document_exists_then_routes_serve_it(server):
    latest, port = server
    assert request(port, "GET", "/healthz")[0] == 503
    assert request(port, "GET", "/v1.json")[0] == 503
    latest.document = document()
    assert request(port, "GET", "/healthz")[0] == 200
    status, kind, body = request(port, "GET", "/v1.json")
    assert status == 200 and kind == "application/json" and json.loads(body)["schema"] == "operator-projection/v1"
    assert "OPERATOR PROJECTION v1" in request(port, "GET", "/v1.txt")[2]
    assert "<section>" in request(port, "GET", "/")[2]
    assert request(port, "GET", "/other")[0] == 404


def test_freshz_is_503_without_a_document_and_once_past_stale_after(server):
    latest, port = server
    assert request(port, "GET", "/freshz")[0] == 503
    now = datetime.now(timezone.utc)
    latest.document = {**document(), "generated_at": stamp(now)}
    assert request(port, "GET", "/freshz")[0] == 200
    latest.document["generated_at"] = stamp(now - timedelta(seconds=latest.document["stale_after_s"] + 60))
    assert request(port, "GET", "/freshz")[0] == 503
    assert request(port, "GET", "/healthz")[0] == 200


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_every_other_method_is_405(server, method):
    latest, port = server
    latest.document = document()
    assert request(port, method, "/")[0] == 405


def test_loop_keeps_the_last_document_when_a_generation_fails():
    latest, stop, calls = Latest(), threading.Event(), []

    def produce():
        calls.append(1)
        if len(calls) > 1:
            stop.set()
            raise RuntimeError("source outage")
        return {"schema": "x"}

    loop(latest, produce, 0, stop)
    assert latest.document == {"schema": "x"} and len(calls) == 2


def test_archive_writes_one_gzip_per_generation_and_prunes_past_the_horizon(tmp_path):
    import gzip, os, time
    stale = tmp_path / "v1-2026-01-01T000000Z.json.gz"
    stale.write_bytes(b"")
    os.utime(stale, (time.time() - ARCHIVE_KEEP_S - 60,) * 2)
    archive(tmp_path, {"generated_at": "2026-09-15T08:00:00Z", "schema": "x"})
    kept = sorted(tmp_path.iterdir())
    assert [f.name for f in kept] == ["v1-2026-09-15T080000Z.json.gz"]
    assert json.loads(gzip.open(kept[0], "rt").read())["schema"] == "x"


def test_cli_text_renders_a_recorded_document(tmp_path, capsys):
    path = tmp_path / "v1.json"
    path.write_text(json.dumps(document()))
    assert cli.main(["text", "--file", str(path)]) == 0
    assert "HAZARDS" in capsys.readouterr().out


def test_missing_profile_and_token_build_without_crashing(tmp_path, monkeypatch):
    monkeypatch.setenv("OPERATOR_PROJECTION_GITHUB_TOKEN_FILE", str(tmp_path / "absent"))
    produce = cli.build(cli.default_registry(), str(tmp_path / "absent-profile.yaml"))
    assert callable(produce)
