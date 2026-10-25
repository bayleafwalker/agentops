"""Shared V2.1 durable runtime mechanics.

The table shapes, atomic replacement, legal lifecycle edges, and lock behavior
are lifted from the Mars Founder V2.1 dispatch runtime. Product and provider
policy lives in consumer adapters.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import uuid
from typing import Any


STATES = {"PLANNED", "RUNNING", "READY", "VERIFYING", "REVIEWED", "MERGING",
          "MERGED", "BLOCKED", "QUARANTINED"}
EXITS = {"committed", "limit_hit", "transport_error", "timeout", "no_change", "check_failed"}
EDGES = {
    "PLANNED": {"RUNNING"},
    "RUNNING": {"READY", "PLANNED"},
    "READY": {"VERIFYING"},
    "VERIFYING": {"READY", "REVIEWED"},
    "REVIEWED": {"VERIFYING", "MERGING"},
    "MERGING": {"MERGED", "VERIFYING"},
    "BLOCKED": {"PLANNED", "READY"},
    "QUARANTINED": {"PLANNED", "READY"},
}


def atomic(path: str | Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("w") as out:
        json.dump(value, out, indent=2, sort_keys=True)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read(path: str | Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def git(repo: str | Path, *args: str, check: bool = True):
    process = subprocess.run(["git", "-C", str(repo), *map(str, args)], text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if check and process.returncode:
        raise RuntimeError(f"git {args}: {process.stderr.strip()}")
    return process.stdout.strip() if check else process


def ancestor(repo: str | Path, old: str | None, new: str) -> bool:
    return bool(old) and git(repo, "merge-base", "--is-ancestor", old, new, check=False).returncode == 0


def identity(pid: int) -> str | None:
    try:
        raw = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return None if raw[0] == "Z" else raw[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def alive(info: dict[str, Any] | None) -> bool:
    return bool(info and info.get("start") and identity(info["pid"]) == info["start"])


class Store:
    """The V2.1 SQLite task, events and metadata journal with original edges."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lease = (self.root / "driver.lock").open("a")
        fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.db = sqlite3.connect(self.root / "state.sqlite3")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, at REAL, kind TEXT, task TEXT, body TEXT);
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, body TEXT);
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()
        self.lease.close()

    def meta(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT body FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def setmeta(self, key: str, value: Any) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, json.dumps(value)))

    def events(self) -> list[dict[str, Any]]:
        return [dict(json.loads(body), seq=sequence, at=at, kind=kind, task=task)
                for sequence, at, kind, task, body in
                self.db.execute("SELECT * FROM events ORDER BY seq")]

    def event(self, kind: str, task: str | None = None, **body: Any) -> None:
        with self.db:
            self.db.execute("INSERT INTO events(at,kind,task,body) VALUES (?,?,?,?)",
                            (time.time(), kind, task, json.dumps(body)))

    def tasks(self) -> list[dict[str, Any]]:
        return [json.loads(row[0]) for row in self.db.execute("SELECT body FROM tasks ORDER BY rowid")]

    def save(self, task: dict[str, Any], state: str | None = None, **updates: Any) -> dict[str, Any]:
        task = dict(task)
        old = task.get("state")
        state = state or old or "PLANNED"
        if state not in STATES or (old and state != old and state not in EDGES.get(old, set())
                                   and not (old != "MERGED" and state in {"BLOCKED", "QUARANTINED"})):
            raise ValueError(f"illegal transition {old} -> {state}")
        task.update(updates, state=state, updated_at=time.time())
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO tasks VALUES (?,?)", (task["id"], json.dumps(task)))
            self.db.execute("INSERT INTO events(at,kind,task,body) VALUES (?,?,?,?)",
                            (time.time(), "transition", task["id"], json.dumps(task)))
        return task

    def journal(self) -> None:
        lines = ["# Dispatch v2 journal", "",
                 "SQLite events are authoritative; this file is a recoverable projection.", ""]
        for event in self.events():
            stamp = dt.datetime.fromtimestamp(event["at"], dt.timezone.utc).isoformat()
            body = event
            if event["kind"] == "transition":
                body = {key: event.get(key) for key in ["state", "run_id", "worker_commit",
                        "verified_base", "verified_tip", "model", "harness", "host", "cause",
                        "attempt", "waiting_cause", "accepted_at"]}
                body["check_log"] = (event.get("check") or {}).get("log")
                body["review_evidence"] = (event.get("review") or {}).get("evidence")
            lines.append(f"- {event['seq']} {stamp} {event['kind']} {event.get('task') or ''}: "
                         + json.dumps(body, sort_keys=True))
        target = self.root / "journal.md"
        temporary = self.root / "journal.md.tmp"
        with temporary.open("w") as out:
            out.write("\n".join(lines) + "\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, target)


def overlaps(a: list[str], b: list[str]) -> bool:
    for left in a:
        for right in b:
            if (left == "." or right == "." or left == right
                    or left.startswith(right.rstrip("/") + "/")
                    or right.startswith(left.rstrip("/") + "/")):
                return True
    return False
