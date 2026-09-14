"""In-memory fakes for the injectable sources. All data here is synthetic."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


class FakeAuthorityClient:
    """Stands in for vuoro_client.AsyncVuoroClient over the recorded synthetic fixtures."""

    def __init__(self, results: dict | None = None, down: bool = False):
        self.results, self.down, self.invoked, self.repo_ids = results or {}, down, [], []
        self.semantics = {o["name"]: o["execution_semantics"] for o in fixture("catalog.json")["operations"]}

    async def handshake(self) -> dict:
        if self.down:
            raise ConnectionError("authority unreachable")
        return fixture("handshake.json")

    async def catalog(self, *, force_refresh: bool = False) -> dict:
        if self.down:
            raise ConnectionError("authority unreachable")
        served = fixture("catalog.json")
        for operation in served["operations"]:
            operation["execution_semantics"] = self.semantics[operation["name"]]
        return served

    async def invoke(self, operation_name: str, arguments, *, repo_id: str | None = None) -> dict:
        self.invoked.append((operation_name, arguments))
        self.repo_ids.append(repo_id)
        result = self.results[operation_name]
        return result(arguments) if callable(result) else result


class MemoryGit:
    """files[repo][commit][path] holds full snapshots; history[repo] lists (sha, iso date) oldest first."""

    def __init__(self, files: dict, history: dict[str, list[tuple[str, str]]]):
        self.files, self.history, self.calls = files, history, []

    def head(self, repo: str, ref: str) -> str:
        return self.history[repo][-1][0] if ref == "main" else ref

    def show(self, repo, commit, path):
        self.calls.append(("show", repo, commit, path))
        return self.files.get(repo, {}).get(self.head(repo, commit), {}).get(path)

    def log(self, repo, ref, paths, since=None, until=None):
        return [(sha, datetime.fromisoformat(when)) for sha, when in reversed(self.history.get(repo, []))]

    def resolve(self, repo, ref, before=None):
        older = [sha for sha, when in self.history.get(repo, []) if before is None or datetime.fromisoformat(when) < before]
        return older[-1] if older else None
