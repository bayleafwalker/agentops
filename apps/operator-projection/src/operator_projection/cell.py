"""Every rendered value is a Cell carrying (transport, record revision or mtime, observed_at) (§11.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

KINDS = ("OBSERVED", "DECLARED", "ATTESTED", "BLIND")


@dataclass(frozen=True)
class Provenance:
    transport: str
    observed_at: str
    record_revision: str | None = None
    mtime: str | None = None

    def __post_init__(self) -> None:
        if not self.transport or not self.observed_at or not (self.record_revision or self.mtime):
            raise ValueError("provenance needs transport, record_revision or mtime, and observed_at")

    def to_dict(self) -> dict:
        stamp = {"record_revision": self.record_revision} if self.record_revision else {"mtime": self.mtime}
        return {"transport": self.transport, **stamp, "observed_at": self.observed_at}


@dataclass(frozen=True)
class Cell:
    kind: str
    value: Any
    prov: Provenance
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown cell kind {self.kind}")
        if not isinstance(self.prov, Provenance):
            raise TypeError("a cell needs a Provenance")
        if self.kind == "BLIND" and not self.reason:
            raise ValueError("a BLIND cell needs a reason")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value, "prov": self.prov.to_dict()} | ({"reason": self.reason} if self.reason else {})


def cell(kind: str, value: Any, transport: str, revision: str | None, observed_at: str, reason: str | None = None) -> dict:
    return Cell(kind, value, Provenance(transport, observed_at, revision), reason).to_dict()


def blind(reason: str, transport: str, revision: str | None, observed_at: str) -> dict:
    return cell("BLIND", None, transport, revision or "none", observed_at, reason)


def demote(value: dict, reason: str) -> dict:
    """A confident cell over an absent or stale source becomes BLIND; its provenance is kept."""
    prov = value["prov"]
    stamp = prov.get("record_revision") or prov.get("mtime")
    return blind(reason, prov["transport"], stamp, prov["observed_at"])


def is_cell(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") in KINDS and "prov" in value
