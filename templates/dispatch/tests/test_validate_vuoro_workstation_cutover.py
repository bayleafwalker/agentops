from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "dispatch/scripts/validate_vuoro_workstation_cutover.py"
SPEC = importlib.util.spec_from_file_location("validate_vuoro_workstation_cutover", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _profile(tmp_path: Path) -> Path:
    profile = tmp_path / "workstation-vuoro-shared.json"
    profile.write_text("{}\n")
    return profile


def test_vuoro_is_a_selected_cutover_repository() -> None:
    """The public Vuoro repo must receive the same served-session contract."""
    assert "vuoro" in validator.REPOSITORIES


def test_served_envrc_is_accepted(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served\n"
        f"export SPRINTCTL_VUORO_PROFILE={profile}\n"
    )

    assert validator.validate_envrc(path, profile) == []


def test_served_envrc_with_unset_sprintctl_url_is_accepted(tmp_path: Path) -> None:
    """The prescribed cutover block ends with `unset SPRINTCTL_URL`; that
    cleanup line must not itself trip the direct-backend-wiring check."""
    profile = _profile(tmp_path)
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served\n"
        f"export SPRINTCTL_VUORO_PROFILE={profile}\n"
        "unset SPRINTCTL_URL\n"
    )

    assert validator.validate_envrc(path, profile) == []


def test_direct_postgres_wiring_is_rejected(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=remote\n"
        "export SPRINTCTL_URL=postgresql://example.invalid/sprintctl\n"
        f"export SPRINTCTL_VUORO_PROFILE={profile}\n"
    )

    errors = validator.validate_envrc(path, profile)

    assert any("direct-backend" in error for error in errors)
    assert any("missing `export SPRINTCTL_BACKEND=served`" in error for error in errors)


def test_commented_direct_backend_wiring_is_ignored(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served # default\n"
        f"export SPRINTCTL_VUORO_PROFILE={profile} # selected profile\n"
        "# export SPRINTCTL_BACKEND=remote\n"
        "# export SPRINTCTL_URL=postgresql://example.invalid/sprintctl\n"
    )

    assert validator.validate_envrc(path, profile) == []


def test_hash_in_quoted_value_is_not_treated_as_comment(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    path = tmp_path / ".envrc"
    path.write_text(
        "export SPRINTCTL_BACKEND=served\n"
        f"export SPRINTCTL_VUORO_PROFILE={profile}\n"
        'export SPRINTCTL_URL="postgresql://example.invalid/sprintctl#fragment"\n'
    )

    assert any("direct-backend" in error for error in validator.validate_envrc(path, profile))
