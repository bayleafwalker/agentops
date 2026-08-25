"""The worker-writability check must report *why* it did not look.

On 2026-08-23 a worker went straight for the right three files, was denied on
every one, burned 1.07M tokens probing why and hit its ceiling -- while prepare
reported a green cold gate and run exited 0. Nothing in the receipt said "the
worker could not write", because nothing had asked.

``worker_can_write_workspace`` now asks. But it reports ``(bool, str)``, the
caller uses the bool to raise or not, and the string is discarded on success.
So a check that was *skipped* and a check that *passed* leave exactly the same
trace: nothing.

That is not hypothetical. ``--worker-user`` defaults to
``os.environ.get("AGENTOPS_WORKER_USER")``. Devbox's agent login shell exports
it; the workstation does not. So on the workstation ``worker_user`` is ``None``,
the function returns ``True`` on its first line -- "no worker user: writes
happen as the coordinator" -- and never reaches the group check or the sudo
probe. The suite was green there for two weeks without exercising the probe
once, on a host that has the ``agentworker`` user and working passwordless sudo
to it. Whether the containment check runs is decided by an unexported variable
in whichever shell invoked it, and nothing anywhere says so.

L-2b already solved this class for the read-trace: it reports
``"skipped:untraced"`` and never ``true``, so "did not look" cannot be read as
"looked and was fine". This oracle gives the writability check the same
property, through a seam that reports a status alongside the verdict::

    def assess_worker_workspace_write(workspace, worker_user) -> dict
        {"writable": bool, "status": str, "detail": str}

The load-bearing rule, and the single most important assertion in this file:
**``status`` is ``"probed"`` only when the sudo probe actually ran and returned
success.** Every other path names why it did not. And the assessment must reach
the prepare receipt under ``worker_writability``, so a dispatch whose
containment check never ran is readable as such from the artifact alone, months
later, by someone who was not there.

``worker_can_write_workspace`` may stay as a thin wrapper or disappear; nothing
here pins it either way.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"

ALLOWED_STATUSES = {
    "probed",
    "denied",
    "static-only",
    "skipped:no-worker-user",
    "skipped:probe-unavailable",
    "skipped:probe-not-permitted",
}

WORKER = "agentworker-fixture"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# hybrid_dispatch.py is large; import it once at module scope.
dispatch = _load_module("hybrid_dispatch_writability_subject", SCRIPTS / "hybrid_dispatch.py")


def _manifest() -> dict:
    return {
        "repo_id": "example",
        "scope": {"allowed_path_roots": ["src/", "tests/"]},
        "hybrid": {
            "enabled": True,
            "worker_routes": ["mechanical_bulk"],
            # Green on purpose: this file is about the writability trace, not
            # about the cold gate's colour.
            "commands": {"example.tests": "true"},
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
        "sprint_item": {
            "ref": "example#42",
            "claim_id": 7,
            "claim_actor": "coordinator/claude-code",
        },
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


class _AssessMixin(unittest.TestCase):
    """Shared fixture: a real directory, and monkeypatching that is restored.

    A test cannot create users or invoke real sudo, so the identity-shaped
    pieces -- ``worker_shared_gid`` and the ``sudo`` call -- are patched inside
    the loaded module. The *filesystem* facts are real: a real temp directory
    with real modes, so the static half of the check is exercised rather than
    simulated.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(os.path.realpath(self.tmp.name)) / "workspace"
        self.workspace.mkdir()
        # Group-shared and group-writable: the state the static check demands,
        # so any denial in these tests comes from what the test set up and not
        # from an accident of the fixture.
        os.chmod(self.workspace, 0o2775)
        self.gid = self.workspace.stat().st_gid
        self.patch("worker_shared_gid", lambda worker_user: self.gid)
        self.probe_calls: list[list[str]] = []
        self.which_calls: list[str] = []

    # -- patching -----------------------------------------------------------
    def patch(self, attr: str, value) -> None:
        original = getattr(dispatch, attr)
        setattr(dispatch, attr, value)
        self.addCleanup(setattr, dispatch, attr, original)

    def patch_subprocess_run(self, fake) -> None:
        original = dispatch.subprocess.run
        dispatch.subprocess.run = fake
        self.addCleanup(setattr, dispatch.subprocess, "run", original)

    def patch_which(self, fake) -> None:
        original = dispatch.shutil.which
        dispatch.shutil.which = fake
        self.addCleanup(setattr, dispatch.shutil, "which", original)

    def stub_probe(self, returncode: int = 0, stderr: str = "", raises=None) -> None:
        """Stand in for the ``sudo ... test -w`` probe and record that it ran."""

        def fake_run(argv, **kwargs):
            self.probe_calls.append(list(argv))
            if raises is not None:
                raise raises
            return subprocess.CompletedProcess(list(argv), returncode, "", stderr)

        self.patch_subprocess_run(fake_run)

        def fake_which(name, path=None):
            self.which_calls.append(name)
            return "/usr/bin/test"

        self.patch_which(fake_which)

    # -- assertions ---------------------------------------------------------
    def assess(self, workspace=None, worker_user: str | None = WORKER) -> dict:
        assess = getattr(dispatch, "assess_worker_workspace_write", None)
        self.assertIsNotNone(
            assess,
            "hybrid_dispatch must expose assess_worker_workspace_write(workspace, worker_user)",
        )
        result = assess(self.workspace if workspace is None else workspace, worker_user)
        self.assertIsInstance(result, dict, f"assessment must be a dict, got {result!r}")
        self.assertEqual(
            set(result),
            {"writable", "status", "detail"},
            f"assessment must carry exactly writable/status/detail, got {sorted(result)}",
        )
        self.assertIn(result["status"], ALLOWED_STATUSES, f"unknown status in {result!r}")
        self.assertIsInstance(result["writable"], bool, f"writable must be a bool: {result!r}")
        self.assertIsInstance(result["detail"], str, f"detail must be a str: {result!r}")
        self.assertTrue(
            result["detail"].strip(),
            f"detail must carry the human-readable reason, got {result!r}",
        )
        self.assertEqual(
            result["writable"],
            result["status"] != "denied",
            f"'denied' is the only status that withholds writability: {result!r}",
        )
        return result

    def assertStatus(self, result: dict, expected: str) -> None:
        self.assertEqual(result["status"], expected, f"expected {expected!r}: {result!r}")

    def assertProbeStatus(self, result: dict, expected: str) -> None:
        """Assert a probe-dependent mapping.

        ``static-only`` is available to an implementation that satisfies the
        static group/mode check and deliberately declines to probe, so it is
        accepted here -- but *only* when no probe was in fact attempted, and
        never in place of ``probed``.
        """
        if result["status"] == "static-only":
            self.assertEqual(
                self.probe_calls,
                [],
                "an implementation reporting 'static-only' must not have run the probe: "
                f"{result!r} after {self.probe_calls!r}",
            )
            self.assertTrue(result["writable"], f"static-only is never a denial: {result!r}")
            return
        self.assertStatus(result, expected)


