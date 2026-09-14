"""Tests for headroom_writer.py -- the out-of-pod writer for the two files the
agent-cockpit web app reads (`.codex-headroom.json`, `.claude-headroom.json`).

Coverage:
  * a fixture Codex rollout file round-trips into the field names
    `apps/web/lib/cockpit/headroom.js`'s `normalizeCodexHeadroom` reads;
  * a fixture Claude statusline tee file round-trips into the field names
    `normalizeClaudeHeadroom` reads;
  * a missing/unparseable source produces `{"available": false, "reason": ...}`
    plus timestamps, never a crash or a partial file;
  * a source older than `--max-age-minutes` is marked `stale: true`;
  * the atomic-write path leaves no temp files behind;
  * the tee script passes stdin through unchanged and writes the state file,
    and still passes stdin through when the state dir is unwritable.
"""
from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "headroom_writer.py"
TEE_SCRIPT = HERE.parent / "hooks" / "statusline-headroom-tee.sh"

_spec = importlib.util.spec_from_file_location("headroom_writer", SCRIPT)
hw = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(hw)


def _rollout_event(
    *,
    timestamp="2026-09-14T18:26:27.323Z",
    primary_used=0.0,
    secondary_used=57.0,
    resets_primary=1789428383,
    resets_secondary=1789818807,
    plan_type="plus",
):
    return {
        "timestamp": timestamp,
        "ordinal": 13,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": 16732,
                    "cached_input_tokens": 12160,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 0,
                    "total_tokens": 16737,
                },
                "model_context_window": 258400,
            },
            "rate_limits": {
                "limit_id": "codex",
                "limit_name": None,
                "primary": {
                    "used_percent": primary_used,
                    "window_minutes": 300,
                    "resets_at": resets_primary,
                },
                "secondary": {
                    "used_percent": secondary_used,
                    "window_minutes": 10080,
                    "resets_at": resets_secondary,
                },
                "credits": {"has_credits": False, "unlimited": False, "balance": "0"},
                "individual_limit": None,
                "spend_control_reached": None,
                "plan_type": plan_type,
                "rate_limit_reached_type": None,
            },
        },
    }


def _write_rollout(sessions_root: Path, day="14", lines=None, mtime=None):
    day_dir = sessions_root / "2026" / "09" / day
    day_dir.mkdir(parents=True, exist_ok=True)
    rollout = day_dir / f"rollout-2026-09-{day}T21-26-20-01a0a12b.jsonl"
    if lines is None:
        lines = [
            json.dumps({"type": "event_msg", "payload": {"type": "other"}}),
            json.dumps(_rollout_event()),
        ]
    rollout.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if mtime is not None:
        os.utime(rollout, (mtime, mtime))
    return rollout


def _statusline_payload(
    *,
    five_hour_pct=42.0,
    seven_day_pct=13.5,
    captured_at="2026-09-14T18:20:00+00:00",
):
    return {
        "workspace": {"current_dir": "/projects/dev/agentops"},
        "model": {"display_name": "Claude Sonnet 5"},
        "cost": {"total_cost_usd": 1.23},
        "rate_limits": {
            "five_hour": {"used_percentage": five_hour_pct},
            "seven_day": {"used_percentage": seven_day_pct},
        },
        "captured_at": captured_at,
    }


