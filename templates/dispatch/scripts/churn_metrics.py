#!/usr/bin/env python3
"""Summarise a worker stream on exactly the terms ``churn_verdict`` judges it.

``churn_verdict`` stops a worker that has stopped making progress and records
nothing when it does not stop, so a healthy run and a lucky one leave the same
trace. This module adds the counters and nothing else: no receipt wiring, no
CLI, no file I/O.

Every counting rule is the verdict's own, so the two cannot drift apart:

* Only ``type == "tool_use"`` events are considered.
* ``tool_events`` counts completed tool events -- completed mutations included,
  since the verdict considers those too (they reset the run).
* ``max_steps_without_mutation`` is the high-water mark of completed non-mutation
  steps since the last completed mutation, over the whole stream -- not the run
  in progress when the stream ended. A failed mutation does not reset it and
  does not spend a step; an incomplete non-mutation call spends no step either.
* ``max_repeated_reads`` / ``most_read_path`` / ``distinct_paths_read`` are
  keyed on ``part.state.input.filePath`` for completed reads only, and the tally
  is never cleared.
* ``failed_mutation_runs`` counts one per maximal run of three or more
  consecutive failed mutation attempts, where only a completed mutation ends a
  run -- interleaved reads and steps do not break it.
* ``incomplete_tool_events`` counts tool events that did not complete and are
  not failed mutations; a failed mutation is charged to its own run counter.

``MUTATION_TOOLS`` is imported from ``hybrid_dispatch`` rather than restated, so
the mutation set cannot drift either.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location(
    "_hybrid_dispatch_for_churn_metrics", HERE / "hybrid_dispatch.py"
)
_dispatch = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_dispatch)  # type: ignore[union-attr]

MUTATION_TOOLS = _dispatch.MUTATION_TOOLS


def churn_metrics(events):
    """Return the churn counters for ``events``, consumed exactly once.

    ``events`` is any iterable of stream events, drained in a single pass.
    """
    tool_events = 0
    max_steps_without_mutation = 0
    max_repeated_reads = 0
    most_read_path = None
    completed_mutations = 0
    failed_mutation_runs = 0
    incomplete_tool_events = 0

    steps_since_mutation = 0
    failed_mutations = 0
    reads: dict[str, int] = {}

    for event in events:
        if event.get("type") != "tool_use":
            continue
        part = event.get("part") or {}
        tool = part.get("tool")
        state = part.get("state") or {}
        status = state.get("status")
        if tool in MUTATION_TOOLS:
            if status == "completed":
                tool_events += 1
                completed_mutations += 1
                if failed_mutations >= 3:
                    failed_mutation_runs += 1
                failed_mutations = 0
                steps_since_mutation = 0
                continue
            failed_mutations += 1
            continue
        if status != "completed":
            incomplete_tool_events += 1
            continue
        tool_events += 1
        steps_since_mutation += 1
        if steps_since_mutation > max_steps_without_mutation:
            max_steps_without_mutation = steps_since_mutation
        if tool == "read":
            path = (state.get("input") or {}).get("filePath")
            if path:
                reads[path] = reads.get(path, 0) + 1
                if reads[path] > max_repeated_reads:
                    max_repeated_reads = reads[path]
                    most_read_path = path
    if failed_mutations >= 3:
        failed_mutation_runs += 1

    return {
        "tool_events": tool_events,
        "max_steps_without_mutation": max_steps_without_mutation,
        "max_repeated_reads": max_repeated_reads,
        "most_read_path": most_read_path,
        "distinct_paths_read": len(reads),
        "completed_mutations": completed_mutations,
        "failed_mutation_runs": failed_mutation_runs,
        "incomplete_tool_events": incomplete_tool_events,
    }