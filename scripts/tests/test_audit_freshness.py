"""Oracle for scripts/audit_freshness.py (agentops#2533, Q6 / B16).

Item 2533: "repair auditctl shard capture and add 'last successful
authoritative event age' as a hard health metric (Q6)". The operator's #255
Q6 decision is emphatic (a): auditctl stays authoritative until S4 (TS-6), a
store that stopped receiving events is a *failed invariant*, and the answer
"is capture healthy?" must come from a health metric, not a manual ``ls``
(docs/plans/2026-09-27-telemetry-audit-and-operator-actions.md, §1 note, §3.6).

§3.6 fixes the observable contract this oracle encodes: every authoritative
audit store exposes **last successful authoritative event age** -- seconds
since the newest event *durably written* to the store (not attempted, not
buffered) -- as the gauge
``agentops_audit_last_authoritative_event_age_seconds{repo=...}`` for the
auditctl shards, and "hard" means an alert fires when a store is stale *and*
when its series is missing (``absent()`` alerts the same as a stale one).

The builder must provide ``scripts/audit_freshness.py`` (a hook-independent
reader of the committed shards under ``_artifacts/<repo>/audit/*.ndjson``,
the same shard set as ``commit_audit_shards.py`` / ``check_append_only_shards.py``)
with this CLI contract, exercised here as a black box:

    python scripts/audit_freshness.py --root DIR [--now ISO8601Z]
                                      --window-seconds N

* ``--root DIR``  : a tree holding shards at ``**/_artifacts/<repo>/audit/events-*.ndjson``.
* ``--now``       : reference "now" (UTC, trailing ``Z``); defaults to the wall clock.
* ``--window-seconds N`` : a store whose newest durable event is older than
  ``N`` seconds is stale.

Behaviour:

* stdout carries one Prometheus gauge line per audit store,
  ``agentops_audit_last_authoritative_event_age_seconds{repo="<scope>"} <age>``,
  where ``<scope>`` is the ``_artifacts/<scope>/audit`` path component and
  ``<age>`` is ``max(0, now - newest_durable_event_ts)`` in seconds. The event
  timestamp is read from ``ts`` (falling back to ``created_at`` / ``occurred_at``).
* exit 0 when every store is within the window; exit 1 (an alert) when any
  store is stale, naming the stale store on stderr/stdout.
* a ``--root`` with no shards / no parsable events at all is an alert
  (exit 1), never a silent "all healthy" -- silence is a failed invariant,
  not a quiet day (``absent()`` == stale).
* a trailing partial (non-newline-terminated) shard line is a write in
  flight, not a durable event: it is never counted as the newest event and
  never crashes the reader.

Every check has a failure condition, and each fails at this revision because
``scripts/audit_freshness.py`` does not yet exist.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

UTC = timezone.utc
SCRIPT = Path(__file__).resolve().parents[1] / "audit_freshness.py"
DAY = 86400

# The gauge §3.6 names, with a required repo="..." label somewhere in the set
# (host/stream labels may be present too) and a trailing numeric value.
METRIC = "agentops_audit_last_authoritative_event_age_seconds"


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def event(ts: datetime, *, source: str = "claude-hook", etype: str = "dispatch.exit") -> str:
    stamp = iso(ts)
    return json.dumps(
        {
            "id": f"ad:{stamp}",
            "ts": stamp,
            "created_at": stamp,
            "occurred_at": stamp,
            "type": etype,
            "event_type": etype,
            "source": source,
            "actor": source,
            "origin_stream_id": "83d0b252-ae8d-44eb-b413-e516a2c3d21f",
            "summary": "oracle fixture event",
            "payload": {},
        },
        sort_keys=True,
    )


def write_shard(root: Path, repo: str, day: str, events: list[str], *, terminated: bool = True) -> Path:
    """Write one shard file ``_artifacts/<repo>/audit/events-<day>.ndjson``."""
    path = root / "_artifacts" / repo / "audit" / f"events-{day}.ndjson"
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(line + "\n" for line in events)
    if events and not terminated:
        # last line left mid-append: strip its trailing newline
        body = body[:-1]
    path.write_text(body)
    return path


def run(root: Path, now: datetime, window: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(root),
            "--now",
            iso(now),
            "--window-seconds",
            str(window),
        ],
        capture_output=True,
        text=True,
    )


def gauges(stdout: str) -> dict[str, float]:
    """Map repo label -> reported age, over lines emitting the §3.6 gauge."""
    out: dict[str, float] = {}
    pat = re.compile(
        rf"^{re.escape(METRIC)}\{{(?P<labels>[^}}]*)\}}\s+(?P<val>-?\d+(?:\.\d+)?)\s*$"
    )
    repo_re = re.compile(r'repo="(?P<repo>[^"]+)"')
    for line in stdout.splitlines():
        m = pat.match(line.strip())
        if not m:
            continue
        rm = repo_re.search(m.group("labels"))
        if rm:
            out[rm.group("repo")] = float(m.group("val"))
    return out


def test_age_reported_per_repo_store():
    """Newest durable event drives the age, computed per audit store.

    Failure condition: the gauge is missing for a store, or its age does not
    match ``now - newest_event_ts`` (per repo, not one global aggregate).
    """
    import tempfile

    now = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # agentops store: newest event 1h old.
        write_shard(
            root,
            "agentops",
            "2026-09-28",
            [event(now - timedelta(hours=6)), event(now - timedelta(hours=1))],
        )
        # demo store: newest event 3h old (a separate series).
        write_shard(
            root,
            "demo",
            "2026-09-28",
            [event(now - timedelta(hours=3))],
        )
        proc = run(root, now, DAY)
        found = gauges(proc.stdout)
        assert "agentops" in found, proc.stdout + proc.stderr
        assert "demo" in found, proc.stdout + proc.stderr
        assert abs(found["agentops"] - 3600) < 2, found
        assert abs(found["demo"] - 10800) < 2, found


def test_fresh_store_exits_zero():
    """Every store within the window: no alert.

    Failure condition: a within-window store makes the exporter exit nonzero.
    """
    import tempfile

    now = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_shard(root, "agentops", "2026-09-28", [event(now - timedelta(hours=2))])
        proc = run(root, now, DAY)  # 2h old, window 24h -> fresh
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_stale_store_alerts():
    """A store older than the window is a hard alert (exit 1) that names it.

    Failure condition: a stale store exits 0, or the stale store is not named.
    """
    import tempfile

    now = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # newest event ~30h old, window 24h -> stale.
        write_shard(root, "agentops", "2026-09-27", [event(now - timedelta(hours=30))])
        proc = run(root, now, DAY)
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "agentops" in (proc.stdout + proc.stderr)
        # The gauge is still emitted, carrying the (stale) age.
        found = gauges(proc.stdout)
        assert "agentops" in found and found["agentops"] > DAY, found


def test_absent_store_alerts_like_stale():
    """No shards / no durable events at all is an alert, not a silent pass.

    §3.6: a missing series alerts the same as a stale one (``absent()``).
    Failure condition: an empty audit tree exits 0.
    """
    import tempfile

    now = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "_artifacts" / "agentops" / "audit").mkdir(parents=True)
        proc = run(root, now, DAY)
        assert proc.returncode == 1, proc.stdout + proc.stderr


def test_partial_trailing_line_not_counted():
    """A mid-append last line is not a durable event and never crashes the read.

    §3.6: the age counts only events durably written (not attempted, not
    buffered), the same partial-line rule ``commit_audit_shards.py`` applies.
    Failure condition: the unterminated newest line is counted (age ~= 0s),
    or the reader errors on it.
    """
    import tempfile

    now = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write_shard(
            root,
            "agentops",
            "2026-09-28",
            [event(now - timedelta(hours=1)), event(now - timedelta(seconds=1))],
            terminated=False,  # the very recent last line is not newline-terminated
        )
        proc = run(root, now, DAY)
        found = gauges(proc.stdout)
        assert "agentops" in found, proc.stdout + proc.stderr
        # The durable newest event is the 1h-old, terminated one -- not the
        # 1s-old partial line.
        assert abs(found["agentops"] - 3600) < 2, found


def test_malformed_line_does_not_crash():
    """A non-JSON shard line is skipped, not fatal.

    Failure condition: a garbage line makes the exporter error out instead of
    reporting the newest parsable durable event.
    """
    import tempfile

    now = datetime(2026, 9, 28, 18, 0, tzinfo=UTC)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = write_shard(root, "agentops", "2026-09-28", [event(now - timedelta(hours=2))])
        with path.open("a") as fh:
            fh.write("this is not json\n")
        proc = run(root, now, DAY)
        found = gauges(proc.stdout)
        assert "agentops" in found, proc.stdout + proc.stderr
        assert abs(found["agentops"] - 7200) < 2, found
