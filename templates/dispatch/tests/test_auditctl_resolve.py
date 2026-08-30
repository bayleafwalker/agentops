"""One publisher-resolution policy for every Python caller, and it is never silent.

The 2026-08-29 measurement that produced `templates/dispatch/hooks/auditctl-resolve.sh`
found four call sites resolving `auditctl` under three different policies. The hook
helper and `hybrid_dispatch` carried the ELF guard and honoured `AUDITCTL_BIN`;
`metanarrative` tested for existence alone; `dispatch_release` accepted whatever
`shutil.which()` answered to. Both of the latter discard the publisher's result, so a
single shared-scope `AUDITCTL_BIN=/bin/true` silenced their telemetry with nothing
anywhere recording that it had.

These tests hold the shared resolver to the reference policy in the shell helper
(REQ-020..REQ-022) and to the one property the shell helper does not have to carry: a
Python caller that swallows the failure must still leave the reason on stderr.

The decoy is a real ELF, because that is what makes the live collision undetectable:
the kernel audit control tool is `/usr/bin/auditctl`, answers to the name, exits 0 and
publishes nothing. A compiled `true` stands in for it -- same shape, no dependency on
the `audit` package being installed.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPTS = ROOT / "templates/dispatch/scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


resolver = _load("auditctl_resolve_subject", SCRIPTS / "auditctl_resolve.py")
release = _load("dispatch_release_resolve_subject", SCRIPTS / "dispatch_release.py")
meta = _load("metanarrative_resolve_subject", SCRIPTS / "metanarrative.py")


def _publisher(directory: Path, tag: str = "ours") -> Path:
    """A stand-in for our publisher: a script, executable, and not an ELF."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "auditctl"
    path.write_text(f"#!/bin/sh\nprintf '{tag}\\n'\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _decoy(directory: Path) -> Path:
    """A compiled executable named auditctl, standing in for the kernel audit tool.

    Named candidates rather than one path: devbox is NixOS, where /bin holds only sh,
    and this fixture has to run on exactly the hosts a downgrade would hurt most.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "auditctl"
    for candidate in ("/bin/true", "/usr/bin/true", shutil.which("true"), shutil.which("env")):
        if not candidate or not os.access(candidate, os.X_OK):
            continue
        with open(candidate, "rb") as handle:
            if handle.read(4) != b"\x7fELF":
                continue
        shutil.copy2(candidate, path)
        return path
    raise unittest.SkipTest("no compiled executable found to stand in for the kernel tool")


class _EnvFixture(unittest.TestCase):
    """A controlled PATH, HOME and AUDITCTL_BIN, restored on the way out."""

    KEYS = ("PATH", "HOME", "AUDITCTL_BIN")

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._saved = {key: os.environ.get(key) for key in self.KEYS}
        # An empty HOME, so ~/.local/bin/auditctl is ours to create or withhold. The
        # workstation running these tests really does have one installed there.
        self.home = self.tmp / "home"
        self.home.mkdir()
        os.environ["HOME"] = str(self.home)
        os.environ["PATH"] = str(self.tmp / "empty")
        os.environ.pop("AUDITCTL_BIN", None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _resolve(self, **kwargs) -> tuple[str | None, str]:
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            answer = resolver.resolve(**kwargs)
        return answer, stderr.getvalue()


class OverrideTests(_EnvFixture):
    def test_auditctl_bin_is_honoured_when_it_names_our_publisher(self) -> None:
        """REQ-021's half of the policy: an explicit override wins over PATH."""
        ours = _publisher(self.tmp / "explicit")
        on_path = _publisher(self.tmp / "onpath", tag="path")
        os.environ["PATH"] = str(on_path.parent)
        os.environ["AUDITCTL_BIN"] = str(ours)

        answer, stderr = self._resolve()

        self.assertEqual(answer, str(ours))
        self.assertEqual(stderr, "", "honouring the override is not worth a diagnostic")

    def test_a_compiled_override_is_refused_and_said_out_loud(self) -> None:
        """The defect itself: `AUDITCTL_BIN=/bin/true` silenced telemetry with no trace.

        Refusing it is only half the fix. A caller here discards the publisher's result,
        so if the refusal is also silent the operator sees exactly what they saw before:
        a run that looks fine and an audit shard that never gains an event.
        """
        decoy = _decoy(self.tmp / "decoy")
        os.environ["AUDITCTL_BIN"] = str(decoy)

        answer, stderr = self._resolve()

        self.assertIsNone(answer)
        self.assertIn("AUDITCTL_BIN", stderr)
        self.assertIn(str(decoy), stderr)
        self.assertIn("compiled", stderr)

    def test_an_override_that_is_not_executable_is_refused_and_said_out_loud(self) -> None:
        dud = self.tmp / "not-a-program"
        dud.write_text("", encoding="utf-8")
        os.environ["AUDITCTL_BIN"] = str(dud)

        answer, stderr = self._resolve()

        self.assertIsNone(answer)
        self.assertIn(str(dud), stderr)

    def test_an_empty_override_means_no_publisher_and_is_not_a_complaint(self) -> None:
        """Set-but-empty is how a caller says "there is no publisher".

        The shell helper treats AUDITCTL_BIN as authoritative when set, empty included,
        because emptying PATH can no longer express it -- the known install location is
        still found. That is a statement, not a misconfiguration, so it stays quiet.
        """
        _publisher(self.home / ".local/bin")
        os.environ["AUDITCTL_BIN"] = ""

        answer, stderr = self._resolve()

        self.assertIsNone(answer)
        self.assertEqual(stderr, "")


class PathResolutionTests(_EnvFixture):
    def test_a_publisher_on_path_is_used(self) -> None:
        """REQ-022: a stub or a virtualenv install still wins."""
        ours = _publisher(self.tmp / "bin")
        os.environ["PATH"] = str(ours.parent)

        answer, stderr = self._resolve()

        self.assertEqual(answer, str(ours))
        self.assertEqual(stderr, "")

    def test_a_decoy_earlier_on_path_is_skipped_for_ours(self) -> None:
        decoy = _decoy(self.tmp / "decoy")
        ours = _publisher(self.tmp / "bin")
        os.environ["PATH"] = os.pathsep.join([str(decoy.parent), str(ours.parent)])

        answer, _ = self._resolve()

        self.assertEqual(answer, str(ours))

    def test_a_path_holding_only_the_decoy_falls_back_to_the_known_install(self) -> None:
        """REQ-020: a hook shell whose PATH holds only the other auditctl still publishes."""
        decoy = _decoy(self.tmp / "decoy")
        ours = _publisher(self.home / ".local/bin")
        os.environ["PATH"] = str(decoy.parent)

        answer, _ = self._resolve()

        self.assertEqual(answer, str(ours))

    def test_no_publisher_anywhere_is_expected_and_reported_once(self) -> None:
        """REQ-023's shape: not installed is not an error, but it is not invisible.

        "auditctl is not installed on this host" and "AUDITCTL_BIN points at the wrong
        program" are different facts, and the second is the one that needs shouting.
        This one gets a single line, and `quiet_when_absent` for a caller that would
        otherwise print it on every invocation.
        """
        answer, stderr = self._resolve()
        self.assertIsNone(answer)
        self.assertEqual(len(stderr.strip().splitlines()), 1)
        self.assertNotIn("AUDITCTL_BIN", stderr)

        answer, stderr = self._resolve(quiet_when_absent=True)
        self.assertIsNone(answer)
        self.assertEqual(stderr, "")


class ChildEnvTests(_EnvFixture):
    def test_auditctl_bin_is_popped_before_a_child_is_spawned(self) -> None:
        """The AGENTOPS_ROOT property, applied to the publisher.

        `hybrid_dispatch` pops AGENTOPS_ROOT before spawning a worker so a child cannot
        inherit the coordinator's value. AUDITCTL_BIN is the same kind of value: one
        export in a shared scope otherwise reaches every process underneath, which is
        precisely how one wrong setting silences a whole tree at once.
        """
        os.environ["AUDITCTL_BIN"] = "/bin/true"

        env = resolver.child_env()

        self.assertNotIn("AUDITCTL_BIN", env)
        self.assertIn("PATH", env, "only AUDITCTL_BIN is dropped; the rest is inherited")
        self.assertEqual(os.environ.get("AUDITCTL_BIN"), "/bin/true",
                         "the caller's own environment is left alone")

    def test_the_release_driver_spawns_children_without_it(self) -> None:
        """Proven through the real runner, not by reading the code."""
        os.environ["AUDITCTL_BIN"] = "/bin/true"
        probe = self.tmp / "probe.py"
        probe.write_text(
            "import json, os, sys\n"
            "json.dump({'seen': os.environ.get('AUDITCTL_BIN')}, sys.stdout)\n",
            encoding="utf-8",
        )

        completed = release._default_runner([sys.executable, str(probe)], None)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNone(json.loads(completed.stdout)["seen"])


class CallSiteTests(_EnvFixture):
    """Both former offenders now go through the shared resolver."""

    def test_neither_call_site_resolves_the_publisher_on_its_own(self) -> None:
        """The REQ-024 property, in Python: one policy, not three copies of two.

        A regrown local `shutil.which("auditctl")` is the exact shape of the defect --
        it is what both of these files did, and neither looked wrong on its own.
        """
        for path in (SCRIPTS / "metanarrative.py", SCRIPTS / "dispatch_release.py"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(script=path.name):
                self.assertIn("auditctl_resolve", source)
                self.assertNotIn('which("auditctl")', source)
                self.assertNotIn(".local/bin/auditctl", source)

    def test_metanarrative_refuses_a_compiled_override_without_losing_the_record(self) -> None:
        decoy = _decoy(self.tmp / "decoy")
        os.environ["AUDITCTL_BIN"] = str(decoy)

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            published = meta._auditctl("model.claim", "a claim", {"id": "X"})

        self.assertFalse(published, "an unpublished event must not report itself published")
        self.assertIn("compiled", stderr.getvalue())

    def test_metanarrative_publishes_through_an_honoured_override(self) -> None:
        log = self.tmp / "calls.log"
        stub = self.tmp / "bin/auditctl"
        stub.parent.mkdir(parents=True)
        stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{log}"\n', encoding="utf-8")
        stub.chmod(0o755)
        os.environ["AUDITCTL_BIN"] = str(stub)

        self.assertTrue(meta._auditctl("model.claim", "a claim", {"id": "X"}))
        self.assertIn("model.claim", log.read_text(encoding="utf-8"))

    def test_the_release_driver_refuses_a_compiled_publisher_loudly(self) -> None:
        decoy = _decoy(self.tmp / "decoy")
        packet = {
            "task_id": "T-RESOLVE",
            "repo_id": "repo-x",
            "starting_commit": "0" * 40,
        }
        calls: list[list[str]] = []

        def runner(cmd, cwd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            record = release.write_escalation(
                packet, "run", 1, "detail", runner, str(decoy),
            )

        self.assertEqual(record["sink"], "unavailable")
        self.assertEqual(calls, [], "the decoy is never executed")
        self.assertIn("compiled", stderr.getvalue())

    def test_the_release_driver_resolves_for_itself_when_none_is_named(self) -> None:
        """`--auditctl-bin` unset no longer means the bare name `auditctl`.

        It used to default to `os.environ.get("AUDITCTL_BIN", "auditctl")` and accept
        whatever answered, so on a host where the kernel tool is first on PATH the
        driver published every escalation into a program that discards it.
        """
        ours = _publisher(self.tmp / "bin")
        os.environ["PATH"] = str(ours.parent)
        packet = {
            "task_id": "T-RESOLVE",
            "repo_id": "repo-x",
            "starting_commit": "0" * 40,
        }
        calls: list[list[str]] = []

        def runner(cmd, cwd):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        record = release.write_escalation(packet, "run", 1, "detail", runner, None)

        self.assertEqual(record["sink"], "auditctl")
        self.assertEqual(calls[0][0], str(ours))


if __name__ == "__main__":
    unittest.main()
