"""The driver publishes the cycle's arms, so a complete cycle stops depending on memory.

Before 2026-08-29 nothing emitted `dispatch.preflight_rejected`, `dispatch.packet.reviewed`
or `dispatch.packet.accepted`. All 23 such events in the workspace were typed by hand by
one coordinator, in one repository, on one day -- which is why sixteen of that
repository's own eighteen cycles are incomplete and no other repository has a single
complete one. The measurement was reporting how reliably someone remembered to write
prose, and reporting it as a property of the consumer.

Two arms need no judgement and are now emitted where they are already known: the prepare
stage knows it refused a packet before starting a worker, and the gate stage knows a
candidate cleared its gates and its review. The third needs a merge commit this process
cannot have, so it stays a coordinator act -- but `--accepted <commit>` makes it a
command rather than remembered prose.

See docs/assessments/dispatch-cycle-substrate-vs-consumer-2026-08-29.md.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load("hybrid_dispatch_arms_subject", SCRIPTS / "hybrid_dispatch.py")
probe = _load("dispatch_cycle_probe_reader", SCRIPTS / "dispatch_cycle_probe.py")

PACKET = {
    "task_id": "ARMS-001-smoke-r1",
    "repo_id": "test-repo",
    "starting_commit": "0" * 40,
    "sprint_item": "test-repo#1",
}


class ArmVocabularyTests(unittest.TestCase):
    def test_the_driver_and_the_probe_agree_on_the_arm_names(self) -> None:
        """One vocabulary, or the producer and the reader drift into two.

        This is the drift that made the pin worth building in the first place: two
        places holding the same list, neither comparing itself with the other.
        """
        published = set(driver.CYCLE_ARMS.values())
        readable = set(probe.REFUSAL_TYPES) | set(probe.REVIEW_TYPES) | set(probe.ACCEPT_TYPES)
        self.assertTrue(
            published <= readable,
            f"the driver publishes arms the probe cannot read: {sorted(published - readable)}",
        )

    def test_every_published_arm_maps_to_a_cycle_arm(self) -> None:
        for arm, event_type in driver.CYCLE_ARMS.items():
            self.assertIsNotNone(
                probe.arm_of(event_type), f"{arm} -> {event_type} is not a recognised arm"
            )


class PublisherResolutionTests(unittest.TestCase):
    """`auditctl` is also the Linux kernel audit tool, and resolving the wrong one loses
    the record silently -- the publisher call tolerates failure by design, so a binary
    that exits 0 without writing anything is indistinguishable from success."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self._environ = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._environ)))

    def _decoy(self) -> Path:
        """A compiled executable named auditctl: the shape that makes the real one
        undetectable, without depending on the `audit` package being installed."""
        directory = self.root / "decoy"
        directory.mkdir()
        target = directory / "auditctl"
        target.write_bytes(b"\x7fELF" + b"\x00" * 64)
        target.chmod(target.stat().st_mode | stat.S_IEXEC)
        return directory

    def _script(self, name: str) -> Path:
        directory = self.root / name
        directory.mkdir()
        target = directory / "auditctl"
        target.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IEXEC)
        return directory

    def test_a_compiled_namesake_on_path_is_skipped(self) -> None:
        ours = self._script("ours")
        os.environ["PATH"] = os.pathsep.join([str(self._decoy()), str(ours)])
        os.environ.pop("AUDITCTL_BIN", None)
        self.assertEqual(str(ours / "auditctl"), driver._auditctl_bin())

    def test_an_explicit_binary_wins(self) -> None:
        ours = self._script("explicit")
        os.environ["AUDITCTL_BIN"] = str(ours / "auditctl")
        os.environ["PATH"] = str(self._decoy())
        self.assertEqual(str(ours / "auditctl"), driver._auditctl_bin())

    def test_an_empty_explicit_binary_means_absent(self) -> None:
        os.environ["AUDITCTL_BIN"] = ""
        os.environ["PATH"] = str(self._script("ours"))
        self.assertIsNone(driver._auditctl_bin())

    def test_publishing_without_a_publisher_is_not_an_error(self) -> None:
        """The arm is evidence about the run, never part of it. A missing publisher
        must never turn a green dispatch red."""
        os.environ["AUDITCTL_BIN"] = ""
        driver._publish_arm("refused", PACKET, "no publisher here", {"driver_stage": "prepare"})


