"""Coordinator-authored oracle for the protected-scope hand-pass (handover §3a,
amendment 1) — items A-F of one hand-pass over ``hybrid_dispatch.py``, the
hybrid policy and the task-packet schema.

A  the read-trace ignores directory-fd-relative ``openat``
B  the trace asks strace for the portable ``%file`` syscall class
C  the ``opencode export`` worker-session path is gone
D  ``mechanical_bulk`` allows a second attempt
E  the packet schema admits ``release_boundary``
F  ``prepare`` lets a retry back into its own workspace

Written against the hand-pass spec only: none of it is implemented, so every
test here fails.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[3]
HYBRID = ROOT / "templates/dispatch/hybrid"
SCRIPTS = ROOT / "templates/dispatch/scripts"

#: The refusal F must leave untouched for a first attempt, word for word.
FIRST_ATTEMPT_REFUSAL = "already exists; never dispatch two workers into one workspace"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


dispatch = _load_module("hybrid_dispatch_handpass_subject", SCRIPTS / "hybrid_dispatch.py")


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest() -> dict:
    return {
        "repo_id": "example",
        "scope": {"allowed_path_roots": ["src/", "tests/"]},
        "hybrid": {
            "enabled": True,
            "worker_routes": ["mechanical_bulk"],
            "commands": {"example.tests": "false"},
            "protected_paths": ["src/authority/**"],
            "max_timeout_seconds": 1200,
            "max_cost_usd": 3.0,
            "soft_token_ceiling": 500000,
            "hard_token_ceiling": 1000000,
        },
    }


def _packet() -> dict:
    return {
        "schema_version": "agentops-task/v2",
        "task_id": "EX-1",
        "repo_id": "example",
        "sprint_item": {"ref": "example#42", "claim_id": 7, "claim_actor": "coordinator/claude-code"},
        "route": "mechanical_bulk",
        "task_class": "mechanical_implementation",
        "risk": "low",
        "oracle": {
            "ownership": "externally_defined",
            "worker_may_modify": False,
            "description": "Coordinator-authored executable oracle",
        },
        "attempt": 1,
        "starting_commit": "a" * 40,
        "purpose": "p",
        "readable_context_paths": ["src/**"],
        "writable_patch_paths": ["tests/**"],
        "protected_paths": ["src/authority/**"],
        "required_outcomes": ["o"],
        "acceptance_properties": [
            {
                "id": "REQ-001",
                "requirement": "o",
                "command_id": "example.tests",
                "fails_when": "o is not implemented",
            }
        ],
        "non_goals": ["n"],
        "allowed_command_ids": ["example.tests"],
        "limits": {
            "timeout_seconds": 600,
            "max_cost_usd": 0.25,
            "soft_token_ceiling": 500000,
            "hard_token_ceiling": 1000000,
        },
        "context_churn": {
            "max_repeated_reads_per_path": 4,
            "max_reasoning_steps_without_mutation": 8,
            "max_identical_context_tokens": 250000,
            "handoff_when_candidate_ready": True,
        },
        "network_policy": "disabled",
        "worktree": {"root": "/tmp/wt", "branch": "hybrid/ex-1", "cleanup": "retain-for-review"},
    }


class DirectoryFdReadTraceTests(unittest.TestCase):
    """A: ``openat(fd, "name", ...)`` resolves against that fd, not the cwd.

    ``shutil.rmtree`` walks with directory fds, so every oracle in this
    repository -- all of which use ``TemporaryDirectory`` -- emits such lines on
    cleanup and the parser invents a checkout-relative read from each one. That
    is why ``oracle_reads_within_paths`` is unobtainable today.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkout = Path(os.path.realpath(self.tmp.name)) / "checkout"
        for rel in ("src/a.py", "src/b.py", "templates/x.py"):
            (self.checkout / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.checkout / rel).write_text("x", encoding="utf-8")

    def _reads(self, *lines: str) -> set[str]:
        return dispatch.parse_strace_reads("\n".join(lines) + "\n", self.checkout)

    def test_A_a_directory_fd_relative_open_is_not_a_read_of_the_checkout(self) -> None:
        # The literal line TemporaryDirectory cleanup emits; "coordinator" here
        # names an entry under fd 3, which is nowhere near the checkout root.
        # The other three forms keep resolving, so the fix cannot be "stop
        # resolving relative paths".
        reads = self._reads(
            '129320 openat(3, "coordinator", O_RDONLY|O_NONBLOCK|O_CLOEXEC) = 4',
            '123   openat(AT_FDCWD, "templates/x.py", O_RDONLY) = 4',
            f'123   openat(AT_FDCWD, "{self.checkout}/src/a.py", O_RDONLY|O_CLOEXEC) = 3',
            # open() has no fd argument at all, so it keeps cwd resolution.
            '123   open("src/b.py", O_RDONLY) = 3',
        )
        self.assertEqual(reads, {"templates/x.py", "src/a.py", "src/b.py"})

    def test_A_the_existing_exclusions_are_unchanged(self) -> None:
        reads = self._reads(
            f'123   openat(AT_FDCWD, "{self.checkout}/src/a.py", O_RDONLY|O_CLOEXEC) = 3',
            f'123   openat(AT_FDCWD, "{self.checkout}/src", O_RDONLY|O_DIRECTORY) = 5',
            f'123   openat(AT_FDCWD, "{self.checkout}/gone.md", O_RDONLY) = -1 ENOENT (No such file)',
            f'123   openat(AT_FDCWD, "{self.checkout}/out.log", O_WRONLY|O_CREAT, 0666) = 6',
            '123   openat(AT_FDCWD, "/usr/lib/python3/os.py", O_RDONLY|O_CLOEXEC) = 7',
            '129320 openat(3, "coordinator", O_RDONLY|O_NONBLOCK|O_CLOEXEC) = 4',
        )
        self.assertEqual(reads, {"src/a.py"})


