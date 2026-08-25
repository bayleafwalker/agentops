#!/usr/bin/env python3
"""Prove exact registered-command execution from the worker's own stream.

``build_overlay`` hands the worker a bash permission map of ``{"*": "deny"}``
plus one exact-string ``allow`` per granted command id, so OpenCode refuses any
bash call that is not character-for-character a registered command. A
configured rule is not a held rule; the proof is in the stream, and this module
reads it.

``command_evidence`` returns exactly:

* ``bash_calls`` -- every bash tool event, completed or not
* ``granted_commands_run`` -- ids whose EXACT string completed, sorted, no dupes
* ``granted_commands_denied`` -- ids whose exact string was attempted and did
  not complete, sorted
* ``ungranted_attempts`` -- bash calls that are not the exact string of a
  GRANTED id, including registered-but-ungranted commands, which the packet did
  not authorise
* ``ungranted_completed`` -- how many of those completed; any nonzero is a
  containment failure
* ``exact_execution_proven`` -- True iff at least one granted id completed
  exactly AND ``ungranted_completed == 0``

Matching is EXACT. A registered command with an extra flag, a prefix of one,
one with surrounding whitespace, or one with something chained after ``&&`` is
a different command; counting any of them as the granted one would report a
boundary that was never tested. The grant is ``packet["allowed_command_ids"]``,
not the manifest: a command the manifest registers but the packet did not grant
is foreign.
"""
from __future__ import annotations


def command_evidence(events, packet, commands):
    """Return the exact-execution evidence for ``events``, drained once.

    ``events`` is any iterable of stream events, consumed in a single pass.
    ``packet`` supplies ``allowed_command_ids``; ``commands`` maps command id
    to its exact command string.
    """
    granted = set(packet.get("allowed_command_ids") or ())
    commands = commands or {}
    exact = {cid: commands[cid] for cid in granted if cid in commands}

    bash_calls = 0
    run: set[str] = set()
    denied: set[str] = set()
    ungranted_attempts = 0
    ungranted_completed = 0

    for event in events:
        if event.get("type") != "tool_use":
            continue
        part = event.get("part") or {}
        if part.get("tool") != "bash":
            continue
        bash_calls += 1
        state = part.get("state") or {}
        command = (state.get("input") or {}).get("command")
        status = state.get("status")
        matched = None
        for cid, text in exact.items():
            if command == text:
                matched = cid
                break
        if matched is not None:
            if status == "completed":
                run.add(matched)
            else:
                denied.add(matched)
        else:
            ungranted_attempts += 1
            if status == "completed":
                ungranted_completed += 1

    return {
        "bash_calls": bash_calls,
        "granted_commands_run": sorted(run),
        "granted_commands_denied": sorted(denied),
        "ungranted_attempts": ungranted_attempts,
        "ungranted_completed": ungranted_completed,
        "exact_execution_proven": bool(run) and ungranted_completed == 0,
    }