class PublishedCycleTests(unittest.TestCase):
    """The end the whole change exists for: three published arms read back as one
    complete cycle."""

    def test_three_arms_read_back_as_a_complete_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = root / "auditctl"
            shard = root / "_artifacts" / "test-repo" / "audit"
            shard.mkdir(parents=True)
            # A stand-in publisher that records exactly what the real one is asked to
            # write. The subject here is which arms the driver emits, not auditctl.
            recorder.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys, pathlib\n"
                "argv = sys.argv[1:]\n"
                "pairs = dict(zip(argv[1::2], argv[2::2]))\n"
                "event = {'type': pairs['--type'], 'summary': pairs['--summary'],\n"
                "         'metadata': json.loads(pairs['--metadata']),\n"
                "         'id': 'ad:' + pairs['--type'], 'created_at': '2026-08-29T00:00:00Z'}\n"
                f"path = pathlib.Path({str(shard / 'events-2026-08-29.ndjson')!r})\n"
                "with path.open('a') as handle:\n"
                "    handle.write(json.dumps(event) + '\\n')\n",
                encoding="utf-8",
            )
            recorder.chmod(recorder.stat().st_mode | stat.S_IEXEC)
            os.environ["AUDITCTL_BIN"] = str(recorder)
            self.addCleanup(lambda: os.environ.pop("AUDITCTL_BIN", None))

            driver._publish_arm("refused", PACKET, "refused at preflight",
                                {"worker_started": False, "no_mutation": True})
            accepted_packet = dict(PACKET, task_id="ARMS-001-smoke-r2")
            driver._publish_arm("reviewed", accepted_packet, "candidate reviewed",
                                {"merge_approved": True})
            driver._publish_arm("accepted", accepted_packet, "accepted and merged",
                                {"implementation_commit": "abc1234"})

            events = probe.load_events("test-repo", root / "_artifacts")
            cycles = probe.group_cycles(events)
            self.assertEqual(["ARMS-001-smoke"], sorted(cycles))
            self.assertTrue(
                probe.is_complete(cycles["ARMS-001-smoke"]),
                "three published arms must read back as one complete cycle",
            )
            candidate = probe.build_candidate("test-repo", "ARMS-001-smoke",
                                              cycles["ARMS-001-smoke"], root)
            for fact in (
                "cycle: an attempt was refused",
                "refusal: no mutation was made",
                "cycle: a revised attempt was independently reviewed",
                "cycle: an attempt was accepted and merged",
            ):
                self.assertIn(fact, candidate["facts"])


if __name__ == "__main__":
    unittest.main()


class FaultLabelTests(unittest.TestCase):
    """A summary line is not worth failing a dispatch over.

    `assess_cold_run` yields fault records; other paths hand back plain strings, and the
    first version of the refusal summary assumed dicts and raised `AttributeError` on a
    retry with no workspace left. The arm is evidence about the run; it must not be able
    to break the run it describes.
    """

    def test_both_fault_shapes_are_read(self) -> None:
        self.assertEqual(["unit.vet"], driver._fault_labels([{"command_id": "unit.vet"}]))
        self.assertEqual(["unit.vet"], driver._fault_labels(["unit.vet"]))
        self.assertEqual(
            ["a", "b"], driver._fault_labels([{"command_id": "b"}, "a", {"command_id": "b"}])
        )

    def test_an_unreadable_fault_is_skipped_rather_than_guessed_at(self) -> None:
        self.assertEqual([], driver._fault_labels([None, 7, {}, {"unrelated": "x"}]))
        self.assertEqual([], driver._fault_labels(None))


# --- the post-inference refusal ----------------------------------------------------
#
# The arm that was missing, and the one the whole cycle turns on. A refusal before a
# worker starts is free; a refusal after one has run and spent is the only evidence
# that a guard was worth its cost -- and it was the single arm with no producer. Every
# post-inference stop returned 2, 3 or 4 and published nothing, so the smallest complete
# cycle on record (bindery-core ERM-005, a churn stop at worker exit 4 followed four
# minutes later by a merge) could not be reproduced by this driver at all.

