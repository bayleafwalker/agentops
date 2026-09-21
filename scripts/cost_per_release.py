#!/usr/bin/env python3
"""Cost per Release: a derived, read-only query (TS-7).

Nothing computes cost per sprintctl Release. A Release is a frozen item
revision (``work_release`` / ``release_commit``, ``sprintctl/db.py`` lines
1026-1060) and every lane accept Decision so far carries ``release_digest``
null -- no lane item has a Release yet. This script reports what TS-7 asks
for anyway: cost joined through to the item (and, once one exists, the
Release), so the number is not thrown away while releases catch up.

**Join** (decided by the refine tick of 2026-09-21, one line, re-decidable --
the query is derived and writes nothing):

    session -> tick (lane-loop ledger; session_id, window [ts - minutes, ts])
    -> items whose lane.dispatch/lane.review notes (actor devbox-agent-vuoro,
       tag "lane") fall inside that window
    -> Release via the item's accept Decision release_digest when non-null,
       else the item id with released=false.

A tick with several items is apportioned by wall time from each item's
dispatch note to its review note; time outside any item's span in the tick
is split equally across the tick's items. Both the apportioned and the
whole-tick figures are reported, per item, alongside the newest cumulative
session-cost-log snapshot for each session touched (when that session
appears in the log at all -- the log covers top-level sessions only,
``maintenance_lane_report.py`` lines 52-53).

This script never calls sprintctl; ``--events-json`` names a file already
produced by ``sprintctl event list --sprint-id <id> --limit 2000 --json``.
No writes anywhere: no dedup file, no cache, no settlement store (TS-7 is
explicit that this join gets no writer).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_LEDGER = Path.home() / ".local" / "state" / "lane-loop" / "ticks.jsonl"
DEFAULT_COSTS = Path("/projects/dev/.claude/session-costs.jsonl")
DEFAULT_BINDINGS_DIR = Path("/projects/dev/.claude/state/session-bindings")

LANE_ACTOR = "devbox-agent-vuoro"
LANE_EVENT_TYPES = ("lane.dispatch", "lane.review")


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------

def _parse_ts(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp, tolerating a trailing 'Z'. Returns None on failure."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# --------------------------------------------------------------------------
# session-costs.jsonl: newest row per session
# --------------------------------------------------------------------------

def load_newest_cost_per_session(path: Path) -> dict[str, dict]:
    """Reduce /projects/dev/.claude/session-costs.jsonl to its newest row per session.

    Rows are cumulative snapshots of one session, so later rows supersede earlier
    ones for the same session -- exactly the rule hooks/cost-summary.sh applies
    (lines 20-21): sort by (ts, cost_usd, out) and keep the last. cost_usd is the
    tiebreaker because ts has one-second resolution and snapshots are monotonic, so
    on a tie the larger cost_usd is the later snapshot.
    """
    rows: list[dict] = []
    if not path.exists():
        return {}
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    by_session: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        session = row.get("session")
        if session is None:
            continue
        by_session[session].append(row)

    newest: dict[str, dict] = {}
    for session, session_rows in by_session.items():
        session_rows.sort(key=lambda r: (r.get("ts") or "", r.get("cost_usd") or 0, r.get("out") or 0))
        newest[session] = session_rows[-1]
    return newest


# --------------------------------------------------------------------------
# lane-loop ledger
# --------------------------------------------------------------------------

def load_done_ticks(path: Path) -> list[dict]:
    ticks: list[dict] = []
    if not path.exists():
        return ticks
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("decision") == "done" and row.get("session_id"):
                ticks.append(row)
    return ticks


# --------------------------------------------------------------------------
# events (offline sprintctl export)
# --------------------------------------------------------------------------

def _payload(event: dict) -> dict:
    raw = event.get("payload")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def load_events(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("events", [])
    return data if isinstance(data, list) else []


def lane_notes(events: list[dict]) -> list[dict]:
    """lane.dispatch / lane.review notes from the lane actor, tagged 'lane'."""
    notes = []
    for event in events:
        if event.get("event_type") not in LANE_EVENT_TYPES:
            continue
        if event.get("actor") != LANE_ACTOR:
            continue
        tags = _payload(event).get("tags", [])
        if "lane" not in tags:
            continue
        ts = _parse_ts(event.get("created_at"))
        if ts is None:
            continue
        notes.append({"item_id": event.get("work_item_id"), "event_type": event.get("event_type"), "ts": ts})
    return notes


def latest_release_digest(events: list[dict], item_id: Any) -> tuple[str | None, bool]:
    """Latest accept Decision's release_digest for an item, or (None, False)."""
    best_ts: datetime | None = None
    best_digest: str | None = None
    found = False
    for event in events:
        if event.get("event_type") != "item-decided" or event.get("work_item_id") != item_id:
            continue
        payload = _payload(event)
        if payload.get("kind") != "accept":
            continue
        ts = _parse_ts(event.get("created_at"))
        if best_ts is not None and (ts is None or ts <= best_ts):
            continue
        best_ts = ts
        best_digest = payload.get("release_digest")
        found = True
    return (best_digest if found else None), found


