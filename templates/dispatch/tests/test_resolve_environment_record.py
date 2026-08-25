from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dispatch/scripts/resolve_environment_record.py"
SPEC = importlib.util.spec_from_file_location("resolve_environment_record", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
resolver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(resolver)


def _write_record(path: Path, *, record_id: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "environment-record/v1",
                "id": record_id,
                "environment_class": "local",
                "revision": 1,
                "roles": ["role-a"],
                "constraints": ["constraint-a"],
                "capabilities": ["capability-a"],
                "runbook_refs": ["/docs/runbook.md"],
                "identity_bindings": [{"principal": "p", "roles": ["r"]}],
            }
        )
    )


class ResolveEnvironmentRecordTests(unittest.TestCase):
    """stdlib unittest, not pytest.

    These are dispatch gate tests: `agentops.dispatch.tests` is a registered
    packet command, so it runs on whatever host a worker is dispatched to, in
    a cold clone, with no project environment. As pytest-style bare functions
    this module was never collected by `unittest discover` at all -- it only
    surfaced on devbox, where importing pytest fails outright and took the
    whole cold run red. Keeping the gate on the standard library is what makes
    "the cold run is green" mean the same thing on every host.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_normalize_hostname_matches_existing_record_id_convention(self) -> None:
        # sprintctl's own claim records show this host's real hostname as
        # PascalCase ("WorkstationLinux"); the environment-record id is
        # kebab-case ("workstation-linux") -- normalization must bridge that.
        self.assertEqual(resolver.normalize_hostname("WorkstationLinux"), "workstation-linux")
        self.assertEqual(resolver.normalize_hostname("devbox-vm"), "devbox-vm")
        self.assertEqual(resolver.normalize_hostname("Some_Host.local"), "some_host.local")

    def test_resolves_this_hosts_real_hostname_without_override(self) -> None:
        # Regression guard: a naive .lower() on "WorkstationLinux" produces
        # "workstationlinux", which matches no real record id.
        records_dir = ROOT / "dispatch/environment-record"
        resolved = resolver.resolve_environment_record(
            records_dir, hostname="WorkstationLinux"
        )
        self.assertEqual(resolved.name, "workstation-linux.vuoro-shared.json")

    def test_resolves_unique_matching_record(self) -> None:
        _write_record(self.tmp_path / "myhost.vuoro-shared.json", record_id="myhost")
        resolved = resolver.resolve_environment_record(self.tmp_path, hostname="myhost")
        self.assertEqual(resolved, self.tmp_path / "myhost.vuoro-shared.json")

    def test_excludes_example_templates_from_resolution(self) -> None:
        _write_record(self.tmp_path / "myhost.example.json", record_id="myhost")
        with self.assertRaises(resolver.EnvironmentResolutionError):
            resolver.resolve_environment_record(self.tmp_path, hostname="myhost")

    def test_raises_on_no_match(self) -> None:
        _write_record(self.tmp_path / "otherhost.vuoro-shared.json", record_id="otherhost")
        with self.assertRaises(resolver.EnvironmentResolutionError):
            resolver.resolve_environment_record(self.tmp_path, hostname="myhost")

    def test_raises_on_ambiguous_match(self) -> None:
        _write_record(self.tmp_path / "myhost.vuoro-shared.json", record_id="myhost")
        _write_record(self.tmp_path / "myhost.other-target.json", record_id="myhost")
        with self.assertRaises(resolver.EnvironmentResolutionError):
            resolver.resolve_environment_record(self.tmp_path, hostname="myhost")

    def test_real_records_dir_resolves_for_known_hosts(self) -> None:
        records_dir = ROOT / "dispatch/environment-record"
        resolved = resolver.resolve_environment_record(
            records_dir, hostname="workstation-linux"
        )
        self.assertEqual(resolved.name, "workstation-linux.vuoro-shared.json")
        resolved = resolver.resolve_environment_record(records_dir, hostname="devbox-vm")
        self.assertEqual(resolved.name, "devbox-vm.vuoro-shared.json")


if __name__ == "__main__":
    unittest.main()