SCENARIO = ROOT / "templates/dispatch/acceptance/dispatch-cycle.scenario.json"

RUN_PACKET = {
    "task_id": "ARMS-002-post-inference-r2",
    "repo_id": "test-repo",
    "route": "mechanical",
    "starting_commit": "1" * 40,
    "sprint_item": "test-repo#2",
    "limits": {"max_cost_usd": 5.0, "soft_token_ceiling": 100, "hard_token_ceiling": 1000},
    "protected_paths": [],
    "writable_patch_paths": ["src/**"],
}

CLEAN_SPEND = {
    "cost_usd": 0.12,
    "tokens": 12543,
    "cost_reported": True,
    "within_cap": True,
    "soft_token_ceiling_exceeded": False,
    "within_hard_token_ceiling": True,
}


def _transcript(churn: dict | None = None, exit_code: int = 0, mutations: int = 1) -> dict:
    return {
        "argv": ["opencode", "run"],
        "exit_code": exit_code,
        "stdout": "",
        "stderr_tail": "",
        "session_id": "ses_test",
        "churn_stop": churn,
        "churn_metrics": {"completed_mutations": mutations},
        "command_evidence": {"ungranted_completed": 0, "exact_execution_proven": True},
    }


class PostInferenceStopTests(unittest.TestCase):
    """Which stops are refusals, and which of them the exit code could have told us.

    Three are already exit codes. The churn stop is not: it leaves the run stage at 0,
    which is why reading the refusal off the return value would have missed the exact
    case ERM-005 is made of.
    """

    def test_a_clean_run_is_not_a_refusal(self) -> None:
        self.assertIsNone(
            driver.post_inference_stop([], False, CLEAN_SPEND, _transcript())
        )

    def test_a_churn_stop_is_a_refusal_even_though_the_run_exits_zero(self) -> None:
        stop = driver.post_inference_stop(
            [], False, CLEAN_SPEND,
            _transcript({"reason": "churn_repeated_reads", "detail": "fixtures.go x3"},
                        exit_code=4, mutations=0),
        )
        self.assertEqual(("churn_repeated_reads", True), stop)

    def test_a_breach_is_a_refusal_that_no_revised_packet_answers(self) -> None:
        self.assertEqual(
            ("containment_breach", False),
            driver.post_inference_stop([" M docs/x.md"], False, CLEAN_SPEND, _transcript()),
        )
        self.assertEqual(
            ("containment_breach", False),
            driver.post_inference_stop([], True, CLEAN_SPEND, _transcript()),
        )

    def test_overspend_is_a_refusal_a_revised_packet_answers(self) -> None:
        for key in ("within_cap", "within_hard_token_ceiling"):
            with self.subTest(key):
                spend = dict(CLEAN_SPEND, **{key: False})
                self.assertEqual(
                    ("budget_exceeded", True),
                    driver.post_inference_stop([], False, spend, _transcript()),
                )

    def test_a_breach_outranks_an_overspend(self) -> None:
        """Both true is triage, not retry. Naming it budget_exceeded would tell an
        operator to revise the packet and dispatch again into an escaped boundary."""
        spend = dict(CLEAN_SPEND, within_cap=False)
        self.assertEqual(
            ("containment_breach", False),
            driver.post_inference_stop([" M docs/x.md"], False, spend, _transcript()),
        )


class GuardedPublisherTests(unittest.TestCase):
    """The arm is evidence about the run, never part of it -- including when the arm's
    own metadata is what is broken.

    `_publish_arm` cannot promise this alone: its summary and metadata are built at the
    call site, before it is entered. `_fault_labels` exists because the first refusal
    summary assumed a fault shape and raised on a retry, and the post-inference arms
    read a worker transcript and a gate report, which are richer and easier to get wrong.
    """

    def test_a_builder_that_raises_publishes_nothing_and_raises_nothing(self) -> None:
        def explode():
            raise KeyError("churn_metrics")

        driver._publish_arm_guarded("rejected", RUN_PACKET, explode)


