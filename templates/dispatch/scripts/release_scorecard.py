"""Reduce Claude Code Stop-hook sink rows to per-session survivors and totals.

The Stop hook appends one cumulative snapshot per assistant turn, so rows for a
session supersede each other. ``reduce_sessions`` keeps the newest snapshot per
session and ``frontier_totals`` sums over those survivors only.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REQUIRED_FLAGS = ("release", "sink", "receipts", "out")
_KNOWN_FLAGS = frozenset(_REQUIRED_FLAGS + ("since", "until", "escalations",
                                            "project"))

_USAGE = """\
usage: release_scorecard.py --release RELEASE --sink SINK --receipts RECEIPTS --out OUT [--since SINCE] [--until UNTIL] [--escalations ESCALATIONS] [--project PROJECT]

Reduce the Stop-hook sink and packet receipts into a release scorecard.

required:
  --release RELEASE    release name the scorecard is filed under
  --sink SINK          JSON-lines Stop-hook sink
  --receipts RECEIPTS  directory of <task>/receipt.json files
  --out OUT            scorecard path to write

optional:
  --since SINCE        lower bound (inclusive) on ts / recorded_at
  --until UNTIL        upper bound (exclusive) on ts / recorded_at
  --escalations FILE   JSON-lines escalation records (default: none)
  --project PROJECT    scope the sink to one project (exact match)
  --help               show this help and exit
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
        "usage_equivalent_usd": 0.0,
        "rework_rounds": 0,
    }
    for row in survivors.values():
        for field in ("turns", "assistant_msgs", "tool_calls", "duration_s",
                      "rework_rounds"):
            totals[field] += row.get(field, 0)
        totals["usage_equivalent_usd"] += row.get("cost_usd", 0)
    totals["usage_equivalent_usd"] = round(totals["usage_equivalent_usd"], 6)
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
    """Return the eight aggregate worker fields over any iterable of receipts.

    The argument is materialised once up front, so a generator, an iterator or
    any other one-shot iterable is consumed exactly once and then totalled
    exactly as a list would be. One silent receipt makes the whole cost total
    unreliable: ``cost_reported`` is True only when every contributing receipt
    reported, and the silent tasks are named in sorted order. A first pass is
    an attempt-1 receipt whose gate evidence passed.
    """
    receipts = list(receipts)
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
        "billed_usd": round(total_cost, 6),
        "tokens": total_tokens,
        "cost_reported": len(receipts) > 0 and len(unreported_tasks) == 0,
        "cost_unreported_tasks": sorted(unreported_tasks),
        "first_pass_tasks": len(first_pass_tasks),
        "first_pass_rate": first_pass_rate,
    }


