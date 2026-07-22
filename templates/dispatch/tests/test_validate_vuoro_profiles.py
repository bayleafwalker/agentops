from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dispatch/scripts/validate_vuoro_profiles.py"
SPEC = importlib.util.spec_from_file_location("validate_vuoro_profiles", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _profile(name: str) -> Path:
    return ROOT / "dispatch/environment-record/profiles" / name


def test_checked_in_workstation_profile_is_valid() -> None:
    environment = validator.validate_environment(
        ROOT / "dispatch/environment-record/workstation-linux.vuoro-shared.json"
    )
    profile = validator.validate_profile(_profile("workstation-vuoro-shared.json"), environment)

    assert profile["target"]["environment_class"] == "production"


def test_checked_in_devbox_profile_is_valid() -> None:
    environment = validator.validate_environment(
        ROOT / "dispatch/environment-record/devbox-vm.vuoro-shared.json"
    )
    profile = validator.validate_profile(_profile("devbox-agent-vuoro-shared.json"), environment)

    assert profile["source_environment_id"] == "devbox-vm"


def test_production_target_is_rejected(tmp_path: Path) -> None:
    environment = validator.validate_environment(
        ROOT / "dispatch/environment-record/workstation-linux.vuoro-shared.json"
    )
    profile = json.loads(_profile("workstation-vuoro-shared.json").read_text())
    profile["target"]["environment_id"] = "vuoro-production"
    profile["target"]["environment_class"] = "production"
    path = tmp_path / "bad-profile.json"
    path.write_text(json.dumps(profile))

    try:
        validator.validate_profile(path, environment)
    except validator.ProfileError as exc:
        assert "primary vuoro-shared production target" in str(exc)
    else:
        raise AssertionError("expected production profile rejection")


def test_credential_value_or_url_is_rejected(tmp_path: Path) -> None:
    environment = validator.validate_environment(
        ROOT / "dispatch/environment-record/workstation-linux.vuoro-shared.json"
    )
    profile = json.loads(_profile("workstation-vuoro-shared.json").read_text())
    profile["credential_ref"] = "postgresql://not-a-reference"
    path = tmp_path / "bad-credential.json"
    path.write_text(json.dumps(profile))

    try:
        validator.validate_profile(path, environment)
    except validator.ProfileError as exc:
        assert "credential_ref" in str(exc)
    else:
        raise AssertionError("expected credential rejection")