class _RecordingPublisher:
    """A stand-in auditctl that records what the driver asked it to write.

    The real one is never used here, and must not be: a test that published into the
    workspace's own store would be adding evidence about runs that never happened.
    """

    def __init__(self, root: Path, repo_id: str = "test-repo") -> None:
        self.artifacts = root / "_artifacts"
        self.log = self.artifacts / repo_id / "audit" / "events-2026-08-30.ndjson"
        self.log.parent.mkdir(parents=True)
        self.binary = root / "auditctl"
        # Written in the store's own shape, so the same recording is both "what the
        # driver asked to publish" and "what a reader would later find" -- a test that
        # asserted only the first could pass while the record stayed unreadable. The
        # sequence number stands in for a clock the probe orders arms by.
        self.binary.write_text(
            "#!/usr/bin/env python3\n"
            "import json, sys, pathlib\n"
            "argv = sys.argv[1:]\n"
            "pairs = dict(zip(argv[1::2], argv[2::2]))\n"
            f"path = pathlib.Path({str(self.log)!r})\n"
            "seq = len(path.read_text().splitlines()) if path.exists() else 0\n"
            "with path.open('a') as handle:\n"
            "    handle.write(json.dumps({'type': pairs['--type'],\n"
            "        'summary': pairs['--summary'],\n"
            "        'metadata': json.loads(pairs['--metadata']),\n"
            "        'id': 'ad:%02d' % seq, 'origin_seq': seq,\n"
            "        'created_at': '2026-08-30T00:00:%02dZ' % seq}) + '\\n')\n",
            encoding="utf-8",
        )
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IEXEC)

    def published(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines() if line.strip()]


class _StageHarness(unittest.TestCase):
    """Drives `main` through one stage with its I/O replaced.

    Rule 11: the subject is the wiring in `main`, so everything it calls that touches
    git, a worker or a network is replaced. A pure-function test cannot pin this half --
    `post_inference_stop` can be perfectly right while nothing calls it.
    """

    POLICY = {"routes": {"mechanical": {"harness_model": "test/model"}},
              "dispositions": ["candidate"]}

    def setUp(self) -> None:
        import contextlib
        from unittest import mock

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.worktree = self.root / "worktree"
        self.worktree.mkdir()
        self.packet_path = self.root / "packet.json"
        self.packet_path.write_text(json.dumps(RUN_PACKET), encoding="utf-8")
        config = self.root / "worker.json"
        config.write_text("{}", encoding="utf-8")

        self.publisher = _RecordingPublisher(self.root)
        self._environ = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._environ)))
        os.environ["AUDITCTL_BIN"] = str(self.publisher.binary)

        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (
            ("load_manifest", {"hybrid": {}}),
            ("load_policy", self.POLICY),
            ("validate_packet", {}),
            ("load_worker_config_path", config),
            ("build_overlay", {}),
            ("overlay_hash", "sha256:overlay"),
            ("worktree_path", self.worktree),
            ("verify_live_coordinator_claim", {}),
            ("_receipt", {}),
            ("_emit", None),
        ):
            self.stack.enter_context(
                mock.patch.object(driver, name, mock.Mock(return_value=value))
            )

    def _main(self, *extra: str) -> int:
        return driver.main([
            "--repo-root", str(self.root),
            "--packet", str(self.packet_path),
            "--agentops-root", str(self.root),
            *extra,
        ])

    def _types(self) -> list[str]:
        return [event["type"] for event in self.publisher.published()]


