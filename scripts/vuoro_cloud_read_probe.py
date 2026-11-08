#!/usr/bin/env python3
"""Read Vuoro Cloud's public GET metadata without exposing credential data.

Work-item invocation is intentionally not attempted here: the service API
defines it as POST /api/invoke/v1, while this probe is restricted to GETs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

BASE_URL = "https://api.vuoro.cloud"


def probe(credential_path: Path, *, get_json=None) -> dict[str, Any]:
    token = credential_path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("credential file is empty")

    def default_get(path: str) -> dict[str, Any]:
        request = Request(
            BASE_URL + path,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Vuoro-Client-Protocol": "1",
                "Accept": "application/json",
            },
            method="GET",
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read())

    fetch = get_json or default_get
    handshake = fetch("/api/meta/v1/handshake")
    catalog = fetch("/api/catalog/v1")
    # Return only fields callers need for a bounded compatibility probe.
    operations = [
        {"id": item.get("name", ""), "title": item.get("summary", "")}
        for item in catalog.get("operations", [])
        if item.get("name", "").startswith("work.")
    ]
    return {
        "environment": handshake.get("environment", {}).get("name", ""),
        "work_operation_count": len(operations),
        "work_operations": operations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("credential_file", type=Path)
    args = parser.parse_args()
    result = probe(args.credential_file)
    print(json.dumps(result, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
