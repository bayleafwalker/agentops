#!/usr/bin/env python3
"""Operator entrypoint and loopback read facade for the resident memory adapter."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from resident_memory.client import HindsightClient, UpstreamError
from resident_memory.policy import KINDS, Policy, canonical, digest
from resident_memory.service import MemoryService
from resident_memory.store import Store
from resident_context import build_context, save_context_packet, load_context_packet, recheck_context


def handler_for(policy: Policy, service: MemoryService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "resident-memory"

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *_):
            pass  # Query text and authentication never enter access logs.

        def do_POST(self):
            self.connection.settimeout(25)
            try:
                if self.path != "/v1/search":
                    self.reply(404, {"error": "unknown operation"})
                    return
                lengths = self.headers.get_all("Content-Length") or []
                if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
                    raise ValueError("one content length required")
                length = int(lengths[0])
                if not 1 <= length <= policy.max_request_bytes:
                    raise ValueError("request exceeds bound")
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError("incomplete request")
                request = json.loads(body)
                if not isinstance(request, dict) or set(request) != {"scope_id", "query"}:
                    raise ValueError("request requires only scope_id and query")
                auth_headers = self.headers.get_all("Authorization") or []
                if len(auth_headers) != 1:
                    raise PermissionError("unauthorized")
                auth = auth_headers[0]
                policy.authenticate(auth[7:] if auth.startswith("Bearer ") else "", request["scope_id"])
                self.reply(200, service.search(request["scope_id"], request["query"]))
            except PermissionError:
                self.reply(403, {"error": "unauthorized"})
            except (ValueError, KeyError, TypeError):
                self.reply(400, {"error": "invalid request"})
            except (UpstreamError, OSError):
                self.reply(503, {"error": "memory unavailable"})

        def reply(self, status: int, value: dict):
            body = canonical(value)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--scope", required=True)
    capture.add_argument("--path", required=True)
    capture.add_argument("--kind", choices=sorted(KINDS), required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("--source", required=True)
    reconcile = commands.add_parser("reconcile")
    reconcile.add_argument("--operation", required=True)
    retract = commands.add_parser("retract")
    retract.add_argument("--source", required=True)
    retract.add_argument("--reason", required=True)
    for name in ("sources", "status", "search"):
        child = commands.add_parser(name)
        child.add_argument("--scope", required=True)
        if name == "search":
            child.add_argument("query")
    backup = commands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    context = commands.add_parser("context")
    context.add_argument("--scope", required=True)
    context.add_argument("--instructions", required=True, type=Path)
    context.add_argument("--work", required=True, type=Path)
    context.add_argument("--query", required=True)
    context.add_argument("--required-source", action="append", default=[])
    context.add_argument("--output-dir", required=True, type=Path)
    context.add_argument("--max-bytes", type=int, default=65536)
    recheck = commands.add_parser("recheck")
    recheck.add_argument("--scope", required=True)
    recheck.add_argument("--context", required=True, type=Path)
    recheck.add_argument("--generation", required=True, type=int)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8791)
    args = parser.parse_args(argv)
    try:
        policy = Policy.load(args.policy)
        store = Store(policy)
        service = MemoryService(policy, store, HindsightClient(policy))
        try:
            if args.command == "capture":
                value = store.capture(args.scope, args.path, args.kind)
            elif args.command == "ingest":
                value = service.ingest(args.source)
            elif args.command == "reconcile":
                value = service.reconcile(args.operation)
            elif args.command == "retract":
                store.retract(args.source, args.reason)
                value = {"retracted": args.source}
            elif args.command == "sources":
                value = store.current_sources(args.scope)
            elif args.command == "status":
                value = store.ingestion_status(args.scope)
            elif args.command == "search":
                value = service.search(args.scope, args.query)
            elif args.command == "backup":
                store.backup(args.destination)
                value = {"backup": str(args.destination)}
            elif args.command == "recheck":
                if args.generation < 1:
                    raise ValueError("generation must be positive")
                packet = load_context_packet(args.context)
                if packet["scope"] != policy.scopes[args.scope].identity:
                    raise ValueError("context scope mismatch")
                value = recheck_context(packet, store.current_sources(args.scope))
                now = datetime.now(timezone.utc)
                value.update(context_sha256=digest(canonical(packet)), generation=args.generation,
                             checked_at=now.isoformat(), valid_until=(now + timedelta(seconds=30)).isoformat())
            elif args.command == "context":
                scope = policy.scopes[args.scope]
                recalled = service.search(args.scope, args.query)
                required = []
                for ident in args.required_source:
                    source = store.source(ident)
                    if source["scope_id"] != args.scope:
                        raise ValueError("required source belongs to another scope")
                    required.append({"id": ident, "content": source["body"].decode(), "status": "current",
                                     "scope": scope.identity,
                                     "source_refs": [{key: source[key] for key in ("source_id", "revision", "sha256")}]})
                for path in (args.instructions, args.work):
                    if path.stat().st_size > 65536:
                        raise ValueError("trusted context input is too large")
                packet = build_context(instructions=args.instructions.read_text(),
                                       current_work=json.loads(args.work.read_text()),
                                       required_sources=required, scope=scope.identity,
                                       current_sources=store.current_sources(args.scope),
                                       memories=recalled["entries"], max_bytes=args.max_bytes,
                                       orientation="Memory status: " + recalled["state"] + "; ingestion: "
                                       + json.dumps(recalled["ingestion"], sort_keys=True))
                target = save_context_packet(args.output_dir, packet)
                value = {"path": str(target), "digest": packet["digest"], "status": packet["status"]}
            else:
                if not 1024 <= args.port <= 65535:
                    raise ValueError("port must be unprivileged")
                HTTPServer(("127.0.0.1", args.port), handler_for(policy, service)).serve_forever()
                return 0
            print(canonical(value).decode())
            return 0
        finally:
            store.close()
    except (ValueError, KeyError, OSError, UpstreamError):
        print('{"error":"resident memory operation failed; inspect protected configuration and source availability"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
