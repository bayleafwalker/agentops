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
Item 2377 in that sprint carries exactly the accepted/first-pass ``lane.dispatch`` +
``lane.review`` pair used as the "known good" shape here; item 2372 carries a
``lane.dispatch`` with no matching review, which is the real shape of a stale item.

The transcript dedup fixture mirrors a real streamed assistant message (three JSONL
records, same ``message.id``, growing ``output_tokens`` across records) pulled from a
live subagent transcript -- the point being that summing all three records would
triple-count tokens; the report must keep only the final one per id.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


mlr = _load_module("maintenance_lane_report_subject", SCRIPTS / "maintenance_lane_report.py")


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

    def test_payload_string_is_parsed(self):
        event = {"payload": json.dumps({"tags": ["lane"], "summary": "x"})}
        self.assertEqual(mlr._payload(event), {"tags": ["lane"], "summary": "x"})

    def test_payload_malformed_json_yields_empty_dict(self):
        event = {"payload": "{not json"}
        self.assertEqual(mlr._payload(event), {})


# --------------------------------------------------------------------------
# Per tier / model aggregation (section a)
# --------------------------------------------------------------------------

class TierModelAggregationTests(unittest.TestCase):
    def test_accepted_first_pass_and_rework_rates(self):
        # Item A: dispatched fast-build/sonnet, accepted first-pass.
        item_a = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
        events_a = [
            _event(
                "lane.dispatch",
                "coordinator",
                {
                    "tags": ["lane", "tier:fast-build", "model:claude-sonnet-5", "harness:claude-subagent"],
                    "summary": "Dispatched to worker",
                },
                "2026-09-14T18:53:49Z",
                1,
            ),
            _event(
                "lane.review",
                "coordinator",
                {
                    "tags": ["lane", "verdict:accepted", "first-pass", "tier:fast-build", "model:claude-sonnet-5"],
                    "summary": "Accepted: meets acceptance criteria",
                },
                "2026-09-14T18:58:24Z",
                2,
            ),
        ]
        # Item B: dispatched fast-build/sonnet, reworked (not first-pass).
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
        items = [item_a, item_b]
        notes = {2377: events_a, 2378: events_b}
        records = mlr.build_item_records(items, notes)
        rows = mlr.aggregate_tier_model(records)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row["tier"], row["model"]), ("fast-build", "claude-sonnet-5"))
        self.assertEqual(row["attempts"], 2)
        self.assertAlmostEqual(row["first_pass_acceptance_rate"], 0.5)
        self.assertAlmostEqual(row["rework_rate"], 0.5)
        self.assertEqual(row["rejected_rate"], 0.0)
        self.assertEqual(row["accepted_items"], [2377])

    def test_dispatch_without_review_counts_as_attempt_with_no_verdict(self):
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
        rows = mlr.aggregate_tier_model(records)
        self.assertEqual(rows[0]["attempts"], 1)
        self.assertEqual(rows[0]["first_pass_acceptance_rate"], 0.0)
        self.assertEqual(rows[0]["accepted_items"], [])

    def test_empty_items_yields_no_rows(self):
        self.assertEqual(mlr.aggregate_tier_model([]), [])


# --------------------------------------------------------------------------
# Stale items (section b)
# --------------------------------------------------------------------------

class StaleItemsTests(unittest.TestCase):
    def test_active_item_without_review_older_than_threshold_is_stale(self):
        now = mlr._parse_ts("2026-09-15T20:00:00Z")
        item = _item(2372, "C", "active", "2026-09-14T18:53:46Z", "2026-09-14T18:55:44Z")
        events = [
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"},
                "2026-09-14T18:58:23Z",
                1,
            )
        ]
        records = mlr.build_item_records([item], {2372: events})
        stale = mlr.find_stale_items(records, stale_hours=24.0, now=now)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["id"], 2372)

    def test_recent_item_without_review_is_not_stale(self):
        now = mlr._parse_ts("2026-09-14T20:00:00Z")
        item = _item(2372, "C", "active", "2026-09-14T18:53:46Z", "2026-09-14T18:55:44Z")
        events = [
            _event(
                "lane.dispatch",
                "coordinator",
                {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"},
                "2026-09-14T18:58:23Z",
                1,
            )
        ]
        records = mlr.build_item_records([item], {2372: events})
        stale = mlr.find_stale_items(records, stale_hours=24.0, now=now)
        self.assertEqual(stale, [])

    def test_reviewed_item_is_never_stale(self):
        now = mlr._parse_ts("2026-09-20T20:00:00Z")
        item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
        events = [
            _event("lane.dispatch", "coordinator", {"tags": ["lane"], "summary": "Dispatched"}, "2026-09-14T18:53:49Z", 1),
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:accepted", "first-pass"], "summary": "Accepted"},
                "2026-09-14T18:58:24Z",
                2,
            ),
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
        with _TempDir() as tmp:
            root = Path(tmp)
            _audit_shard(
                root,
                "agentops",
                "2026-09-01",
                [_dispatch_exit("a1", "agentops", "completed", None, "2026-09-01T00:00:00Z")],
            )
            _audit_shard(
                root,
                "agentops",
                "2026-09-10",
                [_dispatch_exit("a2", "agentops", "completed", None, "2026-09-10T00:00:00Z")],
            )
            events = mlr.load_dispatch_exit_events(root, since=mlr._parse_ts("2026-09-05T00:00:00Z"))
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["metadata"]["agent_id"], "a2")

    def test_skips_wt_and_projects_directories(self):
        with _TempDir() as tmp:
            root = Path(tmp)
            _audit_shard(
                root / "_wt" / "some-worktree",
                "agentops",
                "2026-09-10",
                [_dispatch_exit("skip-me", "agentops", "completed", None, "2026-09-10T00:00:00Z")],
            )
            _audit_shard(
                root,
                "agentops",
                "2026-09-10",
                [_dispatch_exit("keep-me", "agentops", "completed", None, "2026-09-10T00:00:00Z")],
            )
            events = mlr.load_dispatch_exit_events(root, since=None)
            agent_ids = {e["metadata"]["agent_id"] for e in events}
            self.assertEqual(agent_ids, {"keep-me"})

    def test_missing_artifacts_root_yields_no_events(self):
        events = mlr.load_dispatch_exit_events(Path("/nonexistent/root/for/test"), since=None)
        self.assertEqual(events, [])

    def test_ignores_non_ndjson_and_malformed_lines(self):
        with _TempDir() as tmp:
            root = Path(tmp)
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
# Transcript summarization: de-duplication by message.id
# --------------------------------------------------------------------------

