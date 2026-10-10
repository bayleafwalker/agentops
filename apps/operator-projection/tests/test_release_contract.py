"""The package release gate checks the built wheel and immutable client pin."""

import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

CHECKS = Path(__file__).resolve().parents[1] / "checks"
sys.path.insert(0, str(CHECKS))
from validate_release import CLIENT_SHA, CLIENT_URL, validate  # noqa: E402

PACKAGE = Path(__file__).resolve().parents[1]
TAG = "operator-projection-v0.2.5"


def root_copy(tmp_path):
    for name in ("pyproject.toml", "uv.lock"):
        (tmp_path / name).write_bytes((PACKAGE / name).read_bytes())
    return tmp_path


def wheel(tmp_path, *, version="0.2.5", with_module=True, with_private=False):
    path = tmp_path / f"operator_projection-{version}-py3-none-any.whl"
    metadata = (f"Name: operator-projection\nVersion: {version}\nRequires-Python: >=3.11\n"
                f"Requires-Dist: vuoro-client @ {CLIENT_URL}#sha256={CLIENT_SHA} ; python_version >= \"3.12\"\n")
    with ZipFile(path, "w") as archive:
        archive.writestr(f"operator_projection-{version}.dist-info/METADATA", metadata)
        archive.writestr("operator_projection/reconstruction.py", "# P1\n")
        if with_module:
            archive.writestr("operator_projection/portable_acceptance.py", "# portable\n")
        if with_private:
            archive.writestr("operator_projection/../private.txt", "private")
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


@pytest.mark.parametrize("fault", ["wrong_version", "missing_portable", "private_member"])
def test_wrong_wheel_bytes_refuse(tmp_path, fault):
    root = root_copy(tmp_path)
    if fault == "wrong_version":
        candidate = wheel(tmp_path, version="0.2.4")
    elif fault == "missing_portable":
        candidate = wheel(tmp_path, with_module=False)
    else:
        candidate = wheel(tmp_path, with_private=True)
    with pytest.raises(ValueError, match="release contract refused"):
        validate(root, TAG, candidate)
