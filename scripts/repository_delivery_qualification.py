#!/usr/bin/env python3
"""Offline repository-delivery scheduler consumer; owner and integration are fake.

Only run against the disposable repository created by ``init``. This demonstrates
mechanics, not a Sovite lease, authority, Cloud isolation, or a supported workflow.
"""
from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
import subprocess
import sys

from shared_execution.protocol import AttemptEnvelope, RunEnvelope
from shared_execution.runtime import Store, git
from shared_execution.scheduler import tick


class DemoOwner:
    """Injected fake owner: decisions and identities have no external authority."""
    name = "offline-fake-owner"

    def __init__(self, allow=True):
        self.allow = allow

    def review(self, run, candidate, base):
        return {"owner": self.name, "run": run, "candidate": candidate,
                "base": base, "fixture_passed": self.allow}


def initialize(root: Path, failing_test: bool = False, no_change: bool = False):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Offline Demo")
    git(repo, "config", "user.email", "offline@example.invalid")
    (repo / "README.md").write_text("Disposable repository delivery demo.\n")
    git(repo, "add", "README.md")
    git(repo, "commit", "-m", "Base")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "worktree", "add", "--detach", str(root / "candidate"), base)
    run = RunEnvelope(run_id="offline-run-1", project_id="offline-project",
                      repo="offline-repository", base=base, adapter_id="agentops-repository-delivery-demo")
    store = Store(root / "state")
    try:
        store.setmeta("run", run.to_json())
        store.setmeta("failing_test", failing_test)
        store.setmeta("no_change", no_change)
        store.save({"id": "offline-task-1", "state": "PLANNED", "areas": ["."],
                    "provider": "offline", "model": "none", "dependencies": [],
                    "worktree": str(root / "candidate"), "attempt": None})
    finally:
        store.close()


class _Quota:
    def blocked(self, provider):
        return False


