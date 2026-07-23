from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


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


def test_normalize_hostname_matches_existing_record_id_convention() -> None:
    # sprintctl's own claim records show this host's real hostname as
    # PascalCase ("WorkstationLinux"); the environment-record id is
    # kebab-case ("workstation-linux") -- normalization must bridge that.
    assert resolver.normalize_hostname("WorkstationLinux") == "workstation-linux"
    assert resolver.normalize_hostname("devbox-vm") == "devbox-vm"
    assert resolver.normalize_hostname("Some_Host.local") == "some_host.local"


def test_resolves_this_hosts_real_hostname_without_override() -> None:
    # Regression guard: a naive .lower() on "WorkstationLinux" produces
    # "workstationlinux", which matches no real record id.
    records_dir = ROOT / "dispatch/environment-record"
    resolved = resolver.resolve_environment_record(
        records_dir, hostname="WorkstationLinux"
    )
    assert resolved.name == "workstation-linux.vuoro-shared.json"


def test_resolves_unique_matching_record(tmp_path: Path) -> None:
    _write_record(tmp_path / "myhost.vuoro-shared.json", record_id="myhost")
    resolved = resolver.resolve_environment_record(tmp_path, hostname="myhost")
    assert resolved == tmp_path / "myhost.vuoro-shared.json"


def test_excludes_example_templates_from_resolution(tmp_path: Path) -> None:
    _write_record(tmp_path / "myhost.example.json", record_id="myhost")
    with pytest.raises(resolver.EnvironmentResolutionError):
        resolver.resolve_environment_record(tmp_path, hostname="myhost")


def test_raises_on_no_match(tmp_path: Path) -> None:
    _write_record(tmp_path / "otherhost.vuoro-shared.json", record_id="otherhost")
    with pytest.raises(resolver.EnvironmentResolutionError):
        resolver.resolve_environment_record(tmp_path, hostname="myhost")


def test_raises_on_ambiguous_match(tmp_path: Path) -> None:
    _write_record(tmp_path / "myhost.vuoro-shared.json", record_id="myhost")
    _write_record(tmp_path / "myhost.other-target.json", record_id="myhost")
    with pytest.raises(resolver.EnvironmentResolutionError):
        resolver.resolve_environment_record(tmp_path, hostname="myhost")


def test_real_records_dir_resolves_for_known_hosts() -> None:
    records_dir = ROOT / "dispatch/environment-record"
    resolved = resolver.resolve_environment_record(
        records_dir, hostname="workstation-linux"
    )
    assert resolved.name == "workstation-linux.vuoro-shared.json"
    resolved = resolver.resolve_environment_record(records_dir, hostname="devbox-vm")
    assert resolved.name == "devbox-vm.vuoro-shared.json"