class RunStageArmTests(_StageHarness):
    """Every post-inference stop in the run stage now leaves a record, and none of them
    changed what the stage returns."""

    def _run(self, *, breach=(), ungranted=0, spend=None, transcript=None, no_audit=False) -> int:
        from unittest import mock

        seen = [[], list(breach)]
        self.stack.enter_context(mock.patch.object(driver, "worker_cannot_write",
                                                   mock.Mock(return_value=True)))
        self.stack.enter_context(mock.patch.object(driver, "coordinator_tree_state",
                                                   mock.Mock(side_effect=seen)))
        self.stack.enter_context(mock.patch.object(
            driver, "dispatch_worker",
            mock.Mock(return_value=transcript or _transcript())))
        self.stack.enter_context(mock.patch.object(driver, "stream_events",
                                                   mock.Mock(return_value=[])))
        self.stack.enter_context(mock.patch.object(
            driver, "command_evidence_for",
            mock.Mock(return_value={"ungranted_completed": ungranted,
                                    "exact_execution_proven": True})))
        self.stack.enter_context(mock.patch.object(
            driver, "worker_spend", mock.Mock(return_value=spend or CLEAN_SPEND)))
        return self._main(*(["--no-audit"] if no_audit else []), "run")

    def test_a_clean_run_publishes_no_refusal(self) -> None:
        self.assertEqual(0, self._run())
        self.assertEqual([], self._types())

    def test_a_churn_stop_publishes_the_arm_although_the_stage_exits_zero(self) -> None:
        """The case ERM-005 is made of, and the reason the exit code is not the signal:
        this run is a success by return value and a refusal by fact."""
        code = self._run(transcript=_transcript(
            {"reason": "churn_repeated_reads", "detail": "fixtures.go read 3 times (limit 2)"},
            exit_code=4, mutations=0))
        self.assertEqual(0, code)
        self.assertEqual(["dispatch.packet.rejected"], self._types())
        metadata = self.publisher.published()[0]["metadata"]
        self.assertEqual("churn_repeated_reads", metadata["stop_reason"])
        self.assertIs(True, metadata["worker_started"])
        self.assertIs(True, metadata["no_mutation"])
        self.assertIs(True, metadata["retry_required"])
        self.assertIs(False, metadata["candidate_present"])
        self.assertIs(True, metadata["coordinator_tree_untouched"])
        self.assertEqual(4, metadata["worker_exit_code"])
        self.assertEqual("ses_test", metadata["session_id"])
        self.assertEqual(12543, metadata["reported_tokens"])

    def test_a_containment_breach_publishes_and_still_exits_three(self) -> None:
        code = self._run(breach=[" M docs/x.md"])
        self.assertEqual(3, code)
        metadata = self.publisher.published()[0]["metadata"]
        self.assertEqual("containment_breach", metadata["stop_reason"])
        self.assertIs(False, metadata["retry_required"])
        self.assertIs(False, metadata["coordinator_tree_untouched"])

    def test_an_overspend_publishes_and_still_exits_four(self) -> None:
        code = self._run(spend=dict(CLEAN_SPEND, within_cap=False))
        self.assertEqual(4, code)
        self.assertEqual("budget_exceeded",
                         self.publisher.published()[0]["metadata"]["stop_reason"])

    def test_no_audit_still_stops_the_run(self) -> None:
        """`--no-audit` silences the evidence, never the verdict."""
        code = self._run(spend=dict(CLEAN_SPEND, within_cap=False), no_audit=True)
        self.assertEqual(4, code)
        self.assertEqual([], self._types())

    def test_a_broken_publisher_cannot_turn_a_refusal_into_a_pass(self) -> None:
        os.environ["AUDITCTL_BIN"] = ""
        self.assertEqual(3, self._run(breach=[" M docs/x.md"]))


