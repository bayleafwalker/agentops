# Example state-protocol overlay

## Owned subject

- Subject: replace with one closed state object owned by this repository.
- Source of truth: replace with the authoritative row, file, or API resource.
- Semantic contract: `docs/protocols/example-lifecycle.md`.
- Context packet: `verification/contexts/example-lifecycle.json`.

## Verification boundary

- Survey and reconcile are read-only.
- Verification uses disposable state and sanitized evidence.
- Production credentials and copied production transition code never enter a packet.
- Repair requires separate authorization even when a full meta-dispatch is requested.

## Escalation

Stop when the source of truth is ambiguous, required evidence cannot be
produced without production mutation, or the requested claim is stronger than
the available oracle.
