"""Stable JSON envelopes shared by local and hosted execution adapters.

Identity values are supplied by the owner/adapter. This module validates and
serializes them; it does not mint authority or choose a provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from types import MappingProxyType
from typing import Any, Mapping


PROTOCOL_VERSION = "agentops-execution/v1"


def _freeze_json(value: Any) -> Any:
    """Copy a JSON value into recursively immutable containers."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    copied = json.loads(encoded)
    if isinstance(copied, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in copied.items()})
    if isinstance(copied, list):
        return tuple(_freeze_json(item) for item in copied)
    return copied


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class EvidenceRef:
    """A content-addressed or owner-resolved reference to execution evidence."""

    uri: str
    digest: str | None = None
    media_type: str | None = None

    def to_json(self) -> dict[str, Any]:
        value = asdict(self)
        return {key: item for key, item in value.items() if item is not None}


@dataclass(frozen=True)
class RunEnvelope:
    """Caller-owned run identity and immutable execution inputs."""

    run_id: str
    project_id: str
    repo: str
    base: str
    adapter_id: str
    schema_version: str = PROTOCOL_VERSION
    budget: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        for name in ("run_id", "project_id", "repo", "base", "adapter_id"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.budget, Mapping):
            raise ValueError("budget must be a JSON object")
        object.__setattr__(self, "budget", _freeze_json(self.budget))

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "repo": self.repo,
            "base": self.base,
            "adapter_id": self.adapter_id,
            "schema_version": self.schema_version,
            "budget": _thaw_json(self.budget),
        }


@dataclass(frozen=True)
class AttemptEnvelope:
    """Stable identity and explicit command binding for one attempt."""

    run_id: str
    task_id: str
    attempt_id: str
    number: int
    command: tuple[str, ...]
    cwd: str
    timeout_seconds: float
    schema_version: str = PROTOCOL_VERSION
    environment: Mapping[str, str] = field(default_factory=dict)
    evidence_refs: tuple[EvidenceRef, ...] = ()
    adapter_data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        for name in ("run_id", "task_id", "attempt_id", "cwd"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must be a non-empty string")
        if not isinstance(self.number, int) or isinstance(self.number, bool) or self.number < 1:
            raise ValueError("number must be positive")
        if not self.command or not all(isinstance(part, str) for part in self.command):
            raise ValueError("command must contain one or more strings")
        if (not isinstance(self.timeout_seconds, (int, float))
                or isinstance(self.timeout_seconds, bool)
                or not math.isfinite(self.timeout_seconds)
                or self.timeout_seconds <= 0):
            raise ValueError("timeout_seconds must be positive")
        if not all(isinstance(key, str) and isinstance(value, str)
                   for key, value in self.environment.items()):
            raise ValueError("environment keys and values must be strings")
        if not isinstance(self.adapter_data, Mapping):
            raise ValueError("adapter_data must be a JSON object")
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "environment", _freeze_json(dict(self.environment)))
        object.__setattr__(self, "adapter_data", _freeze_json(self.adapter_data))

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "number": self.number,
            "cwd": self.cwd,
            "timeout_seconds": self.timeout_seconds,
            "schema_version": self.schema_version,
            "command": list(self.command),
            "environment": _thaw_json(self.environment),
            "adapter_data": _thaw_json(self.adapter_data),
            "evidence_refs": [ref.to_json() for ref in self.evidence_refs],
        }


@dataclass(frozen=True)
class EventEnvelope:
    """Append-only observation emitted by the execution host."""

    run_id: str
    task_id: str
    attempt_id: str | None
    sequence: int
    at: float
    kind: str
    body: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[EvidenceRef, ...] = ()
    schema_version: str = PROTOCOL_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PROTOCOL_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        if not self.run_id or not self.task_id or not self.kind:
            raise ValueError("run_id, task_id and kind are required")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise ValueError("sequence must be positive")
        if not math.isfinite(self.at):
            raise ValueError("at must be finite")
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "body", _freeze_json(self.body))

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "sequence": self.sequence,
            "at": self.at,
            "kind": self.kind,
            "body": _thaw_json(self.body),
            "evidence_refs": [ref.to_json() for ref in self.evidence_refs],
            "schema_version": self.schema_version,
        }