class PortableTraceSyscallClassTests(unittest.TestCase):
    """B: strace's ``%file`` class, not a hand-maintained syscall list."""

    def setUp(self) -> None:
        self.packet = _packet()
        self.packet["oracle"]["starts_red"] = ["example.tests"]
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.checkout = Path(self.tmp.name) / "checkout"
        self.checkout.mkdir()

    def _traced_argv(self) -> list[str]:
        seen: list[list[str]] = []
        original = dispatch.subprocess.run

        def fake_run(argv, **kwargs):
            seen.append(list(argv))
            return subprocess.CompletedProcess(argv, 1, "", "")

        dispatch.subprocess.run = fake_run
        try:
            dispatch.trace_oracle_reads(
                self.checkout, self.packet, {"example.tests": "pytest -q"}, "/usr/bin/strace",
            )
        finally:
            dispatch.subprocess.run = original
        self.assertTrue(seen, "the tracer was never invoked")
        return seen[0]

    def test_B_the_tracer_asks_for_the_file_syscall_class(self) -> None:
        argv = self._traced_argv()
        self.assertIn("-e", argv)
        self.assertEqual(argv[argv.index("-e") + 1], "trace=%file")

    def test_B_the_hand_maintained_syscall_list_is_gone(self) -> None:
        # A literal list silently misses whatever the platform names differently;
        # the class is what strace itself keeps current.
        self.assertNotIn("openat,open,stat,readlink", " ".join(self._traced_argv()))


class WorkerSessionExportRemovalTests(unittest.TestCase):
    """C: ``opencode export`` produced truncated JSON on every session it ever
    ran on. The transcript survives in the run receipt under ``worker.stdout``,
    which sits beside the receipt, so L-1b holds without the export.

    Deliberately removed -- do not restore the export path or its receipt key.
    """

    def setUp(self) -> None:
        self.packet = _packet()
        self.manifest = _manifest()

    def _run_receipt(self) -> tuple[int, dict]:
        transcript = {
            "argv": ["opencode", "run"],
            "worker_user": None,
            "agent": "ao-mechanical-bulk",
            "model": "opencode-go/deepseek-v4-flash",
            "exit_code": 0,
            "stdout": json.dumps({"sessionID": "ses_1", "type": "text"}) + "\n",
            "stderr_tail": "",
            "session_id": "ses_1",
            "churn_stop": None,
        }
        originals = (
            dispatch.verify_live_coordinator_claim,
            dispatch.dispatch_worker,
            dispatch.worker_cannot_write,
            dispatch.coordinator_tree_state,
        )
        dispatch.verify_live_coordinator_claim = lambda *a, **k: {"claim": "stubbed"}
        dispatch.dispatch_worker = lambda *a, **k: dict(transcript)
        dispatch.worker_cannot_write = lambda *a, **k: True
        dispatch.coordinator_tree_state = lambda *a, **k: []
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.packet["worktree"]["root"] = str(root / "wt")
                (root / "wt" / self.packet["repo_id"] / self.packet["task_id"]).mkdir(parents=True)
                packet_path = root / "p.json"
                packet_path.write_text(json.dumps(self.packet), encoding="utf-8")
                (root / "example.dispatch.json").write_text(json.dumps(self.manifest), encoding="utf-8")
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = dispatch.main([
                        "--repo-root", tmp, "--packet", str(packet_path),
                        "--agentops-root", str(ROOT),
                        # Never a real worker: an absent binary also proves the
                        # receipt does not depend on one for its transcript.
                        "--opencode-bin", str(root / "no-such-opencode"),
                        "run",
                    ])
                return code, json.loads(out.getvalue())
        finally:
            (
                dispatch.verify_live_coordinator_claim,
                dispatch.dispatch_worker,
                dispatch.worker_cannot_write,
                dispatch.coordinator_tree_state,
            ) = originals

    def test_C_the_export_primitive_is_gone(self) -> None:
        self.assertFalse(hasattr(dispatch, "export_worker_session"))

    def test_C_the_run_receipt_carries_the_transcript_instead_of_an_export(self) -> None:
        code, receipt = self._run_receipt()
        self.assertEqual(code, 0, receipt)
        self.assertEqual(receipt["worker"]["session_id"], "ses_1")
        self.assertIn("ses_1", receipt["worker"]["stdout"])
        # Nowhere in the receipt, not merely absent at the top level: a nested
        # remnant would keep dispatch_release carrying it forward.
        self.assertNotIn("worker_session", json.dumps(receipt))


