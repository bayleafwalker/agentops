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


def worker_spend_from_receipt(receipt):
    """Return the run step's spend, or the zero result when the chain breaks.

    The worker's own accounting lives under the driver step named ``run``, in
    its nested ``receipt`` -> ``spend``. The last ``run`` step wins when a retry
    re-ran it. Any missing link returns the zero result and never raises.
    """
    zero = {"cost_usd": 0.0, "tokens": 0, "cost_reported": False}
    if not isinstance(receipt, dict):
        return zero
    driver_steps = receipt.get("driver_steps")
    if not isinstance(driver_steps, list):
        return zero
    spend = None
    for entry in driver_steps:
        if not isinstance(entry, dict) or entry.get("step") != "run":
            continue
        nested = entry.get("receipt")
        if not isinstance(nested, dict):
            continue
        candidate = nested.get("spend")
        if isinstance(candidate, dict):
            spend = candidate
    if spend is None:
        return zero
    return {
        "cost_usd": spend.get("cost_usd", 0.0),
        "tokens": spend.get("tokens", 0),
        "cost_reported": bool(spend.get("cost_reported", False)),
    }


def worker_totals(receipts):
    """Return the eight aggregate worker fields over a list of receipts.

    One silent receipt makes the whole cost total unreliable: ``cost_reported``
    is True only when every contributing receipt reported, and the silent
    tasks are named in sorted order. A first pass is an attempt-1 receipt whose
    gate evidence passed.
    """
    tasks = set()
    unreported_tasks = set()
    first_pass_tasks = set()
    total_cost = 0.0
    total_tokens = 0
    for receipt in receipts:
        task_id = receipt.get("task_id")
        if task_id is not None:
            tasks.add(task_id)
        spend = worker_spend_from_receipt(receipt)
        total_cost += spend["cost_usd"]
        total_tokens += spend["tokens"]
        if not spend["cost_reported"] and task_id is not None:
            unreported_tasks.add(task_id)
        if receipt.get("attempt") == 1 and task_id is not None:
            gate = receipt.get("gate")
            if isinstance(gate, dict):
                evidence = gate.get("evidence")
                if isinstance(evidence, dict) and evidence.get("passed") is True:
                    first_pass_tasks.add(task_id)
    task_count = len(tasks)
    first_pass_rate = (
        0.0 if task_count == 0
        else round(len(first_pass_tasks) / task_count, 4)
    )
    return {
        "attempts": len(receipts),
        "tasks": task_count,
        "cost_usd": round(total_cost, 6),
        "tokens": total_tokens,
        "cost_reported": len(unreported_tasks) == 0,
        "cost_unreported_tasks": sorted(unreported_tasks),
        "first_pass_tasks": len(first_pass_tasks),
        "first_pass_rate": first_pass_rate,
    }


def build_scorecard(release, rows, receipts, escalations, recorded_at):
    """Join the two cost halves into the release scorecard.

    ``frontier`` delegates to ``frontier_totals`` over the reduced sink rows
    and ``worker`` delegates to ``worker_totals`` over the packet receipts.
    Neither half substitutes for the other: the hooks never see an OpenCode
    worker, and the receipts know nothing about frontier turns, so both stay
    separately visible. ``cost_usd.total`` is only as trustworthy as its least
    certain half, so ``total_reliable`` is the worker half's ``cost_reported``.
    Escalation task ids and stop conditions come from each record's metadata;
    a record that carried no stop condition is omitted rather than a null.
    """
    frontier = frontier_totals(rows)
    worker = worker_totals(receipts)
    task_ids = set()
    stop_conditions = set()
    for record in escalations:
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            continue
        task_id = metadata.get("task_id")
        if task_id is not None:
            task_ids.add(task_id)
        stop_condition = metadata.get("stop_condition")
        if stop_condition is not None:
            stop_conditions.add(stop_condition)
    return {
        "schema_version": "workflow-scorecard/v1",
        "release": release,
        "recorded_at": recorded_at,
        "frontier": frontier,
        "worker": worker,
        "escalations": {
            "count": len(escalations),
            "tasks": sorted(task_ids),
            "stop_conditions": sorted(stop_conditions),
        },
        "cost_usd": {
            "frontier": frontier["cost_usd"],
            "worker": worker["cost_usd"],
            "total": round(frontier["cost_usd"] + worker["cost_usd"], 6),
            "total_reliable": worker["cost_reported"],
        },
    }


def detect_worse(scorecards):
    """Return whether the release loop is trending worse over the series.

    ``scorecards`` is a list of ``build_scorecard`` outputs in release order,
    oldest first. A signal fires only when it worsened across two consecutive
    transitions, so it takes three scorecards to fire: one bad release is
    noise, two in a row is a trend. Fewer than three scorecards reports
    ``insufficient_series`` rather than a quiet False.
    """
    if len(scorecards) < 3:
        return {"worse": False, "signals": [], "insufficient_series": True}

    def rework_worsened(a, b):
        return b["frontier"]["rework_rounds"] > a["frontier"]["rework_rounds"]

    def escalations_worsened(a, b):
        return b["escalations"]["count"] > a["escalations"]["count"]

    def turns_flat_cost_up_worsened(a, b):
        return (
            b["frontier"]["turns"] >= a["frontier"]["turns"]
            and b["cost_usd"]["total"] > a["cost_usd"]["total"]
        )

    def rework_value(card):
        return card["frontier"]["rework_rounds"]

    def escalations_value(card):
        return card["escalations"]["count"]

    def turns_flat_cost_up_value(card):
        return [card["frontier"]["turns"], card["cost_usd"]["total"]]

    signals = []
    for name, worsened, value_of in (
        ("rework", rework_worsened, rework_value),
        ("escalations", escalations_worsened, escalations_value),
        ("turns_flat_cost_up", turns_flat_cost_up_worsened, turns_flat_cost_up_value),
    ):
        for index in range(len(scorecards) - 2):
            a, b, c = scorecards[index], scorecards[index + 1], scorecards[index + 2]
            if worsened(a, b) and worsened(b, c):
                signals.append({
                    "signal": name,
                    "releases": [a["release"], b["release"], c["release"]],
                    "values": [value_of(a), value_of(b), value_of(c)],
                })

    return {
        "worse": bool(signals),
        "signals": signals,
        "insufficient_series": False,
    }