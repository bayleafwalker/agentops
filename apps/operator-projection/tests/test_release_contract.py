"""The package release gate checks the built wheel and immutable client pin."""

import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest
import yaml

CHECKS = Path(__file__).resolve().parents[1] / "checks"
sys.path.insert(0, str(CHECKS))
from validate_release import CLIENT_SHA, CLIENT_URL, expected_wheel_members, validate  # noqa: E402

PACKAGE = Path(__file__).resolve().parents[1]
TAG = "operator-projection-v0.2.5"


def root_copy(tmp_path):
    for name in ("pyproject.toml", "uv.lock"):
        (tmp_path / name).write_bytes((PACKAGE / name).read_bytes())
    return tmp_path


def wheel(tmp_path, *, version="0.2.5", with_module=True, extra_member=None):
    path = tmp_path / f"operator_projection-{version}-py3-none-any.whl"
    metadata = (f"Name: operator-projection\nVersion: {version}\nRequires-Python: >=3.11\n"
                f"Requires-Dist: vuoro-client @ {CLIENT_URL}#sha256={CLIENT_SHA} ; python_version >= \"3.12\"\n")
    with ZipFile(path, "w") as archive:
        for name in sorted(expected_wheel_members(version)):
            if name == "operator_projection/portable_acceptance.py" and not with_module:
                continue
            archive.writestr(name, metadata if name.endswith("/METADATA") else "reviewed fixture")
        if extra_member:
            archive.writestr(extra_member, "private marker")
    return path


def test_own_release_tag_and_wheel_identity_pass(tmp_path):
    root = root_copy(tmp_path)
    assert validate(root, TAG) == "0.2.5"
    assert validate(root, TAG, wheel(tmp_path)) == "0.2.5"


@pytest.mark.parametrize("tag", [
    "vuoro-client-v0.2.5", "operator-projection-v0.2.4",
    "operator-projection-v0.2.5-rc1", "operator-projection-v0.2.5;echo bad",
])
def test_wrong_package_or_version_tag_refuses(tmp_path, tag):
    with pytest.raises(ValueError, match="release contract refused"):
        validate(root_copy(tmp_path), tag)


@pytest.mark.parametrize("name,old,new", [
    ("pyproject.toml", CLIENT_SHA, "0" * 64),
    ("uv.lock", CLIENT_SHA, "0" * 64),
    ("uv.lock", 'version = "0.2.5"', 'version = "0.2.4"'),
])
def test_wrong_client_digest_or_lock_version_refuses(tmp_path, name, old, new):
    root = root_copy(tmp_path)
    path = root / name
    path.write_text(path.read_text().replace(old, new, 1))
    with pytest.raises(ValueError, match="release contract refused"):
        validate(root, TAG)


@pytest.mark.parametrize("fault", [
    "wrong_version", "missing_portable", "private_member",
    "ordinary_package_extra", "dist_info_extra",
])
def test_wrong_wheel_bytes_refuse(tmp_path, fault):
    root = root_copy(tmp_path)
    if fault == "wrong_version":
        candidate = wheel(tmp_path, version="0.2.4")
    elif fault == "missing_portable":
        candidate = wheel(tmp_path, with_module=False)
    elif fault == "private_member":
        candidate = wheel(tmp_path, extra_member="operator_projection/../private.txt")
    elif fault == "ordinary_package_extra":
        candidate = wheel(tmp_path, extra_member="operator_projection/private.txt")
    else:
        candidate = wheel(tmp_path, extra_member="operator_projection-0.2.5.dist-info/private.txt")
    with pytest.raises(ValueError, match="release contract refused"):
        validate(root, TAG, candidate)


def test_fresh_main_check_refuses_advance_before_publish(tmp_path):
    """A previously valid release tag must fail after the remote main moves."""
    remote = tmp_path / "remote.git"
    checkout = tmp_path / "checkout"
    script = PACKAGE / "checks" / "require_current_main.sh"

    def git(*args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd, check=True, text=True,
                              capture_output=True).stdout.strip()

    git("init", "--bare", "--initial-branch=main", str(remote))
    git("init", "--initial-branch=main", str(checkout))
    git("config", "user.name", "Release Test", cwd=checkout)
    git("config", "user.email", "release-test@example.invalid", cwd=checkout)
    (checkout / "source.txt").write_text("first")
    git("add", "source.txt", cwd=checkout)
    git("commit", "-m", "first", cwd=checkout)
    original = git("rev-parse", "HEAD", cwd=checkout)
    git("tag", TAG, cwd=checkout)
    git("remote", "add", "origin", str(remote), cwd=checkout)
    git("push", "origin", "main", cwd=checkout)
    env = {**os.environ, "GITHUB_REF": f"refs/tags/{TAG}"}
    command = ["bash", str(script), TAG, original]
    assert subprocess.run(command, cwd=checkout, env=env, capture_output=True).returncode == 0

    (checkout / "source.txt").write_text("second")
    git("commit", "-am", "second", cwd=checkout)
    git("push", "origin", "main", cwd=checkout)
    git("reset", "--hard", original, cwd=checkout)
    result = subprocess.run(command, cwd=checkout, env=env, text=True, capture_output=True)
    assert result.returncode != 0
    assert "tag does not name current canonical main" in result.stderr


def test_publish_step_rechecks_main_immediately_before_publication():
    workflow = yaml.safe_load((PACKAGE.parents[1] / ".github/workflows/publish-operator-projection.yml").read_text())
    steps = workflow["jobs"]["publish"]["steps"]
    initial = next(step for step in steps if step.get("id") == "identity")
    final = next(step for step in steps if step.get("name") == "Publish the verified draft")
    guard = "bash apps/operator-projection/checks/require_current_main.sh \"$RELEASE_TAG\" \"$GITHUB_SHA\""
    assert guard in initial["run"]
    assert final["run"].splitlines()[-2:] == [
        f"{guard}",
        'gh release edit "$RELEASE_TAG" --repo "$GITHUB_REPOSITORY" --draft=false',
    ]