class NoWorkerUserTests(_AssessMixin):
    """The workstation case: the whole check is short-circuited by an unexported
    environment variable, and today that is indistinguishable from a pass."""

    def test_no_worker_user_is_reported_as_skipped_not_as_a_pass(self) -> None:
        self.stub_probe(returncode=0)

        result = self.assess(worker_user=None)

        self.assertStatus(result, "skipped:no-worker-user")
        self.assertTrue(result["writable"], "a check that could not run is never a denial")

    def test_no_worker_user_never_reports_probed(self) -> None:
        """The regression this row buys.

        This is the exact shape of the 2026-08-23 silence: the containment
        check did not run, and nothing said so. An implementation that reports
        ``"probed"`` here -- or that reports anything a reader could mistake for
        "we looked and it was fine" -- reintroduces it.
        """
        self.stub_probe(returncode=0)

        result = self.assess(worker_user=None)

        self.assertNotEqual(
            result["status"],
            "probed",
            "'probed' claims the sudo probe ran and succeeded; with no worker user "
            f"it cannot have: {result!r}",
        )
        self.assertEqual(
            self.probe_calls, [], "no worker user means no probe was attempted at all"
        )
        self.assertTrue(
            result["status"].startswith("skipped:"),
            f"a check that did not run must name itself skipped: {result!r}",
        )

    def test_empty_worker_user_is_the_same_skip(self) -> None:
        # argparse hands through whatever the environment held; an exported but
        # empty AGENTOPS_WORKER_USER is the same "nobody asked" state.
        self.stub_probe(returncode=0)

        self.assertStatus(self.assess(worker_user=""), "skipped:no-worker-user")


