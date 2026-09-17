"""Oracle for maintenance_lane_report.py (docs/runbooks/maintenance-lane.md, "Telemetry").

The report joins four independently-optional sources -- sprintctl lane notes, auditctl
``dispatch.exit`` shards, subagent transcripts, and the local scorecard CSV -- and must
never crash on a missing or malformed one; a missing source makes its section
"unavailable", nothing more.

Fixtures below mirror the real JSON shapes observed live against sprint 559
(``sprintctl item list --sprint-id 559 --json`` / ``item show --id <n> --json`` from
``agentops``, ``SPRINTCTL_BACKEND=served``): ``item show`` returns
``{"item": {...}, "events": [...]}`` where each event's ``payload`` is a *JSON string*
(not an object) carrying ``tags``/``summary``/``detail``/``git_branch``/``git_worktree``.

This file pins the coordinator's attempt-2 review corrections (34e8274 was REWORK), each
verified against live sprint 559 / a live subagent transcript before being encoded here:

1. **Transcript resolution.** ``dispatch.exit``'s ``metadata.transcript_path`` for a
   SUBAGENT exit is the PARENT session's transcript, not the subagent's own -- verified
   live: agent ``ae70fc0a294de1cb0``'s dispatch.exit metadata pointed at
   ``.../279bc82d-d705-42ba-bd8c-a51dbee6538e.jsonl`` (the coordinator session), while its
   own records live at
   ``.../279bc82d-d705-42ba-bd8c-a51dbee6538e/subagents/agent-ae70fc0a294de1cb0.jsonl``
   (confirmed to exist on disk). Using the parent file attributes every sibling subagent's
   tokens to each one.
2. **Usage dedup is MAX per field, not last-record-wins and not summed.** Verified against
   that same live subagent transcript: 81 assistant records collapse to 36 distinct
   ``message.id``s; the correct dedup gives ~1,760,415 input tokens (input + cache_read +
   cache_creation, summed across the 36 deduped messages) and a peak single-message context
   of 61,742.
3. **An attempt is one lane.review note, not a dispatch/review position-pairing.** Verified
   on item 2374 (sprint 559): it carries two ``lane.dispatch`` notes for the same resumed
   agent (the first before the agent id was known, the second after) but exactly two
   ``lane.review`` notes (rework, then accepted) -- rates are computed over review notes.
4. **Multiple ``model:`` tags on one note combine into one bucket key.** Verified on item
   2375's dispatch note: ``tags`` carries both ``model:local3090/worker-fast`` and
   ``model:local3090/devstral``; naive ``dict``-based tag parsing (last key wins) silently
   drops one.
5. **``verdict:blocked`` is its own outcome, not dropped.** Verified on item 2375's review
   note: ``verdict:blocked`` with a llama-swap GPU-runtime failure as the reason.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mlr = _load_module("maintenance_lane_report_subject", SCRIPTS / "maintenance_lane_report.py")


class _TempDir:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        return Path(self._tmp.name)

    def __exit__(self, exc_type, exc, tb):
        self._tmp.cleanup()
        return False


# --------------------------------------------------------------------------
# Fixture builders
# --------------------------------------------------------------------------

def _event(event_type, actor, payload, created_at, event_id=1):
    return {
        "repo_id": "agentops",
        "id": event_id,
        "work_item_id": None,
        "source_type": "actor",
        "actor": actor,
        "event_type": event_type,
        "payload": json.dumps(payload),
        "created_at": created_at,
    }


def _item(item_id, title, status, created_at, updated_at):
    return {
        "repo_id": "agentops",
        "id": item_id,
        "track_id": 1000 + item_id,
        "sprint_id": 559,
        "title": title,
        "status": status,
        "assignee": None,
        "priority": 3,
        "created_at": created_at,
        "updated_at": updated_at,
        "aggregate_uuid": f"uuid-{item_id}",
        "track_name": "telemetry",
    }


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data))


def _write_notes_dir(tmp_path: Path, notes: dict[int, list[dict]]) -> Path:
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    for item_id, events in notes.items():
        _write_json(notes_dir / f"{item_id}.json", {"events": events})
    return notes_dir


def _audit_shard(root: Path, repo: str, day: str, records: list[dict]) -> Path:
    shard_dir = root / "_artifacts" / repo / "audit"
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard = shard_dir / f"events-{day}.ndjson"
    with shard.open("w") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")
    return shard


def _dispatch_exit(agent_id, project, terminal_reason, transcript_path, created_at):
    return {
        "event_type": "dispatch.exit",
        "type": "dispatch.exit",
        "created_at": created_at,
        "metadata": {
            "agent_id": agent_id,
            "project": project,
            "terminal_reason": terminal_reason,
            "transcript_path": str(transcript_path) if transcript_path else None,
            "reset_at": None,
        },
    }


def _assistant_record(message_id, model, timestamp, input_tokens, cache_read, cache_creation, output_tokens):
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {
            "id": message_id,
            "model": model,
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
                "output_tokens": output_tokens,
            },
        },
    }


def _write_transcript(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")


class _Args:
    """Minimal stand-in for argparse.Namespace with the fields build_report reads."""

    def __init__(self, **kwargs):
        self.sprint_id = kwargs.get("sprint_id")
        self.items_json = kwargs.get("items_json")
        self.notes_json = kwargs.get("notes_json")
        self.artifacts_root = kwargs.get("artifacts_root")
        self.since = kwargs.get("since")
        self.scorecard = kwargs.get("scorecard")
        self.stale_hours = kwargs.get("stale_hours", 24.0)
        self.format = kwargs.get("format", "markdown")


# --------------------------------------------------------------------------
# Tag / payload parsing
# --------------------------------------------------------------------------

class TagParsingTests(unittest.TestCase):
    def test_kv_and_flag_tags_split(self):
        kv, flags = mlr._parse_tags(
            ["lane", "tier:fast-build", "model:claude-sonnet-5", "harness:claude-subagent"]
        )
        self.assertEqual(kv, {"tier": "fast-build", "model": "claude-sonnet-5", "harness": "claude-subagent"})
        self.assertEqual(flags, {"lane"})

    def test_verdict_from_tag_wins_over_summary(self):
        payload = {"summary": "rework: needs another pass", "tags": ["lane", "verdict:accepted"]}
        kv, _flags = mlr._parse_tags(payload["tags"])
        self.assertEqual(mlr._verdict_of(payload, kv), "accepted")

    def test_verdict_falls_back_to_summary_first_word(self):
        payload = {"summary": "rejected: does not meet acceptance criteria", "tags": ["lane"]}
        kv, _flags = mlr._parse_tags(payload["tags"])
        self.assertEqual(mlr._verdict_of(payload, kv), "rejected")

    def test_blocked_is_a_recognized_verdict(self):
        payload = {"summary": "blocked: llama-swap GPU runtime failure", "tags": ["lane", "verdict:blocked"]}
        kv, _flags = mlr._parse_tags(payload["tags"])
        self.assertEqual(mlr._verdict_of(payload, kv), "blocked")

    def test_payload_string_is_parsed(self):
        event = {"payload": json.dumps({"tags": ["lane"], "summary": "x"})}
        self.assertEqual(mlr._payload(event), {"tags": ["lane"], "summary": "x"})

    def test_payload_malformed_json_yields_empty_dict(self):
        event = {"payload": "{not json"}
        self.assertEqual(mlr._payload(event), {})

    def test_multi_model_tags_combine_sorted_and_joined(self):
        tags = ["lane", "model:local3090/worker-fast", "model:local3090/devstral"]
        self.assertEqual(mlr._model_key(tags), "local3090/devstral+local3090/worker-fast")

    def test_single_model_tag_key_is_unjoined(self):
        self.assertEqual(mlr._model_key(["model:claude-sonnet-5"]), "claude-sonnet-5")

    def test_no_model_tag_yields_none(self):
        self.assertIsNone(mlr._model_key(["lane", "tier:fast-build"]))


# --------------------------------------------------------------------------
# Per tier / model aggregation (section a)
# --------------------------------------------------------------------------

class TierModelAggregationTests(unittest.TestCase):
    def test_accepted_first_pass_and_rework_rates(self):
        item_a = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
        events_a = [
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5", "harness:claude-subagent"], "summary": "Dispatched"},
                "2026-09-14T18:53:49Z",
                1,
            ),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Accepted"},
                "2026-09-14T18:58:24Z",
                2,
            ),
        ]
        item_b = _item(2378, "B", "active", "2026-09-14T19:00:00Z", "2026-09-14T19:05:00Z")
        events_b = [
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5", "harness:claude-subagent"], "summary": "Dispatched"},
                "2026-09-14T19:00:01Z",
                3,
            ),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:rework", "attempt:1", "tier:fast-build", "model:claude-sonnet-5"], "summary": "rework: wrong path touched"},
                "2026-09-14T19:04:00Z",
                4,
            ),
        ]
        records = mlr.build_item_records([item_a, item_b], {2377: events_a, 2378: events_b})
        rows = mlr.aggregate_tier_model(records)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["tier"], row["model"]), ("fast-build", "claude-sonnet-5"))
        self.assertEqual(row["items"], 2)
        self.assertEqual(row["attempts"], 2)
        self.assertAlmostEqual(row["first_pass_item_rate"], 0.5)
        self.assertAlmostEqual(row["rework_item_rate"], 0.5)
        self.assertEqual(row["rejected_item_rate"], 0.0)
        self.assertEqual(row["blocked_item_rate"], 0.0)
        self.assertEqual(row["accepted_items"], [2377])
        self.assertAlmostEqual(row["attempts_per_accepted_item"], 1.0)

    def test_dispatch_without_review_contributes_no_attempt(self):
        # Real shape of a not-yet-reviewed item (2372 before its first review landed):
        # attempts are counted from lane.review notes only.
        item = _item(2372, "C", "active", "2026-09-14T18:53:46Z", "2026-09-14T18:55:44Z")
        events = [
            _event(
                "lane.dispatch",
                "coordinator",
                {
                    "tags": ["lane", "tier:fast-build", "model:claude-sonnet-5", "harness:claude-subagent"],
                    "summary": "Dispatched to worker (claude-sonnet-5, fast-build)",
                    "git_branch": "feat/headroom-writer",
                    "git_worktree": "/projects/dev/_wt/agentops-headroom-writer",
                },
                "2026-09-14T18:58:23Z",
                1,
            )
        ]
        records = mlr.build_item_records([item], {2372: events})
        self.assertEqual(mlr.aggregate_tier_model(records), [])

    def test_two_dispatch_notes_one_resumed_agent_two_reviews_is_two_attempts_one_item(self):
        # Real shape of item 2374: an initial dispatch (no agent id yet), a follow-up
        # dispatch once the agent id is known, then rework -> accepted.
        item = _item(2374, "D", "active", "2026-09-14T18:53:47Z", "2026-09-14T19:03:20Z")
        events = [
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:fast-build", "model:claude-haiku-4-5", "harness:claude-subagent"], "summary": "Dispatched"},
                "2026-09-14T18:58:23Z",
                1,
            ),
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:fast-build", "model:claude-haiku-4-5", "harness:claude-subagent", "agent:ae70fc0a294de1cb0"], "summary": "Dispatched"},
                "2026-09-14T19:00:38Z",
                2,
            ),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:rework", "attempt:1", "tier:fast-build", "model:claude-haiku-4-5", "agent:ae70fc0a294de1cb0"], "summary": "rework: fix needed"},
                "2026-09-14T19:01:27Z",
                3,
            ),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:accepted", "attempt:2", "tier:fast-build", "model:claude-haiku-4-5", "agent:ae70fc0a294de1cb0"], "summary": "accepted: matches criteria"},
                "2026-09-14T19:03:20Z",
                4,
            ),
        ]
        records = mlr.build_item_records([item], {2374: events})
        rows = mlr.aggregate_tier_model(records)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["items"], 1)
        self.assertEqual(row["attempts"], 2)
        self.assertEqual(row["accepted_items"], [2374])
        # One item, and it did carry a rework verdict at some point -> 100% of items.
        self.assertAlmostEqual(row["rework_item_rate"], 1.0)
        # Not first-pass: the item's earliest review verdict is rework, not accepted.
        self.assertEqual(row["first_pass_item_rate"], 0.0)
        self.assertAlmostEqual(row["attempts_per_accepted_item"], 2.0)

    def test_multi_model_dispatch_tags_form_combined_bucket_when_review_lacks_model(self):
        # Real shape of item 2375: dispatch carries two model tags; the review that
        # follows carries only one of them (the model actually run for that attempt) --
        # exercise the fallback path by omitting the model tag on the review entirely.
        item = _item(2375, "E", "blocked", "2026-09-14T18:53:47Z", "2026-09-14T19:02:25Z")
        events = [
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:local", "model:local3090/worker-fast", "model:local3090/devstral", "harness:opencode"], "summary": "Dispatched"},
                "2026-09-14T18:58:24Z",
                1,
            ),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:blocked", "attempt:1", "tier:local", "agent:aad7a6fbf0e3d21d8"], "summary": "blocked: llama-swap GPU runtime failure"},
                "2026-09-14T19:02:25Z",
                2,
            ),
        ]
        records = mlr.build_item_records([item], {2375: events})
        rows = mlr.aggregate_tier_model(records)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["tier"], "local")
        self.assertEqual(row["model"], "local3090/devstral+local3090/worker-fast")
        self.assertEqual(row["items"], 1)
        self.assertEqual(row["attempts"], 1)
        self.assertAlmostEqual(row["blocked_item_rate"], 1.0)
        self.assertEqual(row["accepted_items"], [])
        self.assertIsNone(row["attempts_per_accepted_item"])

    def test_blocked_verdict_has_its_own_rate_and_does_not_vanish(self):
        item = _item(2375, "E", "blocked", "2026-09-14T18:53:47Z", "2026-09-14T19:02:25Z")
        events = [
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:local", "model:local3090/worker-fast"], "summary": "Dispatched"},
                "2026-09-14T18:58:24Z",
                1,
            ),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:blocked", "attempt:1", "tier:local", "model:local3090/worker-fast", "agent:aad7a6fbf0e3d21d8"], "summary": "blocked: backend broken"},
                "2026-09-14T19:02:25Z",
                2,
            ),
        ]
        records = mlr.build_item_records([item], {2375: events})
        row = mlr.aggregate_tier_model(records)[0]
        self.assertEqual(row["items"], 1)
        self.assertEqual(row["attempts"], 1)
        self.assertAlmostEqual(row["blocked_item_rate"], 1.0)
        self.assertEqual(row["first_pass_item_rate"], 0.0)
        self.assertEqual(row["accepted_items"], [])

    def test_empty_items_yields_no_rows(self):
        self.assertEqual(mlr.aggregate_tier_model([]), [])

    def test_blocked_then_recovered_and_accepted_is_not_counted_blocked(self):
        # An item blocked on one attempt (e.g. transient backend failure) but reworked and
        # accepted afterward should not still read as "blocked" -- blocked_item_rate looks
        # only at the item's LATEST verdict, unlike rework/rejected/escalated which count
        # an item if the verdict appears on *any* attempt.
        item = _item(2400, "F", "done", "2026-09-14T18:00:00Z", "2026-09-14T18:20:00Z")
        events = [
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:blocked", "tier:fast-build", "model:claude-sonnet-5"], "summary": "blocked: backend broken"},
                "2026-09-14T18:05:00Z",
                1,
            ),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:accepted", "tier:fast-build", "model:claude-sonnet-5"], "summary": "accepted: backend recovered"},
                "2026-09-14T18:20:00Z",
                2,
            ),
        ]
        records = mlr.build_item_records([item], {2400: events})
        row = mlr.aggregate_tier_model(records)[0]
        self.assertEqual(row["items"], 1)
        self.assertEqual(row["attempts"], 2)
        self.assertEqual(row["blocked_item_rate"], 0.0)
        self.assertEqual(row["first_pass_item_rate"], 0.0)
        self.assertEqual(row["accepted_items"], [2400])
        self.assertAlmostEqual(row["attempts_per_accepted_item"], 2.0)

    def test_accepted_first_try_is_full_first_pass_rate(self):
        item = _item(2383, "G", "done", "2026-09-14T18:00:00Z", "2026-09-14T18:05:00Z")
        events = [
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-haiku-4-5"], "summary": "Accepted"},
                "2026-09-14T18:05:00Z",
                1,
            ),
        ]
        records = mlr.build_item_records([item], {2383: events})
        row = mlr.aggregate_tier_model(records)[0]
        self.assertEqual(row["items"], 1)
        self.assertEqual(row["attempts"], 1)
        self.assertAlmostEqual(row["first_pass_item_rate"], 1.0)
        self.assertEqual(row["rework_item_rate"], 0.0)
        self.assertEqual(row["accepted_items"], [2383])
        self.assertAlmostEqual(row["attempts_per_accepted_item"], 1.0)

    def test_live_sprint_559_fast_build_item_rates_match_expected(self):
        # Regression for agentops#2385: rates keyed to reviewed ATTEMPTS instead of items
        # showed 33.3% first-pass for both fast-build models on live sprint 559 (2026-09-14)
        # even though each model resolved one item first-try and one item after rework --
        # the correct per-item first-pass and rework rates are 50%/50%.
        items = [
            _item(2374, "haiku rework-then-accept", "done", "2026-09-14T18:53:47Z", "2026-09-14T19:03:20Z"),
            _item(2383, "haiku accepted first", "done", "2026-09-14T19:10:00Z", "2026-09-14T19:15:00Z"),
            _item(2373, "sonnet accepted first", "done", "2026-09-14T18:50:00Z", "2026-09-14T18:55:00Z"),
            _item(2372, "sonnet rework-then-accept", "done", "2026-09-14T18:53:46Z", "2026-09-14T19:10:00Z"),
        ]
        notes = {
            2374: [
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:rework", "tier:fast-build", "model:claude-haiku-4-5"], "summary": "rework: fix needed"}, "2026-09-14T19:01:27Z", 1),
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "tier:fast-build", "model:claude-haiku-4-5"], "summary": "accepted"}, "2026-09-14T19:03:20Z", 2),
            ],
            2383: [
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-haiku-4-5"], "summary": "accepted"}, "2026-09-14T19:15:00Z", 3),
            ],
            2373: [
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-sonnet-5"], "summary": "accepted"}, "2026-09-14T18:55:00Z", 4),
            ],
            2372: [
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:rework", "tier:fast-build", "model:claude-sonnet-5"], "summary": "rework: needs another pass"}, "2026-09-14T19:05:00Z", 5),
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "tier:fast-build", "model:claude-sonnet-5"], "summary": "accepted"}, "2026-09-14T19:10:00Z", 6),
            ],
        }
        records = mlr.build_item_records(items, notes)
        rows = {row["model"]: row for row in mlr.aggregate_tier_model(records)}
        self.assertEqual(set(rows), {"claude-haiku-4-5", "claude-sonnet-5"})
        for model in ("claude-haiku-4-5", "claude-sonnet-5"):
            row = rows[model]
            self.assertEqual(row["tier"], "fast-build")
            self.assertEqual(row["items"], 2)
            self.assertAlmostEqual(row["first_pass_item_rate"], 0.5)
            self.assertAlmostEqual(row["rework_item_rate"], 0.5)


# --------------------------------------------------------------------------
# Stale items (section b)
# --------------------------------------------------------------------------

class StaleItemsTests(unittest.TestCase):
    def test_active_item_without_review_older_than_threshold_is_stale(self):
        now = mlr._parse_ts("2026-09-15T20:00:00Z")
        item = _item(2372, "C", "active", "2026-09-14T18:53:46Z", "2026-09-14T18:55:44Z")
        events = [
            _event("lane.dispatch", "coordinator", {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"}, "2026-09-14T18:58:23Z", 1)
        ]
        records = mlr.build_item_records([item], {2372: events})
        stale = mlr.find_stale_items(records, stale_hours=24.0, now=now)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["id"], 2372)

    def test_recent_item_without_review_is_not_stale(self):
        now = mlr._parse_ts("2026-09-14T20:00:00Z")
        item = _item(2372, "C", "active", "2026-09-14T18:53:46Z", "2026-09-14T18:55:44Z")
        events = [
            _event("lane.dispatch", "coordinator", {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"}, "2026-09-14T18:58:23Z", 1)
        ]
        records = mlr.build_item_records([item], {2372: events})
        stale = mlr.find_stale_items(records, stale_hours=24.0, now=now)
        self.assertEqual(stale, [])

    def test_reviewed_item_is_never_stale(self):
        now = mlr._parse_ts("2026-09-20T20:00:00Z")
        item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
        events = [
            _event("lane.dispatch", "coordinator", {"tags": ["lane"], "summary": "Dispatched"}, "2026-09-14T18:53:49Z", 1),
            _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "first-pass"], "summary": "Accepted"}, "2026-09-14T18:58:24Z", 2),
        ]
        records = mlr.build_item_records([item], {2377: events})
        stale = mlr.find_stale_items(records, stale_hours=24.0, now=now)
        self.assertEqual(stale, [])

    def test_done_item_without_review_is_never_stale(self):
        now = mlr._parse_ts("2026-09-20T20:00:00Z")
        item = _item(2379, "D", "done", "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z")
        records = mlr.build_item_records([item], {})
        stale = mlr.find_stale_items(records, stale_hours=24.0, now=now)
        self.assertEqual(stale, [])


# --------------------------------------------------------------------------
# auditctl shard discovery + dispatch.exit loading
# --------------------------------------------------------------------------

class AuditShardTests(unittest.TestCase):
    def test_finds_shard_and_filters_by_since(self):
        with _TempDir() as root:
            _audit_shard(root, "agentops", "2026-09-01", [_dispatch_exit("a1", "agentops", "completed", None, "2026-09-01T00:00:00Z")])
            _audit_shard(root, "agentops", "2026-09-10", [_dispatch_exit("a2", "agentops", "completed", None, "2026-09-10T00:00:00Z")])
            events = mlr.load_dispatch_exit_events(root, since=mlr._parse_ts("2026-09-05T00:00:00Z"))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["metadata"]["agent_id"], "a2")

    def test_skips_wt_and_projects_directories(self):
        with _TempDir() as root:
            _audit_shard(root / "_wt" / "some-worktree", "agentops", "2026-09-10", [_dispatch_exit("skip-me", "agentops", "completed", None, "2026-09-10T00:00:00Z")])
            _audit_shard(root, "agentops", "2026-09-10", [_dispatch_exit("keep-me", "agentops", "completed", None, "2026-09-10T00:00:00Z")])
            events = mlr.load_dispatch_exit_events(root, since=None)
            agent_ids = {e["metadata"]["agent_id"] for e in events}
            self.assertEqual(agent_ids, {"keep-me"})

    def test_missing_artifacts_root_yields_no_events(self):
        events = mlr.load_dispatch_exit_events(Path("/nonexistent/root/for/test"), since=None)
        self.assertEqual(events, [])

    def test_ignores_non_ndjson_and_malformed_lines(self):
        with _TempDir() as root:
            shard_dir = root / "_artifacts" / "agentops" / "audit"
            shard_dir.mkdir(parents=True)
            shard = shard_dir / "events-2026-09-10.ndjson"
            shard.write_text(
                "not json at all\n"
                + json.dumps(_dispatch_exit("ok", "agentops", "completed", None, "2026-09-10T00:00:00Z"))
                + "\n"
                + json.dumps({"event_type": "other.event", "created_at": "2026-09-10T00:00:00Z"})
                + "\n"
            )
            events = mlr.load_dispatch_exit_events(root, since=None)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["metadata"]["agent_id"], "ok")


# --------------------------------------------------------------------------
# Subagent transcript resolution (fix #1: parent vs. subagent transcript)
# --------------------------------------------------------------------------

class TranscriptResolutionTests(unittest.TestCase):
    def test_resolves_subagent_specific_file_over_parent(self):
        with _TempDir() as root:
            session_id = "279bc82d-d705-42ba-bd8c-a51dbee6538e"
            parent = root / f"{session_id}.jsonl"
            parent.write_text("")  # parent transcript exists too, but must not be chosen
            subagent_path = root / session_id / "subagents" / "agent-ae70fc0a294de1cb0.jsonl"
            subagent_path.parent.mkdir(parents=True)
            subagent_path.write_text("")

            resolved, used_fallback = mlr.resolve_subagent_transcript(str(parent), "ae70fc0a294de1cb0")
            self.assertEqual(resolved, subagent_path)
            self.assertFalse(used_fallback)

    def test_falls_back_to_parent_when_subagent_file_missing_and_flags_it(self):
        with _TempDir() as root:
            session_id = "some-session"
            parent = root / f"{session_id}.jsonl"
            parent.write_text("")
            # No subagents/ directory at all.
            resolved, used_fallback = mlr.resolve_subagent_transcript(str(parent), "missing-agent")
            self.assertEqual(resolved, parent)
            self.assertTrue(used_fallback)

    def test_no_agent_id_falls_back_to_parent(self):
        with _TempDir() as root:
            parent = root / "s.jsonl"
            parent.write_text("")
            resolved, used_fallback = mlr.resolve_subagent_transcript(str(parent), None)
            self.assertEqual(resolved, parent)
            self.assertTrue(used_fallback)

    def test_no_transcript_path_is_not_a_fallback(self):
        resolved, used_fallback = mlr.resolve_subagent_transcript(None, "some-agent")
        self.assertIsNone(resolved)
        self.assertFalse(used_fallback)


# --------------------------------------------------------------------------
# Transcript summarization: MAX-per-field de-duplication by message.id
# --------------------------------------------------------------------------

class TranscriptDedupTests(unittest.TestCase):
    def test_multi_record_message_is_deduplicated_by_max_not_summed(self):
        with _TempDir() as tmp:
            path = tmp / "transcript.jsonl"
            records = [
                _assistant_record("msg_1", "claude-opus-5", "2026-09-12T17:30:05Z", 2, 24750, 9884, 1),
                _assistant_record("msg_1", "claude-opus-5", "2026-09-12T17:30:07Z", 2, 24750, 9884, 1),
                _assistant_record("msg_1", "claude-opus-5", "2026-09-12T17:30:08Z", 2, 24750, 9884, 340),
                _assistant_record("msg_2", "claude-opus-5", "2026-09-12T17:30:13Z", 2, 34634, 1960, 5),
                _assistant_record("msg_2", "claude-opus-5", "2026-09-12T17:30:15Z", 2, 34634, 1960, 333),
            ]
            _write_transcript(path, records)
            summary = mlr.summarize_transcript(path)
            self.assertEqual(summary["messages"], 2)
            self.assertEqual(summary["output_tokens"], 340 + 333)
            expected_input = (2 + 24750 + 9884) + (2 + 34634 + 1960)
            self.assertEqual(summary["input_tokens"], expected_input)
            self.assertEqual(summary["peak_context"], max(2 + 24750 + 9884, 2 + 34634 + 1960))
            self.assertEqual(summary["model"], "claude-opus-5")
            self.assertAlmostEqual(summary["wall_seconds"], 10.0)

    def test_max_is_not_the_last_record_when_a_field_shrinks(self):
        # A pathological but real-possible stream where an earlier record carries a
        # HIGHER cache_creation value than the final record for the same message.id:
        # keeping "last wins" would under-count; MAX per field must not.
        with _TempDir() as tmp:
            path = tmp / "t.jsonl"
            records = [
                _assistant_record("m1", "claude-sonnet-5", "2026-09-14T18:00:00Z", 5, 100, 9000, 1),
                _assistant_record("m1", "claude-sonnet-5", "2026-09-14T18:00:01Z", 5, 100, 500, 250),
            ]
            _write_transcript(path, records)
            summary = mlr.summarize_transcript(path)
            # cache_creation max(9000, 500) = 9000; output max(1, 250) = 250.
            self.assertEqual(summary["input_tokens"], 5 + 100 + 9000)
            self.assertEqual(summary["output_tokens"], 250)

    def test_missing_transcript_returns_none(self):
        self.assertIsNone(mlr.summarize_transcript(Path("/no/such/transcript.jsonl")))

    def test_empty_transcript_returns_zeroed_summary(self):
        with _TempDir() as tmp:
            path = tmp / "empty.jsonl"
            path.write_text("")
            summary = mlr.summarize_transcript(path)
            self.assertEqual(summary["messages"], 0)
            self.assertIsNone(summary["wall_seconds"])

    def test_synthetic_model_excluded_from_model_vote(self):
        with _TempDir() as tmp:
            path = tmp / "t.jsonl"
            records = [
                _assistant_record("m1", "<synthetic>", "2026-09-12T17:30:05Z", 0, 0, 0, 0),
                _assistant_record("m2", "claude-sonnet-5", "2026-09-12T17:30:06Z", 5, 5, 5, 5),
            ]
            _write_transcript(path, records)
            summary = mlr.summarize_transcript(path)
            self.assertEqual(summary["model"], "claude-sonnet-5")


# --------------------------------------------------------------------------
# Worker usage per model + item-token join (section c)
# --------------------------------------------------------------------------

class WorkerUsageTests(unittest.TestCase):
    def test_sessions_tokens_and_abnormal_rate_per_model_using_subagent_transcript(self):
        with _TempDir() as root:
            session_id = "sess-1"
            parent = root / f"{session_id}.jsonl"
            parent.write_text("")  # exists, but must not be summed
            subagent_path = root / session_id / "subagents" / "agent-w1.jsonl"
            _write_transcript(subagent_path, [_assistant_record("m1", "claude-sonnet-5", "2026-09-14T18:00:00Z", 10, 0, 0, 20)])

            events = [
                _dispatch_exit("w1", "agentops", "completed", parent, "2026-09-14T18:00:01Z"),
                _dispatch_exit("agent-2", "agentops", "error", None, "2026-09-14T18:05:00Z"),
            ]
            rows, _cache, by_agent, fallback_count = mlr.summarize_worker_usage(events)
            by_model = {row["model"]: row for row in rows}
            self.assertIn("claude-sonnet-5", by_model)
            self.assertEqual(by_model["claude-sonnet-5"]["sessions"], 1)
            self.assertEqual(by_model["claude-sonnet-5"]["input_tokens"], 10)
            self.assertEqual(by_model["claude-sonnet-5"]["output_tokens"], 20)
            self.assertEqual(by_model["claude-sonnet-5"]["abnormal_exit_rate"], 0.0)
            self.assertIn("unknown", by_model)
            self.assertEqual(by_model["unknown"]["abnormal_exit_rate"], 1.0)
            self.assertIn("w1", by_agent)
            # agent-2 has no transcript_path at all -> not a resolvable fallback (nothing to fall back to).
            self.assertEqual(fallback_count, 0)

    def test_falls_back_and_counts_when_subagent_file_absent(self):
        with _TempDir() as root:
            session_id = "sess-2"
            parent = root / f"{session_id}.jsonl"
            _write_transcript(parent, [_assistant_record("m1", "claude-opus-5", "2026-09-14T18:00:00Z", 1, 1, 1, 1)])
            # No subagents/ directory at all for this agent.
            events = [_dispatch_exit("w-missing", "agentops", "completed", parent, "2026-09-14T18:00:01Z")]
            rows, _cache, by_agent, fallback_count = mlr.summarize_worker_usage(events)
            self.assertEqual(fallback_count, 1)
            self.assertIn("w-missing", by_agent)

    def test_two_exits_for_one_resumed_agent_are_one_session_not_two(self):
        # Real shape: item 2374's agent ae70fc0a294de1cb0 exits once per rework cycle,
        # but it is one worker -- 'sessions' must count it once, and tokens must not
        # be double-counted across the two exit records.
        with _TempDir() as root:
            session_id = "sess-3"
            parent = root / f"{session_id}.jsonl"
            parent.write_text("")
            subagent_path = root / session_id / "subagents" / "agent-ae70fc0a294de1cb0.jsonl"
            _write_transcript(
                subagent_path,
                [_assistant_record("m1", "claude-haiku-4-5", "2026-09-14T19:00:00Z", 100, 0, 0, 50)],
            )
            events = [
                _dispatch_exit("ae70fc0a294de1cb0", "agentops", "completed", parent, "2026-09-14T19:01:00Z"),
                _dispatch_exit("ae70fc0a294de1cb0", "agentops", "completed", parent, "2026-09-14T19:03:00Z"),
            ]
            rows, _cache, by_agent, fallback_count = mlr.summarize_worker_usage(events)
            by_model = {row["model"]: row for row in rows}
            self.assertEqual(by_model["claude-haiku-4-5"]["sessions"], 1)
            self.assertEqual(by_model["claude-haiku-4-5"]["input_tokens"], 100)
            self.assertEqual(by_model["claude-haiku-4-5"]["output_tokens"], 50)
            self.assertEqual(fallback_count, 0)

    def test_abnormal_rate_uses_last_exit_for_grouped_agent(self):
        with _TempDir() as root:
            session_id = "sess-4"
            parent = root / f"{session_id}.jsonl"
            parent.write_text("")
            subagent_path = root / session_id / "subagents" / "agent-flaky.jsonl"
            _write_transcript(subagent_path, [_assistant_record("m1", "claude-sonnet-5", "2026-09-14T19:00:00Z", 1, 0, 0, 1)])
            events = [
                _dispatch_exit("flaky", "agentops", "error", parent, "2026-09-14T19:00:00Z"),
                _dispatch_exit("flaky", "agentops", "completed", parent, "2026-09-14T19:05:00Z"),
            ]
            rows, _cache, _by_agent, _fb = mlr.summarize_worker_usage(events)
            row = next(r for r in rows if r["model"] == "claude-sonnet-5")
            self.assertEqual(row["abnormal_exit_rate"], 0.0)

    def test_no_events_yields_no_rows(self):
        rows, _cache, by_agent, fallback_count = mlr.summarize_worker_usage([])
        self.assertEqual(rows, [])
        self.assertEqual(by_agent, {})
        self.assertEqual(fallback_count, 0)

    def test_tokens_per_accepted_item_join_via_review_agent_tag(self):
        with _TempDir() as root:
            session_id = "sess-5"
            parent = root / f"{session_id}.jsonl"
            parent.write_text("")
            subagent_path = root / session_id / "subagents" / "agent-xyz.jsonl"
            _write_transcript(subagent_path, [_assistant_record("m1", "claude-sonnet-5", "2026-09-14T18:00:00Z", 100, 0, 0, 50)])
            dispatch_events = [_dispatch_exit("xyz", "agentops", "completed", parent, "2026-09-14T18:00:01Z")]
            _rows, _cache, by_agent, _fb = mlr.summarize_worker_usage(dispatch_events)

            item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
            events = [
                _event("lane.dispatch", "coordinator", {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"}, "2026-09-14T18:53:49Z", 1),
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-sonnet-5", "agent:xyz"], "summary": "Accepted"}, "2026-09-14T18:58:24Z", 2),
            ]
            records = mlr.build_item_records([item], {2377: events})
            joined = mlr.join_tokens_per_accepted_item(records, by_agent)
            self.assertEqual(len(joined), 1)
            self.assertEqual(joined[0]["model"], "claude-sonnet-5")
            self.assertEqual(joined[0]["accepted_items_joined"], 1)
            self.assertEqual(joined[0]["input_tokens_per_accepted_item"], 100)
            self.assertEqual(joined[0]["output_tokens_per_accepted_item"], 50)

    def test_unjoinable_attempt_is_skipped_not_crashed(self):
        item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
        events = [
            _event("lane.dispatch", "coordinator", {"tags": ["lane", "model:claude-sonnet-5"], "summary": "Dispatched"}, "2026-09-14T18:53:49Z", 1),
            _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "first-pass", "model:claude-sonnet-5"], "summary": "Accepted"}, "2026-09-14T18:58:24Z", 2),
        ]
        records = mlr.build_item_records([item], {2377: events})
        joined = mlr.join_tokens_per_accepted_item(records, {})
        self.assertEqual(joined, [])


# --------------------------------------------------------------------------
# Local scorecard (section d)
# --------------------------------------------------------------------------

SCORECARD_HEADER = [
    "experiment_id", "date", "profile", "engine_revision", "model", "artifact_sha256",
    "harness", "task_family", "task_id", "prompt_tokens", "output_tokens", "ttft_ms",
    "prefill_tps", "decode_tps", "wall_ms", "tool_calls", "retries", "tests_passed",
    "human_score", "accepted", "notes",
]


def _scorecard_row(**overrides):
    row = {k: "" for k in SCORECARD_HEADER}
    row.update(
        {
            "experiment_id": "exp-1",
            "date": "2026-09-10",
            "model": "worker-fast",
            "task_family": "tier-corpus",
            "task_id": "task-01",
            "wall_ms": "1200",
            "tests_passed": "true",
            "accepted": "true",
        }
    )
    row.update(overrides)
    return row


class ScorecardTests(unittest.TestCase):
    def test_attempts_pass_and_accept_rates_per_model(self):
        with _TempDir() as tmp:
            path = tmp / "scorecard.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=SCORECARD_HEADER)
                writer.writeheader()
                writer.writerow(_scorecard_row(tests_passed="true", accepted="true", wall_ms="1000"))
                writer.writerow(_scorecard_row(tests_passed="false", accepted="false", wall_ms="3000"))
            rows = mlr.load_scorecard(path)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["model"], "worker-fast")
            self.assertEqual(row["attempts"], 2)
            self.assertAlmostEqual(row["tests_passed_rate"], 0.5)
            self.assertAlmostEqual(row["accepted_rate"], 0.5)
            self.assertEqual(row["median_wall_ms"], 2000)

    def test_header_only_csv_yields_no_rows(self):
        with _TempDir() as tmp:
            path = tmp / "scorecard.csv"
            with path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=SCORECARD_HEADER)
                writer.writeheader()
            self.assertEqual(mlr.load_scorecard(path), [])

    def test_missing_scorecard_yields_no_rows(self):
        self.assertEqual(mlr.load_scorecard(Path("/no/such/scorecard.csv")), [])


# --------------------------------------------------------------------------
# Zero-denominator rates
# --------------------------------------------------------------------------

class RateTests(unittest.TestCase):
    def test_rate_is_none_not_zero_division(self):
        self.assertIsNone(mlr._rate(0, 0))
        self.assertEqual(mlr._rate(0, 5), 0.0)
        self.assertEqual(mlr._rate(5, 5), 1.0)


# --------------------------------------------------------------------------
# Full report assembly: missing inputs, both output formats
# --------------------------------------------------------------------------

class BuildReportTests(unittest.TestCase):
    def test_all_inputs_missing_marks_every_section_unavailable_and_does_not_crash(self):
        with _TempDir() as tmp:
            args = _Args(
                sprint_id=None,
                items_json=None,
                notes_json=None,
                artifacts_root=tmp / "no-artifacts-here",
                since=None,
                scorecard=tmp / "no-scorecard.csv",
                stale_hours=24.0,
            )
            report = mlr.build_report(args)
            self.assertFalse(report["tier_model"]["available"])
            self.assertFalse(report["stale_items"]["available"])
            self.assertFalse(report["worker_usage"]["available"])
            self.assertFalse(report["scorecard"]["available"])
            self.assertEqual(report["tier_model"]["rows"], [])
            self.assertEqual(report["worker_usage"]["rows"], [])
            self.assertEqual(report["worker_usage"]["resolution_fallbacks"], 0)

    def test_offline_items_and_notes_json_round_trip(self):
        with _TempDir() as tmp:
            item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
            items_json = tmp / "items.json"
            _write_json(items_json, [item])
            events = [
                _event("lane.dispatch", "coordinator", {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"}, "2026-09-14T18:53:49Z", 1),
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Accepted"}, "2026-09-14T18:58:24Z", 2),
            ]
            notes_dir = _write_notes_dir(tmp, {2377: events})
            args = _Args(items_json=items_json, notes_json=notes_dir, artifacts_root=tmp / "no-artifacts", scorecard=tmp / "no-scorecard.csv", stale_hours=24.0)
            report = mlr.build_report(args)
            self.assertTrue(report["tier_model"]["available"])
            self.assertEqual(len(report["tier_model"]["rows"]), 1)
            self.assertEqual(report["tier_model"]["rows"][0]["accepted_items"], [2377])

    def test_markdown_and_json_both_render_without_error(self):
        with _TempDir() as tmp:
            item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
            items_json = tmp / "items.json"
            _write_json(items_json, [item])
            events = [
                _event("lane.dispatch", "coordinator", {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"}, "2026-09-14T18:53:49Z", 1),
                _event("lane.review", "coordinator", {"tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Accepted"}, "2026-09-14T18:58:24Z", 2),
            ]
            notes_dir = _write_notes_dir(tmp, {2377: events})
            args = _Args(items_json=items_json, notes_json=notes_dir, artifacts_root=tmp / "no-artifacts", scorecard=tmp / "no-scorecard.csv", stale_hours=24.0)
            report = mlr.build_report(args)
            markdown = mlr.render_markdown(report)
            self.assertIn("# Maintenance-lane report", markdown)
            self.assertIn("claude-sonnet-5", markdown)
            self.assertIn("blocked", markdown)
            rendered_json = mlr.render_json(report)
            parsed = json.loads(rendered_json)
            self.assertEqual(parsed["tier_model"]["rows"][0]["model"], "claude-sonnet-5")

    def test_main_cli_smoke_markdown(self):
        with _TempDir() as tmp:
            items_json = tmp / "items.json"
            _write_json(items_json, [])
            notes_dir = tmp / "notes"
            notes_dir.mkdir()
            argv = [
                "--items-json", str(items_json),
                "--notes-json", str(notes_dir),
                "--artifacts-root", str(tmp / "no-artifacts"),
                "--scorecard", str(tmp / "no-scorecard.csv"),
                "--format", "markdown",
            ]
            import contextlib
            import io

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mlr.main(argv)
            self.assertEqual(rc, 0)
            self.assertIn("Maintenance-lane report", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
