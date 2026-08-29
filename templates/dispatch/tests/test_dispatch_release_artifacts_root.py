"""Coordinator-authored oracle for spec row M-6b, reduced.

M-6b once required this driver to default ``AUDITCTL_ARTIFACTS_ROOT`` from
``templates/dispatch/artifacts-root.default``, so that the Python half and the
bash half read one source instead of two literals.

That requirement is retired, not weakened. auditctl 0.1.4 made the root default
to the repository auditctl itself resolves, and an explicit value may only
confirm that resolution rather than redirect it; 0.1.5 is what runs on every
publishing host. A driver that runs in whichever repository the packet targets
therefore cannot improve on the publisher's answer -- it can only replace a
correct root with the name of one repository, which is exactly the misrouting
this row's data file was introduced to contain.

So the property under test is now the opposite one: the driver decides nothing
about where its evidence lands, and an escalation is still recorded when nobody
sets a root at all.

  M-6b/1  the driver sets no artifacts root, by any route
  M-6b/2  no root literal is left in the driver
  M-6b/3  an escalation is recorded with the variable unset, and unset it stays
  M-6b/4  an inherited root is passed through untouched -- that is a repo .envrc's
          business, and confirming it is auditctl's job, not this driver's
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding, so the
# cache is switched off before anything is imported.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
DRIVER_SRC = SCRIPTS / "dispatch_release.py"

ENV_VAR = "AUDITCTL_ARTIFACTS_ROOT"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_under_test", DRIVER_SRC)


class FakeRunner:
    """Records the command and the environment the driver handed the publisher."""

    def __init__(self, auditctl_bin: str):
        self.auditctl_bin = auditctl_bin
        self.calls: list[tuple[list[str], Path | None, str | None]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((cmd, cwd, os.environ.get(ENV_VAR)))

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        return Completed()


class ArtifactsRootIsThePublishersDecision(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.auditctl = self.tmp / "auditctl"
        self.auditctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.auditctl.chmod(0o755)
        self._saved = os.environ.get(ENV_VAR)
        os.environ.pop(ENV_VAR, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = self._saved
        self._tmpdir.cleanup()

    def _packet(self) -> dict:
        return {
            "task_id": "t-1",
            "repo_id": "agentops",
            "starting_commit": "0" * 40,
            "worktree": {"root": str(self.tmp)},
        }

    def _escalate(self, runner) -> dict:
        return driver.write_escalation(
            self._packet(), "gate", 3, "boom", runner, str(self.auditctl),
        )

    # M-6b/1 — the driver holds no opinion about the root, by any route
    def test_driver_has_no_artifacts_root_resolver(self):
        # Named explicitly rather than by a source scan: a resolver that comes
        # back under a different name is the same defect, and this is the name
        # a reader of the retired row will look for first.
        self.assertFalse(
            hasattr(driver, "default_artifacts_root"),
            "dispatch_release.py still resolves an artifacts root of its own",
        )
        source = DRIVER_SRC.read_text(encoding="utf-8")
        offenders = [
            line.strip()
            for line in source.splitlines()
            if ENV_VAR in line and not line.lstrip().startswith("#")
        ]
        self.assertEqual(
            offenders, [], "dispatch_release.py still touches the artifacts root"
        )

    # M-6b/2 — one source of truth, so no literal is left behind
    def test_driver_source_carries_no_root_literal(self):
        hits = [
            line.strip()
            for line in DRIVER_SRC.read_text(encoding="utf-8").splitlines()
            if "/projects/dev" in line
        ]
        self.assertEqual(hits, [], "dispatch_release.py still hardcodes a root")

    # M-6b/3 — an escalation with no root set is still recorded, and stays unset
    def test_escalation_is_recorded_without_a_root_and_sets_none(self):
        runner = FakeRunner(str(self.auditctl))
        record = self._escalate(runner)
        self.assertEqual(record["sink"], "auditctl")
        self.assertEqual(json.loads(runner.calls[0][0][-1])["step"], "gate")
        # Observed at the moment of the call, not afterwards: a driver that set
        # the variable and then cleaned it up would still have decided the root.
        self.assertIsNone(runner.calls[0][2])
        self.assertNotIn(ENV_VAR, os.environ)

    # M-6b/4 — an inherited root reaches the publisher unchanged
    def test_inherited_root_is_passed_through_untouched(self):
        os.environ[ENV_VAR] = "/inherited/root"
        runner = FakeRunner(str(self.auditctl))
        record = self._escalate(runner)
        self.assertEqual(record["sink"], "auditctl")
        self.assertEqual(runner.calls[0][2], "/inherited/root")
        self.assertEqual(os.environ[ENV_VAR], "/inherited/root")


if __name__ == "__main__":
    unittest.main()