class StaticDenialTests(_AssessMixin):
    """The static half needs no privileges and is the decisive check: the group
    must be one the worker is in, and the group-write bit must be set. That is
    exactly the state that failed on devbox, and it is knowable by stat alone."""

    def test_unstattable_workspace_is_denied(self) -> None:
        self.stub_probe(returncode=0)

        result = self.assess(workspace=self.workspace / "does-not-exist")

        self.assertStatus(result, "denied")
        self.assertFalse(result["writable"])

    def test_no_shared_group_is_denied(self) -> None:
        # No mode can make the workspace writable by a user who shares no group
        # with this process.
        self.patch("worker_shared_gid", lambda worker_user: None)
        self.stub_probe(returncode=0)

        result = self.assess()

        self.assertStatus(result, "denied")
        self.assertFalse(result["writable"])

    def test_wrong_group_is_denied(self) -> None:
        # The measured failure: workspace 0775 but owned by a group the worker
        # is not in, so the group-write bit is inert and every edit inside the
        # worker's own workspace fails PermissionDenied.
        self.patch("worker_shared_gid", lambda worker_user: self.gid + 1)
        self.stub_probe(returncode=0)

        result = self.assess()

        self.assertStatus(result, "denied")
        self.assertFalse(result["writable"])

    def test_not_group_writable_is_denied(self) -> None:
        os.chmod(self.workspace, 0o755)
        self.stub_probe(returncode=0)

        result = self.assess()

        self.assertStatus(result, "denied")
        self.assertFalse(result["writable"])

    def test_static_denials_never_report_probed(self) -> None:
        """A denial found by stat has not probed anything, and must not say it
        has -- the status names the evidence, not merely the verdict."""
        for name, setup in (
            ("no shared group", lambda: self.patch("worker_shared_gid", lambda u: None)),
            ("wrong group", lambda: self.patch("worker_shared_gid", lambda u: self.gid + 1)),
            ("not group-writable", lambda: os.chmod(self.workspace, 0o755)),
        ):
            with self.subTest(case=name):
                setup()
                self.stub_probe(returncode=0)
                result = self.assess()
                self.assertNotEqual(result["status"], "probed", f"{name}: {result!r}")
                # restore for the next subtest
                os.chmod(self.workspace, 0o2775)


class ProbeUnavailableTests(_AssessMixin):
    """A probe that cannot run is *skipped*, never a denial: refusing to
    dispatch because we lack the rights to ask would fail the run for a reason
    that has nothing to do with the workspace. But it must still say so."""

    def test_missing_test_binary_is_skipped_probe_unavailable(self) -> None:
        self.patch_subprocess_run(
            lambda argv, **kw: self.fail(f"the probe must not run without a test binary: {argv}")
        )
        self.patch_which(lambda name, path=None: None)

        result = self.assess()

        self.assertProbeStatus(result, "skipped:probe-unavailable")
        self.assertTrue(result["writable"])
        self.assertNotEqual(result["status"], "probed", f"the probe never ran: {result!r}")

    def test_probe_raising_oserror_is_skipped_probe_unavailable(self) -> None:
        self.stub_probe(raises=OSError("sudo: no such file"))

        result = self.assess()

        self.assertProbeStatus(result, "skipped:probe-unavailable")
        self.assertTrue(result["writable"])
        self.assertNotEqual(result["status"], "probed", f"the probe raised: {result!r}")

    def test_probe_timing_out_is_skipped_probe_unavailable(self) -> None:
        self.stub_probe(raises=subprocess.TimeoutExpired(cmd=["sudo"], timeout=30))

        result = self.assess()

        self.assertProbeStatus(result, "skipped:probe-unavailable")
        self.assertTrue(result["writable"])
        self.assertNotEqual(result["status"], "probed", f"the probe timed out: {result!r}")


