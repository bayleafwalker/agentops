#!/usr/bin/env python3
"""Project a synthetic Alloy receipt into metadata-only AgentOps evidence.

The input is the bounded JSON receipt produced by appservice's
``run_native309_alloy_acceptance.py``. This adapter validates the exact receipt
shape and emits only source identity, hashes, counts and mutation outcomes. It
never copies OTLP records, fixture payloads, credentials or response bodies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


PINNED_IMAGE = (
    "docker.io/grafana/alloy@sha256:"
    "2aa2099af76c0098d4af7a4d6e48f86cb66dc1a000222ad927a1c67c6542d13f"
)
SOURCE_BRANCH = "cloud/20261024/programme-06-telemetry"
MUTATIONS = {
    "row-only-session-identity": (False, 1),
    "usage-string-coercion": (False, 1),
    "usage-unsafe-integer": (False, 1),
    "model-conflict": (False, 1),
    "metric-temporality": (True, 0),
    "finite-token-partition": (True, 0),
    "interaction-terminal-only": (False, 1),
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
MAX_RECEIPT_BYTES = 32 * 1024


class ReceiptError(ValueError):
    """The receipt is not the expected synthetic acceptance record."""


def _exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReceiptError(f"{label} has an unexpected shape")
    return value


def validate_receipt(document: Any) -> dict[str, Any]:
    receipt = _exact_object(
        document,
        {
            "credentials_loaded",
            "external_exporters",
            "full_matrix",
            "image",
            "mutations",
            "production_access",
            "rendered_sha256",
            "schema",
            "synthetic_inputs_only",
        },
        "receipt",
    )
    if receipt["schema"] != "native309-alloy-acceptance/v1":
        raise ReceiptError("receipt schema is unsupported")
    if receipt["image"] != PINNED_IMAGE:
        raise ReceiptError("receipt image does not match the pinned Alloy digest")
    for field in ("credentials_loaded", "external_exporters", "production_access"):
        if receipt[field] is not False:
            raise ReceiptError(f"receipt does not prove {field}=false")
    if receipt["synthetic_inputs_only"] is not True:
        raise ReceiptError("receipt does not prove synthetic-only inputs")
    if not isinstance(receipt["rendered_sha256"], str) or not SHA256.fullmatch(
        receipt["rendered_sha256"]
    ):
        raise ReceiptError("rendered config digest is invalid")

    matrix = _exact_object(
        receipt["full_matrix"], {"cases", "exported", "passed", "refused"}, "matrix"
    )
    if (
        type(matrix["cases"]) is not int
        or type(matrix["exported"]) is not int
        or type(matrix["refused"]) is not int
        or matrix["cases"] != 62
        or matrix["exported"] != 54
        or matrix["refused"] != 8
        or matrix["passed"] is not True
    ):
        raise ReceiptError("full matrix did not match the expected passing result")

    rows = receipt["mutations"]
    if not isinstance(rows, list) or len(rows) != len(MUTATIONS):
        raise ReceiptError("mutation matrix is incomplete")
    by_name = {}
    mutation_keys = {
        "mutant_expected_drop",
        "mutant_export_count",
        "mutant_input_sent_after_control",
        "name",
        "passed",
        "positive_control_exported",
    }
    for value in rows:
        row = _exact_object(value, mutation_keys, "mutation")
        name = row["name"]
        if not isinstance(name, str) or name in by_name:
            raise ReceiptError("mutation names are invalid or duplicated")
        if name not in MUTATIONS:
            raise ReceiptError("mutation matrix contains an unknown case")
        expected_drop, expected_count = MUTATIONS[name]
        if (
            row["mutant_expected_drop"] is not expected_drop
            or type(row["mutant_export_count"]) is not int
            or row["mutant_export_count"] != expected_count
            or row["positive_control_exported"] is not True
            or row["mutant_input_sent_after_control"] is not True
            or row["passed"] is not True
        ):
            raise ReceiptError(f"mutation {name} did not match its passing oracle")
        by_name[name] = row
    if set(by_name) != set(MUTATIONS):
        raise ReceiptError("mutation matrix is missing a required case")
    return receipt


def project(receipt_bytes: bytes, *, source_commit: str) -> dict[str, Any]:
    if not isinstance(source_commit, str) or not COMMIT.fullmatch(source_commit):
        raise ReceiptError("source commit must be a full lowercase Git SHA")
    if len(receipt_bytes) > MAX_RECEIPT_BYTES:
        raise ReceiptError("receipt exceeds the 32 KiB metadata limit")
    try:
        document = json.loads(receipt_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ReceiptError("receipt is not valid JSON") from None
    receipt = validate_receipt(document)
    return {
        "schema": "agentops-native309-synthetic-acceptance/v1",
        "source": {
            "repository": "appservice",
            "branch": SOURCE_BRANCH,
            "commit": source_commit,
        },
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "collector_image": PINNED_IMAGE,
        "rendered_config_sha256": receipt["rendered_sha256"],
        "scope": "synthetic-only; no production access or external exporter",
        "full_matrix": {"cases": 62, "exported_records": 54, "refused": 8, "passed": True},
        "mutations": [
            {
                "name": name,
                "expected_drop": MUTATIONS[name][0],
                "exported_records": MUTATIONS[name][1],
                "positive_control_observed": True,
                "mutant_after_control": True,
                "passed": True,
            }
            for name in MUTATIONS
        ],
        "credentials_included": False,
        "telemetry_payloads_included": False,
        "production_access": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        raw = args.receipt.read_bytes()
        result = project(raw, source_commit=args.source_commit)
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (OSError, ReceiptError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