class RetryAttemptAllowanceTests(unittest.TestCase):
    """D: L-4's retry packet carries ``attempt: 2``, and a route capped at one
    attempt made that packet impossible by construction.

    The allowance was raised from one retry to two on 2026-08-24 by owner
    ruling, after V5-M10c needed a third attempt: the counter stays honest and
    the limit moves, rather than a packet resetting its own ``attempt`` field
    to get past the cap.

    The literal below is load-bearing and deliberate. The allowance is an owner
    decision, and the derived fixtures elsewhere cannot see it change: widening
    it to 99 leaves every one of them green. Pinning the number here is the only
    thing that makes a silent widening fail, so this fixture guards the decision
    and the ones in test_hybrid_dispatch.py guard the property."""

    def setUp(self) -> None:
        self.policy = _json(HYBRID / "hybrid-dispatch.v1.json")
        self.manifest = _manifest()
        self.packet = _packet()

    def test_D_the_policy_allows_bounded_retries_on_mechanical_bulk(self) -> None:
        self.assertEqual(
            self.policy["routes"]["mechanical_bulk"]["max_attempts"], 3,
            "the owner-ruled allowance is two retries; changing it is a decision, "
            "not a refactor",
        )

    def test_D_attempts_up_to_the_allowance_validate_and_the_next_is_refused(self) -> None:
        allowance = self.policy["routes"]["mechanical_bulk"]["max_attempts"]
        for attempt in range(2, allowance + 1):
            with self.subTest(attempt=attempt):
                self.packet["attempt"] = attempt
                self.assertEqual(
                    dispatch.validate_packet(self.packet, self.manifest, self.policy),
                    self.policy["gates"]["pre"],
                )
        # Bounded, not an open loop: one past the allowance is still refused.
        self.packet["attempt"] = allowance + 1
        with self.assertRaisesRegex(dispatch.PacketError, "max_attempts"):
            dispatch.validate_packet(self.packet, self.manifest, self.policy)
        del self.packet["attempt"]
        self.assertEqual(
            dispatch.validate_packet(self.packet, self.manifest, self.policy),
            self.policy["gates"]["pre"],
        )


class ReleaseBoundarySchemaTests(unittest.TestCase):
    """E: M-1 shipped a ``release-boundary`` stop reading a top-level
    ``release_boundary``, while the schema forbids unknown properties -- so the
    schema and the driver contradict each other."""

    #: The frozen required set. E adds an optional property and nothing else.
    REQUIRED = [
        "schema_version", "task_id", "repo_id", "sprint_item", "route", "task_class",
        "risk", "oracle", "starting_commit", "purpose", "readable_context_paths",
        "writable_patch_paths", "protected_paths", "required_outcomes",
        "acceptance_properties", "non_goals", "allowed_command_ids", "limits",
        "network_policy", "worktree",
    ]

    def setUp(self) -> None:
        self.schema = _json(HYBRID / "task-packet.schema.json")

    def test_E_the_schema_declares_an_optional_boolean_release_boundary(self) -> None:
        self.assertEqual(self.schema["properties"]["release_boundary"]["type"], "boolean")
        self.assertNotIn("release_boundary", self.schema["required"])
        # Declared, never admitted by loosening the closed property set: the
        # schema is what stops a packet carrying fields nobody reads.
        self.assertIs(self.schema["additionalProperties"], False)
        # Nothing else about the schema moves: the required list is untouched
        # and v2 stays the version.
        self.assertEqual(self.schema["required"], self.REQUIRED)
        self.assertEqual(
            self.schema["properties"]["schema_version"]["enum"],
            ["agentops-task/v1", "agentops-task/v2"],
        )


