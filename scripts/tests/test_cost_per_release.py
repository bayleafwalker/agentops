"""Oracle for cost_per_release.py (TS-7: cost per Release, derived, no writer).

Fixtures below construct the join by hand (ledger tick -> lane notes -> item;
item -> release via item-decided) rather than against live data, so the
apportionment arithmetic is pinned independently of any one day's numbers.

Two ticks:

* **one-item tick** -- a single item spans nearly the whole window; the
  apportioned figure should be close to (and never exceed relevantly) the
  whole-tick figure.
* **three-item tick** -- three items with gaps between dispatch/review spans;
  the gap time is split equally across the three, and the three apportioned
  figures must sum back to the whole-tick cost (the live acceptance check on
  #2507/#2508 pins the same invariant against real data).

A third session in the three-item tick is absent from the cost log
entirely (cost_usd_costlog is None, not zero) and has no binding file
(binding_found is False, and the row is still emitted -- never dropped).
"""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


cpr = _load_module("cost_per_release_subject", SCRIPTS / "cost_per_release.py")


def _lane_event(event_id, item_id, event_type, actor, ts, tags, extra_payload=None):
    payload = {"tags": tags, "summary": event_type}
    if extra_payload:
        payload.update(extra_payload)
    return {
        "id": event_id,
        "sprint_id": 559,
        "work_item_id": item_id,
        "actor": actor,
        "event_type": event_type,
        "payload": json.dumps(payload),
        "created_at": ts,
    }


def _decided_event(event_id, item_id, ts, release_digest=None):
    payload = {"kind": "accept", "resolution": "accepted", "release_digest": release_digest}
    return {
        "id": event_id,
        "sprint_id": 559,
        "work_item_id": item_id,
        "actor": "devbox-agent-vuoro",
        "event_type": "item-decided",
        "payload": json.dumps(payload),
        "created_at": ts,
    }


LEDGER_ROWS = [
    # Noise: a non-"done" row must be ignored.
    {"decision": "run", "ts": "2026-01-01T00:05:00+00:00"},
    # One-item tick: window [00:10:00, 00:20:00], 600s.
    {
        "decision": "done",
        "mode": "implement",
        "minutes": 10.0,
        "session_id": "sess-A",
        "cost_usd": 5.0,
        "ts": "2026-01-01T00:20:00+00:00",
    },
    # Three-item tick: window [01:00:00, 01:30:00], 1800s.
    {
        "decision": "done",
        "mode": "implement",
        "minutes": 30.0,
        "session_id": "sess-B",
        "cost_usd": 9.0,
        "ts": "2026-01-01T01:30:00+00:00",
    },
]

EVENTS = [
    # Item #100: dispatch/review almost span the one-item tick's window.
    _lane_event(1, 100, "lane.dispatch", "devbox-agent-vuoro", "2026-01-01T00:12:00Z", ["lane", "tier:clerical"]),
    _lane_event(2, 100, "lane.review", "devbox-agent-vuoro", "2026-01-01T00:19:00Z", ["lane", "verdict:accepted"]),
    _decided_event(3, 100, "2026-01-01T00:19:05Z", release_digest=None),
    # Item #200: 300s span, 01:00:00-01:05:00.
    _lane_event(4, 200, "lane.dispatch", "devbox-agent-vuoro", "2026-01-01T01:00:00Z", ["lane", "tier:fast-build"]),
    _lane_event(5, 200, "lane.review", "devbox-agent-vuoro", "2026-01-01T01:05:00Z", ["lane", "verdict:accepted"]),
    _decided_event(6, 200, "2026-01-01T01:05:05Z", release_digest=None),
    # Item #201: 600s span, 01:10:00-01:20:00.
    _lane_event(7, 201, "lane.dispatch", "devbox-agent-vuoro", "2026-01-01T01:10:00Z", ["lane", "tier:fast-build"]),
    _lane_event(8, 201, "lane.review", "devbox-agent-vuoro", "2026-01-01T01:20:00Z", ["lane", "verdict:accepted"]),
    _decided_event(9, 201, "2026-01-01T01:20:05Z", release_digest=None),
    # Item #202: 180s span, 01:25:00-01:28:00.
    _lane_event(10, 202, "lane.dispatch", "devbox-agent-vuoro", "2026-01-01T01:25:00Z", ["lane", "tier:fast-build"]),
    _lane_event(11, 202, "lane.review", "devbox-agent-vuoro", "2026-01-01T01:28:00Z", ["lane", "verdict:accepted"]),
    _decided_event(12, 202, "2026-01-01T01:28:05Z", release_digest=None),
    # Wrong actor/tag: must never join.
    _lane_event(13, 999, "lane.dispatch", "workstation-vuoro", "2026-01-01T01:01:00Z", ["lane"]),
    _lane_event(14, 998, "lane.dispatch", "devbox-agent-vuoro", "2026-01-01T01:01:00Z", ["not-lane"]),
]

