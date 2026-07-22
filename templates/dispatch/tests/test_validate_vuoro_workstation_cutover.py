from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dispatch/scripts/validate_vuoro_workstation_cutover.py"
SPEC = importlib.util.spec_from_file_location("validate_vuoro_workstation_cutover", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def test_served_envrc_is_accepted(tmp_path: Path) -> None:
    profile = "/projects/dev/agentops/templates/dispatch/environment-record/profiles/workstation-vuoro-shared.json"
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served\n"
        f"export SPRINTCTL_VUORO_PROFILE={profile}\n"
    )

    assert validator.validate_envrc(path, profile) == []


def test_direct_postgres_wiring_is_rejected(tmp_path: Path) -> None:
    profile = "/profiles/vuoro-shared.json"
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=remote\n"
        "export SPRINTCTL_URL=postgresql://example.invalid/sprintctl\n"
        f"export SPRINTCTL_VUORO_PROFILE={profile}\n"
    )

    errors = validator.validate_envrc(path, profile)

    assert any("direct-backend" in error for error in errors)
    assert any("missing `export SPRINTCTL_BACKEND=served`" in error for error in errors)
