"""Keep unavailable user managers distinct from absent renewal units."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HOOK = Path(__file__).resolve().parents[2] / "hooks/forge-credential.sh"


class RenewalTimerInventoryTests(unittest.TestCase):
    def inventory(self, reply, status=0, unit_present=False, inherited_bus=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if unit_present:
                unit = root / ".config/systemd/user/cred-broker-identity.timer"
                unit.parent.mkdir(parents=True)
                unit.symlink_to(root / "not-loaded-unit")
            executable = root / "systemctl"
            executable.write_text(
                '#!/usr/bin/env bash\n'
                'test "$XDG_RUNTIME_DIR" = "$TIMER_TEST_RUNTIME" || exit 91\n'
                'test "$DBUS_SESSION_BUS_ADDRESS" = "$TIMER_TEST_BUS" || exit 92\n'
                'printf "%s" "$TIMER_TEST_REPLY"\n'
                'exit "$TIMER_TEST_STATUS"\n'
            )
            executable.chmod(0o700)
            environment = dict(os.environ)
            environment.pop("XDG_RUNTIME_DIR", None)
            environment.pop("DBUS_SESSION_BUS_ADDRESS", None)
            environment.pop("XDG_CONFIG_HOME", None)
            runtime = "/tmp/custom-session-runtime" if inherited_bus else f"/run/user/{os.getuid()}"
            bus = "unix:path=/tmp/custom-session-bus" if inherited_bus else f"unix:path={runtime}/bus"
            if inherited_bus:
                environment.update(XDG_RUNTIME_DIR=runtime, DBUS_SESSION_BUS_ADDRESS=bus)
            environment.update(
                HOME=directory, PATH=f"{directory}:{environment['PATH']}",
                TIMER_TEST_REPLY=reply, TIMER_TEST_STATUS=str(status),
                TIMER_TEST_RUNTIME=runtime, TIMER_TEST_BUS=bus,
            )
            result = subprocess.run(
                ["bash", str(HOOK), "inventory"], env=environment,
                capture_output=True, text=True, check=True,
            )
            return next(line for line in result.stdout.splitlines() if "renewal timer:" in line)

    def test_agent_shell_reaches_user_manager(self):
        self.assertIn("UnitFileState=enabled", self.inventory(
            "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n"))

    def test_bus_failure_is_not_absence(self):
        result = self.inventory("", 1)
        self.assertIn("PROBE FAILED", result)
        self.assertNotIn("NOT INSTALLED", result)

    def test_empty_success_is_not_absence(self):
        self.assertIn("PROBE FAILED", self.inventory(""))

    def test_verified_missing_unit(self):
        self.assertIn("NOT INSTALLED", self.inventory(
            "LoadState=not-found\nActiveState=inactive\nUnitFileState=\n"))

    def test_disabled_unit_remains_distinct(self):
        result = self.inventory("LoadState=loaded\nActiveState=inactive\nUnitFileState=disabled\n")
        self.assertIn("UnitFileState=disabled", result)
        self.assertNotIn("NOT INSTALLED", result)

    def test_existing_unit_not_loaded(self):
        self.assertIn("PRESENT BUT NOT LOADED", self.inventory(
            "LoadState=not-found\nActiveState=inactive\nUnitFileState=\n", unit_present=True))

    def test_inherited_bus_is_preserved(self):
        self.assertIn("UnitFileState=enabled", self.inventory(
            "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\n", inherited_bus=True))