class ProbeNotPermittedTests(_AssessMixin):
    """"sudo would not let me ask" is not "the answer is no". The coordinator
    may run only a narrow allowlist as the worker -- on devbox opencode and
    ``test`` -- so a refusal is a skip. It is still not a pass."""

    REFUSALS = (
        "sudo: a password is required",
        "Sorry, user coordinator is not allowed to execute '/usr/bin/test -w /w' as agentworker.",
        "Sorry, user coordinator may not run sudo on devbox.",
    )

    def test_refused_probe_is_skipped_probe_not_permitted(self) -> None:
        for stderr in self.REFUSALS:
            with self.subTest(stderr=stderr):
                self.stub_probe(returncode=1, stderr=stderr)

                result = self.assess()

                self.assertProbeStatus(result, "skipped:probe-not-permitted")
                self.assertTrue(result["writable"], "lacking the right to ask is not a denial")

    def test_refused_probe_never_reports_probed(self) -> None:
        """The probe ran but was turned away at the door: it produced no
        evidence about the workspace, so it cannot be reported as evidence."""
        self.stub_probe(returncode=1, stderr="sudo: a password is required")

        result = self.assess()

        self.assertNotEqual(
            result["status"],
            "probed",
            f"a refused probe answered nothing about the workspace: {result!r}",
        )

    def test_refusal_classification_goes_through_the_module_seam(self) -> None:
        # Whatever markers _probe_was_refused recognises, the assessment must
        # ask it rather than deciding on its own -- otherwise the two meanings
        # of a non-zero exit drift apart again.
        self.patch("_probe_was_refused", lambda stderr: True)
        self.stub_probe(returncode=7, stderr="an unfamiliar sudo dialect")

        result = self.assess()

        self.assertProbeStatus(result, "skipped:probe-not-permitted")
        self.assertTrue(result["writable"])


class ProbeAnsweredTests(_AssessMixin):
    """The probe ran and answered. These are the only two statuses that report
    evidence about the workspace itself."""

    def test_probe_saying_no_is_denied(self) -> None:
        self.patch("_probe_was_refused", lambda stderr: False)
        self.stub_probe(returncode=1, stderr="test: /w: Permission denied")

        result = self.assess()

        self.assertStatus(result, "denied")
        self.assertFalse(result["writable"])
        self.assertTrue(self.probe_calls, "the probe must have run to return this answer")

    def test_probe_succeeding_is_the_only_way_to_report_probed(self) -> None:
        self.stub_probe(returncode=0)

        result = self.assess()

        self.assertTrue(self.probe_calls, "the sudo probe must actually have been invoked")
        self.assertStatus(result, "probed")
        self.assertTrue(result["writable"])

    def test_probed_names_the_worker_in_its_detail(self) -> None:
        # The detail carries the same information the discarded second return
        # value did -- which named the worker -- so the receipt is readable
        # without the code beside it.
        self.stub_probe(returncode=0)

        result = self.assess()

        self.assertIn(WORKER, result["detail"], result["detail"])


