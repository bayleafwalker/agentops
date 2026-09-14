#!/usr/bin/env python3
"""Maintenance-lane telemetry report.

Joins the four sources the maintenance-lane runbook names
(``docs/runbooks/maintenance-lane.md``, "Telemetry") into one report:

1. sprintctl item notes ``lane.dispatch`` / ``lane.review`` for a sprint --
   tier, model, harness, verdict, attempt.
2. auditctl ``dispatch.exit`` events (NDJSON shards under an artifacts root)
   -- agent id, terminal reason, transcript path.
3. subagent transcripts (JSONL, named by ``dispatch.exit``'s
   ``transcript_path``) -- per-message token usage, de-duplicated by
   ``message.id`` since one message can span several stream records.
4. the local-inference scorecard CSV -- local-model attempts.

Every input is optional. A source that is missing, empty, unreadable, or
malformed makes its report section "unavailable" -- it never raises. Rates
are ``None`` (rendered "n/a") rather than a division by zero.

This module adds no new store; it only reads and joins. It never mutates
sprintctl, auditctl, or the scorecard.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DEFAULT_ARTIFACTS_ROOT = Path("/projects/dev")
DEFAULT_SCORECARD = DEFAULT_ARTIFACTS_ROOT / "local-inference" / "benchmarks" / "scorecard.csv"
DEFAULT_SPRINTCTL_PROFILE = (
    "/projects/dev/agentops/templates/dispatch/environment-record/"
    "profiles/workstation-vuoro-shared.json"
)

VERDICTS = ("accepted", "rework", "rejected", "escalated")

CAVEATS = [
    "Token and cost figures derived from transcripts are list price, not subscription spend.",
    "/projects/dev/.claude/session-costs.jsonl covers top-level sessions only and excludes "
    "subagents, so it cannot measure worker tiers.",
    "A dispatch.exit terminal_reason of 'completed' means the process ended normally, not "
    "that the work was right -- only a lane.review verdict says that.",
]


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


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# sprintctl: items + lane notes
# --------------------------------------------------------------------------

def _sprintctl_env() -> dict:
    env = os.environ.copy()
    env.setdefault("SPRINTCTL_BACKEND", "served")
    env.setdefault("SPRINTCTL_VUORO_PROFILE", DEFAULT_SPRINTCTL_PROFILE)
    return env


def fetch_items_live(sprint_id: int) -> list[dict]:
    # No explicit cwd: sprintctl resolves its repo marker (and therefore repo_id) by
    # walking up from the process's own working directory, so this must inherit the
    # caller's cwd rather than pin one -- a worktree checkout of this very script has
    # no local .sprintctl marker of its own, only the home repository does.
    out = subprocess.run(
        ["sprintctl", "item", "list", "--sprint-id", str(sprint_id), "--json"],
        env=_sprintctl_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def fetch_item_events_live(item_id: Any) -> list[dict]:
    out = subprocess.run(
        ["sprintctl", "item", "show", "--id", str(item_id), "--json"],
        env=_sprintctl_env(),
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(out.stdout)
    return data.get("events", [])


def load_items_and_notes(args: argparse.Namespace) -> tuple[list[dict], dict[Any, list[dict]], bool]:
    """Return (items, notes_by_item_id, items_available)."""
    items: list[dict] = []
    items_available = False

    if args.items_json:
        try:
            items = json.loads(Path(args.items_json).read_text())
            items_available = True
        except (OSError, json.JSONDecodeError):
            items = []
    elif args.sprint_id is not None:
        try:
            items = fetch_items_live(args.sprint_id)
            items_available = True
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, OSError):
            items = []

    notes_by_id: dict[Any, list[dict]] = {}
    if args.notes_json:
        notes_dir = Path(args.notes_json)
        for item in items:
            item_id = item.get("id")
            fp = notes_dir / f"{item_id}.json"
            if not fp.exists():
                continue
            try:
                data = json.loads(fp.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                notes_by_id[item_id] = data.get("events", [])
            elif isinstance(data, list):
                notes_by_id[item_id] = data
    elif args.sprint_id is not None and items:
        for item in items:
            item_id = item.get("id")
            try:
                notes_by_id[item_id] = fetch_item_events_live(item_id)
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, OSError):
                notes_by_id[item_id] = []

    return items, notes_by_id, items_available


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


def _parse_tags(tags: list) -> tuple[dict[str, str], set[str]]:
    """Split 'key:value' tags from bare flag tags (e.g. 'lane', 'first-pass')."""
    kv: dict[str, str] = {}
    flags: set[str] = set()
    for tag in tags or []:
        if not isinstance(tag, str):
            continue
        if ":" in tag:
            key, _, value = tag.partition(":")
            kv[key] = value
        else:
            flags.add(tag)
    return kv, flags


def _verdict_of(review_payload: dict, review_tags_kv: dict[str, str]) -> str | None:
    verdict = review_tags_kv.get("verdict")
    if verdict in VERDICTS:
        return verdict
    summary = (review_payload.get("summary") or "").strip().lower()
    for word in VERDICTS:
        if summary.startswith(word):
            return word
    return None


def build_item_records(items: list[dict], notes_by_id: dict[Any, list[dict]]) -> list[dict]:
    """Attach dispatch/review events to each item and pair them into attempts in order."""
    records = []
    for item in items:
        item_id = item.get("id")
        events = notes_by_id.get(item_id, [])
        dispatches = sorted(
            (e for e in events if e.get("event_type") == "lane.dispatch"),
            key=lambda e: e.get("created_at") or "",
        )
        reviews = sorted(
            (e for e in events if e.get("event_type") == "lane.review"),
            key=lambda e: e.get("created_at") or "",
        )
        attempts = []
        for i, dispatch in enumerate(dispatches):
            review = reviews[i] if i < len(reviews) else None
            attempts.append({"dispatch": dispatch, "review": review})
        records.append(
            {
                "item": item,
                "dispatches": dispatches,
                "reviews": reviews,
                "attempts": attempts,
            }
        )
    return records


# --------------------------------------------------------------------------
# Section (a): per tier and per model
# --------------------------------------------------------------------------

def _rate(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


def aggregate_tier_model(records: list[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], dict] = defaultdict(
        lambda: {
            "attempts": 0,
            "first_pass_accepted": 0,
            "accepted": 0,
            "rework": 0,
            "rejected": 0,
            "escalated": 0,
            "accepted_items": set(),
        }
    )
    for record in records:
        item_id = record["item"].get("id")
        for attempt in record["attempts"]:
            dispatch_payload = _payload(attempt["dispatch"])
            kv, _flags = _parse_tags(dispatch_payload.get("tags", []))
            tier = kv.get("tier", "unknown")
            model = kv.get("model", "unknown")
            bucket = buckets[(tier, model)]
            bucket["attempts"] += 1

            review = attempt["review"]
            if review is None:
                continue
            review_payload = _payload(review)
            review_kv, review_flags = _parse_tags(review_payload.get("tags", []))
            verdict = _verdict_of(review_payload, review_kv)
            if verdict == "accepted":
                bucket["accepted"] += 1
                bucket["accepted_items"].add(item_id)
                if "first-pass" in review_flags:
                    bucket["first_pass_accepted"] += 1
            elif verdict in ("rework", "rejected", "escalated"):
                bucket[verdict] += 1

    rows = []
    for (tier, model), bucket in sorted(buckets.items()):
        attempts = bucket["attempts"]
        rows.append(
            {
                "tier": tier,
                "model": model,
                "attempts": attempts,
                "first_pass_acceptance_rate": _rate(bucket["first_pass_accepted"], attempts),
                "rework_rate": _rate(bucket["rework"], attempts),
                "rejected_rate": _rate(bucket["rejected"], attempts),
                "escalated_rate": _rate(bucket["escalated"], attempts),
                "accepted_items": sorted(bucket["accepted_items"]),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Section (b): stale active items
# --------------------------------------------------------------------------

def find_stale_items(records: list[dict], stale_hours: float, now: datetime) -> list[dict]:
    threshold = now - timedelta(hours=stale_hours)
    stale = []
    for record in records:
        item = record["item"]
        if item.get("status") in ("done", "cancelled"):
            continue
        if record["reviews"]:
            continue  # has at least one lane.review note
        ts = None
        if record["dispatches"]:
            ts = _parse_ts(record["dispatches"][-1].get("created_at"))
        if ts is None:
            ts = _parse_ts(item.get("updated_at")) or _parse_ts(item.get("created_at"))
        if ts is None:
            continue
        if ts < threshold:
            stale.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "since": ts.isoformat(),
                    "age_hours": round((now - ts).total_seconds() / 3600, 1),
                }
            )
    stale.sort(key=lambda row: row["age_hours"], reverse=True)
    return stale


# --------------------------------------------------------------------------
# auditctl dispatch.exit shards + transcripts
# --------------------------------------------------------------------------

def find_audit_shards(root: Path):
    if not root.exists():
        return
    for path in sorted(root.rglob("events-*.ndjson")):
        if path.parent.name != "audit":
            continue
        parts = path.parts
        if any(part in ("_wt", "_projects") for part in parts):
            continue
        if "_artifacts" not in parts:
            continue
        yield path


def load_dispatch_exit_events(root: Path, since: datetime | None) -> list[dict]:
    events = []
    for shard in find_audit_shards(root):
        try:
            handle = shard.open("r", encoding="utf-8")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_type = rec.get("event_type") or rec.get("type")
                if event_type != "dispatch.exit":
                    continue
                if since is not None:
                    ts = _parse_ts(rec.get("created_at"))
                    if ts is not None and ts < since:
                        continue
                events.append(rec)
    return events


def summarize_transcript(path: Path) -> dict | None:
    """Stream a transcript JSONL and summarize assistant usage, de-duplicated by message.id.

    A single logical message can appear across several stream records (usage grows as the
    message streams); the last record seen for a given message.id carries the final usage.
    """
    if not path:
        return None
    try:
        if not path.exists():
            return None
    except OSError:
        return None

    last_by_id: dict[str, dict] = {}
    order: list[str] = []
    timestamps: list[datetime] = []

    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") != "assistant":
                    continue
                message = rec.get("message") or {}
                mid = message.get("id")
                if not mid:
                    continue
                if mid not in last_by_id:
                    order.append(mid)
                last_by_id[mid] = {
                    "model": message.get("model"),
                    "usage": message.get("usage") or {},
                }
                ts = _parse_ts(rec.get("timestamp"))
                if ts is not None:
                    timestamps.append(ts)
    except OSError:
        return None

    if not order:
        return {
            "model": None,
            "messages": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "peak_context": 0,
            "wall_seconds": None,
        }

    input_total = 0
    output_total = 0
    peak_context = 0
    model_votes: dict[str, int] = defaultdict(int)
    for mid in order:
        entry = last_by_id[mid]
        usage = entry["usage"]
        message_input = (
            (usage.get("input_tokens") or 0)
            + (usage.get("cache_read_input_tokens") or 0)
            + (usage.get("cache_creation_input_tokens") or 0)
        )
        message_output = usage.get("output_tokens") or 0
        input_total += message_input
        output_total += message_output
        if message_input > peak_context:
            peak_context = message_input
        model = entry["model"]
        if model and model != "<synthetic>":
            model_votes[model] += 1

    model = max(model_votes, key=model_votes.get) if model_votes else None
    wall_seconds = None
    if timestamps:
        wall_seconds = (max(timestamps) - min(timestamps)).total_seconds()

    return {
        "model": model,
        "messages": len(order),
        "input_tokens": input_total,
        "output_tokens": output_total,
        "peak_context": peak_context,
        "wall_seconds": wall_seconds,
    }


# --------------------------------------------------------------------------
# Section (c): worker usage per model, and item-token join
# --------------------------------------------------------------------------

def summarize_worker_usage(dispatch_events: list[dict]) -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    """Return (rows_per_model, transcript_cache_by_path, transcript_by_agent_id)."""
    transcript_cache: dict[str, dict | None] = {}
    transcript_by_agent: dict[str, dict] = {}
    per_model: dict[str, dict] = defaultdict(
        lambda: {
            "sessions": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "peak_contexts": [],
            "wall_seconds": [],
            "abnormal": 0,
            "total": 0,
        }
    )

    for event in dispatch_events:
        metadata = event.get("metadata") or {}
        transcript_path = metadata.get("transcript_path")
        summary = None
        if transcript_path:
            if transcript_path not in transcript_cache:
                transcript_cache[transcript_path] = summarize_transcript(Path(transcript_path))
            summary = transcript_cache[transcript_path]

        agent_id = metadata.get("agent_id")
        if agent_id and summary:
            transcript_by_agent[agent_id] = summary

        model = (summary or {}).get("model") or "unknown"
        bucket = per_model[model]
        bucket["total"] += 1
        if metadata.get("terminal_reason") != "completed":
            bucket["abnormal"] += 1
        if summary:
            bucket["sessions"] += 1
            bucket["input_tokens"] += summary["input_tokens"]
            bucket["output_tokens"] += summary["output_tokens"]
            if summary["peak_context"]:
                bucket["peak_contexts"].append(summary["peak_context"])
            if summary["wall_seconds"] is not None:
                bucket["wall_seconds"].append(summary["wall_seconds"])

    rows = []
    for model, bucket in sorted(per_model.items()):
        rows.append(
            {
                "model": model,
                "sessions": bucket["sessions"],
                "input_tokens": bucket["input_tokens"],
                "output_tokens": bucket["output_tokens"],
                "median_peak_context": (
                    statistics.median(bucket["peak_contexts"]) if bucket["peak_contexts"] else None
                ),
                "median_wall_seconds": (
                    statistics.median(bucket["wall_seconds"]) if bucket["wall_seconds"] else None
                ),
                "abnormal_exit_rate": _rate(bucket["abnormal"], bucket["total"]),
            }
        )
    return rows, transcript_cache, transcript_by_agent


def join_tokens_per_accepted_item(
    records: list[dict], transcript_by_agent: dict[str, dict]
) -> list[dict]:
    """A lane.dispatch note may carry the worker's agent id as tag 'agent:<id>'.

    Where present and joinable to a dispatch.exit/transcript, attach that attempt's
    transcript usage to accepted items, per model.
    """
    per_model: dict[str, dict] = defaultdict(
        lambda: {"accepted_items_joined": 0, "input_tokens": 0, "output_tokens": 0}
    )
    for record in records:
        for attempt in record["attempts"]:
            review = attempt["review"]
            if review is None:
                continue
            review_payload = _payload(review)
            review_kv, _flags = _parse_tags(review_payload.get("tags", []))
            if _verdict_of(review_payload, review_kv) != "accepted":
                continue

            dispatch_payload = _payload(attempt["dispatch"])
            dispatch_kv, _dflags = _parse_tags(dispatch_payload.get("tags", []))
            agent_id = dispatch_kv.get("agent") or dispatch_payload.get("agent_id")
            if not agent_id:
                continue
            summary = transcript_by_agent.get(agent_id)
            if not summary:
                continue

            model = dispatch_kv.get("model", "unknown")
            bucket = per_model[model]
            bucket["accepted_items_joined"] += 1
            bucket["input_tokens"] += summary["input_tokens"]
            bucket["output_tokens"] += summary["output_tokens"]

    rows = []
    for model, bucket in sorted(per_model.items()):
        n = bucket["accepted_items_joined"]
        rows.append(
            {
                "model": model,
                "accepted_items_joined": n,
                "input_tokens_per_accepted_item": (bucket["input_tokens"] / n) if n else None,
                "output_tokens_per_accepted_item": (bucket["output_tokens"] / n) if n else None,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Section (d): local scorecard
# --------------------------------------------------------------------------

def _truthy(value: Any) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "y", "t")


def load_scorecard(path: Path) -> list[dict]:
    if not path or not path.exists():
        return []
    per_model: dict[str, dict] = defaultdict(
        lambda: {"attempts": 0, "tests_passed": 0, "accepted": 0, "wall_ms": []}
    )
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                model = row.get("model") or "unknown"
                bucket = per_model[model]
                bucket["attempts"] += 1
                if _truthy(row.get("tests_passed")):
                    bucket["tests_passed"] += 1
                if _truthy(row.get("accepted")):
                    bucket["accepted"] += 1
                try:
                    bucket["wall_ms"].append(float(row.get("wall_ms")))
                except (TypeError, ValueError):
                    pass
    except OSError:
        return []

    rows = []
    for model, bucket in sorted(per_model.items()):
        n = bucket["attempts"]
        rows.append(
            {
                "model": model,
                "attempts": n,
                "tests_passed_rate": _rate(bucket["tests_passed"], n),
                "accepted_rate": _rate(bucket["accepted"], n),
                "median_wall_ms": statistics.median(bucket["wall_ms"]) if bucket["wall_ms"] else None,
            }
        )
    return rows


# --------------------------------------------------------------------------
# Report assembly + rendering
# --------------------------------------------------------------------------

def build_report(args: argparse.Namespace) -> dict:
    now = _now()
    since = _parse_ts(args.since) if args.since else None

    items, notes_by_id, items_available = load_items_and_notes(args)
    records = build_item_records(items, notes_by_id) if items_available else []

    artifacts_root = Path(args.artifacts_root)
    audit_available = artifacts_root.exists()
    dispatch_events = load_dispatch_exit_events(artifacts_root, since) if audit_available else []

    worker_rows, _transcript_cache, transcript_by_agent = (
        summarize_worker_usage(dispatch_events) if audit_available else ([], {}, {})
    )

    scorecard_path = Path(args.scorecard) if args.scorecard else None
    scorecard_available = bool(scorecard_path and scorecard_path.exists())
    scorecard_rows = load_scorecard(scorecard_path) if scorecard_available else []

    report = {
        "meta": {
            "sprint_id": args.sprint_id,
            "since": since.isoformat() if since else None,
            "stale_hours": args.stale_hours,
            "generated_at": now.isoformat(),
        },
        "tier_model": {
            "available": items_available,
            "rows": aggregate_tier_model(records) if items_available else [],
        },
        "stale_items": {
            "available": items_available,
            "rows": find_stale_items(records, args.stale_hours, now) if items_available else [],
        },
        "worker_usage": {
            "available": audit_available,
            "rows": worker_rows,
            "tokens_per_accepted_item": (
                join_tokens_per_accepted_item(records, transcript_by_agent)
                if items_available and audit_available
                else []
            ),
        },
        "scorecard": {
            "available": scorecard_available,
            "rows": scorecard_rows,
        },
        "caveats": list(CAVEATS),
    }
    return report


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _fmt_num(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown(report: dict) -> str:
    lines = ["# Maintenance-lane report", ""]
    meta = report["meta"]
    lines.append(
        f"Sprint {meta['sprint_id']}"
        + (f", since {meta['since']}" if meta["since"] else "")
        + f" -- generated {meta['generated_at']}"
    )
    lines.append("")

    lines.append("## Per tier / model")
    tm = report["tier_model"]
    if not tm["available"]:
        lines.append("_unavailable: no sprintctl items input given_")
    elif not tm["rows"]:
        lines.append("_no lane attempts in window_")
    else:
        lines.append(
            "| tier | model | attempts | first-pass | rework | rejected | escalated | accepted items |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in tm["rows"]:
            lines.append(
                "| {tier} | {model} | {attempts} | {fp} | {rw} | {rj} | {esc} | {accepted} |".format(
                    tier=row["tier"],
                    model=row["model"],
                    attempts=row["attempts"],
                    fp=_fmt_rate(row["first_pass_acceptance_rate"]),
                    rw=_fmt_rate(row["rework_rate"]),
                    rj=_fmt_rate(row["rejected_rate"]),
                    esc=_fmt_rate(row["escalated_rate"]),
                    accepted=len(row["accepted_items"]),
                )
            )
    lines.append("")

    lines.append(f"## Stale active items (no lane.review, older than {meta['stale_hours']}h)")
    stale = report["stale_items"]
    if not stale["available"]:
        lines.append("_unavailable: no sprintctl items input given_")
    elif not stale["rows"]:
        lines.append("_none_")
    else:
        lines.append("| id | title | status | age (h) |")
        lines.append("|---|---|---|---|")
        for row in stale["rows"]:
            lines.append(f"| {row['id']} | {row['title']} | {row['status']} | {row['age_hours']} |")
    lines.append("")

    lines.append("## Worker usage per model")
    wu = report["worker_usage"]
    if not wu["available"]:
        lines.append("_unavailable: no auditctl artifacts root found_")
    elif not wu["rows"]:
        lines.append("_no dispatch.exit events in window_")
    else:
        lines.append(
            "| model | sessions | input tokens | output tokens | median peak context | "
            "median wall (s) | abnormal exit rate |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for row in wu["rows"]:
            lines.append(
                "| {model} | {sessions} | {inp} | {out} | {peak} | {wall} | {abn} |".format(
                    model=row["model"],
                    sessions=row["sessions"],
                    inp=row["input_tokens"],
                    out=row["output_tokens"],
                    peak=_fmt_num(row["median_peak_context"], 0),
                    wall=_fmt_num(row["median_wall_seconds"], 1),
                    abn=_fmt_rate(row["abnormal_exit_rate"]),
                )
            )
        if wu["tokens_per_accepted_item"]:
            lines.append("")
            lines.append("Tokens per accepted item (joined via lane.dispatch `agent:<id>` tag):")
            lines.append("| model | accepted items joined | input tokens/item | output tokens/item |")
            lines.append("|---|---|---|---|")
            for row in wu["tokens_per_accepted_item"]:
                lines.append(
                    "| {model} | {n} | {inp} | {out} |".format(
                        model=row["model"],
                        n=row["accepted_items_joined"],
                        inp=_fmt_num(row["input_tokens_per_accepted_item"], 0),
                        out=_fmt_num(row["output_tokens_per_accepted_item"], 0),
                    )
                )
    lines.append("")

    lines.append("## Local scorecard per model")
    sc = report["scorecard"]
    if not sc["available"]:
        lines.append("_unavailable: no scorecard CSV found_")
    elif not sc["rows"]:
        lines.append("_no scorecard rows_")
    else:
        lines.append("| model | attempts | tests passed rate | accepted rate | median wall (ms) |")
        lines.append("|---|---|---|---|---|")
        for row in sc["rows"]:
            lines.append(
                "| {model} | {attempts} | {tp} | {acc} | {wall} |".format(
                    model=row["model"],
                    attempts=row["attempts"],
                    tp=_fmt_rate(row["tests_passed_rate"]),
                    acc=_fmt_rate(row["accepted_rate"]),
                    wall=_fmt_num(row["median_wall_ms"], 0),
                )
            )
    lines.append("")

    lines.append("## Caveats")
    for caveat in report["caveats"]:
        lines.append(f"- {caveat}")
    lines.append("")

    return "\n".join(lines)


def render_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=False)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sprint-id", type=int, default=None, help="sprintctl sprint id")
    parser.add_argument(
        "--items-json", type=Path, default=None, help="offline: 'sprintctl item list --json' output"
    )
    parser.add_argument(
        "--notes-json",
        type=Path,
        default=None,
        help="offline: directory of <item-id>.json files, each 'sprintctl item show --json' output "
        "(or a bare events list)",
    )
    parser.add_argument("--artifacts-root", type=Path, default=DEFAULT_ARTIFACTS_ROOT)
    parser.add_argument("--since", default=None, help="ISO date/datetime; filters dispatch.exit events")
    parser.add_argument("--scorecard", type=Path, default=DEFAULT_SCORECARD)
    parser.add_argument("--stale-hours", type=float, default=24.0)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.format == "json":
        print(render_json(report))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
