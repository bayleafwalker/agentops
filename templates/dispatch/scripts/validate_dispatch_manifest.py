#!/usr/bin/env python3
"""Validate dispatch manifests against ``templates/dispatch/manifest.schema.json``.

Every repository in this fleet carries a ``<name>.dispatch.json`` and the
agentops test suite can only reach the ones inside agentops. This is the
standalone checker the sibling repositories run for themselves: ``main(argv)``
returns an int exit code and the ``__main__`` block raises ``SystemExit`` on
it, so the tool works as a command from any checkout.

Two names are pinned surface, exercised by the oracle:

* ``resolve_template_root(manifest, manifest_path) -> Path`` -- where one
  manifest's skills directory listing is expected to live. Absent from the
  manifest, the schema's own ``default`` is used (read out of the schema file,
  not hard-coded); present and absolute, it is used verbatim; present and
  relative, it resolves against the directory holding the manifest, not the
  process CWD, so the same manifest validates the same way from any shell.
* ``validate`` -- a module-level alias for ``schema_check.validate``, kept
  substitutable so ``UnsupportedKeyword`` handling can be exercised.

Reporting. Every manifest named on the command line is checked and every
violation is printed, each naming the file it came from; the exit code reflects
'any failed', never the last file. Missing file, unparseable file, and schema
violation are distinguished by message: only a schema violation carries
``schema_check`` breadcrumbs. Beyond the schema, ``skills.selected`` is
cross-checked against the directories that exist under the resolved template
root -- the schema enum is a copy of that listing, so the directory is the
source of truth. A template root that does not exist on this machine is a
warning, not a violation: it is the normal cross-repo case, and the enum is
still enforced so the run is not silently weakened.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schema_check  # noqa: E402

validate = schema_check.validate
UnsupportedKeyword = schema_check.UnsupportedKeyword

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "manifest.schema.json"
#: Formats asserted when checking a manifest against its schema. Passing this
#: to validate() is what makes the declared list the enforced list.
ASSERTED_SCHEMA_FORMATS = ("uuid",)
_SCHEMA_DOC = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _schema_default_template_root() -> str:
    return _SCHEMA_DOC["properties"]["skills"]["properties"]["template_root"][
        "default"
    ]


def resolve_template_root(manifest, manifest_path):
    """Return the directory where this manifest's skills are expected to live."""
    root = None
    skills = manifest.get("skills") if isinstance(manifest, dict) else None
    if isinstance(skills, dict):
        root = skills.get("template_root")
    if root is None:
        root = _schema_default_template_root()
    candidate = Path(root)
    if not candidate.is_absolute():
        candidate = Path(manifest_path).parent / candidate
    return candidate


def _check_manifest(path):
    """Return (errors, warnings) for one manifest file."""
    path = Path(path)
    if not path.is_file():
        return [f"no such file or directory: {path}"], []

    try:
        instance = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid JSON: {exc}"], []

    errors = []
    warnings = []
    try:
        # assert_formats, not bare validate: manifest.schema.json declares
        # "format": "uuid" and this is the repository's dedicated manifest
        # schema checker, so leaving format as an annotation here would mean the
        # residual V6-I identified is closed in one validator and open in the
        # one most callers actually reach.
        violations = validate(instance, _SCHEMA_DOC, assert_formats=ASSERTED_SCHEMA_FORMATS)
    except UnsupportedKeyword as exc:
        errors.append(
            f"schema cannot be fully enforced: {exc}")
        return errors, warnings
    errors.extend(violations)

    if isinstance(instance, dict):
        skills = instance.get("skills")
        if isinstance(skills, dict) and isinstance(skills.get("selected"), list):
            root = resolve_template_root(instance, path)
            if not root.is_dir():
                warnings.append(
                    f"skills template root {root} does not exist; skipping "
                    f"the directory cross-check")
            else:
                for skill in skills["selected"]:
                    if not (root / skill).is_dir():
                        errors.append(
                            f"selected skill {skill!r} has no directory under "
                            f"{root}")

    return errors, warnings


def main(argv=None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    paths = [Path(arg) for arg in argv]
    if not paths:
        print(
            f"usage: {Path(sys.argv[0]).name} <manifest.dispatch.json> [...]",
            file=sys.stderr,
        )
        return 2

    any_failed = False
    for path in paths:
        errors, warnings = _check_manifest(path)
        for warning in warnings:
            print(f"warning: {path}: {warning}")
        if errors:
            any_failed = True
            for error in errors:
                print(f"error: {path}: {error}")
        else:
            print(f"ok {path}")
    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
