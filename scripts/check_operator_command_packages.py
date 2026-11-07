#!/usr/bin/env python3
"""Check operator command packages: `agentops check-operator-command-packages`.

Every `*.json` under docs/dispatch/operator-gates/ must be an
`operator-command-package/v1` document (schemas/operator-command-package.v1.schema.json)
and satisfy two cheap rules the schema cannot express:

* `ready` means nothing is left to find out: no blockers, every precondition
  carries a `verified_at`, and every command says `exact: true`;
* `blocked` names at least one blocker, and no blocker's resolver starts with
  "operator". Waiting on the operator is the thing a package exists to
  remove, so an unresolved step routes to build, repair or park.

The README beside the packages must list every package file, so the index a
human reads cannot drift from the files a tool reads.

Exit 0 when every package passes, 1 otherwise. Read-only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / "docs" / "dispatch" / "operator-gates"
SCHEMA = ROOT / "schemas" / "operator-command-package.v1.schema.json"
OPERATOR_FIRST = re.compile(r"^\W*(the\s+)?operator\b", re.IGNORECASE)
LINK = re.compile(r"\]\(([^)#\s]+)\)")


_SCHEMA_CHECK = None


def _schema_check():
    global _SCHEMA_CHECK
    if _SCHEMA_CHECK is not None:
        return _SCHEMA_CHECK
    spec = importlib.util.spec_from_file_location(
        "schema_check", ROOT / "scripts" / "schema_check.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    _SCHEMA_CHECK = module
    return module


def check_package(doc: dict, schema: dict) -> list[str]:
    errors = list(_schema_check().validate(doc, schema))
    if errors:
        return errors
    blockers = doc.get("blockers", [])
    if doc["readiness"] == "ready":
        if blockers:
            errors.append("readiness is ready but blockers are listed")
        for i, pre in enumerate(doc["preconditions"]):
            if pre["verified_at"] is None:
                errors.append(f"readiness is ready but preconditions[{i}] is unverified")
        for cmd in doc["commands"]:
            if cmd.get("exact") is not True:
                errors.append(f"readiness is ready but command step {cmd['step']} is not exact")
    else:
        if not blockers:
            errors.append("readiness is blocked but no blocker is named")
    for i, blocker in enumerate(blockers):
        if OPERATOR_FIRST.match(blocker["resolved_by"]):
            errors.append(
                f"blockers[{i}].resolved_by starts with 'operator'; name the build, repair or park item")
    steps = [c["step"] for c in doc["commands"]]
    if steps != list(range(1, len(steps) + 1)):
        errors.append(f"command steps must be 1..n in order, got {steps}")
    return errors


def check_directory(directory: Path, schema_path: Path = SCHEMA) -> dict[str, list[str]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    results: dict[str, list[str]] = {}
    files = sorted(directory.glob("*.json"))
    readme = directory / "README.md"
    readme_text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    linked = {t for t in LINK.findall(readme_text) if t.endswith(".json") and "/" not in t}
    ids: dict[str, str] = {}
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            results[path.name] = [f"not JSON: {exc}"]
            continue
        errors = check_package(doc, schema) if isinstance(doc, dict) else ["not an object"]
        package_id = doc.get("package_id") if isinstance(doc, dict) else None
        if package_id in ids:
            errors.append(f"package_id {package_id!r} also used by {ids[package_id]}")
        elif package_id:
            ids[package_id] = path.name
        if path.name not in linked:
            errors.append("not linked from README.md")
        results[path.name] = errors
    for target in sorted(linked - {p.name for p in files}):
        results[f"README.md -> {target}"] = ["README links a package file that does not exist"]
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR,
                        help="directory holding the packages (default: %(default)s)")
    parser.add_argument("--schema", type=Path, default=SCHEMA)
    args = parser.parse_args(argv)
    results = check_directory(args.dir, args.schema)
    if not results:
        print(f"no packages found in {args.dir}", file=sys.stderr)
        return 1
    failed = 0
    for name, errors in results.items():
        if errors:
            failed += 1
            print(f"{name}: FAIL")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{name}: ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