class StatusVocabularyTests(_AssessMixin):
    """Cross-cutting invariants over every branch at once."""

    def _scenarios(self):
        return {
            "no-worker-user": (lambda: self.stub_probe(0), {"worker_user": None}),
            "no-shared-group": (
                lambda: (self.patch("worker_shared_gid", lambda u: None), self.stub_probe(0)),
                {},
            ),
            "wrong-group": (
                lambda: (
                    self.patch("worker_shared_gid", lambda u: self.gid + 1),
                    self.stub_probe(0),
                ),
                {},
            ),
            "not-group-writable": (
                lambda: (os.chmod(self.workspace, 0o755), self.stub_probe(0)),
                {},
            ),
            "probe-unavailable": (
                lambda: (
                    self.patch_subprocess_run(
                        lambda argv, **kw: self.fail(f"no test binary, no probe: {argv}")
                    ),
                    self.patch_which(lambda name, path=None: None),
                ),
                {},
            ),
            "probe-raised": (lambda: self.stub_probe(raises=OSError("boom")), {}),
            "probe-refused": (
                lambda: self.stub_probe(1, "sudo: a password is required"),
                {},
            ),
            "probe-denied": (
                lambda: (
                    self.patch("_probe_was_refused", lambda s: False),
                    self.stub_probe(1, "Permission denied"),
                ),
                {},
            ),
            "probed": (lambda: self.stub_probe(0), {}),
        }

    def test_every_branch_reports_a_known_status_a_reason_and_a_consistent_verdict(self) -> None:
        for name, (setup, kwargs) in self._scenarios().items():
            with self.subTest(scenario=name):
                setup()
                # assess() itself asserts: exactly three keys, status in the
                # allowed set, non-empty detail, and writable iff not denied.
                result = self.assess(**kwargs)
                if result["status"] == "static-only":
                    self.assertTrue(result["writable"], f"{name}: {result!r}")
                os.chmod(self.workspace, 0o2775)
                self.probe_calls.clear()

    def test_probed_is_reported_only_where_the_probe_actually_answered_yes(self) -> None:
        """The one assertion this whole file exists for, stated over every
        branch: no path other than a successful probe may report ``probed``."""
        for name, (setup, kwargs) in self._scenarios().items():
            if name == "probed":
                continue
            with self.subTest(scenario=name):
                setup()
                result = self.assess(**kwargs)
                self.assertNotEqual(
                    result["status"],
                    "probed",
                    f"{name} did not run a successful probe, so it may not claim one: {result!r}",
                )
                os.chmod(self.workspace, 0o2775)
                self.probe_calls.clear()


