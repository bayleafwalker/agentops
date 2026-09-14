#!/usr/bin/env python3
"""Write the provider headroom files the agent-cockpit pod reads.

The cockpit's appservice deployment shells out to ``cat
.claude-headroom.json`` / ``cat .codex-headroom.json`` inside its pod, whose
``/projects/dev`` is a read-only NFS mount. Nothing inside the pod can write
those files, so something outside it -- this script, run on a host that can
write the real ``/projects/dev`` -- has to produce them on a schedule.

This script is read-only towards its two sources (a Codex CLI session
directory and a tee'd Claude Code statusline payload) and only ever writes
inside ``--out-dir``, atomically (temp file + ``os.replace``). A missing or
unparseable source is not an error: it produces
``{"available": false, "reason": ..., ...timestamps}`` and the script exits
0. The field names emitted for an *available* source match exactly what
``apps/web/lib/cockpit/headroom.js`` reads (see ``normalizeCodexHeadroom`` /
``normalizeClaudeHeadroom`` there) because that module ``JSON.parse``s our
file's stdout directly as its "raw" payload.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def utc_now_iso(now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(timezone.utc).isoformat()


def epoch_to_iso(value: Any) -> Optional[str]:
    """Best-effort epoch-seconds -> UTC ISO8601. Returns None if not numeric."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an epoch number or ISO8601 string into an aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Bare numeric string (epoch seconds).
        try:
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        except ValueError:
            pass
        iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(iso_text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        # If os.replace succeeded the temp name no longer exists; this is a
        # no-op then. If we raised before replace, clean up the leftover.
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def unavailable_payload(reason: str, refreshed_at: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "refreshed_at": refreshed_at,
        "source": None,
        "source_observed_at": None,
        "stale": False,
    }


# --- Codex -------------------------------------------------------------


def find_latest_rollout(codex_home: Path, max_day_dirs: int = 5) -> Optional[Path]:
    """Return the most-recently-modified rollout-*.jsonl under codex_home/sessions.

    Scans only the most recent few YYYY/MM/DD directories (by directory mtime,
    then confirmed by file mtime) rather than the whole session tree.
    """
    sessions_root = codex_home / "sessions"
    if not sessions_root.is_dir():
        return None

    day_dirs = []
    try:
        for year_dir in sessions_root.iterdir():
            if not year_dir.is_dir():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                for day_dir in month_dir.iterdir():
                    if not day_dir.is_dir():
                        continue
                    try:
                        mtime = day_dir.stat().st_mtime
                    except OSError:
                        continue
                    day_dirs.append((mtime, day_dir))
    except OSError:
        return None

    if not day_dirs:
        return None

    day_dirs.sort(key=lambda item: item[0], reverse=True)
    candidate_dirs = [d for _, d in day_dirs[:max_day_dirs]]

    newest_path: Optional[Path] = None
    newest_mtime = -1.0
    for day_dir in candidate_dirs:
        try:
            entries = list(day_dir.glob("rollout-*.jsonl"))
        except OSError:
            continue
        for entry in entries:
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            if mtime > newest_mtime:
                newest_mtime = mtime
                newest_path = entry

    return newest_path


def find_latest_rate_limits_event(rollout_path: Path) -> Optional[dict]:
    """Return the last {"type": "event_msg", "payload": {"type": "token_count", ...,
    "rate_limits": {...}}} line in rollout_path, or None.

    Streamed line-by-line (not loaded whole) and prefiltered on the substring
    "rate_limits" before attempting JSON parse, since rollout files can be
    large and most lines do not carry rate limit data.
    """
    latest: Optional[dict] = None
    try:
        with rollout_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "rate_limits" not in line:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("type") != "event_msg":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") != "token_count":
                    continue
                rate_limits = payload.get("rate_limits")
                if not isinstance(rate_limits, dict):
                    continue
                latest = record
    except OSError:
        return None
    return latest


def normalize_codex_window(window: Optional[dict]) -> Optional[dict]:
    if not isinstance(window, dict):
        return None
    window_minutes = window.get("window_minutes")
    try:
        limit_window_seconds = (
            int(window_minutes) * 60 if window_minutes is not None else None
        )
    except (TypeError, ValueError):
        limit_window_seconds = None

    resets_at = window.get("resets_at")
    reset_at_iso = epoch_to_iso(resets_at)

    remaining_seconds = None
    reset_dt = parse_timestamp(resets_at)
    if reset_dt is not None:
        remaining = (reset_dt - datetime.now(timezone.utc)).total_seconds()
        remaining_seconds = remaining if remaining > 0 else 0

    return {
        "used_percent": window.get("used_percent"),
        "limit_window_seconds": limit_window_seconds,
        "reset_at": reset_at_iso,
        "remaining_seconds": remaining_seconds,
    }


def build_codex_payload(
    codex_home: Path, max_age_minutes: float, now: datetime
) -> dict:
    refreshed_at = utc_now_iso(now)
    rollout_path = find_latest_rollout(codex_home)
    if rollout_path is None:
        return unavailable_payload(
            f"no rollout-*.jsonl found under {codex_home / 'sessions'}",
            refreshed_at,
        )

    event = find_latest_rate_limits_event(rollout_path)
    if event is None:
        return unavailable_payload(
            f"no token_count event with rate_limits in {rollout_path}",
            refreshed_at,
        )

    payload = event.get("payload", {})
    rate_limits = payload.get("rate_limits", {})
    event_timestamp = record_observed_at = event.get("timestamp")
    source_observed_dt = parse_timestamp(event_timestamp)
    if source_observed_dt is None:
        # Fall back to the rollout file's own mtime.
        try:
            source_observed_dt = datetime.fromtimestamp(
                rollout_path.stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            source_observed_dt = None

    source_observed_at = (
        source_observed_dt.isoformat() if source_observed_dt is not None else None
    )

    stale = True
    if source_observed_dt is not None:
        age_minutes = (now - source_observed_dt).total_seconds() / 60.0
        stale = age_minutes > max_age_minutes

    credits_raw = rate_limits.get("credits") or {}
    balance_raw = credits_raw.get("balance")
    try:
        balance = float(balance_raw) if balance_raw is not None else None
    except (TypeError, ValueError):
        balance = balance_raw

    return {
        "available": True,
        "reason": None,
        "refreshed_at": refreshed_at,
        "source": str(rollout_path),
        "source_observed_at": source_observed_at,
        "stale": stale,
        "plan_type": rate_limits.get("plan_type"),
        "model": payload.get("model"),
        "reasoning_level": payload.get("reasoning_level") or payload.get("reasoning"),
        "cwd": payload.get("cwd") or payload.get("working_directory"),
        "account_email": payload.get("account_email") or payload.get("email"),
        "rate_limit": {
            "primary_window": normalize_codex_window(rate_limits.get("primary")),
            "secondary_window": normalize_codex_window(rate_limits.get("secondary")),
        },
        "credits": {
            "has_credits": bool(credits_raw.get("has_credits", False)),
            "unlimited": bool(credits_raw.get("unlimited", False)),
            "balance": balance,
        },
    }


# --- Claude --------------------------------------------------------------


def normalize_claude_window(
    used_percentage: Any, resets_value: Any
) -> Optional[dict]:
    if used_percentage is None:
        return None
    reset_at_iso = None
    remaining_seconds = None
    reset_dt = parse_timestamp(resets_value)
    if reset_dt is not None:
        reset_at_iso = reset_dt.isoformat()
        remaining = (reset_dt - datetime.now(timezone.utc)).total_seconds()
        remaining_seconds = remaining if remaining > 0 else 0
    return {
        "used_percent": used_percentage,
        "limit_window_seconds": None,
        "reset_at": reset_at_iso,
        "remaining_seconds": remaining_seconds,
    }


def build_claude_payload(
    statusline_path: Path, max_age_minutes: float, now: datetime
) -> dict:
    refreshed_at = utc_now_iso(now)

    if not statusline_path.is_file():
        return unavailable_payload(
            f"statusline tee file not found: {statusline_path}", refreshed_at
        )

    try:
        raw_text = statusline_path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        return unavailable_payload(
            f"could not parse statusline tee file {statusline_path}: {exc}",
            refreshed_at,
        )

    if not isinstance(raw, dict):
        return unavailable_payload(
            f"statusline tee file {statusline_path} did not contain a JSON object",
            refreshed_at,
        )

    rate_limits = raw.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return unavailable_payload(
            f"statusline tee file {statusline_path} has no rate_limits", refreshed_at
        )

    five_hour = rate_limits.get("five_hour") or {}
    seven_day = rate_limits.get("seven_day") or {}

    captured_at = raw.get("captured_at")
    source_observed_dt = parse_timestamp(captured_at)
    if source_observed_dt is None:
        try:
            source_observed_dt = datetime.fromtimestamp(
                statusline_path.stat().st_mtime, tz=timezone.utc
            )
        except OSError:
            source_observed_dt = None

    source_observed_at = (
        source_observed_dt.isoformat() if source_observed_dt is not None else None
    )

    stale = True
    if source_observed_dt is not None:
        age_minutes = (now - source_observed_dt).total_seconds() / 60.0
        stale = age_minutes > max_age_minutes

    def resets_value(window: dict) -> Any:
        return window.get("resets_at", window.get("reset_at"))

    current_window = normalize_claude_window(
        five_hour.get("used_percentage"), resets_value(five_hour)
    )
    other_window = normalize_claude_window(
        seven_day.get("used_percentage"), resets_value(seven_day)
    )

    return {
        "available": True,
        "reason": None,
        "refreshed_at": refreshed_at,
        "source": str(statusline_path),
        "source_observed_at": source_observed_at,
        "stale": stale,
        "model": raw.get("model", {}).get("display_name")
        if isinstance(raw.get("model"), dict)
        else raw.get("model"),
        "cost_usd": raw.get("cost", {}).get("total_cost_usd")
        if isinstance(raw.get("cost"), dict)
        else raw.get("cost_usd"),
        "projected_cost_usd": raw.get("projected_cost_usd"),
        "current_window": current_window,
        "weekly_limit": {
            "opus": None,
            "other": other_window,
        },
    }


# --- CLI -------------------------------------------------------------


def default_codex_home() -> Path:
    env_value = os.environ.get("CODEX_HOME")
    if env_value:
        return Path(env_value).expanduser()
    return Path.home() / ".codex"


def default_statusline_path() -> Path:
    state_dir = os.environ.get("HEADROOM_STATE_DIR")
    if state_dir:
        base = Path(state_dir).expanduser()
    else:
        base = Path.home() / ".local" / "state" / "headroom"
    return base / "claude-statusline.json"


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write .codex-headroom.json and .claude-headroom.json into "
            "--out-dir for the agent-cockpit web app to read."
        )
    )
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Directory to write .codex-headroom.json and .claude-headroom.json into.",
    )
    parser.add_argument(
        "--codex-home",
        type=Path,
        default=None,
        help="Codex CLI home directory (default: $CODEX_HOME or ~/.codex).",
    )
    parser.add_argument(
        "--claude-statusline",
        type=Path,
        default=None,
        help=(
            "Path to the tee'd Claude Code statusline JSON "
            "(default: ${HEADROOM_STATE_DIR:-~/.local/state/headroom}/claude-statusline.json)."
        ),
    )
    parser.add_argument(
        "--max-age-minutes",
        type=float,
        default=30.0,
        help="Age beyond which a source is considered stale (default: 30).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    args = parse_args(argv)
    now = datetime.now(timezone.utc)

    codex_home = args.codex_home or default_codex_home()
    statusline_path = args.claude_statusline or default_statusline_path()
    out_dir = args.out_dir

    try:
        codex_payload = build_codex_payload(codex_home, args.max_age_minutes, now)
    except Exception as exc:  # noqa: BLE001 - never crash, always produce a file
        codex_payload = unavailable_payload(
            f"unexpected error reading codex source: {exc}", utc_now_iso(now)
        )

    try:
        claude_payload = build_claude_payload(
            statusline_path, args.max_age_minutes, now
        )
    except Exception as exc:  # noqa: BLE001 - never crash, always produce a file
        claude_payload = unavailable_payload(
            f"unexpected error reading claude source: {exc}", utc_now_iso(now)
        )

    atomic_write_json(out_dir / ".codex-headroom.json", codex_payload)
    atomic_write_json(out_dir / ".claude-headroom.json", claude_payload)

    return 0


if __name__ == "__main__":
    sys.exit(main())
