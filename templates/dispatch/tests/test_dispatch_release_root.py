"""Coordinator-authored oracle for hand-pass 2 (handover §3c, amendment 3) --
item C over ``dispatch_release.py``: one policy per run.

C  every stage invocation carries ``--agentops-root``, resolved from the
   driver's own location unless the caller overrides it

The driver builds each stage with ``--repo-root`` and ``--packet`` only, so each
stage resolves its policy from ``hybrid_dispatch.AGENTOPS_ROOT`` -- a checkout
that need not be the one the coordinator validated the packet against. The two
disagreed the moment ``mechanical_bulk``'s ``max_attempts`` changed: ``validate``
accepted a retry packet the ``run`` stage then refused.

Written against the hand-pass spec only: item C is not implemented, so every
test here fails. Rule 11 keeps this file to its own subject -- it never imports
``hybrid_dispatch.py``, and the one subprocess it runs loads only the driver and
stands in a temp dir.
"""
from __future__ import annotations

import contextlib
import importlib.util
import inspect
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Loading a module by path writes a .pyc beside it. This oracle is run under
# strace at freeze time, where a write into the repository is a finding.
sys.dont_write_bytecode = True

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"
DRIVER_SRC = SCRIPTS / "dispatch_release.py"

FLAG = "--agentops-root"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


driver = _load_module("dispatch_release_root_subject", DRIVER_SRC)


class FakeRunner:
    """Scripted stand-in for subprocess: records every command and its cwd."""

    def __init__(self):
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), cwd))
        stdout = ""
        if cmd and "--packet" in cmd:
            step = cmd[-1]
            payload = {"stage": step}
            if step == "gate":
                payload["disposition"] = "candidate"
            stdout = json.dumps(payload)
        return subprocess.CompletedProcess(cmd, 0, stdout, "")

    def stage_commands(self) -> list[list[str]]:
        """Only the hybrid_dispatch stage invocations -- not gh, git, auditctl."""
        return [cmd for cmd, _ in self.calls if "--packet" in cmd]


class AgentopsRootTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.repo_root = self.tmp / "coordinator"
        self.repo_root.mkdir()
        self.packet_path = self.tmp / "packet.json"
        self.packet_path.write_text(json.dumps(self._packet()), encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def _packet(self) -> dict:
        return {
            "task_id": "T-ROOT",
            "repo_id": "repo-x",
            "starting_commit": "0" * 40,
            "worktree": {"root": str(self.tmp / "wt"), "branch": "hybrid/t-root"},
        }

    def _flag_value(self, cmd: list[str]) -> str:
        """The --agentops-root value, reported as a failure when it is absent.

        Indexing straight into the command turns the missing flag into a
        ValueError, which reads like a broken oracle rather than like the
        contract this file exists to state.
        """
        self.assertIn(FLAG, cmd, f"stage {cmd[-1]} carries no {FLAG}: {cmd}")
        return cmd[cmd.index(FLAG) + 1]

    def _drive(self, module=None, **kw):
        module = module or driver
        runner = FakeRunner()
        kw.setdefault("dry_run", True)
        kw.setdefault("base_branch", "main")
        module.drive(self.packet_path, self.repo_root, runner=runner, **kw)
        return runner

    # C1 -- the seam exists, and it is optional and keyword-only
    def test_c_drive_takes_an_optional_keyword_only_agentops_root(self):
        parameters = inspect.signature(driver.drive).parameters
        self.assertIn("agentops_root", parameters, "drive() has no agentops_root keyword")
        parameter = parameters["agentops_root"]
        # Keyword-only, so no future call site can pass it by position and land
        # it on repo_root -- the two are different roots and easily confused.
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameter.default)

    # C2 -- every stage, not just the first
    def test_c_every_stage_command_carries_the_flag_with_a_value(self):
        runner = self._drive()
        commands = runner.stage_commands()
        self.assertEqual(
            [cmd[-1] for cmd in commands], list(driver.STEPS),
            "the fixed step order changed; item C moves no steps",
        )
        for cmd in commands:
            with self.subTest(step=cmd[-1]):
                value = self._flag_value(cmd)
                self.assertFalse(value.startswith("-"), f"{FLAG} has no value: {cmd}")

    # C3 -- resolved from the driver's file location, not a hardcoded literal
    def test_c_the_default_is_derived_from_the_drivers_own_location(self):
        # A copy of the driver planted under a different repository root: only
        # HERE.parents[2] resolution reports that root back. A literal
        # "/projects/dev/agentops" survives this fixture in the real tree,
        # where the two paths coincide, and dies here.
        home = self.tmp / "elsewhere-agentops"
        scripts = home / "templates/dispatch/scripts"
        scripts.mkdir(parents=True)
        shutil.copy(DRIVER_SRC, scripts / "dispatch_release.py")
        relocated = _load_module("relocated_driver", scripts / "dispatch_release.py")
        runner = self._drive(module=relocated)
        for cmd in runner.stage_commands():
            with self.subTest(step=cmd[-1]):
                self.assertEqual(Path(self._flag_value(cmd)).resolve(), home.resolve())

    # C4 -- and not from the working directory
    def test_c_the_default_ignores_the_working_directory(self):
        # Run from a temp cwd: a driver that resolved the root from Path.cwd()
        # would report the temp dir, while HERE-based resolution is indifferent
        # to where the process happens to stand. Only the driver module and the
        # temp dir are touched -- no git, no foreign checkout.
        program = self.tmp / "probe.py"
        program.write_text(
            "import importlib.util, json, subprocess, sys\n"
            "from pathlib import Path\n"
            "sys.dont_write_bytecode = True\n"
            f"spec = importlib.util.spec_from_file_location('d', {str(DRIVER_SRC)!r})\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "def runner(cmd, cwd):\n"
            "    out = ''\n"
            "    if '--packet' in cmd:\n"
            "        payload = {'stage': cmd[-1]}\n"
            "        if cmd[-1] == 'gate':\n"
            "            payload['disposition'] = 'candidate'\n"
            "        out = json.dumps(payload)\n"
            "    return subprocess.CompletedProcess(cmd, 0, out, '')\n"
            f"code, report = m.drive(Path({str(self.packet_path)!r}),"
            f" Path({str(self.repo_root)!r}),"
            " dry_run=True, base_branch='main', runner=runner)\n"
            "print(json.dumps([s['command'] for s in report['steps']]))\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, "-B", str(program)],
            cwd=self.tmp, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        commands = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(commands, "the driver ran no stages")
        for cmd in commands:
            with self.subTest(step=cmd[-1]):
                value = Path(self._flag_value(cmd)).resolve()
                self.assertEqual(value, ROOT.resolve())
                self.assertNotEqual(value, self.tmp.resolve())

    # C5 -- an explicit root is used verbatim
    def test_c_an_explicit_agentops_root_is_passed_through_unchanged(self):
        # The override is the whole point of the keyword: a coordinator running
        # out of a second checkout must be able to name it.
        override = self.tmp / "pinned-agentops"
        override.mkdir()
        # Checked before the call so an absent keyword reads as this contract
        # failing rather than as a TypeError out of the driver.
        self.assertIn("agentops_root", inspect.signature(driver.drive).parameters)
        runner = self._drive(agentops_root=override)
        for cmd in runner.stage_commands():
            with self.subTest(step=cmd[-1]):
                self.assertEqual(self._flag_value(cmd), str(override))

    # C6 -- the CLI exposes the same override
    def test_c_the_cli_accepts_agentops_root_and_hands_it_to_drive(self):
        seen: dict = {}
        original = driver.drive

        def spy(packet_path, repo_root, **kwargs):
            seen["kwargs"] = kwargs
            return 0, {"steps": []}

        override = self.tmp / "cli-agentops"
        override.mkdir()
        driver.drive = spy
        try:
            # main() dumps its report to stdout; swallowed so a failing run
            # reports one assertion instead of a report on top of it.
            with contextlib.redirect_stdout(io.StringIO()):
                driver.main([str(self.packet_path), "--repo-root", str(self.repo_root),
                             FLAG, str(override), "--dry-run"])
        finally:
            driver.drive = original
        self.assertIn("agentops_root", seen.get("kwargs", {}))
        self.assertEqual(Path(seen["kwargs"]["agentops_root"]).resolve(), override.resolve())

    # C7 -- the two roots item C touches keep their existing meaning
    def test_c_repo_root_and_packet_are_unchanged(self):
        runner = self._drive()
        for cmd in runner.stage_commands():
            with self.subTest(step=cmd[-1]):
                self.assertEqual(cmd[cmd.index("--repo-root") + 1], str(self.repo_root))
                self.assertEqual(cmd[cmd.index("--packet") + 1], str(self.packet_path))
                # --agentops-root is a policy root and must never be confused
                # with the coordinator's repository root.
                self.assertNotEqual(self._flag_value(cmd), str(self.repo_root))
                # The step stays last: every existing driver oracle reads it as
                # cmd[-1], so a flag appended after it breaks all of them.
                self.assertIn(cmd[-1], driver.STEPS)


if __name__ == "__main__":
    unittest.main()
