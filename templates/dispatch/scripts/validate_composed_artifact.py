#!/usr/bin/env python3
"""Validate end-to-end CLI-to-deployment composition evidence.

The evidence document is intentionally self-contained. Release jobs populate it
from the owning repositories and a deployed catalog response; this validator
then proves that the same operation set and immutable adapter artifact survived
every composition boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "composed-artifact/v1"
DISPOSITIONS = {"catalog", "local", "unavailable"}


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _array(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _sha256(value: Any, field: str) -> str:
    text = _string(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return text


def _revision(value: Any, field: str) -> str:
    text = _string(value, field)
    if len(text) != 40 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field} must be a full lowercase Git revision")
    return text


def operation_digest(operations: list[str]) -> str:
    canonical = json.dumps(
        sorted(operations), ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _operations(section: dict[str, Any], field: str) -> list[str]:
    values = _array(section.get("operations"), f"{field}.operations")
    operations = [_string(value, f"{field}.operations[]") for value in values]
    if len(operations) != len(set(operations)):
        raise ValueError(f"{field}.operations contains duplicates")
    declared = _sha256(section.get("operations_sha256"), f"{field}.operations_sha256")
    actual = operation_digest(operations)
    if declared != actual:
        raise ValueError(
            f"{field}.operations_sha256 mismatch: declared {declared}, actual {actual}"
        )
    return operations


def validate(value: dict[str, Any]) -> None:
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    _string(value.get("domain"), "domain")

    cli = _object(value.get("cli"), "cli")
    facade = _object(value.get("served_facade"), "served_facade")
    adapter = _object(value.get("released_adapter"), "released_adapter")
    composition = _object(value.get("composition"), "composition")
    deployment = _object(value.get("deployment"), "deployment")

    for name, section in (
        ("cli", cli),
        ("served_facade", facade),
        ("released_adapter", adapter),
        ("composition", composition),
    ):
        _revision(section.get("source_revision"), f"{name}.source_revision")

    commands = _array(cli.get("commands"), "cli.commands")
    command_names: set[str] = set()
    catalog_routes: set[tuple[str, str]] = set()
    for index, raw in enumerate(commands):
        command = _object(raw, f"cli.commands[{index}]")
        name = _string(command.get("command"), f"cli.commands[{index}].command")
        if name in command_names:
            raise ValueError(f"cli.commands contains duplicate command {name!r}")
        command_names.add(name)
        disposition = command.get("disposition")
        if disposition not in DISPOSITIONS:
            raise ValueError(
                f"cli.commands[{index}].disposition must be one of {sorted(DISPOSITIONS)}"
            )
        operations = _array(command.get("operations", []), f"cli.commands[{index}].operations")
        operation_names = [
            _string(operation, f"cli.commands[{index}].operations[]")
            for operation in operations
        ]
        if disposition == "catalog" and not operation_names:
            raise ValueError(f"catalog command {name!r} must name an operation")
        if disposition != "catalog" and operation_names:
            raise ValueError(
                f"{disposition} command {name!r} must not name a served operation"
            )
        catalog_routes.update((name, operation) for operation in operation_names)

    facade_routes_raw = _array(facade.get("routes"), "served_facade.routes")
    facade_routes: set[tuple[str, str]] = set()
    for index, raw in enumerate(facade_routes_raw):
        route = _object(raw, f"served_facade.routes[{index}]")
        pair = (
            _string(route.get("command"), f"served_facade.routes[{index}].command"),
            _string(route.get("operation"), f"served_facade.routes[{index}].operation"),
        )
        if pair in facade_routes:
            raise ValueError(f"served_facade.routes contains duplicate route {pair!r}")
        facade_routes.add(pair)
    if facade_routes != catalog_routes:
        missing = sorted(catalog_routes - facade_routes)
        extra = sorted(facade_routes - catalog_routes)
        raise ValueError(f"CLI/facade route mismatch: missing={missing}, extra={extra}")

    facade_operations = {operation for _, operation in facade_routes}
    adapter_operations = set(_operations(adapter, "released_adapter"))
    composition_operations = set(_operations(composition, "composition"))
    deployed_operations = set(_operations(deployment, "deployment"))
    missing_adapter = sorted(facade_operations - adapter_operations)
    if missing_adapter:
        raise ValueError(
            f"released adapter is missing served facade operations: {missing_adapter}"
        )
    if adapter_operations != composition_operations:
        raise ValueError("released adapter and composition operation catalogs differ")
    if composition_operations != deployed_operations:
        raise ValueError("composition and deployed operation catalogs differ")

    adapter_sha = _sha256(adapter.get("artifact_sha256"), "released_adapter.artifact_sha256")
    if _sha256(composition.get("artifact_sha256"), "composition.artifact_sha256") != adapter_sha:
        raise ValueError("composition does not pin the released adapter artifact")
    if (
        _string(composition.get("distribution"), "composition.distribution")
        != _string(adapter.get("distribution"), "released_adapter.distribution")
        or _string(composition.get("distribution_version"), "composition.distribution_version")
        != _string(adapter.get("distribution_version"), "released_adapter.distribution_version")
    ):
        raise ValueError("composition distribution identity does not match released adapter")

    _sha256(composition.get("pin_manifest_sha256"), "composition.pin_manifest_sha256")
    image_digest = _string(deployment.get("image_digest"), "deployment.image_digest")
    if not image_digest.startswith("sha256:"):
        raise ValueError("deployment.image_digest must use the sha256: form")
    _sha256(image_digest.removeprefix("sha256:"), "deployment.image_digest")
    _string(deployment.get("environment"), "deployment.environment")
    _string(deployment.get("observed_at"), "deployment.observed_at")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    value = json.loads(args.manifest.read_text(encoding="utf-8"))
    validate(_object(value, str(args.manifest)))
    print(f"ok {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
