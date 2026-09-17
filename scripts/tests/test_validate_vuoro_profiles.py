from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/validate_vuoro_profiles.py"
SPEC = importlib.util.spec_from_file_location("validate_vuoro_profiles", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _profile(name: str) -> Path:
    return ROOT / "environment-record/profiles" / name


def test_checked_in_workstation_profile_is_valid() -> None:
    environment = validator.validate_environment(
        ROOT / "environment-record/workstation-linux.vuoro-shared.json"
    )
    profile = validator.validate_profile(_profile("workstation-vuoro-shared.json"), environment)

    assert profile["target"]["environment_class"] == "production"
    assert "work:sprint" in profile["required_authorities"]


def test_checked_in_devbox_profile_is_valid() -> None:
    environment = validator.validate_environment(
        ROOT / "environment-record/devbox-vm.vuoro-shared.json"
    )
    profile = validator.validate_profile(_profile("devbox-agent-vuoro-shared.json"), environment)

    assert profile["source_environment_id"] == "devbox"
    assert "work:sprint" not in profile["required_authorities"]


def test_production_target_is_rejected(tmp_path: Path) -> None:
    environment = validator.validate_environment(
        ROOT / "environment-record/workstation-linux.vuoro-shared.json"
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
        ROOT / "environment-record/workstation-linux.vuoro-shared.json"
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


# --------------------------------------------------------------------------- #
# TS-10 interim DSN fence: no .envrc or shared profile selects a direct
# PostgreSQL backend. Ported from the retired
# validate_vuoro_workstation_cutover.py (39cf66a); retires at S5.
# --------------------------------------------------------------------------- #


def test_served_envrc_has_no_dsn_fence_violation(tmp_path: Path) -> None:
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served\n"
        "export SPRINTCTL_VUORO_PROFILE=/some/profile.json\n"
        "unset SPRINTCTL_URL\n"
    )

    assert validator.dsn_fence_violations(path) == []


def test_direct_postgres_wiring_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=remote\n"
        "export SPRINTCTL_URL=postgresql://example.invalid/sprintctl\n"
    )

    errors = validator.dsn_fence_violations(path)

    assert any("direct-backend" in error for error in errors)


def test_commented_direct_backend_wiring_is_ignored(tmp_path: Path) -> None:
    """`unset SPRINTCTL_URL` is prescribed cleanup and must not itself trip the fence."""
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served # default\n"
        "unset SPRINTCTL_URL\n"
        "# export SPRINTCTL_BACKEND=remote\n"
        "# export SPRINTCTL_URL=postgresql://example.invalid/sprintctl\n"
    )

    assert validator.dsn_fence_violations(path) == []


def test_hash_in_quoted_value_is_not_treated_as_comment(tmp_path: Path) -> None:
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served\n"
        'export SPRINTCTL_URL="postgresql://example.invalid/sprintctl#fragment"\n'
    )

    assert any("direct-backend" in error for error in validator.dsn_fence_violations(path))


def test_shared_profile_json_is_scanned_for_direct_dsn(tmp_path: Path) -> None:
    """A shared profile JSON has no shell comment syntax; it is scanned as-is."""
    path = tmp_path / "shared-profile.json"
    path.write_text(json.dumps({"note": "postgresql://example.invalid/sprintctl"}))

    assert any("direct-backend" in error for error in validator.dsn_fence_violations(path))
