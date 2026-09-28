#!/usr/bin/env python3
"""Report the last-authoritative-event-age hard health metric (agentops#2533, Q6 / B16).

The operator's #255 Q6 decision (a): auditctl stays authoritative until S4
(TS-6), a store that stopped receiving events is a *failed invariant*, and
"is capture healthy?" must come from a health metric, not a manual ``ls``
(docs/plans/2026-09-27-telemetry-audit-and-operator-actions.md, §1 note,
§3.6).

This is a hook-independent reader of the committed shards under
``_artifacts/<repo>/audit/events-*.ndjson`` -- the same shard set
``commit_audit_shards.py`` / ``check_append_only_shards.py`` operate on --
that emits, per audit store, the Prometheus gauge

    agentops_audit_last_authoritative_event_age_seconds{repo="<scope>"} <age>

where ``<age>`` is ``max(0, now - newest_durable_event_ts)`` in seconds: the
age of the newest event *durably written* to the store (not attempted, not
buffered -- a trailing partial/non-newline-terminated shard line is a write
in flight and is never counted).

Exit 0 when every store is within ``--window-seconds``; exit 1 (an alert)
when any store is stale, or when a store directory exists with no shards /
no parsable events at all (silence is a failed invariant, not a quiet day --
``absent()`` alerts the same as a stale series), naming the stale/absent
store on stderr.

Usage::

    audit_freshness.py --root DIR [--now ISO8601Z] --window-seconds N
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

#: The gauge §3.6 names.
METRIC = "agentops_audit_last_authoritative_event_age_seconds"
#: Same audit-store directory layout as commit_audit_shards.py / check_append_only_shards.py.
STORE_GLOB = "**/_artifacts/*/audit"
SHARD_GLOB = "events-*.ndjson"
UTC = timezone.utc


def parse_ts(value: str) -> datetime | None:
    """Parse an ISO 8601 UTC timestamp with a trailing ``Z``."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def event_ts(obj: dict) -> datetime | None:
    """The event's timestamp: ``ts``, falling back to ``created_at`` / ``occurred_at``."""
    for key in ("ts", "created_at", "occurred_at"):
        value = obj.get(key)
        if value:
            ts = parse_ts(value)
            if ts is not None:
                return ts
    return None


def newest_durable_event(path: Path) -> datetime | None:
    """The newest event timestamp among this shard's durably written lines.

    A trailing line with no newline terminator is a write in flight, not a
    durable event: it is dropped before parsing, and never crashes the read.
    Malformed (non-JSON, non-object) lines are skipped, not fatal.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data:
        return None
    terminated = data.endswith(b"\n")
    lines = data.split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if lines and not terminated:
        lines.pop()
    newest: datetime | None = None
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if not isinstance(obj, dict):
            continue
        ts = event_ts(obj)
        if ts is None:
            continue
        if newest is None or ts > newest:
            newest = ts
    return newest


def discover_stores(root: Path) -> dict[str, list[Path]]:
    """Map audit-store scope (the ``_artifacts/<scope>/audit`` component) to its shards."""
    stores: dict[str, list[Path]] = {}
    for audit_dir in root.glob(STORE_GLOB):
        if not audit_dir.is_dir():
            continue
        scope = audit_dir.parent.name
        shards = stores.setdefault(scope, [])
        shards.extend(sorted(audit_dir.glob(SHARD_GLOB)))
    return stores


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report the last-authoritative-event-age hard health metric per audit store.")
    parser.add_argument("--root", required=True, type=Path,
                        help="tree holding shards at **/_artifacts/<repo>/audit/events-*.ndjson")
    parser.add_argument("--now", default=None,
                        help="reference \"now\" (UTC, trailing Z); defaults to the wall clock")
    parser.add_argument("--window-seconds", required=True, type=float,
                        help="a store whose newest durable event is older than this is stale")
    args = parser.parse_args(argv)

    if args.now is not None:
        now = parse_ts(args.now)
        if now is None:
            print(f"audit-freshness: cannot parse --now {args.now!r}", file=sys.stderr)
            return 2
    else:
        now = datetime.now(UTC)

    root: Path = args.root
    if not root.is_dir():
        print(f"audit-freshness: root {root} is not a directory", file=sys.stderr)
        return 2

    stores = discover_stores(root)
    if not stores:
        print(f"audit-freshness: no audit stores found under {root} (absent() == stale)",
              file=sys.stderr)
        return 1

    alerts: list[str] = []
    for scope in sorted(stores):
        newest = None
        for shard in stores[scope]:
            ts = newest_durable_event(shard)
            if ts is not None and (newest is None or ts > newest):
                newest = ts
        if newest is None:
            alerts.append(scope)
            print(f"audit-freshness: {scope}: no durable events found (absent() == stale)",
                  file=sys.stderr)
            continue
        age = max(0.0, (now - newest).total_seconds())
        print(f'{METRIC}{{repo="{scope}"}} {age:.3f}')
        if age > args.window_seconds:
            alerts.append(scope)
            print(f"audit-freshness: {scope}: stale, last durable event {age:.0f}s ago "
                  f"(window {args.window_seconds:.0f}s)", file=sys.stderr)

    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
