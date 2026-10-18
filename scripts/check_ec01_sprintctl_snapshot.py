#!/usr/bin/env python3
"""Offline check of Sprintctl source exports embedded in the EC-01 snapshot.

Run with the pinned Sprintctl lock environment and checkout at the exact commit;
this command imports source only and never opens a backend or network connection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "docs/architecture/2026-10-18-estate-first-consumer-contracts.json"
EXPECTED_ADAPTER_KIT = "0.2.2"


def git(checkout: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(checkout), *args], text=True).strip()


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-checkout", action="append", required=True, metavar="REPO=PATH",
        help="checkout containing the recorded git object(s); repeat for each public repo",
    )
    args = parser.parse_args()
    checkouts: dict[str, Path] = {}
    for item in args.source_checkout:
        repo, sep, path = item.partition("=")
        if not sep or not repo or repo in checkouts:
            fail(f"invalid or duplicate --source-checkout: {item}")
        checkouts[repo] = Path(path).resolve(strict=True)

    data = json.loads(SNAPSHOT.read_text())
    all_sources = [source for record in data["records"] for source in record.get("source", [])]
    needed = {source["repository"] for source in all_sources}
    if set(checkouts) != needed:
        fail(f"checkouts must cover exactly: {', '.join(sorted(needed))}")
    for source in all_sources:
        checkout = checkouts[source["repository"]]
        raw = subprocess.check_output([
            "git", "-C", str(checkout), "show", f"{source['commit']}:{source['path']}"
        ])
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            fail(f"source hash mismatch: {source['repository']}:{source['path']}@{source['commit']}")

    record = next(x for x in data["records"] if x["id"] == "sprintctl:work-catalog-source")
    checkout = checkouts["sprintctl"]
    commit = record["source"][0]["commit"]
    if git(checkout, "rev-parse", "HEAD") != commit:
        fail(f"Sprintctl checkout must be exactly {commit}")
    if git(checkout, "status", "--porcelain", "--untracked-files=no"):
        fail("Sprintctl tracked working tree must be clean")

    catalog = data["sprintctl_catalog_extraction"]
    cli_snapshot = data["sprintctl_cli_extraction"]
    snapshot_ops = catalog.get("operations", [])
    snapshot_names = [x.get("name") for x in snapshot_ops]
    conditional_expected = record["protocol"]["conditional_resource_schema_operations"]
    if len(snapshot_ops) != catalog.get("operation_count") or len(set(snapshot_names)) != len(snapshot_ops):
        fail("catalog snapshot operation count or name uniqueness is invalid")
    if len(snapshot_ops) - len(conditional_expected) != 103:
        fail("catalog snapshot conditional count is inconsistent")
    if cli_snapshot.get("served_route_count") != len(cli_snapshot.get("served_routes", [])):
        fail("CLI snapshot route count is inconsistent")
    if cli_snapshot.get("served_command_leaf_count") != len(cli_snapshot.get("command_dispositions", {})):
        fail("CLI snapshot disposition count is inconsistent")

    try:
        installed = version("vuoro-adapter-kit")
    except PackageNotFoundError:
        fail("locked vuoro-adapter-kit==0.2.2 is required")
    if installed != EXPECTED_ADAPTER_KIT:
        fail(f"expected locked vuoro-adapter-kit=={EXPECTED_ADAPTER_KIT}, found {installed}")
    if any(name == "sprintctl" or name.startswith("sprintctl.") for name in sys.modules):
        fail("Sprintctl modules were imported before source checkout binding")

    sys.path.insert(0, str(checkout))
    from click.testing import CliRunner
    import sprintctl
    from sprintctl import served_routes
    from sprintctl import vuoro_adapter
    from sprintctl.cli import cli

    for name, module in tuple(sys.modules.items()):
        if (name == "sprintctl" or name.startswith("sprintctl.")) and getattr(module, "__file__", None):
            origin = Path(module.__file__).resolve()
            if not origin.is_relative_to(checkout):
                fail(f"imported Sprintctl module is outside pinned checkout: {name} -> {origin}")
    true_specs = vuoro_adapter.catalog_operation_specs(resource_schema_available=True)
    false_specs = vuoro_adapter.catalog_operation_specs(resource_schema_available=False)
    if canonical(true_specs) != canonical(snapshot_ops):
        fail("resource_schema_available=True catalog differs from embedded source snapshot")
    conditional = sorted({x["name"] for x in true_specs} - {x["name"] for x in false_specs})
    if conditional != conditional_expected:
        fail("conditional resource operations differ from embedded source snapshot")
    if len(false_specs) != len(snapshot_ops) - len(conditional_expected):
        fail("resource_schema_available=False catalog count differs from conditional snapshot")
    summary = {
        "execution_semantics": dict(Counter(x["execution_semantics"] for x in true_specs)),
        "idempotency": dict(Counter(x["idempotency"] for x in true_specs)),
        "repo_scoped": dict(Counter(str(x["repo_scoped"]).lower() for x in true_specs)),
        "required_authority": dict(Counter(str(x["required_authority"]) for x in true_specs)),
    }
    if summary != record["protocol"]["summary"]:
        fail("catalog summary counters differ from embedded snapshot")

    routes = [asdict(x) for x in served_routes.SERVED_COMMAND_ROUTES]
    dispositions = served_routes.SERVED_COMMAND_DISPOSITIONS
    if len(routes) != cli_snapshot["served_route_count"] or canonical(routes) != canonical(cli_snapshot["served_routes"]):
        fail("served command routes differ from embedded source snapshot")
    if len(dispositions) != cli_snapshot["served_command_leaf_count"]:
        fail("served command disposition count differs from embedded snapshot")
    if dispositions != cli_snapshot["command_dispositions"]:
        fail("served command dispositions differ from embedded source snapshot")
    protocol_result = CliRunner().invoke(cli, ["agent-protocol", "--json"])
    if protocol_result.exit_code != 0:
        fail(f"agent-protocol --json failed: {protocol_result.exception!r}")
    if json.loads(protocol_result.output) != cli_snapshot["agent_protocol"]:
        fail("agent-protocol --json output differs from embedded source snapshot")
    print(
        f"verified {len(all_sources)} source hashes, {len(true_specs)}/{len(false_specs)} catalog exports, "
        f"{len(routes)} routes, {len(dispositions)} dispositions, and agent-protocol v3"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
