from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


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


def test_shared_profiles_hold_no_claim_authority() -> None:
    # #2556(d): claim authority belongs to hosted/connector paths, not vuoro-shared.
    assert "work:claim" not in validator.WORK_AUTHORITIES
    for name in ("workstation-vuoro-shared.json", "devbox-agent-vuoro-shared.json"):
        profile = json.loads(_profile(name).read_text())
        assert "work:claim" not in profile["required_authorities"]


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


def test_native_evidence_profile_is_scoped_and_operator_profile_unchanged() -> None:
    environment = validator.validate_environment(
        ROOT / "environment-record/workstation-linux.vuoro-shared.json"
    )
    native = validator.validate_profile(
        _profile("workstation-mi1-native-vuoro-shared.json"), environment
    )
    assert set(native["required_authorities"]) == {"work:read", "work:evidence"}
    operator = validator.validate_profile(_profile("workstation-vuoro-shared.json"), environment)
    assert "work:sprint" in operator["required_authorities"]
    assert native["credential_ref"] != operator["credential_ref"]


def test_native_evidence_profile_cannot_request_effect_authority(tmp_path: Path) -> None:
    environment = validator.validate_environment(
        ROOT / "environment-record/workstation-linux.vuoro-shared.json"
    )
    value = json.loads(_profile("workstation-mi1-native-vuoro-shared.json").read_text())
    value["required_authorities"].append("work:effect-apply")
    path = tmp_path / "widened.json"
    path.write_text(json.dumps(value))
    try:
        validator.validate_profile(path, environment)
    except validator.ProfileError as exc:
        assert "extra=['work:effect-apply']" in str(exc)
    else:
        raise AssertionError("expected native evidence scope rejection")


def test_inbox_native_profiles_are_evidence_scoped_and_host_bound(tmp_path: Path) -> None:
    hosts = {
        "workstation-inbox-native-vuoro-shared.json": "workstation-linux.vuoro-shared.json",
        "devbox-inbox-native-vuoro-shared.json": "devbox-vm.vuoro-shared.json",
    }
    for profile, environment_file in hosts.items():
        environment = validator.validate_environment(ROOT / "environment-record" / environment_file)
        value = validator.validate_profile(_profile(profile), environment)
        assert set(value["required_authorities"]) == {"work:read", "work:evidence"}
        assert value["credential_ref"].endswith("/vuoro-shared-inbox-native")
    other = validator.validate_environment(ROOT / "environment-record/workstation-linux.vuoro-shared.json")
    try:
        validator.validate_profile(_profile("devbox-inbox-native-vuoro-shared.json"), other)
    except validator.ProfileError as exc:
        assert "source_environment_id" in str(exc) or "bound to devbox" in str(exc)
    else:
        raise AssertionError("expected host binding rejection")

DEVBOX = ROOT / "environment-record/devbox-vm.vuoro-shared.json"


def _devbox_with(tmp_path: Path, mutate) -> Path:
    record = json.loads(DEVBOX.read_text(encoding="utf-8"))
    mutate(record)
    path = tmp_path / "devbox.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_devbox_record_declares_bounded_authority_and_pinned_tooling() -> None:
    record = validator.validate_environment(DEVBOX)
    scoped = record["authority"]["scoped_execution"]
    assert scoped["repositories"] == ["agentops"]
    assert scoped["publication_operation"] == "agentops.dispatch.publish-v1"
    tools = {tool["name"]: tool["version"] for tool in record["tooling"]}
    assert tools["sprintctl"] == "0.19.0" and tools["opencode"] == "1.18.33"
    assert {c["capability"] for c in record["credential_broker"]["capabilities"]} <= validator.BROKER_CAPABILITIES


def test_runner_record_without_authority_is_rejected(tmp_path: Path) -> None:
    path = _devbox_with(tmp_path, lambda r: r.pop("authority"))
    with pytest.raises(validator.ProfileError, match="must declare authority"):
        validator.validate_environment(path)


def test_records_without_runner_role_need_no_authority() -> None:
    record = validator.validate_environment(ROOT / "environment-record/workstation-linux.vuoro-shared.json")
    assert "authority" not in record


def test_unknown_environment_field_is_rejected(tmp_path: Path) -> None:
    path = _devbox_with(tmp_path, lambda r: r.update({"authorities": {}}))
    with pytest.raises(validator.ProfileError, match="unknown authorities"):
        validator.validate_environment(path)


def test_publication_operation_must_be_in_scope(tmp_path: Path) -> None:
    def mutate(r):
        r["authority"]["scoped_execution"]["publication_operation"] = "agentops.other.publish-v1"
    with pytest.raises(validator.ProfileError, match="not within scoped_execution"):
        validator.validate_environment(_devbox_with(tmp_path, mutate))


def test_approval_operation_cannot_also_be_scoped(tmp_path: Path) -> None:
    def mutate(r):
        r["authority"]["scoped_execution"]["operations"].append("rollout.*")
    with pytest.raises(validator.ProfileError, match="also granted without approval"):
        validator.validate_environment(_devbox_with(tmp_path, mutate))


def test_ttl_is_bounded(tmp_path: Path) -> None:
    def mutate(r):
        r["authority"]["scoped_execution"]["max_ttl_seconds"] = 86401
    with pytest.raises(validator.ProfileError, match="max_ttl_seconds"):
        validator.validate_environment(_devbox_with(tmp_path, mutate))


def test_unpinned_tool_is_rejected(tmp_path: Path) -> None:
    def mutate(r):
        r["tooling"][0]["digest"] = "latest"
    with pytest.raises(validator.ProfileError, match="digest"):
        validator.validate_environment(_devbox_with(tmp_path, mutate))


def test_unknown_broker_capability_is_rejected(tmp_path: Path) -> None:
    def mutate(r):
        r["credential_broker"]["capabilities"][0]["capability"] = "repo.everything"
    with pytest.raises(validator.ProfileError, match="cred-broker capability"):
        validator.validate_environment(_devbox_with(tmp_path, mutate))
