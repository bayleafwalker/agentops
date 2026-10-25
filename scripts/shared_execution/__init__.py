"""Portable, project-neutral execution mechanics for Agentops consumers."""

from .protocol import AttemptEnvelope, EventEnvelope, EvidenceRef, RunEnvelope
from .lock import verify_dispatch_lock

__all__ = ["AttemptEnvelope", "EventEnvelope", "EvidenceRef", "RunEnvelope",
           "verify_dispatch_lock"]