COST_ROWS = [
    # sess-A: two cumulative rows, newest (by ts) wins.
    {"session": "sess-A", "ts": "2026-01-01T00:15:00Z", "cost_usd": 4.5, "out": 10},
    {"session": "sess-A", "ts": "2026-01-01T00:19:30Z", "cost_usd": 6.0, "out": 20},
    # sess-B is deliberately ABSENT: sessions from the three-item tick have no
    # cost-log entry at all (the log covers top-level sessions only).
]


class CostPerReleaseTests(unittest.TestCase):
    def setUp(self):
        self.notes = cpr.lane_notes(EVENTS)
        self.rows_by_item = {}
        for tick in [row for row in LEDGER_ROWS if row.get("decision") == "done"]:
            for item_row in cpr.apportion_tick(tick, self.notes):
                self.rows_by_item.setdefault(item_row["item_id"], []).append(item_row)

    def test_newest_row_per_session_reduction(self):
        # Uses the real jsonl reducer against an on-disk fixture (cost-summary.sh's rule).
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            costs_path = Path(tmp) / "session-costs.jsonl"
            costs_path.write_text("\n".join(json.dumps(r) for r in COST_ROWS) + "\n")
            newest = cpr.load_newest_cost_per_session(costs_path)
        self.assertEqual(set(newest.keys()), {"sess-A"})
        self.assertEqual(newest["sess-A"]["cost_usd"], 6.0)

    def test_one_item_tick_apportioned_close_to_whole_tick(self):
        rows = self.rows_by_item[100]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["cost_usd_ledger"], 5.0)
        # 420s span + 0 gap (single item absorbs all gap) out of 600s window.
        self.assertAlmostEqual(row["cost_usd_apportioned"], 5.0, places=6)

    def test_three_item_tick_apportionment_sums_to_whole_tick(self):
        apportioned = {
            item_id: self.rows_by_item[item_id][0]["cost_usd_apportioned"] for item_id in (200, 201, 202)
        }
        # spans: 300s, 600s, 180s; occupied=1080s; gap=720s split 3 ways = 240s each.
        self.assertAlmostEqual(apportioned[200], 9.0 * 540 / 1800, places=6)
        self.assertAlmostEqual(apportioned[201], 9.0 * 840 / 1800, places=6)
        self.assertAlmostEqual(apportioned[202], 9.0 * 420 / 1800, places=6)
        self.assertAlmostEqual(sum(apportioned.values()), 9.0, places=6)
        for item_id in (200, 201, 202):
            self.assertEqual(self.rows_by_item[item_id][0]["cost_usd_ledger"], 9.0)

    def test_build_rows_flags_missing_binding_and_missing_costlog(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            costs_path = tmp_path / "session-costs.jsonl"
            costs_path.write_text("\n".join(json.dumps(r) for r in COST_ROWS) + "\n")
            bindings_dir = tmp_path / "session-bindings"
            bindings_dir.mkdir()
            (bindings_dir / "sess-A.json").write_text("{}")
            # No binding file for sess-B on purpose.

            done_ticks = [row for row in LEDGER_ROWS if row.get("decision") == "done"]
            newest_cost = cpr.load_newest_cost_per_session(costs_path)
            rows = cpr.build_rows(done_ticks, self.notes, EVENTS, newest_cost, bindings_dir)

        by_item = {}
        for row in rows:
            for item_id in row["item_ids"]:
                by_item[item_id] = row

        row_a = by_item[100]
        self.assertEqual(row_a["session_ids"], ["sess-A"])
        self.assertEqual(row_a["cost_usd_costlog"], 6.0)
        self.assertTrue(row_a["binding_found"]["sess-A"])
        self.assertFalse(row_a["released"])
        self.assertIsNone(row_a["release_digest"])

        row_b = by_item[200]
        self.assertEqual(row_b["session_ids"], ["sess-B"])
        # sess-B never appears in the cost log at all: None, not 0.
        self.assertIsNone(row_b["cost_usd_costlog"])
        self.assertFalse(row_b["binding_found"]["sess-B"])
        # Row is still emitted, never dropped, despite the missing binding.
        self.assertIn(200, by_item)
        self.assertIn(201, by_item)
        self.assertIn(202, by_item)

    def test_released_item_groups_by_release_digest(self):
        events = list(EVENTS) + [_decided_event(100, 100, "2026-01-01T00:19:10Z", release_digest="deadbeef")]
        done_ticks = [row for row in LEDGER_ROWS if row.get("decision") == "done"]
        rows = cpr.build_rows(done_ticks, self.notes, events, {}, Path("/nonexistent"))
        matches = [r for r in rows if 100 in r["item_ids"]]
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0]["released"])
        self.assertEqual(matches[0]["release_digest"], "deadbeef")

    def test_load_done_ticks_ignores_non_done_rows(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ticks.jsonl"
            ledger_path.write_text("\n".join(json.dumps(r) for r in LEDGER_ROWS) + "\n")
            ticks = cpr.load_done_ticks(ledger_path)
        self.assertEqual(len(ticks), 2)
        self.assertTrue(all(t["decision"] == "done" for t in ticks))


if __name__ == "__main__":
    unittest.main()