class CodexPayloadTests(unittest.TestCase):
    def test_fixture_rollout_maps_to_headroom_js_field_names(self):
        with _tmp_home() as home:
            codex_home = home / ".codex"
            _write_rollout(codex_home / "sessions")
            now = datetime(2026, 9, 14, 18, 30, tzinfo=timezone.utc)

            payload = hw.build_codex_payload(codex_home, 30.0, now)

            self.assertTrue(payload["available"])
            self.assertFalse(payload["stale"])
            self.assertEqual(payload["plan_type"], "plus")
            primary = payload["rate_limit"]["primary_window"]
            secondary = payload["rate_limit"]["secondary_window"]
            self.assertEqual(primary["used_percent"], 0.0)
            self.assertEqual(primary["limit_window_seconds"], 300 * 60)
            self.assertEqual(secondary["used_percent"], 57.0)
            self.assertEqual(secondary["limit_window_seconds"], 10080 * 60)
            self.assertTrue(primary["reset_at"].startswith("20"))
            self.assertIsInstance(primary["remaining_seconds"], (int, float))
            self.assertEqual(
                payload["credits"],
                {"has_credits": False, "unlimited": False, "balance": 0.0},
            )

    def test_picks_the_newest_rollout_across_day_dirs(self):
        with _tmp_home() as home:
            codex_home = home / ".codex"
            older = _write_rollout(
                codex_home / "sessions",
                day="12",
                lines=[json.dumps(_rollout_event(secondary_used=10.0))],
                mtime=1_000_000,
            )
            newer = _write_rollout(
                codex_home / "sessions",
                day="14",
                lines=[json.dumps(_rollout_event(secondary_used=57.0))],
                mtime=2_000_000,
            )
            self.assertNotEqual(older, newer)

            found = hw.find_latest_rollout(codex_home)
            self.assertEqual(found, newer)

    def test_missing_codex_home_is_unavailable_not_a_crash(self):
        with _tmp_home() as home:
            payload = hw.build_codex_payload(
                home / "no-such-codex-home", 30.0, datetime.now(timezone.utc)
            )
            self.assertFalse(payload["available"])
            self.assertIn("reason", payload)
            self.assertIsNotNone(payload["refreshed_at"])

    def test_rollout_with_no_rate_limits_event_is_unavailable(self):
        with _tmp_home() as home:
            codex_home = home / ".codex"
            _write_rollout(
                codex_home / "sessions",
                lines=[json.dumps({"type": "event_msg", "payload": {"type": "other"}})],
            )
            payload = hw.build_codex_payload(
                codex_home, 30.0, datetime.now(timezone.utc)
            )
            self.assertFalse(payload["available"])

    def test_unparseable_rollout_lines_are_skipped_not_fatal(self):
        with _tmp_home() as home:
            codex_home = home / ".codex"
            _write_rollout(
                codex_home / "sessions",
                lines=["not json at all", json.dumps(_rollout_event())],
            )
            payload = hw.build_codex_payload(
                codex_home, 30.0, datetime.now(timezone.utc)
            )
            self.assertTrue(payload["available"])

    def test_stale_detection(self):
        with _tmp_home() as home:
            codex_home = home / ".codex"
            old_timestamp = "2026-09-14T00:00:00.000Z"
            _write_rollout(
                codex_home / "sessions",
                lines=[json.dumps(_rollout_event(timestamp=old_timestamp))],
            )
            now = datetime(2026, 9, 14, 5, 0, tzinfo=timezone.utc)  # 5h later
            payload = hw.build_codex_payload(codex_home, 30.0, now)
            self.assertTrue(payload["available"])
            self.assertTrue(payload["stale"])

    def test_fresh_is_not_stale(self):
        with _tmp_home() as home:
            codex_home = home / ".codex"
            _write_rollout(
                codex_home / "sessions",
                lines=[
                    json.dumps(
                        _rollout_event(timestamp="2026-09-14T18:29:00.000Z")
                    )
                ],
            )
            now = datetime(2026, 9, 14, 18, 30, tzinfo=timezone.utc)
            payload = hw.build_codex_payload(codex_home, 30.0, now)
            self.assertFalse(payload["stale"])


