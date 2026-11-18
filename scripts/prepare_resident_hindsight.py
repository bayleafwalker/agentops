#!/usr/bin/env python3
"""Materialize the pinned downstream Hindsight patch into a new local checkout.

This does not create a remote repository, push upstream, install dependencies,
run candidate code, or authorize a service. A failed attempt leaves its new
checkout available for inspection; it never deletes an existing directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "integrations" / "hindsight-resident" / "manifest.json"
UPSTREAM = "https://github.com/vectorize-io/hindsight.git"


def run(argv: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(argv, cwd=cwd, check=True, capture_output=True,
                          text=True, timeout=180).stdout.strip()


def prepare(destination: Path, manifest_path: Path = MANIFEST) -> dict:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "resident-hindsight-source/v1" or manifest.get("upstream") != UPSTREAM:
        raise ValueError("invalid pinned upstream manifest")
    for name, length in (("base_commit", 40), ("result_tree", 40), ("patch_sha256", 64)):
        if not isinstance(manifest.get(name), str) or not re.fullmatch("[0-9a-f]{" + str(length) + "}", manifest[name]):
            raise ValueError("invalid source digest")
    patch = manifest_path.parent / "downstream.patch"
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest["patch_sha256"]:
        raise ValueError("downstream patch digest mismatch")
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "clone", "--depth", "1", "--branch", "v1.2.1", "--no-checkout", UPSTREAM, str(destination)])
    # The tag is a transfer convenience, not identity or upgrade authority.
    if run(["git", "rev-parse", "HEAD"], destination) != manifest["base_commit"]:
        run(["git", "fetch", "--depth", "1", "origin", manifest["base_commit"]], destination)
    run(["git", "checkout", "-b", "resident/v1.2.1", manifest["base_commit"]], destination)
    run(["git", "remote", "rename", "origin", "upstream"], destination)
    run(["git", "apply", "--check", "--index", str(patch)], destination)
    run(["git", "apply", "--index", str(patch)], destination)
    if run(["git", "write-tree"], destination) != manifest["result_tree"]:
        raise ValueError("materialized tree does not match the tested downstream source")
    return {"checkout": str(destination), "base_commit": manifest["base_commit"],
            "result_tree": manifest["result_tree"], "state": "staged-local-source",
            "remote_fork_created": False, "execution_authorized": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(args.destination), sort_keys=True))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError):
        print('{"error":"source preparation failed; inspect the local checkout and pinned manifest"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
