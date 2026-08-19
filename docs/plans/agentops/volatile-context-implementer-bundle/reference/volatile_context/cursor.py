from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class CursorKey:
    dispatch_id: str
    harness: str
    session_id: str
    agent_id: str
    provider_id: str


class CursorStore(Protocol):
    def get(self, key: CursorKey) -> str | None: ...

    def set(self, key: CursorKey, revision: str, projection_id: str) -> None: ...

    def invalidate(
        self,
        *,
        dispatch_id: str,
        harness: str,
        session_id: str,
        agent_id: str,
        provider_ids: set[str] | None = None,
    ) -> None: ...


class InMemoryCursorStore:
    def __init__(self) -> None:
        self._values: dict[CursorKey, tuple[str, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: CursorKey) -> str | None:
        with self._lock:
            value = self._values.get(key)
            return value[0] if value else None

    def set(self, key: CursorKey, revision: str, projection_id: str) -> None:
        with self._lock:
            self._values[key] = (revision, projection_id)

    def invalidate(
        self,
        *,
        dispatch_id: str,
        harness: str,
        session_id: str,
        agent_id: str,
        provider_ids: set[str] | None = None,
    ) -> None:
        with self._lock:
            doomed = [
                key
                for key in self._values
                if key.dispatch_id == dispatch_id
                and key.harness == harness
                and key.session_id == session_id
                and key.agent_id == agent_id
                and (provider_ids is None or key.provider_id in provider_ids)
            ]
            for key in doomed:
                self._values.pop(key, None)


class SQLiteCursorStore:
    """Disposable cursor cache; never use this store for authorization."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS context_cursor (
                    dispatch_id TEXT NOT NULL,
                    harness TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    revision TEXT NOT NULL,
                    projection_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (dispatch_id, harness, session_id, agent_id, provider_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=2.0)

    def get(self, key: CursorKey) -> str | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT revision FROM context_cursor
                WHERE dispatch_id=? AND harness=? AND session_id=?
                  AND agent_id=? AND provider_id=?
                """,
                (
                    key.dispatch_id,
                    key.harness,
                    key.session_id,
                    key.agent_id,
                    key.provider_id,
                ),
            ).fetchone()
        return str(row[0]) if row else None

    def set(self, key: CursorKey, revision: str, projection_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO context_cursor (
                    dispatch_id, harness, session_id, agent_id, provider_id,
                    revision, projection_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dispatch_id, harness, session_id, agent_id, provider_id)
                DO UPDATE SET revision=excluded.revision,
                              projection_id=excluded.projection_id,
                              updated_at=CURRENT_TIMESTAMP
                """,
                (
                    key.dispatch_id,
                    key.harness,
                    key.session_id,
                    key.agent_id,
                    key.provider_id,
                    revision,
                    projection_id,
                ),
            )

    def invalidate(
        self,
        *,
        dispatch_id: str,
        harness: str,
        session_id: str,
        agent_id: str,
        provider_ids: set[str] | None = None,
    ) -> None:
        query = (
            "DELETE FROM context_cursor WHERE dispatch_id=? AND harness=? "
            "AND session_id=? AND agent_id=?"
        )
        params: list[str] = [dispatch_id, harness, session_id, agent_id]
        if provider_ids:
            placeholders = ",".join("?" for _ in provider_ids)
            query += f" AND provider_id IN ({placeholders})"
            params.extend(sorted(provider_ids))
        with self._lock, self._connect() as conn:
            conn.execute(query, params)
