"""Portable, project-neutral execution mechanics for Agentops consumers."""

from .protocol import AttemptEnvelope, EventEnvelope, EvidenceRef, RunEnvelope
from .lock import verify_dispatch_lock
from .provider import FailoverDecision, decide_failover, harness_command_digest, validate_failover_policy

__all__ = ["AttemptEnvelope", "EventEnvelope", "EvidenceRef", "RunEnvelope",
           "verify_dispatch_lock", "FailoverDecision", "decide_failover",
           "harness_command_digest", "validate_failover_policy"]