class GateStageArmTests(_StageHarness):
    """Red gates are a refusal. A missing review record is not -- and telling them apart
    is what keeps the stream free of refusals nobody made."""

    GREEN = {"diff-nonempty": True, "registered-commands-green": True}
    RED = {"diff-nonempty": False, "registered-commands-green": False}

    def _gate(self, gates, *, touched, review_class=None) -> int:
        from unittest import mock

        self.stack.enter_context(mock.patch.object(driver, "post_gates", mock.Mock(
            return_value={"gates": gates, "passed": all(gates.values()),
                          "touched_paths": touched, "out_of_scope_paths": [],
                          "protected_path_hits": [], "command_results": []})))
        self.stack.enter_context(mock.patch.object(
            driver, "self_candidate_class", mock.Mock(return_value=review_class)))
        return self._main("gate")

    def test_red_gates_publish_the_refusal_and_exit_two(self) -> None:
        self.assertEqual(2, self._gate(self.RED, touched=[]))
        self.assertEqual(["dispatch.packet.rejected"], self._types())
        metadata = self.publisher.published()[0]["metadata"]
        self.assertEqual("post_gates_red", metadata["stop_reason"])
        self.assertIs(True, metadata["no_mutation"])
        self.assertIs(False, metadata["candidate_present"])
        self.assertEqual(["diff-nonempty", "registered-commands-green"],
                         metadata["failed_gates"])

    def test_a_pending_review_is_not_a_refusal(self) -> None:
        """Green gates with no review record exits 2 as well, but nothing was refused --
        the coordinator has not looked yet. Publishing here would let any cycle show a
        refusal simply by being invoked without --review-record."""
        self.assertEqual(2, self._gate(self.GREEN, touched=["src/a.py"]))
        self.assertEqual([], self._types())

    def test_a_candidate_still_publishes_only_the_reviewed_arm(self) -> None:
        self.assertEqual(0, self._gate(self.GREEN, touched=["src/a.py"],
                                       review_class="mechanical"))
        self.assertEqual(["dispatch.packet.reviewed"], self._types())