class ClaudePayloadTests(unittest.TestCase):
    def test_fixture_statusline_maps_to_headroom_js_field_names(self):
        with _tmp_home() as home:
            statusline = home / "state" / "claude-statusline.json"
            statusline.parent.mkdir(parents=True, exist_ok=True)
            statusline.write_text(
                json.dumps(_statusline_payload()), encoding="utf-8"
            )
            now = datetime(2026, 9, 14, 18, 25, tzinfo=timezone.utc)

            payload = hw.build_claude_payload(statusline, 30.0, now)

            self.assertTrue(payload["available"])
            self.assertFalse(payload["stale"])
            self.assertEqual(payload["current_window"]["used_percent"], 42.0)
            self.assertEqual(payload["weekly_limit"]["other"]["used_percent"], 13.5)
            self.assertIsNone(payload["weekly_limit"]["opus"])

    def test_missing_statusline_file_is_unavailable(self):
        with _tmp_home() as home:
            payload = hw.build_claude_payload(
                home / "state" / "nope.json", 30.0, datetime.now(timezone.utc)
            )
            self.assertFalse(payload["available"])
            self.assertIn("reason", payload)

    def test_unparseable_statusline_file_is_unavailable_not_a_crash(self):
        with _tmp_home() as home:
            statusline = home / "state" / "claude-statusline.json"
            statusline.parent.mkdir(parents=True, exist_ok=True)
            statusline.write_text("{not valid json", encoding="utf-8")
            payload = hw.build_claude_payload(
                statusline, 30.0, datetime.now(timezone.utc)
            )
            self.assertFalse(payload["available"])

    def test_stale_detection(self):
        with _tmp_home() as home:
            statusline = home / "state" / "claude-statusline.json"
            statusline.parent.mkdir(parents=True, exist_ok=True)
            statusline.write_text(
                json.dumps(
                    _statusline_payload(captured_at="2026-09-14T10:00:00+00:00")
                ),
                encoding="utf-8",
            )
            now = datetime(2026, 9, 14, 18, 0, tzinfo=timezone.utc)
            payload = hw.build_claude_payload(statusline, 30.0, now)
            self.assertTrue(payload["available"])
            self.assertTrue(payload["stale"])


class AtomicWriteTests(unittest.TestCase):
    def test_atomic_write_leaves_no_temp_files(self):
        with _tmp_home() as home:
            out_dir = home / "out"
            hw.atomic_write_json(out_dir / ".codex-headroom.json", {"a": 1})
            entries = list(out_dir.iterdir())
            self.assertEqual([p.name for p in entries], [".codex-headroom.json"])
            data = json.loads((out_dir / ".codex-headroom.json").read_text())
            self.assertEqual(data, {"a": 1})

    def test_main_writes_both_files_end_to_end(self):
        with _tmp_home() as home:
            codex_home = home / ".codex"
            _write_rollout(codex_home / "sessions")
            statusline = home / "state" / "claude-statusline.json"
            statusline.parent.mkdir(parents=True, exist_ok=True)
            statusline.write_text(
                json.dumps(_statusline_payload()), encoding="utf-8"
            )
            out_dir = home / "out"

            rc = hw.main(
                [
                    "--out-dir",
                    str(out_dir),
                    "--codex-home",
                    str(codex_home),
                    "--claude-statusline",
                    str(statusline),
                ]
            )
            self.assertEqual(rc, 0)

            names = sorted(p.name for p in out_dir.iterdir())
            self.assertEqual(names, [".claude-headroom.json", ".codex-headroom.json"])

            codex_data = json.loads((out_dir / ".codex-headroom.json").read_text())
            claude_data = json.loads((out_dir / ".claude-headroom.json").read_text())
            self.assertTrue(codex_data["available"])
            self.assertTrue(claude_data["available"])


class TeeScriptTests(unittest.TestCase):
    def test_passes_stdin_through_and_writes_state_file(self):
        with _tmp_home() as home:
            state_dir = home / "headroom-state"
            payload = json.dumps({"hello": "world"})
            env = dict(os.environ)
            env["HEADROOM_STATE_DIR"] = str(state_dir)

            result = subprocess.run(
                ["bash", str(TEE_SCRIPT)],
                input=payload,
                capture_output=True,
                text=True,
                env=env,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, payload)

            written = state_dir / "claude-statusline.json"
            self.assertTrue(written.is_file())
            self.assertEqual(written.read_text(), payload)

    def test_still_passes_through_when_state_dir_unwritable(self):
        with _tmp_home() as home:
            unwritable_parent = home / "locked"
            unwritable_parent.mkdir()
            state_dir = unwritable_parent / "headroom-state"
            os.chmod(unwritable_parent, stat.S_IRUSR | stat.S_IXUSR)  # read+exec, no write
            payload = json.dumps({"hello": "again"})
            env = dict(os.environ)
            env["HEADROOM_STATE_DIR"] = str(state_dir)

            try:
                result = subprocess.run(
                    ["bash", str(TEE_SCRIPT)],
                    input=payload,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, payload)
            finally:
                os.chmod(unwritable_parent, stat.S_IRWXU)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

import contextlib
import tempfile


@contextlib.contextmanager
def _tmp_home():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


if __name__ == "__main__":
    unittest.main()
