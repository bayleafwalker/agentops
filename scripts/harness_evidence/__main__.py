"""`python -m scripts.harness_evidence --dry-run <payload.json>`

Reads a payload fixture, builds the same OTLP/JSON batch `export()` would
send, and prints it -- without ever calling `export()`, so this never
performs network I/O regardless of `$OTEL_EXPORTER_OTLP_ENDPOINT`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .metrics import build_rate_limit_gauges
from .spans import build_session_span


def _build_batch(payload: dict[str, Any]) -> dict[str, Any]:
    batch: dict[str, Any] = {"spans": [build_session_span(payload)]}
    if payload.get("windows"):
        batch["metrics"] = [build_rate_limit_gauges(payload)]
    return batch


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.harness_evidence")
    parser.add_argument(
        "--dry-run",
        metavar="PAYLOAD",
        required=True,
        help="print the OTLP/JSON batch build_session_span()/build_rate_limit_gauges() "
        "would produce for this payload file, without exporting it",
    )
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.dry_run).read_text())
    batch = _build_batch(payload)
    print(json.dumps(batch, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
