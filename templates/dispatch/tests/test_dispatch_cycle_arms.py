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
