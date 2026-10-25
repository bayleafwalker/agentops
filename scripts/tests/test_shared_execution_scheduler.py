"""Parity guards for the mechanically extracted one-tick scheduler."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared_execution.scheduler import advance_serialized_candidate, schedule_worker_slots, tick  # noqa: E402


class FakeStore:
    def __init__(self, tasks, meta=None):
        self._tasks = deepcopy(tasks)
        self._meta = dict(meta or {})

    def tasks(self):
        return deepcopy(self._tasks)

    def meta(self, key, default=None):
        return self._meta.get(key, default)

    def setmeta(self, key, value):
        self._meta[key] = value


class FakeQuota:
    def __init__(self, blocked=()):
        self.blocked_providers = set(blocked)

    def blocked(self, provider):
        return [dict(provider=provider)] if provider in self.blocked_providers else []


class Adapter:
    def __init__(self, tasks, *, max_workers=3, results=None, blocked=()):
        self.store = FakeStore(tasks)
        self.config = {"max_workers": max_workers, "launch_spacing": 0}
        self.quota = FakeQuota(blocked)
        self.results = dict(results or {})
        self.calls = []
        self.attempt_number = 0
        self.tip = "main-0"

    def ingest(self): self.calls.append("ingest")
    def ingest_usage(self): self.calls.append("usage")
    def retry_deferred_failovers(self): self.calls.append("failovers")
    def capture_checkpoints(self, task): self.calls.append(("checkpoint", task["id"])); return task
    def status(self, attempt): self.calls.append(("status", attempt)); return self.results.get(attempt)
    def finish_worker(self, task, result):
        self.calls.append(("finish_worker", task["id"]))
        self.save(task, "READY", worker_result=result)
    def resume_quota_blocked(self, task): self.calls.append(("resume_quota", task["id"]))
    def waiting(self, task, cause):
        self.calls.append(("waiting", task["id"], cause))
        return task
    def block(self, task, cause, resume):
        self.calls.append(("block", task["id"], cause, resume))
        return self.save(task, "BLOCKED", cause=cause, resume=resume)
    def start_worker(self, task):
        self.calls.append(("start_worker", task["id"]))
        self.save(task, "RUNNING", attempt="worker:" + task["id"])
    def save(self, task, state=None, **updates):
        saved = next(item for item in self.store._tasks if item["id"] == task["id"])
        if state is not None:
            saved["state"] = state
        saved.update(updates)
        self.calls.append(("save", task["id"], state))
        return deepcopy(saved)
    def main_tip(self): self.calls.append("main_tip"); return self.tip
    def verification_command(self):
        self.calls.append("verification_command")
        return ["adapter-check", "--project-profile"]
    def attempt(self, kind, task, command, cwd, provider, model, base):
        self.attempt_number += 1
        value = ("attempt:" + str(self.attempt_number), self.attempt_number)
        self.calls.append(("attempt", kind, task["id"], tuple(command), base))
        return value
    def launch(self, path): self.calls.append(("launch", str(path)))
    def finish_verify(self, task, result): self.calls.append(("finish_verify", task["id"]))
    def accept_review(self, task): self.calls.append(("accept_review", task["id"]))
    def integrate(self, task): self.calls.append(("integrate", task["id"]))
    def finalize_tick(self): self.calls.append("finalize")


class SchedulerTests(unittest.TestCase):
    @staticmethod
    def task(task_id, state, *, areas=None, attempt=None, dependencies=(), overlap_with=()):
        return dict(id=task_id, state=state, areas=list(areas or ["src"]),
                    provider="provider-a", model="model-a", worktree="/tmp/" + task_id,
                    attempt=attempt, dependencies=list(dependencies), overlap_with=list(overlap_with))

    def test_tick_collects_completion_before_refilling_worker_slot(self):
        adapter = Adapter(
            [self.task("done", "RUNNING", attempt="worker:done"), self.task("next", "PLANNED")],
            max_workers=1, results={"worker:done": {"exit": "committed"}})
        tick(adapter)
        finish_index = adapter.calls.index(("finish_worker", "done"))
        start_index = adapter.calls.index(("start_worker", "next"))
        self.assertLess(finish_index, start_index)
        self.assertEqual(adapter.store._tasks[0]["state"], "VERIFYING")
        self.assertEqual(adapter.store._tasks[1]["state"], "RUNNING")
        self.assertEqual(adapter.calls[-1], "finalize")

    def test_slot_admission_respects_areas_dependencies_and_unblocked_capacity(self):
        adapter = Adapter([
            self.task("active", "RUNNING", areas=["src/core"], attempt="a1"),
            self.task("overlap", "PLANNED", areas=["src"]),
            self.task("dependency", "PLANNED", areas=["ui"], dependencies=["missing"]),
            self.task("independent", "PLANNED", areas=["docs"]),
        ], max_workers=2)
        schedule_worker_slots(adapter)
        self.assertEqual(adapter.store._tasks[1]["state"], "PLANNED")
        self.assertEqual(adapter.store._tasks[2]["state"], "PLANNED")
        self.assertEqual(adapter.store._tasks[3]["state"], "RUNNING")
        self.assertIn(("waiting", "overlap", "overlapping_areas"), adapter.calls)
        self.assertIn(("waiting", "dependency", "dependencies"), adapter.calls)

    def test_only_one_ready_candidate_enters_serialized_verification(self):
        adapter = Adapter([self.task("first", "READY"), self.task("second", "READY")])
        advance_serialized_candidate(adapter)
        self.assertEqual(adapter.store._tasks[0]["state"], "VERIFYING")
        self.assertEqual(adapter.store._tasks[1]["state"], "READY")
        self.assertEqual(adapter.attempt_number, 1)
        self.assertIn(("attempt", "verify", "first", ("adapter-check", "--project-profile"), "main-0"),
                      adapter.calls)
        self.assertEqual(sum(1 for call in adapter.calls if isinstance(call, tuple)
                             and call[0] == "attempt"), 1)
        self.assertIn(("waiting", "second", "integration_queue"), adapter.calls)

    def test_stale_reviewed_candidate_returns_to_verify_before_next_candidate(self):
        stale = self.task("first", "REVIEWED", attempt="verify:1")
        stale.update(verified_base="main-old", verified_tip="candidate-tip")
        next_ready = self.task("second", "READY")
        adapter = Adapter([stale, next_ready])
        adapter.tip = "main-new"
        advance_serialized_candidate(adapter)
        self.assertEqual(adapter.store._tasks[0]["state"], "VERIFYING")
        self.assertEqual(adapter.store._tasks[0]["attempt"], None)
        self.assertEqual(adapter.store._tasks[1]["state"], "READY")


if __name__ == "__main__":
    unittest.main()