# --------------------------------------------------------------------------
# Join: tick -> items -> apportioned cost
# --------------------------------------------------------------------------

def apportion_tick(tick: dict, notes: list[dict]) -> list[dict]:
    """Split one tick's whole-tick cost across the items its lane notes name.

    Each item's span runs from its earliest lane.dispatch note in the tick window to
    its latest lane.review note (clipped to the window). Wall time inside the window
    that falls outside every item's span (dead time, or a dispatch/review note pair
    that never both landed in-window) is split equally across the tick's items --
    the rule the item text spells out, not a per-item guess.

    Returns one dict per item: item_id, session_id, cost_usd_ledger (whole tick),
    cost_usd_apportioned.
    """
    end = _parse_ts(tick.get("ts"))
    minutes = tick.get("minutes") or 0
    session_id = tick["session_id"]
    cost_usd = tick.get("cost_usd") or 0.0
    if end is None:
        return []
    start = end - timedelta(minutes=minutes)
    window_seconds = max((end - start).total_seconds(), 0.0)

    by_item: dict[Any, list[dict]] = defaultdict(list)
    for note in notes:
        if start <= note["ts"] <= end:
            by_item[note["item_id"]].append(note)

    if not by_item:
        return []

    spans: dict[Any, float] = {}
    for item_id, item_notes in by_item.items():
        lo = min(n["ts"] for n in item_notes)
        hi = max(n["ts"] for n in item_notes)
        lo = max(lo, start)
        hi = min(hi, end)
        spans[item_id] = max((hi - lo).total_seconds(), 0.0)

    occupied = sum(spans.values())
    gap = max(window_seconds - occupied, 0.0)
    gap_per_item = gap / len(spans) if spans else 0.0

    rows = []
    for item_id, span_seconds in spans.items():
        apportioned_seconds = span_seconds + gap_per_item
        fraction = apportioned_seconds / window_seconds if window_seconds > 0 else 1.0 / len(spans)
        rows.append(
            {
                "item_id": item_id,
                "session_id": session_id,
                "cost_usd_ledger": cost_usd,
                "cost_usd_apportioned": cost_usd * fraction,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Build report rows
# --------------------------------------------------------------------------

def build_rows(
    ticks: list[dict],
    notes: list[dict],
    events: list[dict],
    newest_cost: dict[str, dict],
    bindings_dir: Path,
) -> list[dict]:
    per_item: dict[Any, dict] = defaultdict(
        lambda: {"sessions": {}, "cost_usd_ledger": 0.0, "cost_usd_apportioned": 0.0}
    )

    for tick in ticks:
        for row in apportion_tick(tick, notes):
            item_id = row["item_id"]
            entry = per_item[item_id]
            entry["cost_usd_ledger"] += row["cost_usd_ledger"]
            entry["cost_usd_apportioned"] += row["cost_usd_apportioned"]
            session_id = row["session_id"]
            entry["sessions"].setdefault(session_id, 0.0)
            entry["sessions"][session_id] += row["cost_usd_apportioned"]

    grouped: dict[Any, dict] = {}
    for item_id, entry in per_item.items():
        release_digest, has_decision = latest_release_digest(events, item_id)
        released = bool(has_decision and release_digest)
        key = release_digest if released else ("item", item_id)
        group = grouped.setdefault(
            key,
            {
                "release_digest": release_digest if released else None,
                "released": released,
                "item_ids": [],
                "sessions": set(),
                "cost_usd_ledger": 0.0,
                "cost_usd_apportioned": 0.0,
            },
        )
        group["item_ids"].append(item_id)
        group["sessions"].update(entry["sessions"].keys())
        group["cost_usd_ledger"] += entry["cost_usd_ledger"]
        group["cost_usd_apportioned"] += entry["cost_usd_apportioned"]

    rows = []
    for group in grouped.values():
        session_ids = sorted(group["sessions"])
        costlog_total = 0.0
        costlog_covered = False
        binding_found = {}
        for session_id in session_ids:
            if session_id in newest_cost:
                costlog_total += newest_cost[session_id].get("cost_usd") or 0.0
                costlog_covered = True
            binding_found[session_id] = (bindings_dir / f"{session_id}.json").exists()
        rows.append(
            {
                "release_digest": group["release_digest"],
                "item_ids": sorted(group["item_ids"]),
                "released": group["released"],
                "session_ids": session_ids,
                "cost_usd_ledger": round(group["cost_usd_ledger"], 6),
                "cost_usd_apportioned": round(group["cost_usd_apportioned"], 6),
                "cost_usd_costlog": round(costlog_total, 6) if costlog_covered else None,
                "binding_found": binding_found,
            }
        )
    rows.sort(key=lambda r: (r["item_ids"][0] if r["item_ids"] else 0))
    return rows


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def render_table(rows: list[dict]) -> str:
    if not rows:
        return "(no rows)"
    header = (
        f"{'item(s)':<12} {'release':<10} {'released':<9} {'sessions':<40} "
        f"{'ledger':>10} {'apportioned':>12} {'costlog':>10} {'bindings'}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        items = ",".join(f"#{i}" for i in row["item_ids"])
        digest = (row["release_digest"] or "-")[:10]
        released = "yes" if row["released"] else "no"
        sessions = ",".join(s[:8] for s in row["session_ids"]) or "-"
        costlog = "n/a" if row["cost_usd_costlog"] is None else f"{row['cost_usd_costlog']:.4f}"
        missing = [s[:8] for s, found in row["binding_found"].items() if not found]
        bindings = "ok" if not missing else f"MISSING:{','.join(missing)}"
        lines.append(
            f"{items:<12} {digest:<10} {released:<9} {sessions:<40} "
            f"{row['cost_usd_ledger']:>10.4f} {row['cost_usd_apportioned']:>12.4f} {costlog:>10} {bindings}"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER, help="lane-loop ticks.jsonl")
    parser.add_argument("--costs", type=Path, default=DEFAULT_COSTS, help="session-costs.jsonl")
    parser.add_argument("--bindings-dir", type=Path, default=DEFAULT_BINDINGS_DIR, help="session-bindings directory")
    parser.add_argument(
        "--events-json",
        type=Path,
        required=True,
        help="output of 'sprintctl event list --sprint-id <id> --limit 2000 --json' "
        "(this script never calls sprintctl itself)",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON list instead of a table")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    ticks = load_done_ticks(args.ledger)
    newest_cost = load_newest_cost_per_session(args.costs)
    events = load_events(args.events_json)
    notes = lane_notes(events)
    rows = build_rows(ticks, notes, events, newest_cost, args.bindings_dir)

    if args.json:
        print(json.dumps(rows, indent=2, default=str))
    else:
        print(render_table(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