class Demo:
    def __init__(self, root: Path, owner: DemoOwner):
        self.root = Path(root).resolve()
        self.repo = self.root / "repo"
        self.candidate = self.root / "candidate"
        self.owner = owner
        self.store = Store(self.root / "state")
        self.run = self.store.meta("run")
        if not self.run:
            self.store.close()
            raise ValueError("not an initialized offline demo")
        self.config = {"max_workers": 1, "launch_spacing": 0}
        self.quota = _Quota()

    def close(self): self.store.close()
    def task(self): return self.store.tasks()[0]
    def step(self):
        task = self.task()
        if task.get("worker_commit") and task["state"] != "MERGED":
            self._integrity(task)
        tick(self)
    def ingest(self): pass
    def ingest_usage(self): pass
    def retry_deferred_failovers(self): pass
    def resume_quota_blocked(self, task): pass
    def capture_checkpoints(self, task): return task
    def finalize_tick(self): pass
    def waiting(self, task, cause): return task
    def save(self, task, state=None, **updates): return self.store.save(task, state, **updates)
    def block(self, task, cause, resume): return self.save(task, "BLOCKED", cause=cause, resume=resume)
    def main_tip(self): return git(self.repo, "rev-parse", "main")
    def verification_command(self):
        return [sys.executable, "-I", str(Path(__file__).with_name("repository_delivery_verifier.py"))]

    def _integrity(self, task):
        candidate = task.get("worker_commit")
        if not candidate or git(self.candidate, "rev-parse", "HEAD") != candidate:
            raise ValueError("candidate commit changed")
        if git(self.candidate, "status", "--porcelain", "--untracked-files=all"):
            raise ValueError("candidate worktree changed")
        if git(self.candidate, "rev-parse", "HEAD^1") != self.run["base"]:
            raise ValueError("candidate base changed")
        check = task.get("check")
        if check and hashlib.sha256(Path(self.verification_command()[-1]).read_bytes()).hexdigest() != check.get("verifier_sha256"):
            raise ValueError("trusted verifier changed after check")

    def start_worker(self, task):
        if self.main_tip() != self.run["base"] or git(self.candidate, "status", "--porcelain"):
            raise ValueError("initial base or candidate changed")
        envelope = AttemptEnvelope(run_id=self.run["run_id"], task_id=task["id"],
            attempt_id="offline-worker-1", number=1, command=("offline-fixture",),
            cwd=str(self.candidate), timeout_seconds=30)
        task = self.save(task, "RUNNING", attempt="offline-worker-1", worker_envelope=envelope.to_json())
        if self.store.meta("no_change"):
            self.store.setmeta("offline-worker-1", {"exit": "no_change"})
            return
        (self.candidate / "delivery.py").write_text('VALUE = "delivered"\n')
        expected = "wrong" if self.store.meta("failing_test") else "delivered"
        (self.candidate / "test_delivery.py").write_text(
            'import unittest\nfrom delivery import VALUE\nclass DeliveryTest(unittest.TestCase):\n'
            f'    def test_value(self): self.assertEqual(VALUE, {expected!r})\n')
        git(self.candidate, "add", "delivery.py", "test_delivery.py")
        git(self.candidate, "commit", "-m", "Offline candidate")
        self.store.setmeta("offline-worker-1", {"exit": "committed", "commit": git(self.candidate, "rev-parse", "HEAD")})

    def status(self, attempt): return self.store.meta(attempt)
    def finish_worker(self, task, result):
        if result["exit"] != "committed":
            self.block(task, "worker-failed", "PLANNED")
        else:
            self.save(task, "READY", worker_commit=result["commit"], attempt=None)

    def attempt(self, kind, task, command, cwd, provider, model, base):
        self._integrity(task)
        if base != self.run["base"]:
            raise ValueError("source base changed; regenerate candidate")
        envelope = AttemptEnvelope(run_id=self.run["run_id"], task_id=task["id"],
            attempt_id="offline-verify-1", number=1, command=tuple(command), cwd=cwd,
            timeout_seconds=30, adapter_data={"base": base, "candidate": task["worker_commit"]})
        self.store.setmeta("verification_envelope", envelope.to_json())
        return "offline-verify-1", 1

    def launch(self, path):
        task = self.task()
        self._integrity(task)
        clean = self.root / "verification"
        if clean.exists():
            raise ValueError("verification worktree already exists; reconcile before retry")
        git(self.repo, "worktree", "add", "--detach", str(clean), task["worker_commit"])
        try:
            verifier = Path(self.verification_command()[-1])
            verifier_hash = hashlib.sha256(verifier.read_bytes()).hexdigest()
            result = subprocess.run(self.verification_command() + [str(clean)], cwd=self.root, env={},
                capture_output=True, text=True, timeout=30)
            dirty = git(clean, "status", "--porcelain", "--untracked-files=all")
            if hashlib.sha256(verifier.read_bytes()).hexdigest() != verifier_hash:
                raise ValueError("trusted verifier changed during check")
            self.store.setmeta(str(path), {"exit": "committed" if result.returncode == 0 and not dirty else "check_failed",
                "candidate": git(clean, "rev-parse", "HEAD"), "verifier_sha256": verifier_hash, "output": result.stdout + result.stderr})
        finally:
            git(self.repo, "worktree", "remove", "--force", str(clean))

    def finish_verify(self, task, result):
        self._integrity(task)
        if result["exit"] != "committed" or result["candidate"] != task["worker_commit"]:
            self.block(task, "verification-failed", "READY")
            return
        self.save(task, verification_done=True, verified_tip=result["candidate"], check=result)

    def accept_review(self, task):
        self._integrity(task)
        decision = self.owner.review(self.run["run_id"], task["worker_commit"], task["verified_base"])
        if not decision.get("fixture_passed") or decision.get("candidate") != task["verified_tip"] or decision.get("base") != task["verified_base"]:
            self.block(task, "fake-owner-denied", "READY")
            return
        self.save(task, "REVIEWED", review=decision)

    def integrate(self, task):
        self._integrity(task)
        if self.main_tip() != task["verified_base"] or task["verified_tip"] != task["worker_commit"]:
            raise ValueError("base or verified candidate changed")
        decision = self.owner.review(self.run["run_id"], task["worker_commit"], task["verified_base"])
        if decision != task["review"] or not decision.get("fixture_passed"):
            raise ValueError("fake owner decision changed")
        # Simulated completion only: no merge or publication occurs.
        self.save(task, "MERGED", receipt={"owner": self.owner.name, "candidate": task["worker_commit"], "simulated": True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["init", "step", "inspect"])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    if args.action == "init":
        initialize(args.directory)
        print("Initialized disposable offline demo; no live owner or authority.")
        return 0
    demo = Demo(args.directory, DemoOwner())
    try:
        if args.action == "step": demo.step()
        print(json.dumps({"owner": "offline-fake-owner", "task": demo.task()}, indent=2))
    finally:
        demo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
