"""The one exemption in the protected-paths CI check: the registration seam.

Commit 1 of every freeze branch adds a key under ``hybrid.commands`` -- a
packet's oracle has to be runnable by id before a worker can be paid against
it. ``agentops.dispatch.json`` is a protected path, so before this exemption
the CI check was red on EVERY hybrid packet PR; #80 and #82 were both merged
over it. A gate that is red on every legitimate PR gets merged over by habit,
and then it is not there for the case it was built for (PR #74, where a change
to ``hybrid_dispatch.py`` rode into main under a title about something else).

The exemption is therefore the narrowest shape that fixes that: this one file,
purely additive command keys, and only under a ``[hybrid]`` title. Every test
below that expects 1 is a way of proving it stays narrow.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
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


checker = _load("check_protected_paths_registration_subject",
                SCRIPTS / "check_protected_paths.py")

#: A manifest small enough to read, carrying the two things that matter here:
#: the protected list names the manifest itself, and there is an existing
#: command id for an "additive" change to be additive to.
MANIFEST = {
    "hybrid": {
        "protected_paths": [
            "agentops.dispatch.json",
            "templates/dispatch/scripts/hybrid_dispatch.py",
        ],
        "commands": {"agentops.dispatch.tests": "python -m unittest discover"},
        "worker_routes": ["mechanical_bulk"],
    },
    "routing": {"action_classes": {"mechanical_bulk": {"self_candidate": True}}},
}

PACKET_TITLE = "[hybrid] V5-T6a-scorecard-reduce @ be30cfed1cf2"


class RegistrationSeamTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t.invalid")
        self._git("config", "user.name", "t")
        self._write_manifest(MANIFEST)
        driver = self.repo / "templates/dispatch/scripts/hybrid_dispatch.py"
        driver.parent.mkdir(parents=True, exist_ok=True)
        driver.write_text("base\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "base")
        self.base = self._git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True, check=True,
        ).stdout

    def _write_manifest(self, manifest) -> None:
        (self.repo / "agentops.dispatch.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    def _commit_manifest(self, manifest) -> None:
        self._write_manifest(manifest)
        self._git("add", "-A")
        self._git("commit", "-qm", "manifest")

    def _with_extra_command(self):
        """What commit 1 of a freeze branch actually does, and nothing else."""
        manifest = copy.deepcopy(MANIFEST)
        manifest["hybrid"]["commands"]["agentops.dispatch.tests.scorecard_reduce"] = (
            "python templates/dispatch/tests/test_release_scorecard_reduce.py"
        )
        return manifest

    def _run(self, title: str) -> int:
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return checker.main([
                "--base", self.base, "--head", "HEAD", "--title", title,
                "--manifest", "agentops.dispatch.json",
            ])
        finally:
            os.chdir(cwd)

    def test_a_packet_registering_its_command_id_passes(self):
        self._commit_manifest(self._with_extra_command())
        self.assertEqual(
            self._run(PACKET_TITLE), 0,
            "the freeze commit's command registration was refused, so this "
            "gate is red on every hybrid packet PR",
        )

    def test_the_same_change_without_the_packet_marker_still_fails(self):
        self._commit_manifest(self._with_extra_command())
        self.assertEqual(
            self._run("chore: register a command"), 1,
            "the exemption applied to a PR that never said it was a packet",
        )

    def test_a_hand_pass_title_still_works_for_the_same_change(self):
        self._commit_manifest(self._with_extra_command())
        self.assertEqual(self._run("hand-pass: register a command"), 0)

    def test_a_second_protected_path_defeats_the_exemption(self):
        self._write_manifest(self._with_extra_command())
        (self.repo / "templates/dispatch/scripts/hybrid_dispatch.py").write_text(
            "changed\n", encoding="utf-8"
        )
        self._git("add", "-A")
        self._git("commit", "-qm", "both")
        self.assertEqual(
            self._run(PACKET_TITLE), 1,
            "a driver change rode along under a packet title -- exactly the "
            "PR #74 shape this gate exists for",
        )

    def test_repointing_an_existing_command_is_not_additive(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["hybrid"]["commands"]["agentops.dispatch.tests"] = "echo green"
        self._commit_manifest(manifest)
        self.assertEqual(
            self._run(PACKET_TITLE), 1,
            "an existing command id was re-pointed under a packet title -- a "
            "gate could be made to pass by pointing it at true",
        )

    def test_removing_a_command_is_not_additive(self):
        manifest = copy.deepcopy(MANIFEST)
        manifest["hybrid"]["commands"] = {}
        self._commit_manifest(manifest)
        self.assertEqual(self._run(PACKET_TITLE), 1)

    def test_any_other_manifest_change_is_not_the_registration_seam(self):
        manifest = self._with_extra_command()
        manifest["routing"]["action_classes"]["mechanical_bulk"]["self_candidate"] = False
        self._commit_manifest(manifest)
        self.assertEqual(
            self._run(PACKET_TITLE), 1,
            "a routing flip rode along with a command registration",
        )

    def test_a_protected_path_that_is_not_the_manifest_is_unaffected(self):
        (self.repo / "templates/dispatch/scripts/hybrid_dispatch.py").write_text(
            "changed\n", encoding="utf-8"
        )
        self._git("add", "-A")
        self._git("commit", "-qm", "driver")
        self.assertEqual(self._run(PACKET_TITLE), 1)

    def test_the_manifest_appearing_for_the_first_time_is_not_exempt(self):
        """No base version to be additive to -- fail closed, do not guess."""
        self._git("rm", "-q", "agentops.dispatch.json")
        self._git("commit", "-qm", "drop manifest")
        base_without = self._git("rev-parse", "HEAD").strip()
        self._commit_manifest(self._with_extra_command())
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            self.assertEqual(
                checker.main([
                    "--base", base_without, "--head", "HEAD",
                    "--title", PACKET_TITLE,
                    "--manifest", "agentops.dispatch.json",
                ]), 1,
            )
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