class PrepareReceiptTests(unittest.TestCase):
    """And it must reach the receipt.

    The trace belongs in the artifact, not in a discarded local. A dispatch
    whose containment check never ran must be readable as such from the receipt
    alone, months later, by someone who was not there.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(os.path.realpath(self.tmp.name))
        # 0755, matching the real worktree root /tmp/agentops-hybrid. A
        # TemporaryDirectory is 0700, which a worker user cannot traverse.
        os.chmod(root, 0o755)
        self.root = root
        self.repo = root / "repo"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "src/a.py").write_text("x\n", encoding="utf-8")
        env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@x",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@x",
        }
        for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "start"]):
            subprocess.run(
                ["git", "-C", str(self.repo), *args], check=True, env=env, capture_output=True
            )
        self.packet = _packet()
        self.packet["starting_commit"] = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.packet["worktree"]["root"] = str(root / "wt")
        (self.repo / "example.dispatch.json").write_text(
            json.dumps(_manifest()), encoding="utf-8"
        )
        self._patch("verify_live_coordinator_claim", lambda *a, **k: {"claim": "stubbed"})

    def _patch(self, attr: str, value) -> None:
        original = getattr(dispatch, attr)
        setattr(dispatch, attr, value)
        self.addCleanup(setattr, dispatch, attr, original)

    def _prepare_receipt(self, *extra_argv: str) -> tuple[int, dict]:
        packet_path = self.repo / "p.json"
        packet_path.write_text(json.dumps(self.packet), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = dispatch.main(
                [
                    "--repo-root",
                    str(self.repo),
                    "--packet",
                    str(packet_path),
                    "--agentops-root",
                    str(ROOT),
                    *extra_argv,
                    "prepare",
                ]
            )
        return code, json.loads(out.getvalue())

    def _assessment(self, receipt: dict) -> dict:
        self.assertIn(
            "worker_writability",
            receipt,
            "the prepare receipt must carry the writability assessment: "
            f"{sorted(receipt)}",
        )
        assessment = receipt["worker_writability"]
        self.assertIsInstance(assessment, dict, f"{assessment!r}")
        self.assertEqual(set(assessment), {"writable", "status", "detail"}, f"{assessment!r}")
        self.assertIn(assessment["status"], ALLOWED_STATUSES, f"{assessment!r}")
        self.assertTrue(assessment["detail"].strip(), f"{assessment!r}")
        self.assertEqual(assessment["writable"], assessment["status"] != "denied", f"{assessment!r}")
        return assessment

    def test_a_workstation_prepare_records_that_it_never_looked(self) -> None:
        """No AGENTOPS_WORKER_USER, so no worker user, so no containment check.
        This is the run that was green for two weeks without probing once. The
        receipt now says which of the two it was."""
        code, receipt = self._prepare_receipt()

        self.assertEqual(code, 0, receipt)
        self.assertEqual(receipt["stage"], "prepare")
        assessment = self._assessment(receipt)
        self.assertEqual(assessment["status"], "skipped:no-worker-user", receipt)
        self.assertTrue(assessment["writable"])
        self.assertNotEqual(
            assessment["status"],
            "probed",
            "a receipt claiming 'probed' where nothing was probed is the original defect, "
            f"written down: {assessment!r}",
        )

    def test_the_receipt_records_a_real_probe_as_probed(self) -> None:
        """The devbox case. The probe is faked at the sudo boundary only; the
        clone, the modes and the group ownership are real."""
        target = dispatch.worktree_path(self.packet)
        self._patch(
            "worker_shared_gid",
            lambda worker_user: os.stat(target).st_gid if target.exists() else None,
        )
        probe_calls: list[list[str]] = []
        real_run = dispatch.subprocess.run

        def fake_run(argv, **kwargs):
            # git and the registered cold commands still run for real; only the
            # sudo probe is stood in for, because a test cannot invoke sudo.
            if isinstance(argv, (list, tuple)) and argv and argv[0] == "sudo":
                probe_calls.append(list(argv))
                return subprocess.CompletedProcess(list(argv), 0, "", "")
            return real_run(argv, **kwargs)

        dispatch.subprocess.run = fake_run
        self.addCleanup(setattr, dispatch.subprocess, "run", real_run)

        code, receipt = self._prepare_receipt("--worker-user", WORKER)

        self.assertEqual(code, 0, receipt)
        assessment = self._assessment(receipt)
        if assessment["status"] == "static-only":
            self.assertEqual(probe_calls, [], f"static-only must not have probed: {assessment!r}")
            self.assertTrue(assessment["writable"])
        else:
            self.assertTrue(probe_calls, f"expected a sudo probe; receipt said {assessment!r}")
            self.assertEqual(assessment["status"], "probed", receipt)
            self.assertTrue(assessment["writable"])

    def test_the_receipt_distinguishes_a_skipped_probe_from_a_passed_one(self) -> None:
        """The property in one assertion: two prepares that differ only in
        whether the check could run must not produce the same receipt."""
        target = dispatch.worktree_path(self.packet)
        self._patch(
            "worker_shared_gid",
            lambda worker_user: os.stat(target).st_gid if target.exists() else None,
        )
        real_run = dispatch.subprocess.run

        def fake_run(argv, **kwargs):
            if isinstance(argv, (list, tuple)) and argv and argv[0] == "sudo":
                return subprocess.CompletedProcess(
                    list(argv), 1, "", "sudo: a password is required"
                )
            return real_run(argv, **kwargs)

        dispatch.subprocess.run = fake_run
        self.addCleanup(setattr, dispatch.subprocess, "run", real_run)

        code, receipt = self._prepare_receipt("--worker-user", WORKER)

        self.assertEqual(code, 0, receipt)
        assessment = self._assessment(receipt)
        self.assertNotEqual(
            assessment["status"],
            "probed",
            f"the probe was refused, so the receipt may not report a pass: {assessment!r}",
        )
        self.assertIn(
            assessment["status"],
            {"skipped:probe-not-permitted", "static-only"},
            f"a refused probe is a named skip: {assessment!r}",
        )
        self.assertTrue(assessment["writable"])


if __name__ == "__main__":
    unittest.main()
