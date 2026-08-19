from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from .model import RevisionConflict


class MissingPrecondition(RuntimeError):
    """A revisioned mutation omitted its expected revision."""


@dataclass(frozen=True)
class MutationResult:
    previous_revision: str
    new_revision: str
    event_id: str
    idempotent_replay: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "result": "applied",
            "previous_revision": self.previous_revision,
            "new_revision": self.new_revision,
            "event_id": self.event_id,
            "idempotent_replay": self.idempotent_replay,
        }


class InMemoryRevisionedTaskStore:
    """Reference authority demonstrating atomic CAS and idempotency."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._revision = 1
        self._state: dict[str, Any] = {
            "task_id": "TASK-42",
            "title": "Demo revision-gated context",
            "state": "implementing",
            "next_actions": ["Run the acceptance sequence"],
            "claims_count": 0,
        }
        self._idempotency: dict[str, MutationResult] = {}

    def revision(self) -> str:
        with self._lock:
            return f"task:{self._revision}"

    def snapshot(self) -> tuple[str, dict[str, Any]]:
        with self._lock:
            return f"task:{self._revision}", dict(self._state)

    def mutate(
        self,
        *,
        expected_revision: str | None,
        patch: Mapping[str, Any],
        actor: str,
        idempotency_key: str,
    ) -> MutationResult:
        if expected_revision is None:
            raise MissingPrecondition("if_revision is required")
        if not actor:
            raise ValueError("actor is required")
        if not idempotency_key:
            raise ValueError("idempotency_key is required")

        with self._lock:
            replay = self._idempotency.get(idempotency_key)
            if replay is not None:
                return MutationResult(
                    previous_revision=replay.previous_revision,
                    new_revision=replay.new_revision,
                    event_id=replay.event_id,
                    idempotent_replay=True,
                )

            current = f"task:{self._revision}"
            if expected_revision != current:
                raise RevisionConflict(
                    f"expected {expected_revision}, current {current}"
                )

            previous = current
            self._state.update(dict(patch))
            self._revision += 1
            result = MutationResult(
                previous_revision=previous,
                new_revision=f"task:{self._revision}",
                event_id=str(uuid.uuid4()),
            )
            self._idempotency[idempotency_key] = result
            return result
