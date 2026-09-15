"""operator-projection serve: GET-only HTTP over the last document, regenerated in-process every cadence (§0)."""

from __future__ import annotations

import gzip
import json
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import contract, render_html, render_text  # noqa: F401  (contract asserts renderer coverage on import)

ROUTES = {
    "/": ("text/html; charset=utf-8", render_html.render),
    "/v1.json": ("application/json", lambda doc: json.dumps(doc, indent=1, ensure_ascii=False) + "\n"),
    "/v1.txt": ("text/plain; charset=utf-8", render_text.render),
}
ARCHIVE_KEEP_S = 60 * 86400  # H is 56 days; the margin keeps the verdict day's inputs


def fresh(doc: dict | None, now: datetime) -> bool:
    """Gatus checks the page itself on freshness (§8), not /healthz: a stale document must not restart the pod."""
    return doc is not None and (now - datetime.fromisoformat(doc["generated_at"])).total_seconds() <= doc["stale_after_s"]


def archive(directory: Path, doc: dict, now: float | None = None) -> None:
    """One gzip per generation (P2), pruned past ARCHIVE_KEEP_S, so M1 reads document history from the first day of H."""
    directory.mkdir(parents=True, exist_ok=True)
    with gzip.open(directory / f"v1-{doc['generated_at'].replace(':', '')}.json.gz", "wt", encoding="utf-8") as out:
        json.dump(doc, out, ensure_ascii=False)
    cutoff = (now or time.time()) - ARCHIVE_KEEP_S
    for old in directory.glob("v1-*.json.gz"):
        if old.stat().st_mtime < cutoff:
            old.unlink()


class Latest:
    """The only state the process holds: the last generated document, in memory."""

    document: dict | None = None


def handler(latest: Latest) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status: int, kind: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if status == 405:
                self.send_header("Allow", "GET")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path, doc = self.path.split("?", 1)[0], latest.document
            if path == "/freshz":
                ok = fresh(doc, datetime.now(timezone.utc))
                return self.reply(200 if ok else 503, "text/plain", b"fresh\n" if ok else b"stale\n")
            if path == "/healthz" or (path in ROUTES and doc is None):
                return self.reply(200 if doc else 503, "text/plain", b"ok\n" if doc else b"no document yet\n")
            if path not in ROUTES:
                return self.reply(404, "text/plain", b"not found\n")
            kind, render = ROUTES[path]
            self.reply(200, kind, render(doc).encode())

        def refuse(self) -> None:
            self.reply(405, "text/plain", b"GET only\n")

        do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = do_TRACE = do_CONNECT = refuse

        def log_message(self, *_args) -> None:
            pass

    return Handler


def loop(latest: Latest, produce: Callable[[], dict], cadence_s: int, stop: threading.Event, archive_dir: Path | None = None) -> None:
    while not stop.is_set():
        try:
            latest.document = produce()
            if archive_dir:
                archive(archive_dir, latest.document)
        except Exception as error:  # keep serving the last document; it turns STALE on its own
            print(f"generation or archive failed: {type(error).__name__}: {error}", flush=True)
        stop.wait(cadence_s)


def serve(produce: Callable[[], dict], cadence_s: int, host: str = "0.0.0.0", port: int = 8080, archive_dir: Path | None = None) -> None:
    latest, stop = Latest(), threading.Event()
    threading.Thread(target=loop, args=(latest, produce, cadence_s, stop, archive_dir), daemon=True).start()
    ThreadingHTTPServer((host, port), handler(latest)).serve_forever()
