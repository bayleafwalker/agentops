#!/usr/bin/env python3
"""Check an EC-01 owner-source inventory against exact local Git objects."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPOS = {"cred-broker", "datacluster-template", "acceptance-lab", "homelab-analytics"}
UNKNOWN = "unknown"

def fail(message: str) -> None:
    raise ValueError(message)

def check(path: Path, roots: dict[str, Path]) -> None:
    data = json.loads(path.read_text())
    if data.get("schema") != "agentops-estate-owner-source-interfaces/v1":
        fail("unexpected schema")
    repos = data.get("repositories", [])
    if {r.get("repo") for r in repos} != REPOS:
        fail("repository set must contain exactly the four scoped owners")
    revisions: dict[str, str] = {}
    for repo in repos:
        name, rev = repo.get("repo"), repo.get("source_revision")
        if name not in roots or not isinstance(rev, str) or len(rev) != 40:
            fail(f"missing root or full source revision for {name}")
        revisions[name] = rev
        visibility = repo.get("visibility_observation", {})
        if visibility.get("value") != "public" or not visibility.get("observed_at"):
            fail(f"{name}: public visibility observation missing")
        for item in repo.get("source_files", []):
            p, expected = item.get("path"), item.get("sha256")
            if not p or not expected or p.startswith("/") or ".." in Path(p).parts:
                fail(f"{name}: invalid evidence path")
            raw = subprocess.check_output(["git", "-C", str(roots[name]), "show", f"{rev}:{p}"], stderr=subprocess.DEVNULL)
            if hashlib.sha256(raw).hexdigest() != expected:
                fail(f"{name}:{p}: source hash mismatch")
    ids: set[str] = set()
    for item in data.get("interfaces", []):
        iid, repo, owner = item.get("id"), item.get("repo"), item.get("owner")
        if not iid or iid in ids:
            fail("interface IDs must be present and unique")
        ids.add(iid)
        if repo not in REPOS or owner != next(r["owner"] for r in repos if r["repo"] == repo):
            fail(f"{iid}: owner/repository mapping mismatch")
        if item.get("source_revision") != revisions[repo]:
            fail(f"{iid}: source revision mismatch")
        known_paths = {f["path"] for r in repos if r["repo"] == repo for f in r["source_files"]}
        for f in item.get("source_files", []):
            if f["path"] not in known_paths:
                fail(f"{iid}: interface evidence missing from repository evidence list")
        for field in ("live_use", "configured_consumers", "compatibility_cutover_rollback", "disposition"):
            if not item.get(field):
                fail(f"{iid}: {field} must be explicit")
        if item["live_use"] != UNKNOWN and "unknown" not in item["live_use"].lower():
            fail(f"{iid}: source-only record cannot claim measured live use")
        if item["configured_consumers"] != UNKNOWN and "unknown" not in item["configured_consumers"].lower():
            fail(f"{iid}: configured consumers must remain explicitly unknown")
    if not ids or {i["owner"] for i in data["interfaces"]} != {r["owner"] for r in repos}:
        fail("each scoped owner must have at least one interface record")

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inventory", type=Path)
    ap.add_argument("--repo", action="append", default=[], metavar="NAME=PATH", help="local Git checkout; repeat for each repository")
    ns = ap.parse_args()
    roots = {}
    for value in ns.repo:
        if "=" not in value:
            ap.error("--repo must be NAME=PATH")
        name, path = value.split("=", 1)
        roots[name] = Path(path)
    try:
        check(ns.inventory, roots)
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"EC-01 source inventory check failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print("EC-01 source inventory: exact revisions and hashes verified")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
