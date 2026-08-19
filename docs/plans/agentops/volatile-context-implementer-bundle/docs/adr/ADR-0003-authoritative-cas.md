# ADR-0003: Enforce Revision Preconditions at the Authority

- Status: proposed
- Date: 2026-08-17

## Context

`PreToolUse` hooks can block recognized calls, but hook coverage is incomplete and shell parsing is inherently bypassable.

## Decision

All revisioned mutations require an expected revision and atomically compare it at the authoritative write boundary. Hooks perform early validation and return current context for better recovery, but are not relied upon for correctness.

## Consequences

- stale writes remain blocked when hooks are disabled or bypassed;
- CLI/API contracts change and need migration handling;
- callers must process typed conflict responses;
- post-mutation results can carry the new revision for immediate reinjection.

## Rollout rule

Do not enable strict hook blocking until authoritative CAS has acceptance evidence. Once CAS exists, keep it even if projection hooks are rolled back.
