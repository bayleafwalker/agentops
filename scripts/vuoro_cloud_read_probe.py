#!/usr/bin/env python3
"""Read kotona sprint names through Vuoro Cloud's read-only workspace API."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

BASE_URL = "https://api.vuoro.cloud"


class RefuseRedirects(HTTPRedirectHandler):
    """Do not forward a workspace bearer token to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "redirect refused", headers, fp)


def probe(
    credential_path: Path,
    repo_id: str,
    *,
    open_request: Callable[[Request], dict[str, Any]] | None = None,
    request_id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> dict[str, Any]:
    token = credential_path.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("credential file is empty")
    if not repo_id.strip():
        raise ValueError("repo_id must not be empty")

    def default_open(request: Request) -> dict[str, Any]:
        with build_opener(RefuseRedirects).open(request, timeout=20) as response:
            return json.loads(response.read())

    send = open_request or default_open
    common_headers = {
        "Authorization": f"Bearer {token}",
        "X-Vuoro-Client-Protocol": "1",
        "User-Agent": "agentops-operator",
        "Accept": "application/json",
    }
    handshake_request = Request(
        BASE_URL + "/api/meta/v1/handshake", headers=common_headers, method="GET"
    )
    send(handshake_request)
    catalog_request = Request(
        BASE_URL + "/api/catalog/v1", headers=common_headers, method="GET"
    )
    catalog = send(catalog_request)
    operation = next(
        (item for item in catalog.get("operations", []) if item.get("name") == "work.read.sprints"),
        None,
    )
    if not operation or operation.get("execution_semantics") != "read":
        raise ValueError("catalog does not declare work.read.sprints as read-only")

    request_id = request_id_factory()
    invocation = {
        "schema_version": "invocation/v1",
        "request_id": request_id,
        "operation": "work.read.sprints",
        "arguments": {},
        "catalog_revision": catalog["revision"],
        "basis_revision": None,
        "idempotency_key": None,
        "repo_id": repo_id,
    }
    invoke_request = Request(
        BASE_URL + "/api/invoke/v1",
        data=json.dumps(invocation).encode("utf-8"),
        headers={
            **common_headers,
            "Content-Type": "application/json",
            "X-Request-ID": request_id,
        },
        method="POST",
    )
    response = send(invoke_request)
    if response.get("status") != "accepted":
        error = response.get("error", {})
        raise ValueError(f"work.read.sprints rejected: {error.get('code', 'unknown')}")
    result = response.get("result") or {}
    sprints = result.get("sprints", [])
    names = [item["name"] for item in sprints if isinstance(item, dict) and isinstance(item.get("name"), str)]
    return {"sprint_count": len(names), "sprint_names": names}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("credential_file", type=Path)
    parser.add_argument("--repo-id", required=True)
    args = parser.parse_args()
    print(json.dumps(probe(args.credential_file, args.repo_id), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
