"""Validate this one distribution's source/tag/wheel identity before publishing."""

from __future__ import annotations

import argparse
import re
import tomllib
from email import policy
from email.parser import BytesParser
from pathlib import Path
from zipfile import BadZipFile, ZipFile

PACKAGE = "operator-projection"
CLIENT_VERSION = "0.1.2"
CLIENT_SHA = "7a4f32d4e2531a1abc99f5dc017fb8f6f22c4a1ef191079b98808be897081660"
CLIENT_URL = (
    "https://github.com/bayleafwalker/vuoro/releases/download/"
    "vuoro-client-v0.1.2/vuoro_client-0.1.2-py3-none-any.whl"
)
TAG = re.compile(r"operator-projection-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
PACKAGE_MEMBERS = frozenset({
    "operator_projection/__init__.py",
    "operator_projection/bundle.py",
    "operator_projection/bundle_cli.py",
    "operator_projection/cell.py",
    "operator_projection/cli.py",
    "operator_projection/comparison.py",
    "operator_projection/comparison_cli.py",
    "operator_projection/contract.py",
    "operator_projection/evaluators.py",
    "operator_projection/generate.py",
    "operator_projection/portable_acceptance.py",
    "operator_projection/reconstruction.py",
    "operator_projection/reconstruction_cli.py",
    "operator_projection/render_html.py",
    "operator_projection/render_text.py",
    "operator_projection/replay.py",
    "operator_projection/serve.py",
    "operator_projection/sources.py",
})
DIST_INFO_MEMBERS = frozenset({"METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD"})


def expected_wheel_members(version: str) -> frozenset[str]:
    """The reviewed distribution file set; additions require explicit review."""
    return PACKAGE_MEMBERS | {f"operator_projection-{version}.dist-info/{name}" for name in DIST_INFO_MEMBERS}


def refuse() -> None:
    raise ValueError("operator-projection release contract refused")


def validate(root: Path, tag: str, wheel: Path | None = None) -> str:
    """Return the version only after fixed source and optional wheel checks."""
    if type(tag) is not str or not TAG.fullmatch(tag):
        refuse()
    project = tomllib.loads((root / "pyproject.toml").read_text())
    metadata = project.get("project", {})
    version = metadata.get("version")
    if (metadata.get("name") != PACKAGE or type(version) is not str
            or tag != f"{PACKAGE}-v{version}"):
        refuse()
    client_pin = f"vuoro-client @ {CLIENT_URL}#sha256={CLIENT_SHA} ; python_version >= '3.12'"
    dependencies = metadata.get("dependencies")
    if type(dependencies) is not list or dependencies.count(client_pin) != 1:
        refuse()
    lock = tomllib.loads((root / "uv.lock").read_text())
    packages = lock.get("package")
    if type(packages) is not list or any(type(row) is not dict for row in packages):
        refuse()
    own = [row for row in packages if row.get("name") == PACKAGE]
    clients = [row for row in packages if row.get("name") == "vuoro-client"]
    if (len(own) != 1 or own[0].get("version") != version or len(clients) != 1
            or clients[0].get("version") != CLIENT_VERSION
            or clients[0].get("source") != {"url": CLIENT_URL}
            or clients[0].get("wheels") != [{"url": CLIENT_URL, "hash": f"sha256:{CLIENT_SHA}"}]):
        refuse()
    expected_dep = {"name": "vuoro-client", "marker": "python_full_version >= '3.12'", "url": CLIENT_URL}
    if expected_dep not in own[0].get("metadata", {}).get("requires-dist", []):
        refuse()
    if wheel is None:
        return version
    wheel_name = f"operator_projection-{version}-py3-none-any.whl"
    if wheel.name != wheel_name:
        refuse()
    dist_info = f"operator_projection-{version}.dist-info/"
    with ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != expected_wheel_members(version):
            refuse()
        built = BytesParser(policy=policy.default).parsebytes(archive.read(f"{dist_info}METADATA"))
    expected_wheel_pin = f"vuoro-client @ {CLIENT_URL}#sha256={CLIENT_SHA} ; python_version >= \"3.12\""
    requirements = built.get_all("Requires-Dist", [])
    if (built.get("Name") != PACKAGE or built.get("Version") != version
            or built.get("Requires-Python") != metadata.get("requires-python")
            or [row for row in requirements if row.startswith("vuoro-client")] != [expected_wheel_pin]):
        refuse()
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args()
    try:
        version = validate(Path(__file__).resolve().parents[1], args.tag, args.wheel)
    except (OSError, ValueError, KeyError, TypeError, BadZipFile) as error:
        # Keep filenames, owner metadata and parser details out of release logs.
        parser.exit(2, f"release contract refused ({type(error).__name__})\n")
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
