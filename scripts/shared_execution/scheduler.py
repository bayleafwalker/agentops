"""Mechanical task scheduling and single-candidate integration progression.

Project adapters provide task ingestion, provider policy, worker/check attempts,
acceptance decisions, integration, and tick finalization. This module preserves
the ordered queue mechanics without defining project risk or authority policy.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .runtime import EXITS, overlaps


def tick(adapter: Any) -> None:
    """Run one scheduling tick against a project adapter's existing hooks."""
    adapter.ingest()
    adapter.ingest_usage()

    # Collect every completed slot before admitting more work; no batch wait.
    for task in adapter.store.tasks():
        if task["state"] == "RUNNING":
            task = adapter.capture_checkpoints(task)
            result = adapter.status(task["attempt"])
            if result:
                if result.get("exit") not in EXITS:
                    raise ValueError("invalid worker exit contract")
                adapter.finish_worker(task, result)
        elif task["state"] == "BLOCKED":
            adapter.resume_quota_blocked(task)

    # Provider- and owner-specific usage reconciliation remains in the adapter.
    adapter.retry_deferred_failovers()
    schedule_worker_slots(adapter)
    advance_serialized_candidate(adapter)
    adapter.finalize_tick()


def schedule_worker_slots(adapter: Any) -> None:
    """Admit planned tasks using capacity, dependency, area, quota and spacing rules."""
    tasks = adapter.store.tasks()
    active = [task for task in tasks if task["state"] == "RUNNING"]
    for task in tasks:
        if task["state"] != "PLANNED":
            continue
        if len(active) >= adapter.config.get("max_workers", 3):
            adapter.waiting(task, "worker_capacity")
            continue
        if any(not any(other["id"] == dependency and other["state"] == "MERGED"
                       for other in tasks) for dependency in task.get("dependencies", [])):
            adapter.waiting(task, "dependencies")
            continue
        if any(overlaps(task["areas"], other["areas"]) and not
               (other["id"] in task.get("overlap_with", [])
                and task["id"] in other.get("overlap_with", [])) for other in active):
            adapter.waiting(task, "overlapping_areas")
            continue
        if adapter.quota.blocked(task["provider"]):
            task = adapter.waiting(task, None)
            adapter.block(task, "quota:" + task["provider"], "PLANNED")
            continue
        if time.time() < adapter.store.meta("next_worker_start", 0):
            adapter.waiting(task, "startup_spacing")
            continue
        task = adapter.waiting(task, None)
        adapter.start_worker(task)
        adapter.store.setmeta("next_worker_start", time.time() + adapter.config.get("launch_spacing", 90))
        active.append(task)


def advance_serialized_candidate(adapter: Any) -> None:
    """Advance at most one candidate through verification, review and integration."""
    tasks = adapter.store.tasks()
    for task in tasks:
        if task["state"] == "READY":
            adapter.waiting(task, "integration_queue")

    tasks = adapter.store.tasks()
    candidate = next((task for task in tasks
                      if task["state"] in {"VERIFYING", "REVIEWED", "MERGING"}), None)
    if candidate is None:
        candidate = next((task for task in tasks if task["state"] == "READY"), None)
        if candidate:
            candidate = adapter.save(candidate, "VERIFYING", attempt=None,
                                     verification_done=False, review=None)
    if candidate is None:
        return

    state = candidate["state"]
    if state == "VERIFYING":
        if not candidate.get("attempt"):
            base = adapter.main_tip()
            command = adapter.config.get("check_command", ["nix", "develop", "-c", "just", "check"])
            directory, number = adapter.attempt(
                "verify", candidate, command, candidate["worktree"],
                candidate["provider"], candidate["model"], base)
            candidate = adapter.save(candidate, attempt=directory, attempts=number,
                                     verified_base=base, verified_tip=None, review=None,
                                     verification_done=False)
            adapter.launch(Path(directory))
        elif not candidate.get("verification_done"):
            result = adapter.status(candidate["attempt"])
            if result:
                adapter.finish_verify(candidate, result)
        elif adapter.main_tip() != candidate["verified_base"]:
            adapter.save(candidate, attempt=None, check=None, review=None,
                         verification_done=False)
        else:
            candidate = adapter.waiting(candidate, "automated_review")
            adapter.accept_review(candidate)
    elif state == "REVIEWED":
        if adapter.main_tip() != candidate["verified_base"]:
            adapter.save(candidate, "VERIFYING", attempt=None, check=None,
                         review=None, verification_done=False)
        else:
            adapter.save(candidate, "MERGING")
    else:
        adapter.integrate(candidate)
