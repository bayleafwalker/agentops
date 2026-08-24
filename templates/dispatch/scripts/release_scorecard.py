"""Reduce Claude Code Stop-hook sink rows to per-session survivors and totals.

The Stop hook appends one cumulative snapshot per assistant turn, so rows for a
session supersede each other. ``reduce_sessions`` keeps the newest snapshot per
session and ``frontier_totals`` sums over those survivors only.
"""


def reduce_sessions(rows):
    """Return {session id: that session's single surviving row}."""
    survivors = {}
    for row in rows:
        session = row.get("session")
        if not session:
            continue
        key = (row.get("ts", ""), row.get("cost_usd", 0), row.get("out", 0))
        if session not in survivors or key > survivors[session][0]:
            survivors[session] = (key, row)
    return {session: row for session, (_, row) in survivors.items()}


def frontier_totals(rows):
    """Return the seven aggregate fields over the reduced survivors only."""
    survivors = reduce_sessions(rows)
    totals = {
        "sessions": len(survivors),
        "turns": 0,
        "assistant_msgs": 0,
        "tool_calls": 0,
        "duration_s": 0,
        "cost_usd": 0.0,
        "rework_rounds": 0,
    }
    for row in survivors.values():
        for field in ("turns", "assistant_msgs", "tool_calls", "duration_s",
                      "rework_rounds"):
            totals[field] += row.get(field, 0)
        totals["cost_usd"] += row.get("cost_usd", 0)
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    return totals