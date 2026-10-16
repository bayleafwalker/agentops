"""Packet command registration is a hand-pass, not a title-only exemption.

Commit 1 of every freeze branch adds a key under ``hybrid.commands`` -- a
packet's oracle has to be runnable by id before a worker can be paid against
it. ``agentops.dispatch.json`` is a protected path. #83 exempted purely
additive ``hybrid.commands`` keys under a ``[hybrid]`` title, so the gate was
not red on every packet PR. But a ``hybrid.commands`` entry is a shell command
the dispatcher runs, and any PR author -- an agent included -- can write a
``[hybrid]`` title. That seam is closed: registering a command now needs the
same operator hand-pass (sender in ``hybrid.hand_pass_actors``, full head sha
in the title) as every other protected-path change.
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

ROOT = Path(__file__).parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


checker = _load("check_protected_paths_registration_subject",
                SCRIPTS / "check_protected_paths.py")

MANIFEST = {
    "hybrid": {
        "protected_paths": [
            "agentops.dispatch.json",
            "hybrid/scripts/hybrid_dispatch.py",
        ],
        "commands": {"agentops.dispatch.tests": "python -m unittest discover"},
        "worker_routes": ["mechanical_bulk"],
        "hand_pass_actors": ["operator"],
    },
    "routing": {"action_classes": {"mechanical_bulk": {"self_candidate": True}}},
}

PACKET_TITLE = "[hybrid] V5-T6a-scorecard-reduce @ be30cfed1cf2"


class RegistrationIsAHandPassTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self._git("init", "-q", "-b", "main")
        self._git("config", "user.email", "t@t.invalid")
        self._git("config", "user.name", "t")
        self._write_manifest(MANIFEST)
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

    def _register_a_command(self) -> None:
        """What commit 1 of a freeze branch actually does, and nothing else."""
        manifest = copy.deepcopy(MANIFEST)
        manifest["hybrid"]["commands"]["agentops.dispatch.tests.scorecard_reduce"] = (
            "python hybrid/tests/test_release_scorecard_reduce.py"
        )
        self._write_manifest(manifest)
        self._git("add", "-A")
        self._git("commit", "-qm", "register")

    def _head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

    def _run(self, title: str, sender: str = "operator") -> int:
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return checker.main([
                "--base", self.base, "--head", "HEAD", "--title", title,
                "--manifest", "agentops.dispatch.json",
                "--sender", sender,
            ])
        finally:
            os.chdir(cwd)

    def test_a_packet_title_alone_no_longer_registers_a_command(self):
        self._register_a_command()
        self.assertEqual(
            self._run(PACKET_TITLE, sender="agent-app[bot]"), 1,
            "an agent PR registered a dispatcher command under a [hybrid] title",
        )

    def test_a_packet_title_is_not_enough_even_for_the_operator(self):
        self._register_a_command()
        self.assertEqual(self._run(PACKET_TITLE, sender="operator"), 1)

    def test_an_operator_hand_pass_on_the_full_head_sha_registers_it(self):
        self._register_a_command()
        self.assertEqual(
            self._run(f"hand-pass@{self._head()}: register scorecard_reduce"), 0,
        )

    def test_an_agent_hand_pass_title_does_not_register_it(self):
        self._register_a_command()
        self.assertEqual(
            self._run(f"hand-pass@{self._head()}: register", sender="agent-app[bot]"), 1,
        )

    def test_a_short_sha_hand_pass_does_not_register_it(self):
        self._register_a_command()
        self.assertEqual(self._run(f"hand-pass@{self._head()[:7]}: register"), 1)


if __name__ == "__main__":
    unittest.main()