class TranscriptDedupTests(unittest.TestCase):
    def test_multi_record_message_is_deduplicated_not_summed(self):
        with _TempDir() as tmp:
            path = Path(tmp) / "transcript.jsonl"
            # Mirrors a real streamed message: three records share message.id, usage
            # grows monotonically (the API streams partial usage, then final usage).
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
            # Only the final record per message id should contribute output tokens.
            self.assertEqual(summary["output_tokens"], 340 + 333)
            # Input total = sum over messages of (input + cache_read + cache_creation)
            # using each message's own final record.
            expected_input = (2 + 24750 + 9884) + (2 + 34634 + 1960)
            self.assertEqual(summary["input_tokens"], expected_input)
            self.assertEqual(summary["peak_context"], max(2 + 24750 + 9884, 2 + 34634 + 1960))
            self.assertEqual(summary["model"], "claude-opus-5")
            self.assertAlmostEqual(summary["wall_seconds"], 10.0)

    def test_missing_transcript_returns_none(self):
        self.assertIsNone(mlr.summarize_transcript(Path("/no/such/transcript.jsonl")))

    def test_empty_transcript_returns_zeroed_summary(self):
        with _TempDir() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("")
            summary = mlr.summarize_transcript(path)
            self.assertEqual(summary["messages"], 0)
            self.assertIsNone(summary["wall_seconds"])

    def test_synthetic_model_excluded_from_model_vote(self):
        with _TempDir() as tmp:
            path = Path(tmp) / "t.jsonl"
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
    def test_sessions_tokens_and_abnormal_rate_per_model(self):
        with _TempDir() as tmp:
            tpath = Path(tmp) / "t1.jsonl"
            _write_transcript(
                tpath,
                [_assistant_record("m1", "claude-sonnet-5", "2026-09-14T18:00:00Z", 10, 0, 0, 20)],
            )
            events = [
                _dispatch_exit("agent-1", "agentops", "completed", tpath, "2026-09-14T18:00:01Z"),
                _dispatch_exit("agent-2", "agentops", "error", None, "2026-09-14T18:05:00Z"),
            ]
            rows, _cache, by_agent = mlr.summarize_worker_usage(events)
            by_model = {row["model"]: row for row in rows}
            self.assertIn("claude-sonnet-5", by_model)
            self.assertEqual(by_model["claude-sonnet-5"]["sessions"], 1)
            self.assertEqual(by_model["claude-sonnet-5"]["input_tokens"], 10)
            self.assertEqual(by_model["claude-sonnet-5"]["output_tokens"], 20)
            self.assertEqual(by_model["claude-sonnet-5"]["abnormal_exit_rate"], 0.0)
            self.assertIn("unknown", by_model)
            self.assertEqual(by_model["unknown"]["abnormal_exit_rate"], 1.0)
            self.assertIn("agent-1", by_agent)

    def test_no_events_yields_no_rows(self):
        rows, _cache, by_agent = mlr.summarize_worker_usage([])
        self.assertEqual(rows, [])
        self.assertEqual(by_agent, {})

    def test_tokens_per_accepted_item_join_via_agent_tag(self):
        with _TempDir() as tmp:
            tpath = Path(tmp) / "t.jsonl"
            _write_transcript(
                tpath,
                [_assistant_record("m1", "claude-sonnet-5", "2026-09-14T18:00:00Z", 100, 0, 0, 50)],
            )
            dispatch_events = [_dispatch_exit("agent-xyz", "agentops", "completed", tpath, "2026-09-14T18:00:01Z")]
            _rows, _cache, by_agent = mlr.summarize_worker_usage(dispatch_events)

            item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
            events = [
                _event(
                    "lane.dispatch",
                    "coordinator",
                    {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5", "agent:agent-xyz"], "summary": "Dispatched"},
                    "2026-09-14T18:53:49Z",
                    1,
                ),
                _event(
                    "lane.review",
                    "coordinator",
                    {"tags": ["lane", "verdict:accepted", "first-pass"], "summary": "Accepted"},
                    "2026-09-14T18:58:24Z",
                    2,
                ),
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
            _event(
                "lane.review",
                "coordinator",
                {"tags": ["lane", "verdict:accepted", "first-pass"], "summary": "Accepted"},
                "2026-09-14T18:58:24Z",
                2,
            ),
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
            path = Path(tmp) / "scorecard.csv"
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
            path = Path(tmp) / "scorecard.csv"
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
                artifacts_root=Path(tmp) / "no-artifacts-here",
                since=None,
                scorecard=Path(tmp) / "no-scorecard.csv",
                stale_hours=24.0,
            )
            report = mlr.build_report(args)
            self.assertFalse(report["tier_model"]["available"])
            self.assertFalse(report["stale_items"]["available"])
            self.assertFalse(report["worker_usage"]["available"])
            self.assertFalse(report["scorecard"]["available"])
            self.assertEqual(report["tier_model"]["rows"], [])
            self.assertEqual(report["worker_usage"]["rows"], [])

    def test_offline_items_and_notes_json_round_trip(self):
        with _TempDir() as tmp:
            tmp_path = Path(tmp)
            item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
            items_json = tmp_path / "items.json"
            _write_json(items_json, [item])
            events = [
                _event(
                    "lane.dispatch",
                    "coordinator",
                    {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"},
                    "2026-09-14T18:53:49Z",
                    1,
                ),
                _event(
                    "lane.review",
                    "coordinator",
                    {"tags": ["lane", "verdict:accepted", "first-pass"], "summary": "Accepted"},
                    "2026-09-14T18:58:24Z",
                    2,
                ),
            ]
            notes_dir = _write_notes_dir(tmp_path, {2377: events})
            args = _Args(
                items_json=items_json,
                notes_json=notes_dir,
                artifacts_root=tmp_path / "no-artifacts",
                scorecard=tmp_path / "no-scorecard.csv",
                stale_hours=24.0,
            )
            report = mlr.build_report(args)
            self.assertTrue(report["tier_model"]["available"])
            self.assertEqual(len(report["tier_model"]["rows"]), 1)
            self.assertEqual(report["tier_model"]["rows"][0]["accepted_items"], [2377])

    def test_markdown_and_json_both_render_without_error(self):
        with _TempDir() as tmp:
            tmp_path = Path(tmp)
            item = _item(2377, "A", "done", "2026-09-14T18:53:48Z", "2026-09-14T18:58:25Z")
            items_json = tmp_path / "items.json"
            _write_json(items_json, [item])
            events = [
                _event(
                    "lane.dispatch",
                    "coordinator",
                    {"tags": ["lane", "tier:fast-build", "model:claude-sonnet-5"], "summary": "Dispatched"},
                    "2026-09-14T18:53:49Z",
                    1,
                ),
                _event(
                    "lane.review",
                    "coordinator",
                    {"tags": ["lane", "verdict:accepted", "first-pass"], "summary": "Accepted"},
                    "2026-09-14T18:58:24Z",
                    2,
                ),
            ]
            notes_dir = _write_notes_dir(tmp_path, {2377: events})
            args = _Args(
                items_json=items_json,
                notes_json=notes_dir,
                artifacts_root=tmp_path / "no-artifacts",
                scorecard=tmp_path / "no-scorecard.csv",
                stale_hours=24.0,
            )
            report = mlr.build_report(args)
            markdown = mlr.render_markdown(report)
            self.assertIn("# Maintenance-lane report", markdown)
            self.assertIn("claude-sonnet-5", markdown)
            rendered_json = mlr.render_json(report)
            parsed = json.loads(rendered_json)
            self.assertEqual(parsed["tier_model"]["rows"][0]["model"], "claude-sonnet-5")

    def test_main_cli_smoke_markdown(self):
        with _TempDir() as tmp:
            tmp_path = Path(tmp)
            items_json = tmp_path / "items.json"
            _write_json(items_json, [])
            notes_dir = tmp_path / "notes"
            notes_dir.mkdir()
            argv = [
                "--items-json", str(items_json),
                "--notes-json", str(notes_dir),
                "--artifacts-root", str(tmp_path / "no-artifacts"),
                "--scorecard", str(tmp_path / "no-scorecard.csv"),
                "--format", "markdown",
            ]
            import io
            import contextlib

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mlr.main(argv)
            self.assertEqual(rc, 0)
            self.assertIn("Maintenance-lane report", buf.getvalue())


# --------------------------------------------------------------------------
# tempfile helper (avoids importing tempfile at module scope purely for typing clarity)
# --------------------------------------------------------------------------

import tempfile


class _TempDir:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        return self._tmp.name

    def __exit__(self, exc_type, exc, tb):
        self._tmp.cleanup()
        return False


if __name__ == "__main__":
    unittest.main()
