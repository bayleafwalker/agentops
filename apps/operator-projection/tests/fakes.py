"""In-memory fakes for the injectable sources. All data here is synthetic."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


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
