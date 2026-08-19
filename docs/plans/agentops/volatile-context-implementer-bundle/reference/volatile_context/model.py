from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RevisionConflict(RuntimeError):
    """The provider could not render the exact revision requested."""


class ContextServiceError(RuntimeError):
    """The served projection endpoint failed or returned an invalid response."""


@dataclass(frozen=True)
class Binding:
    dispatch_id: str
    repo_id: str | None = None
    task_id: str | None = None
    host_id: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectionRequest:
    harness: str
    event: str
    mode: str
    dispatch_id: str
    session_id: str
    cwd: str
    repo_id: str | None = None
    agent_id: str | None = None
    provider_ids: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProjectionRequest":
        return cls(
            harness=str(value.get("harness", "reference")),
            event=str(value.get("event", "unknown")),
            mode=str(value.get("mode", "delta")),
            dispatch_id=str(value["dispatch_id"]),
            session_id=str(value["session_id"]),
            cwd=str(value.get("cwd", ".")),
            repo_id=(str(value["repo_id"]) if value.get("repo_id") is not None else None),
            agent_id=(str(value["agent_id"]) if value.get("agent_id") is not None else None),
            provider_ids=tuple(str(v) for v in value.get("provider_ids", ())),
        )


@dataclass(frozen=True)
class ProviderSnapshot:
    provider_id: str
    revision: str
    source_uri: str
    data: Mapping[str, Any]
    priority: int = 50
    budget_bytes: int = 1500
    status: str = "ok"


@dataclass(frozen=True)
class ProviderSummary:
    provider_id: str
    revision: str
    status: str
    bytes: int
    truncated: bool


@dataclass(frozen=True)
class ProjectionResult:
    projection_id: str
    mode: str
    observed_at: str
    context: str | None
    providers: tuple[ProviderSummary, ...]
    total_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "projection_id": self.projection_id,
            "mode": self.mode,
            "observed_at": self.observed_at,
            "context": self.context,
            "providers": [
                {
                    "id": p.provider_id,
                    "revision": p.revision,
                    "status": p.status,
                    "bytes": p.bytes,
                    "truncated": p.truncated,
                }
                for p in self.providers
            ],
            "total_bytes": self.total_bytes,
        }


@dataclass(frozen=True)
class MutationIntent:
    provider_id: str
    resource_id: str | None
    expected_revision: str | None
    tool_name: str
    tool_input: Any
    confident: bool


@dataclass(frozen=True)
class MutationValidation:
    allowed: bool
    reason: str | None
    current_revision: str | None
    context: str | None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MutationValidation":
        return cls(
            allowed=bool(value.get("allowed")),
            reason=(str(value["reason"]) if value.get("reason") is not None else None),
            current_revision=(
                str(value["current_revision"])
                if value.get("current_revision") is not None
                else None
            ),
            context=(str(value["context"]) if value.get("context") is not None else None),
        )