class ScenarioCheckTests(unittest.TestCase):
    """`the-refusal-was-paid-for` must fail against what the driver did yesterday.

    A check added after the behaviour it describes scores the implementation that
    produced it. This one is built the other way round: the cycle below is the best
    shape today's driver could reach -- a preflight refusal, a worker that ran and
    spent and left nothing, then a reviewed and merged retry -- and every other check
    in the scenario passes on it while the paid refusal is invisible.
    """

    def _check(self, name: str) -> dict:
        scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
        return next(check for check in scenario["checks"] if check["id"] == name)

    def _coverage(self, candidate: dict, name: str) -> float:
        """`required_fact_coverage` as the harness reports it: N/M required facts.

        M is the scenario's own declared fact list, so it is fixed at 2 whatever the
        candidate contains. A check whose denominator came from the candidate's own
        refusals would score 0/0 on a cycle with no refusal -- the vacuous pass that
        `_ratio(0, 0)` handed out until it was fixed, and the one shape this check
        must never reward.
        """
        facts = self._check(name)["params"]["facts"]
        return len([fact for fact in facts if fact in candidate["facts"]]) / len(facts)

    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.publisher = _RecordingPublisher(self.root)
        self._environ = dict(os.environ)
        self.addCleanup(lambda: (os.environ.clear(), os.environ.update(self._environ)))
        os.environ["AUDITCTL_BIN"] = str(self.publisher.binary)

    def _candidate(self) -> dict:
        events = probe.load_events("test-repo", self.publisher.artifacts)
        cycles = probe.group_cycles(events)
        self.assertEqual(["ARMS-003-paid"], sorted(cycles))
        return probe.build_candidate("test-repo", "ARMS-003-paid",
                                     cycles["ARMS-003-paid"], self.root)

    def _publish_the_arms_the_old_driver_could(self) -> None:
        driver._publish_arm(
            "refused", dict(RUN_PACKET, task_id="ARMS-003-paid-r1"),
            "ARMS-003 r1 refused at preflight: unit.vet",
            {"driver_stage": "prepare", "packet_status": "unfit", "worker_started": False,
             "no_mutation": True, "starting_commit": "1" * 40, "cold_faults": ["unit.vet"]},
        )
        driver._publish_arm(
            "reviewed", dict(RUN_PACKET, task_id="ARMS-003-paid-r3"),
            "ARMS-003 r3 candidate cleared its gates and review",
            {"driver_stage": "gate", "starting_commit": "1" * 40,
             "review_mode": "independent-record", "merge_approved": True},
        )
        driver._publish_arm(
            "accepted", dict(RUN_PACKET, task_id="ARMS-003-paid-r3"),
            "ARMS-003 r3 accepted and merged as abc1234",
            {"driver_stage": "receipt", "implementation_commit": "abc1234",
             "starting_commit": "1" * 40, "merge_approved": True},
        )

    def test_the_check_fails_on_the_best_cycle_the_old_driver_could_produce(self) -> None:
        self._publish_the_arms_the_old_driver_could()
        candidate = self._candidate()
        # The cycle reads as complete, and that is the point: nothing else in the
        # scenario notices that the only refusal it can show cost nothing.
        self.assertEqual(1.0, self._coverage(candidate, "cycle-is-complete"))
        self.assertEqual(1.0, self._coverage(candidate, "refusal-cost-no-inference"))
        self.assertEqual(0.0, self._coverage(candidate, "the-refusal-was-paid-for"))
        self.assertTrue(self._check("the-refusal-was-paid-for")["hard_gate"])

    def test_a_cycle_with_no_refusal_at_all_scores_zero_and_not_zero_over_zero(self) -> None:
        """The vacuous pass, tried directly. An empty subject must be a failure, not an
        undefined ratio that rounds to 1.0."""
        driver._publish_arm(
            "reviewed", dict(RUN_PACKET, task_id="ARMS-003-paid-r3"),
            "reviewed", {"merge_approved": True})
        self.assertEqual(0.0, self._coverage(self._candidate(), "the-refusal-was-paid-for"))

    def test_a_candidate_that_says_nothing_fails_rather_than_passes(self) -> None:
        """The second trap. A forbidden-shaped gate -- 'the candidate must not say no
        worker ran' -- is satisfied by silence, and silence is exactly what the old
        driver produced. The requirement is positive, so silence scores zero."""
        self._publish_the_arms_the_old_driver_could()
        candidate = self._candidate()
        for fact in self._check("the-refusal-was-paid-for")["params"]["facts"]:
            self.assertNotIn(fact, candidate["facts"])
            self.assertNotIn(fact.replace("was refused", "was not refused"),
                             candidate["facts"])

    def test_the_check_passes_once_the_driver_publishes_the_post_inference_arm(self) -> None:
        driver._publish_arm(
            "refused", dict(RUN_PACKET, task_id="ARMS-003-paid-r1"),
            "ARMS-003 r1 refused at preflight: unit.vet",
            {"driver_stage": "prepare", "packet_status": "unfit", "worker_started": False,
             "no_mutation": True, "starting_commit": "1" * 40, "cold_faults": ["unit.vet"]},
        )
        # The arm that did not exist: the ERM-005 shape, built by the driver's own
        # run-stage publish rather than by this test's idea of it.
        harness = RunStageArmTests("test_a_churn_stop_publishes_the_arm_although_the_stage_exits_zero")
        harness.setUp()
        harness.publisher = self.publisher
        os.environ["AUDITCTL_BIN"] = str(self.publisher.binary)
        harness.packet_path.write_text(
            json.dumps(dict(RUN_PACKET, task_id="ARMS-003-paid-r2")), encoding="utf-8")
        self.assertEqual(0, harness._run(transcript=_transcript(
            {"reason": "churn_repeated_reads", "detail": "fixtures.go read 3 times (limit 2)"},
            exit_code=4, mutations=0)))
        harness.doCleanups()
        os.environ["AUDITCTL_BIN"] = str(self.publisher.binary)

        driver._publish_arm(
            "reviewed", dict(RUN_PACKET, task_id="ARMS-003-paid-r3"),
            "ARMS-003 r3 candidate cleared its gates and review",
            {"driver_stage": "gate", "starting_commit": "1" * 40,
             "review_mode": "independent-record", "merge_approved": True},
        )
        driver._publish_arm(
            "accepted", dict(RUN_PACKET, task_id="ARMS-003-paid-r3"),
            "ARMS-003 r3 accepted and merged as abc1234",
            {"driver_stage": "receipt", "implementation_commit": "abc1234",
             "starting_commit": "1" * 40, "merge_approved": True},
        )

        candidate = self._candidate()
        self.assertEqual(1.0, self._coverage(candidate, "the-refusal-was-paid-for"))
        self.assertEqual(1.0, self._coverage(candidate, "cycle-is-complete"))
        # Still one arm per step, in order: the second refusal is a second refusal,
        # not a second kind of thing the scenario has to be taught about.
        self.assertEqual(
            ["cycle.refused", "cycle.refused", "cycle.reviewed", "cycle.accepted"],
            [step["tool"] for step in candidate["trajectory"]],
        )
