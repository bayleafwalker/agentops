"""Durable source lineage and ingestion receipts, never a work scheduler."""
from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .policy import KINDS, Policy, canonical, digest
from .sources import read_source


class Store:
    def __init__(self, policy: Policy):
        self.policy = policy
        policy.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = policy.state_dir / "memory.sqlite3"
        # Deployment must make the entire state directory inaccessible to the
        # resident UID. chmod is not a privilege boundary against the same UID.
        self.db = sqlite3.connect(self.path, timeout=10)
        os.chmod(self.path, 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA synchronous=FULL;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS scope_bindings (
            scope_id TEXT PRIMARY KEY, identity BLOB NOT NULL);
          CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT NOT NULL, revision TEXT NOT NULL, scope_id TEXT NOT NULL,
            path TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
            body BLOB NOT NULL, captured REAL NOT NULL,
            PRIMARY KEY(source_id,revision));
          CREATE TABLE IF NOT EXISTS heads (
            source_id TEXT PRIMARY KEY, scope_id TEXT NOT NULL,
            revision TEXT NOT NULL, retracted INTEGER NOT NULL DEFAULT 0,
            reason TEXT, updated REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS ingestions (
            operation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, revision TEXT NOT NULL,
            scope_id TEXT NOT NULL, document_id TEXT UNIQUE NOT NULL,
            policy_sha256 TEXT NOT NULL, payload BLOB NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            updated REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS selections (
            sha256 TEXT PRIMARY KEY, body BLOB NOT NULL, created REAL NOT NULL);
          CREATE TABLE IF NOT EXISTS corrections (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL,
            previous_revision TEXT, revision TEXT NOT NULL,
            action TEXT NOT NULL, reason TEXT, created REAL NOT NULL);
        """)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for scope in policy.scopes.values():
                identity = canonical({"bank": scope.bank, "identity": scope.identity,
                                      "source_root": str(scope.source_root)})
                old = self.db.execute("SELECT identity FROM scope_bindings WHERE scope_id=?", (scope.id,)).fetchone()
                if old and old["identity"] != identity:
                    raise ValueError("existing scope identity changed; explicit migration required")
                self.db.execute("INSERT OR IGNORE INTO scope_bindings VALUES(?,?)", (scope.id, identity))

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def ingestion_lock(self):
        with (self.policy.state_dir / "ingestion.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def capture(self, scope_id: str, name: str, kind: str) -> dict:
        if kind not in KINDS:
            raise ValueError("unsupported source kind")
        scope = self.policy.scopes[scope_id]
        body = read_source(scope, name, self.policy.max_source_bytes)
        hashed = digest(body)
        source_id = "src-" + digest(canonical([scope_id, name]))
        revision = digest(canonical([hashed, kind]))
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute("SELECT * FROM heads WHERE source_id=?", (source_id,)).fetchone()
            if old and old["retracted"]:
                raise ValueError("source is retracted; explicit operator repair required")
            self.db.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?)",
                            (source_id, revision, scope_id, name, kind, hashed, body, time.time()))
            self.db.execute("INSERT INTO heads VALUES(?,?,?,0,NULL,?) ON CONFLICT(source_id) "
                            "DO UPDATE SET revision=excluded.revision,updated=excluded.updated",
                            (source_id, scope_id, revision, time.time()))
            if not old or old["revision"] != revision:
                self.db.execute("INSERT INTO corrections(source_id,previous_revision,revision,action,created) "
                                "VALUES(?,?,?,'capture',?)",
                                (source_id, old["revision"] if old else None, revision, time.time()))
        return {"source_id": source_id, "revision": revision, "sha256": hashed, "kind": kind}

    def retract(self, source_id: str, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1024:
            raise ValueError("retraction requires a bounded reason")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute("SELECT * FROM heads WHERE source_id=?", (source_id,)).fetchone()
            if not old:
                raise ValueError("unknown source")
            self.db.execute("UPDATE heads SET retracted=1,reason=?,updated=? WHERE source_id=?",
                            (reason, time.time(), source_id))
            self.db.execute("INSERT INTO corrections(source_id,previous_revision,revision,action,reason,created) "
                            "VALUES(?,?,?,'retract',?,?)",
                            (source_id, old["revision"], old["revision"], reason, time.time()))

    def current_sources(self, scope_id: str) -> dict:
        rows = self.db.execute("SELECT s.*,h.retracted FROM sources s JOIN heads h "
                               "ON s.source_id=h.source_id AND s.revision=h.revision WHERE s.scope_id=?",
                               (scope_id,)).fetchall()
        result = {}
        for row in rows:
            available = not row["retracted"]
            try:
                if available:
                    available = digest(read_source(self.policy.scopes[scope_id], row["path"],
                                                   self.policy.max_source_bytes)) == row["sha256"]
            except (OSError, ValueError, PermissionError, UnicodeError):
                available = False
            result[row["source_id"]] = {"revision": row["revision"], "sha256": row["sha256"],
                                        "available": available}
        return result

    def source(self, source_id: str, revision: str | None = None):
        if revision is None:
            head = self.db.execute("SELECT revision FROM heads WHERE source_id=?", (source_id,)).fetchone()
            if not head:
                raise ValueError("unknown source")
            revision = head["revision"]
        row = self.db.execute("SELECT * FROM sources WHERE source_id=? AND revision=?", (source_id, revision)).fetchone()
        if not row:
            raise ValueError("unknown source revision")
        return row

    def ingestion_status(self, scope_id: str) -> dict:
        counts = {r["status"]: r["n"] for r in self.db.execute(
            "SELECT status,count(*) n FROM ingestions WHERE scope_id=? GROUP BY status", (scope_id,))}
        uncaptured = self.db.execute("SELECT count(*) FROM heads h WHERE h.scope_id=? AND h.retracted=0 "
                                    "AND NOT EXISTS(SELECT 1 FROM ingestions i WHERE i.source_id=h.source_id "
                                    "AND i.revision=h.revision)", (scope_id,)).fetchone()[0]
        return {"states": counts, "not_submitted": uncaptured, "consolidation": "not-observed"}

    def save_selection(self, packet: dict) -> str:
        body = canonical(packet)
        sha = digest(body)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO selections VALUES(?,?,?)", (sha, body, time.time()))
        return sha

    def backup(self, destination: Path) -> None:
        if destination.exists():
            raise ValueError("backup destination already exists")
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            target = sqlite3.connect(destination)
            try:
                self.db.backup(target)
            finally:
                target.close()
            with destination.open("rb") as stream:
                os.fsync(stream.fileno())
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