def build_scorecard(release, rows, receipts, escalations, recorded_at,
                    scope=None):
    """Join the two cost halves into the release scorecard.

    ``frontier`` delegates to ``frontier_totals`` over the reduced sink rows
    and ``worker`` delegates to ``worker_totals`` over the packet receipts.
    ``escalations`` is materialised once up front, so a generator, an iterator
    or any other one-shot iterable is consumed exactly once and counted
    exactly as a list would be. Neither half substitutes for the other: the
    hooks never see an OpenCode worker, and the receipts know nothing about
    frontier turns, so both stay separately visible. The two halves are not
    the same kind of number -- the
    frontier figure is an imputed list price that nothing meters, the worker
    figure is real metered spend -- so ``cost_usd`` never adds them.
    ``worker_billed_usd`` is the only money, ``total_billed_usd`` equals it,
    ``frontier_usage_equivalent_usd`` carries the imputed figure renamed,
    ``commensurable`` is always False, and ``total_reliable`` is the worker
    half's ``cost_reported``. Escalation task ids and stop conditions come
    from each record's metadata; a record that carried no stop condition is
    omitted rather than a null.

    ``scope`` is the optional trailing parameter recording what the scorecard
    was built from (project and window). It is carried through verbatim as the
    top-level ``scope`` key, with ``None`` or an omitted value becoming an
    empty dict, so a reader never has to tell absent from unbounded.
    """
    frontier = frontier_totals(rows)
    worker = worker_totals(receipts)
    escalations = list(escalations)
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
            "worker_billed_usd": worker["billed_usd"],
            "frontier_usage_equivalent_usd": frontier["usage_equivalent_usd"],
            "total_billed_usd": worker["billed_usd"],
            "commensurable": False,
            "total_reliable": worker["cost_reported"],
        },
        "scope": scope if scope is not None else {},
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

    def cost_up_without_more_turns_worsened(a, b):
        return (
            b["frontier"]["turns"] <= a["frontier"]["turns"]
            and b["cost_usd"]["frontier_usage_equivalent_usd"]
            > a["cost_usd"]["frontier_usage_equivalent_usd"]
        )

    def rework_value(card):
        return card["frontier"]["rework_rounds"]

    def escalations_value(card):
        return card["escalations"]["count"]

    def cost_up_without_more_turns_value(card):
        return [card["frontier"]["turns"],
                card["cost_usd"]["frontier_usage_equivalent_usd"]]

    signals = []
    for name, worsened, value_of in (
        ("rework", rework_worsened, rework_value),
        ("escalations", escalations_worsened, escalations_value),
        ("cost_up_without_more_turns", cost_up_without_more_turns_worsened,
         cost_up_without_more_turns_value),
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


def load_sink_rows(path):
    """Read a JSON-lines sink and return the parsed dict rows in order.

    Tolerant by design: blank lines, lines that are not valid JSON, and lines
    that parse to something other than a dict are skipped rather than fatal,
    and a path that does not exist returns an empty list. The sink is appended
    to by a shell hook on every assistant turn, so one truncated line from an
    interrupted write must not cost a release its whole scorecard.
    """
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    parsed = json.loads(stripped)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    rows.append(parsed)
    except OSError:
        return []
    return rows


def load_receipts(root):
    """Parse every <task>/receipt.json beneath root, sorted by task_id.

    A subdirectory without a receipt, an unparseable receipt, and a missing
    root are all skipped or empty rather than errors. Sorting by task_id makes
    a scorecard reproducible instead of filesystem-order dependent.
    """
    receipts = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return []
    for name in entries:
        receipt_path = os.path.join(root, name, "receipt.json")
        try:
            with open(receipt_path, encoding="utf-8") as handle:
                parsed = json.load(handle)
        except (OSError, ValueError):
            continue
        if isinstance(parsed, dict):
            receipts.append(parsed)
    receipts.sort(key=lambda r: r.get("task_id", ""))
    return receipts


def filter_by_window(records, start, end, key):
    """Keep records whose key timestamp falls in the half-open [start, end).

    A None bound means that side is unbounded. A record missing the key, or
    carrying a non-string there, is excluded: a record that cannot be placed
    in time cannot be attributed to a release. ISO-8601 strings compare
    directly, which is correct for the fixed-width UTC format the sink writes.
    """
    kept = []
    for record in records:
        value = record.get(key)
        if not isinstance(value, str):
            continue
        if start is not None and value < start:
            continue
        if end is not None and value >= end:
            continue
        kept.append(record)
    return kept


def filter_by_project(rows, project):
    """Keep only the rows whose project equals ``project`` exactly.

    A project of ``None`` means no scoping and returns the rows unchanged in
    the same order. Otherwise matching is exact -- never a substring and never
    case-folded, because ``agentops`` must not match ``agentops-web``, which is
    precisely how another repository's sessions would fold back into the
    figure. A row with no ``project`` key, or a non-string one, is excluded
    when a project is requested, since a row that cannot be attributed to a
    project cannot be counted for one; with no project requested it is kept,
    because nothing is being attributed. The input is not mutated.
    """
    if project is None:
        return list(rows)
    kept = []
    for row in rows:
        if row.get("project") == project:
            kept.append(row)
    return kept


def main(argv):
    """Wire the readers and window together and write the scorecard.

    Takes --release, --sink, --receipts and --out, with optional --since and
    --until bounding the window (sink rows filtered on ts, receipts on
    recorded_at), an optional --project scoping the sink rows to one project
    after the window filter, and an optional --escalations JSON-lines file
    whose absence means an empty list rather than an error. Writes
    build_scorecard's output to --out as indent-2 JSON with a trailing
    newline, creating the parent directory if missing, and returns 0.

    The four required flags are validated before anything is written: a
    missing one, or an unknown flag, writes an error to stderr and returns
    non-zero without touching --out. --help prints the flags to stdout and
    returns 0.
    """
    args = {}
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag == "--help":
            sys.stdout.write(_USAGE)
            return 0
        if not flag.startswith("--"):
            index += 1
            continue
        name = flag[2:]
        if name not in _KNOWN_FLAGS:
            sys.stderr.write(f"error: unknown flag {flag}\n")
            return 2
        if index + 1 >= len(argv):
            sys.stderr.write(f"error: {flag} requires a value\n")
            return 2
        args[name] = argv[index + 1]
        index += 2
    missing = [name for name in _REQUIRED_FLAGS if name not in args]
    if missing:
        sys.stderr.write(
            "error: missing required flag(s): "
            + ", ".join("--" + name for name in missing) + "\n")
        return 2
    release = args.get("release")
    sink_path = args.get("sink")
    receipts_root = args.get("receipts")
    out_path = args.get("out")
    since = args.get("since")
    until = args.get("until")
    project = args.get("project")
    escalations_path = args.get("escalations")

    rows = load_sink_rows(sink_path)
    receipts = load_receipts(receipts_root)
    if since is not None or until is not None:
        rows = filter_by_window(rows, since, until, "ts")
        receipts = filter_by_window(receipts, since, until, "recorded_at")
    if project is not None:
        rows = filter_by_project(rows, project)
    if escalations_path is not None:
        escalations = load_sink_rows(escalations_path)
    else:
        escalations = []
    recorded_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scope = {"project": project, "since": since, "until": until}
    scorecard = build_scorecard(release, rows, receipts, escalations,
                                recorded_at, scope)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scorecard, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))