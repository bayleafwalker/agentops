"""Read-only sources: git at named commits, the ghcr tag map, and the vuoro authority."""

from __future__ import annotations

import concurrent.futures
import json
import urllib.request
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Protocol


class GitSource(Protocol):
    def show(self, repo: str, commit: str, path: str) -> str | None: ...

    def log(self, repo: str, ref: str, paths: Sequence[str], since: datetime | None = None,
            until: datetime | None = None) -> list[tuple[str, datetime]]: ...

    def resolve(self, repo: str, ref: str, before: datetime | None = None) -> str | None: ...


class ImageTags:
    def __init__(self, document: dict):
        self.document = document
        self.by_digest: dict[str, list[str]] = defaultdict(list)
        for tag, digest in document["tags"].items():
            self.by_digest[digest].append(tag)

    def source_commit(self, digest: str) -> str | None:
        return next((t[4:] for t in self.by_digest.get(digest, []) if t.startswith("sha-")), None)

    def release(self, digest: str | None) -> str | None:
        tags = sorted(self.by_digest.get(digest or "", []))
        return next((t for t in tags if t.startswith("vuoro-service-v")), None)


def fetch_image_tags(repository: str) -> dict:
    """Unauthenticated GET: anonymous pull token, tag list, then one manifest HEAD per tag."""
    accept = ", ".join([
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ])
    token_url = f"https://ghcr.io/token?scope=repository:{repository}:pull&service=ghcr.io"
    token = json.load(urllib.request.urlopen(token_url, timeout=30))["token"]

    def request(url: str, method: str = "GET"):
        headers = {"Authorization": f"Bearer {token}", "Accept": accept}
        return urllib.request.urlopen(urllib.request.Request(url, method=method, headers=headers), timeout=30)

    tags, url = [], f"https://ghcr.io/v2/{repository}/tags/list?n=1000"
    while url:
        response = request(url)
        tags += json.load(response)["tags"]
        link = response.headers.get("Link")
        url = "https://ghcr.io" + link.split(";")[0].strip("<>") if link else None

    def digest(tag: str) -> tuple[str, str]:
        manifest = request(f"https://ghcr.io/v2/{repository}/manifests/{tag}", "HEAD")
        return tag, manifest.headers["Docker-Content-Digest"]

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        resolved = dict(pool.map(digest, tags))
    return {
        "source": f"ghcr.io/v2/{repository}",
        "evaluator": "unauthenticated HTTP GET (anonymous pull token)",
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tags": dict(sorted(resolved.items())),
    }