class RetryWorkspaceReuseTests(unittest.TestCase):
    """F: the "two workers in one workspace" guard also blocked the one thing a
    retry needs -- coming back to its own workspace for a second attempt. It is
    what made V5-M2 the packet that could not unblock its own retry."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(os.path.realpath(self.tmp.name))
        self.repo = root / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "src/a.py").write_text("x\n", encoding="utf-8")
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x",
        }
        for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "start"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True, env=env, capture_output=True)
        self.packet = _packet()
        self.packet["starting_commit"] = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self.packet["worktree"]["root"] = str(root / "wt")
        self.manifest = _manifest()
        (self.repo / "example.dispatch.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def _prepare_receipt(self) -> tuple[int, dict]:
        original = dispatch.verify_live_coordinator_claim
        dispatch.verify_live_coordinator_claim = lambda *a, **k: {"claim": "stubbed"}
        try:
            packet_path = self.repo / "p.json"
            packet_path.write_text(json.dumps(self.packet), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = dispatch.main([
                    "--repo-root", str(self.repo), "--packet", str(packet_path),
                    "--agentops-root", str(ROOT), "prepare",
                ])
            return code, json.loads(out.getvalue())
        finally:
            dispatch.verify_live_coordinator_claim = original

    def test_F_a_retry_reuses_the_workspace_a_first_attempt_may_not(self) -> None:
        target = dispatch.prepare_workspace(self.repo, self.packet)
        # Attempt 1 is still refused word for word: the guard against two
        # workers in one workspace is not what F relaxes.
        with self.assertRaisesRegex(dispatch.PacketError, re.escape(FIRST_ATTEMPT_REFUSAL)):
            dispatch.prepare_workspace(self.repo, self.packet)

        # The previous attempt's edits. A re-clone would erase them, and that is
        # exactly what a retry must not do.
        (target / "tests" / "attempt-1.txt").parent.mkdir(exist_ok=True)
        (target / "tests" / "attempt-1.txt").write_text("kept\n", encoding="utf-8")

        self.packet["attempt"] = 2
        reused = dispatch.prepare_workspace(self.repo, self.packet)

        self.assertEqual(reused, target)
        self.assertEqual((target / "tests" / "attempt-1.txt").read_text(encoding="utf-8"), "kept\n")
        branch = subprocess.run(
            ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(branch, self.packet["worktree"]["branch"])

    def test_F_a_retry_with_no_workspace_left_prepares_a_fresh_one(self) -> None:
        # Nothing is standing here on purpose: the reuse trigger is the workspace
        # being there, so a retry whose workspace was cleaned up must clone one
        # and be assessed cold exactly as a first attempt is -- the red
        # registered command still blocks dispatch.
        self.packet["attempt"] = 2

        code, receipt = self._prepare_receipt()

        self.assertEqual(code, 2, receipt)
        self.assertTrue((Path(receipt["worktree"]) / "src/a.py").is_file())
        self.assertIsNot(receipt.get("workspace_reused"), True)
        self.assertFalse(receipt["eligible_for_dispatch"])

    def test_F_a_reuse_reports_its_skipped_cold_gate_assessment(self) -> None:
        """A reused workspace holds the previous attempt's edits, so its cold
        gates no longer have the colours the packet declared. The commands still
        run and are recorded; only the verdict is withheld -- and the receipt
        has to say so, or a reader cannot tell a skipped assessment from a green
        one."""
        dispatch.prepare_workspace(self.repo, self.packet)
        self.packet["attempt"] = 2

        code, receipt = self._prepare_receipt()

        self.assertEqual(code, 0, receipt)
        self.assertIs(receipt["workspace_reused"], True)
        self.assertEqual(receipt["cold_gate_assessment"], "skipped:workspace-reused")
        self.assertTrue(receipt["eligible_for_dispatch"])
        # Recorded, not suppressed: the red cold command is still evidence.
        self.assertEqual(
            [r["command_id"] for r in receipt["cold_command_results"]], ["example.tests"],
        )
        self.assertNotEqual(receipt["cold_command_results"][0]["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
