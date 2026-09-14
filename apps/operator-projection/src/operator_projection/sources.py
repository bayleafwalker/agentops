"""Read-only sources: git at named commits, the ghcr tag map, and the vuoro authority."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

FULL_SHA = re.compile(r"[0-9a-f]{40}")


class SourceUnavailable(RuntimeError):
    """A source could not be read; the panels that need it render BLIND with this message."""


class GitSource(Protocol):
    def show(self, repo: str, commit: str, path: str) -> str | None: ...

    def log(self, repo: str, ref: str, paths: Sequence[str], since: datetime | None = None,
            until: datetime | None = None) -> list[tuple[str, datetime]]: ...

    def resolve(self, repo: str, ref: str, before: datetime | None = None) -> str | None: ...


def stamp(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class GitHubRest:
    """GitSource over api.github.com. Revalidates with ETags; content at a full sha is cached for good."""

    def __init__(self, repos: dict[str, str], token: str | None = None, client: httpx.Client | None = None):
        self.repos = repos  # repo id -> "owner/name"
        self.http = client or httpx.Client(base_url="https://api.github.com", timeout=30)
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        self.headers |= {"Authorization": f"Bearer {token}"} if token else {}
        self._etags: dict[str, tuple[str, object]] = {}
        self._immutable: dict[tuple[str, str, str], str | None] = {}
        self._readable: set[str] = set()

    def get(self, path: str, params: dict | None = None, raw: bool = False):
        key = f"{path}?{sorted((params or {}).items())}{raw}"
        headers = self.headers | ({"Accept": "application/vnd.github.raw+json"} if raw else {})
        cached = self._etags.get(key)
        response = self.http.get(path, params=params, headers=headers | ({"If-None-Match": cached[0]} if cached else {}))
        if response.status_code == 304 and cached:
            return cached[1]
        if response.status_code == 404:
            return None
        if response.is_error:
            raise SourceUnavailable(f"GitHub answered {response.status_code} for {path}")
        body = response.text if raw else response.json()
        if response.headers.get("etag"):
            self._etags[key] = (response.headers["etag"], body)
        return body

    def repo(self, repo: str) -> str:
        name = self.repos[repo]
        if name not in self._readable:
            # A private repository answers 404 without a credential; never mistake that for an absent file.
            if self.get(f"/repos/{name}") is None:
                raise SourceUnavailable(f"{name} is not readable with the configured GitHub credential")
            self._readable.add(name)
        return f"/repos/{name}"

    def show(self, repo: str, commit: str, path: str) -> str | None:
        key = (repo, commit, path)
        if key in self._immutable:
            return self._immutable[key]
        text = self.get(f"{self.repo(repo)}/contents/{path}", {"ref": commit}, raw=True)
        if FULL_SHA.fullmatch(commit):
            self._immutable[key] = text
        return text

    def log(self, repo: str, ref: str, paths: Sequence[str], since: datetime | None = None,
            until: datetime | None = None) -> list[tuple[str, datetime]]:
        window = {"sha": ref, "per_page": 100} | ({"since": stamp(since)} if since else {}) | ({"until": stamp(until)} if until else {})
        commits: dict[str, datetime] = {}
        for path in paths:
            page = 1
            while True:
                batch = self.get(f"{self.repo(repo)}/commits", window | {"path": path, "page": page}) or []
                commits |= {c["sha"]: datetime.fromisoformat(c["commit"]["committer"]["date"].replace("Z", "+00:00")) for c in batch}
                if len(batch) < 100:
                    break
                page += 1
        return sorted(commits.items(), key=lambda item: item[1], reverse=True)

    def resolve(self, repo: str, ref: str, before: datetime | None = None) -> str | None:
        if before is None:
            found = self.get(f"{self.repo(repo)}/commits/{ref}")
            return found["sha"] if found else None
        found = self.get(f"{self.repo(repo)}/commits", {"sha": ref, "until": stamp(before), "per_page": 1})
        return found[0]["sha"] if found else None


READ_OPS = frozenset({"work.project.context", "work.read.handoff", "work.read.context-candidates"})


class ReadRefused(PermissionError):
    """The generator never sends an operation outside the read allowlist (§6.4, §11.5)."""


class AuthorityClient(Protocol):
    async def handshake(self) -> dict: ...

    async def catalog(self, *, force_refresh: bool = False) -> dict: ...

    async def invoke(self, operation_name: str, arguments: Any) -> Any: ...


class Authority:
    """The only path to the vuoro authority: handshake, catalog, and allowlisted read-semantics operations."""

    def __init__(self, client: AuthorityClient, has_credential: Callable[[], bool]):
        self.client, self.has_credential = client, has_credential
        self.loop = asyncio.new_event_loop()
        self.served: dict | None = None

    def handshake(self) -> dict:
        return self.loop.run_until_complete(self.client.handshake())

    def catalog(self) -> dict:
        self.served = self.loop.run_until_complete(self.client.catalog())
        return self.served

    def read(self, operation: str, arguments: dict) -> Any:
        if operation not in READ_OPS:
            raise ReadRefused(f"{operation} is not on the read allowlist")
        served = next((o for o in (self.served or {}).get("operations", []) if o["name"] == operation), None)
        if served is None or served.get("execution_semantics") != "read":
            raise ReadRefused(f"{operation} is not read-semantics in the catalog fetched this generation")
        if not self.has_credential():
            raise SourceUnavailable("no generator credential (work:read, work:project-read)")
        return self.loop.run_until_complete(self.client.invoke(operation, arguments))


def open_authority(profile: dict) -> Authority:
    """Build the vuoro-client transport from the profile ConfigMap; the credential is read only on invoke."""
    from vuoro_client import AsyncVuoroClient, Profile  # absent on Python 3.11: the caller renders BLIND

    reference = profile["credential_ref"]
    path = Path(reference.removeprefix("file:")).expanduser()
    client = AsyncVuoroClient(
        Profile(name="operator-projection", endpoint=profile["authority_url"], credential_ref=reference),
        lambda _ref: path.read_text().strip(),
    )
    return Authority(client, lambda: reference.startswith("file:") and path.is_file())


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
